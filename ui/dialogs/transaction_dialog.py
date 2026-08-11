"""
ui/dialogs/transaction_dialog.py - Transaction Entry Dialog for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, 
    QDateEdit, QDoubleSpinBox, QPushButton, QMessageBox, QFormLayout
)
from PySide6.QtCore import QDate, Qt

class TransactionDialog(QDialog):
    def __init__(self, accounts=None, categories=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Transaction")
        self.setFixedWidth(450)
        self.accounts = accounts or ["Cash", "Bank Account", "Accounts Receivable", "Accounts Payable"]
        self.categories = categories or ["Sales", "Utilities", "Rent", "Software", "Salaries", "Supplies"]
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        form_layout.addRow("Date:", self.date_edit)

        self.account_combo = QComboBox()
        self.account_combo.addItems(self.accounts)
        form_layout.addRow("Account:", self.account_combo)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Debit", "Credit"])
        form_layout.addRow("Type:", self.type_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 10000000.00)
        self.amount_spin.setValue(100.00)
        self.amount_spin.setPrefix("$ ")
        form_layout.addRow("Amount:", self.amount_spin)

        self.category_combo = QComboBox()
        self.category_combo.addItems(self.categories)
        form_layout.addRow("Category:", self.category_combo)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Enter transaction description...")
        form_layout.addRow("Description:", self.desc_input)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("Save Transaction")
        self.save_btn.clicked.connect(self.validate_and_accept)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def validate_and_accept(self):
        if not self.desc_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Please enter a transaction description.")
            return
        self.accept()

    def get_data(self):
        return {
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "account": self.account_combo.currentText(),
            "type": self.type_combo.currentText(),
            "amount": self.amount_spin.value(),
            "category": self.category_combo.currentText(),
            "description": self.desc_input.text().strip()
        }
