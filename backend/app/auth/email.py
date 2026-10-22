"""Email notification delivery service for email verification and password reset.

Supports Resend REST API (via httpx) as well as standard SMTP delivery.
In production, missing email credentials raise an immediate ValueError and
console link logging is strictly prohibited.
"""

import asyncio
import logging
import smtplib
import ssl
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import EmailOutbox

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_email(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str | None = None,
) -> None:
    """Send an email using Resend API, SMTP, or console fallback in development."""
    has_resend = bool(settings.RESEND_API_KEY)
    has_smtp = bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)

    if settings.ENVIRONMENT == "production" and not (has_resend or has_smtp):
        raise ValueError(
            "Production email delivery requires either RESEND_API_KEY or configured SMTP settings. "
            "Console email fallback is strictly disabled in production."
        )

    if has_smtp:
        await asyncio.to_thread(
            _send_smtp_sync,
            to_email,
            subject,
            text_content,
            html_content,
        )
    elif has_resend:
        await _send_resend(to_email, subject, text_content, html_content)
    else:
        # Development / test console fallback
        logger.warning(
            "[DEV-ONLY EMAIL DISPATCH] Recipient: %s | Subject: %s\n%s",
            to_email,
            subject,
            text_content,
        )


async def _send_resend(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str | None,
) -> None:
    """Dispatch email via Resend REST API asynchronously."""
    from_email = settings.SMTP_FROM_EMAIL
    if from_email == "noreply@orvian.local":
        from_email = "onboarding@resend.dev"

    sender = f"{settings.SMTP_FROM_NAME} <{from_email}>"
    payload: dict[str, object] = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": text_content,
    }
    if html_content:
        payload["html"] = html_content

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            logger.error(
                "Resend email delivery failed [%s]: %s",
                response.status_code,
                response.text,
            )
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(
                    f"Resend delivery failed with status {response.status_code}: {response.text}"
                )
            logger.warning(
                "[DEV FALLBACK] Resend delivery rejected (status %s: %s). "
                "Local development will continue using console OTP.",
                response.status_code,
                response.text,
            )


