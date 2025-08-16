# 🚀 Telegram Bot System - Инструкция по установке

## 📋 Что нужно сделать для запуска

### 1. Переместить файлы в правильные места

```bash
# Создать папку templates (если её нет)
mkdir -p templates

# Переместить dashboard.html в templates
mv dashboard.html templates/dashboard.html

# Создать необходимые папки
mkdir -p data/exports
mkdir -p data/logs  
mkdir -p sessions
```

### 2. Создать новые файлы

Создайте эти файлы в корневой папке проекта:

- `shared_db.py` - общая база данных
- `improved_app.py` - улучшенный Telegram бот  
- `simplified_web_server.py` - упрощенный веб-сервер
- `main.py` - главный запускной файл

### 3. Обновить старые файлы

**Замените старый `app.py` на `improved_app.py`** или добавьте в `app.py`:

```python
# В начало файла добавить:
from shared_db import db

# В функции forward_with_card добавить сохранение в БД:
lead_id = db.add_lead(
    chat_source=getattr(src_entity, "username", str(src_entity.id)),
    chat_name=chat_title,
    sender_id=message.sender_id,
    sender_name=display,
    message_text=message.text or "",
    quality_score=lead_analysis['score'],
    quality_label=lead_analysis['quality'],
    quality_reasons=lead_analysis['reasons']
)
```

### 4. Проверить переменные окружения в .env

```env
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
TOGETHER_API_KEY=your_together_ai_key
FORWARD_TO=me
```

## 🎯 Варианты запуска

