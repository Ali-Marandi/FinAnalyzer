"""Automated management reports for FinAnalyzer Enterprise v2.

Reports are derived from the double-entry ledger rather than demo values. Schedule
records remain local; optional email or Telegram delivery reads credentials from
environment variables and never writes secrets into the schedule file.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

import requests
from sqlalchemy import select

from core.accounting_engine import AccountingEngine
from core.database import DatabaseManager
from core.import_export import DataImportExport
from core.models import Company, JournalEntry


class ReportingError(RuntimeError):
    """Raised when a scheduled report cannot be produced or delivered safely."""


@dataclass
class ReportSchedule:
    id: str
    company_id: int
    name: str
    cadence: str = "monthly"
    formats: List[str] = field(default_factory=lambda: ["pdf", "xlsx"])
    hour_utc: int = 8
    weekday: int = 0
    recipients: List[str] = field(default_factory=list)
    telegram_chat_id: Optional[str] = None
    enabled: bool = True
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None

    def validate(self) -> None:
        if self.cadence not in {"daily", "weekly", "monthly"}:
            raise ReportingError("cadence must be daily, weekly, or monthly")
        if not 0 <= self.hour_utc <= 23:
            raise ReportingError("hour_utc must be between 0 and 23")
        if not 0 <= self.weekday <= 6:
            raise ReportingError("weekday must be between Monday (0) and Sunday (6)")
        if not set(self.formats).issubset({"pdf", "xlsx"}):
            raise ReportingError("formats may contain only pdf and xlsx")


class ManagementReportBuilder:
    """Build report data from the current enterprise chart of accounts and journal."""

    def __init__(self, database: DatabaseManager):
        self.database = database

    def build(self, company_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        with self.database.get_session() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise ReportingError("The selected company does not exist.")
            engine = AccountingEngine(session, company_id)
            trial_balance = engine.calculate_trial_balance(end_date)
            balance_sheet = engine.generate_balance_sheet(end_date)
            income_statement = engine.generate_income_statement(start_date, end_date)
            entry_count = len(list(session.scalars(
                select(JournalEntry).where(
                    JournalEntry.company_id == company_id,
                    JournalEntry.date >= start_date,
                    JournalEntry.date <= end_date,
                )
            )))
            company_name = company.name
            currency_code = company.currency_code

        return {
            "metadata": {
                "company": company_name,
                "currency_code": currency_code,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "FinAnalyzer double-entry ledger",
            },
            "trial_balance": trial_balance,
            "balance_sheet": balance_sheet,
            "income_statement": income_statement,
            "entry_count": entry_count,
        }


class EnterpriseReportGenerator:
    """Produce management PDF and Excel reports from a verified ledger snapshot."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, report: Dict[str, Any], formats: Iterable[str], prefix: str = "management_pack") -> Dict[str, str]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        created: Dict[str, str] = {}
        for output_format in formats:
            normalized = output_format.lower().replace("excel", "xlsx")
            path = self.output_dir / f"{prefix}_{stamp}.{normalized}"
            if normalized == "pdf":
                created["pdf"] = self.generate_pdf(report, path)
            elif normalized == "xlsx":
                created["xlsx"] = self.generate_excel(report, path)
            else:
                raise ReportingError(f"Unsupported report format: {output_format}")
        return created

    def generate_pdf(self, report: Dict[str, Any], output_path: Path) -> str:
        summary = self._summary(report)
        title = f"FinAnalyzer Management Pack | {report['metadata']['company']}"
        return DataImportExport.generate_pdf_report(title, summary, str(output_path))

    def generate_excel(self, report: Dict[str, Any], output_path: Path) -> str:
        return DataImportExport.export_excel_with_formulas(report["trial_balance"], str(output_path))

    @staticmethod
    def _summary(report: Dict[str, Any]) -> Dict[str, Any]:
        metadata = report["metadata"]
        balance = report["balance_sheet"]
        income = report["income_statement"]
        return {
            "company": metadata["company"],
            "period_start": metadata["period_start"],
            "period_end": metadata["period_end"],
            "currency": metadata["currency_code"],
            "ledger_entries": report["entry_count"],
            "total_assets": balance["total_assets"],
            "total_liabilities": balance["total_liabilities"],
            "total_equity": balance["total_equity"],
            "balance_sheet_balanced": balance["is_balanced"],
            "total_revenue": income["total_revenue"],
            "total_expense": income["total_expense"],
            "net_income": income["net_income"],
            "generated_at": metadata["generated_at"],
            "credential_policy": "No banking access tokens or delivery secrets are included in reports.",
        }


