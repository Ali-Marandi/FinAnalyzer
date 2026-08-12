"""Structured, tamper-evident security audit logging for FinAnalyzer v2.4.0.

The local audit trail is append-only by application policy and chained with an HMAC
key protected by Windows DPAPI (or a mode-0600 developer key outside Windows). This
makes unauthorized edits detectable during verification. It is not a substitute for
an external immutable/WORM sink when an attacker controls the Windows profile or the
local database and DPAPI context; enterprise deployments should export anchors/events
to their approved SIEM or evidence store.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import AuditChainState, AuditLog
from core.security import KeyProtectionError, WindowsDpapiProtector


GENESIS_HASH = "0" * 64
SENSITIVE_DETAIL_KEYS = {
    "access_token", "authorization", "client_secret", "cookie", "encrypted_access_token",
    "id_token", "password", "private_key", "public_token", "refresh_token", "secret", "token",
}


class AuditIntegrityError(RuntimeError):
    """Raised when the audit key or integrity chain cannot be used safely."""


@dataclass(frozen=True)
class AuditVerificationResult:
    valid: bool
    checked_events: int
    legacy_events: int
    first_invalid_sequence: Optional[int] = None
    message: str = ""


class AuditSigningKeyStore:
    """Holds an HMAC signing key without persisting it in raw form on Windows."""

    def __init__(
        self,
        key_path: str = "data/.finanalyzer.audit.hmac",
        *,
        dpapi: Optional[WindowsDpapiProtector] = None,
        operating_system: Optional[str] = None,
    ) -> None:
        self._raw_path = Path(key_path)
        self._protected_path = self._raw_path.with_suffix(self._raw_path.suffix + ".dpapi")
        self._os = operating_system or platform.system()
        self._dpapi = dpapi or WindowsDpapiProtector()
        self._key = self._load_key()

    @property
    def key_id(self) -> str:
        return hashlib.sha256(self._key).hexdigest()[:16]

    def key_bytes(self) -> bytes:
        return self._key

    def _load_key(self) -> bytes:
        configured = os.getenv("FINANALYZER_AUDIT_HMAC_KEY", "").strip()
        if configured:
            if len(configured) < 32:
                raise AuditIntegrityError("FINANALYZER_AUDIT_HMAC_KEY must be at least 32 characters.")
            return configured.encode("utf-8")
        if self._os == "Windows":
            return self._load_dpapi_key()
        return self._load_development_key()

    def _load_dpapi_key(self) -> bytes:
        self._protected_path.parent.mkdir(parents=True, exist_ok=True)
        if self._protected_path.exists():
            try:
                return self._dpapi.unprotect(self._protected_path.read_bytes())
            except KeyProtectionError as exc:
                raise AuditIntegrityError("The Windows DPAPI-protected audit signing key is unavailable.") from exc
        if self._raw_path.exists():
            # One-time migration from a legacy audit key, then remove the raw copy.
            key = self._raw_path.read_bytes()
            self._atomic_write(self._protected_path, self._dpapi.protect(key))
            self._remove_raw_key()
            return key
        key = os.urandom(32)
        self._atomic_write(self._protected_path, self._dpapi.protect(key))
        return key

    def _load_development_key(self) -> bytes:
        self._raw_path.parent.mkdir(parents=True, exist_ok=True)
        if self._raw_path.exists():
            return self._raw_path.read_bytes()
        key = os.urandom(32)
        self._atomic_write(self._raw_path, key)
        try:
            os.chmod(self._raw_path, 0o600)
        except OSError:
            pass
        return key

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

    def _remove_raw_key(self) -> None:
        try:
            self._raw_path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AuditIntegrityError("Audit key was migrated but the raw legacy key could not be removed.") from exc


class AuditLogger:
    """Writes security events and maintains one HMAC-linked chain per local database."""

    def __init__(self, key_store: Optional[AuditSigningKeyStore] = None) -> None:
        self.key_store = key_store or AuditSigningKeyStore()

    def record(
        self,
        session: Session,
        *,
        action: str,
        category: str,
        outcome: str,
        severity: str = "info",
        actor_id: Optional[int] = None,
        company_id: Optional[int] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        source: str = "desktop",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditLog:
        """Append an event and its HMAC link in the caller's database transaction."""
        if not action or not category or not outcome:
            raise ValueError("Audit events require action, category, and outcome.")
        occurred_at = self._as_utc(timestamp or datetime.now(timezone.utc))
        state = session.get(AuditChainState, "global")
        if state is None:
            state = AuditChainState(scope="global", last_sequence=0, last_hash=GENESIS_HASH, key_id=self.key_store.key_id)
            session.add(state)
            session.flush()
        if state.key_id and state.key_id != self.key_store.key_id:
            raise AuditIntegrityError(
                "The local audit signing-key identifier changed. Complete the approved audit-key rotation procedure before writing events."
            )
        sequence = state.last_sequence + 1
        event_id = str(uuid4())
        clean_details = self._redact(details or {})
        payload = self._canonical_payload(
            event_id=event_id,
            sequence=sequence,
            action=action,
            category=category,
            outcome=outcome,
            severity=severity,
            actor_id=actor_id,
            company_id=company_id,
            session_id=session_id,
            request_id=request_id,
            source=source,
            target_type=target_type,
            target_id=target_id,
            details=clean_details,
            timestamp=occurred_at,
            previous_hash=state.last_hash,
            key_id=self.key_store.key_id,
        )
        event_hash = self._sign(payload)
        event = AuditLog(
            event_id=event_id,
            sequence=sequence,
            user_id=actor_id,
            company_id=company_id,
            session_id=session_id,
            request_id=request_id,
            action=action,
            category=category,
            severity=severity,
            outcome=outcome,
            source=source,
            target_type=target_type,
            target_id=target_id,
            details=json.dumps(clean_details, ensure_ascii=False, sort_keys=True, default=str),
            previous_hash=state.last_hash,
            event_hash=event_hash,
            key_id=self.key_store.key_id,
            timestamp=occurred_at,
        )
        session.add(event)
        session.flush()
        state.last_sequence = sequence
        state.last_hash = event_hash
        state.key_id = self.key_store.key_id
        session.flush()
        return event

    def verify_chain(self, session: Session) -> AuditVerificationResult:
        """Verify all structured v2.4+ events; legacy pre-chain rows are reported separately."""
        events = list(session.scalars(
            select(AuditLog).where(AuditLog.sequence.is_not(None)).order_by(AuditLog.sequence)
        ))
        legacy = session.scalar(select(AuditLog).where(AuditLog.sequence.is_(None)).count()) if False else 0
        # SQLAlchemy's count() on Select is not portable; count legacy events in a small local list.
        legacy = len(list(session.scalars(select(AuditLog.id).where(AuditLog.sequence.is_(None)))))
        expected_previous = GENESIS_HASH
        expected_sequence = 1
        for event in events:
            if event.sequence != expected_sequence or event.previous_hash != expected_previous:
                return AuditVerificationResult(False, expected_sequence - 1, legacy, event.sequence, "Sequence or previous hash mismatch.")
            payload = self._canonical_payload(
                event_id=event.event_id or "",
                sequence=event.sequence,
                action=event.action,
                category=event.category or "",
                outcome=event.outcome or "",
                severity=event.severity or "",
                actor_id=event.user_id,
                company_id=event.company_id,
                session_id=event.session_id,
                request_id=event.request_id,
                source=event.source or "",
                target_type=event.target_type,
                target_id=event.target_id,
                details=json.loads(event.details or "{}"),
                timestamp=self._as_utc(event.timestamp),
                previous_hash=event.previous_hash or "",
                key_id=event.key_id or "",
            )
            if not event.event_hash or not hmac.compare_digest(event.event_hash, self._sign(payload)):
                return AuditVerificationResult(False, expected_sequence - 1, legacy, event.sequence, "HMAC verification failed.")
            expected_previous = event.event_hash
            expected_sequence += 1
        state = session.get(AuditChainState, "global")
        if events and (state is None or state.last_hash != expected_previous or state.last_sequence != len(events)):
            return AuditVerificationResult(False, len(events), legacy, None, "Chain state checkpoint does not match the event chain.")
        return AuditVerificationResult(True, len(events), legacy, None, "Audit chain verified.")

    def _sign(self, payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hmac.new(self.key_store.key_bytes(), canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def _canonical_payload(**values: Any) -> dict[str, Any]:
        normalized = dict(values)
        normalized["timestamp"] = AuditLogger._as_utc(normalized["timestamp"]).isoformat()
        return normalized

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            clean: dict[str, Any] = {}
            for key, nested in value.items():
                key_text = str(key)
                if key_text.lower() in SENSITIVE_DETAIL_KEYS:
                    clean[key_text] = "[REDACTED]"
                else:
                    clean[key_text] = cls._redact(nested)
            return clean
        if isinstance(value, (list, tuple, set)):
            return [cls._redact(item) for item in value]
        return value


__all__ = [
    "AuditIntegrityError", "AuditLogger", "AuditSigningKeyStore", "AuditVerificationResult", "GENESIS_HASH",
]