### Вариант 1: Полная система (Рекомендуется)
```bash
python main.py --mode combined
```
**Что запускается:**
- ✅ Telegram бот (сканирование + мониторинг)
- ✅ Веб-интерфейс (http://localhost:8080)
- ✅ Общая база данных
- ✅ WebSocket для реального времени

### Вариант 2: Только Telegram бот
```bash
python main.py --mode telegram
```

### Вариант 3: Только веб-интерфейс
```bash
python main.py --mode web
```

### Вариант 4: Проверка системы
```bash
python main.py --mode status
```

## 🔧 Проверка готовности системы

Запустите проверку:
```bash
python main.py --mode status
```

Вы увидите статус всех компонентов:
```
📊 СТАТУС TELEGRAM BOT SYSTEM
============================================================
📁 Файлы системы: ✅ OK
🔑 Переменные окружения: ✅ OK  
🗄️ База данных: ✅ OK (15 лидов)
⚙️ Конфигурация: ✅ OK
🔑 Ключевые слова: ✅ OK (67 фраз)
💬 Источники чатов: ✅ OK (2 чата)
============================================================
🎉 Система готова к запуску!
```

## 🛠️ Устранение проблем

### Проблема: "Файлы системы: ❌ Ошибки"

**Решение:**
```bash
# Проверьте наличие всех файлов:
ls -la shared_db.py improved_app.py simplified_web_server.py main.py
ls -la templates/dashboard.html
ls -la config.json keywords.txt chats.txt .env

# Если dashboard.html в корне:
mv dashboard.html templates/

# Если нет папки templates:
mkdir templates
```

### Проблема: "Переменные окружения: ❌ Ошибки"

**Решение:**
```bash
# Проверьте .env файл:
cat .env

# Должно содержать:
API_ID=12345678
API_HASH=your_hash_here
TOGETHER_API_KEY=your_key_here
FORWARD_TO=me
```

### Проблема: "База данных: ❌ Ошибка"

**Решение:**
```bash
# Проверьте права доступа:
chmod 755 data/
touch data/shared_bot.sqlite

# Или удалите и пересоздайте:
rm -f data/shared_bot.sqlite
python -c "from shared_db import db; print('БД создана')"
```

### Проблема: Порт 8080 занят

**Решение 1 - Измените порт в simplified_web_server.py:**
```python
# В конце файла замените:
socketio.run(app, host='0.0.0.0', port=8081, debug=True)  # был 8080
```

**Решение 2 - Освободите порт:**
```bash
# Найдите процесс на порту 8080:
lsof -i :8080

# Завершите процесс:
kill -9 PID_ПРОЦЕССА
```

## 📱 Настройка Telegram API

1. Перейдите на https://my.telegram.org/apps
2. Войдите в аккаунт
3. Создайте новое приложение
4. Скопируйте `API_ID` и `API_HASH`
5. Добавьте в `.env` файл

## 🤖 Настройка Together.ai

1. Регистрация на https://together.ai/
2. Получите API ключ
3. Добавьте в `.env`:
```env
TOGETHER_API_KEY=your_together_api_key_here
```

## 📊 Структура проекта после установки

```
telegram-bot-system/
├── main.py                    # 🚀 Главный запускной файл
├── shared_db.py              # 🗄️ Общая база данных
├── improved_app.py           # 🤖 Улучшенный Telegram бот
├── simplified_web_server.py  # 🌐 Веб-сервер
├── app.py                    # 📱 Старый бот (можно удалить)
├── web_server.py            # 🌐 Старый веб-сервер (можно удалить)
├── config.json              # ⚙️ Конфигурация
├── keywords.txt             # 🔑 Ключевые слова
├── chats.txt               # 💬 Источники чатов
├── .env                    # 🔐 Переменные окружения
├── templates/
│   └── dashboard.html      # 📊 Веб-интерфейс
├── data/
│   ├── shared_bot.sqlite   # 🗄️ База данных
│   ├── exports/           # 📁 Экспорты
│   └── logs/             # 📝 Логи
└── sessions/             # 🔐 Сессии Telegram
```

## 🎯 Режимы работы

### 1. Полная система (combined)
- **Что:** Telegram бот + Веб-интерфейс
- **Порты:** 8080 (веб-интерфейс)
- **Команда:** `python main.py --mode combined`

### 2. Только бот (telegram)  
- **Что:** Только Telegram функционал
- **Порты:** Нет
- **Команда:** `python main.py --mode telegram`

### 3. Только веб (web)
- **Что:** Только веб-интерфейс
- **Порты:** 8080
- **Команда:** `python main.py --mode web`

## 🔄 Миграция с старой версии

Если у вас уже была старая версия:

1. **Сохраните данные:**
```bash
cp keywords.txt keywords_backup.txt
cp chats.txt chats_backup.txt
cp config.json config_backup.json
```

2. **Обновите файлы:**
- Создайте новые файлы из артефактов
- Переместите `dashboard.html` в `templates/`

3. **Проверьте работу:**
```bash
python main.py --mode status
```

4. **Запустите систему:**
```bash
python main.py --mode combined
```

## 🆘 Если что-то не работает

### Полная переустановка:

```bash
# 1. Остановите все процессы
pkill -f "python.*main.py"
pkill -f "python.*app.py"

# 2. Очистите временные файлы
rm -rf data/shared_bot.sqlite
rm -rf sessions/

# 3. Пересоздайте структуру
mkdir -p templates data/exports data/logs sessions

# 4. Переместите файлы
mv dashboard.html templates/ 2>/dev/null || true

# 5. Проверьте систему
python main.py --mode status

# 6. Запустите
python main.py --mode combined
```

## 🎉 Успешный запуск

Если все работает правильно, вы увидите:

```
🚀 ЗАПУСК TELEGRAM BOT SYSTEM
============================================================
✅ Все проверки пройдены!

🌐 Запуск веб-сервера...
🤖 Запуск Telegram бота...
🎉 Система запущена!
📊 Веб-интерфейс: http://localhost:8080
🤖 Telegram бот: активен
⏹️ Для остановки нажмите Ctrl+C
============================================================
```

Откройте браузер и перейдите на http://localhost:8080 - вы увидите рабочий дашборд!

## 🔗 Полезные команды

```bash
# Проверка статуса
python main.py --mode status

# Полный запуск
python main.py --mode combined

# Только сканирование (без веб-интерфейса)
python main.py --mode telegram

# Только веб-интерфейс (без Telegram)  
python main.py --mode web

# Просмотр логов
tail -f data/logs/parser.log

# Просмотр базы данных
sqlite3 data/shared_bot.sqlite ".tables"
```
