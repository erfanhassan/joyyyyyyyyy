import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings
from fastapi import HTTPException


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a URL-safe 32-byte base64-encoded key suitable for Fernet from any string."""
    if not secret or len(secret) < 32 or secret == "joy_master_aes256_secret_key_change_in_production_32b":
        raise HTTPException(
            status_code=503,
            detail="Configure a private ENCRYPTION_KEY_SECRET or SESSION_SECRET of at least 32 characters before storing provider credentials.",
        )
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_token(token: str, key_secret: Optional[str] = None) -> str:
    """
    Encrypt a plaintext OAuth access or refresh token using AES-256 (Fernet authenticated encryption).
    Returns a URL-safe base64 string.
    """
    if not token:
        return ""
    secret = key_secret or settings.ENCRYPTION_KEY_SECRET
    fernet_key = _derive_fernet_key(secret)
    f = Fernet(fernet_key)
    encrypted_bytes = f.encrypt(token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str, key_secret: Optional[str] = None) -> str:
    """
    Decrypt an AES-256 encrypted token string back to its original plaintext.
    """
    if not encrypted_token:
        return ""
    secret = key_secret or settings.ENCRYPTION_KEY_SECRET
    fernet_key = _derive_fernet_key(secret)
    f = Fernet(fernet_key)
    decrypted_bytes = f.decrypt(encrypted_token.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


# AES-256-GCM Envelope Encryption Helpers
def encrypt_with_aes_gcm(plaintext: str, key_bytes: bytes) -> str:
    """
    Encrypt plaintext using AES-256-GCM with a 96-bit nonce.
    Returns: base64(nonce + ciphertext + tag)
    """
    if not plaintext:
        return ""
    import os
    nonce = os.urandom(12)
    aesgcm = AESGCM(key_bytes)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_with_aes_gcm(encrypted_payload: str, key_bytes: bytes) -> str:
    """
    Decrypt a base64(nonce + ciphertext + tag) payload using AES-256-GCM.
    """
    if not encrypted_payload:
        return ""
    raw = base64.b64decode(encrypted_payload.encode("utf-8"))
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key_bytes)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")
