import psycopg2
from psycopg2 import sql
from datetime import datetime

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
        if not self.connect():
            return []

        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'logger\\_%' ESCAPE '\\'
                ORDER BY table_name
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            self.close()

    def get_all_logger_data(self, imei):
        if not self.connect():
            return None

        table_name = f"logger_{imei}_data"
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                sql.SQL("""
                    SELECT adc_version, add_data_0, add_data_1, add_data_2,
                           add_data_3, add_data_4, add_data_5, add_data_6,
                           add_data_7, points, timestamp
                    FROM {}
                    ORDER BY timestamp
                """).format(sql.Identifier(table_name))
            )
            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()
            result = [{
                'adc_version': r[0],
                'add_data': {str(i): r[i + 1] for i in range(8)},
                'points': r[9][1:-1],
                'timestamp': r[10],
                'datetime': self._timestamp_to_datetime(r[10])
            } for r in data]

            return {
                'columns': columns,
                'data': result,
                'imei': imei,
                'count': len(result)
            }

        finally:
            cursor.close()
            self.close()

    def get_logger_data_by_timestamp(self, imei, timestamp_ms):
        if not self.connect():
            return None

        table_name = f"logger_{imei}_data"
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                sql.SQL("""
                    SELECT adc_version, add_data_0, add_data_1, add_data_2,
                           add_data_3, add_data_4, add_data_5, add_data_6,
                           add_data_7, points, timestamp
                    FROM {}
                    WHERE timestamp BETWEEN %s AND %s
                    ORDER BY ABS(timestamp - %s)
                    LIMIT 1
                """).format(sql.Identifier(table_name)),
                [timestamp_ms - 1, timestamp_ms + 1, timestamp_ms]
            )
            row = cursor.fetchone()
            if row:
                return {
                    'adc_version': row[0],
                    'add_data': {str(i): row[i + 1] for i in range(8)},
                    'points': row[9][1:-1],
                    'timestamp': row[10],
                    'datetime': self._timestamp_to_datetime(row[10])
                }
        finally:
            cursor.close()
            self.close()

    @staticmethod
    def _timestamp_to_datetime(timestamp_ms):
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
