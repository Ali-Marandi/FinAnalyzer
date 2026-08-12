"""Run all due FinAnalyzer Enterprise report schedules.

Configure this file as a Windows Task Scheduler action. It reads local schedule
records, writes outputs to the reports directory, and only uses email/Telegram when
explicitly configured through protected environment variables.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.automated_reporting import AutomatedReportService  # noqa: E402
from core.database import DatabaseManager  # noqa: E402


def main() -> int:
    database = DatabaseManager(str(PROJECT_ROOT / "finanalyzer.db"))
    database.init_database()
    service = AutomatedReportService(
        database=database,
        schedules_path=str(PROJECT_ROOT / "data" / "report_schedules.json"),
        output_dir=str(PROJECT_ROOT / "reports"),
    )
    outcomes = service.run_due()
    print(json.dumps(outcomes, ensure_ascii=False, indent=2))
    return 0 if all(outcome["status"] == "completed" for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
