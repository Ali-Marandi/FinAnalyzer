#!/usr/bin/env python3
"""Minimal, self-contained HMAC-SHA256 audit-chain demonstration.

Run:
    python scripts/demo_hmac_audit_chain.py

The example intentionally verifies a clean chain and then modifies a local event
in memory. Verification must reject the modified chain. It does not use a real
production key and does not write application data.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


GENESIS_HASH = "0" * 64
SENSITIVE_KEYS = {"access_token", "authorization", "password", "refresh_token", "secret", "token"}


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    checked_events: int
    first_invalid_sequence: int | None = None
    reason: str = ""


def redact(value: Any) -> Any:
    """Remove common secrets before the event is signed or persisted."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(nested)
            for key, nested in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    return value


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Produce one deterministic byte representation for HMAC signing."""
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def sign(key: bytes, payload: Mapping[str, Any]) -> str:
    return hmac.new(key, canonical_json(payload), hashlib.sha256).hexdigest()


def payload_for(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly the signed fields, excluding the output event_hash itself."""
    return {
        "event_id": event["event_id"],
        "sequence": event["sequence"],
        "action": event["action"],
        "actor_id": event["actor_id"],
        "company_id": event["company_id"],
        "details": event["details"],
        "occurred_at": event["occurred_at"],
        "previous_hash": event["previous_hash"],
    }


class AuditChain:
    """Educational append-only chain. Production uses core.audit.AuditLogger instead."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Use a randomly generated key of at least 32 bytes.")
        self._key = key
        self.events: list[dict[str, Any]] = []
        self._last_hash = GENESIS_HASH

    def append(
        self,
        *,
        action: str,
        actor_id: int,
        company_id: int,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = {
            "event_id": str(uuid4()),
            "sequence": len(self.events) + 1,
            "action": action,
            "actor_id": actor_id,
            "company_id": company_id,
            "details": redact(details),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "previous_hash": self._last_hash,
        }
        event["event_hash"] = sign(self._key, payload_for(event))
        self.events.append(event)
        self._last_hash = event["event_hash"]
        return event

    def verify(self, events: list[dict[str, Any]] | None = None) -> VerificationResult:
        candidate_events = self.events if events is None else events
        expected_previous = GENESIS_HASH
        for expected_sequence, event in enumerate(candidate_events, start=1):
            if event.get("sequence") != expected_sequence:
                return VerificationResult(False, expected_sequence - 1, expected_sequence, "sequence mismatch")
            if event.get("previous_hash") != expected_previous:
                return VerificationResult(False, expected_sequence - 1, expected_sequence, "previous-hash mismatch")
            expected_hash = sign(self._key, payload_for(event))
            if not hmac.compare_digest(str(event.get("event_hash", "")), expected_hash):
                return VerificationResult(False, expected_sequence - 1, expected_sequence, "HMAC mismatch")
            expected_previous = event["event_hash"]
        return VerificationResult(True, len(candidate_events), None, "chain verified")


def run_demo() -> int:
    # Never replace this generated demonstration key with a hard-coded production key.
    chain = AuditChain(secrets.token_bytes(32))
    first = chain.append(
        action="period_close.requested",
        actor_id=41,
        company_id=7,
        details={"fiscal_year": 2025, "access_token": "never-persist-this"},
    )
    chain.append(
        action="period_close.executed",
        actor_id=84,
        company_id=7,
        details={"request_id": first["event_id"], "outcome": "success"},
    )

    clean = chain.verify()
    print(f"Clean chain: valid={clean.valid}, checked={clean.checked_events}, reason={clean.reason}")
    print(f"Redacted value: {chain.events[0]['details']['access_token']}")

    tampered = copy.deepcopy(chain.events)
    tampered[1]["details"]["outcome"] = "changed-after-persistence"
    altered = chain.verify(tampered)
    print(
        "Tampered chain: "
        f"valid={altered.valid}, first_invalid_sequence={altered.first_invalid_sequence}, reason={altered.reason}"
    )

    if not clean.valid or altered.valid:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