class AutomatedReportService:
    """Evaluate local schedules, create reports, and perform opt-in delivery."""

    def __init__(
        self,
        database: DatabaseManager,
        schedules_path: str = "data/report_schedules.json",
        output_dir: str = "reports",
    ):
        self.database = database
        self.builder = ManagementReportBuilder(database)
        self.generator = EnterpriseReportGenerator(output_dir)
        self.schedules_path = Path(schedules_path)
        self.schedules_path.parent.mkdir(parents=True, exist_ok=True)

    def create_schedule(
        self,
        company_id: int,
        name: str,
        cadence: str = "monthly",
        formats: Iterable[str] = ("pdf", "xlsx"),
        hour_utc: int = 8,
        weekday: int = 0,
        recipients: Optional[Iterable[str]] = None,
        telegram_chat_id: Optional[str] = None,
    ) -> ReportSchedule:
        schedule = ReportSchedule(
            id=str(uuid4()),
            company_id=company_id,
            name=name,
            cadence=cadence,
            formats=list(formats),
            hour_utc=hour_utc,
            weekday=weekday,
            recipients=list(recipients or []),
            telegram_chat_id=telegram_chat_id,
        )
        schedule.validate()
        schedule.next_run_at = self._next_run(schedule, datetime.now(timezone.utc)).isoformat()
        schedules = self.list_schedules()
        schedules.append(schedule)
        self._write_schedules(schedules)
        return schedule

    def list_schedules(self) -> List[ReportSchedule]:
        if not self.schedules_path.exists():
            return []
        return [ReportSchedule(**record) for record in json.loads(self.schedules_path.read_text(encoding="utf-8"))]

    def run_due(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        schedules = self.list_schedules()
        outcomes: List[Dict[str, Any]] = []
        changed = False
        for schedule in schedules:
            if not schedule.enabled:
                continue
            due = self._parse_datetime(schedule.next_run_at)
            if due and due > now:
                continue
            try:
                files = self.run_schedule(schedule)
                schedule.last_run_at = now.isoformat()
                outcomes.append({"schedule_id": schedule.id, "status": "completed", "files": files})
            except Exception as exc:
                outcomes.append({"schedule_id": schedule.id, "status": "failed", "error": str(exc)})
            schedule.next_run_at = self._next_run(schedule, now).isoformat()
            changed = True
        if changed:
            self._write_schedules(schedules)
        return outcomes

    def run_schedule(self, schedule: ReportSchedule) -> Dict[str, str]:
        end = datetime.now(timezone.utc).date()
        start = self._start_date(schedule.cadence, end)
        report = self.builder.build(schedule.company_id, start, end)
        files = self.generator.generate_all(report, schedule.formats, prefix=self._safe_name(schedule.name))
        self._deliver(files, schedule)
        return files

    def _deliver(self, files: Dict[str, str], schedule: ReportSchedule) -> None:
        if schedule.recipients:
            self._send_email(files, schedule)
        if schedule.telegram_chat_id:
            self._send_telegram(files, schedule.telegram_chat_id)

    @staticmethod
    def _send_email(files: Dict[str, str], schedule: ReportSchedule) -> None:
        host = os.getenv("FINANALYZER_SMTP_HOST")
        username = os.getenv("FINANALYZER_SMTP_USERNAME")
        password = os.getenv("FINANALYZER_SMTP_PASSWORD")
        sender = os.getenv("FINANALYZER_EMAIL_FROM") or username
        port = int(os.getenv("FINANALYZER_SMTP_PORT", "587"))
        if not all([host, username, password, sender]):
            raise ReportingError("SMTP delivery was selected but SMTP environment variables are incomplete.")
        message = EmailMessage()
        message["Subject"] = f"FinAnalyzer automated report | {schedule.name}"
        message["From"] = sender
        message["To"] = ", ".join(schedule.recipients)
        message.set_content("Attached are the requested FinAnalyzer reports. Banking credentials are not included.")
        for extension, file_path in files.items():
            path = Path(file_path)
            subtype = "pdf" if extension == "pdf" else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            message.add_attachment(path.read_bytes(), maintype="application", subtype=subtype, filename=path.name)
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)

    @staticmethod
    def _send_telegram(files: Dict[str, str], chat_id: str) -> None:
        token = os.getenv("FINANALYZER_TELEGRAM_BOT_TOKEN")
        if not token:
            raise ReportingError("Telegram delivery was selected but FINANALYZER_TELEGRAM_BOT_TOKEN is not configured.")
        for file_path in files.values():
            with open(file_path, "rb") as document:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id},
                    files={"document": document},
                    timeout=45,
                )
                response.raise_for_status()

    def _write_schedules(self, schedules: Iterable[ReportSchedule]) -> None:
        temporary = self.schedules_path.with_suffix(".tmp")
        temporary.write_text(json.dumps([asdict(schedule) for schedule in schedules], ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.schedules_path)

    @staticmethod
    def _next_run(schedule: ReportSchedule, now: datetime) -> datetime:
        candidate = now.replace(hour=schedule.hour_utc, minute=0, second=0, microsecond=0)
        if schedule.cadence == "daily":
            return candidate if candidate > now else candidate + timedelta(days=1)
        if schedule.cadence == "weekly":
            candidate += timedelta(days=(schedule.weekday - candidate.weekday()) % 7)
            return candidate if candidate > now else candidate + timedelta(days=7)
        candidate = candidate.replace(day=1)
        if candidate <= now:
            year = candidate.year + (candidate.month == 12)
            month = 1 if candidate.month == 12 else candidate.month + 1
            candidate = candidate.replace(year=year, month=month)
        return candidate

    @staticmethod
    def _start_date(cadence: str, end: date) -> date:
        return end - timedelta(days={"daily": 1, "weekly": 7, "monthly": 31}[cadence])

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(character if character.isalnum() else "_" for character in value).strip("_") or "report"


__all__ = ["ReportSchedule", "ManagementReportBuilder", "EnterpriseReportGenerator", "AutomatedReportService", "ReportingError"]
