from PyQt6.QtWidgets import QMainWindow, QMdiArea, QStatusBar, QToolBar, QToolButton
from PyQt6.QtGui import QIcon
from ui.records_view import RecordsViev_subwindow
from ui.signals_view import SignalsView_subwindow
from ui.trends_view import TrendsSubwindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mdi = QMdiArea()
        self.setCentralWidget(self.mdi)
        self.setWindowTitle("Визуализатор для PipeStreamDB v.1.0")
        self._resizing = False  # Flag to prevent recursive resize calls

        # Add status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Add toolbar for layout control
        self.layout_toolbar = QToolBar("Layout Control")
        self.addToolBar(self.layout_toolbar)
        self.layout_mode = "horizontal"  # Default layout mode
        self.layout_button = QToolButton()
        self.layout_button.setText("↔ Горизонтальная")
        self.layout_button.setToolTip("Переключить компоновку окон (горизонтальная/вертикальная)")
        self.layout_button.setIcon(QIcon("./icons/layout_horizontal.png"))
        self.layout_button.setFixedSize(120, 40)  # Increased size for visibility
        self.layout_button.setStyleSheet("""
            QToolButton {
                background-color: #8e2dc5;  /* Bright purple background */
                color: white;
                font-weight: bold;
                border: 2px solid #ffffff;
                border-radius: 8px;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #a13de5;  /* Lighter purple on hover */
            }
            QToolButton:pressed {
                background-color: #6e1da5;  /* Darker purple when pressed */
            }
        """)
        self.layout_toolbar.addWidget(self.layout_button)
        self.layout_toolbar.addSeparator()  # Add some spacing for clarity
        self.layout_button.clicked.connect(self.toggle_layout)

        ico = QIcon("./icons/oscilloscope.png")
        self.setWindowIcon(ico)

        self.RecordsViev_subwindow = RecordsViev_subwindow(self)
        self.SignalsView_subwindow = SignalsView_subwindow(self)
        self.TrendsSubwindow = TrendsSubwindow(self)

        self.RecordsViev_subwindow.setWindowIcon(ico)
        self.SignalsView_subwindow.setWindowIcon(ico)
        self.TrendsSubwindow.setWindowIcon(ico)

        self.mdi.addSubWindow(self.RecordsViev_subwindow)
        self.mdi.addSubWindow(self.SignalsView_subwindow)  # Исправлено: addSubSubWindow -> addSubWindow
        self.mdi.addSubWindow(self.TrendsSubwindow)

        # Connect signals
        self.RecordsViev_subwindow.data_to_plot_signal.connect(self.SignalsView_subwindow.plot_record)
        self.RecordsViev_subwindow.record_list_signal.connect(
            self.SignalsView_subwindow.set_current_table_timestamp_list)
        self.RecordsViev_subwindow.data_to_plot_signal.connect(self.TrendsSubwindow.plot_data_from_signal)

        # Initialize window positions
        self.tile_subwindows()

    def toggle_layout(self):
        """
        Переключает между горизонтальной и вертикальной компоновкой.
        """
        self.layout_mode = "vertical" if self.layout_mode == "horizontal" else "horizontal"
        self.layout_button.setIcon(QIcon(f"./icons/layout_{self.layout_mode}.png"))
        self.layout_button.setText("↕ Вертикальная" if self.layout_mode == "vertical" else "↔ Горизонтальная")
        self.tile_subwindows()

    def tile_subwindows(self, restore_50_50=False, resized_window=None, resize_from=None):
        """
        Tile subwindows based on layout mode, placing TrendsSubwindow in the middle and SignalsView_subwindow on the right in horizontal mode.
        """
        if self._resizing:
            return  # Prevent recursive calls

        self._resizing = True
        try:
            mdi_geometry = self.mdi.geometry()
            total_width = mdi_geometry.width()
            total_height = mdi_geometry.height()

            left_window = self.RecordsViev_subwindow
            middle_window = self.TrendsSubwindow  # TrendsSubwindow посередине
            right_window = self.SignalsView_subwindow  # SignalsView_subwindow справа

            # Ensure all windows are visible
            left_window.setVisible(True)
            left_window.show()
            middle_window.setVisible(True)
            middle_window.show()
            right_window.setVisible(True)
            right_window.show()

            if self.layout_mode == "horizontal":
                # Determine left window width
                if restore_50_50:
                    left_width = total_width // 3  # Equal split for all windows
                else:
                    left_width = left_window.width()
                    if left_window.isMinimized():
                        left_width = max(left_window.minimumWidth(), left_width)
                    elif resize_from == "left":
                        left_width = left_window.width()

                # Ensure minimum width for left window
                left_min_width = left_window.minimumWidth()
                if left_width < left_min_width:
                    left_width = left_min_width

                # Calculate remaining width for middle and right windows
                remaining_width = total_width - left_width

                # Determine widths based on which window was resized
                middle_min_width = middle_window.minimumWidth()
                right_min_width = right_window.minimumWidth()

                if resized_window == middle_window:
                    middle_width = middle_window.width()
                    if middle_width < middle_min_width:
                        middle_width = middle_min_width
                    elif middle_width > remaining_width - right_min_width:
                        middle_width = remaining_width - right_min_width
                    right_width = remaining_width - middle_width
                elif resized_window == right_window:
                    right_width = right_window.width()
                    if right_width < right_min_width:
                        right_width = right_min_width
                    elif right_width > remaining_width - middle_min_width:
                        right_width = remaining_width - middle_min_width
                    middle_width = remaining_width - right_width
                else:
                    # Default: split equally
                    middle_width = remaining_width // 2
                    right_width = remaining_width - middle_width

                # Ensure minimum widths
                if middle_width < middle_min_width:
                    middle_width = middle_min_width
                    right_width = remaining_width - middle_width
                if right_width < right_min_width:
                    right_width = right_min_width
                    middle_width = remaining_width - right_width

                # Adjust left width if total exceeds available space
                if left_width + middle_width + right_width > total_width:
                    left_width = total_width - (middle_width + right_width)

                # Set geometries for horizontal layout
                left_window.setGeometry(0, 0, left_width, total_height)
                middle_window.setGeometry(left_width, 0, middle_width, total_height)
                right_window.setGeometry(left_width + middle_width, 0, right_width, total_height)

            else:  # Vertical layout
                # Determine left window width
                if restore_50_50:
                    left_width = total_width // 3
                else:
                    left_width = left_window.width()
                    if left_window.isMinimized():
                        left_width = max(left_window.minimumWidth(), left_width)
                    elif resize_from == "left":
                        left_width = left_window.width()

                # Ensure minimum width for left window
                left_min_width = left_window.minimumWidth()
                if left_width < left_min_width:
                    left_width = left_min_width

                right_width = total_width - left_width

                # Determine heights based on which window was resized
                middle_min_height = middle_window.minimumHeight()
                right_min_height = right_window.minimumHeight()

                if resized_window == middle_window:
                    middle_height = middle_window.height()
                    if middle_height < middle_min_height:
                        middle_height = middle_min_height
                    elif middle_height > total_height - right_min_height:
                        middle_height = total_height - right_min_height
                    right_height = total_height - middle_height
                elif resized_window == right_window:
                    right_height = right_window.height()
                    if right_height < right_min_height:
                        right_height = right_min_height
                    elif right_height > total_height - middle_min_height:
                        right_height = total_height - middle_min_height
                    middle_height = total_height - right_height
                else:
                    # Default: split equally
                    middle_height = total_height // 2
                    right_height = total_height - middle_height

                # Ensure minimum heights
                if middle_height < middle_min_height:
                    middle_height = middle_min_height
                    right_height = total_height - middle_height
                if right_height < right_min_height:
                    right_height = right_min_height
                    middle_height = total_height - right_height

                # Ensure minimum width for right panel
                right_min_width = max(middle_window.minimumWidth(), right_window.minimumWidth())
                if right_width < right_min_width:
                    right_width = right_min_width
                    left_width = total_width - right_width

                # Set geometries for vertical layout
                left_window.setGeometry(0, 0, left_width, total_height)
                middle_window.setGeometry(left_width, 0, right_width, middle_height)
                right_window.setGeometry(left_width, middle_height, right_width, right_height)
        finally:
            self._resizing = False

    def resizeEvent(self, event):
        """
        Synchronize subwindow resizing with main window.
        """
        self.tile_subwindows(restore_50_50=self.RecordsViev_subwindow.isMinimized())
        QMainWindow.resizeEvent(self, event)