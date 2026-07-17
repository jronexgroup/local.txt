import base64
import hashlib
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _derive_key(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = kdf.derive(password.encode())
    return key, salt


def encrypt(password: str, plaintext: str) -> str:
    key, salt = _derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    combined = salt + nonce + ciphertext
    return base64.urlsafe_b64encode(combined).decode()


def decrypt(password: str, token: str) -> str:
    combined = base64.urlsafe_b64decode(token.encode())
    salt = combined[:16]
    nonce = combined[16:28]
    ciphertext = combined[28:]
    key, _ = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def encrypt_file(password: str, data: bytes) -> bytes:
    key, salt = _derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def decrypt_file(password: str, data: bytes) -> bytes:
    salt = data[:16]
    nonce = data[16:28]
    ciphertext = data[28:]
    key, _ = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
