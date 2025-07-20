#!/usr/bin/env python3
"""
Скрипт для извлечения всех уникальных расширений файлов из БД
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def extract_unique_extensions():
    """Извлекает все уникальные расширения файлов из таблицы secrets"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database URL
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/secrets_scanner.db")
    
    # Connect to database
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    
    try:
        # Получаем все уникальные пути файлов
        with engine.connect() as conn:
            query = text("SELECT DISTINCT path FROM secrets WHERE path IS NOT NULL")
            file_paths = conn.execute(query).fetchall()
        
        extensions = set()
        
        for (path,) in file_paths:
            if path:
                # Получаем только имя файла без папок
                filename = path.split('/')[-1]  # для Linux путей
                filename = filename.split('\\')[-1]  # для Windows путей
                
                if '.' in filename:
                    # Извлекаем расширение (все после последней точки в имени файла)
                    extension = '.' + filename.split('.')[-1].lower()
                    extensions.add(extension)
                else:
                    # Файлы без расширения
                    extensions.add('NO_EXTENSION')
        
        # Сортируем расширения
        sorted_extensions = sorted(extensions)
        
        # Записываем в файл
        with open('utils/unique_extensions.txt', 'w', encoding='utf-8') as f:
            for ext in sorted_extensions:
                f.write(ext + '\n')
        
        print(f"Найдено {len(sorted_extensions)} уникальных расширений")
        print(f"Результат записан в файл: unique_extensions.txt")
        
        # Выводим первые 20 для предварительного просмотра
        print("\nПервые 20 расширений:")
        for ext in sorted_extensions[:20]:
            print(f"  {ext}")
        
        if len(sorted_extensions) > 20:
            print(f"  ... и еще {len(sorted_extensions) - 20}")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    extract_unique_extensions()

if __name__ == "__main__":
    extract_unique_extensions()