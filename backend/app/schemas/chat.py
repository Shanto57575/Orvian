"""Request/response schemas for the AI operations analyst chat endpoint."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=2000)


class ToolCallTrace(BaseModel):
    name: str
    ok: bool
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None


class DocumentCitation(BaseModel):
    citation_id: str
    doc_key: str
    document_title: str
    category: str
    version: str
    effective_date: date
    section_title: str
    page_number: int
    similarity_score: float
    excerpt: str


class ChatUsage(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    answer: str
    status: Literal["ok", "no_data", "limit_reached", "ungrounded"]
    as_of: date
    tool_calls: list[ToolCallTrace] = []
    citations: list[DocumentCitation] = []
    usage: ChatUsage | None = None
    correlation_id: str
