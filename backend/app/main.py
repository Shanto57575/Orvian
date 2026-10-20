"""Main entrypoint for the Orvian FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Orvian AI Business Data Assistant Backend API",
    version="0.1.0",
    debug=settings.DEBUG,
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
