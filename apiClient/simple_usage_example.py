from SecretScannerClient import SecretsScanner

API_KEY = "ss_live_..."
SCANNER_URL = "http://127.0.0.1:8000/secret_scanner"

Scanner = SecretsScanner(api_token=API_KEY, base_url=SCANNER_URL)

Repository_1 = "https://github.com/ILYXAAA/SecretsScanner"
Commit_1 = "99ab6d5e7e13ae78e777a9345caf6ac1faf16c6d"

Repository_2 = "https://github.com/ILYXAAA/SecretsScanner_service"
Commit_2 = "b63d12986311fc64a36ce44fc68de4f31b243131"

repos = [
    {"repository": Repository_1, "commit": Commit_1},
    {"repository": Repository_2, "commit": Commit_2}
]


### Проверка существует ли проект ###
print("=== Проверка проекта ===")
try:
    project_info = Scanner.check_project(Repository_1)
    if project_info:
        print(f"Проект - Существует: {project_info['exists']}, Имя: {project_info['project_name']}")
    else:
        print(f"Ошибка проверки проекта: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при проверке проекта: {e}")
input("Нажмите для продолжения..")


### Создание проекта ###
print("\n=== Создание проектов ===")
try:
    project_created = Scanner.add_project(Repository_1)
    if project_created:
        print("Проект успешно создан")
    else:
        print(f"Не удалось создать проект: {Scanner.get_last_error()}")

    project_created = Scanner.add_project(Repository_2)
    if project_created:
        print("Второй проект успешно создан")
    else:
        print(f"Не удалось создать второй проект: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при создании проекта: {e}")


### Быстрое сканирование с сохранением отчета ###
print("\n=== Быстрое сканирование ===")
try:
    result = Scanner.quick_scan(Repository_1, Commit_1, save_report=True, report_filename="SecretsScanner_scan.json")
    if result:
        print(f"Сканирование завершено - ID: {result.scan_id}")
        print(f"Статус: {result.status}")
        print(f"Найдено секретов: {result.secret_count}")
    else:
        print(f"Ошибка быстрого сканирования: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при быстром сканировании: {e}")
input("Нажмите для продолжения..")


### Запуск одиночного сканирования с получением scan_id ###
print("\n=== Одиночное сканирование ===")
try:
    scan_id = Scanner.start_scan(Repository_2, Commit_2)
    if scan_id:
        print(f"Сканирование запущено - ID: {scan_id}")
        
        # Проверка статуса
        scan_status = Scanner.get_scan_status(scan_id)
        print(f"Статус сканирования: {scan_status}")
        
    else:
        print(f"Не удалось запустить сканирование: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при одиночном сканировании: {e}")
input("Нажмите для продолжения..")


### Запуск мульти-сканирования с получением scan_ids ###
print("\n=== Мульти-сканирование ===")
try:
    scan_ids = Scanner.start_multi_scan(repos)
    if scan_ids:
        print(f"Мульти-сканирование запущено - {len(scan_ids)} сканирований")
        print(f"Scan IDs: {scan_ids}")
         
    else:
        print(f"Не удалось запустить мульти-сканирование: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при мульти-сканировании: {e}")
input("Нажмите для продолжения..")


### Получение результатов сканирования по scan_id ###
print("\n=== Получение результатов ===")
try:
    if scan_status == "completed":
        result = Scanner.get_scan_results(scan_id)
        if result:
            print(f"Scan ID: {result.scan_id}")
            print(f"Статус: {result.status}")
            print(f"Результаты: найдено {result.secret_count} секретов")
            
            # Показываем первые несколько результатов
            if result.results and len(result.results) > 0:
                print("Первые найденные секреты:")
                for i, secret in enumerate(result.results[:3]):
                    print(f"  {i+1}. Файл: {secret.get('path', 'N/A')}, Строка: {secret.get('line', 'N/A')}")
                
                if len(result.results) > 3:
                    print(f"  ... и еще {len(result.results) - 3} секретов")
        else:
            print(f"Не удалось получить результаты: {Scanner.get_last_error()}")
    else:
        print(f"Сканирование еще не завершено, статус: {scan_status}")
        
except Exception as e:
    print(f"Исключение при получении результатов: {e}")