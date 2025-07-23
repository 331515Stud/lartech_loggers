import sys
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QTextEdit,
                             QFrame)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QCursor, QColor, QPalette
import pyqtgraph as pg
from datetime import datetime, timedelta
from io import StringIO


# Настройка тёмной темы для приложения
def set_dark_theme(app):
    app.setStyle("Fusion")

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(142, 45, 197))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

    app.setPalette(dark_palette)
    app.setStyleSheet("""
        QPushButton {
            background-color: #5A5A5A;
            border: 1px solid #5A5A5A;
            border-radius: 4px;
            padding: 5px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #6A6A6A;
            border: 1px solid #6A6A6A;
        }
        QPushButton:pressed {
            background-color: #4A4A4A;
            border: 1px solid #4A4A4A;
        }
        QTextEdit {
            background-color: #353535;
            border: 1px solid #5A5A5A;
        }
    """)


class CustomInfiniteLine(pg.InfiniteLine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseHover(True)
        self.is_dragging = False

    def mouseDragEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if ev.isStart():
                self.is_dragging = True
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif ev.isFinish():
                self.is_dragging = False
                QApplication.restoreOverrideCursor()
            super().mouseDragEvent(ev)

    def hoverEvent(self, ev):
        if not self.is_dragging and self.movable and ev.isEnter():
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif ev.isExit():
            QApplication.restoreOverrideCursor()


class MainWindow(QMainWindow):
    def make_cursor_sync_function(self, source_col):
        def sync_all_cursors(line):
            pos = line.value()
            for col, cursor in self.cursors.items():
                if col != source_col:
                    cursor.blockSignals(True)
                    cursor.setValue(pos)
                    cursor.blockSignals(False)
            self.update_values()

        return sync_all_cursors

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV Data Plotter - Synced Stacked Plots with Cursor")
        self.setGeometry(100, 100, 1400, 1200)

        # Main widget and layout
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QHBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Left panel (plots)
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(1000)
        self.plot_layout = QVBoxLayout()
        self.left_panel.setLayout(self.plot_layout)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(5)

        # Right panel (controls and values)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.right_panel.setMinimumWidth(300)
        self.right_panel.setMaximumWidth(350)
        self.right_layout = QVBoxLayout()
        self.right_panel.setLayout(self.right_layout)
        self.right_layout.setContentsMargins(5, 5, 5, 5)
        self.right_layout.setSpacing(10)

        # Add panels to main layout
        self.main_layout.addWidget(self.left_panel)
        self.main_layout.addWidget(self.right_panel)

        # Create plot widgets
        self.plot_widgets = {}
        self.view_boxes = {}
        self.cursors = {}
        columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
        y_range = [0, 300]

        for i, col in enumerate(columns):
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground('k')  # Black background

            plot_widget.getAxis('left').setTextPen('w')  # White text for y-axis
            plot_widget.getAxis('bottom').setTextPen('w')  # White text for x-axis
            plot_widget.setLabel('bottom', 'Time', color='white')
            plot_widget.setLabel('left', col, color='white')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)
            plot_widget.setMouseEnabled(x=True, y=False)
            plot_widget.setYRange(y_range[0], y_range[1], padding=0)
            axis = pg.DateAxisItem(orientation='bottom')
            axis.setTextPen('w')  # White text for time axis
            plot_widget.setAxisItems({'bottom': axis})
            self.plot_layout.addWidget(plot_widget)
            self.plot_widgets[col] = plot_widget
            self.view_boxes[col] = plot_widget.getViewBox()

            if i > 0:
                self.view_boxes[col].setXLink(self.view_boxes[columns[0]])

            cursor_pen = pg.mkPen(color='g', width=3)  # Толще и белее
            cursor = CustomInfiniteLine(pos=0, angle=90, pen=cursor_pen, movable=True, hoverPen=cursor_pen)

            cursor.setZValue(10)
            plot_widget.addItem(cursor)
            self.cursors[col] = cursor
            cursor.sigPositionChanged.connect(self.update_values)
            self.view_boxes[col].sigRangeChanged.connect(
                lambda vb, ranges, changed, col=col: self.adjust_cursor_sensitivity(col, ranges))

        # Add button to right panel
        self.open_button = QPushButton("Load CSV File")
        self.open_button.clicked.connect(self.open_csv)
        self.right_layout.addWidget(self.open_button)

        # Add value display to right panel
        self.value_display = QTextEdit()
        self.value_display.setReadOnly(True)
        self.right_layout.addWidget(self.value_display)

        # Data initialization
        self.data = pd.DataFrame()
        self.time_seconds = []
        self.load_default_data()


        # Synchronize all cursors on any movement
        for col in columns:
            self.cursors[col].sigPositionChanged.connect(self.make_cursor_sync_function(col))

    def adjust_cursor_sensitivity(self, col, ranges):
        x_range = ranges[0][1] - ranges[0][0]
        sensitivity = x_range / 100
        self.cursors[col].setBounds([min(self.time_seconds, default=0), max(self.time_seconds, default=0)])
        if sensitivity > 0:
            self.cursors[col].setPen({'color': '#8e2dc5', 'width': max(1, sensitivity / 1000)})

    def sync_cursors(self, line, source_col):
        pos = line.value()
        columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
        for col in columns:
            if col != source_col:
                self.cursors[col].setValue(pos)

    def update_values(self):
        if not self.data.empty and self.time_seconds:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.time_seconds) - cursor_pos))

            try:
                timestamp = pd.to_datetime(self.data['timestamp'].iloc[idx], unit='ms', errors='coerce')
                date_time = timestamp.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(timestamp) else "Invalid"
            except:
                date_time = "Invalid"

            display_text = f"<span style='color:#8e2dc5; font-weight:bold;'>Date/Time:</span> {date_time}<br><br>"
            columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']

            for col in columns:
                try:
                    value = self.data[col].iloc[idx]
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>{value:.2f}</span><br>"
                except:
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>N/A</span><br>"

            self.value_display.setHtml(display_text)

    def load_default_data(self):
        data_str = """timestamp,U_A_rms,U_B_rms,U_C_rms,I_A_rms,I_B_rms,I_C_rms
1746997783772,234.9,236.0,236.5,17.0,14.9,2.8
1746998645662,234.5,236.6,,16.1,14.8,3.5
1747000384802,235.1,236.1,236.3,18.1,,12.7
1747001246702,235.0,236.1,236.6,17.5,14.4,
1747002108572,235.7,235.6,236.6,17.5,15.0,3.2
1747003847732,,235.0,236.1,17.6,14.6,2.4
1747004709632,234.8,235.2,236.1,16.7,15.0,2.4
1747005571502,235.0,234.2,236.0,17.2,15.1,2.4
1747010000000,235.5,235.8,236.2,17.0,15.2,2.5
1747020000000,236.0,236.5,237.0,17.5,15.5,3.0
"""
        try:
            self.data = pd.read_csv(StringIO(data_str), skipinitialspace=True)
            self.plot_data()
        except Exception as e:
            print(f"Error loading default data: {e}")

    def open_csv(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open CSV File", "", "CSV Files (*.csv)")
        if file_name:
            try:
                self.data = pd.read_csv(file_name, skipinitialspace=True)
                required_columns = ['timestamp', 'U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
                if not all(col in self.data.columns for col in required_columns):
                    print("Error: CSV file must contain columns: " + ", ".join(required_columns))
                    return
                self.plot_data()
            except Exception as e:
                print(f"Error loading CSV file: {e}")

    def plot_data(self):
        # Clear all plots
        for plot_widget in self.plot_widgets.values():
            plot_widget.clear()
            for col, cursor in self.cursors.items():
                if plot_widget == self.plot_widgets[col]:
                    plot_widget.addItem(cursor)

        # Convert timestamps and find gaps >15 minutes
        try:
            timestamps = pd.to_datetime(self.data['timestamp'], unit='ms', errors='coerce')
            self.time_seconds = [t.timestamp() for t in timestamps if pd.notnull(t)]

            if len(self.time_seconds) > 1:
                time_diffs = np.diff(self.time_seconds)
                large_gaps = np.where(time_diffs > 900)[0]
            else:
                large_gaps = []
        except:
            self.time_seconds = []
            large_gaps = []
            print("Error processing timestamps")
            return

        # Plot each column
        columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']

        for col in columns:
            if col not in self.data.columns:
                continue

            plot_widget = self.plot_widgets[col]
            values = pd.to_numeric(self.data[col], errors='coerce')

            # Create mask for valid data
            valid_mask = ~np.isnan(values) & ~np.isnan(timestamps)

            # Add yellow background for large gaps (>15 minutes)
            self.add_large_gap_regions(plot_widget, self.time_seconds, large_gaps)

            # Add yellow background for missing data points
            self.add_missing_data_regions(plot_widget, timestamps, valid_mask)

            # Convert to numpy arrays for plotting
            x = np.array(self.time_seconds)
            y = np.array(values)

            # Only plot if we have valid data
            if np.any(valid_mask):
                # Plot valid segments separately - only lines, no points
                valid_indices = np.where(valid_mask)[0]
                segments = np.split(valid_indices, np.where(np.diff(valid_indices) > 1)[0] + 1)

                for seg in segments:
                    if len(seg) > 0:
                        plot_widget.plot(x[seg], y[seg], pen=pg.mkPen('r', width=2), name=col)


        # Update cursors
        for col in columns:
            if self.time_seconds:
                self.cursors[col].setValue(self.time_seconds[0])
                self.adjust_cursor_sensitivity(col, ([self.time_seconds[0], self.time_seconds[-1]], [0, 300]))

        self.update_values()

    def add_large_gap_regions(self, plot_widget, time_seconds, large_gaps):
        """Add yellow background regions for gaps >15 minutes"""
        for gap_idx in large_gaps:
            start_time = time_seconds[gap_idx]
            end_time = time_seconds[gap_idx + 1]
            region = pg.LinearRegionItem(values=[start_time, end_time], movable=False)
            region.setBrush(QColor(255, 255, 0, 255))
            region.setZValue(-10)
            plot_widget.addItem(region)

    def add_missing_data_regions(self, plot_widget, timestamps, valid_mask):
        """Add yellow background regions where individual data points are missing"""
        if len(timestamps) < 2:
            return

        time_sec = np.array([t.timestamp() if pd.notnull(t) else np.nan for t in timestamps])
        missing_starts = []
        missing_ends = []

        current_state = valid_mask[0] if len(valid_mask) > 0 else True
        start_idx = 0

        for i in range(1, len(valid_mask)):
            if valid_mask[i] != current_state:
                if current_state:  # Transition from valid to missing
                    missing_starts.append(time_sec[i])
                else:  # Transition from missing to valid
                    missing_ends.append(time_sec[i])
                current_state = valid_mask[i]

        if not current_state and len(missing_starts) > len(missing_ends):
            missing_ends.append(time_sec[-1])

        for start, end in zip(missing_starts, missing_ends):
            if not np.isnan(start) and not np.isnan(end) and (end - start) <= 900:
                region = pg.LinearRegionItem(values=[start, end], movable=False)
                region.setBrush(QColor(255, 255, 0, 255))
                region.setZValue(-10)
                plot_widget.addItem(region)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    set_dark_theme(app)  # Apply dark theme
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
