from PyQt6.QtWidgets import QMdiSubWindow, QToolBar, QScrollArea, QToolButton, QLabel, QSlider, QCheckBox, QSizePolicy, QMessageBox, QWidget, QVBoxLayout, QLineEdit
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt
from PyQt6 import QtCore
from Lib import pipestreamdbread as pdb
from Lib import read_record_by_time_thread as rec_read_trr
from Lib import cifer_diapasons_parsing as cdp
import pyqtgraph as pg
import numpy as np
from scipy.fft import rfft
import base64
import logging
from ui.widgets import ResizableLineEdit
from ui.date_time_dialog import DateTimeSelectionDialog

class SignalsView_subwindow(QMdiSubWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Просмотр сигналов")
        self.setMinimumWidth(100)  # Reasonable minimum to prevent collapse

        self.current_current_table_timestamp_list = []
        self.current_rec_num = 0
        self.current_device = ""
        self.colnameList = []
        self.channel_boolmask = [True] * 7
        self.current_data = {}
        self.current_freq_range = (-1, -1)
        self.show_grid = False

        size_policy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.navi_toolbar = QToolBar('Navigation')
        self.navi_toolbar.setStyleSheet("""
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
        self.navi_toolbar.addAction("ЗАПИСИ")
        self.navi_toolbar.setSizePolicy(size_policy)

        self.plot_params = QToolBar('Plotting params')
        self.plot_params.setStyleSheet("""
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
        self.plot_params.addAction("ГРАФИКИ")
        self.plot_params.setSizePolicy(size_policy)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)

        self.plot = pg.GraphicsLayoutWidget()
        self.plotLayout = self.plot.ci.layout
        self.scrollArea.setWidget(self.plot)

        self.plot_array = [[0] * 2 for i in range(7)]
        for plot_row in range(7):
            for plot_col in range(2):
                plot = self.plot.addPlot(row=plot_row, col=plot_col)
                self.plot_array[plot_row][plot_col] = plot

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.navi_toolbar)
        main_layout.addWidget(self.plot_params)
        main_layout.addWidget(self.scrollArea)

        self.firstButton = QToolButton()
        self.firstButton.setText("<<")
        self.firstButton.setToolTip("К первой записи")
        self.firstButton.setMinimumWidth(20)
        self.firstButton.setAutoRaise(True)
        self.firstButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.firstButton)
        self.firstButton.clicked.connect(self.firstButton_clicked)

        self.leftButton = QToolButton()
        self.leftButton.setText("<")
        self.leftButton.setToolTip("К записи раньше")
        self.leftButton.setMinimumWidth(20)
        self.leftButton.setAutoRaise(True)
        self.leftButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.leftButton)
        self.leftButton.clicked.connect(self.leftButton_clicked)

        self.timeEdit = ResizableLineEdit(parent=self)
        self.timeEdit.setText("0000-00-00 00:00:00")
        self.timeEdit.setToolTip("Дата и время записи (YYYY-MM-DD HH:MM:SS)")
        self.timeEdit.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self.timeEdit.setReadOnly(True)
        timeEditIcon = QIcon("./icons/clock.png")
        timeEditIcon_action = QAction(timeEditIcon, "Время записи", self.timeEdit)
        self.timeEdit.addAction(timeEditIcon_action, QLineEdit.ActionPosition.LeadingPosition)
        self.timeEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.timeEdit)
        self.timeEdit.mousePressEvent = self.show_datetime_dialog

        self.savePointsButton = QToolButton()
        self.savePointsButton.setText("💾")
        self.savePointsButton.setToolTip("Сохранить точки в бинарный файл")
        self.savePointsButton.setMinimumWidth(20)
        self.savePointsButton.setAutoRaise(True)
        self.savePointsButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.savePointsButton)
        self.savePointsButton.clicked.connect(self.save_points_to_file)

        self.recNumEdit = ResizableLineEdit(parent=self)
        self.recNumEdit.setText("000000")
        self.recNumEdit.setToolTip("Номер записи в таблице БД")
        recNumEditIcon = QIcon("./icons/number.png")
        recNumEdit_action = QAction(recNumEditIcon, "Номер записи", self.recNumEdit)
        self.recNumEdit.addAction(recNumEdit_action, QLineEdit.ActionPosition.LeadingPosition)
        self.recNumEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.recNumEdit)
        self.recNumEdit.textEdited.connect(self.rec_num_edited)

        self.rightButton = QToolButton()
        self.rightButton.setText(">")
        self.rightButton.setToolTip("К записи позже")
        self.rightButton.setMinimumWidth(20)
        self.rightButton.setAutoRaise(True)
        self.rightButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.rightButton)
        self.rightButton.clicked.connect(self.rightButton_clicked)

        self.lastButton = QToolButton()
        self.lastButton.setText(">>")
        self.lastButton.setToolTip("К последней записи")
        self.lastButton.setMinimumWidth(20)
        self.lastButton.setAutoRaise(True)
        self.lastButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.lastButton)
        self.lastButton.clicked.connect(self.lastButton_clicked)

        self.stepEdit = ResizableLineEdit(parent=self)
        self.stepEdit.setText("1")
        self.stepEdit.setToolTip("Шаг промотки")
        stepEditIcon = QIcon("./icons/walking-man.png")
        stepEditEdit_action = QAction(stepEditIcon, "Шаг промотки", self.stepEdit)
        self.stepEdit.addAction(stepEditEdit_action, QLineEdit.ActionPosition.LeadingPosition)
        self.stepEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.stepEdit)

        filterIco = QIcon("./icons/three-horizontal-lines-icon.png")
        self.channelsFilterEdit = ResizableLineEdit(parent=self)
        self.channelsFilterEdit.setText(" ")
        self.channelsFilterEdit.setToolTip("Фильтр отображения каналов")
        self.channelsFilterEdit.setMinimumWidth(60)
        filter_action = QAction(filterIco, "Фильтр каналов", self.channelsFilterEdit)
        self.channelsFilterEdit.addAction(filter_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.channelsFilterEdit)
        self.channelsFilterEdit.textChanged.connect(self.on_channel_filter_changed)

        self.plot_params.addSeparator()

        self.plotColumnRationLabel = QLabel("1:1")
        self.plot_params.addWidget(self.plotColumnRationLabel)

        self.plotColumnRationSlider = QSlider(Qt.Orientation.Horizontal)
        self.plotColumnRationSlider.setToolTip("Соотношение ширины графиков сигнала и спектра")
        self.plotColumnRationSlider.setMinimum(1)
        self.plotColumnRationSlider.setMaximum(7)
        self.plotColumnRationSlider.setSliderPosition(4)
        self.plotColumnRationSlider.setMaximumWidth(150)
        self.plotColumnRationSlider.setMinimumWidth(50)
        self.plotColumnRationSlider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.plotColumnRationSlider.setTickInterval(1)
        self.plot_params.addWidget(self.plotColumnRationSlider)
        self.plotColumnRationSlider.valueChanged.connect(self.onPlotColumnSliderChanged)

        self.plot_params.addSeparator()

        self.freqRangeEdit = ResizableLineEdit(parent=self)
        self.freqRangeEdit.setText(" ")
        self.freqRangeEdit.setToolTip("Ограничение полосы отображения спектра")
        self.freqRangeEdit.setMinimumWidth(80)
        bandpassIco = QIcon("./icons/spectrum.png")
        bandpass_action = QAction(bandpassIco, "Полоса спектра", self.freqRangeEdit)
        self.freqRangeEdit.addAction(bandpass_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.freqRangeEdit)
        self.freqRangeEdit.textChanged.connect(self.on_freq_range_changed)

        self.plot_params.addSeparator()

        self.gridCheck = QCheckBox()
        self.gridCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        gridIco = QIcon("./icons/grid.png")
        self.gridCheck.setIcon(gridIco)
        self.gridCheck.setSizePolicy(size_policy)
        self.gridCheck.setToolTip("Включить сетку на графиках")
        self.plot_params.addWidget(self.gridCheck)
        self.gridCheck.checkStateChanged.connect(self.on_grid_check_changed)

        self.currentScaleEdit = ResizableLineEdit(parent=self)
        self.currentScaleEdit.setText(" ")
        self.currentScaleEdit.setToolTip("Установка минимальной шкалы тока")
        self.currentScaleEdit.setMinimumWidth(60)
        current_scale_ico = QIcon("./icons/Y-scale.png")
        current_scale_action = QAction(current_scale_ico, "Шкала тока", self.currentScaleEdit)
        self.currentScaleEdit.addAction(current_scale_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.currentScaleEdit)
        self.currentScaleEdit.textChanged.connect(self.on_current_scale_changed)

        self.plot_params.addSeparator()

        self.fix_X_AxleCheck = QCheckBox()
        self.fix_X_AxleCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        fixXIco = QIcon("./icons/axis-y.png")
        self.fix_X_AxleCheck.setIcon(fixXIco)
        self.fix_X_AxleCheck.setSizePolicy(size_policy)
        self.fix_X_AxleCheck.setToolTip("Зафиксировать ось X")
        self.plot_params.addWidget(self.fix_X_AxleCheck)
        self.fix_X_AxleCheck.checkStateChanged.connect(self.on_fixX_check_changed)

        self.fix_Y_AxleCheck = QCheckBox()
        self.fix_Y_AxleCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        fixYIco = QIcon("./icons/axis-x.png")
        self.fix_Y_AxleCheck.setIcon(fixYIco)
        self.fix_Y_AxleCheck.setSizePolicy(size_policy)
        self.fix_Y_AxleCheck.setToolTip("Зафиксировать ось Y")
        self.plot_params.addWidget(self.fix_Y_AxleCheck)
        self.fix_Y_AxleCheck.checkStateChanged.connect(self.on_fixY_check_changed)

        self.autoScaleButtton = QToolButton()
        self.autoScaleButtton.setText("AUTO")
        self.autoScaleButtton.setToolTip("Сбросить ограничения масштаба")
        self.plot_params.addWidget(self.autoScaleButtton)
        self.autoScaleButtton.pressed.connect(self.autoScaleBottonPressed)

        self.MainWidget = QWidget()
        self.MainWidget.setLayout(main_layout)
        self.setWidget(self.MainWidget)

    def set_current_table_timestamp_list(self, timestamp_list: list):
        self.current_current_table_timestamp_list = timestamp_list
        self.update_button_states()

    def set_current_rec_num(self, rec_num: int):
        self.current_rec_num = rec_num
        self.recNumEdit.setText(str(rec_num))
        self.update_button_states()

    def set_current_device(self, table_name: str):
        self.current_device = table_name
        self.update_button_states()

    def set_colname_list(self, colnameList: list):
        self.colnameList = colnameList
        self.update_button_states()

    def set_current_data(self, in_data: dict):
        self.current_data = in_data
        self.update_button_states()

    def set_current_freq_range(self, range: tuple):
        self.current_freq_range = range

    def update_button_states(self):
        """
        Включает или отключает кнопки навигации и сохранения в зависимости от доступности данных.
        """
        has_data = len(self.current_device) > 2 and len(self.colnameList) > 1 and len(
            self.current_current_table_timestamp_list) > 0
        self.firstButton.setEnabled(has_data and self.current_rec_num > 1)
        self.leftButton.setEnabled(has_data and self.current_rec_num > 1)
        self.rightButton.setEnabled(has_data and self.current_rec_num < len(self.current_current_table_timestamp_list))
        self.lastButton.setEnabled(has_data and self.current_rec_num < len(self.current_current_table_timestamp_list))
        self.savePointsButton.setEnabled(has_data and bool(self.current_data))

    def plot_record(self, table_name: str, colname_list: list, in_data: dict, rec_num: int):
        if len(table_name) < 1 or len(colname_list) < 1 or len(in_data) < 1:
            return

        self.set_current_device(table_name)
        self.set_colname_list(colname_list)
        self.set_current_data(in_data)

        rec = pdb.LogRecord(in_data)
        rec_dict = rec.get_record_dict()

        timestamp = rec_dict["timestamp"]
        time_to_display = pdb.datetime_from_timestamp(timestamp)
        self.timeEdit.blockSignals(True)
        self.timeEdit.setText(str(time_to_display)[:-3])
        self.timeEdit.blockSignals(False)

        self.set_current_rec_num(rec_num)

        signals = rec.get_signals()
        channel_num = signals.shape[1]

        curr_len = len(self.plot_array)

        for i in range(curr_len):
            if type(self.plot_array[i][0]) != int:
                self.plot_array[i][0].clear()

        for i in range(channel_num):
            if type(self.plot_array[i][0]) != int:
                if self.check_bool_mask(i):
                    self.plot_array[i][0].plot(signals[:, i])
                    self.plot_array[i][0].setTitle(f"Канал {i + 1}")
                else:
                    self.plot_array[i][0].clear()

        for i in range(curr_len):
            if type(self.plot_array[i][1]) != int:
                self.plot_array[i][1].clear()

        for i in range(channel_num):
            sig = signals[:, i]
            sampling = 25600

            sig = sig - sig.mean()
            l = len(sig)
            time_len = l / sampling
            time = np.linspace(0., time_len, l)

            yf = rfft(sig)
            sl = len(yf)
            freqstep = (sampling / 2) / sl
            spectrum = np.abs(rfft(sig)) / l
            step = (sampling / l)
            fr = np.arange(0, (sampling / 2) + 1, step)

            low_ind = 0
            hi_ind = sl

            if self.current_freq_range[0] > 0:
                low_ind = int((sl / (sampling / 2)) * self.current_freq_range[0])

            if self.current_freq_range[1] > 0 and self.current_freq_range[1] > self.current_freq_range[0] \
                    and self.current_freq_range[1] < (sampling / 2):
                hi_ind = int((sl / (sampling / 2)) * self.current_freq_range[1])

            if type(self.plot_array[i][1]) != int:
                if self.check_bool_mask(i):
                    self.plot_array[i][1].plot(fr[low_ind:hi_ind], spectrum[low_ind:hi_ind], pen='r')
                else:
                    self.plot_array[i][1].clear()

    def select_and_plot_record(self, num):
        rec_list_num = len(self.current_current_table_timestamp_list)
        if rec_list_num < 1 or num < 1 or num > rec_list_num:
            return

        timestamp = self.current_current_table_timestamp_list[num - 1]
        self.read_rec_thread = rec_read_trr.ReadRecordThread(self.current_device, self.colnameList, timestamp)
        self.read_rec_thread.error_signal.connect(self.on_error_message)
        self.read_rec_thread.result_signal.connect(self.on_next_rec_result)
        self.read_rec_thread.start()

    def save_points_to_file(self):
        """
        Сохраняет данные points текущей записи в бинарный файл в папку export.
        """
        if not self.current_data or len(self.current_device) < 3:
            self.on_error_message("Нет выбранной записи для сохранения")
            return

        rec = pdb.LogRecord(self.current_data)
        rec_dict = rec.get_record_dict()

        if "points" not in rec_dict or not rec_dict["points"]:
            self.on_error_message("Нет данных points в текущей записи")
            return

        try:
            # Декодируем base64 данные points
            byte_string = base64.b64decode(rec_dict["points"])
            timestamp = rec_dict["timestamp"]
            datetime_obj = pdb.datetime_from_timestamp(timestamp)
            # Формируем имя файла на основе устройства и времени
            filename = f"export/{self.current_device}_{datetime_obj.strftime('%Y%m%d_%H%M%S')}.bin"

            # Сохраняем в бинарный файл
            with open(filename, 'wb') as f:
                f.write(byte_string)

            self.parent.status_bar.showMessage(f"Данные points сохранены в файл: {filename}", 5000)
            logging.info(f"Сохранены данные points в файл: {filename}")

        except Exception as e:
            self.on_error_message(f"Ошибка при сохранении файла: {str(e)}")
            logging.error(f"Ошибка при сохранении points в файл: {str(e)}")

    def on_error_message(self, text):
        msgBox = QMessageBox()
        msgBox.setText(f"Ошибка: {text}")
        msgBox.exec()

    def on_next_rec_result(self, rec_dict):
        tab_name = self.current_device
        colname_list = self.colnameList
        rec_num = self.current_rec_num
        self.plot_record(tab_name, colname_list, rec_dict, rec_num)

    def firstButton_clicked(self):
        self.set_current_rec_num(1)
        self.select_and_plot_record(1)

    def leftButton_clicked(self):
        step_text = self.stepEdit.text()
        step = int(step_text) if step_text.isdigit() else 0

        if len(self.current_current_table_timestamp_list) < 1 or len(self.current_device) < 3 \
                or len(self.colnameList) < 2 or step < 1:
            return

        if step > self.current_rec_num:
            step = self.current_rec_num - 1

        if step == 0:
            return

        num = self.current_rec_num - step
        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def rightButton_clicked(self):
        step_text = self.stepEdit.text()
        step = int(step_text) if step_text.isdigit() else 0

        if len(self.current_current_table_timestamp_list) < 1 or len(self.current_device) < 3 \
                or len(self.colnameList) < 2 or step < 1:
            return

        total_rec_num = len(self.current_current_table_timestamp_list)

        if step > total_rec_num - self.current_rec_num:
            step = total_rec_num - self.current_rec_num

        if step == 0:
            return

        num = self.current_rec_num + step
        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def lastButton_clicked(self):
        last_num = len(self.current_current_table_timestamp_list)
        self.set_current_rec_num(last_num)
        self.select_and_plot_record(last_num)

    def rec_num_edited(self):
        rec_num_text = self.recNumEdit.text()
        num = int(rec_num_text) if rec_num_text.isdigit() else 0
        last = len(self.current_current_table_timestamp_list)

        if last < 1 or len(self.current_device) < 3 or len(self.colnameList) < 2 or num < 1 or num > last:
            return

        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def show_datetime_dialog(self, event=None):
        """
        Создает и показывает диалоговое окно для выбора даты и времени.
        Обрабатывает результат после его закрытия.
        """
        initial_datetime = None
        if self.current_data and "timestamp" in self.current_data:
            initial_datetime = pdb.datetime_from_timestamp(self.current_data["timestamp"])

        dialog = DateTimeSelectionDialog(initial_datetime, self)

        if dialog.exec():
            selected_dt = dialog.get_selected_datetime()
            timestamp = int(selected_dt.toSecsSinceEpoch() * 1000)

            if len(self.current_current_table_timestamp_list) < 1 or len(self.current_device) < 3 or len(
                    self.colnameList) < 2:
                self.on_error_message("Нет выбранного устройства или списка записей")
                return

            timestamp_list = self.current_current_table_timestamp_list
            if not timestamp_list:
                self.on_error_message("Список записей пуст")
                return

            closest_timestamp = min(timestamp_list, key=lambda x: abs(x - timestamp))
            closest_index = timestamp_list.index(closest_timestamp) + 1

            self.set_current_rec_num(closest_index)
            self.timeEdit.blockSignals(True)
            self.timeEdit.setText(selected_dt.toString("yyyy-MM-dd HH:mm:ss"))
            self.timeEdit.blockSignals(False)
            self.select_and_plot_record(closest_index)
            self.parent.status_bar.showMessage(
                f"Загрузка осциллограммы с {selected_dt.toString('dd.MM.yyyy HH:mm:ss')}", 5000
            )

    def on_channel_filter_changed(self, text):
        mask = cdp.pars_cipher_diapasons_to_boolmask(text, 8)[1:]

        for i in range(len(self.channel_boolmask)):
            if i > len(mask) - 1:
                continue
            self.channel_boolmask[i] = mask[i]

        for i in range(len(self.channel_boolmask)):
            if not self.channel_boolmask[i] and type(self.plot_array[i][0]) != int and type(
                    self.plot_array[i][1]) != int:
                self.plot.removeItem(self.plot_array[i][0])
                self.plot_array[i][0] = 0
                self.plot.removeItem(self.plot_array[i][1])
                self.plot_array[i][1] = 0

            if self.channel_boolmask[i] and type(self.plot_array[i][0]) == int:
                plot = self.plot.addPlot(row=i, col=0)
                self.plot_array[i][0] = plot

            if self.channel_boolmask[i] and type(self.plot_array[i][1]) == int:
                plot = self.plot.addPlot(row=i, col=1)
                self.plot_array[i][1] = plot

        self.plot_record(self.current_device, self.colnameList, self.current_data, self.current_rec_num)
        self.on_grid_check_changed(self.gridCheck.isChecked())
        self.on_current_scale_changed(self.currentScaleEdit.text())
        self.on_fixX_check_changed()
        self.on_fixY_check_changed()

    def check_bool_mask(self, i: int) -> bool:
        if i < len(self.channel_boolmask):
            return self.channel_boolmask[i]
        else:
            return False

    def onPlotColumnSliderChanged(self, position):
        labels = ["1:7", "1:3", "3:5", "1:1", "5:3", "3:1", "7:1"]
        scalers = [[1, 1, 3, 1, 5, 3, 7], [7, 3, 5, 1, 3, 1, 1]]
        text = labels[position - 1]
        self.plotColumnRationLabel.setText(text)
        self.plotLayout.setColumnStretchFactor(0, scalers[0][position - 1])
        self.plotLayout.setColumnStretchFactor(1, scalers[1][position - 1])

    def on_freq_range_changed(self, text):
        range = cdp.rangeTextParse(text)
        self.set_current_freq_range(range)
        self.plot_record(self.current_device, self.colnameList, self.current_data, self.current_rec_num)

    def on_grid_check_changed(self, state):
        is_checked = self.gridCheck.isChecked()
        self.show_grid = is_checked

        if is_checked:
            for i in range(len(self.plot_array)):
                if type(self.plot_array[i][0]) != int:
                    self.plot_array[i][0].showGrid(x=False, y=True)
                    self.plot_array[i][1].showGrid(x=True, y=True)
        else:
            for i in range(len(self.plot_array)):
                if type(self.plot_array[i][0]) != int:
                    self.plot_array[i][0].showGrid(x=False, y=False)
                    self.plot_array[i][1].showGrid(x=False, y=False)

    def on_current_scale_changed(self, text):
        limit_set = False
        limit = 0
        blankless = ''.join(text.split())
        if len(blankless) == 0 or not blankless.isdigit():
            limit_set = False
        else:
            limit_set = True
            limit = int(blankless)

        for i in range(3, 6):
            if self.channel_boolmask[i]:
                if limit_set:
                    self.plot_array[i][0].setRange(yRange=[-limit, limit])
                else:
                    self.plot_array[i][0].enableAutoRange()

    def on_fixX_check_changed(self):
        checked = self.fix_X_AxleCheck.isChecked()
        for i in range(len(self.plot_array)):
            if type(self.plot_array[i][0]) != int:
                self.plot_array[i][0].setMouseEnabled(x=not checked)
                self.plot_array[i][1].setMouseEnabled(x=not checked)

    def on_fixY_check_changed(self):
        checked = self.fix_Y_AxleCheck.isChecked()
        for i in range(len(self.plot_array)):
            if type(self.plot_array[i][0]) != int:
                self.plot_array[i][0].setMouseEnabled(y=not checked)
                self.plot_array[i][1].setMouseEnabled(y=not checked)

    def autoScaleBottonPressed(self):
        self.set_current_freq_range((-1, -1))
        self.currentScaleEdit.clear()
        for i in range(len(self.plot_array)):
            if type(self.plot_array[i][0]) != int:
                self.plot_array[i][0].autoRange()
                self.plot_array[i][1].autoRange()

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

    def set_timestamp_from_trends(self, timestamp):
        """
        Handle timestamp received from TrendsSubwindow and trigger record loading.
        """
        if self.current_device and self.colnameList and self.current_current_table_timestamp_list:
            closest_timestamp = min(self.current_current_table_timestamp_list, key=lambda x: abs(x - timestamp))
            closest_index = self.current_current_table_timestamp_list.index(closest_timestamp) + 1
            self.set_current_rec_num(closest_index)
            self.select_and_plot_record(closest_index)
            self.timeEdit.setText(pdb.datetime_from_timestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S'))
            self.parent.status_bar.showMessage(
                f"Загрузка сигнала на {pdb.datetime_from_timestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')}", 5000)