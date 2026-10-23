"""Bounded tool-calling loop: LLM proposes tool calls, we validate and execute them.

Guarantees:
- At most ``max_iterations`` model calls, ``max_tool_calls`` tool executions, and
  ``max_input_tokens`` cumulative input tokens per request.
- Tools run sequentially on one read-only session (AsyncSession is not concurrency-safe).
- Any final answer stating account-specific monetary figures or invoice/customer IDs without
  a supporting tool result is withheld as ungrounded.
- Citations are verified against chunks actually retrieved during the turn; hallucinated
  citation tags (`[DOC-FAKE#C99]`) are stripped from the final answer and never returned.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.ai.llm import ChatMessage, LLMClient
from app.ai.prompts import build_system_prompt
from app.ai.tools import (
    DOCUMENT_RAG_TOOLS,
    SQL_BUSINESS_TOOLS,
    TOOLS,
    ToolExecution,
    execute_tool,
)
from app.business.service import BusinessDataService
from app.documents.service import DocumentRetrievalService
from app.schemas.chat import DocumentCitation

ChatStatus = Literal["ok", "no_data", "limit_reached", "ungrounded"]

LIMIT_REACHED_ANSWER = (
    "I couldn't complete this request within the allowed number of data lookups. "
    "Please ask a narrower question (for example, one customer or one time period)."
)
UNGROUNDED_ANSWER = (
    "I couldn't verify an answer against your business data, so I'm not going to guess. "
    "Please rephrase the question, for example by naming a time period or customer."
)
EMPTY_ANSWER = "I wasn't able to produce an answer. Please try rephrasing your question."
NO_ACCOUNT_ANSWER = (
    "No business data is linked to your account yet, so there is nothing to analyze."
)

# Money-like figures: 1,234.56 | $120 | USD 120 | 120 USD
_MONEY_PATTERN = re.compile(
    r"(\d[\d,]*\.\d{2}\b)|([$€£]\s?\d)|(\b[A-Z]{3}\s?\d)|(\d[\d,]*\s?(USD|EUR|GBP)\b)"
)
_NUMERIC_TOKEN_RE = re.compile(r"\b\d[\d,]*(?:\.\d{2})?\b")
_RECORD_ID_RE = re.compile(r"\b(?:INV-[A-Z0-9-]+|CUST-\d{4})\b")
_CITATION_TAG_RE = re.compile(r"\[(DOC-[A-Z0-9-]+#C\d{2,3})\]")


@dataclass
class ChatOutcome:
    answer: str
    status: ChatStatus
    tool_calls: list[ToolExecution] = field(default_factory=list)
    citations: list[DocumentCitation] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


def _assistant_tool_message(
    content: str | None, calls: Sequence[tuple[str, str, str]]
) -> ChatMessage:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
            for cid, name, args in calls
        ],
    }


def _collect_retrieved_chunks(
    executions: Sequence[ToolExecution],
) -> dict[str, DocumentCitation]:
    """Gather all chunks returned by successful search_policy_documents executions."""
    by_id: dict[str, DocumentCitation] = {}
    for ex in executions:
        if not ex.ok or ex.name not in DOCUMENT_RAG_TOOLS or not ex.result:
            continue
        raw_chunks = ex.result.get("chunks")
        if not isinstance(raw_chunks, list):
            continue
        for item in raw_chunks:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("citation_id", ""))
            if not cid or cid in by_id:
                continue
            eff_raw = item.get("effective_date")
            eff_date = (
                date.fromisoformat(eff_raw)
                if isinstance(eff_raw, str)
                else eff_raw
                if isinstance(eff_raw, date)
                else date(2026, 1, 1)
            )
            by_id[cid] = DocumentCitation(
                citation_id=cid,
                doc_key=str(item.get("doc_key", "")),
                document_title=str(item.get("document_title", "")),
                category=str(item.get("category", "")),
                version=str(item.get("version", "")),
                effective_date=eff_date,
                section_title=str(item.get("section_title", "")),
                page_number=int(item.get("page_number", 1)),
                similarity_score=float(item.get("similarity_score", 0.0)),
                excerpt=str(item.get("untrusted_document_excerpt", "")),
            )
    return by_id


def verify_and_extract_citations(
    answer: str, executions: Sequence[ToolExecution]
) -> tuple[str, list[DocumentCitation]]:
    """Strip unverified `[DOC-...#C..]` tags and return verified DocumentCitation items."""
    available = _collect_retrieved_chunks(executions)
    cited_ids_in_order: list[str] = []

    for match in _CITATION_TAG_RE.finditer(answer):
        cid = match.group(1)
        if cid in available and cid not in cited_ids_in_order:
            cited_ids_in_order.append(cid)

    def _replace_tag(m: re.Match[str]) -> str:
        cid = m.group(1)
        return m.group(0) if cid in available else ""

    cleaned_answer = _CITATION_TAG_RE.sub(_replace_tag, answer)
    # Clean up any double spaces created by stripping invalid citation tags
    cleaned_answer = re.sub(r"  +", " ", cleaned_answer).strip()

    citations = [available[cid] for cid in cited_ids_in_order] if cited_ids_in_order else []

    return cleaned_answer, citations


def looks_ungrounded(answer: str, executions: Sequence[ToolExecution]) -> bool:
    """True when the answer states money figures or record IDs without supporting tool data."""
    sql_ok = any(ex.ok and ex.name in SQL_BUSINESS_TOOLS for ex in executions)
    if sql_ok:
        return False

    doc_chunks = _collect_retrieved_chunks(executions)
    has_money = bool(_MONEY_PATTERN.search(answer))
    has_record_id = bool(_RECORD_ID_RE.search(answer))

    if not doc_chunks:
        return has_money

    # Only document tools ran (no SQL tools). Reject if the answer invents invoice/customer IDs
    # or monetary numbers that do not appear anywhere in the retrieved policy chunks.
    combined_excerpts = " ".join(c.excerpt for c in doc_chunks.values())
    if has_record_id:
        for rec_id in _RECORD_ID_RE.findall(answer):
            if rec_id not in combined_excerpts:
                return True

    if has_money:
        excerpt_numbers = {n.replace(",", "") for n in _NUMERIC_TOKEN_RE.findall(combined_excerpts)}
        # Find numbers adjacent to currency/money markers in the answer
        for m in _MONEY_PATTERN.finditer(answer):
            matched_text = m.group(0)
            for num in _NUMERIC_TOKEN_RE.findall(matched_text):
                normalized_num = num.replace(",", "")
                # Allow either exact match or integer equivalent (e.g. 10000 vs 10000.00)
                stripped_cents = (
                    normalized_num[:-3] if normalized_num.endswith(".00") else normalized_num
                )
                if (
                    normalized_num not in excerpt_numbers
                    and f"{normalized_num}.00" not in excerpt_numbers
                    and stripped_cents not in excerpt_numbers
                ):
                    return True

    return False


async def run_chat(
    *,
    llm: LLMClient,
    service: BusinessDataService,
    message: str,
    as_of: date,
    max_iterations: int,
    max_tool_calls: int,
    document_service: DocumentRetrievalService | None = None,
    max_input_tokens: int = 16000,
) -> ChatOutcome:
    """Run the bounded tool loop. ``LLMError`` from the client propagates to the caller."""
    tool_specs = [
        spec
        for spec in TOOLS.values()
        if spec.name not in DOCUMENT_RAG_TOOLS or document_service is not None
    ]
    messages: list[ChatMessage] = [
        {"role": "system", "content": build_system_prompt(as_of)},
        {"role": "user", "content": message},
    ]
    outcome = ChatOutcome(answer="", status="ok")

    for _ in range(max_iterations):
        response = await llm.complete(messages, tool_specs)
        outcome.input_tokens += response.input_tokens
        outcome.output_tokens += response.output_tokens

        if not response.tool_calls:
            raw_answer = (response.content or "").strip()
            if not raw_answer:
                outcome.answer = EMPTY_ANSWER
                outcome.status = "ungrounded"
                return outcome

            verified_answer, citations = verify_and_extract_citations(
                raw_answer, outcome.tool_calls
            )
            if looks_ungrounded(verified_answer, outcome.tool_calls):
                outcome.answer = UNGROUNDED_ANSWER
                outcome.status = "ungrounded"
                outcome.citations = []
            else:
                outcome.answer = verified_answer
                outcome.citations = citations
            return outcome

        if (
            len(outcome.tool_calls) + len(response.tool_calls) > max_tool_calls
            or outcome.input_tokens > max_input_tokens
        ):
            break

        messages.append(
            _assistant_tool_message(
                response.content,
                [(c.id, c.name, c.arguments) for c in response.tool_calls],
            )
        )
        for call in response.tool_calls:
            execution = await execute_tool(
                service,
                call.name,
                call.arguments,
                document_service=document_service,
            )
            outcome.tool_calls.append(execution)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(execution.payload, separators=(",", ":")),
                }
            )

    outcome.answer = LIMIT_REACHED_ANSWER
    outcome.status = "limit_reached"
    return outcome
