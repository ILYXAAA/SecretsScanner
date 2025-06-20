import os
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

ENV_PATH = ".env"
load_dotenv(ENV_PATH)

def generate_key(KEY_NAME):
    key = Fernet.generate_key().decode()
    set_key(ENV_PATH, KEY_NAME, key)
    load_dotenv(ENV_PATH, override=True)
    return key

def get_key(KEY_NAME):
    key = os.getenv(KEY_NAME)
    if key is None:
        raise ValueError("Ключ не найден в .env")
    return key

def get_or_create_key(KEY_NAME):
    key = os.getenv(KEY_NAME)
    if key is None:
        key = generate_key(KEY_NAME)
    return key

def encrypt_and_save(text: str, filename: str, key_name):
    key = get_or_create_key(key_name)
    fernet = Fernet(key.encode())
    encrypted = fernet.encrypt(text.encode())

    with open(filename, "wb") as file:
        file.write(encrypted)

def decrypt_from_file(filename: str, key_name: str) -> str:
    key = get_key(key_name)
    fernet = Fernet(key.encode())

    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл {filename} не найден")

    with open(filename, "rb") as file:
        encrypted = file.read()

    decrypted = fernet.decrypt(encrypted)
    return decrypted.decode()

def first_setup():
    print("Мастер первичной настройки login, password")
    print("="*20)
    Path("Auth").mkdir(exist_ok=True)
    filename = "Auth/login.dat"
    key_name = "LOGIN_KEY"
    message = input("Введите логин для учетной записи:")
    encrypt_and_save(text=message, filename=filename, key_name=key_name)

    filename = "Auth/password.dat"
    key_name = "PASSWORD_KEY"
    message = input("Введите пароль для учетной записи:")
    encrypt_and_save(text=message, filename=filename, key_name=key_name)

if __name__ == "__main__":
    print("Мастер первичной настройки login, password")
    print("="*20)
    Path("Auth").mkdir(exist_ok=True)
    filename = "Auth/login.dat"
    key_name = "LOGIN_KEY"
    message = input("Введите логин для учетной записи:")
    encrypt_and_save(text=message, filename=filename, key_name=key_name)

    filename = "Auth/password.dat"
    key_name = "PASSWORD_KEY"
    message = input("Введите пароль для учетной записи:")
    encrypt_and_save(text=message, filename=filename, key_name=key_name)