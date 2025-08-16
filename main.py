#!/usr/bin/env python3
"""
ИСПРАВЛЕННЫЙ главный запускной файл без конфликтов asyncio
"""

import os
import sys
import time
import signal
import subprocess
import argparse
from pathlib import Path
import multiprocessing as mp

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

def check_requirements():
    """Проверяет наличие всех необходимых файлов"""
    required_files = [
        'config.json',
        'keywords.txt',
        'chats.txt',
        '.env',
        'shared_db.py',
        'app.py',
        'web_server.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ Отсутствуют необходимые файлы:")
        for file in missing_files:
            print(f"   - {file}")
        
        # Создаем недостающие папки
        os.makedirs('templates', exist_ok=True)
        os.makedirs('data/exports', exist_ok=True)
        os.makedirs('data/logs', exist_ok=True)
        os.makedirs('sessions', exist_ok=True)
        
        return False
    
    return True

def check_environment():
    """Проверяет переменные окружения"""
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден")
        return False
    
    # Загружаем .env файл вручную
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if '#' in value:
                        value = value.split('#')[0].strip()
                    os.environ[key.strip()] = value.strip()
    except Exception as e:
        print(f"❌ Ошибка загрузки .env: {e}")
        return False
    
    required_env = ['API_ID', 'API_HASH']
    missing_env = []
    
    for env_var in required_env:
        value = os.getenv(env_var)
        if not value:
            missing_env.append(env_var)
        else:
            masked_value = value[:3] + "..." if len(value) > 3 else "***"
            print(f"   ✅ {env_var}: {masked_value}")
    
    if missing_env:
        print(f"❌ Отсутствуют переменные окружения: {missing_env}")
        return False
    
    return True

def kill_existing_processes():
    """Убивает существующие процессы бота"""
    try:
        # Убиваем процессы по портам
        for port in [8080]:
            try:
                result = subprocess.run(['lsof', '-ti', f':{port}'],
                                      capture_output=True, text=True)
                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            subprocess.run(['kill', '-9', pid], check=False)
                            print(f"🔫 Убит процесс на порту {port}: PID {pid}")
                        except:
                            pass
            except:
                pass
        
        # Убиваем процессы Python с app.py или main.py
        try:
            result = subprocess.run(['pgrep', '-f', 'python.*app.py'],
                                  capture_output=True, text=True)
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], check=False)
                        print(f"🔫 Убит Python процесс: PID {pid}")
                    except:
                        pass
        except:
            pass
            
        time.sleep(2)  # Даем время процессам завершиться
        
    except Exception as e:
        print(f"⚠️ Ошибка при убийстве процессов: {e}")

def cleanup_database():
    """Очищает заблокированную базу данных"""
    try:
        # Удаляем WAL и SHM файлы если есть
        db_files = [
            'data/shared_bot.sqlite-wal',
            'data/shared_bot.sqlite-shm',
            'shared_bot_data.sqlite-wal',
            'shared_bot_data.sqlite-shm',
            'bot_data.sqlite-wal',
            'bot_data.sqlite-shm'
        ]
        
        for db_file in db_files:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"🗑️ Удален файл блокировки: {db_file}")
        
        print("✅ База данных разблокирована")
        
    except Exception as e:
        print(f"⚠️ Ошибка очистки БД: {e}")

