"""Bounded tool-calling loop: LLM proposes tool calls, we validate and execute them.

Guarantees:
- At most ``max_iterations`` model calls and ``max_tool_calls`` tool executions per request.
- Tools run sequentially on one read-only session (AsyncSession is not concurrency-safe).
- Any final answer containing monetary figures without at least one successful tool result
  is withheld as ungrounded.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.ai.llm import ChatMessage, LLMClient
from app.ai.prompts import build_system_prompt
from app.ai.tools import TOOLS, ToolExecution, execute_tool
from app.business.service import BusinessDataService

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


@dataclass
class ChatOutcome:
    answer: str
    status: ChatStatus
    tool_calls: list[ToolExecution] = field(default_factory=list)
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


def looks_ungrounded(answer: str, executions: Sequence[ToolExecution]) -> bool:
    """True when the answer states money figures but no tool returned data."""
    if any(ex.ok for ex in executions):
        return False
    return bool(_MONEY_PATTERN.search(answer))


async def run_chat(
    *,
    llm: LLMClient,
    service: BusinessDataService,
    message: str,
    as_of: date,
    max_iterations: int,
    max_tool_calls: int,
) -> ChatOutcome:
    """Run the bounded tool loop. ``LLMError`` from the client propagates to the caller."""
    tool_specs = list(TOOLS.values())
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
            answer = (response.content or "").strip()
            if not answer:
                outcome.answer = EMPTY_ANSWER
                outcome.status = "ungrounded"
            elif looks_ungrounded(answer, outcome.tool_calls):
                outcome.answer = UNGROUNDED_ANSWER
                outcome.status = "ungrounded"
            else:
                outcome.answer = answer
            return outcome

        if len(outcome.tool_calls) + len(response.tool_calls) > max_tool_calls:
            break

        messages.append(
            _assistant_tool_message(
                response.content,
                [(c.id, c.name, c.arguments) for c in response.tool_calls],
            )
        )
        for call in response.tool_calls:
            execution = await execute_tool(service, call.name, call.arguments)
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
