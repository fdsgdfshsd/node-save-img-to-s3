import os
import sys
import subprocess


def install_requirements():
    # Определяем путь до файла requirements.txt в папке ноды
    current_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_path = os.path.join(current_dir, 'requirements.txt')
    if os.path.exists(requirements_path):
        try:
            print(f"Устанавливаем зависимости из {requirements_path}...")
            # Запускаем установку зависимостей через pip
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', requirements_path])
            print("Зависимости успешно установлены.")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при установке зависимостей: {e}")
    else:
        print("Файл requirements.txt не найден, установка зависимостей пропущена.")


install_requirements()
