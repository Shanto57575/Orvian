"""Google OAuth 2.0 / OpenID Connect integration using Authlib."""

import secrets
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()

GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def is_google_oauth_configured() -> bool:
    """Check if Google OAuth credentials are configured."""
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def create_oauth_client() -> AsyncOAuth2Client:
    """Create an AsyncOAuth2Client configured for Google."""
    if not is_google_oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID "
                "and GOOGLE_OAUTH_CLIENT_SECRET in the root .env file."
            ),
        )
    return AsyncOAuth2Client(
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scope="openid email profile",
    )


def generate_oauth_state() -> str:
    """Generate a cryptographic state token to prevent CSRF during OAuth handshake."""
    return secrets.token_urlsafe(32)


async def get_google_authorization_url(
    state: str,
    code_challenge: str,
) -> str:
    """Construct Google OAuth consent URL with PKCE (S256) and state."""
    async with create_oauth_client() as client:
        url, _ = client.create_authorization_url(
            GOOGLE_AUTH_ENDPOINT,
            redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            prompt="select_account",
        )
        return str(url)


async def exchange_google_code_for_user_info(
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange authorization code for tokens and extract verified OpenID claims."""
    async with create_oauth_client() as client:
        token_response = await client.fetch_token(
            GOOGLE_TOKEN_ENDPOINT,
            code=code,
            redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
            code_verifier=code_verifier,
        )

        user_info = token_response.get("userinfo")
        if not user_info:
            # Fetch userinfo using the authenticated client session
            resp = await client.get("https://openidconnect.googleapis.com/v1/userinfo")
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to fetch Google user profile: {resp.text}",
                )
            user_info = resp.json()

    # Validate mandatory verified OIDC claims
    google_id = user_info.get("sub")
    email = user_info.get("email")
    email_verified = user_info.get("email_verified")

    if not google_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token missing mandatory identity claims ('sub', 'email').",
        )

    if email_verified is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is not verified.",
        )

    return {
        "google_id": str(google_id),
        "email": str(email).strip().lower(),
        "full_name": user_info.get("name"),
    }
