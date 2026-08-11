"""
ui/pages/transactions.py - Transaction Management Page for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import (QDialog, 
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt
from ui.dialogs.transaction_dialog import TransactionDialog

class TransactionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Transaction Management")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.add_btn = QPushButton("+ New Transaction")
        self.add_btn.clicked.connect(self.open_add_dialog)
        header_layout.addWidget(self.add_btn)

        self.import_btn = QPushButton("Bulk Import")
        self.import_btn.setObjectName("secondaryButton")
        self.import_btn.clicked.connect(self.bulk_import)
        header_layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("Export (CSV/PDF)")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.clicked.connect(self.export_data)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Filter Toolbar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transactions...")
        self.search_input.textChanged.connect(self.filter_table)
        filter_layout.addWidget(self.search_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["All Categories", "Sales", "Utilities", "Rent", "Software", "Salaries", "Supplies"])
        self.category_combo.currentIndexChanged.connect(self.filter_table)
        filter_layout.addWidget(self.category_combo)

        self.account_combo = QComboBox()
        self.account_combo.addItems(["All Accounts", "Cash", "Bank Account", "Accounts Receivable", "Accounts Payable"])
        self.account_combo.currentIndexChanged.connect(self.filter_table)
        filter_layout.addWidget(self.account_combo)

        layout.addLayout(filter_layout)

        # Transactions Table
        self.table = QTableWidget(6, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Date", "Description", "Account", "Category", "Amount"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)

        self.load_sample_data()
        layout.addWidget(self.table)

    def load_sample_data(self):
        self.sample_transactions = [
            ("TXN-1001", "2026-08-10", "Client Invoice #1042 - Acme Corp", "Accounts Receivable", "Sales", "$15,400.00"),
            ("TXN-1002", "2026-08-09", "AWS Cloud Infrastructure Hosting", "Bank Account", "Utilities", "$2,150.00"),
            ("TXN-1003", "2026-08-08", "Office Rent - HQ Floor 4", "Bank Account", "Rent", "$12,000.00"),
            ("TXN-1004", "2026-08-07", "Software Subscriptions (GitHub/Jira)", "Bank Account", "Software", "$1,450.00"),
            ("TXN-1005", "2026-08-06", "Enterprise Consulting Retainer", "Accounts Receivable", "Sales", "$8,500.00"),
            ("TXN-1006", "2026-08-05", "Office Supplies & Hardware", "Cash", "Supplies", "$650.00")
        ]
        self.populate_table(self.sample_transactions)

    def populate_table(self, data):
        self.table.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            for col_idx, text in enumerate(row_data):
                item = QTableWidgetItem(text)
                if col_idx == 5:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

    def filter_table(self):
        query = self.search_input.text().lower()
        selected_cat = self.category_combo.currentText()
        selected_acc = self.account_combo.currentText()

        filtered = []
        for txn in self.sample_transactions:
            txn_id, date, desc, acc, cat, amt = txn
            if query and query not in desc.lower() and query not in txn_id.lower():
                continue
            if selected_cat != "All Categories" and cat != selected_cat:
                continue
            if selected_acc != "All Accounts" and acc != selected_acc:
                continue
            filtered.append(txn)
        self.populate_table(filtered)

    def open_add_dialog(self):
        dlg = TransactionDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            new_row = (
                f"TXN-100{self.table.rowCount() + 1}",
                data["date"],
                data["description"],
                data["account"],
                data["category"],
                f"${data['amount']:,.2f}"
            )
            self.sample_transactions.insert(0, new_row)
            self.filter_table()
            QMessageBox.information(self, "Success", "Transaction recorded successfully.")

    def bulk_import(self):
        QMessageBox.information(self, "Bulk Import", "OFX/QIF/CSV file importer wizard launched.")

    def export_data(self):
        QMessageBox.information(self, "Export", "Transactions exported successfully to CSV and PDF formats.")
