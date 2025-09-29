from PyQt6.QtWidgets import QMdiSubWindow, QTableView, QAbstractItemView, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QLineEdit, QWidget, QHeaderView
from PyQt6.QtGui import QIcon, QAction, QPalette, QColor
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6 import QtCore
from Lib import read_tables_thread as rtt
from Lib import read_last_record_thread as last_rec_thr
from Lib import read_records_list_thread as rrlt
from Lib import pipestreamdbread as pdb
from ui.widgets import ResizableLineEdit

class RecordsTableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._full_data = data  # Store full dataset
        self._data = data  # Displayed (filtered) data

    hheaders = ["Устройство", "Ш, Д", "Число записей", "Первая запись", "Последняя запись"]

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._data[0]) if self._data else 0

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data[index.row()][index.column()])
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.hheaders[section]
        return None

    def insertRow(self, row, row_data, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row)
        self._full_data.insert(row, row_data)
        self._data.insert(row, row_data)
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(count):
            del self._data[row]
        self.endRemoveRows()
        return True

    def filter_by_device(self, search_text):
        """
        Фильтрует таблицу по частичному совпадению в первом столбце (Устройство).
        """
        self.beginResetModel()
        if not search_text:
            self._data = self._full_data.copy()  # Restore full data if search is empty
        else:
            search_text = search_text.lower()
            self._data = [row for row in self._full_data if search_text in row[0].lower()]
        self.endResetModel()

