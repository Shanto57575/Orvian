"""Protected AI operations analyst chat endpoint."""

import logging
import re
import time
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import LLMClient, LLMError, OpenAIChatClient
from app.ai.orchestrator import NO_ACCOUNT_ANSWER, run_chat
from app.auth.dependencies import require_verified_user, validate_csrf
from app.auth.limiter import limiter
from app.business.service import BusinessDataService
from app.config import get_settings
from app.db.models import User
from app.db.session import get_read_only_db_session
from app.schemas.chat import ChatRequest, ChatResponse, ChatUsage, ToolCallTrace

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def get_llm_client() -> LLMClient | None:
    """Provide the configured LLM client, or None when no API key is configured."""
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAIChatClient(
        api_key=settings.OPENAI_API_KEY,
        model=settings.LLM_MODEL,
        timeout_seconds=float(settings.LLM_TIMEOUT_SECONDS),
        max_retries=settings.LLM_MAX_RETRIES,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    )


def get_as_of_date() -> date:
    """Business 'today' (UTC). Overridable in tests for deterministic results."""
    return datetime.now(UTC).date()


def _correlation_id(request: Request) -> str:
    incoming = request.headers.get("X-Request-ID", "")
    return incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex


def _error(status_code: int, code: str, message: str, correlation_id: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "correlation_id": correlation_id},
        headers={"X-Request-ID": correlation_id},
    )


@router.post("", response_model=ChatResponse, dependencies=[Depends(validate_csrf)])
@limiter.limit(settings.CHAT_RATE_LIMIT)
async def chat(
    request: Request,
    response: Response,
    data: ChatRequest,
    user: User = Depends(require_verified_user),
    db: AsyncSession = Depends(get_read_only_db_session),
    llm: LLMClient | None = Depends(get_llm_client),
    as_of: date = Depends(get_as_of_date),
) -> ChatResponse:
    """Answer a business question using only approved, account-scoped read-only tools."""
    correlation_id = _correlation_id(request)
    response.headers["X-Request-ID"] = correlation_id

    if user.account_id is None:
        return ChatResponse(
            answer=NO_ACCOUNT_ANSWER,
            status="no_data",
            as_of=as_of,
            correlation_id=correlation_id,
        )

    if llm is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "llm_not_configured",
            "The AI assistant is not configured on this server (OPENAI_API_KEY is missing).",
            correlation_id,
        )

    service = BusinessDataService(db, user.account_id, as_of)
    started = time.perf_counter()
    try:
        outcome = await run_chat(
            llm=llm,
            service=service,
            message=data.message,
            as_of=as_of,
            max_iterations=settings.LLM_MAX_TOOL_ITERATIONS,
            max_tool_calls=settings.LLM_MAX_TOOL_CALLS,
        )
    except LLMError as exc:
        logger.warning(
            "chat.llm_error",
            extra={"correlation_id": correlation_id, "error_code": exc.code},
        )
        raise _error(
            status.HTTP_502_BAD_GATEWAY,
            "llm_unavailable",
            "The AI provider is temporarily unavailable. Please try again shortly.",
            correlation_id,
        ) from exc
    except Exception as exc:
        logger.exception("chat.internal_error", extra={"correlation_id": correlation_id})
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Something went wrong while answering. Please try again.",
            correlation_id,
        ) from exc

    # Telemetry only: no message text, tool results or answer content is logged.
    logger.info(
        "chat.completed",
        extra={
            "correlation_id": correlation_id,
            "user_id": str(user.id),
            "account_id": str(user.account_id),
            "status": outcome.status,
            "tools": [t.name for t in outcome.tool_calls],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "model": llm.model,
        },
    )

    return ChatResponse(
        answer=outcome.answer,
        status=outcome.status,
        as_of=as_of,
        tool_calls=[
            ToolCallTrace(
                name=t.name,
                ok=t.ok,
                arguments=t.arguments,
                result=t.result,
                error_code=t.error_code,
            )
            for t in outcome.tool_calls
        ],
        usage=ChatUsage(
            model=llm.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        ),
        correlation_id=correlation_id,
    )
