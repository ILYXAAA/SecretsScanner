import os
import zipfile

def split_and_zip_file(input_file, lines_per_file=49, zip_name="output_parts.zip"):
    # Читаем исходный файл
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total_lines = len(lines)
    parts = []
    for i in range(0, total_lines, lines_per_file):
        part_lines = lines[i:i + lines_per_file]
        part_filename = f"part_{i // lines_per_file + 1}.txt"
        with open(part_filename, "w", encoding="utf-8") as pf:
            pf.writelines(part_lines)
        parts.append(part_filename)

    # Создаем ZIP-архив
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for part_file in parts:
            zipf.write(part_file)
            os.remove(part_file)  # Удаляем файл после добавления в архив

    print(f"✅ Разбито на {len(parts)} файлов, архивировано в '{zip_name}' и временные файлы удалены.")

if __name__ == "__main__":
    split_and_zip_file("AllSecrets.txt") 