def _send_smtp_sync(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str | None,
) -> None:
    """Synchronous SMTP email dispatcher run in a threadpool."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.set_content(text_content)

    if html_content:
        msg.add_alternative(html_content, subtype="html")

    assert settings.SMTP_HOST is not None
    assert settings.SMTP_USER is not None
    assert settings.SMTP_PASSWORD is not None

    tls_context = ssl.create_default_context()
    timeout = settings.SMTP_TIMEOUT_SECONDS

    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            context=tls_context,
            timeout=timeout,
        ) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=timeout,
        ) as server:
            server.starttls(context=tls_context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)


# ====================================================================
# Responsive HTML Email Layouts (Strict <= 100 chars per line)
# ====================================================================
def _render_verification_html(
    verify_url: str,
    expire_hours: int,
    otp: str | None = None,
) -> str:
    """Generate modern, responsive HTML layout for email verification."""
    otp_section = ""
    if otp:
        otp_section = f"""
        <div style="text-align: center; margin: 28px 0 20px;">
          <p style="font-size: 13px; font-weight: 700; color: #475569;
                    text-transform: uppercase; letter-spacing: 1.5px; margin: 0 0 10px;">
            Your 6-Digit Verification Code
          </p>
          <div style="display: inline-block; font-size: 34px; font-weight: 800;
                      letter-spacing: 10px; color: #1d4ed8; background: #eff6ff;
                      border: 2px dashed #93c5fd; border-radius: 12px; padding: 14px 28px;">
            {otp}
          </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify your Orvian account</title>
  <style>
    body {{
      margin: 0; padding: 0; background-color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #0f172a;
    }}
    .wrapper {{ width: 100%; background-color: #f8fafc; padding: 40px 16px; }}
    .container {{
      max-width: 560px; margin: 0 auto; background-color: #ffffff;
      border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden;
    }}
    .header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      padding: 32px 32px 28px; text-align: center;
    }}
    .logo {{
      display: inline-block; width: 44px; height: 44px; line-height: 44px;
      background-color: #2563eb; color: #ffffff; font-size: 22px;
      font-weight: 800; border-radius: 12px; margin-bottom: 12px; text-align: center;
    }}
    .brand-title {{ color: #ffffff; font-size: 20px; font-weight: 700; margin: 0; }}
    .content {{ padding: 36px 32px 28px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #0f172a; margin: 0 0 16px; }}
    p {{ font-size: 15px; line-height: 1.6; color: #475569; margin: 0 0 20px; }}
    .btn-container {{ text-align: center; margin: 28px 0; }}
    .btn {{
      display: inline-block; background-color: #2563eb; color: #ffffff !important;
      text-decoration: none; font-weight: 600; font-size: 15px; padding: 13px 36px;
      border-radius: 8px;
    }}
    .badge {{
      background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
      padding: 12px 16px; font-size: 13px; color: #1e40af; margin-bottom: 24px;
    }}
    .fallback {{
      font-size: 12px; color: #64748b; word-break: break-all;
      background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 12px; margin-top: 16px;
    }}
    .footer {{
      border-top: 1px solid #f1f5f9; padding: 24px 32px; text-align: center;
      font-size: 12px; color: #94a3b8; line-height: 1.5;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <div class="logo">O</div>
        <div class="brand-title">Orvian</div>
      </div>
      <div class="content">
        <h1>Verify your email address</h1>
        <p>
          Welcome to <strong>Orvian</strong>. Please enter the verification code below in
          your app, or click the verification button to activate your account.
        </p>
        {otp_section}
        <div class="btn-container">
          <a href="{verify_url}" class="btn" target="_blank" rel="noopener">Verify My Account</a>
        </div>
        <div class="badge">
          &#9201; <strong>Notice:</strong> The 6-digit code expires in <strong>15 minutes</strong>.
          The verification link expires in <strong>{expire_hours} hours</strong>.
        </div>
        <p style="font-size: 13px; color: #64748b; margin-bottom: 8px;">
          Alternatively, you can copy and paste this direct verification link:
        </p>
        <div class="fallback">{verify_url}</div>
      </div>
      <div class="footer">
        <p style="margin: 0 0 6px;">&copy; 2026 Orvian &middot; Synthetic Data Assistant</p>
        <p style="margin: 0;">If you did not create an account, you can disregard this email.</p>
      </div>
    </div>
  </div>
</body>
</html>"""


def _render_password_reset_html(reset_url: str, expire_minutes: int) -> str:
    """Generate modern, responsive HTML layout for password reset."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset your Orvian password</title>
  <style>
    body {{
      margin: 0; padding: 0; background-color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #0f172a;
    }}
    .wrapper {{ width: 100%; background-color: #f8fafc; padding: 40px 16px; }}
    .container {{
      max-width: 560px; margin: 0 auto; background-color: #ffffff;
      border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden;
    }}
    .header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      padding: 32px 32px 28px; text-align: center;
    }}
    .logo {{
      display: inline-block; width: 44px; height: 44px; line-height: 44px;
      background-color: #2563eb; color: #ffffff; font-size: 22px;
      font-weight: 800; border-radius: 12px; margin-bottom: 12px; text-align: center;
    }}
    .brand-title {{ color: #ffffff; font-size: 20px; font-weight: 700; margin: 0; }}
    .content {{ padding: 36px 32px 28px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #0f172a; margin: 0 0 16px; }}
    p {{ font-size: 15px; line-height: 1.6; color: #475569; margin: 0 0 20px; }}
    .btn-container {{ text-align: center; margin: 28px 0; }}
    .btn {{
      display: inline-block; background-color: #2563eb; color: #ffffff !important;
      text-decoration: none; font-weight: 600; font-size: 15px; padding: 13px 36px;
      border-radius: 8px;
    }}
    .badge {{
      background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
      padding: 12px 16px; font-size: 13px; color: #92400e; margin-bottom: 24px;
    }}
    .fallback {{
      font-size: 12px; color: #64748b; word-break: break-all;
      background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 12px; margin-top: 16px;
    }}
    .footer {{
      border-top: 1px solid #f1f5f9; padding: 24px 32px; text-align: center;
      font-size: 12px; color: #94a3b8; line-height: 1.5;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <div class="logo">O</div>
        <div class="brand-title">Orvian</div>
      </div>
      <div class="content">
        <h1>Reset your password</h1>
        <p>
          We received a request to reset your password for your <strong>Orvian</strong>
          account. Click the button below to choose a new password:
        </p>
        <div class="btn-container">
          <a href="{reset_url}" class="btn" target="_blank" rel="noopener">Reset Password</a>
        </div>
        <div class="badge">
          &#9201; <strong>Security Notice:</strong> This single-use recovery link will expire
          in <strong>{expire_minutes} minutes</strong>. Active sessions will be revoked.
        </div>
        <p style="font-size: 13px; color: #64748b; margin-bottom: 8px;">
          If the button above does not work, copy and paste this link into your browser:
        </p>
        <div class="fallback">{reset_url}</div>
      </div>
      <div class="footer">
        <p style="margin: 0 0 6px;">&copy; 2026 Orvian &middot; Synthetic Data Assistant</p>
        <p style="margin: 0;">If you did not request a reset, you can disregard this email.</p>
      </div>
    </div>
  </div>
</body>
</html>"""


# ====================================================================
# Public Dispatch Helpers
# ====================================================================
async def send_verification_email(
    to_email: str,
    token: str,
    otp: str | None = None,
) -> None:
    """Send email verification link and 6-digit OTP code with text and responsive HTML."""
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your Orvian account"
    otp_text = (
        f"\nYour 6-digit verification code is: {otp}\n"
        f"This verification code expires in "
        f"{settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} minutes.\n\n"
        if otp
        else ""
    )
    text = (
        f"Welcome to Orvian!\n\n"
        f"{otp_text}"
        f"Enter this code in your app to verify your account, or visit the link below:\n"
        f"{verify_url}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.\n"
        f"If you did not create an account, you can safely ignore this email."
    )
    if settings.ENVIRONMENT == "development" and otp:
        logger.warning(
            "\n"
            "============================================================\n"
            "  [DEV VERIFICATION OTP]  \n"
            "  Recipient: %s\n"
            "  6-digit Code: %s (Expires in %s min)\n"
            "============================================================",
            to_email,
            otp,
            settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES,
        )
    html = _render_verification_html(
        verify_url,
        settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
        otp,
    )
    await send_email(to_email, subject, text, html)


def dispatch_verification_email_background(
    to_email: str,
    token: str,
    otp: str | None = None,
) -> None:
    """Decouple email delivery from HTTP transaction to eliminate timing side-channels."""

    async def _safe_send() -> None:
        try:
            await send_verification_email(to_email, token, otp)
        except Exception as exc:
            logger.error("Background verification email failed for %s: %s", to_email, exc)

    asyncio.create_task(_safe_send())


def dispatch_password_reset_email_background(to_email: str, token: str) -> None:
    """Decouple email delivery from HTTP transaction to eliminate timing side-channels."""

    async def _safe_send() -> None:
        try:
            await send_password_reset_email(to_email, token)
        except Exception as exc:
            logger.error("Background password reset email failed for %s: %s", to_email, exc)

    asyncio.create_task(_safe_send())


async def send_password_reset_email(to_email: str, token: str) -> None:
    """Send password reset link with text and responsive HTML."""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your Orvian password"
    text = (
        f"We received a request to reset your Orvian password.\n\n"
        f"Please visit the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.\n"
        f"If you did not request a password reset, you can safely ignore this email."
    )
    html = _render_password_reset_html(
        reset_url,
        settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )
    await send_email(to_email, subject, text, html)


# ====================================================================
# Transactional PostgreSQL Outbox
# ====================================================================
_outbox_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_outbox_session_factory(factory: async_sessionmaker[AsyncSession] | None) -> None:
    """Override session factory for testing or isolated environments."""
    global _outbox_session_factory
    _outbox_session_factory = factory


def get_outbox_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retrieve the active session factory for outbox delivery."""
    global _outbox_session_factory
    if _outbox_session_factory is not None:
        return _outbox_session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


def enqueue_verification_outbox(
    db: AsyncSession,
    to_email: str,
    token: str,
    otp: str | None = None,
) -> EmailOutbox:
    """Enqueue a verification email atomically within the caller's DB transaction."""
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your Orvian account"
    otp_text = (
        f"\nYour 6-digit verification code is: {otp}\n"
        f"This verification code expires in "
        f"{settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} minutes.\n\n"
        if otp
        else ""
    )
    text = (
        f"Welcome to Orvian!\n\n"
        f"{otp_text}"
        f"Enter this code in your app to verify your account, or visit the link below:\n"
        f"{verify_url}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.\n"
        f"If you did not create an account, you can safely ignore this email."
    )
    if settings.ENVIRONMENT == "development" and otp:
        logger.warning(
            "\n"
            "============================================================\n"
            "  [DEV VERIFICATION OTP]  \n"
            "  Recipient: %s\n"
            "  6-digit Code: %s (Expires in %s min)\n"
            "============================================================",
            to_email,
            otp,
            settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES,
        )
    html = _render_verification_html(
        verify_url,
        settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
        otp,
    )
    outbox_item = EmailOutbox(
        id=uuid.uuid4(),
        recipient=to_email,
        subject=subject,
        body_text=text,
        body_html=html,
        status="pending",
        attempts=0,
        max_retries=3,
    )
    db.add(outbox_item)
    return outbox_item


def enqueue_password_reset_outbox(
    db: AsyncSession,
    to_email: str,
    token: str,
) -> EmailOutbox:
    """Enqueue a password reset email atomically within the caller's DB transaction."""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your Orvian password"
    text = (
        f"We received a request to reset your Orvian password.\n\n"
        f"Please visit the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.\n"
        f"If you did not request a password reset, you can safely ignore this email."
    )
    html = _render_password_reset_html(
        reset_url,
        settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )
    outbox_item = EmailOutbox(
        id=uuid.uuid4(),
        recipient=to_email,
        subject=subject,
        body_text=text,
        body_html=html,
        status="pending",
        attempts=0,
        max_retries=3,
    )
    db.add(outbox_item)
    return outbox_item


async def deliver_outbox_message(outbox_id: uuid.UUID) -> bool:
    """Deliver an outbox message with bounded retries and status updates."""
    session_maker = get_outbox_session_factory()
    for attempt in range(1, 4):
        async with session_maker() as session:
            stmt = select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update()
            res = await session.execute(stmt)
            msg = res.scalar_one_or_none()
            if not msg or msg.status == "sent":
                return True

            try:
                await send_email(msg.recipient, msg.subject, msg.body_text, msg.body_html)
                msg.status = "sent"
                msg.processed_at = datetime.now(UTC)
                await session.commit()
                return True
            except Exception as exc:
                msg.attempts += 1
                msg.last_error = str(exc)[:1000]
                if msg.attempts >= msg.max_retries:
                    msg.status = "failed"
                await session.commit()
                logger.error(
                    "Outbox email delivery failed for %s (attempt %d/%d): %s",
                    msg.recipient,
                    msg.attempts,
                    msg.max_retries,
                    exc,
                )
                if attempt < 3:
                    await asyncio.sleep(0.05 * (2 ** (attempt - 1)))
    return False


_pending_outbox_tasks: set[asyncio.Task[bool]] = set()


def dispatch_outbox_delivery(outbox_id: uuid.UUID) -> asyncio.Task[bool]:
    """Trigger background delivery for an outbox message after transaction commit."""
    task = asyncio.create_task(deliver_outbox_message(outbox_id))
    _pending_outbox_tasks.add(task)
    task.add_done_callback(_pending_outbox_tasks.discard)
    return task


async def wait_outbox_delivery() -> None:
    """Await all active background outbox deliveries (useful in tests and shutdown)."""
    if _pending_outbox_tasks:
        await asyncio.gather(*list(_pending_outbox_tasks), return_exceptions=True)
