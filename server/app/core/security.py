import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import get_settings

settings = get_settings()


def get_fernet() -> Fernet:
    # Derive a proper Fernet key from the ENCRYPTION_KEY setting
    # Use SHA256 to get 32 bytes, then base64 encode for Fernet
    secret = settings.ENCRYPTION_KEY.encode()
    key = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt HF API key for storage."""
    f = get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt HF API key for use."""
    f = get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()