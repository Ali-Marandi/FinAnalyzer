"""Desktop page for verified, company-scoped compliance evidence exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.authorization import AuthorizationService
from core.compliance_evidence import ComplianceEvidenceService, EvidenceExportError
from core.database import DatabaseManager
from core.identity import AuthenticatedPrincipal


class ComplianceEvidencePage(QWidget):
    """Creates an auditable JSON evidence pack after MFA and chain verification."""

    def __init__(self, principal: AuthenticatedPrincipal | None = None) -> None:
        super().__init__()
        root = Path(__file__).resolve().parents[2]
        self.database = DatabaseManager(str(root / "finanalyzer.db"))
        self.database.init_database()
        self.authorization = AuthorizationService()
        self.service = ComplianceEvidenceService(self.database, authorization=self.authorization)
        self.default_export_directory = root / "evidence_exports"
        self.principal = principal
        self._build_ui()
        self._set_session_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Compliance Evidence Packs")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel(
            "Generate a company-scoped JSON evidence pack only after recent MFA, explicit permission and complete HMAC audit-chain verification."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: palette(mid);")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.session_label = QLabel()
        self.session_label.setWordWrap(True)
        self.session_label.setStyleSheet("padding: 10px; background: palette(alternate-base); border-radius: 6px;")
        layout.addWidget(self.session_label)

        export_box = QGroupBox("Generate verified evidence pack")
        export_form = QFormLayout(export_box)
        self.company_input = QSpinBox()
        self.company_input.setRange(1, 2_147_483_647)
        self.output_input = QLineEdit(str(self.default_export_directory))
        self.output_input.setPlaceholderText("Local directory for a newly generated evidence-pack folder")
        self.export_button = QPushButton("Verify chain and export evidence pack")
        self.export_button.clicked.connect(self.export_evidence)
        export_form.addRow("Company ID", self.company_input)
        export_form.addRow("Output directory", self.output_input)
        export_form.addRow("", self.export_button)
        layout.addWidget(export_box)

        self.result_label = QLabel(
            "No evidence pack has been created in this session. Exported evidence should be transferred to the organization's approved SIEM, DMS or WORM repository."
        )
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("padding: 12px; background: palette(alternate-base); border-radius: 6px;")
        layout.addWidget(self.result_label)
        layout.addStretch()

    def set_principal(self, principal: AuthenticatedPrincipal | None) -> None:
        self.principal = principal
        self._set_session_state()

    def _set_session_state(self) -> None:
        active = isinstance(self.principal, AuthenticatedPrincipal)
        self.export_button.setEnabled(active)
        if active:
            self.session_label.setText(
                f"Enterprise session active for user #{self.principal.user_id}. Evidence export requires recent MFA and the compliance.evidence.export permission."
            )
        else:
            self.session_label.setText("Sign in with Enterprise SSO before exporting compliance evidence.")

    def export_evidence(self) -> None:
        if not isinstance(self.principal, AuthenticatedPrincipal):
            QMessageBox.warning(self, "Enterprise sign-in required", "Sign in with Enterprise SSO before exporting evidence.")
            return
        output_text = self.output_input.text().strip()
        if not output_text:
            QMessageBox.warning(self, "Output directory required", "Choose a local output directory for the evidence pack.")
            return
        try:
            result = self.service.export_company_evidence(
                self.company_input.value(), output_text, self.principal
            )
            self.result_label.setText(
                "EXPORTED: audit chain was verified before export.\n"
                f"Manifest: {result.manifest_path}\n"
                f"Manifest SHA-256: {result.manifest_sha256}\n"
                f"Company audit events: {result.audit_event_count}; global chain sequence: {result.audit_last_sequence}"
            )
            self.result_label.setStyleSheet("padding: 12px; color: #0b6e4f; background: #e8f5ee; border-radius: 6px;")
            QMessageBox.information(self, "Evidence pack exported", "The verified evidence pack has been written. Store it in approved external retention.")
        except (PermissionError, EvidenceExportError) as exc:
            self.result_label.setText(f"EXPORT BLOCKED: {exc}")
            self.result_label.setStyleSheet("padding: 12px; color: #a01818; background: #fff0f0; border-radius: 6px;")
        except Exception:
            self.result_label.setText("EXPORT FAILED: no usable evidence pack was retained. Review the audit log.")
            self.result_label.setStyleSheet("padding: 12px; color: #a01818; background: #fff0f0; border-radius: 6px;")


__all__ = ["ComplianceEvidencePage"]
