"""
AnnotationEngine Desktop - Encryption Utilities
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from annotation_engine.config import APP_DATA_DIR


class EncryptionManager:
    """Manage encryption for sensitive data like HF API keys."""
    
    def __init__(self):
        self.key_file = APP_DATA_DIR / '.key'
        self._fernet = None
        self._initialize_key()
    
    def _initialize_key(self):
        """Initialize or load encryption key."""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Restrict permissions (Unix only)
            try:
                os.chmod(self.key_file, 0o600)
            except (AttributeError, OSError):
                pass
        
        self._fernet = Fernet(key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data."""
        if not data:
            return ""
        encrypted = self._fernet.encrypt(data.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt string data."""
        if not encrypted_data:
            return ""
        try:
            decoded = base64.b64decode(encrypted_data.encode())
            decrypted = self._fernet.decrypt(decoded)
            return decrypted.decode()
        except Exception:
            return ""
    
    def encrypt_dict(self, data: dict) -> dict:
        """Encrypt all string values in a dictionary."""
        return {k: self.encrypt(v) if isinstance(v, str) else v for k, v in data.items()}
    
    def decrypt_dict(self, data: dict) -> dict:
        """Decrypt all string values in a dictionary."""
        return {k: self.decrypt(v) if isinstance(v, str) else v for k, v in data.items()}