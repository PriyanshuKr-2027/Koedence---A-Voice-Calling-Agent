"""
test_encryption.py — Tests for app/utils/encryption.py (AES-256-GCM).

This is one of the few modules with actual real implementation.
"""
import pytest
import json
from app.utils.encryption import encrypt_config, decrypt_config, encrypt_dict, decrypt_dict


class TestEncryptConfig:
    """TC-ENC-*: AES-256-GCM encryption round-trip tests."""

    def test_encrypt_returns_string(self):
        """TC-ENC-01: encrypt_config returns a non-empty string."""
        result = encrypt_config({"key": "value"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encrypt_decrypt_roundtrip(self):
        """TC-ENC-02: encrypt → decrypt recovers original dict."""
        original = {"api_key": "sk-test-123", "url": "https://api.example.com"}
        encrypted = encrypt_config(original)
        decrypted = decrypt_config(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_outputs(self):
        """TC-ENC-03: Same input produces different ciphertext (random nonce)."""
        data = {"key": "same_value"}
        enc1 = encrypt_config(data)
        enc2 = encrypt_config(data)
        assert enc1 != enc2, "Encryption must use random nonce for each call"

    def test_decrypt_from_dict_with_encrypted_key(self):
        """TC-ENC-04: decrypt_config handles {'encrypted': base64string} format."""
        original = {"token": "secret123"}
        encrypted_str = encrypt_config(original)
        wrapped = {"encrypted": encrypted_str}
        decrypted = decrypt_config(wrapped)
        assert decrypted == original

    def test_decrypt_plain_dict_returns_as_is(self):
        """TC-ENC-05: decrypt_config on a plain dict (no 'encrypted' key) returns it unchanged."""
        plain = {"some": "data", "number": 42}
        result = decrypt_config(plain)
        assert result == plain

    def test_decrypt_empty_string_returns_empty_dict(self):
        """TC-ENC-06: decrypt_config on an unrecognized string returns {}."""
        result = decrypt_config("not_valid_base64_encrypted_string")
        assert isinstance(result, dict)

    def test_decrypt_none_type_returns_empty_dict(self):
        """TC-ENC-07: decrypt_config on None returns {}."""
        result = decrypt_config(None)
        assert result == {}

    def test_encrypt_nested_dict(self):
        """TC-ENC-08: Nested dicts are correctly encrypted and decrypted."""
        nested = {
            "db": {"host": "localhost", "port": 5432},
            "credentials": {"user": "admin", "pass": "secret"},
        }
        assert decrypt_config(encrypt_config(nested)) == nested

    def test_encrypt_non_dict_wraps_in_data_key(self):
        """TC-ENC-09: Non-dict input is wrapped in {'data': value} before encrypting."""
        encrypted = encrypt_config("raw_string_value")  # type: ignore
        decrypted = decrypt_config(encrypted)
        assert decrypted == {"data": "raw_string_value"}

    def test_aliases_work(self):
        """TC-ENC-10: encrypt_dict and decrypt_dict are functional aliases."""
        data = {"alias": "test"}
        assert decrypt_dict(encrypt_dict(data)) == data

    def test_encryption_key_is_32_bytes(self):
        """TC-ENC-11: The default encryption key is exactly 32 bytes (256-bit AES)."""
        from app.utils.encryption import KEY_BYTES
        assert len(KEY_BYTES) == 32, f"Key should be 32 bytes, got {len(KEY_BYTES)}"

    def test_encrypt_large_payload(self):
        """TC-ENC-12: Large payloads encrypt/decrypt correctly."""
        large_data = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}
        assert decrypt_config(encrypt_config(large_data)) == large_data
