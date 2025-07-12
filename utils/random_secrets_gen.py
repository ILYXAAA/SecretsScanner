import random
import string
import os
import zipfile
import math

# Константы
TOTAL_SECRETS = 50_000
SECRETS_PER_FILE = 49
secret_keys = ["password", "api_key", "APIkey", "Creds", "Passwd", "token", "secret", "access_key", "key", "auth"]

# Генерация случайной строки
def random_string(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# Генерация "ключ=значение"
def generate_secret():
    key = random.choice(secret_keys)
    value = random_string(random.randint(12, 32))
    return f"{key}={value}"

# Генерация имени файла
def random_filename():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + ".txt"

# Список созданных файлов
created_files = []

# Вычисление общего количества нужных файлов
num_full_files = TOTAL_SECRETS // SECRETS_PER_FILE
remaining_secrets = TOTAL_SECRETS % SECRETS_PER_FILE

file_counts = [SECRETS_PER_FILE] * num_full_files
if remaining_secrets:
    file_counts.append(remaining_secrets)

# Создание файлов
for secrets_in_file in file_counts:
    filename = random_filename()
    created_files.append(filename)
    with open(filename, 'w') as f:
        for _ in range(secrets_in_file):
            f.write(generate_secret() + '\n')

# Архивация и удаление
with zipfile.ZipFile('my_files.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
    for file in created_files:
        zipf.write(file)
        os.remove(file)

print(f"✅ Готово: создано {len(created_files)} файлов, все упакованы в my_files.zip и оригиналы удалены.")
