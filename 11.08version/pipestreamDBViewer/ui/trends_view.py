from PyQt6.QtWidgets import QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QMessageBox, QTextEdit, QApplication, QToolButton, QToolBar, QProgressBar, QLabel
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QCursor, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
from Lib import pipestreamdbread as pdb
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(list, list)  # Передаем records и required_columns
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, table_name, parent=None):
        super().__init__(parent)
        self.table_name = table_name

    def run(self):
        try:
            connection, cursor, status = pdb.connect_db(pdb.db_connection_params)
            if connection == 0 or cursor == 0:
                self.error_occurred.emit(f"Ошибка подключения к БД: {status}")
                return

            colnames_list = pdb.get_column_names(cursor, self.table_name)
            required_columns = ['timestamp', 'points', 'mask', 'npoints', 'cfg_voltage_multiplier',
                             'cfg_voltage_divider', 'cfg_current_multiplier', 'cfg_current_divider']
            if not all(col in colnames_list for col in required_columns):
                self.error_occurred.emit(f"Ошибка: Таблица {self.table_name} не содержит всех необходимых столбцов")
                cursor.close()
                connection.close()
                return

            query = f"SELECT {', '.join(required_columns)} FROM {self.table_name} ORDER BY timestamp ASC"
            cursor.execute(query)
            records = cursor.fetchall()
            cursor.close()
            connection.close()

            if not records:
                self.error_occurred.emit(f"Нет данных в таблице {self.table_name}")
                return

            total_records = len(records)
            for i in range(total_records):
                self.progress_updated.emit(int((i + 1) / total_records * 100))

            self.data_loaded.emit(records, required_columns)
        except Exception as e:
            self.error_occurred.emit(f"Ошибка при загрузке данных: {str(e)}")

