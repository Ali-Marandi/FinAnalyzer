"""
ui/widgets/card_widget.py - Summary card widget for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class SummaryCard(QFrame):
    def __init__(self, title, value, trend="", trend_positive=True, icon_text="", parent=None):
        super().__init__(parent)
        self.setObjectName("SummaryCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setLineWidth(1)
        self.setStyleSheet("""
            QFrame#SummaryCard {
                background-color: palette(window);
                border: 1px solid palette(mid);
                border-radius: 10px;
                padding: 15px;
            }
            QFrame#SummaryCard:hover {
                border: 1px solid palette(highlight);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

        top_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.title_label.setStyleSheet("color: palette(text); opacity: 0.8;")
        top_layout.addWidget(self.title_label)

        top_layout.addStretch()

        if icon_text:
            self.icon_label = QLabel(icon_text)
            self.icon_label.setFont(QFont("Segoe UI", 12))
            top_layout.addWidget(self.icon_label)

        layout.addLayout(top_layout)

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Segoe UI", 22, QFont.Bold))
        layout.addWidget(self.value_label)

        if trend:
            self.trend_label = QLabel(trend)
            trend_color = "#2ecc71" if trend_positive else "#e74c3c"
            self.trend_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.trend_label.setStyleSheet(f"color: {trend_color};")
            layout.addWidget(self.trend_label)

    def update_value(self, new_value, trend="", trend_positive=True):
        self.value_label.setText(new_value)
        if trend and hasattr(self, 'trend_label'):
            self.trend_label.setText(trend)
            trend_color = "#2ecc71" if trend_positive else "#e74c3c"
            self.trend_label.setStyleSheet(f"color: {trend_color};")
