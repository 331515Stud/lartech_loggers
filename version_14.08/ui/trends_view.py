from PyQt6.QtWidgets import QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QTextEdit, QToolButton, QProgressBar, QLabel, QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
from Lib import pipestreamdbread as pdb
import logging
from datetime import datetime
import math
import warnings

# Настройка pyqtgraph для улучшенного отображения графиков
pg.setConfigOptions(antialias=True, background='k', foreground='w')
warnings.filterwarnings("ignore", category=UserWarning, module="pyqtgraph")


def RMS(sig):
    """Расчет среднеквадратичного значения (СКЗ) по предоставленной формуле"""
    l = len(sig)
    if l == 0:
        return 0
    summ = sum(x ** 2 for x in sig)
    return math.sqrt(summ / l)


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
    data_loaded = pyqtSignal(list, list, int, int)  # Сигнал: записи, столбцы, индекс части, общее количество частей
    error_occurred = pyqtSignal(str)  # Сигнал: сообщение об ошибке
    progress_updated = pyqtSignal(int)  # Сигнал: обновление прогресса
    finished_loading_chunk = pyqtSignal()

    def __init__(self, table_name, chunk_index, chunk_size=100, total_records=None, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.chunk_index = chunk_index
        self.chunk_size = chunk_size
        self.total_records = total_records

    def run(self):
        try:
            connection, cursor, status = pdb.connect_db(pdb.db_connection_params)
            if connection == 0 or cursor == 0:
                self.error_occurred.emit(f"Ошибка подключения к БД: {status}")
                return

            colnames_list = pdb.get_column_names(cursor, self.table_name)
            required_columns = ['timestamp', 'points', 'mask', 'npoints',
                               'cfg_voltage_multiplier', 'cfg_voltage_divider',
                               'cfg_current_multiplier', 'cfg_current_divider']

            if not all(col in colnames_list for col in required_columns):
                self.error_occurred.emit(f"Ошибка: Таблица {self.table_name} не содержит всех необходимых столбцов")
                cursor.close()
                connection.close()
                return

            if self.total_records is None:
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                self.total_records = cursor.fetchone()[0]
            if self.total_records == 0:
                self.error_occurred.emit(f"Нет данных в таблице {self.table_name}")
                cursor.close()
                connection.close()
                return

            total_chunks = math.ceil(self.total_records / self.chunk_size)
            offset = self.chunk_index * self.chunk_size
            query = f"SELECT {', '.join(required_columns)} FROM {self.table_name} ORDER BY timestamp ASC LIMIT {self.chunk_size} OFFSET {offset}"
            cursor.execute(query)
            records = cursor.fetchall()
            if records:
                self.data_loaded.emit(records, required_columns, self.chunk_index, total_chunks)
            self.progress_updated.emit(int((self.chunk_index + 1) / total_chunks * 100))
            cursor.close()
            connection.close()
            self.finished_loading_chunk.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка при загрузке данных: {str(e)}")


class RMSCalculatorThread(QThread):
    data_ready = pyqtSignal(pd.DataFrame, int, int)  # Сигнал: DataFrame, индекс части, общее количество частей
    error_occurred = pyqtSignal(str)  # Сигнал: сообщение об ошибке
    progress_updated = pyqtSignal(int)  # Сигнал: обновление прогресса
    finished_calculating = pyqtSignal()

    def __init__(self, records, required_columns, chunk_index, total_chunks, parent=None):
        super().__init__(parent)
        self.records = records
        self.required_columns = required_columns
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks

    def run(self):
        try:
            data_list = []
            total_records = len(self.records)

            for i, record in enumerate(self.records):
                record_dict = dict(zip(self.required_columns, record))
                rec = pdb.LogRecord(record_dict)
                signals = rec.get_signals()

                if len(signals) == 0:
                    rms_values = [np.nan] * 6
                else:
                    rms_values = []
                    for channel in range(min(6, signals.shape[1])):
                        channel_signal = signals[:, channel]
                        rms_values.append(RMS(channel_signal))
                    rms_values.extend([np.nan] * (6 - len(rms_values)))

                row = {'timestamp': record_dict['timestamp']}
                for j, col in enumerate(['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']):
                    row[col] = rms_values[j] if j < len(rms_values) else np.nan
                data_list.append(row)

                if (i + 1) % 10 == 0 or (i + 1) == total_records:
                    self.progress_updated.emit(int((i + 1) / total_records * 100))

            df = pd.DataFrame(data_list)
            self.data_ready.emit(df, self.chunk_index, self.total_chunks)
            self.finished_calculating.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ошибка при расчете СКЗ: {str(e)}")


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

        # Область содержимого
        self.content_layout = QHBoxLayout()
        self.main_layout.addLayout(self.content_layout)

        # Левая панель с графиками
        self.left_panel = QWidget()
        self.plot_layout = QVBoxLayout()
        self.left_panel.setLayout(self.plot_layout)
        self.content_layout.addWidget(self.left_panel)

        # Правая панель с кнопками, статусом и информацией
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.right_panel.setMinimumWidth(200)
        self.right_panel.setMaximumWidth(300)
        self.right_layout = QVBoxLayout()
        self.right_layout.setContentsMargins(5, 5, 5, 5)
        self.right_layout.setSpacing(10)
        self.right_panel.setLayout(self.right_layout)
        self.content_layout.addWidget(self.right_panel)

        # Статус и прогресс
        self.status_label = QLabel("Нет данных")
        self.right_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.right_layout.addWidget(self.progress_bar)

        # Кнопки
        self.go_to_cursor_button = QToolButton()
        self.go_to_cursor_button.setText("Перейти к курсору")
        self.go_to_cursor_button.setToolTip("Центрировать вид на текущем положении курсора")
        self.go_to_cursor_button.setIcon(QIcon("./icons/center.png"))
        self.go_to_cursor_button.clicked.connect(self.center_on_cursor)
        self.right_layout.addWidget(self.go_to_cursor_button)

        self.center_cursor_button = QToolButton()
        self.center_cursor_button.setText("Центр видимого")
        self.center_cursor_button.setToolTip("Переместить курсор в центр текущего видимого диапазона")
        self.center_cursor_button.setIcon(QIcon("./icons/center_cursor.png"))
        self.center_cursor_button.clicked.connect(self.move_cursor_to_center)
        self.right_layout.addWidget(self.center_cursor_button)

        self.center_data_range_button = QToolButton()
        self.center_data_range_button.setText("Центр данных")
        self.center_data_range_button.setToolTip("Переместить курсор в центр полного диапазона данных")
        self.center_data_range_button.setIcon(QIcon("./icons/center_data.png"))
        self.center_data_range_button.clicked.connect(self.move_cursor_to_data_center)
        self.right_layout.addWidget(self.center_data_range_button)

        self.send_timestamp_button = QToolButton()
        self.send_timestamp_button.setText("→ Сигналы")
        self.send_timestamp_button.setToolTip("Передать время курсора в окно сигналов")
        self.send_timestamp_button.setIcon(QIcon("./icons/send.png"))
        self.send_timestamp_button.clicked.connect(self.send_timestamp_to_signals)
        self.right_layout.addWidget(self.send_timestamp_button)

        # Отображение значений
        self.value_display = QTextEdit()
        self.value_display.setReadOnly(True)
        self.right_layout.addWidget(self.value_display)

        # Добавляем растяжение, чтобы элементы не растягивались по высоте
        self.right_layout.addStretch()

        # Инициализация графиков и курсоров
        self.plot_widgets = {}
        self.view_boxes = {}
        self.cursors = {}
        self.columns = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
        self.plot_items = {col: [] for col in self.columns}  # Хранит ссылки на объекты графиков

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

            cursor_pen = pg.mkPen(color='y', width=3)
            cursor = CustomInfiniteLine(pos=0, angle=90, pen=cursor_pen, movable=True, hoverPen=cursor_pen)
            cursor.setZValue(10)
            plot_widget.addItem(cursor)
            self.cursors[col] = cursor
            cursor.sigPositionChanged.connect(self.make_cursor_sync_function(col))

        # Данные
        self.all_data = pd.DataFrame()  # Все данные для курсора
        self.time_labels = []  # Временные метки для текущего чанка
        self.valid_data_indices = []  # Индексы валидных данных
        self.all_time_labels = []  # Все временные метки для курсора
        self.all_valid_indices = []  # Все валидные индексы для курсора
        self.current_device = None
        self.data_loader = None
        self.rms_calculator = None
        self.total_chunks = 0  # Общее количество частей
        self.processed_chunks = 0  # Количество обработанных частей
        self.current_chunk_index = 0
        self.total_records = None

        self.set_style()

    def move_cursor_to_center(self):
        """Перемещает курсор в центр текущего видимого диапазона графика"""
        if not self.plot_widgets:
            return

        viewbox = self.view_boxes[self.columns[0]]
        x_range = viewbox.viewRange()[0]
        center_pos = (x_range[0] + x_range[1]) / 2

        for cursor in self.cursors.values():
            cursor.setValue(center_pos)

        self.update_values()

    def move_cursor_to_data_center(self):
        """Перемещает курсор в центр полного диапазона данных"""
        if not self.all_time_labels:
            return

        min_t, max_t = min(self.all_time_labels), max(self.all_time_labels)
        center_pos = (min_t + max_t) / 2

        for cursor in self.cursors.values():
            cursor.setValue(center_pos)

        self.update_values()

    def set_style(self):
        """Установка стилей для элементов интерфейса"""
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
                font-size: 12px;
                min-width: 100px;
                max-width: 150px;
            }
            QToolButton:hover {
                background-color: #a13de5;
            }
            QToolButton:pressed {
                background-color: #6e1da5;
            }
            QToolButton#center_data_range_button {
                background-color: #6a1b9a;
            }
            QToolButton#center_data_range_button:hover {
                background-color: #7b1fa2;
            }
            QToolButton#center_data_range_button:pressed {
                background-color: #4a0072;
            }
            QFrame#right_panel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)
        self.right_panel.setObjectName("right_panel")
        self.center_data_range_button.setObjectName("center_data_range_button")

    def make_cursor_sync_function(self, source_col):
        """Создает функцию синхронизации курсоров между графиками"""
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
        """Обновляет отображаемые значения на правой панели"""
        if not self.all_data.empty and self.all_time_labels and self.all_valid_indices:
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.all_time_labels) - cursor_pos))
            if 0 <= idx < len(self.all_valid_indices):
                data_idx = self.all_valid_indices[idx]
                try:
                    timestamp_ms = self.all_data['timestamp'].iloc[data_idx]
                    timestamp_sec = timestamp_ms / 1000
                    date_time = datetime.fromtimestamp(timestamp_sec).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                except Exception as e:
                    date_time = "Ошибка"
                    logging.error(f"Ошибка обработки временной метки: {str(e)}")

                display_text = f"<span style='color:#8e2dc5; font-weight:700;'>Date/Time:</span> {date_time}<br><br>"
                for col in self.columns:
                    try:
                        value = self.all_data[col].iloc[data_idx]
                        val_str = f"{value:.2f}" if pd.notna(value) else "N/A"
                        display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>{val_str}</span><br>"
                    except:
                        display_text += f"<span style='color:#8e2dc5;'>{col}:</span> <span style='color:white;'>N/A</span><br>"
                self.value_display.setHtml(display_text)

    def clear_previous_data(self):
        """Очищает предыдущие данные и графики"""
        self.all_data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.all_time_labels = []
        self.all_valid_indices = []
        self.total_chunks = 0
        self.processed_chunks = 0
        self.current_chunk_index = 0
        self.total_records = None

        for col in self.columns:
            plot_widget = self.plot_widgets[col]
            for item in self.plot_items[col]:
                plot_widget.removeItem(item)
            self.plot_items[col] = []
            plot_widget.addItem(self.cursors[col])

        self.value_display.setHtml("")
        self.status_label.setText("Очистка данных...")

    def fetch_logger_data(self, table_name: str):
        """Запускает загрузку данных для указанной таблицы"""
        if self.current_device == table_name:
            return

        self.clear_previous_data()
        self.current_device = table_name
        self.status_label.setText(f"Загрузка данных для {table_name}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()
        if self.rms_calculator and self.rms_calculator.isRunning():
            self.rms_calculator.terminate()
            self.rms_calculator.wait()

        self.start_next_chunk_loader()

    def start_next_chunk_loader(self):
        self.data_loader = DataLoaderThread(self.current_device, self.current_chunk_index, chunk_size=100, total_records=self.total_records)
        self.data_loader.data_loaded.connect(self.on_data_loaded)
        self.data_loader.error_occurred.connect(self.on_error_occurred)
        self.data_loader.progress_updated.connect(self.update_progress)
        self.data_loader.finished_loading_chunk.connect(self.on_chunk_loaded_finished)
        self.data_loader.start()

    def on_chunk_loaded_finished(self):
        self.data_loader.deleteLater()
        self.data_loader = None

    def on_data_loaded(self, records, required_columns, chunk_index, total_chunks):
        """Обрабатывает загруженные данные и запускает расчет СКЗ"""
        self.status_label.setText(f"Рассчет СКЗ для {self.current_device} (Часть {chunk_index + 1}/{total_chunks})...")
        self.total_chunks = total_chunks
        if self.total_records is None:
            self.total_records = total_chunks * 100  # Примерное значение, если не известно точно

        self.rms_calculator = RMSCalculatorThread(records, required_columns, chunk_index, total_chunks)
        self.rms_calculator.data_ready.connect(self.on_rms_calculated)
        self.rms_calculator.error_occurred.connect(self.on_error_occurred)
        self.rms_calculator.progress_updated.connect(self.update_rms_progress)
        self.rms_calculator.finished_calculating.connect(self.on_calculating_finished)
        self.rms_calculator.start()

    def on_calculating_finished(self):
        self.rms_calculator.deleteLater()
        self.rms_calculator = None

    def on_rms_calculated(self, df, chunk_index, total_chunks):
        """Обрабатывает рассчитанные СКЗ данные и обновляет график"""
        self.all_data = pd.concat([self.all_data, df], ignore_index=True)
        self.processed_chunks += 1
        self.plot_data(df)  # Передаем текущий df для отрисовки
        self.status_label.setText(f"Загружено {self.processed_chunks}/{total_chunks} частей для {self.current_device} ({len(self.all_data)} записей)")
        self.current_chunk_index += 1
        if self.processed_chunks < total_chunks:
            self.start_next_chunk_loader()  # Загружаем следующий чанк после отрисовки
        else:
            self.progress_bar.setVisible(False)
            # Авто-зум на полный диапазон после загрузки всех чанков
            if self.all_time_labels:
                min_t, max_t = min(self.all_time_labels), max(self.all_time_labels)
                for vb in self.view_boxes.values():
                    vb.setXRange(min_t, max_t, padding=0.05)

    def update_rms_progress(self, value):
        """Обновляет прогресс расчета СКЗ"""
        chunk_progress = (self.processed_chunks / self.total_chunks) * 100 if self.total_chunks > 0 else 0
        sub_progress = value / self.total_chunks if self.total_chunks > 0 else 0
        total_progress = int(chunk_progress + sub_progress)
        self.progress_bar.setValue(total_progress)

    def plot_data_from_signal(self, table_name: str, colname_list: list = None, in_data: dict = None, rec_num: int = None):
        """Обрабатывает сигнал с данными для построения графиков"""
        if table_name:
            self.fetch_logger_data(table_name)
        else:
            self.parent.status_bar.showMessage("Ошибка: Не указано имя таблицы", 5000)

    def plot_data(self, df):
        """Рисует графики на основе текущего чанка данных"""
        try:
            timestamps = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
            valid_indices = [i for i, t in enumerate(timestamps) if pd.notna(t)]
            self.time_labels = [timestamps[i].timestamp() for i in valid_indices]
            self.valid_data_indices = valid_indices

            if len(self.time_labels) < 2:
                return

            # Обновляем глобальные списки временных меток для курсора
            offset = len(self.all_time_labels)
            self.all_time_labels.extend(self.time_labels)
            self.all_valid_indices.extend([i + offset for i in valid_indices])

            time_diffs = np.diff(self.time_labels)
            gap_indices = np.where(time_diffs > 900)[0]

            for col in self.columns:
                plot_widget = self.plot_widgets[col]

                # Сначала рисуем линии графика
                split_indices = np.concatenate([[0], gap_indices + 1, [len(self.time_labels)]])

                for i in range(len(split_indices) - 1):
                    start_idx = split_indices[i]
                    end_idx = split_indices[i + 1]

                    if end_idx - start_idx < 2:
                        continue

                    x_segment = np.array(self.time_labels[start_idx:end_idx])
                    y_segment = np.array(df[col].iloc[valid_indices[start_idx:end_idx]])

                    # Отрисовка красных линий для валидных данных
                    if not np.all(np.isnan(y_segment)):
                        plot_item = plot_widget.plot(x_segment, y_segment,
                                                     pen={'color': '#FF0000', 'width': 1},
                                                     connect='finite')
                        self.plot_items[col].append(plot_item)

                # Затем добавляем серые регионы для временных разрывов
                for idx in gap_indices:
                    if idx + 1 < len(self.time_labels):
                        start = self.time_labels[idx]
                        end = self.time_labels[idx + 1]
                        region = pg.LinearRegionItem(values=[start, end], movable=False)
                        region.setBrush(QColor(128, 128, 128, 100))  # Серый с прозрачностью
                        region.setZValue(-10)
                        plot_widget.addItem(region)
                        self.plot_items[col].append(region)

            # Добавляем жёлтые регионы для точек, где все значения N/A
            for i, idx in enumerate(self.valid_data_indices):
                row = df.iloc[idx]
                if all(pd.isna(row[col]) for col in self.columns):
                    timestamp = self.time_labels[i]
                    # Определяем границы региона: от предыдущей до следующей записи
                    start = self.time_labels[i - 1] if i > 0 else timestamp - 0.5
                    end = self.time_labels[i + 1] if i < len(self.time_labels) - 1 else timestamp + 0.5
                    for col in self.columns:
                        plot_widget = self.plot_widgets[col]
                        region = pg.LinearRegionItem(values=[start, end], movable=False)
                        region.setBrush(QColor(255, 255, 0, 100))  # Жёлтый с прозрачностью
                        region.setZValue(-5)  # Чуть выше серых регионов, но ниже курсоров
                        plot_widget.addItem(region)
                        self.plot_items[col].append(region)

            # Обновляем границы курсора
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
        """Центрирует график на текущем положении курсора"""
        if self.all_time_labels:
            cursor_pos = self.cursors['U_A_rms'].value()
            half_range = 1800

            for vb in self.view_boxes.values():
                vb.setXRange(cursor_pos - half_range, cursor_pos + half_range, padding=0)

    def send_timestamp_to_signals(self):
        """Передает время курсора в окно сигналов"""
        if not self.all_data.empty and self.all_time_labels and hasattr(self.parent, 'SignalsView_subwindow'):
            cursor_pos = self.cursors['U_A_rms'].value()
            idx = np.argmin(np.abs(np.array(self.all_time_labels) - cursor_pos))
            if 0 <= idx < len(self.all_valid_indices):
                timestamp = self.all_data['timestamp'].iloc[self.all_valid_indices[idx]]
                self.parent.SignalsView_subwindow.set_timestamp_from_trends(timestamp)
                self.parent.status_bar.showMessage(f"Время {timestamp} передано в окно сигналов", 5000)

    def update_progress(self, value):
        """Обновляет прогресс загрузки данных"""
        self.progress_bar.setValue(value)

    def on_error_occurred(self, error_msg):
        """Обрабатывает ошибки и отображает их в интерфейсе"""
        self.parent.status_bar.showMessage(error_msg, 5000)
        self.status_label.setText("Ошибка")
        self.progress_bar.setVisible(False)
        logging.error(error_msg)

    def closeEvent(self, event):
        """Очищает ресурсы при закрытии окна"""
        if hasattr(self, 'data_loader') and self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()
        if hasattr(self, 'rms_calculator') and self.rms_calculator and self.rms_calculator.isRunning():
            self.rms_calculator.terminate()
            self.rms_calculator.wait()
        super().closeEvent(event)