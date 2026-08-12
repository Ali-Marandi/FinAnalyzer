"""Run due FinAnalyzer Enterprise report schedules under a validated service session.

Windows Task Scheduler must execute under a dedicated least-privilege Windows account
and supply FINANALYZER_SCHEDULER_SESSION_ID. The runner deliberately does not accept a
raw user id or caller-controlled MFA flag. v2.3.0 therefore fails closed until a
service-account/session lifecycle is configured by the enterprise identity layer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.automated_reporting import AutomatedReportService  # noqa: E402
from core.database import DatabaseManager  # noqa: E402
from core.identity import IdentityService, IdentityValidationError  # noqa: E402


def main() -> int:
    database = DatabaseManager(str(PROJECT_ROOT / "finanalyzer.db"))
    database.init_database()
    session_id = os.getenv("FINANALYZER_SCHEDULER_SESSION_ID", "").strip()
    if not session_id:
        raise RuntimeError(
            "Set FINANALYZER_SCHEDULER_SESSION_ID to a validated, least-privilege Enterprise service session. "
            "Raw actor IDs and MFA flags are not accepted."
        )
    identity = IdentityService(database)
    try:
        principal = identity.get_active_principal(session_id)
    except IdentityValidationError as exc:
        raise RuntimeError("The configured scheduler service session is invalid, revoked, or expired.") from exc
    service = AutomatedReportService(
        database=database,
        schedules_path=str(PROJECT_ROOT / "data" / "report_schedules.json"),
        output_dir=str(PROJECT_ROOT / "reports"),
    )
    outcomes = service.run_due(principal)
    print(json.dumps(outcomes, ensure_ascii=False, indent=2))
    return 0 if all(outcome["status"] == "completed" for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
