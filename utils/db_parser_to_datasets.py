import sqlite3
import os

def parse_secrets_db():
    # Путь к БД
    db_path = "../database/secrets_scanner.db"
    
    # Проверяем существование файла БД
    if not os.path.exists(db_path):
        print(f"Файл БД не найден: {db_path}")
        return
    
    try:
        # Подключение к БД
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Запрос для получения уникальных Confirmed секретов
        cursor.execute("SELECT DISTINCT secret FROM secrets WHERE status = 'Confirmed'")
        confirmed_secrets = cursor.fetchall()
        
        # Запрос для получения уникальных Refuted секретов
        cursor.execute("SELECT DISTINCT secret FROM secrets WHERE status = 'Refuted'")
        refuted_secrets = cursor.fetchall()
        
        # Создание файла с секретами (Confirmed)
        with open("Dataset_Secrets.txt", "w", encoding="utf-8") as f:
            for secret in confirmed_secrets:
                f.write(secret[0] + "\n")
        
        # Создание файла с не-секретами (Refuted)
        with open("Dataset_NonSecrets.txt", "w", encoding="utf-8") as f:
            for secret in refuted_secrets:
                f.write(secret[0] + "\n")
        
        # Статистика
        print(f"Создано файлов:")
        print(f"Dataset_Secrets.txt - {len(confirmed_secrets)} записей")
        print(f"Dataset_NonSecrets.txt - {len(refuted_secrets)} записей")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Ошибка при работе с БД: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    parse_secrets_db()