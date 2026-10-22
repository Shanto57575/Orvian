"""Main entrypoint for the Orvian FastAPI application."""

import asyncio
import sys
from typing import cast

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.types import ExceptionHandler

from app.api.v1 import api_v1_router
from app.auth.limiter import limiter
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Orvian AI Business Data Assistant Backend API",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Attach slowapi rate limiter to app state and register error handler
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    cast(ExceptionHandler, _rate_limit_exceeded_handler),
)

# CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_v1_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root redirect / information endpoint."""
    return {
        "message": "Welcome to Orvian API",
        "docs_url": "/docs",
        "health_url": "/api/v1/health",
    }
