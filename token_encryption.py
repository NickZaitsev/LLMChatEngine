"""
Token encryption utilities for securely storing bot tokens.

Uses Fernet symmetric encryption with a key from environment variables.
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """
    Get or derive the encryption key from environment variable.
    
    Derives a Fernet-compatible key from TOKEN_ENCRYPTION_KEY.
    
    Returns:
        32-byte Fernet-compatible key
    """
    key_str = os.getenv('TOKEN_ENCRYPTION_KEY', '')
    
    if not key_str:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is required before storing bot tokens. "
            "Generate one with cryptography.fernet.Fernet.generate_key()."
        )
    
    # Derive a 32-byte key using SHA256
    derived = hashlib.sha256(key_str.encode()).digest()
    return base64.urlsafe_b64encode(derived)


def encrypt_token(token: str) -> str:
    """
    Encrypt a bot token for secure storage.
    
    Args:
        token: The plain-text bot token
        
    Returns:
        Encrypted token string (base64)
    """
    key = _get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a stored bot token.
    
    Args:
        encrypted_token: The encrypted token string
        
    Returns:
        Plain-text bot token
    """
    key = _get_encryption_key()
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted_token.encode())
    return decrypted.decode()
