# 🗄️ Команды миграций базы данных

## Основные команды

### 📋 Просмотр статуса миграций
```bash
python migrate.py status
```
Показывает список всех миграций и их статус (применена ✅ / ожидает ❌).

### 🔍 Проверка консистентности
```bash
python migrate.py check
```
Проверяет соответствие между файлами миграций и записями в БД:
- ⚠️ Orphaned миграции - есть запись в БД, но файл удален
- 📋 Pending миграции - есть файл, но не применена

### ⬆️ Применение миграций
```bash
# Применить все ожидающие миграции
python migrate.py migrate

# Применить миграции до определенной версии
python migrate.py migrate 003
```

### ⬇️ Откат миграций
```bash
# Откатить до версии 002 (удалит 003, 004, etc.)
python migrate.py rollback 002
```

## Создание новых миграций

### 🎯 Интерактивный режим (рекомендуется)
```bash
python migrate.py create
```
Запускает пошаговый мастер создания миграции:
- ➕ Создание новых таблиц
- 🔧 Добавление колонок к существующим таблицам  
- 🔍 Создание индексов
- ⚙️ Произвольные SQL-операции

### 📝 Простой режим
```bash
python migrate.py create "Описание миграции"
```
Создает файл миграции с базовым шаблоном для ручного заполнения.

## Примеры использования

### Создание новой таблицы
```bash
python migrate.py create
# Выбрать "1. Add/modify table" → "1. Create new table"
# Ввести название и колонки с типами данных
```

### Добавление колонки
```bash
python migrate.py create  
# Выбрать "1. Add/modify table" → "2. Modify existing table"
# Выбрать таблицу из списка и добавить новые колонки
```

### Создание индекса
```bash
python migrate.py create
# Выбрать "2. Add index"
# Указать название индекса, таблицу и колонки
```

## Управление записями миграций

### ✅ Пометить миграцию как примененную
```bash
python migrate.py mark 005 --description "Manually applied"
```
Добавляет запись в таблицу `schema_migrations` без выполнения миграции.

### ❌ Убрать отметку о применении
```bash
python migrate.py unmark 005
```
Удаляет запись из таблицы `schema_migrations` (миграция станет "ожидающей").

## Проблемы и решения

### 🚨 Удален файл миграции, но запись в БД осталась
```bash
# 1. Проверить консистентность
python migrate.py check

# 2. Удалить orphaned записи
python migrate.py unmark 005
```

### 🔧 Нужно пропустить проблемную миграцию
```bash
# Пометить как применённую без выполнения
python migrate.py mark 005 --description "Skipped due to manual application"
```

### 📁 Восстановление после сбоя
```bash
# 1. Проверить что сломано
python migrate.py check

# 2. Убрать отметки с частично примененных миграций
python migrate.py unmark 005

# 3. Применить заново
python migrate.py migrate
```

```
migrations/
├── 001_initial_schema.py      # Базовые индексы
├── 002_add_user_tracking.py   # Поля пользователей  
├── 003_add_confidence_field.py # Поле confidence
├── 004_add_multi_scans.py     # Таблица multi_scans
└── 005_your_new_migration.py  # Ваша новая миграция
```

## Безопасность

- ✅ Миграции проверяют существование объектов перед изменением
- ✅ Поддержка отката через функции `downgrade()`
- ✅ Совместимость с SQLite, PostgreSQL, MySQL
- ✅ Автоматическое применение при запуске приложения
- ⚠️ SQLite не поддерживает удаление колонок при откате

## Полезные советы

- 📋 Всегда проверяйте статус перед применением: `python migrate.py status`
- 💾 Делайте бэкап БД перед применением миграций в продакшене