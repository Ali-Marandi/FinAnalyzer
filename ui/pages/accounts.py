"""
ui/pages/accounts.py - Chart of Accounts Page for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTreeWidget, QTreeWidgetItem, QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt

class AccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Account")
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. 1010")
        form.addRow("Account Code:", self.code_input)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Account Name...")
        form.addRow("Account Name:", self.name_input)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Asset", "Liability", "Equity", "Revenue", "Expense"])
        form.addRow("Account Type:", self.type_combo)
        
        self.balance_spin = QDoubleSpinBox()
        self.balance_spin.setRange(-10000000.0, 10000000.0)
        self.balance_spin.setPrefix("$ ")
        form.addRow("Initial Balance:", self.balance_spin)
        
        layout.addLayout(form)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

    def get_data(self):
        return {
            "code": self.code_input.text().strip(),
            "name": self.name_input.text().strip(),
            "type": self.type_combo.currentText(),
            "balance": self.balance_spin.value()
        }

class AccountsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title = QLabel("Chart of Accounts")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)

        header.addStretch()

        add_btn = QPushButton("+ Add Account")
        add_btn.clicked.connect(self.open_add_account)
        header.addWidget(add_btn)

        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Account Name", "Code", "Type", "Balance"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setAlternatingRowColors(True)

        self.load_accounts()
        layout.addWidget(self.tree)

    def load_accounts(self):
        self.tree.clear()

        categories = [
            ("Assets", [
                ("1010", "Cash on Hand", "Asset", "$150,400.00"),
                ("1020", "Silicon Valley Bank Checking", "Asset", "$2,000,000.00"),
                ("1200", "Accounts Receivable", "Asset", "$340,500.00"),
                ("1500", "Equipment & Software Assets", "Asset", "$450,000.00")
            ]),
            ("Liabilities", [
                ("2010", "Accounts Payable", "Liability", "$85,200.00"),
                ("2100", "Corporate Credit Card", "Liability", "$14,300.00"),
                ("2500", "SBA Term Loan", "Liability", "$500,000.00")
            ]),
            ("Equity", [
                ("3010", "Common Stock", "Equity", "$1,000,000.00"),
                ("3900", "Retained Earnings", "Category", "$1,341,400.00")
            ]),
            ("Revenue", [
                ("4010", "Enterprise SaaS Subscriptions", "Revenue", "$4,250,000.00"),
                ("4020", "Consulting & Professional Services", "Revenue", "$680,000.00")
            ]),
            ("Expenses", [
                ("5010", "Cloud Hosting (AWS/GCP)", "Expense", "$125,000.00"),
                ("5020", "Salaries & Wages", "Expense", "$2,400,000.00"),
                ("5030", "Office Rent & Facilities", "Expense", "$144,000.00"),
                ("5040", "Marketing & Growth", "Expense", "$320,000.00")
            ])
        ]

        for cat_name, accounts in categories:
            parent_item = QTreeWidgetItem(self.tree, [cat_name, "", "Category", ""])
            parent_item.setExpanded(True)
            for code, name, acc_type, bal in accounts:
                child = QTreeWidgetItem(parent_item, [name, code, acc_type, bal])
                child.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)

    def open_add_account(self):
        dlg = AccountDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            QMessageBox.information(self, "Success", f"Account {data['code']} - {data['name']} created.")
            self.load_accounts()
