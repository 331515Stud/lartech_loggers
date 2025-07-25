from PyQt6.QtWidgets import QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QMessageBox, QTextEdit, QApplication, QToolButton
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QIcon, QCursor, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
from Lib import pipestreamdbread as pdb
import logging

class CustomInfiniteLine(pg.InfiniteLine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseHover(True)
        self.is_dragged = False

    def mouseDragEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if ev.isStart():
                self.is_dragged = True
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif ev.isFinish():
                self.is_dragged = False
                QApplication.restoreOverrideCursor()
            super().mouseDragEvent(ev)

    def hoverEvent(self, ev):
        if not self.is_dragged and self.movable and ev.isEnter():
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif ev.isExit():
            QApplication.restoreOverrideCursor()

class TrendsSubwindow(QMdiSubWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Тренды")
        self.setMinimumWidth(100)

        # Main widget and layout
        self.main_widget = QWidget()
        self.setWidget(self.main_widget)
        self.main_layout = QHBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Left panel (plots)
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(300)
        self.plot_layout = QVBoxLayout()
        self.left_panel.setLayout(self.plot_layout)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(5)

        # Right panel (controls and values)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.right_panel.setMinimumWidth(200)
        self.right_panel.setMaximumWidth(300)
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
        self.columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
        y_range = [0, 300]

        for i, col in enumerate(self.columns):
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground('k')
            plot_widget.getAxis('left').setTextPen('w')
            plot_widget.getAxis('bottom').setTextPen('w')
            plot_widget.setLabel('bottom', 'Time', color='white')
            plot_widget.setLabel('left', col, color='white')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)
            plot_widget.setMouseEnabled(x=True, y=False)
            plot_widget.setYRange(y_range[0], y_range[1], padding=0)
            axis = pg.DateAxisItem(orientation='bottom')
            axis.setTextPen('w')
            plot_widget.setAxisItems({'bottom': axis})
            self.plot_layout.addWidget(plot_widget)
            self.plot_widgets[col] = plot_widget
            self.view_boxes[col] = plot_widget.getViewBox()

            if i > 0:
                self.view_boxes[col].setXLink(self.view_boxes[self.columns[0]])

            cursor_pen = pg.mkPen(color='g', width=3)
            cursor = CustomInfiniteLine(pos=0, angle=90, pen=cursor_pen, movable=True, hoverPen=cursor_pen)
            cursor.setZValue(10)
            plot_widget.addItem(cursor)
            self.cursors[col] = cursor
            cursor.sigPositionChanged.connect(self.make_cursor_sync_function(col))

        # Add value display to right panel
        self.value_display = QTextEdit()
        self.value_display.setReadOnly(True)
        self.right_layout.addWidget(self.value_display)

        # Add button to send cursor timestamp to SignalsView
        self.send_timestamp_button = QToolButton()
        self.send_timestamp_button.setText("→ Сигналы")
        self.send_timestamp_button.setToolTip("Передать время курсора в окно сигналов")
        self.send_timestamp_button.setIcon(QIcon("./icons/send.png"))  # Ensure this icon exists
        self.send_timestamp_button.clicked.connect(self.send_timestamp_to_signals)
        self.right_layout.addWidget(self.send_timestamp_button)

        # Data initialization
        self.data = pd.DataFrame()
        self.time_labels = []
        self.current_device = None

        # Apply styles
        self.set_style()

    def set_style(self):
        self.setStyleSheet("""
            QTextEdit {
                background-color: #353535;
                border: 1px solid #353535;
                color: white;
            }
            QToolButton {
                background-color: #8e2dc5;
                color: white;
                border: 2px solid #ffffff;
                border-radius: 8px;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #a13de5;
            }
            QToolButton:pressed {
                background-color: #6e1da5;
            }
        """)

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

    def adjust_cursor_sensitivity(self, col, ranges):
        x_range = ranges[0][1] - ranges[0][0]
        sensitivity = x_range / 100
        self.cursors[col].setBounds([min(self.time_labels, default=0), max(self.time_labels, default=0)])
        if sensitivity > 0:
            self.cursors[col].setPen({'color': '#8e2dc5', 'width': max(1, sensitivity / 1000)})

    def update_values(self):
        if not self.data.empty and self.time_labels:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.time_labels) - cursor_pos))
            try:
                timestamp = pd.to_datetime(self.data['timestamp'].iloc[idx], unit='ms', errors='coerce')
                date_time = timestamp.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(timestamp) else "Invalid"
            except:
                date_time = "Invalid"
            display_text = f"<span style='color:#8e2dc5; font-weight:700;'>Date/Time:</span> {date_time}<br><br>"
            for col in self.columns:
                try:
                    value = self.data[col].iloc[idx]
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>{value:.2f}</span><br>"
                except:
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>N/A</span><br>"
            self.value_display.setHtml(display_text)

    def fetch_logger_data(self, table_name: str):
        """
        Fetch all records from the specified logger table and compute RMS values for each record.
        """
        try:
            connection, cursor, status = pdb.connect_db(pdb.db_connection_params)
            if connection == 0 or cursor == 0:
                self.parent.status_bar.showMessage(f"Ошибка подключения к БД: {status}", 5000)
                logging.error(f"Ошибка подключения к БД: {status}")
                return

            # Get column names
            colnames_list = pdb.get_column_names(cursor, table_name)
            required_columns = ['timestamp', 'points', 'mask', 'npoints', 'cfg_voltage_multiplier',
                              'cfg_voltage_divider', 'cfg_current_multiplier', 'cfg_current_divider']
            if not all(col in colnames_list for col in required_columns):
                self.parent.status_bar.showMessage(
                    f"Ошибка: Таблица {table_name} не содержит всех необходимых столбцов: {', '.join(required_columns)}",
                    5000
                )
                cursor.close()
                connection.close()
                return

            # Fetch all records
            query = f"SELECT {', '.join(required_columns)} FROM {table_name} ORDER BY timestamp ASC"
            cursor.execute(query)
            records = cursor.fetchall()
            cursor.close()
            connection.close()

            if not records:
                self.parent.status_bar.showMessage(f"Нет данных в таблице {table_name}", 5000)
                return

            # Process records to compute RMS values
            data_list = []
            for record in records:
                record_dict = dict(zip(required_columns, record))
                rec = pdb.LogRecord(record_dict)
                signals = rec.get_signals()
                if len(signals) == 0:
                    continue  # Skip invalid records
                rms_values = np.sqrt(np.mean(signals**2, axis=0))  # Compute RMS for each channel
                record_data = {'timestamp': record_dict['timestamp']}
                for i, col in enumerate(self.columns):
                    record_data[col] = rms_values[i] if i < len(rms_values) else np.nan
                data_list.append(record_data)

            # Create DataFrame
            self.data = pd.DataFrame(data_list)
            self.plot_data()

        except Exception as e:
            self.parent.status_bar.showMessage(f"Ошибка при загрузке данных: {str(e)}", 5000)
            logging.error(f"Ошибка при загрузке данных: {str(e)}")

    def plot_data_from_signal(self, table_name: str, colname_list: list, in_data: dict, rec_num: int):
        """
        Handle the signal emitted when a logger is selected and fetch RMS data.
        """
        if len(table_name) < 1:
            self.parent.status_bar.showMessage("Ошибка: Не указано имя таблицы", 5000)
            return

        self.current_device = table_name
        self.fetch_logger_data(table_name)

    def plot_data(self):
        """
        Plot the RMS data stored in self.data.
        """
        for plot_widget in self.plot_widgets.values():
            plot_widget.clear()
            for col, cursor in self.cursors.items():
                if plot_widget == self.plot_widgets[col]:
                    plot_widget.addItem(cursor)

        try:
            timestamps = pd.to_datetime(self.data['timestamp'], unit='ms', errors='coerce')
            self.time_labels = [t.timestamp() for t in timestamps if pd.notna(t)]
            if len(self.time_labels) > 1:
                time_diffs = np.diff(self.time_labels)
                large_gaps = np.where(time_diffs > 900)[0]
            else:
                large_gaps = []
        except:
            self.time_labels = []
            large_gaps = []
            self.parent.status_bar.showMessage("Ошибка обработки временных меток", 5000)
            return

        for col in self.columns:
            if col not in self.data.columns:
                continue
            plot_widget = self.plot_widgets[col]
            values = pd.to_numeric(self.data[col], errors='coerce')
            valid_mask = ~np.isnan(values) & ~np.isnan(timestamps)
            self.add_large_gap_regions(plot_widget, self.time_labels, large_gaps)
            self.add_missing_data_regions(plot_widget, timestamps, valid_mask)
            x = np.array(self.time_labels)
            y = np.array(values)
            if np.any(valid_mask):
                valid_indices = np.where(np.array(valid_mask))[0]
                segments = np.split(valid_indices, np.where(np.diff(valid_indices) > 1)[0] + 1)
                for seg in segments:
                    if len(seg) > 0:
                        plot_widget.plot(x[seg], y[seg], pen={'color': '#FF0000', 'width': 2}, name=col)

        for col in self.columns:
            if self.time_labels:
                self.cursors[col].setValue(self.time_labels[0])
                self.adjust_cursor_sensitivity(col, ([self.time_labels[0], self.time_labels[-1]], [0, 300]))
        self.update_values()

    def add_large_gap_regions(self, plot_widget, time_labels, large_gaps):
        for gap_idx in large_gaps:
            start_time = time_labels[gap_idx]
            end_time = time_labels[gap_idx + 1]
            region = pg.LinearRegionItem(values=[start_time, end_time], movable=False)
            region.setBrush(QColor(255, 255, 0, 100))
            region.setZValue(-10)
            plot_widget.addItem(region)

    def add_missing_data_regions(self, plot_widget, timestamps, valid_mask):
        if len(timestamps) < 2:
            return
        time_sec = np.array([t.timestamp() if pd.notna(t) else np.nan for t in timestamps])
        missing_starts = []
        missing_ends = []
        current_state = valid_mask[0] if len(valid_mask) > 0 else True
        for i in range(1, len(valid_mask)):
            if valid_mask[i] != current_state:
                if current_state:
                    missing_starts.append(time_sec[i])
                else:
                    missing_ends.append(time_sec[i])
                current_state = valid_mask[i]
        if not current_state and len(missing_starts) > len(missing_ends):
            missing_ends.append(time_sec[-1])
        for start, end in zip(missing_starts, missing_ends):
            if not np.isnan(start) and not np.isnan(end) and (end - start) <= 900:
                region = pg.LinearRegionItem(values=[start, end], movable=False)
                region.setBrush(QColor(255, 255, 0, 100))
                region.setZValue(-10)
                plot_widget.addItem(region)

    def send_timestamp_to_signals(self):
        """
        Send the timestamp at the cursor position to the SignalsView window.
        """
        if not self.data.empty and self.time_labels and self.parent.SignalsView_subwindow:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.time_labels) - cursor_pos))
            if 0 <= idx < len(self.data):
                timestamp = self.data['timestamp'].iloc[idx]
                # Assuming SignalsView_subwindow has a method to handle the timestamp
                self.parent.SignalsView_subwindow.set_timestamp_from_trends(timestamp)
                self.parent.status_bar.showMessage(f"Время {timestamp} передано в окно сигналов", 5000)

    def moveEvent(self, event):
        """
        Перемещение окна не вызывает пересчет компоновки, чтобы избежать рекурсии.
        """
        super().moveEvent(event)

    def resizeEvent(self, event):
        """
        Notify parent to adjust layout when this window is resized.
        """
        super().resizeEvent(event)
        if self.parent and not self.parent._resizing:
            self.parent.tile_subwindows(resized_window=self)