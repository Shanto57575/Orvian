# Authentication Architecture (Phase 2)

Per project requirements, authentication is not scaffolded with mock or fake implementations during the initial setup phase.

## Requirements for Phase 2:
1. **Registration & Login**: Secure email and password authentication using Argon2id (`pwdlib[argon2]`).
2. **Mandatory Email Verification**: Cryptographic token generation and email dispatch via SMTP before granting access to protected routes.
3. **Google OAuth2**: Handled via `authlib` with PKCE or state validation to prevent CSRF.
4. **Session Management**: Server-side revocable session tracking (`UserSession` table in Neon PostgreSQL) with `HttpOnly`, `Secure`, `SameSite=Lax` cookies.
5. **Password Reset & Account Authorization**: Tokenized self-service password reset flows and role/account-level permission guards.
6. **Rate Limiting**: Brute-force protection on auth endpoints using `slowapi`.

Full evaluation of alternatives and design trade-offs is documented in `docs/AUTHENTICATION.md`.
