"""
Security module for FinAnalyzer Enterprise v2.0.0.
Provides user authentication with bcrypt, role-based access control (RBAC),
license key generation and validation, and Fernet data encryption.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
import bcrypt
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from core.models import User, UserRole, AuditLog

class SecurityManager:
    """Handles authentication, encryption, licensing, and access control."""

    def __init__(self, encryption_key: Optional[bytes] = None):
        # Generate or load Fernet encryption key
        self.fernet_key = encryption_key or Fernet.generate_key()
        self.cipher = Fernet(self.fernet_key)

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its bcrypt hash."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    def encrypt_data(self, plaintext: str) -> str:
        """Encrypt sensitive string data using Fernet (AES-128/256)."""
        return self.cipher.encrypt(plaintext.encode('utf-8')).decode('utf-8')

    def decrypt_data(self, ciphertext: str) -> str:
        """Decrypt Fernet encrypted data."""
        return self.cipher.decrypt(ciphertext.encode('utf-8')).decode('utf-8')

    def generate_license_key(self, company_name: str, days_valid: int = 365) -> str:
        """Generate a cryptographically signed enterprise license key."""
        expiry_date = (datetime.utcnow() + timedelta(days=days_valid)).strftime("%Y%m%d")
        payload = f"{company_name}:{expiry_date}"
        signature = hmac.HMAC(
            self.fernet_key,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:16].upper()
        
        raw_key = f"{company_name}-{expiry_date}-{signature}"
        return base64.urlsafe_b64encode(raw_key.encode('utf-8')).decode('utf-8')

    def validate_license_key(self, license_key: str, company_name: str) -> bool:
        """Validate an enterprise license key."""
        try:
            decoded = base64.urlsafe_b64decode(license_key.encode('utf-8')).decode('utf-8')
            parts = decoded.split('-')
            if len(parts) != 3:
                return False
            
            comp, expiry_str, sig = parts
            if comp != company_name:
                return False
            
            expiry_date = datetime.strptime(expiry_str, "%Y%m%d")
            if datetime.utcnow() > expiry_date:
                return False
            
            payload = f"{comp}:{expiry_str}"
            expected_sig = hmac.HMAC(
                self.fernet_key,
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()[:16].upper()
            
            return hmac.compare_digest(sig, expected_sig)
        except Exception:
            return False

    def check_permission(self, user: User, required_role: UserRole) -> bool:
        """Check if user has sufficient privileges based on RBAC hierarchy."""
        role_hierarchy = {
            UserRole.VIEWER: 1,
            UserRole.ACCOUNTANT: 2,
            UserRole.ADMIN: 3
        }
        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(required_role, 3)
        return user_level >= required_level

    def log_audit(self, session: Session, user_id: Optional[int], action: str, details: Optional[str] = None) -> None:
        """Record an audit log entry for compliance."""
        audit = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            timestamp=datetime.utcnow()
        )
        session.add(audit)
        session.commit()


class LocalSecretStore:
    """Persist or obtain a Fernet key for local integration secrets.

    A deployment may supply ``FINANALYZER_MASTER_KEY``. Otherwise a locally scoped
    key is created. The key file belongs to the operating-system user and must not
    be committed or copied outside the device without an approved recovery process.
    """

    def __init__(self, key_path: str = "data/.finanalyzer.key"):
        from pathlib import Path
        import os

        self._path = Path(key_path)
        configured_key = os.getenv("FINANALYZER_MASTER_KEY")
        if configured_key:
            key = configured_key.encode("utf-8")
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists():
                key = self._path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                self._path.write_bytes(key)
                try:
                    os.chmod(self._path, 0o600)
                except OSError:
                    # Windows permissions are governed by the current user profile/ACL.
                    pass
        self._cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("A non-empty secret is required.")
        return self._cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
