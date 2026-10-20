"""Clerk session verification and the configured first-owner authorization."""
import logging
import os
import time
from urllib.parse import urlsplit

from clerk_backend_api import (
    AuthenticateRequestOptions,
    Clerk,
    authenticate_request_async,
)
from starlette.datastructures import Headers

from app.core.config import settings

logger = logging.getLogger("joy.auth.clerk")

_email_cache: dict[str, tuple[str, float]] = {}
_EMAIL_CACHE_SECONDS = 300


class ClerkAuthFailure(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def clerk_auth_configured() -> bool:
    return bool(
        settings.CLERK_SECRET_KEY.strip()
        and settings.CLERK_PUBLISHABLE_KEY.strip()
        and settings.JOY_INITIAL_ADMIN_EMAIL.strip()
    )


def _deployment_origins() -> set[str]:
    origins: set[str] = set()
    for value in os.environ.get("REPLIT_DOMAINS", "").split(","):
        domain = value.strip()
        if not domain:
            continue
        parsed = urlsplit(domain if "://" in domain else f"https://{domain}")
        if parsed.hostname:
            origins.add(f"https://{parsed.netloc.lower()}")
    return origins


def _authorized_origin(headers: Headers) -> str | None:
    allowed_origins = _deployment_origins()
    if not allowed_origins:
        return None

    origin_header = headers.get("origin")
    host_header = (
        headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        or headers.get("host", "").split(",", 1)[0].strip()
    )
    if origin_header:
        parsed_origin = urlsplit(origin_header)
        if parsed_origin.scheme != "https" or not parsed_origin.netloc:
            return None
        origin = f"https://{parsed_origin.netloc.lower()}"
        if origin not in allowed_origins:
            return None
        if host_header and parsed_origin.netloc.lower() != host_header.lower():
            return None
        return origin

    if not host_header:
        return None
    origin = f"https://{host_header.lower()}"
    return origin if origin in allowed_origins else None


async def _verified_primary_email(user_id: str) -> str | None:
    now = time.monotonic()
    cached = _email_cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]

    client = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)
    user = await client.users.get_async(user_id=user_id, timeout_ms=8000)
    if user.banned or user.locked:
        return None

    email = next(
        (
            item
            for item in user.email_addresses
            if item.id == user.primary_email_address_id
        ),
        None,
    )
    if not email or not email.verification:
        return None
    verification_status = getattr(email.verification.status, "value", email.verification.status)
    if str(verification_status).casefold() != "verified":
        return None

    normalized = email.email_address.strip().casefold()
    _email_cache[user_id] = (normalized, now + _EMAIL_CACHE_SECONDS)
    return normalized


async def authenticate_owner(scope) -> dict[str, str]:
    headers = Headers(scope=scope)
    origin = _authorized_origin(headers)
    if not origin:
        raise ClerkAuthFailure(401, "Sign in to continue.")

    request_like = type("ClerkRequest", (), {"headers": headers})()
    try:
        state = await authenticate_request_async(
            request_like,
            AuthenticateRequestOptions(
                secret_key=settings.CLERK_SECRET_KEY,
                authorized_parties=[origin],
            ),
        )
    except Exception as exc:
        logger.warning("Clerk session verification failed (%s)", type(exc).__name__)
        raise ClerkAuthFailure(503, "Sign-in verification is temporarily unavailable.") from None

    user_id = (state.payload or {}).get("sub") if state.is_signed_in else None
    if not user_id:
        raise ClerkAuthFailure(401, "Sign in to continue.")

    try:
        email = await _verified_primary_email(user_id)
    except Exception as exc:
        logger.warning("Clerk owner lookup failed (%s)", type(exc).__name__)
        raise ClerkAuthFailure(503, "Sign-in verification is temporarily unavailable.") from None

    owner_email = settings.JOY_INITIAL_ADMIN_EMAIL.strip().casefold()
    if not email or email != owner_email:
        raise ClerkAuthFailure(403, "This account is not authorized to administer JOY.")

    return {"user_id": user_id}
