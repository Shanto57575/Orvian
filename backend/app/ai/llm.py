"""Small provider abstraction for tool-calling chat models.

The orchestrator depends only on ``LLMClient``. ``OpenAIChatClient`` is the single concrete
implementation today (official OpenAI SDK, Chat Completions with strict function tools).
Messages use the widely adopted chat format: ``system`` / ``user`` / ``assistant`` (with
optional ``tool_calls``) / ``tool``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import openai
from openai import AsyncOpenAI

from app.ai.tools import ToolSpec

ChatMessage = dict[str, Any]


class LLMError(Exception):
    """Provider call failed (timeout, network, auth, rate limit, or malformed response)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse: ...


class OpenAIChatClient:
    """OpenAI Chat Completions client with strict, Pydantic-derived tool schemas."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        max_output_tokens: int,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )
        self._model = model
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        tool_params = [
            openai.pydantic_function_tool(t.args_model, name=t.name, description=t.description)
            for t in tools
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=cast(Any, list(messages)),
                tools=tool_params,
                tool_choice="auto",
                temperature=0,
                max_completion_tokens=self._max_output_tokens,
            )
        except openai.APITimeoutError as exc:
            raise LLMError("timeout") from exc
        except openai.RateLimitError as exc:
            raise LLMError("rate_limited") from exc
        except openai.AuthenticationError as exc:
            raise LLMError("auth_failed") from exc
        except openai.OpenAIError as exc:
            raise LLMError("provider_error") from exc

        if not response.choices:
            raise LLMError("empty_response")
        message = response.choices[0].message
        calls = [
            ToolCallRequest(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (message.tool_calls or [])
            if tc.type == "function"
        ]
        usage = response.usage
        return LLMResponse(
            content=message.content,
            tool_calls=calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
