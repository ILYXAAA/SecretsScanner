from SecretScannerClient import SecretsScanner

API_KEY = "ss_live_..."
SCANNER_URL = "http://127.0.0.1:8000/secret_scanner"

Scanner = SecretsScanner(api_token=API_KEY, base_url=SCANNER_URL)

# Примеры для Azure DevOps
# Базовая ссылка на репозиторий
Repository_1_Base = "http://server/collection/project/_git/repo"

# Ссылки с ref в URL (рекомендуемый способ)
Repository_1_Branch = "http://server/collection/project/_git/repo?version=GBmain"
Repository_1_Tag = "http://server/collection/project/_git/repo?version=GTv1.0.0"
Repository_1_Commit = "http://server/collection/project/_git/repo?version=GCabc123def456"

# Пример для Devzone
Repository_2_Base = "https://git.devzone.local/group/project"
Repository_2_Branch = "https://git.devzone.local/group/project?version=GBdevelop"

# Для мульти-сканирования можно использовать разные форматы
repos = [
    {"repository": Repository_1_Branch},  # Ссылка с ref в URL
    {"repository": Repository_2_Base, "ref_type": "Branch", "ref": "main"},  # Base URL с ref_type и ref
    {"repository": Repository_1_Base, "commit": "abc123def456"}  # Legacy формат (deprecated)
]
# ref_type - Commit/Branch/Tag

### Проверка существует ли проект ###
print("=== Проверка проекта ===")
try:
    # Можно использовать базовую ссылку или ссылку с ref (ref будет проигнорирован)
    project_info = Scanner.check_project(Repository_1_Base)
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
    # Используйте базовую ссылку (ref будет проигнорирован)
    project_created = Scanner.add_project(Repository_1_Base)
    if project_created:
        print("Проект успешно создан")
    else:
        print(f"Не удалось создать проект: {Scanner.get_last_error()}")

    project_created = Scanner.add_project(Repository_2_Base)
    if project_created:
        print("Второй проект успешно создан")
    else:
        print(f"Не удалось создать второй проект: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при создании проекта: {e}")


### Быстрое сканирование с сохранением отчета ###
print("\n=== Быстрое сканирование ===")
print("Пример 1: Сканирование ветки через URL с ref")
try:
    result = Scanner.quick_scan(
        Repository_1_Branch, 
        save_report=True, 
        report_filename="scan_branch.json"
    )
    if result:
        print(f"Сканирование завершено - ID: {result.scan_id}")
        print(f"Статус: {result.status}")
        print(f"Найдено секретов: {result.secret_count}")
    else:
        print(f"Ошибка быстрого сканирования: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при быстром сканировании: {e}")

print("\nПример 2: Сканирование тега через base URL с ref_type и ref")
try:
    result = Scanner.quick_scan(
        Repository_1_Base,
        ref_type="Tag",
        ref="v1.0.0",
        save_report=True,
        report_filename="scan_tag.json"
    )
    if result:
        print(f"Сканирование тега завершено - ID: {result.scan_id}")
        print(f"Найдено секретов: {result.secret_count}")
    else:
        print(f"Ошибка: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение: {e}")

print("\nПример 3: Сканирование коммита (legacy формат, deprecated)")
try:
    result = Scanner.quick_scan(
        Repository_1_Base,
        commit="abc123def456",
        save_report=True,
        report_filename="scan_commit.json"
    )
    if result:
        print(f"Сканирование коммита завершено - ID: {result.scan_id}")
        print(f"Найдено секретов: {result.secret_count}")
    else:
        print(f"Ошибка: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение: {e}")

input("Нажмите для продолжения..")


### Запуск одиночного сканирования с получением scan_id ###
print("\n=== Одиночное сканирование ===")
try:
    # Пример: сканирование ветки через URL с ref
    scan_id = Scanner.start_scan(Repository_2_Branch)
    if scan_id:
        print(f"Сканирование запущено - ID: {scan_id}")
        
        # Проверка статуса
        scan_status = Scanner.get_scan_status(scan_id)
        print(f"Статус сканирования: {scan_status}")
        
    else:
        print(f"Не удалось запустить сканирование: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение при одиночном сканировании: {e}")

print("\nПример: сканирование через base URL с ref_type и ref")
try:
    scan_id = Scanner.start_scan(
        Repository_1_Base,
        ref_type="Branch",
        ref="develop"
    )
    if scan_id:
        print(f"Сканирование ветки запущено - ID: {scan_id}")
        scan_status = Scanner.get_scan_status(scan_id)
        print(f"Статус: {scan_status}")
    else:
        print(f"Ошибка: {Scanner.get_last_error()}")
except Exception as e:
    print(f"Исключение: {e}")

input("Нажмите для продолжения..")


### Запуск мульти-сканирования с получением scan_ids ###
print("\n=== Мульти-сканирование ===")
print("Пример с разными форматами ref:")
multi_repos = [
    {"repository": Repository_1_Branch},  # URL с ref
    {"repository": Repository_2_Base, "ref_type": "Tag", "ref": "v2.0.0"},  # Base URL с ref_type и ref
    {"repository": Repository_1_Commit}  # URL с коммитом
]
try:
    scan_ids = Scanner.start_multi_scan(multi_repos)
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
    # Используем scan_id из предыдущего примера
    if 'scan_id' in locals() and scan_id:
        scan_status = Scanner.get_scan_status(scan_id)
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
    else:
        print("Нет активного scan_id для проверки результатов")
        
except Exception as e:
    print(f"Исключение при получении результатов: {e}")

print("\n=== Справка по форматам ссылок ===")
print("""
Поддерживаемые форматы ссылок для Azure DevOps и Devzone:

1. URL с ref (рекомендуется):
   - Ветка: http://server/collection/project/_git/repo?version=GBbranch_name
   - Тег:   http://server/collection/project/_git/repo?version=GTtag_name
   - Коммит: http://server/collection/project/_git/repo?version=GCcommit_hash
   - Коммит: http://server/collection/project/_git/repo/commit/commit_hash

2. Base URL с ref_type и ref:
   - repository="http://server/collection/project/_git/repo"
   - ref_type="Branch" или "Tag" или "Commit"
   - ref="branch_name" или "tag_name" или "commit_hash"

3. Legacy формат (deprecated):
   - repository="http://server/collection/project/_git/repo"
   - commit="commit_hash"

Для Devzone:
   - https://git.devzone.local/group/project?version=GBbranch
   - git@git.devzone.local:group/project.git (автоматически конвертируется)
""")