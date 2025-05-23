from db.logger_db import LoggerDB
from utils.processing import process_points_data
from visualization.plotter import visualize_points
from interface.display import *

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

    logger_data = None  # Кэшировать для повторного использования

    while True:

        print("\nРежимы работы:")
        print("1. Просмотреть все данные логгера")
        print("2. Найти данные по точному timestamp")
        print("3. Вывести данные по списку timestamp")
        print("4. Визуализировать данные по точному timestamp")
        print("5. Перейти к выводу timestamp'ов")
        print("6. Вернуться к выбору логгера")
        print("7. Выход")

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
                try:
                    ts_input = input("Введите список timestamp (через запятую): ")
                    ts_list = [int(ts.strip()) for ts in ts_input.split(',')]
                    logger_data = db.get_all_logger_data(imei)
                    display_data_by_timestamps_list(logger_data, ts_list)
                except ValueError:
                    print("Ошибка: введите корректные числа через запятую")
            elif mode == 4:
                timestamp_input = input("Введите timestamp в миллисекундах: ")
                try:
                    timestamp = int(timestamp_input)
                    data = db.get_logger_data_by_timestamp(imei, timestamp)
                    if data:
                        print(f"Визуализация данных для timestamp: {timestamp}")
                        streams = process_points_data(data['points'])
                        for i, stream in enumerate(streams):
                            if stream:
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

            elif mode == 5:
                print("Режим вывода:")
                print("1. Показать все timestamp'ы логгера ")
                print("2. Показать последние 5 timestamp'ов логгера")
                print("3. Показать записи timestamp'ов в выбранном промежутке")
                print("4. Выход")
                try:
                    mode1 = int(input("Выберете режим вывода: "))
                    if mode1 == 1:
                        if not logger_data:
                            logger_data = db.get_all_logger_data(imei)
                        display_all_timestamps(logger_data)

                    elif mode1 == 2:
                        logger_data = db.get_all_logger_data(imei)
                        display_last_5_timestamps(logger_data)
                    elif mode1 == 3:
                        logger_data = db.get_all_logger_data(imei)
                        start_ts = int(input("Введите стартовый timestamp в мс: "))
                        end_ts = int(input("Введите конечный timestamp в мс: "))

                        display_timestamps_in_range(logger_data, start_ts, end_ts)
                    elif mode1 == 4:
                        print("")
                except ValueError:
                    print("Введите число от 1 до 4")
            elif mode == 6:
                return main()  # Перезапустить выбор логгера

            elif mode == 7:
                break

            else:
                print("Некорректный выбор режима")

        except ValueError:
            print("Введите число от 1 до 7")




if __name__ == "__main__":
    main()
