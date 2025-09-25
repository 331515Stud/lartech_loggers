from PyQt6.QtWidgets import QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QToolButton, QProgressBar, QLabel, QApplication, QSizePolicy
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QCursor, QPalette, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
from Lib import pipestreamdbread as pdb
import logging
from datetime import datetime
import warnings
import os


pg.setConfigOptions(antialias=True, background='k', foreground='w')
warnings.filterwarnings("ignore", category=UserWarning, module="pyqtgraph")

# Константы для преобразования ADC
ADC_full_scale_V = 0.93
ADC_raw_max = (1 << 21)

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

class DataLoaderThread(QThread):
    data_processed = pyqtSignal(pd.DataFrame)
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

            # Проверка наличия столбцов
            colnames_list = pdb.get_column_names(cursor, self.table_name)
            rms_colnames = ["timestamp", "add_data_0", "add_data_1", "add_data_2", "add_data_3", "add_data_4", "add_data_5"]
            multypliers_colnames = ["cfg_voltage_multiplier", "cfg_voltage_divider", "cfg_current_multiplier", "cfg_current_divider"]
            required_columns = rms_colnames + multypliers_colnames

            if not all(col in colnames_list for col in required_columns):
                self.error_occurred.emit(f"Ошибка: Таблица {self.table_name} не содержит всех необходимых столбцов")
                cursor.close()
                connection.close()
                return

            # Получение множителей
            multypliers_names = ["VoltMult", "VoltDiv", "CurrMult", "CurrDiv"]
            query_last = f"SELECT {', '.join(multypliers_colnames)} FROM {self.table_name} ORDER BY timestamp DESC LIMIT 1"
            cursor.execute(query_last)
            last_ans = cursor.fetchone()
            if not last_ans:
                self.error_occurred.emit("Не удалось получить множители из таблицы")
                cursor.close()
                connection.close()
                return
            mult_dict = dict(zip(multypliers_names, last_ans))

            # Проверка валидности множителей
            if any(v is None or v == 0 for v in [mult_dict["VoltDiv"], mult_dict["CurrDiv"]]):
                self.error_occurred.emit("Ошибка: Множители содержат None или нули")
                cursor.close()
                connection.close()
                return

            # Загрузка всех данных
            query = f"SELECT {', '.join(rms_colnames)} FROM {self.table_name} ORDER BY timestamp ASC"
            cursor.execute(query)
            records = cursor.fetchall()
            if not records:
                self.error_occurred.emit(f"Нет данных в таблице {self.table_name}")
                cursor.close()
                connection.close()
                return

            total_records = len(records)
            val_names = ["timestamp", "U_A_rms", "U_B_rms", "U_C_rms", "I_A_rms", "I_B_rms", "I_C_rms"]
            data_dict = dict(zip(val_names, zip(*records)))

            def get_voltage(adc_rms):
                if adc_rms is None:
                    return np.nan
                try:
                    return round(((mult_dict["VoltMult"] / mult_dict["VoltDiv"]) / (ADC_raw_max / ADC_full_scale_V)) * (adc_rms >> 2), 2)
                except (TypeError, ZeroDivisionError):
                    return np.nan

            def get_ampertage(adc_rms):
                if adc_rms is None:
                    return np.nan
                try:
                    return round(((mult_dict["CurrMult"] / mult_dict["CurrDiv"]) / (ADC_raw_max / ADC_full_scale_V)) * (adc_rms >> 2), 2)
                except (TypeError, ZeroDivisionError):
                    return np.nan

            # Преобразование данных
            data_list = []
            for i in range(total_records):
                row = {
                    'timestamp': data_dict['timestamp'][i],
                    'U_A_rms': get_voltage(data_dict['U_A_rms'][i]),
                    'U_B_rms': get_voltage(data_dict['U_B_rms'][i]),
                    'U_C_rms': get_voltage(data_dict['U_C_rms'][i]),
                    'I_A_rms': get_ampertage(data_dict['I_A_rms'][i]),
                    'I_B_rms': get_ampertage(data_dict['I_B_rms'][i]),
                    'I_C_rms': get_ampertage(data_dict['I_C_rms'][i])
                }
                data_list.append(row)

                if (i + 1) % 100 == 0 or (i + 1) == total_records:
                    progress = int((i + 1) / total_records * 100)
                    self.progress_updated.emit(progress)

            df = pd.DataFrame(data_list)
            self.data_processed.emit(df)
            cursor.close()
            connection.close()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка при загрузке и обработке данных: {str(e)}")

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

        # Контейнер для верхней части (кнопки, дата/время, прогресс)
        self.top_container = QWidget()
        self.top_layout = QHBoxLayout()
        self.top_container.setLayout(self.top_layout)
        self.top_layout.setContentsMargins(5, 5, 5, 5)
        self.top_layout.setSpacing(5)
        self.main_layout.addWidget(self.top_container)

        # Контейнер для кнопок навигации
        self.navigation_container = QWidget()
        self.navigation_layout = QHBoxLayout()
        self.navigation_container.setLayout(self.navigation_layout)
        self.navigation_layout.setContentsMargins(0, 0, 0, 0)
        self.navigation_layout.setSpacing(5)
        self.top_layout.addWidget(self.navigation_container)

        # Добавляем кнопки навигации
        self.go_to_cursor_button = QToolButton()
        self.go_to_cursor_button.setIcon(QIcon("./icons/center_cursor.png"))
        self.go_to_cursor_button.setIconSize(QSize(20, 20))
        self.go_to_cursor_button.setToolTip("Центрировать вид на текущем положении курсора")
        self.go_to_cursor_button.clicked.connect(self.center_on_cursor)
        self.navigation_layout.addWidget(self.go_to_cursor_button)

        self.center_cursor_button = QToolButton()
        self.center_cursor_button.setIcon(QIcon("./icons/custom_center_view.png"))
        self.center_cursor_button.setIconSize(QSize(20, 20))
        self.center_cursor_button.setToolTip("Переместить курсор в центр текущего видимого диапазона")
        self.center_cursor_button.clicked.connect(self.move_cursor_to_center)
        self.navigation_layout.addWidget(self.center_cursor_button)

        self.send_timestamp_button = QToolButton()
        self.send_timestamp_button.setIcon(QIcon("./icons/send_to_signals.png"))
        self.send_timestamp_button.setIconSize(QSize(20, 20))
        self.send_timestamp_button.setToolTip("Передать время курсора в окно сигналов")
        self.send_timestamp_button.clicked.connect(self.send_timestamp_to_signals)
        self.navigation_layout.addWidget(self.send_timestamp_button)

        self.lock_cursor_button = QToolButton()
        self.lock_cursor_button.setIcon(QIcon("./icons/lock_cursor_active.png"))
        self.lock_cursor_button.setIconSize(QSize(20, 20))
        self.lock_cursor_button.setToolTip("Фиксировать курсор в центре видимого диапазона")
        self.lock_cursor_button.setCheckable(True)
        self.lock_cursor_button.clicked.connect(self.toggle_lock_cursor_mode)
        self.navigation_layout.addWidget(self.lock_cursor_button)

        # Контейнер для даты/времени
        self.datetime_container = QWidget()
        self.datetime_layout = QHBoxLayout()
        self.datetime_container.setLayout(self.datetime_layout)
        self.datetime_layout.setContentsMargins(0, 0, 0, 0)
        self.datetime_layout.setSpacing(5)
        self.top_layout.addWidget(self.datetime_container)

        self.datetime_label = QLabel("Дата/время: -")
        self.datetime_label.setMinimumWidth(200)
        self.datetime_layout.addWidget(self.datetime_label)

        # Контейнер для прогресс-бара и процента
        self.progress_container = QWidget()
        self.progress_layout = QHBoxLayout()
        self.progress_container.setLayout(self.progress_layout)
        self.progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_layout.setSpacing(5)
        self.top_layout.addWidget(self.progress_container)

        self.status_label = QLabel("Нет данных")
        self.progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(150)
        self.progress_bar.setVisible(True)
        self.progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("0%")
        self.progress_label.setMinimumWidth(50)
        self.progress_layout.addWidget(self.progress_label)

        # Контейнер для значений U и I
        self.values_container = QWidget()
        self.values_layout = QHBoxLayout()
        self.values_container.setLayout(self.values_layout)
        self.values_layout.setContentsMargins(5, 5, 5, 5)
        self.values_layout.setSpacing(5)
        self.main_layout.addWidget(self.values_container)

        # Контейнер для напряжений
        self.voltage_container = QWidget()
        self.voltage_layout = QHBoxLayout()
        self.voltage_container.setLayout(self.voltage_layout)
        self.voltage_layout.setSpacing(5)
        self.voltage_layout.setContentsMargins(0, 0, 0, 0)
        self.values_layout.addWidget(self.voltage_container)

        # Метки для напряжений
        self.u_a_label = QLabel("U_A: -")
        self.u_a_label.setMinimumWidth(80)
        self.voltage_layout.addWidget(self.u_a_label)

        self.u_b_label = QLabel("U_B: -")
        self.u_b_label.setMinimumWidth(80)
        self.voltage_layout.addWidget(self.u_b_label)

        self.u_c_label = QLabel("U_C: -")
        self.u_c_label.setMinimumWidth(80)
        self.voltage_layout.addWidget(self.u_c_label)

        # Контейнер для токов
        self.current_container = QWidget()
        self.current_layout = QHBoxLayout()
        self.current_container.setLayout(self.current_layout)
        self.current_layout.setSpacing(5)
        self.current_layout.setContentsMargins(0, 0, 0, 0)
        self.values_layout.addWidget(self.current_container)

        # Метки для токов
        self.i_a_label = QLabel("I_A: -")
        self.i_a_label.setMinimumWidth(80)
        self.current_layout.addWidget(self.i_a_label)

        self.i_b_label = QLabel("I_B: -")
        self.i_b_label.setMinimumWidth(80)
        self.current_layout.addWidget(self.i_b_label)

        self.i_c_label = QLabel("I_C: -")
        self.i_c_label.setMinimumWidth(80)
        self.current_layout.addWidget(self.i_c_label)

        # Панель с графиками
        self.plot_widget = QWidget()
        self.plot_layout = QVBoxLayout()
        self.plot_widget.setLayout(self.plot_layout)
        self.main_layout.addWidget(self.plot_widget)

        self.plot_widgets = {}
        self.view_boxes = {}
        self.cursors = {}
        self.columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
        self.plot_items = {col: [] for col in self.columns}

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

        # Подключаем сигнал изменения диапазона для фиксации курсора
        self.lock_cursor_mode = False
        self.view_boxes['U_A_rms'].sigRangeChanged.connect(self.update_cursor_on_range_change)

        # Данные
        self.all_data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.all_time_labels = []
        self.all_valid_indices = []
        self.current_device = None
        self.data_loader = None
        self.pending_timestamps = []
        self.is_loading = False

        self.lock_cursor_mode = False
        self.lock_cursor_button.setChecked(False)

        self.apply_theme(True)

    def apply_theme(self, dark_theme):
        palette = QPalette()
        if dark_theme:
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

            navigation_style = """
                QWidget {
                    background-color: #353535;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    padding: 5px;
                }
                QToolButton {
                    margin: 2px;
                    padding: 5px;
                }
            """
            label_style = """
                QLabel {
                    background-color: #353535;
                    border: 1px solid #666;
                    border-radius: 3px;
                    padding: 3px;
                    color: white;
                    font-weight: bold;
                }
            """
            values_container_style = """
                QWidget {
                    background-color: #353535;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    padding: 5px;
                }
            """
        else:
            palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(76, 163, 224))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

            navigation_style = """
                QWidget {
                    background-color: #f0f0f0;
                    border: 1px solid #999;
                    border-radius: 5px;
                    padding: 5px;
                }
                QToolButton {
                    margin: 2px;
                    padding: 5px;
                }
            """
            label_style = """
                QLabel {
                    background-color: #f0f0f0;
                    border: 1px solid #999;
                    border-radius: 3px;
                    padding: 3px;
                    color: black;
                    font-weight: bold;
                }
            """
            values_container_style = """
                QWidget {
                    background-color: #f0f0f0;
                    border: 1px solid #999;
                    border-radius: 5px;
                    padding: 5px;
                }
            """

        self.setPalette(palette)
        self.main_widget.setPalette(palette)
        self.top_container.setPalette(palette)
        self.navigation_container.setPalette(palette)
        self.datetime_container.setPalette(palette)
        self.progress_container.setPalette(palette)
        self.values_container.setPalette(palette)
        self.voltage_container.setPalette(palette)
        self.current_container.setPalette(palette)
        self.plot_widget.setPalette(palette)

        self.navigation_container.setStyleSheet(navigation_style)
        self.values_container.setStyleSheet(values_container_style)
        self.datetime_label.setStyleSheet(label_style)
        self.status_label.setStyleSheet(label_style)
        self.progress_label.setStyleSheet(label_style)
        self.u_a_label.setStyleSheet(label_style)
        self.u_b_label.setStyleSheet(label_style)
        self.u_c_label.setStyleSheet(label_style)
        self.i_a_label.setStyleSheet(label_style)
        self.i_b_label.setStyleSheet(label_style)
        self.i_c_label.setStyleSheet(label_style)

        for col in self.columns:
            plot_widget = self.plot_widgets[col]
            plot_widget.setBackground('k')
            plot_widget.getAxis('left').setTextPen('w')
            plot_widget.getAxis('bottom').setTextPen('w')
            plot_widget.setLabel('bottom', 'Time', color='white')
            plot_widget.setLabel('left', col, color='white')

    def set_cursor_to_timestamp(self, timestamp_ms):
        if self.is_loading or self.all_data.empty:
            self.pending_timestamps.append(timestamp_ms)
            return

        diffs = np.abs(self.all_data['timestamp'].values - timestamp_ms)
        idx = np.argmin(diffs)
        if diffs[idx] == 0:
            timestamp_sec = timestamp_ms / 1000.0
            for cursor in self.cursors.values():
                cursor.blockSignals(True)
                cursor.setValue(timestamp_sec)
                cursor.blockSignals(False)
            self.update_values()
            self.center_on_cursor()
        else:
            logging.warning(f"No exact match for timestamp {timestamp_ms} in trends data")

    def process_pending_timestamps(self):
        while self.pending_timestamps:
            ts = self.pending_timestamps.pop(0)
            self.set_cursor_to_timestamp(ts)

    def toggle_lock_cursor_mode(self):
        self.lock_cursor_mode = self.lock_cursor_button.isChecked()
        if self.lock_cursor_mode:
            self.move_cursor_to_center()
            self.lock_cursor_button.setIcon(QIcon("./icons/lock_cursor.png"))
        else:
            self.lock_cursor_button.setIcon(QIcon("./icons/lock_cursor_active.png"))
        self.update_values()

    def update_cursor_on_range_change(self, viewbox, range):
        if self.lock_cursor_mode:
            x_range = range[0]
            center_pos = (x_range[0] + x_range[1]) / 2
            for cursor in self.cursors.values():
                cursor.blockSignals(True)
                cursor.setValue(center_pos)
                cursor.blockSignals(False)
            self.update_values()

    def move_cursor_to_center(self):
        if not self.plot_widgets:
            return

        viewbox = self.view_boxes[self.columns[0]]
        x_range = viewbox.viewRange()[0]
        center_pos = (x_range[0] + x_range[1]) / 2

        for cursor in self.cursors.values():
            cursor.blockSignals(True)
            cursor.setValue(center_pos)
            cursor.blockSignals(False)

        self.update_values()

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

    def update_values(self):
        if not self.all_data.empty and self.all_time_labels and self.all_valid_indices:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.all_time_labels) - cursor_pos))
            if 0 <= idx < len(self.all_valid_indices):
                data_idx = self.all_valid_indices[idx]
                try:
                    timestamp_ms = self.all_data['timestamp'].iloc[data_idx]
                    timestamp_sec = timestamp_ms / 1000
                    date_time = datetime.fromtimestamp(timestamp_sec).strftime('%Y-%m-%d %H:%M:%S')
                    self.datetime_label.setText(f"Дата/время: {date_time}")
                except Exception as e:
                    self.datetime_label.setText("Дата/время: Ошибка")
                    logging.error(f"Ошибка обработки временной метки: {str(e)}")

                try:
                    u_a = self.all_data['U_A_rms'].iloc[data_idx]
                    u_b = self.all_data['U_B_rms'].iloc[data_idx]
                    u_c = self.all_data['U_C_rms'].iloc[data_idx]
                    i_a = self.all_data['I_A_rms'].iloc[data_idx]
                    i_b = self.all_data['I_B_rms'].iloc[data_idx]
                    i_c = self.all_data['I_C_rms'].iloc[data_idx]

                    self.u_a_label.setText(f"U_A: {u_a:.1f} V" if pd.notna(u_a) else "U_A: -")
                    self.u_b_label.setText(f"U_B: {u_b:.1f} V" if pd.notna(u_b) else "U_B: -")
                    self.u_c_label.setText(f"U_C: {u_c:.1f} V" if pd.notna(u_c) else "U_C: -")
                    self.i_a_label.setText(f"I_A: {i_a:.1f} A" if pd.notna(i_a) else "I_A: -")
                    self.i_b_label.setText(f"I_B: {i_b:.1f} A" if pd.notna(i_b) else "I_B: -")
                    self.i_c_label.setText(f"I_C: {i_c:.1f} A" if pd.notna(i_c) else "I_C: -")
                except Exception as e:
                    logging.error(f"Ошибка обновления значений: {str(e)}")
                    self.u_a_label.setText("U_A: -")
                    self.u_b_label.setText("U_B: -")
                    self.u_c_label.setText("U_C: -")
                    self.i_a_label.setText("I_A: -")
                    self.i_b_label.setText("I_B: -")
                    self.i_c_label.setText("I_C: -")

    def clear_previous_data(self):
        self.all_data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.all_time_labels = []
        self.all_valid_indices = []
        self.pending_timestamps = []

        for col in self.columns:
            plot_widget = self.plot_widgets[col]
            for item in self.plot_items[col]:
                plot_widget.removeItem(item)
            self.plot_items[col] = []
            plot_widget.addItem(self.cursors[col])

        self.datetime_label.setText("Дата/время: -")
        self.u_a_label.setText("U_A: -")
        self.u_b_label.setText("U_B: -")
        self.u_c_label.setText("U_C: -")
        self.i_a_label.setText("I_A: -")
        self.i_b_label.setText("I_B: -")
        self.i_c_label.setText("I_C: -")
        self.status_label.setText("Очистка данных...")
        self.progress_label.setText("0%")

    def fetch_logger_data(self, table_name: str):
        if self.current_device == table_name:
            return

        self.clear_previous_data()
        self.is_loading = True
        self.current_device = table_name
        self.status_label.setText("Загрузка данных...")
        self.progress_bar.setVisible(True)
        self.progress_label.setText("0%")

        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()

        self.data_loader = DataLoaderThread(self.current_device)
        self.data_loader.data_processed.connect(self.on_data_processed)
        self.data_loader.error_occurred.connect(self.on_error_occurred)
        self.data_loader.progress_updated.connect(self.update_progress)
        self.data_loader.finished.connect(self.on_data_loader_finished)
        self.data_loader.start()

    def on_data_loader_finished(self):
        self.data_loader.deleteLater()
        self.data_loader = None

    def on_data_processed(self, df):
        self.all_data = df
        self.plot_data(df)
        self.status_label.setText("Данные загружены")
        self.is_loading = False
        self.progress_bar.setVisible(False)
        self.progress_label.setText("100%")
        self.process_pending_timestamps()
        if self.all_time_labels:
            min_t, max_t = min(self.all_time_labels), max(self.all_time_labels)
            for vb in self.view_boxes.values():
                vb.setXRange(min_t, max_t, padding=0.05)
            if self.lock_cursor_mode:
                self.move_cursor_to_center()

        # Автоматическое масштабирование для токовых каналов
        current_cols = ['I_A_rms', 'I_B_rms', 'I_C_rms']
        for col in current_cols:
            if col in self.all_data.columns:
                max_val = self.all_data[col].max()
                if pd.notna(max_val) and max_val < 10:
                    self.plot_widgets[col].setYRange(0, 10)
                else:
                    self.plot_widgets[col].enableAutoRange()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        self.progress_label.setText(f"{value}%")

    def plot_data_from_signal(self, table_name: str, colname_list: list = None, in_data: dict = None, rec_num: int = None):
        if table_name:
            if in_data and 'timestamp' in in_data:
                self.pending_timestamps.append(in_data['timestamp'])
            self.fetch_logger_data(table_name)
        else:
            self.parent.status_bar.showMessage("Ошибка: Не указано имя таблицы", 5000)

    def plot_data(self, df):
        try:
            timestamps = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
            valid_indices = [i for i, t in enumerate(timestamps) if pd.notna(t)]
            self.time_labels = [timestamps[i].timestamp() for i in valid_indices]
            self.valid_data_indices = valid_indices

            if len(self.time_labels) < 2:
                return

            self.all_time_labels = self.time_labels
            self.all_valid_indices = valid_indices

            time_diffs = np.diff(self.time_labels)
            gap_indices = np.where(time_diffs > 900)[0]

            for col in self.columns:
                plot_widget = self.plot_widgets[col]
                split_indices = np.concatenate([[0], gap_indices + 1, [len(self.time_labels)]])

                for i in range(len(split_indices) - 1):
                    start_idx = split_indices[i]
                    end_idx = split_indices[i + 1]
                    if end_idx - start_idx < 2:
                        continue

                    x_segment = np.array(self.time_labels[start_idx:end_idx])
                    y_segment = np.array(df[col].iloc[valid_indices[start_idx:end_idx]])

                    if not np.all(np.isnan(y_segment)):
                        plot_item = plot_widget.plot(x_segment, y_segment,
                                                     pen={'color': '#FF0000', 'width': 1},
                                                     connect='finite')
                        self.plot_items[col].append(plot_item)

                for idx in gap_indices:
                    if idx + 1 < len(self.time_labels):
                        start = self.time_labels[idx]
                        end = self.time_labels[idx + 1]
                        region = pg.LinearRegionItem(values=[start, end], movable=False)
                        region.setBrush(QColor(128, 128, 128, 100))
                        region.setZValue(-10)
                        plot_widget.addItem(region)
                        self.plot_items[col].append(region)

            for i, idx in enumerate(self.valid_data_indices):
                row = df.iloc[idx]
                if all(pd.isna(row[col]) for col in self.columns):
                    timestamp = self.time_labels[i]
                    start = self.time_labels[i - 1] if i > 0 else timestamp - 0.5
                    end = self.time_labels[i + 1] if i < len(self.time_labels) - 1 else timestamp + 0.5
                    for col in self.columns:
                        plot_widget = self.plot_widgets[col]
                        region = pg.LinearRegionItem(values=[start, end], movable=False)
                        region.setBrush(QColor(255, 255, 0, 100))
                        region.setZValue(-5)
                        plot_widget.addItem(region)
                        self.plot_items[col].append(region)

            if self.all_time_labels:
                min_t, max_t = min(self.all_time_labels), max(self.all_time_labels)
                for cursor in self.cursors.values():
                    cursor.setBounds([min_t, max_t])
                    if cursor.value() < min_t or cursor.value() > max_t:
                        cursor.setValue((min_t + max_t) / 2)

            self.update_values()

        except Exception as e:
            logging.error(f"Ошибка при отрисовке графика: {str(e)}")
            self.on_error_occurred(f"Ошибка при отрисовке графика: {str(e)}")

    def center_on_cursor(self):
        if self.all_time_labels:
            cursor_pos = self.cursors['U_A_rms'].value()
            half_range = 1800
            for vb in self.view_boxes.values():
                vb.setXRange(cursor_pos - half_range, cursor_pos + half_range, padding=0)

    def send_timestamp_to_signals(self):
        if not self.all_data.empty and self.all_time_labels and hasattr(self.parent, 'SignalsView_subwindow'):
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.all_time_labels) - cursor_pos))
            if 0 <= idx < len(self.all_valid_indices):
                timestamp = self.all_data['timestamp'].iloc[self.all_valid_indices[idx]]
                self.parent.SignalsView_subwindow.set_timestamp_from_trends(timestamp)
                self.parent.status_bar.showMessage(f"Время {timestamp} передано в окно сигналов", 5000)

    def on_error_occurred(self, error_msg):
        self.parent.status_bar.showMessage(error_msg, 5000)
        self.status_label.setText("Ошибка")
        self.progress_bar.setVisible(False)
        self.progress_label.setText("0%")
        self.is_loading = False
        logging.error(error_msg)

    def closeEvent(self, event):
        if hasattr(self, 'data_loader') and self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()
        super().closeEvent(event)
