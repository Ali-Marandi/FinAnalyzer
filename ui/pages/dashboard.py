"""
ui/pages/dashboard.py - Enterprise Dashboard Page for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton
from PySide6.QtCore import Qt, QDate
from ui.widgets.card_widget import SummaryCard
from ui.widgets.chart_widget import ChartWidget

class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Header with Period Selector
        header_layout = QHBoxLayout()
        title_label = QLabel("Executive Dashboard")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        period_label = QLabel(f"Period: {QDate.currentDate().toString('MMMM yyyy')}")
        period_label.setStyleSheet("font-weight: bold; color: palette(highlight);")
        header_layout.addWidget(period_label)

        main_layout.addLayout(header_layout)

        # Summary Cards Grid
        cards_layout = QGridLayout()
        cards_layout.setSpacing(15)

        self.card_revenue = SummaryCard("Total Revenue", "$1,245,800.00", "+12.5% vs last month", True, "📈")
        self.card_expenses = SummaryCard("Total Expenses", "$842,300.00", "-3.2% vs last month", True, "📉")
        self.card_net_income = SummaryCard("Net Income", "$403,500.00", "+18.4% vs last month", True, "💰")
        self.card_cash = SummaryCard("Cash Balance", "$2,150,400.00", "+5.1% liquidity ratio", True, "🏦")

        cards_layout.addWidget(self.card_revenue, 0, 0)
        cards_layout.addWidget(self.card_expenses, 0, 1)
        cards_layout.addWidget(self.card_net_income, 0, 2)
        cards_layout.addWidget(self.card_cash, 0, 3)

        main_layout.addLayout(cards_layout)

        # Charts Section
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(15)

        self.revenue_chart = ChartWidget("line")
        self.revenue_chart.plot_data(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            [120, 145, 132, 160, 185, 210],
            title="Monthly Revenue Trend ($K)",
            xlabel="Month", ylabel="Revenue ($K)", color="#2ecc71"
        )
        charts_layout.addWidget(self.revenue_chart)

        self.expense_chart = ChartWidget("bar")
        self.expense_chart.plot_data(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            [90, 95, 88, 105, 115, 120],
            title="Monthly Expenses ($K)",
            xlabel="Month", ylabel="Expenses ($K)", color="#e74c3c"
        )
        charts_layout.addWidget(self.expense_chart)

        main_layout.addLayout(charts_layout)

        # Recent Transactions Table
        recent_label = QLabel("Recent Transactions")
        recent_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(recent_label)

        self.table = QTableWidget(5, 5)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Account", "Category", "Amount"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)

        sample_data = [
            ("2026-08-10", "Client Invoice #1042 - Acme Corp", "Accounts Receivable", "Sales", "$15,400.00"),
            ("2026-08-09", "AWS Cloud Infrastructure Hosting", "Bank Account", "Utilities", "$2,150.00"),
            ("2026-08-08", "Office Rent - HQ Floor 4", "Bank Account", "Rent", "$12,000.00"),
            ("2026-08-07", "Software Subscriptions (GitHub/Jira)", "Bank Account", "Software", "$1,450.00"),
            ("2026-08-06", "Enterprise Consulting Retainer", "Accounts Receivable", "Sales", "$8,500.00")
        ]

        for row_idx, row_data in enumerate(sample_data):
            for col_idx, text in enumerate(row_data):
                item = QTableWidgetItem(text)
                if col_idx == 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

        main_layout.addWidget(self.table)
