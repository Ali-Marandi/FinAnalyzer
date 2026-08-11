"""
ui/widgets/chart_widget.py - Embedded Matplotlib chart widget for FinAnalyzer Enterprise v2.0.0
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
import matplotlib
matplotlib.use('Agg') # Use non-interactive backend for robust embedding
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class ChartWidget(QWidget):
    def __init__(self, chart_type="line", parent=None):
        super().__init__(parent)
        self.chart_type = chart_type
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        self.ax = self.figure.add_subplot(111)
        self.apply_theme_styling()

    def apply_theme_styling(self, dark_mode=True):
        if dark_mode:
            self.figure.patch.set_facecolor('#16213e')
            self.ax.set_facecolor('#16213e')
            text_color = '#ffffff'
            grid_color = '#2a3a5e'
        else:
            self.figure.patch.set_facecolor('#ffffff')
            self.ax.set_facecolor('#ffffff')
            text_color = '#1e293b'
            grid_color = '#cbd5e1'

        self.ax.tick_params(colors=text_color, labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color(grid_color)
        self.ax.xaxis.label.set_color(text_color)
        self.ax.yaxis.label.set_color(text_color)
        self.ax.title.set_color(text_color)
        self.ax.grid(True, linestyle='--', alpha=0.3, color=grid_color)

    def plot_data(self, x, y, title="", xlabel="", ylabel="", color="#e94560"):
        self.ax.clear()
        self.apply_theme_styling()
        
        if self.chart_type == "line":
            self.ax.plot(x, y, color=color, linewidth=2.5, marker='o', markersize=4)
        elif self.chart_type == "bar":
            self.ax.bar(x, y, color=color, alpha=0.85, width=0.6)
        elif self.chart_type == "area":
            self.ax.plot(x, y, color=color, linewidth=2)
            self.ax.fill_between(x, y, color=color, alpha=0.3)
            
        if title:
            self.ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        if xlabel:
            self.ax.set_xlabel(xlabel, fontsize=9)
        if ylabel:
            self.ax.set_ylabel(ylabel, fontsize=9)
            
        self.figure.tight_layout()
        self.canvas.draw()

    def plot_pie(self, labels, sizes, title=""):
        self.ax.clear()
        self.apply_theme_styling()
        colors = ['#e94560', '#0f3460', '#2ecc71', '#f39c12', '#3498db', '#9b59b6']
        self.ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors[:len(sizes)],
                    textprops={'color': 'white', 'fontsize': 9})
        if title:
            self.ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        self.figure.tight_layout()
        self.canvas.draw()
