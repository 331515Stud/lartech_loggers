import psycopg2
from psycopg2 import sql
from datetime import datetime
from tabulate import tabulate
import base64
import matplotlib.pyplot as plt

class LoggerDB:
    def __init__(self):
        self.connection = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                user="postgres",
                password="1234",
                host="localhost",
                port="5432",
                database="postgres"
            )
            return True
        except psycopg2.Error as e:
            print(f"Connection error: {e}")
            return False

    def close(self):
        if self.connection:
            self.connection.close()

    def get_logger_list(self):
        """Получить список всех логгеров (таблиц) в базе данных"""
        if not self.connect():
            return []

        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                           SELECT table_name
                           FROM information_schema.tables
                           WHERE table_schema = 'public'
                             AND table_name LIKE 'logger\\_%' ESCAPE '\\'
                           ORDER BY table_name
                           """)
            return [row[0] for row in cursor.fetchall()]
        except psycopg2.Error as e:
            print(f"Error fetching logger list: {e}")
            return []
        finally:
            cursor.close()
            self.close()

    def get_all_logger_data(self, imei):
        """Получить все данные для указанного логгера"""
        if not self.connect():
            return None

        table_name = f"logger_{imei}_data"

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                sql.SQL("""
                        SELECT adc_version,
                               add_data_0,
                               add_data_1,
                               add_data_2,
                               add_data_3,
                               add_data_4,
                               add_data_5,
                               add_data_6,
                               add_data_7,
                               points, timestamp
                        FROM {}
                        ORDER BY timestamp
                        """).format(sql.Identifier(table_name))
            )

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            result = []
            for row in data:
                item = {
                    'adc_version': row[0],
                    'add_data': {
                        '0': row[1], '1': row[2], '2': row[3], '3': row[4],
                        '4': row[5], '5': row[6], '6': row[7], '7': row[8]
                    },
                    'points': row[9][1:-1],  # Remove curly braces
                    'timestamp': row[10],
                    'datetime': self._timestamp_to_datetime(row[10])
                }
                result.append(item)

            return {
                'columns': columns,
                'data': result,
                'imei': imei,
                'count': len(result)
            }

        except psycopg2.Error as e:
            print(f"Error fetching data for logger {imei}: {e}")
            return None
        finally:
            cursor.close()
            self.close()

    def get_logger_data_by_timestamp(self, imei, timestamp_ms):
        """Получить данные по приблизительному timestamp (±1 мс)"""
        if not self.connect():
            return None

        table_name = f"logger_{imei}_data"

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                sql.SQL("""
                        SELECT adc_version,
                               add_data_0,
                               add_data_1,
                               add_data_2,
                               add_data_3,
                               add_data_4,
                               add_data_5,
                               add_data_6,
                               add_data_7,
                               points, timestamp
                        FROM {}
                        WHERE timestamp BETWEEN %s
                          AND %s
                        ORDER BY ABS(timestamp - %s)
                            LIMIT 1
                        """).format(sql.Identifier(table_name)),
                [timestamp_ms - 1, timestamp_ms + 1, timestamp_ms]
            )

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'adc_version': row[0],
                'add_data': {
                    '0': row[1], '1': row[2], '2': row[3], '3': row[4],
                    '4': row[5], '5': row[6], '6': row[7], '7': row[8]
                },
                'points': row[9][1:-1],  # Remove curly braces
                'timestamp': row[10],
                'datetime': self._timestamp_to_datetime(row[10])
            }

        except psycopg2.Error as e:
            print(f"Error fetching data for logger {imei}: {e}")
            return None
        finally:
            cursor.close()
            self.close()

    @staticmethod
    def _timestamp_to_datetime(timestamp_ms):
        """Конвертировать timestamp в мс в читаемую дату/время"""
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def base64_to_hex(base64_string):
    """Конвертировать base64 строку в hex"""
    try:
        decoded_bytes = base64.b64decode(base64_string)
        hex_string = ''.join([format(byte, '02X') for byte in decoded_bytes])
        return hex_string
    except Exception as e:
        print(f"Ошибка декодирования base64: {str(e)}")
        return ""

def hex_to_signed_decimal(hex_str):
    """Конвертирует hex строку в знаковое целое"""
    num = int(hex_str, 16)
    if len(hex_str) >= 6 and (num & (1 << (len(hex_str) * 4 - 1))):
        num -= 1 << (len(hex_str) * 4)
    return num

def reverse_bytes_order(bytes_data):
    """Переворачивает порядок байтов в hex строке"""
    return ''.join([bytes_data[i - 2:i] for i in range(len(bytes_data), 0, -2)])

def ADC_Scale(raw, fullScaleVolts, rawMax):
    """Масштабирование ADC значений"""
    result = ((raw >> 2) * fullScaleVolts) / rawMax
    return result

def process_points_data(base64_points):
    """Обработать base64 строку точек и вернуть потоки данных"""
    streams = [[] for _ in range(6)]  # 6 потоков данных
    ADC_full_scale_V = 0.93
    ADC_raw_max = (1 << 21)

    result = base64_to_hex(base64_points)
    if not result:
        return streams

    if len(result) < 6:
        print("Недостаточно данных")
        return streams

    mask = result[:2]
    npoints_hex = result[2:6]
    result = result[6:]
    npoints = int(reverse_bytes_order(npoints_hex), 16)

    print(f"Mask: {mask}, Points: {npoints}")

    while len(result) >= 12:
        for i in range(6):
            value_hex = result[i * 6: (i + 1) * 6]
            if not value_hex:
                break
            reversed_hex = reverse_bytes_order(value_hex)
            value = hex_to_signed_decimal(reversed_hex)
            streams[i].append(value)
        result = result[6 * 6:]

    for j in range(len(streams)):
        for i in range(len(streams[j])):
            streams[j][i] = -(ADC_Scale(streams[j][i], ADC_full_scale_V, ADC_raw_max) * 24000) / 25000

    return streams

def visualize_points(points, title="Визуализация массива точек", xlabel="Индекс", ylabel="Значение"):
    """Визуализировать массив точек"""
    plt.figure(figsize=(12, 6))
    plt.plot(points, marker='', linestyle='-', linewidth=2)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.tight_layout()
    plt.show()
    plt.close()

def display_all_data(logger_data):
    """Вывести все данные в табличном виде"""
    if not logger_data or not logger_data['data']:
        print("Нет данных для отображения")
        return

    print(f"\nВсе данные логгера {logger_data['imei']} (всего записей: {logger_data['count']})")

    table_data = []
    for item in logger_data['data']:
        table_data.append([
            item['timestamp'],
            item['datetime'],
            item['adc_version'],
            item['points'],
            *[item['add_data'][str(i)] for i in range(8)]
        ])

    headers = [
        'Timestamp', 'Дата/Время', 'ADC Version', 'Points',
        'add_data_0', 'add_data_1', 'add_data_2', 'add_data_3',
        'add_data_4', 'add_data_5', 'add_data_6', 'add_data_7'
    ]

    print(tabulate(table_data, headers=headers, tablefmt='grid'))

def display_single_data(data):
    """Вывести данные одной записи"""
    if not data:
        print("Данные не найдены")
        return

    print("\n" + "=" * 50)
    print(f"Данные логгера для временной метки:")
    print(f"Timestamp: {data['timestamp']} ({data['datetime']})")
    print(f"ADC Version: {data['adc_version']}")
    print("\nДополнительные данные:")
    for k, v in data['add_data'].items():
        print(f"  add_data_{k}: {v}")
    print(f"\nPoints: {data['points']}")
    print("=" * 50 + "\n")

def main():
    db = LoggerDB()

    print("Получаем список логгеров...")
    loggers = db.get_logger_list()

    if not loggers:
        print("Логгеры не найдены в базе данных")
        return

    print("\nДоступные логгеры:")
    for i, logger in enumerate(loggers, 1):
        imei = logger.split('_')[1]
        print(f"{i}. {imei}")

    while True:
        try:
            choice = int(input("\nВыберите номер логгера: ")) - 1
            if 0 <= choice < len(loggers):
                selected_logger = loggers[choice]
                imei = selected_logger.split('_')[1]
                break
            print("Некорректный номер, попробуйте снова")
        except ValueError:
            print("Введите число")

    while True:
        print("\nРежимы работы:")
        print("1. Просмотреть все данные логгера")
        print("2. Найти данные по точному timestamp")
        print("3. Визуализировать данные по точному timestamp")
        print("4. Выход")

        try:
            mode = int(input("Выберите режим: "))

            if mode == 1:
                logger_data = db.get_all_logger_data(imei)
                if logger_data:
                    display_all_data(logger_data)
                else:
                    print("Не удалось получить данные")

            elif mode == 2:
                timestamp_input = input("Введите timestamp в миллисекундах: ")
                try:
                    timestamp = int(timestamp_input)
                    data = db.get_logger_data_by_timestamp(imei, timestamp)
                    display_single_data(data)
                except ValueError:
                    print("Ошибка: введите корректное число")

            elif mode == 3:
                timestamp_input = input("Введите timestamp в миллисекундах: ")
                try:
                    timestamp = int(timestamp_input)
                    data = db.get_logger_data_by_timestamp(imei, timestamp)
                    if data:
                        print(f"Визуализация данных для timestamp: {timestamp}")
                        streams = process_points_data(data['points'])
                        for i, stream in enumerate(streams):
                            if stream:  # Only visualize non-empty streams
                                visualize_points(
                                    stream[:2047],
                                    title=f"Stream {i+1} - Logger {imei} - {data['datetime']}",
                                    xlabel="Index",
                                    ylabel="Scaled Value"
                                )
                                print(f"Отображен график для Stream {i+1}")
                    else:
                        print("Данные не найдены")
                except ValueError:
                    print("Ошибка: введите корректное число")

            elif mode == 4:
                break

            else:
                print("Некорректный выбор режима")

        except ValueError:
            print("Введите число от 1 до 4")

if __name__ == "__main__":
    main()