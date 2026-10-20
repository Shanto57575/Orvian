# Authentication Architecture & Evaluation

## Context & Requirements
Orvian requires an authentication system supporting:
- Email and password registration and login
- Mandatory email verification before accessing protected resources
- Google OAuth2 social login
- Secure password hashing (Argon2id)
- Secure session management with server-side revocation and logout
- Account-level authorization and rate limiting
- High compatibility with FastAPI, Pydantic v2, and SQLAlchemy 2 async
- Adherence to standard security protocols without rolling custom crypto or handshake mechanisms

## Evaluation of Alternatives (FastAPI Users Replacement)

`FastAPI Users` is in maintenance mode and has accumulated compatibility friction with newer async SQLAlchemy patterns and Python 3.12+ dependencies. We evaluated the leading production-grade alternatives:

### Option 1: Managed Authentication Provider — Clerk or Supabase Auth
- **Mechanics**:
  - Frontend uses official SDK (e.g., `@clerk/clerk-react` or `@supabase/supabase-js`) for pre-built, accessible UI components handling signup, login, email verification, password reset, and Google OAuth.
  - Backend verifies short-lived JWTs via JWKS using standard cryptographic libraries (`PyJWT` / `cryptography`).
- **Pros**:
  - Zero custom authentication code or session token maintenance in Python.
  - Built-in bot protection, rate limiting, MFA, and OAuth provider management.
  - Battle-tested compliance and session revocation.
- **Cons**:
  - External SaaS dependency (though generous free tiers exist).

### Option 2: Maintained Open-Source Framework — SuperTokens
- **Mechanics**:
  - Uses `supertokens-python` SDK with FastAPI middleware.
  - Provides pre-built backend recipes for EmailPassword, ThirdParty (Google), EmailVerification, and Session management.
- **Pros**:
  - Full control over user data; native FastAPI integration; robust session security (anti-CSRF tokens, rotating refresh tokens).
- **Cons**:
  - Requires running the SuperTokens core service (Docker or managed SuperTokens cloud).

### Option 3: Battle-Tested Standard Python Libraries — Authlib + pwdlib[argon2] + PyJWT + DB Sessions
- **Mechanics**:
  - **Password Hashing**: `pwdlib[argon2]` (the modern, official replacement for abandoned `passlib`, recommended by FastAPI/Pydantic maintainers).
  - **Google OAuth2 / OIDC**: `authlib` (the premier, actively maintained OAuth/OIDC client in the Python ecosystem).
  - **Sessions & Revocation**: Server-side session tokens stored in Neon PostgreSQL (`UserSession` table with expiry and revocation timestamp) set via `HttpOnly`, `Secure`, `SameSite=Lax` cookies.
  - **Email Verification & Password Reset**: Cryptographically signed timed tokens (`itsdangerous` or `PyJWT`) with dedicated database tracking.
  - **Rate Limiting**: `slowapi` on auth endpoints.
- **Pros**:
  - 100% self-contained in native Windows development without additional Docker containers or external SaaS vendor lock-in.
  - Direct integration with SQLAlchemy 2 async models and Neon PostgreSQL.
  - No custom crypto protocols: uses standard RFC-compliant Argon2id, OAuth2/OIDC, and signed tokens.
- **Cons**:
  - Requires writing standard endpoints and email-sending templates (implemented in Phase 2).

## Architectural Decision

For Orvian:
1. **Scaffolding / Setup (Current)**:
   - Dependency selection configured in `pyproject.toml` for standard maintained libraries: `pwdlib[argon2]`, `authlib`, `pyjwt[crypto]`, `itsdangerous`, `slowapi`.
   - Settings in `app/config.py` define auth secrets, token expiry durations, Google OAuth client credentials, and email delivery settings without hardcoding secrets.
   - Zero application auth routes or fake authentication are scaffolded in this phase.
2. **Phase 2 Implementation**:
   - If self-contained native Windows development without third-party services is prioritized, implement **Option 3** (`authlib` + `pwdlib[argon2]` + database session revocation).
   - If the team opts for a zero-boilerplate managed provider, **Clerk** / **Supabase Auth** can be wired seamlessly by exchanging the token dependency for JWKS verification.
