"""Authenticated encryption of database records (AES-256-GCM).

Every stored value is encrypted with a random 96-bit nonce and authenticated
with "associated data" that identifies where the value lives (for example
`classes:<id>`). Moving ciphertext to another row or table, or changing a
single byte, makes decryption fail.

Blob layout: version (1 byte) | nonce (12 bytes) | ciphertext + GCM tag (16 bytes)
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_SIZE = 32  # bytes -> AES-256
NONCE_SIZE = 12
TAG_SIZE = 16
FORMAT_VERSION = 1


class DecryptionError(Exception):
    """The value was not encrypted with this key, or it was modified."""


def generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=KEY_SIZE * 8)


def encode_key(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode("ascii")


def decode_key(encoded: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError("Invalid encryption key encoding.") from error
    if len(key) != KEY_SIZE:
        raise ValueError("Invalid encryption key length.")
    return key


class RecordCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_SIZE:
            raise ValueError(f"The encryption key must be {KEY_SIZE} bytes.")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> bytes:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._aead.encrypt(nonce, plaintext, associated_data)
        return bytes([FORMAT_VERSION]) + nonce + ciphertext

    def decrypt(self, blob: bytes, associated_data: bytes) -> bytes:
        if len(blob) < 1 + NONCE_SIZE + TAG_SIZE or blob[0] != FORMAT_VERSION:
            raise DecryptionError("Unknown encrypted value format.")
        nonce, ciphertext = blob[1 : 1 + NONCE_SIZE], blob[1 + NONCE_SIZE :]
        try:
            return self._aead.decrypt(nonce, ciphertext, associated_data)
        except InvalidTag as error:
            raise DecryptionError("Wrong key or modified data.") from error
