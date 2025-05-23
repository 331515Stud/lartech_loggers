from tabulate import tabulate

def display_all_data(logger_data):
    """Отображение всех записей логгера в табличном виде"""
    if not logger_data or not logger_data['data']:
        print("Нет данных")
        return

    table = [[
        item['timestamp'],
        item['datetime'],
        item['adc_version'],
        item['points'],
        *[item['add_data'][str(i)] for i in range(8)]
    ] for item in logger_data['data']]

    headers = ['Timestamp', 'Дата/Время', 'ADC Version', 'Points'] + [f'add_data_{i}' for i in range(8)]
    print(tabulate(table, headers=headers, tablefmt='grid'))

def display_single_data(data):
    """Отображение одной записи логгера"""
    if not data:
        print("Данные не найдены")
        return

    print(f"\nTimestamp: {data['timestamp']} ({data['datetime']})")
    print(f"ADC Version: {data['adc_version']}")
    print("Доп. данные:")
    for k, v in data['add_data'].items():
        print(f"  add_data_{k}: {v}")
    print(f"Points: {data['points']}")

def display_all_timestamps(logger_data):
    """Вывод всех доступных timestamp'ов по логгеру"""
    if not logger_data or not logger_data['data']:
        print("Нет данных для отображения timestamp'ов")
        return

    timestamps = [str(item['timestamp']) for item in logger_data['data']]
    print(f"\nДоступные Timestamp'ы для логгера {logger_data['imei']} (всего: {len(timestamps)}):")
    for i in range(0, len(timestamps), 5):
        print(', '.join(timestamps[i:i + 5]))

def display_last_5_timestamps(logger_data):
    """Вывод последних 5 timestamp'ов по логгеру"""
    if not logger_data or not logger_data['data']:
        print("Нет данных")
        return

    last_items = logger_data['data'][-5:]
    timestamps = [str(item['timestamp']) for item in last_items]
    print(f"\nПоследние 5 Timestamp'ов логгера {logger_data['imei']}:")
    print(', '.join(timestamps))

def display_timestamps_in_range(logger_data, from_ts, to_ts):
    """Вывод timestamp'ов в диапазоне от и до"""
    if not logger_data or not logger_data['data']:
        print("Нет данных")
        return

    timestamps = [str(item['timestamp']) for item in logger_data['data']
                  if from_ts <= item['timestamp'] <= to_ts]

    if not timestamps:
        print("Нет timestamp'ов в заданном диапазоне")
        return

    print(f"\nTimestamp'ы в диапазоне от {from_ts} до {to_ts} (всего: {len(timestamps)}):")
    for i in range(0, len(timestamps), 5):
        print(', '.join(timestamps[i:i + 5]))

def display_data_by_timestamps_list(logger_data, ts_list):
    """Вывод данных по списку timestamp'ов"""
    if not logger_data or not logger_data['data']:
        print("Нет данных")
        return

    data_map = {item['timestamp']: item for item in logger_data['data']}
    found_any = False

    for ts in ts_list:
        try:
            ts_int = int(ts)
        except ValueError:
            print(f"Неверный формат timestamp: {ts}")
            continue

        item = data_map.get(ts_int)
        if item:
            display_single_data(item)
            found_any = True
        else:
            print(f"Запись с timestamp {ts} не найдена.")

    if not found_any:
        print("Ни одной записи не найдено по переданным timestamp.")

