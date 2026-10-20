"""Tests for application health and status endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_healthy(async_client: AsyncClient) -> None:
    """Verify GET /api/v1/health returns 200 with healthy status."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "Orvian"
    assert "environment" in data
    assert "debug" in data


@pytest.mark.asyncio
async def test_root_endpoint_returns_welcome_and_links(async_client: AsyncClient) -> None:
    """Verify GET / returns welcome payload with documentation and health links."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "Welcome to Orvian API" in data["message"]
    assert data["health_url"] == "/api/v1/health"
