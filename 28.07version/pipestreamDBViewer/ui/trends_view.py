from PyQt6.QtWidgets import QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QMessageBox, QTextEdit, QApplication, QToolButton
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
from Lib import pipestreamdbread as pdb
import logging

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(pd.DataFrame)
    error_occurred = pyqtSignal(str)

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

            data_list = []
            for record in records:
                record_dict = dict(zip(required_columns, record))
                rec = pdb.LogRecord(record_dict)
                signals = rec.get_signals()
                if len(signals) == 0:
                    continue
                rms_values = (np.max(signals, axis=0) - np.min(signals, axis=0)) / 2
                record_data = {'timestamp': record_dict['timestamp']}
                for i, col in enumerate(['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']):
                    record_data[col] = rms_values[i] if i < len(rms_values) else np.nan
                data_list.append(record_data)

            self.data_loaded.emit(pd.DataFrame(data_list))
        except Exception as e:
            self.error_occurred.emit(f"Ошибка при загрузке данных: {str(e)}")

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
        self.main_layout = QHBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

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

        self.main_layout.addWidget(self.left_panel)
        self.main_layout.addWidget(self.right_panel)

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
        self.valid_data_indices = []  # Для синхронизации индексов данных
        self.current_device = None
        self.data_loader = None

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
            cursor_pos = self.cursors['U_A_rms'].value()  # Позиция курсора в секундах (Unix timestamp)

            # Находим ближайший индекс в time_labels
            idx = np.argmin(np.abs(np.array(self.time_labels) - cursor_pos))

            # Получаем индекс в данных, соответствующий time_labels
            data_idx = self.valid_data_indices[idx]

            try:
                from datetime import datetime

                timestamp_ms = self.data['timestamp'].iloc[data_idx]
                timestamp_sec = timestamp_ms / 1000  # переводим в секунды
                date_time = datetime.fromtimestamp(timestamp_sec).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # точность до миллисекунд

            except Exception as e:
                date_time = f"Error: {str(e)}"
                logging.error(f"Ошибка обработки временной метки: {str(e)}")

            # Формируем текст для отображения
            display_text = f"<span style='color:#8e2dc5; font-weight:700;'>Date/Time:</span> {date_time}<br><br>"
            for col in self.columns:
                try:
                    value = self.data[col].iloc[data_idx]
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>{value:.2f}</span><br>"
                except Exception as e:
                    display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>N/A</span><br>"
                    logging.error(f"Ошибка получения значения для {col}: {str(e)}")

            self.value_display.setHtml(display_text)

    def fetch_logger_data(self, table_name: str):
        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
        self.data_loader = DataLoaderThread(table_name, self)
        self.data_loader.data_loaded.connect(self.on_data_loaded)
        self.data_loader.error_occurred.connect(self.on_error_occurred)
        self.data_loader.start()

    def on_data_loaded(self, data):
        self.data = data
        logging.info(f"Первые 5 временных меток: {self.data['timestamp'].head().tolist()}")
        self.plot_data()
        self.data_loader = None

    def on_error_occurred(self, error_msg):
        self.parent.status_bar.showMessage(error_msg, 5000)
        logging.error(error_msg)
        self.data_loader = None

    def plot_data_from_signal(self, table_name: str, colname_list: list, in_data: dict, rec_num: int):
        if len(table_name) < 1:
            self.parent.status_bar.showMessage("Ошибка: Не указано имя таблицы", 5000)
            return
        self.current_device = table_name
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

    def plot_data(self):
        for plot_widget in self.plot_widgets.values():
            plot_widget.clear()
            for col, cursor in self.cursors.items():
                if plot_widget == self.plot_widgets[col]:
                    plot_widget.addItem(cursor)

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

        for col in self.columns:
            if col not in self.data.columns:
                continue

            plot_widget = self.plot_widgets[col]
            values = pd.to_numeric(self.data[col], errors='coerce')
            valid_mask = ~np.isnan(values) & ~np.isnan(timestamps)

            self.add_gray_gap_regions(plot_widget, self.time_labels, self.gap_indices)
            self.add_missing_data_regions(plot_widget, timestamps, valid_mask)

            x = np.array(self.time_labels)
            y = np.array(values)[valid_indices]
            valid_mask = valid_mask[valid_indices]
            valid_indices_segment = np.where(valid_mask)[0]
            valid_times = x[valid_indices_segment]

            time_diffs_valid = np.diff(valid_times)
            segment_split_indices = np.where(time_diffs_valid > 900)[0] + 1
            segments = np.split(valid_indices_segment, segment_split_indices)

            for seg in segments:
                if len(seg) > 1:
                    x_seg = x[seg]
                    y_seg = y[seg]
                    plot_widget.plot(x_seg, y_seg, pen={'color': '#FF0000', 'width': 2}, name=col)

        for col in self.columns:
            if self.time_labels:
                self.cursors[col].setValue(self.time_labels[0])
                self.adjust_cursor_sensitivity(col, ([self.time_labels[0], self.time_labels[-1]], [0, 300]))
        self.update_values()

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