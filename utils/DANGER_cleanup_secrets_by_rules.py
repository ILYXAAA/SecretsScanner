#!/usr/bin/env python3

import re
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Secret
from config import DATABASE_URL

def load_rules(rules_file):
    """Загружает правила из YAML файла"""
    with open(rules_file, 'r', encoding='utf-8') as f:
        rules = yaml.safe_load(f)
    return rules

def check_secret_against_rules(secret_value, rules):
    """Проверяет соответствует ли секрет хотя бы одному правилу"""
    for rule in rules:
        pattern = rule.get('pattern', '')
        if pattern:
            try:
                if re.search(pattern, secret_value, re.IGNORECASE):
                    return True
            except re.error:
                # Пропускаем некорректные регулярки
                continue
    return False

def main():
    # Подключение к БД
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Загружаем правила
        rules = load_rules('rules.yml')
        print(f"Загружено {len(rules)} правил")
        
        # Получаем все секреты
        all_secrets = db.query(Secret).all()
        print(f"Найдено {len(all_secrets)} секретов в БД")
        
        # Проверяем каждый секрет
        to_delete = []
        for secret in all_secrets:
            if not check_secret_against_rules(secret.secret, rules):
                to_delete.append(secret)
        
        print(f"Найдено {len(to_delete)} секретов для удаления")
        
        if to_delete:
            confirm = input("Удалить найденные секреты? (y/N): ")
            if confirm.lower() == 'y':
                for secret in to_delete:
                    db.delete(secret)
                db.commit()
                print(f"Удалено {len(to_delete)} секретов")
            else:
                print("Удаление отменено")
        else:
            print("Секретов для удаления не найдено")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()