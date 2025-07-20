import numpy as np
import csv
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QObject, pyqtSignal


class AsyncDataLoader(QObject):
    loaded = pyqtSignal(object, str)  # data, error

    def __init__(self):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=1)

    def load_csv(self, file_path, num_channels):
        future = self.executor.submit(self._load_csv_data, file_path, num_channels)
        future.add_done_callback(self._emit_result)

    def _load_csv_data(self, file_path, num_channels):
        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader)

                required = ['x'] + [f'y{i + 1}' for i in range(num_channels)]
                if not all(col in headers for col in required):
                    return None, f"Missing required columns: {required}"

                data = {col: [] for col in required}
                for row in reader:
                    for header, value in zip(headers, row):
                        if header in data:
                            try:
                                data[header].append(float(value))
                            except ValueError:
                                return None, f"Invalid value: {value}"

                for key in data:
                    data[key] = np.array(data[key])

                return data, None
        except Exception as e:
            return None, f"Error: {str(e)}"

    def _emit_result(self, future):
        data, error = future.result()
        self.loaded.emit(data, error)