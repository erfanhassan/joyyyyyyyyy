"""Safe handling for Meta and WhatsApp credential failures."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class MetaCredentialError(RuntimeError):
    """A Meta Graph API response indicates expired credentials or revoked access."""

    def __init__(self, channel: str):
        self.channel = channel
        self.needs_reconnect = True
        super().__init__(
            f"{channel} access expired or lost required permissions. Reconnect the account."
        )


def credential_error(data: Any, channel: str) -> Optional[MetaCredentialError]:
    """Return a safe reconnect error only for known OAuth and permission failures."""
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    try:
        code = int(error.get("code"))
    except (TypeError, ValueError):
        code = None
    try:
        subcode = int(error.get("error_subcode"))
    except (TypeError, ValueError):
        subcode = None

    # 190 and its common subcodes indicate an invalid, expired, or revoked token.
    # 102 is an invalid/expired session; 10 and 200 indicate missing permissions.
    if code in {10, 102, 190, 200} or subcode in {458, 459, 460, 463, 464, 467}:
        return MetaCredentialError(channel)
    return None


def mark_reconnect_required(integration, channel: str) -> None:
    """Persist only non-sensitive recovery metadata; leave credentials and records intact."""
    settings: Dict[str, Any] = dict(integration.settings or {})
    if settings.get("connection_status") == "needs_reconnect":
        return
    settings.update({
        "connection_status": "needs_reconnect",
        "attention_channel": channel,
        "attention_reason": "credentials_expired_or_permissions_revoked",
        "attention_detected_at": datetime.now(timezone.utc).isoformat(),
    })
    integration.settings = settings


def clear_reconnect_required(integration) -> bool:
    """Remove recovery metadata after a verified connection succeeds."""
    settings: Dict[str, Any] = dict(integration.settings or {})
    if settings.get("connection_status") != "needs_reconnect":
        return False
    for key in (
        "connection_status",
        "attention_channel",
        "attention_reason",
        "attention_detected_at",
    ):
        settings.pop(key, None)
    integration.settings = settings
    return True
