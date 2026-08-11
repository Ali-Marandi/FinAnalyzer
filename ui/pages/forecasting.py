"""
ui/pages/forecasting.py - AI Forecasting & Analytics Page for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QSlider, QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from ui.widgets.chart_widget import ChartWidget

class ForecastingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title = QLabel("AI Financial Forecasting & Anomaly Detection")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)

        header.addStretch()

        self.horizon_combo = QComboBox()
        self.horizon_combo.addItems(["3 Months Forecast", "6 Months Forecast", "12 Months Forecast"])
        self.horizon_combo.currentIndexChanged.connect(self.update_forecast)
        header.addWidget(self.horizon_combo)

        layout.addLayout(header)

        # Main Layout split into Chart and What-if / Anomaly panel
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # Left: Forecast Chart
        self.chart = ChartWidget("line")
        self.chart.plot_data(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul (Fcst)", "Aug (Fcst)", "Sep (Fcst)"],
            [120, 145, 132, 160, 185, 210, 230, 255, 280],
            title="Revenue & AI Cash Flow Projection ($K)",
            xlabel="Timeline", ylabel="Amount ($K)", color="#3498db"
        )
        content_layout.addWidget(self.chart, stretch=2)

        # Right: What-if Scenarios & Anomaly Panel
        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)

        # What-if Group
        whatif_group = QGroupBox("What-If Scenario Simulator")
        whatif_layout = QVBoxLayout(whatif_group)

        whatif_layout.addWidget(QLabel("Revenue Growth Rate (%):"))
        self.rev_slider = QSlider(Qt.Horizontal)
        self.rev_slider.setRange(-50, 100)
        self.rev_slider.setValue(15)
        self.rev_slider.setTickInterval(10)
        self.rev_slider.setTickPosition(QSlider.TicksBelow)
        whatif_layout.addWidget(self.rev_slider)

        whatif_layout.addWidget(QLabel("Expense Inflation (%):"))
        self.exp_slider = QSlider(Qt.Horizontal)
        self.exp_slider.setRange(0, 50)
        self.exp_slider.setValue(5)
        self.exp_slider.setTickInterval(5)
        self.exp_slider.setTickPosition(QSlider.TicksBelow)
        whatif_layout.addWidget(self.exp_slider)

        simulate_btn = QPushButton("Run Simulation")
        simulate_btn.clicked.connect(self.run_simulation)
        whatif_layout.addWidget(simulate_btn)

        right_layout.addWidget(whatif_group)

        # Anomaly Detection Group
        anomaly_group = QGroupBox("AI Anomaly Detection Results")
        anomaly_layout = QVBoxLayout(anomaly_group)
        
        self.anomaly_table = QTableWidget(2, 3)
        self.anomaly_table.setHorizontalHeaderLabels(["Date", "Anomaly Type", "Confidence"])
        self.anomaly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        anomalies = [
            ("2026-08-04", "Unusually high cloud server cost (AWS)", "98.4%"),
            ("2026-07-28", "Duplicate invoice payment detected", "92.1%")
        ]
        for r_idx, row in enumerate(anomalies):
            for c_idx, val in enumerate(row):
                self.anomaly_table.setItem(r_idx, c_idx, QTableWidgetItem(val))
        
        anomaly_layout.addWidget(self.anomaly_table)
        right_layout.addWidget(anomaly_group)

        content_layout.addLayout(right_layout, stretch=1)
        layout.addLayout(content_layout)

    def update_forecast(self):
        horizon = self.horizon_combo.currentText()
        if "3" in horizon:
            self.chart.plot_data(
                ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"],
                [120, 145, 132, 160, 185, 210, 230, 255, 280],
                title="Revenue & AI Cash Flow Projection (3 Months)",
                xlabel="Timeline", ylabel="Amount ($K)", color="#3498db"
            )
        elif "6" in horizon:
            self.chart.plot_data(
                ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                [120, 145, 132, 160, 185, 210, 230, 255, 280, 310, 340, 375],
                title="Revenue & AI Cash Flow Projection (6 Months)",
                xlabel="Timeline", ylabel="Amount ($K)", color="#3498db"
            )
        else:
            self.chart.plot_data(
                ["Q1-25", "Q2-25", "Q3-25", "Q4-25", "Q1-26", "Q2-26", "Q3-26 (Fcst)", "Q4-26 (Fcst)"],
                [420, 480, 510, 590, 640, 710, 780, 860],
                title="Revenue & AI Cash Flow Projection (12 Months)",
                xlabel="Timeline", ylabel="Amount ($K)", color="#3498db"
            )

    def run_simulation(self):
        rev_growth = self.rev_slider.value()
        exp_inf = self.exp_slider.value()
        self.chart.plot_data(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul (Sim)", "Aug (Sim)", "Sep (Sim)"],
            [120, 145, 132, 160, 185, 210, int(230 * (1 + rev_growth/100)), int(255 * (1 + rev_growth/100)), int(280 * (1 + rev_growth/100))],
            title=f"Simulation (Rev: +{rev_growth}%, Exp: +{exp_inf}%)",
            xlabel="Timeline", ylabel="Amount ($K)", color="#2ecc71"
        )