class RecordsViev_subwindow(QMdiSubWindow):
    data_to_plot_signal = QtCore.pyqtSignal(str, list, dict, int)
    record_list_signal = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Выбор источника")

        # Allow resizing to smaller widths
        self.setMinimumWidth(200)  # Reasonable minimum to prevent collapse
        self.is_minimized = False  # Track whether window is minimized to first column

        self.model = RecordsTableModel([["1", "2", "3", "4", "5"]])
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.resizeColumnsToContents()

        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        selection_model = self.table_view.selectionModel()
        selection_model.selectionChanged.connect(self.row_selection_event_handler)

        # Add search field
        self.search_edit = ResizableLineEdit(parent=self)
        self.search_edit.setPlaceholderText("Поиск по устройству")
        self.search_edit.setToolTip("Введите часть имени устройства для фильтрации")
        self.search_edit.setMinimumWidth(150)
        search_icon = QIcon("./icons/search.png")  # Ensure this icon exists
        search_action = QAction(search_icon, "Поиск устройства", self.search_edit)
        self.search_edit.addAction(search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(self.filter_table)

        # Add resize button
        self.resize_button = QPushButton("↔")
        self.resize_button.setToolTip("Изменить размер окна")
        self.resize_button.setFixedWidth(30)
        self.resize_button.clicked.connect(self.toggle_resize)

        # Layout
        main_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()  # Push search field to the left
        main_layout.addLayout(search_layout)
        table_layout = QHBoxLayout()
        table_layout.addWidget(self.table_view)
        table_layout.addWidget(self.resize_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(table_layout)

        self.MainWidget = QWidget()
        self.MainWidget.setLayout(main_layout)
        self.setWidget(self.MainWidget)

        cnt = self.model.rowCount()
        self.model.removeRows(cnt - 1, 1)

        self.ReadTablesThread = rtt.ReadTablesThread()
        self.ReadTablesThread.error_signal.connect(self.on_error_message)
        self.ReadTablesThread.result_signal.connect(self.on_rtt_result_message)
        self.ReadTablesThread.start()

        # Set initial size
        self.resize(300, self.height())

    def apply_theme(self, dark_theme: bool):
        """Apply the current theme to the records view subwindow"""
        palette = QPalette()
        if dark_theme:
            # Dark theme colors
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        else:
            # Light theme colors
            palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(76, 163, 224))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

        self.setPalette(palette)
        self.MainWidget.setPalette(palette)

        # Apply to table view
        self.table_view.setPalette(palette)
        header = self.table_view.horizontalHeader()
        header.setPalette(palette)
        self.table_view.verticalHeader().setPalette(palette)

        # Style for table (alternating rows)
        if dark_theme:
            self.table_view.setStyleSheet("""
                QTableView {
                    background-color: #353535;
                    alternate-background-color: #404040;
                    gridline-color: #555555;
                    selection-background-color: #2a82da;
                    color: white;
                }
                QHeaderView::section {
                    background-color: #404040;
                    color: white;
                    border: 1px solid #555555;
                    padding: 4px;
                }
            """)
        else:
            self.table_view.setStyleSheet("""
                QTableView {
                    background-color: white;
                    alternate-background-color: #f5f5f5;
                    gridline-color: #d0d0d0;
                    selection-background-color: #4c9eff;
                    color: black;
                }
                QHeaderView::section {
                    background-color: #e0e0e0;
                    color: black;
                    border: 1px solid #cccccc;
                    padding: 4px;
                }
            """)

        # Apply to search edit
        if dark_theme:
            self.search_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #404040;
                    color: white;
                    border: 2px solid #555555;
                    border-radius: 4px;
                    padding: 5px;
                }
                QLineEdit:focus {
                    border-color: #2a82da;
                }
            """)
        else:
            self.search_edit.setStyleSheet("""
                QLineEdit {
                    background-color: white;
                    color: black;
                    border: 2px solid #cccccc;
                    border-radius: 4px;
                    padding: 5px;
                }
                QLineEdit:focus {
                    border-color: #4c9eff;
                }
            """)

        # Apply to resize button
        if dark_theme:
            self.resize_button.setStyleSheet("""
                QPushButton {
                    background-color: #404040;
                    color: white;
                    border: 2px solid #555555;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
                QPushButton:pressed {
                    background-color: #303030;
                }
            """)
        else:
            self.resize_button.setStyleSheet("""
                QPushButton {
                    background-color: #e0e0e0;
                    color: black;
                    border: 2px solid #cccccc;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
            """)

    def on_error_message(self, text):
        msgBox = QMessageBox()
        msgBox.setText(f"Ошибка чтения БД: {text}")
        msgBox.exec()

    def on_rtt_result_message(self, result):
        device = result["device"] if "device" in result else "-"
        first_records = result["first_records"] if "first_records" in result else "-"
        last_records = result["last_records"] if "last_records" in result else "-"
        gps_latitude = result["gps_latitude"] if "gps_latitude" in result else "-"
        gps_longitude = result["gps_longitude"] if "gps_longitude" in result else "-"
        record_num = result["record_num"] if "record_num" in result else "-"

        first_records = str(pdb.datetime_from_timestamp(first_records))[:-4] if first_records != "-" else "-"
        last_records = str(pdb.datetime_from_timestamp(last_records))[:-4] if last_records != "-" else "-"

        row = [device, f"{gps_latitude}, {gps_longitude}", record_num, first_records, last_records]
        self.model.insertRow(self.model.rowCount(), row)
        self.table_view.resizeColumnsToContents()
        self.filter_table(self.search_edit.text())  # Reapply filter after adding new row

    def row_selection_event_handler(self, selected, deselected):
        if selected:
            ind = selected.indexes()[0]
            if ind.column() == 0:
                device_name_index = self.model.index(ind.row(), 0)
                device_name = self.model.data(device_name_index)

                self.ReadLastRecordThread = last_rec_thr.ReadLastRecordThread(device_name)
                self.ReadLastRecordThread.error_signal.connect(self.on_error_message)
                self.ReadLastRecordThread.result_signal.connect(self.on_last_rec_message)
                self.ReadLastRecordThread.start()

                self.ReadRecordListThread = rrlt.ReadRecordListThread(device_name)
                self.ReadRecordListThread.error_signal.connect(self.on_error_message)
                self.ReadRecordListThread.result_signal.connect(self.on_rrlt_result_message)
                self.ReadRecordListThread.start()

    def on_rrlt_result_message(self, result_list):
        self.record_list_signal.emit(result_list)

    def on_last_rec_message(self, table_name, column_list, result_dict, rec_num):
        self.data_to_plot_signal.emit(table_name, column_list, result_dict, rec_num)

    def filter_table(self, text):
        """
        Фильтрует таблицу по введенному тексту в поле поиска.
        """
        self.model.filter_by_device(text)
        self.table_view.resizeColumnsToContents()
        # Clear selection if no rows are displayed
        if self.model.rowCount() == 0:
            self.table_view.clearSelection()

    def toggle_resize(self):
        """
        Переключает между минимизацией до ширины первого столбца и восстановлением 50/50 компоновки.
        """
        self.table_view.resizeColumnsToContents()
        first_col_width = self.table_view.columnWidth(0)
        padding = 70  # Учитывает кнопку и декорации
        min_width = max(first_col_width + padding, 200)

        if not self.is_minimized:
            # Минимизировать до ширины первого столбца
            self.setMinimumWidth(min_width)
            self.resize(min_width, self.height())
            self.is_minimized = True
        else:
            # Восстановить 50/50 компоновку
            mdi_width = self.parent.mdi.geometry().width()
            target_width = mdi_width // 3  # Use 1/3 for balanced initial layout
            self.setMinimumWidth(200)  # Reset minimum width
            self.resize(target_width, self.height())
            self.is_minimized = False

        # Обновить позиции окон
        self.parent.tile_subwindows(restore_50_50=not self.is_minimized, resize_from="left")

    def moveEvent(self, event):
        """
        Перемещает оба окна вместе, сохраняя их склеенное состояние.
        """
        if self.is_minimized:
            # Убедиться в минимальной ширине при минимизации
            self.setMinimumWidth(max(self.table_view.columnWidth(0) + 70, 200))
        self.parent.tile_subwindows(restore_50_50=self.is_minimized, resize_from="left")
        super().moveEvent(event)

    def resizeEvent(self, event):
        """
        Корректирует правое окно при изменении размера левого окна.
        """
        self.parent.tile_subwindows(restore_50_50=self.is_minimized, resize_from="left")
        super().resizeEvent(event)