def run_telegram_bot_process():
    """Запуск Telegram бота в отдельном процессе"""
    try:
        print("🤖 Запуск Telegram бота в отдельном процессе...")
        
        # Запускаем app.py с аргументом both
        process = subprocess.Popen([
            sys.executable, 'app.py', '--mode', 'both'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        return process
        
    except Exception as e:
        print(f"❌ Ошибка запуска Telegram бота: {e}")
        return None

def run_web_server_process():
    """Запуск веб-сервера в отдельном процессе"""
    try:
        print("🌐 Запуск веб-сервера в отдельном процессе...")
        
        # Запускаем web_server.py
        process = subprocess.Popen([
            sys.executable, 'web_server.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        return process
        
    except Exception as e:
        print(f"❌ Ошибка запуска веб-сервера: {e}")
        return None

def monitor_process(process, name):
    """Мониторинг процесса"""
    while True:
        if process.poll() is not None:
            print(f"⚠️ Процесс {name} завершился с кодом {process.returncode}")
            break
        time.sleep(5)

def run_combined_system():
    """Запуск объединенной системы без конфликтов"""
    print("🚀 ЗАПУСК TELEGRAM BOT SYSTEM (БЕЗ КОНФЛИКТОВ)")
    print("=" * 60)
    
    # Проверяем готовность
    if not check_requirements():
        return
        
    if not check_environment():
        return
    
    # Убиваем существующие процессы
    print("🔫 Убиваю существующие процессы...")
    kill_existing_processes()
    
    # Очищаем заблокированную БД
    print("🗑️ Очищаю блокировки БД...")
    cleanup_database()
    
    print("✅ Все проверки пройдены!")
    print()
    
    # Создаем тестовые данные
    print("🧪 Создание тестовых данных...")
    try:
        subprocess.run([sys.executable, 'simple_debug.py'],
                      timeout=30, check=False)
    except:
        print("⚠️ Не удалось создать тестовые данные")
    
    web_process = None
    telegram_process = None
    
    try:
        # Запускаем веб-сервер
        web_process = run_web_server_process()
        if not web_process:
            print("❌ Не удалось запустить веб-сервер")
            return
        
        print("⏳ Ждем запуска веб-сервера...")
        time.sleep(5)
        
        # Проверяем что веб-сервер запустился
        try:
            import requests
            response = requests.get('http://localhost:8080', timeout=5)
            if response.status_code == 200:
                print("✅ Веб-сервер запущен успешно")
            else:
                print(f"⚠️ Веб-сервер отвечает с кодом {response.status_code}")
        except:
            print("⚠️ Веб-сервер пока недоступен")
        
        # Запускаем Telegram бота
        telegram_process = run_telegram_bot_process()
        if not telegram_process:
            print("❌ Не удалось запустить Telegram бота")
            return
        
        print("🎉 Система запущена!")
        print("📊 Веб-интерфейс: http://localhost:8080")
        print("🤖 Telegram бот: запущен в отдельном процессе")
        print("⏹️  Для остановки нажмите Ctrl+C")
        print("=" * 60)
        
        # Ждем сигнала остановки
        while True:
            time.sleep(1)
            
            # Проверяем состояние процессов
            if web_process and web_process.poll() is not None:
                print("⚠️ Веб-сервер остановился")
                break
                
            if telegram_process and telegram_process.poll() is not None:
                print("⚠️ Telegram бот остановился")
                # Не перезапускаем автоматически
                
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        
    finally:
        print("🔄 Завершение работы компонентов...")
        
        # Останавливаем процессы
        if telegram_process:
            try:
                telegram_process.terminate()
                telegram_process.wait(timeout=10)
                print("✅ Telegram бот остановлен")
            except:
                telegram_process.kill()
                print("🔫 Telegram бот убит принудительно")
                
        if web_process:
            try:
                web_process.terminate()
                web_process.wait(timeout=10)
                print("✅ Веб-сервер остановлен")
            except:
                web_process.kill()
                print("🔫 Веб-сервер убит принудительно")
        
        print("👋 Система остановлена")

def run_telegram_only():
    """Запуск только Telegram бота"""
    print("🤖 Запуск только Telegram бота")
    
    if not check_requirements():
        return
        
    if not check_environment():
        return
    
    cleanup_database()
    
    try:
        subprocess.run([sys.executable, 'app.py', '--mode', 'both'])
    except KeyboardInterrupt:
        print("\n👋 Telegram бот остановлен")

def run_web_only():
    """Запуск только веб-сервера"""
    print("🌐 Запуск только веб-сервера")
    
    if not check_requirements():
        return
    
    cleanup_database()
    
    try:
        subprocess.run([sys.executable, 'web_server.py'])
    except KeyboardInterrupt:
        print("\n👋 Веб-сервер остановлен")

def show_status():
    """Показывает статус системы"""
    print("📊 СТАТУС TELEGRAM BOT SYSTEM")
    print("=" * 60)
    
    # Проверяем файлы
    files_ok = check_requirements()
    env_ok = check_environment()
    
    print(f"📁 Файлы системы: {'✅ OK' if files_ok else '❌ Ошибки'}")
    print(f"🔑 Переменные окружения: {'✅ OK' if env_ok else '❌ Ошибки'}")
    
    # Проверяем процессы
    try:
        result = subprocess.run(['lsof', '-ti', ':8080'],
                              capture_output=True, text=True)
        web_running = bool(result.stdout.strip())
        print(f"🌐 Веб-сервер: {'✅ Запущен' if web_running else '❌ Остановлен'}")
    except:
        print("🌐 Веб-сервер: ❓ Неизвестно")
    
    # Проверяем базу данных
    try:
        import sqlite3
        conn = sqlite3.connect('data/shared_bot.sqlite', timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM leads")
        leads_count = cursor.fetchone()[0]
        conn.close()
        print(f"🗄️  База данных: ✅ OK ({leads_count} лидов)")
    except Exception as e:
        print(f"🗄️  База данных: ❌ Ошибка ({e})")
    
    print("=" * 60)
    
    if files_ok and env_ok:
        print("🎉 Система готова к запуску!")
        print("💡 Используйте: python main.py --mode combined")
    else:
        print("🔧 Устраните ошибки и попробуйте снова")

def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Telegram Bot System - управление лидами",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--mode',
        choices=['combined', 'telegram', 'web', 'status'],
        default='combined',
        help='Режим запуска системы'
    )
    
    args = parser.parse_args()
    
    # Обработка сигналов
    def signal_handler(signum, frame):
        print(f"\n📡 Получен сигнал {signum}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Выполняем действие
    if args.mode == 'combined':
        run_combined_system()
    elif args.mode == 'telegram':
        run_telegram_only()
    elif args.mode == 'web':
        run_web_only()
    elif args.mode == 'status':
        show_status()

if __name__ == '__main__':
    main()
