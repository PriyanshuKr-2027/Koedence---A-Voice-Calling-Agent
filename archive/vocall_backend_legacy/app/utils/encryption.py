import base64
import json
import os
from typing import Any, Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RAW_KEY = os.environ.get("ENCRYPTION_KEY")
if not RAW_KEY:
    # Default 64-char hex key (32 bytes) for development when env var is not set
    RAW_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    os.environ["ENCRYPTION_KEY"] = RAW_KEY

try:
    KEY_BYTES = bytes.fromhex(RAW_KEY)
    if len(KEY_BYTES) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to 32 bytes (64 hex chars), got {len(KEY_BYTES)} bytes."
        )
except Exception as exc:
    raise ValueError(
        f"ENCRYPTION_KEY must be a valid 64-character hex string (32 bytes): {exc}"
    ) from exc


def encrypt_config(config: dict) -> str:
    """
    JSON-serializes the dict, encrypts with AES-256-GCM, and returns base64-encoded ciphertext.
    The base64 payload includes the 12-byte random nonce prepended to the ciphertext + tag.
    """
    if not isinstance(config, dict):
        config = {"data": config}

    plaintext = json.dumps(config).encode("utf-8")
    aesgcm = AESGCM(KEY_BYTES)
    nonce = os.urandom(12)  # 96-bit random nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_config(ciphertext: Any) -> dict:
    """
    Reverses encrypt_config. Accepts base64-encoded string (or dict wrapping it) and returns original dict.
    """
    if isinstance(ciphertext, dict):
        if "encrypted" in ciphertext and isinstance(ciphertext["encrypted"], str):
            ciphertext_str = ciphertext["encrypted"]
        else:
            return ciphertext
    elif isinstance(ciphertext, str):
        ciphertext_str = ciphertext
    else:
        return {}

    try:
        raw = base64.b64decode(ciphertext_str)
        if len(raw) < 13:
            return json.loads(ciphertext_str)

        nonce = raw[:12]
        encrypted_data = raw[12:]
        aesgcm = AESGCM(KEY_BYTES)
        plaintext = aesgcm.decrypt(nonce, encrypted_data, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        try:
            return json.loads(ciphertext_str)
        except Exception:
            return {}


# Aliases for backward compatibility across modules
encrypt_dict = encrypt_config
decrypt_dict = decrypt_config


if __name__ == "__main__":
    sample_config = {
        "api_key": "sk_test_123456789",
        "url": "https://api.example.com",
        "is_active": True,
        "settings": {"timeout": 30, "retries": 3},
    }
    print("Original config:", sample_config)
    encrypted = encrypt_config(sample_config)
    print("Encrypted base64:", encrypted)
    decrypted = decrypt_config(encrypted)
    print("Decrypted config:", decrypted)
    assert (
        decrypted == sample_config
    ), "Sanity check failed: Decrypted dict does not match original!"
    print("Sanity check passed successfully!")
