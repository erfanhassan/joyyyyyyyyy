import hmac
import hashlib
import base64
import logging
from typing import Optional

logger = logging.getLogger("joy.hmac")


def verify_meta_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """
    Verify Meta Graph API X-Hub-Signature-256 header.
    Format: 'sha256=<hex_digest>'
    """
    if not secret:
        # If no secret configured in test/dev, allow
        return True
    if not signature_header:
        logger.warning("Missing Meta X-Hub-Signature-256 header")
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        logger.warning(f"Malformed Meta signature header: {signature_header}")
        return False

    expected_signature = signature_header[len(prefix):]
    computed_digest = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_digest, expected_signature)


def verify_shopify_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """
    Verify Shopify X-Shopify-Hmac-Sha256 header.
    Format: '<base64_encoded_digest>'
    """
    if not secret:
        return True
    if not signature_header:
        logger.warning("Missing Shopify X-Shopify-Hmac-Sha256 header")
        return False

    computed_hmac = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    computed_b64 = base64.b64encode(computed_hmac).decode("utf-8")

    return hmac.compare_digest(computed_b64, signature_header.strip())


def verify_woocommerce_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """
    Verify WooCommerce X-WC-Webhook-Signature header.
    Format: '<base64_encoded_digest>'
    """
    if not secret:
        return True
    if not signature_header:
        logger.warning("Missing WooCommerce X-WC-Webhook-Signature header")
        return False

    computed_hmac = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    computed_b64 = base64.b64encode(computed_hmac).decode("utf-8")

    return hmac.compare_digest(computed_b64, signature_header.strip())


def verify_custom_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """
    Verify generic custom storefront X-Signature-SHA256 header.
    Accepts either hex or 'sha256=<hex>'.
    """
    if not secret:
        return True
    if not signature_header:
        logger.warning("Missing custom X-Signature-SHA256 header")
        return False

    clean_header = signature_header.removeprefix("sha256=").strip()
    computed_digest = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_digest, clean_header)