class RMSCalculationThread(QThread):
    rms_calculated = pyqtSignal(pd.DataFrame)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, records, required_columns, parent=None):
        super().__init__(parent)
        self.records = records
        self.required_columns = required_columns

    def run(self):
        try:
            data_list = []
            total_records = len(self.records)
            for i, record in enumerate(self.records):
                record_dict = dict(zip(self.required_columns, record))
                rec = pdb.LogRecord(record_dict)
                signals = rec.get_signals()
                if len(signals) == 0:
                    continue
                rms_values = (np.max(signals, axis=0) - np.min(signals, axis=0)) / 2
                record_data = {'timestamp': record_dict['timestamp']}
                for j, col in enumerate(['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']):
                    record_data[col] = rms_values[j] if j < len(rms_values) else np.nan
                data_list.append(record_data)
                self.progress_updated.emit(int((i + 1) / total_records * 100))

            self.rms_calculated.emit(pd.DataFrame(data_list))
        except Exception as e:
            self.error_occurred.emit(f"Ошибка при расчете СКЗ: {str(e)}")

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

        self.main_widget = QWidget()
        self.setWidget(self.main_widget)
        self.main_layout = QVBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        self.toolbar = QToolBar('Trends Controls')
        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                spacing: 5px;
            }
            QToolBar::separator {
                width: 1px;
                background-color: #ccc;
                margin-left: 5px;
                margin-right: 5px;
            }
            QToolBar::item {
                margin: 2px;
                padding: 5px;
            }
        """)
        self.main_layout.addWidget(self.toolbar)

        self.status_label = QLabel("Нет данных")
        self.toolbar.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.toolbar.addWidget(self.progress_bar)

        self.center_cursor_button = QToolButton()
        self.center_cursor_button.setText("Центр курсора")
        self.center_cursor_button.setToolTip("Установить курсор в середину периода")
        self.center_cursor_button.clicked.connect(self.center_cursor)
        self.toolbar.addWidget(self.center_cursor_button)

        self.view_now_button = QToolButton()
        self.view_now_button.setText("К курсору")
        self.view_now_button.setToolTip("Показать область вокруг курсора")
        self.view_now_button.clicked.connect(self.view_now)
        self.toolbar.addWidget(self.view_now_button)

        self.content_layout = QHBoxLayout()
        self.main_layout.addLayout(self.content_layout)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(300)
        self.plot_layout = QVBoxLayout()
        self.left_panel.setLayout(self.plot_layout)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(5)

        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.right_panel.setMinimumWidth(200)
        self.right_panel.setMaximumWidth(300)
        self.right_layout = QVBoxLayout()
        self.right_panel.setLayout(self.right_layout)
        self.right_layout.setContentsMargins(5, 5, 5, 5)
        self.right_layout.setSpacing(10)

        self.content_layout.addWidget(self.left_panel)
        self.content_layout.addWidget(self.right_panel)

        self.plot_widgets = {}
        self.view_boxes = {}
        self.cursors = {}
        self.columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']

        for i, col in enumerate(self.columns):
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground('k')
            plot_widget.getAxis('left').setTextPen('w')
            plot_widget.getAxis('bottom').setTextPen('w')
            plot_widget.setLabel('bottom', 'Time', color='white')
            plot_widget.setLabel('left', col, color='white')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)
            plot_widget.setMouseEnabled(x=True, y=False)
            y_range = [0, 300] if i < 3 else [0, 100]
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

        self.value_display = QTextEdit()
        self.value_display.setReadOnly(True)
        self.right_layout.addWidget(self.value_display)

        self.send_timestamp_button = QToolButton()
        self.send_timestamp_button.setText("→ Сигналы")
        self.send_timestamp_button.setToolTip("Передать время курсора в окно сигналов")
        self.send_timestamp_button.setIcon(QIcon("./icons/send.png"))
        self.send_timestamp_button.clicked.connect(self.send_timestamp_to_signals)
        self.right_layout.addWidget(self.send_timestamp_button)

        self.data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.current_device = None
        self.data_loader = None
        self.rms_calculator = None
        self.executor = ThreadPoolExecutor(max_workers=len(self.columns))
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self.plot_next_segment)
        self.current_segment_index = 0
        self.current_column = None
        self.plot_segments = {}
        self.plot_timestamps = []
        self.plot_valid_indices = []
        self.plot_time_labels = []
        self.plot_gap_indices = []

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
        if not self.data.empty and self.time_labels and self.valid_data_indices:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.time_labels) - cursor_pos))
            data_idx = self.valid_data_indices[idx]

            try:
                timestamp_ms = self.data['timestamp'].iloc[data_idx]
                timestamp_sec = timestamp_ms / 1000
                date_time = datetime.fromtimestamp(timestamp_sec).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            except Exception as e:
                date_time = f"Error: {str(e)}"
                logging.error(f"Ошибка обработки временной метки: {str(e)}")

            display_text = f"<span style='color:#8e2dc5; font-weight:700;'>Date/Time:</span> {date_time}<br><br>"
            for col in self.columns:
                try:
                    value = self.data[col].iloc[data_idx]
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>{value:.2f}</span><br>"
                except Exception as e:
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>N/A</span><br>"
                    logging.error(f"Ошибка получения значения для {col}: {str(e)}")

            self.value_display.setHtml(display_text)

    def clear_previous_data(self):
        """Clear all previous data and plots."""
        self.data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        for col in self.columns:
            if col in self.plot_widgets:
                plot_widget = self.plot_widgets[col]
                plot_widget.clear()
                plot_widget.addItem(self.cursors[col])
        self.value_display.setHtml("")
        self.status_label.setText("Очистка предыдущих данных...")
        QApplication.processEvents()

    def fetch_logger_data(self, table_name: str):
        if self.current_device != table_name:
            self.clear_previous_data()
            time.sleep(0.1)  # Brief delay to ensure user sees the cleared state
            self.status_label.setText(f"Загрузка данных для {table_name}...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
        if self.rms_calculator and self.rms_calculator.isRunning():
            self.rms_calculator.terminate()

        self.current_device = table_name
        self.data_loader = DataLoaderThread(table_name, self)
        self.data_loader.data_loaded.connect(self.on_raw_data_loaded)
        self.data_loader.error_occurred.connect(self.on_error_occurred)
        self.data_loader.progress_updated.connect(self.update_progress)
        self.data_loader.start()

    def on_raw_data_loaded(self, records, required_columns):
        self.data_loader = None
        self.status_label.setText(f"Рассчет СКЗ для {self.current_device}...")
        self.progress_bar.setValue(0)
        self.rms_calculator = RMSCalculationThread(records, required_columns, self)
        self.rms_calculator.rms_calculated.connect(self.on_rms_calculated)
        self.rms_calculator.error_occurred.connect(self.on_error_occurred)
        self.rms_calculator.progress_updated.connect(self.update_progress)
        self.rms_calculator.start()

    def on_rms_calculated(self, data):
        self.data = data
        logging.info(f"Первые 5 временных меток: {self.data['timestamp'].head().tolist()}")
        self.plot_data()
        self.rms_calculator = None
        self.status_label.setText(f"Данные загружены для {self.current_device} ({len(self.data)} записей)")

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if value == 100:
            self.progress_bar.setVisible(False)

    def on_error_occurred(self, error_msg):
        self.parent.status_bar.showMessage(error_msg, 5000)
        self.status_label.setText("Ошибка загрузки данных")
        self.progress_bar.setVisible(False)
        logging.error(error_msg)
        self.data_loader = None
        self.rms_calculator = None

    def plot_data_from_signal(self, table_name: str, colname_list: list, in_data: dict, rec_num: int):
        if len(table_name) < 1:
            self.parent.status_bar.showMessage("Ошибка: Не указано имя таблицы", 5000)
            return
        self.fetch_logger_data(table_name)

    def add_gray_gap_regions(self, plot_widget, time_labels, gap_indices):
        for idx in gap_indices:
            if idx + 1 < len(time_labels):
                start = time_labels[idx]
                end = time_labels[idx + 1]
                region = pg.LinearRegionItem(values=[start, end], movable=False)
                region.setBrush(QColor(128, 128, 128, 100))
                region.setZValue(-20)
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

    def plot_column(self, col, timestamps, valid_indices, time_labels, gap_indices):
        plot_widget = self.plot_widgets[col]
        plot_widget.clear()
        plot_widget.addItem(self.cursors[col])

        values = pd.to_numeric(self.data[col], errors='coerce')
        valid_mask = ~np.isnan(values) & ~np.isnan(timestamps)

        self.add_gray_gap_regions(plot_widget, time_labels, gap_indices)
        self.add_missing_data_regions(plot_widget, timestamps, valid_mask)

        x = np.array(time_labels)
        y = np.array(values)[valid_indices]
        valid_mask = valid_mask[valid_indices]
        valid_indices_segment = np.where(valid_mask)[0]
        valid_times = x[valid_indices_segment]

        time_diffs_valid = np.diff(valid_times)
        segment_split_indices = np.where(time_diffs_valid > 900)[0] + 1
        segments = np.split(valid_indices_segment, segment_split_indices)

        return col, segments, x, y

    def plot_next_segment(self):
        segments, x, y = self.plot_segments[self.current_column]
        if self.current_segment_index >= len(segments):
            self.current_segment_index = 0
            col_index = self.columns.index(self.current_column)
            col_index = (col_index + 1) % len(self.columns)
            self.current_column = self.columns[col_index]
            if self.current_column == self.columns[0]:
                self.plot_timer.stop()
                for col in self.columns:
                    if self.plot_time_labels:
                        self.cursors[col].setValue(self.plot_time_labels[0])
                        self.adjust_cursor_sensitivity(col, ([self.plot_time_labels[0], self.plot_time_labels[-1]],
                                                             [0, 300]))
                self.update_values()
                return
            segments, x, y = self.plot_segments[self.current_column]

        seg = segments[self.current_segment_index]
        if len(seg) > 1:
            x_seg = x[seg]
            y_seg = y[seg]
            self.plot_widgets[self.current_column].plot(x_seg, y_seg, pen={'color': '#FF0000', 'width': 2}, name=self.current_column)
            QApplication.processEvents()  # Ensure the UI updates

        self.current_segment_index += 1

    def plot_data(self):
        try:
            timestamps = pd.to_datetime(self.data['timestamp'], unit='ms', errors='coerce')
            valid_indices = [i for i, t in enumerate(timestamps) if pd.notna(t)]
            self.time_labels = [timestamps[i].timestamp() for i in valid_indices]
            self.valid_data_indices = valid_indices
            if len(self.time_labels) > 1:
                time_diffs = np.diff(self.time_labels)
                self.gap_indices = np.where(time_diffs > 900)[0]
            else:
                self.gap_indices = []
        except Exception as e:
            self.time_labels = []
            self.gap_indices = []
            self.valid_data_indices = []
            self.parent.status_bar.showMessage(f"Ошибка обработки временных меток: {str(e)}", 5000)
            logging.error(f"Ошибка обработки временных меток: {str(e)}")
            return

        self.plot_segments = {}
        self.plot_timestamps = timestamps
        self.plot_valid_indices = valid_indices
        self.plot_time_labels = self.time_labels
        self.plot_gap_indices = self.gap_indices
        self.current_segment_index = 0
        self.current_column = self.columns[0]

        futures = []
        for col in self.columns:
            if col in self.data.columns:
                future = self.executor.submit(self.plot_column, col, timestamps, valid_indices, self.time_labels, self.gap_indices)
                futures.append(future)

        for future in as_completed(futures):
            try:
                col, segments, x, y = future.result()
                self.plot_segments[col] = (segments, x, y)
            except Exception as e:
                self.parent.status_bar.showMessage(f"Ошибка построения графика: {str(e)}", 5000)
                logging.error(f"Ошибка построения графика: {str(e)}")

        self.plot_timer.start(100)  # Plot each segment with a 100ms delay

    def center_cursor(self):
        if self.time_labels:
            mid_time = (min(self.time_labels) + max(self.time_labels)) / 2
            for col, cursor in self.cursors.items():
                cursor.setValue(mid_time)
            self.update_values()

    def view_now(self):
        if self.time_labels:
            cursor_pos = self.cursors['U_A_rms'].value()
            for col in self.columns:
                self.view_boxes[col].setXRange(cursor_pos - 3600, cursor_pos + 3600)

    def send_timestamp_to_signals(self):
        if not self.data.empty and self.time_labels and self.parent.SignalsView_subwindow:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.time_labels) - cursor_pos))
            if 0 <= idx < len(self.valid_data_indices):
                data_idx = self.valid_data_indices[idx]
                timestamp = self.data['timestamp'].iloc[data_idx]
                self.parent.SignalsView_subwindow.set_timestamp_from_trends(timestamp)
                self.parent.status_bar.showMessage(f"Время {timestamp} передано в окно сигналов", 5000)

    def moveEvent(self, event):
        super().moveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent and not self.parent._resizing:
            self.parent.tile_subwindows(resized_window=self)

    def closeEvent(self, event):
        self.executor.shutdown(wait=True)
        self.plot_timer.stop()
        super().closeEvent(event)