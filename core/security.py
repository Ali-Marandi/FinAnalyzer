"""Security primitives for FinAnalyzer Enterprise.

The module contains password hashing, baseline RBAC helpers, audit logging, and a
local secret store. On Windows, the secret store protects its Fernet key with the
current user's DPAPI profile instead of leaving a raw key on disk. A file-key fallback
exists only for non-Windows local development; production deployment should use DPAPI
or an enterprise KMS supplied through FINANALYZER_MASTER_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import platform
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import bcrypt
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from core.models import User, UserRole


class KeyProtectionError(RuntimeError):
    """Raised when a local encryption key cannot be safely protected or recovered."""


class SecurityManager:
    """Compatibility helpers for password hashing, licensing, and legacy role checks."""

    def __init__(self, encryption_key: Optional[bytes] = None, audit_logger=None):
        self.fernet_key = encryption_key or Fernet.generate_key()
        self.cipher = Fernet(self.fernet_key)
        self.audit_logger = audit_logger

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    def encrypt_data(self, plaintext: str) -> str:
        return self.cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_data(self, ciphertext: str) -> str:
        return self.cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    def generate_license_key(self, company_name: str, days_valid: int = 365) -> str:
        expiry_date = (datetime.utcnow() + timedelta(days=days_valid)).strftime("%Y%m%d")
        payload = f"{company_name}:{expiry_date}"
        signature = hmac.HMAC(self.fernet_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16].upper()
        return base64.urlsafe_b64encode(f"{company_name}-{expiry_date}-{signature}".encode("utf-8")).decode("utf-8")

    def validate_license_key(self, license_key: str, company_name: str) -> bool:
        try:
            decoded = base64.urlsafe_b64decode(license_key.encode("utf-8")).decode("utf-8")
            comp, expiry_str, signature = decoded.rsplit("-", 2)
            if comp != company_name or datetime.utcnow() > datetime.strptime(expiry_str, "%Y%m%d"):
                return False
            payload = f"{comp}:{expiry_str}"
            expected = hmac.HMAC(self.fernet_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16].upper()
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False

    def check_permission(self, user: User, required_role: UserRole) -> bool:
        role_hierarchy = {UserRole.VIEWER: 1, UserRole.ACCOUNTANT: 2, UserRole.ADMIN: 3}
        return role_hierarchy.get(user.role, 0) >= role_hierarchy.get(required_role, 3)

    def log_audit(self, session: Session, user_id: Optional[int], action: str, details: Optional[str] = None) -> None:
        """Compatibility bridge that records legacy calls in the v2.4 audit chain."""
        if self.audit_logger is None:
            # Imported lazily because core.audit imports the DPAPI protector from this module.
            from core.audit import AuditLogger
            self.audit_logger = AuditLogger()
        self.audit_logger.record(
            session,
            action=action,
            category="security",
            outcome="success",
            severity="info",
            actor_id=user_id,
            source="security_manager",
            target_type="user" if user_id is not None else None,
            target_id=str(user_id) if user_id is not None else None,
            details={"legacy_details_present": bool(details)},
        )


class WindowsDpapiProtector:
    """Wrap Windows DPAPI via pywin32, binding data to the current Windows profile."""

    DESCRIPTION = "FinAnalyzer Enterprise local encryption key"

    def __init__(
        self,
        protect_function: Optional[Callable[[bytes], bytes]] = None,
        unprotect_function: Optional[Callable[[bytes], bytes]] = None,
    ) -> None:
        self._protect_function = protect_function
        self._unprotect_function = unprotect_function

    @property
    def available(self) -> bool:
        return self._protect_function is not None or platform.system() == "Windows"

    def protect(self, plaintext: bytes) -> bytes:
        if self._protect_function:
            return self._protect_function(plaintext)
        if platform.system() != "Windows":
            raise KeyProtectionError("Windows DPAPI is unavailable on this operating system.")
        try:
            import win32crypt
            return win32crypt.CryptProtectData(plaintext, self.DESCRIPTION, None, None, None, 0)[1]
        except Exception as exc:
            raise KeyProtectionError("Windows DPAPI could not protect the local encryption key.") from exc

    def unprotect(self, ciphertext: bytes) -> bytes:
        if self._unprotect_function:
            return self._unprotect_function(ciphertext)
        if platform.system() != "Windows":
            raise KeyProtectionError("Windows DPAPI is unavailable on this operating system.")
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(ciphertext, None, None, None, 0)[1]
        except Exception as exc:
            raise KeyProtectionError(
                "Windows DPAPI could not decrypt the local key. Sign in as the original Windows user or restore through the approved recovery process."
            ) from exc


class LocalSecretStore:
    """Encrypt integration secrets using a Fernet key protected by DPAPI on Windows.

    Key sources are ordered as follows: a deployment-managed environment key, a
    Windows DPAPI-protected local key, or (non-Windows development only) a mode-0600
    file key. Windows intentionally fails closed if DPAPI cannot protect or recover a
    local key; it does not silently fall back to a raw key file.
    """

    def __init__(
        self,
        key_path: str = "data/.finanalyzer.key",
        *,
        dpapi: Optional[WindowsDpapiProtector] = None,
        operating_system: Optional[str] = None,
    ) -> None:
        self._legacy_path = Path(key_path)
        self._dpapi_path = self._legacy_path.with_suffix(self._legacy_path.suffix + ".dpapi")
        self._os = operating_system or platform.system()
        self._dpapi = dpapi or WindowsDpapiProtector()
        self._mode = ""
        key = self._load_key()
        try:
            Fernet(key)
        except Exception as exc:
            raise KeyProtectionError("The configured local encryption key is not a valid Fernet key.") from exc
        self._cipher = Fernet(key)

    @property
    def protection_mode(self) -> str:
        """Return environment, dpapi, or file; suitable for diagnostics but never logs a key."""
        return self._mode

    def _load_key(self) -> bytes:
        environment_key = os.getenv("FINANALYZER_MASTER_KEY")
        if environment_key:
            self._mode = "environment"
            return environment_key.encode("utf-8")
        if self._os == "Windows":
            self._mode = "dpapi"
            return self._load_windows_dpapi_key()
        self._mode = "file"
        return self._load_non_windows_key()

    def _load_windows_dpapi_key(self) -> bytes:
        self._dpapi_path.parent.mkdir(parents=True, exist_ok=True)
        if self._dpapi_path.exists():
            return self._dpapi.unprotect(self._dpapi_path.read_bytes())

        # One-time migration from previous raw-key versions. Successful migration removes
        # the legacy key to avoid leaving a second unprotected copy on the filesystem.
        if self._legacy_path.exists():
            key = self._legacy_path.read_bytes().strip()
            self._write_dpapi_key(key)
            self._remove_legacy_key()
            return key

        key = Fernet.generate_key()
        self._write_dpapi_key(key)
        return key

    def _load_non_windows_key(self) -> bytes:
        self._legacy_path.parent.mkdir(parents=True, exist_ok=True)
        if self._legacy_path.exists():
            return self._legacy_path.read_bytes().strip()
        key = Fernet.generate_key()
        self._atomic_write(self._legacy_path, key)
        try:
            os.chmod(self._legacy_path, 0o600)
        except OSError:
            pass
        return key

    def _write_dpapi_key(self, key: bytes) -> None:
        protected = self._dpapi.protect(key)
        self._atomic_write(self._dpapi_path, protected)

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def _remove_legacy_key(self) -> None:
        try:
            self._legacy_path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise KeyProtectionError(
                "DPAPI migration completed, but the legacy raw key could not be removed. Remove it manually before production use."
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("A non-empty secret is required.")
        return self._cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


__all__ = ["SecurityManager", "WindowsDpapiProtector", "LocalSecretStore", "KeyProtectionError"]
