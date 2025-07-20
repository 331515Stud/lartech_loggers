from PyQt6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from concurrent.futures import ThreadPoolExecutor


class AsyncPlotWidget(QWidget):
    def __init__(self, channel_num, parent=None):
        super().__init__(parent)
        self.channel_num = channel_num
        self.figure = Figure(figsize=(6, 2), facecolor='black', dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)

        self._setup_axes()
        self._setup_layout()

        self.line = None
        self.cursor = None
        self.executor = ThreadPoolExecutor(max_workers=1)

    def _setup_axes(self):
        self.ax.set_facecolor('black')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.ax.grid(True, color='#444444', alpha=0.5)
        self.ax.tick_params(axis='both', colors='white')

    def _setup_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def async_update(self, x, y, x_range, cursor_x):
        if self.line is None:
            self._initial_draw(x, y, x_range, cursor_x)
        else:
            future = self.executor.submit(self._update_data, x, y, x_range, cursor_x)
            future.add_done_callback(lambda _: self.canvas.draw_idle())

    def _initial_draw(self, x, y, x_range, cursor_x):
        self.line, = self.ax.plot(x, y, label=f'Channel {self.channel_num}',
                                  color='red', linewidth=1.5, antialiased=True)
        self.cursor = self.ax.axvline(cursor_x, color='white', linestyle='--', linewidth=1)
        self.ax.legend(facecolor='#353535', edgecolor='white', labelcolor='white')
        self.ax.set_xlim(*x_range)
        self.canvas.draw()

    def _update_data(self, x, y, x_range, cursor_x):
        self.line.set_data(x, y)
        self.cursor.set_xdata([cursor_x])
        self.ax.set_xlim(*x_range)

        if np.any(y != 0):
            self.ax.relim()
            self.ax.autoscale_view(scalex=False, scaley=True)