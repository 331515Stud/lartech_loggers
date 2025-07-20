from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QScrollArea, QFileDialog, QLineEdit)
from PyQt6.QtCore import Qt, QTimer, QThreadPool, QRunnable, pyqtSignal, QObject
from PyQt6.QtGui import QCursor
from config import DARK_PALETTE, NUM_CHANNELS, DEFAULT_X, INITIAL_X_RANGE, MAX_THREADS
from data_loader import AsyncDataLoader
from plot_widget import AsyncPlotWidget
import numpy as np
from concurrent.futures import ThreadPoolExecutor


class PlotUpdater(QRunnable):
    def __init__(self, widget, x, y, x_range, cursor_x):
        super().__init__()
        self.widget = widget
        self.x = x
        self.y = y
        self.x_range = x_range
        self.cursor_x = cursor_x

    def run(self):
        self.widget.async_update(self.x, self.y, self.x_range, self.cursor_x)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("6-Channel Async Plot Viewer")
        self.setGeometry(100, 100, 1200, 900)
        self.setPalette(DARK_PALETTE)

        # Data initialization
        self.x = DEFAULT_X.copy()
        self.data = {f"y{i + 1}": np.zeros(len(DEFAULT_X)) for i in range(NUM_CHANNELS)}
        self.cursor_x = self.x[len(self.x) // 2]
        self.x_range = INITIAL_X_RANGE
        self.grab_scale_factor = 0.008
        self.pan_sensitivity = 0.5
        self.is_dragging = False
        self.is_dragging_cursor = False

        # Thread pools
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(MAX_THREADS)
        self.compute_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
        self.data_loader = AsyncDataLoader()
        self.data_loader.loaded.connect(self._on_data_loaded)

        # UI setup
        self._setup_ui()

        # Timer for operations
        self.timer = QTimer()
        self.timer.setInterval(30)  # 30ms ~ 33 FPS
        self.timer.timeout.connect(self._handle_operations)
        self.timer.start()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Plot area
        self.plot_scroll = QScrollArea()
        plot_widget = QWidget()
        self.plot_layout = QVBoxLayout(plot_widget)
        self.plot_scroll.setWidget(plot_widget)
        self.plot_scroll.setWidgetResizable(True)

        # Create plot widgets
        self.plot_widgets = []
        for i in range(NUM_CHANNELS):
            plot = AsyncPlotWidget(i + 1)
            self.plot_layout.addWidget(plot)
            self.plot_widgets.append(plot)

            # Connect mouse events to each plot
            plot.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
            plot.canvas.mpl_connect('scroll_event', self.on_scroll)
            plot.canvas.mpl_connect('button_press_event', self.on_mouse_press)
            plot.canvas.mpl_connect('button_release_event', self.on_mouse_release)

        # Control panel
        control_panel = self._create_control_panel()

        main_layout.addWidget(self.plot_scroll, stretch=4)
        main_layout.addLayout(control_panel, stretch=1)

        # Initial update
        self.update_plots()

    def _create_control_panel(self):
        panel = QVBoxLayout()

        # Value display
        self.value_label = QLabel("Values will appear here")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setStyleSheet("""
            font-family: monospace; font-size: 12px;
            color: white; background: #353535;
            padding: 5px; border: 1px solid #444;
            min-width: 200px;
        """)
        panel.addWidget(self.value_label)

        # X input
        self.x_input = QLineEdit()
        self.x_input.setPlaceholderText("Enter x position")
        self.x_input.setStyleSheet("""
            background: #353535; color: white;
            border: 1px solid #444; padding: 5px;
        """)
        self.x_input.textEdited.connect(self.on_x_input_changed)
        panel.addWidget(self.x_input)

        # Buttons
        buttons = [
            ("Find Cursor", self.center_on_cursor),
            ("Reset View", self.reset_view),
            ("Load CSV", self.load_csv)
        ]

        btn_style = """
            QPushButton {
                background: #353535; color: white;
                border: 1px solid #444; padding: 5px;
                min-width: 100px; margin: 2px;
            }
            QPushButton:hover { background: #454545; }
        """

        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(handler)
            panel.addWidget(btn)

        panel.addStretch()
        return panel

    def update_plots(self):
        # Update plots in parallel
        for i, plot in enumerate(self.plot_widgets):
            updater = PlotUpdater(plot, self.x, self.data[f"y{i + 1}"], self.x_range, self.cursor_x)
            self.thread_pool.start(updater)

        # Update values display asynchronously
        future = self.compute_executor.submit(self._compute_values)
        future.add_done_callback(self._update_values_display)

    def _compute_values(self):
        return [np.interp(self.cursor_x, self.x, self.data[f"y{i + 1}"]) for i in range(NUM_CHANNELS)]

    def _update_values_display(self, future):
        values = future.result()
        text = "\n".join([f"Ch{i + 1}: {val:.6f}" for i, val in enumerate(values)])
        self.value_label.setText(text)
        self.x_input.blockSignals(True)
        self.x_input.setText(f"{self.cursor_x:.4f}")
        self.x_input.blockSignals(False)

    def _handle_operations(self):
        """Handle periodic operations"""
        pass

    def center_on_cursor(self):
        width = self.x_range[1] - self.x_range[0]
        self.x_range = (
            max(self.cursor_x - width / 2, min(self.x)),
            min(self.cursor_x + width / 2, max(self.x))
        )
        self.update_plots()

    def reset_view(self):
        self.x_range = INITIAL_X_RANGE
        self.cursor_x = self.x[len(self.x) // 2]
        self.update_plots()

    def load_csv(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open CSV", "", "CSV Files (*.csv)")

        if file_name:
            self.value_label.setText("Loading data...")
            self.data_loader.load_csv(file_name, NUM_CHANNELS)

    def _on_data_loaded(self, data, error):
        if error:
            self.value_label.setText(error)
            return

        self.x = data['x']
        for i in range(NUM_CHANNELS):
            self.data[f"y{i + 1}"] = data[f'y{i + 1}']

        self.x_range = (np.min(self.x), np.max(self.x))
        self.cursor_x = (self.x_range[0] + self.x_range[1]) / 2
        self.value_label.setText("Data loaded successfully")
        self.update_plots()

    def on_x_input_changed(self, text):
        try:
            x_val = float(text) if text else 0.0
            self.cursor_x = np.clip(x_val, min(self.x), max(self.x))
            self.update_plots()
        except ValueError:
            pass

    def on_mouse_move(self, event):
        if event.inaxes is None or event.xdata is None:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            return

        near_cursor = abs(event.xdata - self.cursor_x) < (self.x_range[1] - self.x_range[0]) * 0.01
        self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor if near_cursor else Qt.CursorShape.OpenHandCursor))

        if self.is_dragging:
            if self.is_dragging_cursor:
                self.cursor_x = np.clip(event.xdata, min(self.x), max(self.x))
                self.update_plots()
            else:
                dx = (event.xdata - self.initial_x) * self.pan_sensitivity
                self.x_range = (
                    self.initial_xmin - dx,
                    self.initial_xmax - dx
                )
                self.update_plots()

    def on_mouse_press(self, event):
        if event.button == 1 and event.inaxes is not None and event.xdata is not None:
            self.is_dragging = True
            self.initial_x = event.xdata
            self.initial_xmin = self.x_range[0]
            self.initial_xmax = self.x_range[1]
            self.is_dragging_cursor = abs(event.xdata - self.cursor_x) < (self.x_range[1] - self.x_range[0]) * 0.01

    def on_mouse_release(self, event):
        if event.button == 1:
            self.is_dragging = False
            self.is_dragging_cursor = False

    def on_scroll(self, event):
        if event.inaxes is None:
            return

        center = event.xdata or self.cursor_x
        scale = 1 / 1.1 if event.button == 'up' else 1.1
        width = (self.x_range[1] - self.x_range[0]) * scale
        self.x_range = (
            max(center - width / 2, min(self.x)),
            min(center + width / 2, max(self.x))
        )
        self.update_plots()