"""Company-scoped compliance evidence packs for FinAnalyzer Enterprise.

The exporter produces a self-describing JSON evidence pack after verifying the
local HMAC audit chain. It is an export and verification aid, not an external
immutable evidence store; enterprises should place the resulting manifest hash
and files in their approved SIEM, DMS, or WORM repository.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select

from core.audit import AuditLogger
from core.authorization import AuthorizationDenied, AuthorizationService
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal, IdentityValidationError
from core.models import AuditChainState, AuditLog, FiscalYear, PeriodCloseRequest


class EvidenceExportError(RuntimeError):
    """Raised when a compliance evidence pack cannot be safely generated."""


@dataclass(frozen=True)
class EvidencePackResult:
    """Immutable result containing only non-secret evidence-pack metadata."""

    pack_directory: str
    manifest_path: str
    manifest_sha256: str
    audit_event_count: int
    audit_last_sequence: int
    generated_at: datetime


class ComplianceEvidenceService:
    """Exports company-scoped accounting and audit evidence after chain verification."""

    MFA_MAX_AGE = timedelta(minutes=15)

    def __init__(
        self,
        database: DatabaseManager,
        authorization: Optional[AuthorizationService] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.database = database
        self.audit_logger = audit_logger or AuditLogger()
        self.authorization = authorization or AuthorizationService(audit_logger=self.audit_logger)

    def export_company_evidence(
        self,
        company_id: int,
        output_directory: str | Path,
        principal: AuthenticatedPrincipal,
        *,
        timestamp: Optional[datetime] = None,
    ) -> EvidencePackResult:
        """Write an evidence pack only when the complete local audit chain is valid.

        Files are first written into a uniquely named local folder. If a database
        authorization or audit-recording operation fails, that folder is removed so
        the caller is not handed an unrecorded partial evidence pack.
        """
        generated_at = self._as_utc(timestamp or datetime.now(timezone.utc))
        base_directory = Path(output_directory).expanduser().resolve()
        pack_directory = base_directory / (
            f"finanalyzer-evidence-company-{company_id}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        )
        try:
            with self.database.get_session() as session:
                context = self._context(principal, company_id)
                self._require(session, context)
                verification = self.audit_logger.verify_chain(session)
                if not verification.valid:
                    self._record_export_event(
                        session,
                        principal,
                        company_id,
                        outcome="denied",
                        severity="warning",
                        details={
                            "reason": "audit_chain_invalid",
                            "first_invalid_sequence": verification.first_invalid_sequence,
                        },
                    )
                    session.commit()
                    raise EvidenceExportError(
                        "Compliance evidence export is blocked because the local audit chain is invalid."
                    )

                audit_events = self._audit_events(session, company_id)
                fiscal_years = self._fiscal_years(session, company_id)
                close_requests = self._close_requests(session, company_id)
                chain_state = session.get(AuditChainState, "global")
                if chain_state is None:
                    raise EvidenceExportError("Audit-chain checkpoint is unavailable.")

                pack_directory.mkdir(parents=True, exist_ok=False)
                file_hashes = {
                    "audit-events.json": self._write_json(pack_directory / "audit-events.json", audit_events),
                    "fiscal-years.json": self._write_json(pack_directory / "fiscal-years.json", fiscal_years),
                    "period-close-requests.json": self._write_json(
                        pack_directory / "period-close-requests.json", close_requests
                    ),
                }
                manifest = {
                    "format_version": "1.0",
                    "product": "FinAnalyzer Enterprise",
                    "company_id": company_id,
                    "generated_at": generated_at.isoformat(),
                    "audit_chain": {
                        "verified": True,
                        "checked_events": verification.checked_events,
                        "legacy_events": verification.legacy_events,
                        "last_sequence": chain_state.last_sequence,
                        "last_hash": chain_state.last_hash,
                        "key_id": chain_state.key_id,
                    },
                    "files": [
                        {"name": name, "sha256": digest}
                        for name, digest in sorted(file_hashes.items())
                    ],
                }
                manifest_sha256 = self._sha256(self._canonical_json(manifest))
                manifest["manifest_sha256"] = manifest_sha256
                manifest_path = pack_directory / "manifest.json"
                self._write_json(manifest_path, manifest)

                self._record_export_event(
                    session,
                    principal,
                    company_id,
                    outcome="success",
                    severity="notice",
                    details={
                        "manifest_sha256": manifest_sha256,
                        "audit_event_count": len(audit_events),
                        "audit_last_sequence": chain_state.last_sequence,
                        "file_count": len(file_hashes),
                    },
                )
                return EvidencePackResult(
                    pack_directory=str(pack_directory),
                    manifest_path=str(manifest_path),
                    manifest_sha256=manifest_sha256,
                    audit_event_count=len(audit_events),
                    audit_last_sequence=chain_state.last_sequence,
                    generated_at=generated_at,
                )
        except Exception:
            if pack_directory.exists():
                shutil.rmtree(pack_directory, ignore_errors=True)
            raise

    @staticmethod
    def _audit_events(session, company_id: int) -> list[dict[str, Any]]:
        events = list(session.scalars(
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
            .order_by(AuditLog.sequence, AuditLog.id)
        ))
        return [
            {
                "event_id": event.event_id,
                "sequence": event.sequence,
                "timestamp": ComplianceEvidenceService._as_utc(event.timestamp).isoformat(),
                "action": event.action,
                "category": event.category,
                "severity": event.severity,
                "outcome": event.outcome,
                "actor_id": event.user_id,
                "company_id": event.company_id,
                "session_id": event.session_id,
                "request_id": event.request_id,
                "source": event.source,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "details": ComplianceEvidenceService._details(event.details),
                "previous_hash": event.previous_hash,
                "event_hash": event.event_hash,
                "key_id": event.key_id,
            }
            for event in events
        ]

    @staticmethod
    def _fiscal_years(session, company_id: int) -> list[dict[str, Any]]:
        years = list(session.scalars(
            select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.year)
        ))
        return [
            {
                "id": year.id,
                "year": year.year,
                "start_date": year.start_date.isoformat(),
                "end_date": year.end_date.isoformat(),
                "is_closed": year.is_closed,
            }
            for year in years
        ]

    @staticmethod
    def _close_requests(session, company_id: int) -> list[dict[str, Any]]:
        requests = list(session.scalars(
            select(PeriodCloseRequest)
            .where(PeriodCloseRequest.company_id == company_id)
            .order_by(PeriodCloseRequest.requested_at, PeriodCloseRequest.id)
        ))
        return [
            {
                "id": request.id,
                "fiscal_year_id": request.fiscal_year_id,
                "closing_account_id": request.closing_account_id,
                "status": request.status.value,
                "requested_by_user_id": request.requested_by_user_id,
                "approved_by_user_id": request.approved_by_user_id,
                "requested_at": ComplianceEvidenceService._as_utc(request.requested_at).isoformat(),
                "approved_at": ComplianceEvidenceService._datetime_text(request.approved_at),
                "executed_at": ComplianceEvidenceService._datetime_text(request.executed_at),
                "rejection_reason_present": bool(request.rejection_reason),
            }
            for request in requests
        ]

    def _require(self, session, context) -> None:
        try:
            self.authorization.require(session, context, "compliance.evidence.export")
        except AuthorizationDenied:
            session.commit()
            raise

    def _record_export_event(
        self,
        session,
        principal: AuthenticatedPrincipal,
        company_id: int,
        *,
        outcome: str,
        severity: str,
        details: dict[str, Any],
    ) -> None:
        self.audit_logger.record(
            session,
            action="compliance.evidence.exported",
            category="compliance",
            outcome=outcome,
            severity=severity,
            actor_id=principal.user_id,
            company_id=company_id,
            session_id=principal.session_id,
            source="compliance_evidence_service",
            target_type="company",
            target_id=str(company_id),
            details=details,
        )

    @classmethod
    def _context(cls, principal: AuthenticatedPrincipal, company_id: int):
        if not isinstance(principal, AuthenticatedPrincipal):
            raise IdentityValidationError("A validated Enterprise session principal is required for evidence exports.")
        return principal.authorization_context(company_id, "compliance_evidence_export", mfa_max_age=cls.MFA_MAX_AGE)

    @staticmethod
    def _details(value: Optional[str]) -> Any:
        try:
            return json.loads(value or "{}")
        except json.JSONDecodeError:
            return {"unparseable_details": True}

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    @classmethod
    def _write_json(cls, path: Path, payload: Any) -> str:
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")
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
        return cls._sha256(content)

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _datetime_text(cls, value: Optional[datetime]) -> Optional[str]:
        return cls._as_utc(value).isoformat() if value else None


__all__ = ["ComplianceEvidenceService", "EvidenceExportError", "EvidencePackResult"]
