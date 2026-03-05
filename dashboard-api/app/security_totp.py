"""TOTP helpers with encrypted secret storage."""

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
from datetime import UTC, datetime
from urllib.parse import quote

from app.config import settings


def _mfa_key() -> bytes:
    secret = settings.api_secret_key.strip()
    if not secret:
        raise ValueError("API_SECRET_KEY is required for MFA")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _xor_stream(key: bytes, nonce: bytes, data_len: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < data_len:
        block = hmac.new(
            key,
            nonce + counter.to_bytes(4, byteorder="big", signed=False),
            hashlib.sha256,
        ).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:data_len])


def generate_totp_secret() -> str:
    """Generate a Base32 secret suitable for authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_totp_secret(secret: str) -> str:
    key = _mfa_key()
    nonce = secrets.token_bytes(16)
    plaintext = secret.encode("utf-8")
    stream = _xor_stream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    packed = nonce + ciphertext + mac
    return base64.urlsafe_b64encode(packed).decode("ascii")


def decrypt_totp_secret(secret_encrypted: str) -> str:
    try:
        key = _mfa_key()
        packed = base64.urlsafe_b64decode(secret_encrypted.encode("ascii"))
        if len(packed) < 16 + 32:
            raise ValueError("Invalid stored MFA secret")
        nonce = packed[:16]
        mac = packed[-32:]
        ciphertext = packed[16:-32]
        expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("Invalid stored MFA secret")
        stream = _xor_stream(key, nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream))
        return plaintext.decode("utf-8")
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise ValueError("Invalid stored MFA secret") from exc


def build_otpauth_uri(*, issuer: str, account_name: str, secret: str) -> str:
    label = quote(f"{issuer}:{account_name}")
    issuer_q = quote(issuer)
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={issuer_q}&algorithm=SHA1&digits=6&period=30"
    )


def _normalize_secret(secret: str) -> bytes:
    cleaned = secret.replace(" ", "").upper()
    padded = cleaned + "=" * ((8 - (len(cleaned) % 8)) % 8)
    return base64.b32decode(padded.encode("ascii"), casefold=True)


def _totp_code_for_counter(secret: str, counter: int, *, digits: int = 6) -> str:
    key = _normalize_secret(secret)
    payload = struct.pack(">Q", counter)
    digest = hmac.new(key, payload, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = binary % (10**digits)
    return f"{code:0{digits}d}"


def verify_totp_code(secret: str, code: str, *, window_steps: int = 1) -> bool:
    cleaned = "".join(ch for ch in code if ch.isdigit())
    if len(cleaned) != 6:
        return False
    now_counter = int(datetime.now(UTC).timestamp() // 30)
    for offset in range(-window_steps, window_steps + 1):
        if hmac.compare_digest(_totp_code_for_counter(secret, now_counter + offset), cleaned):
            return True
    return False


def current_totp_code(secret: str) -> str:
    counter = int(datetime.now(UTC).timestamp() // 30)
    return _totp_code_for_counter(secret, counter)
