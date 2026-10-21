"""Shared boundaries for untrusted URLs, credentials and public visitors."""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import socket
import time
import httpx
from urllib.parse import urlsplit

from fastapi import HTTPException
from app.core.config import settings

SENSITIVE = ("token", "secret", "password", "authorization", "consumer_key", "api_key")


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(s in k.lower() for s in SENSITIVE)
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def seal_credentials(value):
    """Encrypt recognized credential fields at every nesting depth."""
    from app.core.security import encrypt_token
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if item and not isinstance(item, (dict, list)) and any(marker in key.lower() for marker in SENSITIVE):
                result[key] = item if isinstance(item,str) and item.startswith("enc:") else "enc:" + encrypt_token(str(item))
            else:
                result[key] = seal_credentials(item)
        return result
    if isinstance(value, list):
        return [seal_credentials(item) for item in value]
    return value


async def public_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                 and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, "Use a public HTTPS URL without credentials or a custom port.")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("non-public address")
    except (OSError, ValueError):
        raise HTTPException(400, "The URL must resolve exclusively to public internet addresses.") from None
    return url


class PublicTransport(httpx.AsyncHTTPTransport):
    """Pin the checked public address; a second DNS lookup cannot rebind privately."""
    async def handle_async_request(self, request):
        host = request.url.host
        await public_url(str(request.url))
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise HTTPException(400, "Private network destinations are not allowed.")
        headers = request.headers.copy()
        headers["host"] = host
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = host
        pinned = httpx.Request(request.method, request.url.copy_with(host=addresses[0][4][0]),
                               headers=headers, stream=request.stream, extensions=extensions)
        return await super().handle_async_request(pinned)


def visitor_token(tenant: str, visitor: str, expires: int | None = None) -> str:
    key = settings.ENCRYPTION_KEY_SECRET
    if len(key) < 32:
        raise HTTPException(503, "Secure widget sessions are not configured.")
    payload = base64.urlsafe_b64encode(json.dumps(
        {"tenant": tenant, "visitor": visitor, "exp": expires or int(time.time()) + 43200},
        separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_visitor(token: str, tenant: str, visitor: str | None = None) -> dict:
    try:
        payload, signature = token.split(".")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        expected = visitor_token(data["tenant"], data["visitor"], data["exp"]).split(".")[1]
        if (not hmac.compare_digest(expected, signature) or data["tenant"] != tenant
                or (visitor and data["visitor"] != visitor) or data["exp"] <= time.time()):
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Widget session expired or invalid. Reopen the chat.") from None
