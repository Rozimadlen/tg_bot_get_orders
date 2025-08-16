#!/usr/bin/env python3
"""
Скрипт для принудительного перезапуска системы
"""

import os
import subprocess
import time
import signal
import sys

def kill_all_processes():
    """Убивает все связанные процессы"""
    print("🔫 Убиваю все процессы...")
    
    commands = [
        # Убиваем Python процессы
        "pkill -f 'python.*app.py'",
        "pkill -f 'python.*main.py'",
        "pkill -f 'python.*web_server.py'",
        
        # Освобождаем порт 8080
        "lsof -ti:8080 | xargs kill -9 2>/dev/null || true",
        
        # Убиваем процессы по имени
        "pkill -f 'telegram'",
        "pkill -f 'bot'",
    ]
    
    for cmd in commands:
        try:
            subprocess.run(cmd, shell=True, check=False)
        except:
            pass
    
    print("⏳ Ждем завершения процессов...")
    time.sleep(3)

def cleanup_database():
    """Очищает блокировки БД"""
    print("🗑️ Очистка блокировок БД...")
    
    # Файлы блокировки SQLite
    lock_files = [
        'data/shared_bot.sqlite-wal',
        'data/shared_bot.sqlite-shm',
        'shared_bot_data.sqlite-wal',
        'shared_bot_data.sqlite-shm',
        'bot_data.sqlite-wal',
        'bot_data.sqlite-shm'
    ]
    
    for lock_file in lock_files:
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
                print(f"  ✅ Удален: {lock_file}")
        except Exception as e:
            print(f"  ⚠️ Не удалось удалить {lock_file}: {e}")

def create_folders():
    """Создает необходимые папки"""
    print("📁 Создание папок...")
    
    folders = [
        'data',
        'data/exports',
        'data/logs',
        'templates',
        'sessions'
    ]
    
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"  ✅ {folder}")

def check_dashboard_html():
    """Проверяет dashboard.html"""
    print("📄 Проверка dashboard.html...")
    
    if os.path.exists('dashboard.html') and not os.path.exists('templates/dashboard.html'):
        import shutil
        shutil.move('dashboard.html', 'templates/dashboard.html')
        print("  ✅ dashboard.html перемещен в templates/")
    elif os.path.exists('templates/dashboard.html'):
        print("  ✅ templates/dashboard.html существует")
    else:
        print("  ❌ dashboard.html не найден!")
        return False
    
    return True

def restart_system():
    """Перезапускает систему"""
    print("🚀 ПРИНУДИТЕЛЬНЫЙ ПЕРЕЗАПУСК СИСТЕМЫ")
    print("=" * 50)
    
    # Шаг 1: Убиваем процессы
    kill_all_processes()
    
    # Шаг 2: Очищаем БД
    cleanup_database()
    
    # Шаг 3: Создаем папки
    create_folders()
    
    # Шаг 4: Проверяем dashboard.html
    if not check_dashboard_html():
        print("❌ Невозможно продолжить без dashboard.html")
        return False
    
    # Шаг 5: Создаем тестовые данные
    print("🧪 Создание тестовых данных...")
    try:
        result = subprocess.run([sys.executable, 'simple_debug.py'],
                              timeout=30, capture_output=True, text=True)
        if result.returncode == 0:
            print("  ✅ Тестовые данные созданы")
        else:
            print(f"  ⚠️ Ошибка создания тестовых данных: {result.stderr}")
    except Exception as e:
        print(f"  ⚠️ Не удалось создать тестовые данные: {e}")
    
    # Шаг 6: Запускаем систему
    print("\n🚀 Запуск системы...")
    try:
        subprocess.run([sys.executable, 'main.py', '--mode', 'combined'])
    except KeyboardInterrupt:
        print("\n🛑 Система остановлена пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
    
    return True

if __name__ == "__main__":
    restart_system()
