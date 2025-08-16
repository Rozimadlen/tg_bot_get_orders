import os
import re
import json
import asyncio
from telethon.errors import rpcerrorlist
import logging
from datetime import datetime, timedelta
import argparse
import random
import pandas as pd
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User
import requests
from flask import Flask, jsonify
from flask_socketio import SocketIO, emit
import threading
# Импортируем общую базу данных
from shared_db import db
# Импорт для WebSocket уведомлений
import socketio

# Создаем клиент для отправки уведомлений в веб-интерфейс
sio_client = socketio.AsyncClient()

async def connect_to_web_interface():
    """Подключение к веб-интерфейсу для отправки уведомлений"""
    try:
        await sio_client.connect('http://localhost:8080')
        log.info("🔗 Подключен к веб-интерфейсу")
        return True
    except Exception as e:
        log.warning(f"⚠️ Не удалось подключиться к веб-интерфейсу: {e}")
        return False

async def notify_web_interface(event_type: str, data: dict):
    """Отправка уведомления в веб-интерфейс"""
    try:
        if sio_client.connected:
            await sio_client.emit(event_type, data)
            log.verbose(f"📡 Отправлено в веб: {event_type}")
    except Exception as e:
        log.verbose(f"⚠️ Ошибка отправки в веб: {e}")

# ---------- загрузка окружения ----------
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
FORWARD_TO_ENV = os.getenv("FORWARD_TO", "me")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")



# ---------- конфиг ----------
with open("config.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

DAYS_BACK = int(CFG.get("days_back", 1))
MIN_LENGTH = int(CFG.get("min_length", 1))
KW_FILE = CFG.get("keywords_file", "keywords.txt")
CHATS_FILE = CFG.get("chats_file", "chats.txt")
SAVE_CSV = bool(CFG.get("save_csv", True))
SAVE_JSON = bool(CFG.get("save_json", False))
USE_NATASHA = bool(CFG.get("use_natasha", False))
EXPORT_DIR = CFG.get("export_dir", "data/exports")
LOG_DIR = CFG.get("log_dir", "data/logs")
FORWARD_CFG = CFG.get("forward_to", "env")
VERBOSE_LOGS = bool(CFG.get("verbose_logs", False))
ENABLE_AUTO_REPLY = bool(CFG.get("enable_auto_reply", False))
MAX_REPLIES_PER_DAY = int(CFG.get("max_replies_per_day", 30))
ENABLE_TOGETHER_AI = bool(CFG.get("enable_together_ai", True))

# Более точные настройки времени
HOURS_BACK = int(CFG.get("hours_back", 24))
MAX_MESSAGES_PER_CHAT = int(CFG.get("max_messages_per_chat", 500))
TIME_SEARCH_MODE = CFG.get("time_search_mode", "hours")

os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs("sessions", exist_ok=True)

# ---------- логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "parser.log"), encoding="utf-8")
    ],
)
log = logging.getLogger("tg-scout")

def log_verbose(message):
    """Логирует только если включен verbose режим"""
    if VERBOSE_LOGS:
        log.info(message)

# Вычисляем время поиска
if TIME_SEARCH_MODE == "hours":
    DATE_FROM = datetime.now() - timedelta(hours=HOURS_BACK)
    time_desc = f"{HOURS_BACK} часов"
else:
    DATE_FROM = datetime.now() - timedelta(days=DAYS_BACK)
    time_desc = f"{DAYS_BACK} дней"

log.info(f"⏰ Режим поиска: последние {time_desc}")

# Модели Together.ai
TOGETHER_MODELS = [
    "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
]

# Инициализация Together.ai клиента
together_client = None
if TOGETHER_API_KEY and ENABLE_TOGETHER_AI:
    together_client = True
    log.info("🤖 Together.ai ИИ автоответы включены")
else:
    log.info("💬 Together.ai автоответы отключены")

daily_replies_count = 0
last_reset_date = datetime.now().date()

# Flask приложение для API
api_app = Flask(__name__)
api_app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(api_app, cors_allowed_origins="*")

# ---------- клиент ----------
client = TelegramClient(os.path.join("sessions", "session_one"), API_ID, API_HASH)
FORWARD_TARGET = None

# WebSocket для уведомлений веб-интерфейса
def notify_web_interface(event_type: str, data: dict):
    """Отправляет уведомление в веб-интерфейс"""
    try:
        socketio.emit(event_type, data)
    except Exception as e:
        log.error(f"Ошибка отправки WebSocket уведомления: {e}")

# ---------- NLP: natasha (опционально) ----------
if USE_NATASHA:
    try:
        from natasha import Segmenter, MorphVocab, NewsEmbedding, NewsMorphTagger, Doc
        from razdel import tokenize
        SEGMENTER = Segmenter()
        MORPH_VOCAB = MorphVocab()
        EMB = NewsEmbedding()
        TAGGER = NewsMorphTagger(EMB)
        _LEMMA_CACHE = {}

        def normalize_text(s: str):
            out = []
            for tok in tokenize(s.lower()):
                w = tok.text
                if w in _LEMMA_CACHE:
                    out.append(_LEMMA_CACHE[w]); continue
                doc = Doc(w); doc.segment(SEGMENTER); doc.tag_morph(TAGGER)
                if doc.tokens:
                    t = doc.tokens[0]; t.lemmatize(MORPH_VOCAB)
                    _LEMMA_CACHE[w] = t.lemma
                    out.append(t.lemma)
            return out
    except Exception as e:
        log.warning(f"Natasha не загрузилась ({e}). Перехожу в быстрый режим.")
        USE_NATASHA = False

if not USE_NATASHA:
    def normalize_text(s: str):
        return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9#@_]+", s.lower())

# ---------- ключевые слова ----------
def load_keywords_from_file():
    """Загружает ключевые слова из файла в БД"""
    if not os.path.exists(KW_FILE):
        log.warning(f"Файл с ключами не найден: {KW_FILE}")
        return
    
    with open(KW_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                db.add_keyword(line)
    
    log.info(f"🔋 Ключевые слова загружены из {KW_FILE}")

def kw_hit(text: str) -> bool:
    """
    СТРОГИЙ поиск только по полным фразам из БД
    """
    keywords = db.get_keywords()
    if not keywords:
        log.warning("⚠️ Нет ключевых фраз - пропускаю все сообщения")
        return False
    
    text_lower = text.lower()
    
    # Ищем ТОЛЬКО полные фразы
    for phrase in keywords:
        if phrase in text_lower:
            log.info(f"🎯 НАЙДЕНА ФРАЗА: '{phrase}'")
            return True
    
    return False

def analyze_lead_quality(text: str, sender=None) -> dict:
    """
    Анализирует качество потенциального лида.
    """
    score = 0
    reasons = []
    
    text_lower = text.lower()
    
    # Положительные сигналы для оценки качества
    positive_signals = [
        ("бюджет", 3, "💰 Упоминает бюджет"),
        ("готов платить", 3, "💰 Готов платить"),
        ("плачу", 3, "💰 Готов платить"),
        ("оплачу", 3, "💰 Готов платить"),
        ("срочно", 2, "⚡ Срочная потребность"),
        ("deadline", 2, "📅 Есть дедлайн"),
        ("дедлайн", 2, "📅 Есть дедлайн"),
        ("опытного", 2, "⭐ Ищет опытного специалиста"),
        ("портфолио", 2, "📁 Интересует портфолио"),
        ("примеры работ", 2, "📁 Хочет видеть примеры"),
        ("техническое задание", 2, "📋 Есть ТЗ"),
        ("тз", 1, "📋 Есть ТЗ"),
        ("профессионал", 2, "⭐ Ищет профессионала"),
        ("качественно", 1, "✨ Важно качество"),
        ("быстро", 1, "⚡ Нужно быстро"),
    ]
    
    for signal, points, reason in positive_signals:
        if signal in text_lower:
            score += points
            reasons.append(reason)
    
    # Негативные сигналы (снижают качество)
    negative_signals = [
        ("бесплатно", -5, "🚫 Ищет бесплатно"),
        ("даром", -5, "🚫 Ищет даром"),
        ("без оплаты", -5, "🚫 Без оплаты"),
        ("взаимозачет", -3, "🤝 Взаимозачет"),
        ("процент", -2, "📈 Процент от прибыли"),
        ("стажер", -2, "👶 Ищет стажера"),
        ("новичок", -1, "👶 Ищет новичка"),
        ("дешево", -2, "💸 Ищет дешево"),
        ("недорого", -1, "💸 Ищет недорого"),
    ]
    
    for signal, points, reason in negative_signals:
        if signal in text_lower:
            score += points
            reasons.append(reason)
    
    # Определяем категорию качества
    if score >= 5:
        quality = "🔥 ГОРЯЧИЙ ЛИД"
    elif score >= 2:
        quality = "🟡 ХОРОШИЙ ЛИД"
    elif score >= 0:
        quality = "🟢 ОБЫЧНЫЙ ЛИД"
    else:
        quality = "🔴 НИЗКОЕ КАЧЕСТВО"
    
    return {
        "score": score,
        "quality": quality,
        "reasons": reasons
    }

# Функция генерации ответа с Together.ai
async def generate_together_response(lead_message, lead_quality, sender_name="Клиент"):
    """
    Генерирует персональный ответ с помощью Together.ai
    """
    if not TOGETHER_API_KEY:
        return None
    
    # Определяем тон ответа по качеству лида
    if "ГОРЯЧИЙ" in lead_quality:
        tone = "очень заинтересованно и профессионально"
        urgency = "Это важный клиент!"
    elif "ХОРОШИЙ" in lead_quality:
        tone = "дружелюбно и активно"
        urgency = "Хороший клиент."
    else:
        tone = "вежливо и кратко"
        urgency = "Обычный запрос."
    
    # Создаем промпт специально для DeepSeek
    prompt = f"""Ты профессиональный видеопродюсер отвечаешь клиенту в Telegram {tone}.

СООБЩЕНИЕ КЛИЕНТА: "{lead_message}"

ВАЖНО: Отвечай БЕЗ тегов <think>, БЕЗ размышлений, только готовый ответ!

Напиши короткий ответ на русском языке:
- Поприветствуй клиента
- Покажи понимание его потребности  
- Предложи свою помощь
- Попроси написать в личные сообщения
- Используй 1-2 смодзи
- Максимум 80 слов

Ответ:"""

    try:
        # Пробуем модели по очереди с повторными попытками
        for model_index, model in enumerate(TOGETHER_MODELS, 1):
            log.info(f"🧪 Тестируем модель {model_index}/{len(TOGETHER_MODELS)}: {model}")
            
            # Для каждой модели делаем до 3 попыток
            for attempt in range(1, 4):
                try:
                    log.info(f"📡 Попытка {attempt}/3 для модели {model.split('/')[-1]}")
                    
                    # Используем Chat Completions API
                    response = requests.post(
                        "https://api.together.xyz/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {TOGETHER_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ],
                            "max_tokens": 150,
                            "temperature": 0.7,
                            "top_p": 0.9,
                            "stop": ["\n\n", "Клиент:", "Пользователь:"]
                        },
                        timeout=30
                    )
                    
                    log.info(f"📊 Статус ответа: {response.status_code}")
                            
                    if response.status_code == 200:
                        result = response.json()
                        ai_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    
                        if ai_text and len(ai_text) > 10:
                            log.info(f"🧠 Полный ответ DeepSeek: {ai_text[:200]}...")
                        
                            # Простая очистка - только убираем теги размышлений
                            import re
                            clean_response = ai_text.strip()
                        
                            # Убираем только теги <think>...</think>
                            clean_response = re.sub(r'<think>.*?</think>', '', clean_response, flags=re.DOTALL)
                        
                            # Убираем лишние пробелы и переносы
                            clean_response = re.sub(r'\n+', ' ', clean_response).strip()
                            clean_response = re.sub(r'\s+', ' ', clean_response).strip()
                        
                            # Убираем "Ответ:" если есть
                            if "Ответ:" in clean_response:
                                clean_response = clean_response.split("Ответ:")[-1].strip()
                        
                            if len(clean_response.strip()) > 10:
                                log.info(f"✅ Очищенный ответ: {clean_response}")
                                return clean_response
                            else:
                                log.warning(f"⚠️ После очистки ответ пустой, используем fallback")
                                return generate_fallback_response(lead_message, lead_quality)
                        else:
                            log.warning(f"⚠️ Получен пустой ответ")
                            break  # Переходим к следующей модели
                        
                    elif response.status_code == 429:
                        # Rate limit - ждем и пробуем еще раз
                        wait_time = attempt * 15  # 15, 30, 45 секунд
                        log.warning(f"⏰ Rate limit для {model.split('/')[-1]}, ждем {wait_time} секунд...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    elif response.status_code == 401:
                        log.error("🔐 Неверный API ключ Together.ai")
                        return generate_fallback_response(lead_message, lead_quality)
                        
                    elif response.status_code == 404:
                        log.warning(f"⚠ Модель {model} недоступна (404)")
                        break
                        
                    else:
                        log.warning(f"⚠️ Ошибка {response.status_code} для модели {model}")
                        if attempt < 3:
                            log.info(f"⏳ Ждем 10 секунд перед повтором...")
                            await asyncio.sleep(10)
                            continue
                        else:
                            break
                        
                except requests.exceptions.Timeout:
                    log.warning(f"⏰ Тайм-аут для модели {model}, попытка {attempt}/3")
                    if attempt < 3:
                        await asyncio.sleep(5)
                        continue
                    else:
                        break
                        
                except Exception as model_error:
                    log.warning(f"⚠ Ошибка с моделью {model}, попытка {attempt}/3: {model_error}")
                    if attempt < 3:
                        await asyncio.sleep(5)
                        continue
                    else:
                        break
            
            # Пауза между моделями
            if model_index < len(TOGETHER_MODELS):
                log.info(f"⏳ Пауза 5 секунд перед следующей моделью...")
                await asyncio.sleep(5)
        
        # Если все модели не сработали
        log.warning("⚠ Все модели Together.ai недоступны после всех попыток")
        log.info("🔄 Используем резервный ответ")
        return generate_fallback_response(lead_message, lead_quality)
        
    except Exception as e:
        log.error(f"💥 Общая ошибка Together.ai API: {e}")
        return generate_fallback_response(lead_message, lead_quality)

# Резервная функция для генерации ответов
def generate_fallback_response(lead_message, lead_quality):
    """
    Генерирует базовый ответ если ИИ недоступен
    """
    templates = {
        "🔥 ГОРЯЧИЙ": [
            "Привет! Вижу вам нужен видеопродюсер 🎬 У меня большой опыт в этой сфере. Напишите мне в личные сообщения - обсудим ваш проект детально!",
            "Здравствуйте! Отлично, что ищете профессионала для видео 🎥 Готов помочь с вашим проектом. Пишите в ЛС - обговорим все детали!"
        ],
        "🟡 ХОРОШИЙ": [
            "Привет! Могу помочь с видеопродакшеном 🎬 Есть портфолио и опыт. Напишите в личку - обсудим ваши задачи!",
            "Здравствуйте! Вижу нужен видеопродюсер 🎥 С удовольствием помогу. Пишите в ЛС!"
        ],
        "default": [
            "Привет! Помогу с видеопроизводством 🎬 Напишите в личные сообщения для обсуждения деталей.",
            "Здравствуйте! Готов помочь с вашим видеопроектом 🎥 Пишите в ЛС!"
        ]
    }
    
    # Выбираем шаблон по качеству лида
    if "ГОРЯЧИЙ" in lead_quality:
        options = templates["🔥 ГОРЯЧИЙ"]
    elif "ХОРОШИЙ" in lead_quality:
        options = templates["🟡 ХОРОШИЙ"]
    else:
        options = templates["default"]
    
    return random.choice(options)

# Функция отправки автоответа
async def send_auto_reply_together(src_entity, original_message, lead_analysis):
    """
    Отправляет автоматический ответ с Together.ai ИИ
    """
    global daily_replies_count, last_reset_date
    
    # Сброс счетчика в новый день
    today = datetime.now().date()
    if today != last_reset_date:
        daily_replies_count = 0
        last_reset_date = today
    
    # Проверка лимита ответов
    if daily_replies_count >= MAX_REPLIES_PER_DAY:
        log.warning(f"⚠️ Достигнут дневной лимит ответов: {MAX_REPLIES_PER_DAY}")
        return
    
    # Проверка рабочих часов (9-21)
    current_hour = datetime.now().hour
    if not (9 <= current_hour <= 21):
        log.info(f"😴 Вне рабочих часов ({current_hour}:00). Пропускаем автоответ.")
        return
    
    # Проверка качества лида - не отвечаем на плохие
    if lead_analysis['score'] < 0:
        log.info(f"🚫 Низкое качество лида ({lead_analysis['score']}). Пропускаем автоответ.")
        return
    
    # Генерируем ответ
    sender = await original_message.get_sender()
    sender_name = "Клиент"
    if isinstance(sender, User) and sender.first_name:
        sender_name = sender.first_name
    
    ai_response = await generate_together_response(
        original_message.text or "",
        lead_analysis['quality'],
        sender_name
    )
    
    if not ai_response:
        log.error("⚠ Не удалось сгенерировать ответ")
        return
    
    # Определяем задержку по качеству лида
    if lead_analysis['score'] >= 5:  # Горячий лид
        delay_min, delay_max = 300, 900  # 5-15 минут
        priority = "🔥 ГОРЯЧИЙ"
    elif lead_analysis['score'] >= 2:  # Хороший лид
        delay_min, delay_max = 900, 1800  # 15-30 минут
        priority = "🟡 ХОРОШИЙ"
    else:  # Обычный лид
        delay_min, delay_max = 1800, 3600  # 30-60 минут
        priority = "🟢 ОБЫЧНЫЙ"
    
    delay_seconds = random.randint(delay_min, delay_max)
    delay_minutes = delay_seconds // 60
    
    log.info(f"🤖 Together.ai автоответ для {priority} лида через {delay_minutes} мин")
    log.info(f"📝 Ответ: {ai_response[:100]}...")
    
    # Ждем перед отправкой
    await asyncio.sleep(delay_seconds)
    
    try:
        # Отправляем ответ в тот же чат где найден лид
        await client.send_message(src_entity, ai_response)
        daily_replies_count += 1
        
        log.info(f"✅ Together.ai автоответ отправлен! ({daily_replies_count}/{MAX_REPLIES_PER_DAY} за день)")
        
        # Уведомляем себя об отправленном ответе
        if FORWARD_TARGET:
            notification = f"🤖 **TOGETHER.AI АВТООТВЕТ**\n\n📝 **Ответ:** {ai_response}\n\n📊 **Качество лида:** {lead_analysis['quality']}\n📈 **Счетчик:** {daily_replies_count}/{MAX_REPLIES_PER_DAY}"
            try:
                await client.send_message(FORWARD_TARGET, notification, parse_mode='markdown')
            except:
                await client.send_message(FORWARD_TARGET, notification)
                
    except Exception as e:
        log.error(f"⚠ Ошибка отправки Together.ai автоответа: {e}")

# Функция проверки времени сообщения
def is_message_in_timeframe(message_date) -> bool:
    """
    Проверяет, попадает ли сообщение в нужный временной интервал
    """
    # Убираем timezone для корректного сравнения
    msg_time = message_date.replace(tzinfo=None) if message_date.tzinfo else message_date
    current_time = datetime.now()
    
    # Проверяем, что сообщение не из будущего (на всякий случай)
    if msg_time > current_time:
        return False
    
    # Проверяем, что сообщение в нужном диапазоне
    return msg_time >= DATE_FROM

# ---------- хелперы ----------
async def resolve_chat(raw: str):
    """
    Возвращает entity группы/чата. Каналы (broadcast=True) пропускаем.
    Улучшенная обработка разных форматов ссылок.
    """
    try:
        # Различные форматы ссылок
        if raw.startswith('https://t.me/'):
            # Обрабатываем разные типы ссылок
            if '/+' in raw:
                # Приватная ссылка: https://t.me/+R_KxUQG5hYo5ZjAy
                invite_hash = raw.split('/+')[1]
                try:
                    entity = await client.get_entity(f"https://t.me/+{invite_hash}")
                except Exception as e:
                    log.warning(f"⚠️ Не удалось получить чат по приватной ссылке {raw}: {e}")
                    return None
            else:
                # Публичная ссылка: https://t.me/jetlagchat
                username = raw.split('/')[-1]
                entity = await client.get_entity(username)
        elif raw.startswith('@'):
            # @jetlagchat
            entity = await client.get_entity(raw)
        elif raw.lstrip("-").isdigit():
            # -1001234567890
            entity = await client.get_entity(int(raw))
        else:
            # jetlagchat
            entity = await client.get_entity(raw)
        
        # Проверяем тип entity
        if isinstance(entity, Channel) and getattr(entity, "broadcast", False):
            log.info(f"⚠️ Пропуск канала (broadcast): {raw}")
            return None  # канал — не чат/группа
        
        if isinstance(entity, Chat):
            return entity
        
        if isinstance(entity, Channel) and getattr(entity, "megagroup", False):
            return entity
            
        log.info(f"⚠️ Неподдерживаемый тип entity: {type(entity)} для {raw}")
        return None
        
    except Exception as e:
        log.error(f"Не удалось получить {raw}: {e}")
        return None

async def resolve_forward_target():
    """
    Цель пересылки: 'me' / @username / numeric id.
    Если в config 'forward_to' стоит 'env' — берём из FORWARD_TO_ENV.
    """
    target = FORWARD_CFG
    if str(target).lower() == "env":
        target = FORWARD_TO_ENV or "me"
    if str(target).lower() == "me":
        return "me"
    try:
        return await client.get_entity(int(target)) if str(target).lstrip("-").isdigit() else await client.get_entity(str(target))
    except Exception as e:
        log.error(f"Не смог получить цель пересылки {target}: {e}")
        return "me"

def format_target_display(target):
    """
    Красиво форматирует цель пересылки для логов
    """
    if target == "me":
        return "Сохраненные сообщения"
    
    if hasattr(target, 'first_name'):
        name_parts = []
        if target.first_name:
            name_parts.append(target.first_name)
        if hasattr(target, 'last_name') and target.last_name:
            name_parts.append(target.last_name)
        
        name = " ".join(name_parts) if name_parts else "Пользователь"
        
        if hasattr(target, 'username') and target.username:
            return f"{name} (@{target.username})"
        else:
            return f"{name} (ID: {target.id})"
    
    if hasattr(target, 'title'):
        return f"Чат: {target.title}"
    
    return "Неизвестная цель"

# НАЙДИТЕ ЭТУ ФУНКЦИЮ В app.py И ЗАМЕНИТЕ НА ИСПРАВЛЕННУЮ ВЕРСИЮ:

async def forward_with_card(src_entity, message):
    """
    ИСПРАВЛЕННАЯ версия с защитой от блокировки БД и правильным сохранением
    """
    global FORWARD_TARGET
    if FORWARD_TARGET is None:
        FORWARD_TARGET = await resolve_forward_target()
        log.info(f"➡️ Пересылаю в: {format_target_display(FORWARD_TARGET)}")
    
    try:
        sender = await message.get_sender()
        display = "unknown"
        clickable_username = None
        
        if isinstance(sender, User):
            if sender.username:
                display = f"@{sender.username}"
                clickable_username = f"@{sender.username}"
            else:
                first_name = sender.first_name or ""
                last_name = sender.last_name or ""
                full_name = " ".join([first_name, last_name]).strip()
                
                if full_name:
                    display = f"{full_name}"
                    clickable_username = f"[{full_name}](tg://user?id={sender.id})"
                else:
                    display = f"id:{sender.id}"
                    clickable_username = f"[Пользователь](tg://user?id={sender.id})"
        
        chat_title = getattr(src_entity, "title", "chat")
        dt = message.date.strftime("%Y-%m-%d %H:%M:%S")
        
        msg_link = None
        try:
            if isinstance(src_entity, Channel) and getattr(src_entity, "username", None):
                msg_link = f"https://t.me/{src_entity.username}/{message.id}"
        except Exception:
            pass
        
        # Анализ качества лида
        lead_analysis = analyze_lead_quality(message.text or "", sender)
        
        # 💾 ИСПРАВЛЕННОЕ СОХРАНЕНИЕ В БД
        try:
            # Получаем chat_source с fallback
            chat_source = getattr(src_entity, "username", None)
            if not chat_source:
                chat_source = f"chat_{src_entity.id}" if hasattr(src_entity, 'id') else "unknown_chat"
            
            # Убираем @ если есть
            if chat_source.startswith('@'):
                chat_source = chat_source[1:]
            
            print(f"💾 Сохраняю лид: chat_source='{chat_source}', sender='{display}'")
            
            lead_id = db.add_lead(
                chat_source=chat_source,  # ИСПРАВЛЕНО: убеждаемся что не None
                sender_id=message.sender_id,
                sender_name=display,
                message_text=message.text or "",
                quality_score=lead_analysis['score'],
                quality_label=lead_analysis['quality'],
                quality_reasons=lead_analysis['reasons'],
                chat_name=chat_title
            )
            
            print(f"✅ Лид сохранен в БД с ID: {lead_id}")
            
        except Exception as save_error:
            print(f"❌ Ошибка сохранения лида в БД: {save_error}")
            print(f"📋 Данные: chat_source='{chat_source}', sender_id={message.sender_id}")
            # Продолжаем выполнение даже если сохранение не удалось
            lead_id = 0
        
        # 📡 УВЕДОМЛЯЕМ ВЕБ-ИНТЕРФЕЙС О НОВОМ ЛИДЕ
        try:
            await notify_web_interface('new_lead', {
                'id': lead_id,
                'chat_source': chat_title,
                'sender_name': display,
                'message_text': message.text or "",
                'quality_label': lead_analysis['quality'],
                'quality_score': lead_analysis['score'],
                'timestamp': dt,
                'responded': False
            })
        except Exception as notify_error:
            print(f"⚠️ Ошибка уведомления веб-интерфейса: {notify_error}")
        
        # Добавляем информацию об автоответе в карточку
        auto_reply_status = "🤖 Together.ai автоответ запланирован" if ENABLE_AUTO_REPLY and lead_analysis['score'] >= 0 else "💬 Ручной ответ"
        
        # Строим карточку
        card_lines = [
            f"👀 **Найдено в:** \n {chat_title}",
            f"⏰ **{dt}**",
            f"✏️ **Автор:** \n {clickable_username or display}",
            f"🎯 **Качество:** \n {lead_analysis['quality']} (очки: {lead_analysis['score']})",
            f"🤖 **Статус:** {auto_reply_status}",
            f"🆔 **ID лида:** {lead_id}"
        ]
        
        if lead_analysis['reasons']:
            card_lines.append(f"📊 **Причины:** \n {', '.join(lead_analysis['reasons'])}")
        
        if msg_link:
            card_lines.append(f"🔗 {msg_link}")
        
        card_text = "\n".join(card_lines)
        
        # Отправляем карточку
        try:
            await client.send_message(FORWARD_TARGET, card_text, parse_mode='markdown')
        except Exception as e:
            try:
                card_text_plain = card_text.replace('[', '').replace('](tg://user?id=', ' (ID: ').replace(')', ')')
                await client.send_message(FORWARD_TARGET, card_text_plain)
            except Exception as e2:
                print(f"❌ Ошибка отправки карточки: {e2}")
        
        # Пересылаем оригинал
        try:
            await client.forward_messages(FORWARD_TARGET, message)
        except Exception as e:
            log.error(f"Ошибка пересылки: {e}")
        
        # 🤖 ЗАПУСКАЕМ АВТООТВЕТ (в фоне)
        if ENABLE_AUTO_REPLY and together_client:
            log.info("🤖 Автоответы включены - отправляю ответ")
            asyncio.create_task(send_auto_reply_together(src_entity, message, lead_analysis))
        else:
            log.info("💬 Автоответы отключены - только сохраняю лид")
        
        # Пауза между лидами
        delay = random.randint(3, 15)
        log.info(f"⏳ Пауза {delay} сек до следующего лида")
        await asyncio.sleep(delay)
        
    except Exception as e:
        print(f"❌ Критическая ошибка в forward_with_card: {e}")
        import traceback
        traceback.print_exc()

# API эндпоинты для веб-интерфейса
@api_app.route('/api/status')
def get_status():
    """API: Получить статус бота"""
    stats = db.get_leads_stats()
    return jsonify({
        'telegram_connected': client.is_connected() if client else False,
        'ai_connected': bool(TOGETHER_API_KEY and ENABLE_TOGETHER_AI),
        'monitoring_active': True,  # Пока всегда активен
        **stats
    })

@api_app.route('/api/leads')
def get_leads():
    """API: Получить список лидов"""
    limit = request.args.get('limit', 20, type=int)
    leads = db.get_recent_leads(limit)
    return jsonify(leads)

# ---------- режимы ----------
async def scan_history():
    """Сканирует историю чатов и ищет лиды"""
    load_keywords_from_file()  # Загружаем ключевые слова из файла
    
    all_msgs = []
    with open(CHATS_FILE, "r", encoding="utf-8") as f:
        raw_chats = [l.strip() for l in f if l.strip()]

    now = datetime.now()
    log.info(f"🕐 Поиск сообщений с {DATE_FROM.strftime('%Y-%m-%d %H:%M:%S')} по {now.strftime('%Y-%m-%d %H:%M:%S')}")

    for raw in raw_chats:
        entity = await resolve_chat(raw)
        if not entity:
            log.info(f"⭕ Пропуск (не чат/группа): {raw}")
            continue

        title = getattr(entity, "title", str(raw))
        log.info(f"🔎 Парсим: {title}")
        checked = passed = in_timeframe = too_old_count = 0

        try:
            async for m in client.iter_messages(entity, limit=MAX_MESSAGES_PER_CHAT):
                checked += 1
                
                # Проверяем время сообщения
                if not is_message_in_timeframe(m.date):
                    too_old_count += 1
                    # Если подряд 10 сообщений слишком старые - останавливаемся
                    if too_old_count >= 10:
                        log.info(f"ℹ️ Достигнута граница времени в {title}")
                        break
                    continue
                else:
                    too_old_count = 0  # сбрасываем счетчик
                    in_timeframe += 1
                
                txt = m.text or ""
                if len(txt) < MIN_LENGTH:
                    continue
                if not kw_hit(txt):
                    continue

                all_msgs.append({
                    "chat": title,
                    "chat_ref": raw,
                    "id": m.id,
                    "date": m.date.strftime("%Y-%m-%d %H:%M:%S"),
                    "sender_id": m.sender_id,
                    "text": txt[:200]  # ограничиваем длину для CSV
                })
                passed += 1

                # Сразу пересылаем
                await forward_with_card(entity, m)
                
        except Exception as e:
            log.error(f"Ошибка при парсинге {title}: {e}")
            continue

        log.info(f"✅ {title}: проверено {checked}, в периоде {in_timeframe}, найдено {passed}")

    if not all_msgs:
        log.warning("⚠️ Ничего не найдено по заданным условиям")
        return

    # Сохраняем результаты
    df = pd.DataFrame(all_msgs).drop_duplicates(subset=["text"])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if SAVE_CSV:
        csv_path = os.path.join(EXPORT_DIR, f"leads_{ts}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        log.info(f"💾 CSV сохранен: {csv_path}")
    
    if SAVE_JSON:
        json_path = os.path.join(EXPORT_DIR, f"leads_{ts}.json")
        df.to_json(json_path, orient="records", force_ascii=False, indent=2)
        log.info(f"💾 JSON сохранен: {json_path}")
    
    log.info(f"📊 Итого найдено {len(df)} уникальных лидов за {time_desc}")

async def watch():
    """Мониторинг новых сообщений в реальном времени"""
    load_keywords_from_file()  # Загружаем ключевые слова из файла
    
    with open(CHATS_FILE, "r", encoding="utf-8") as f:
        raw_chats = [l.strip() for l in f if l.strip()]

    for raw in raw_chats:
        entity = await resolve_chat(raw)
        if not entity:
            continue
        title = getattr(entity, "title", str(raw))

        # фикс late-binding: прокидываем значения в дефолты
        @client.on(events.NewMessage(chats=entity))
        async def _handler(event, _entity=entity, _title=title):
            txt = event.message.message or ""
            if len(txt) < MIN_LENGTH or not kw_hit(txt):
                return
            log.info(f"📡 {_title}: {txt[:140].replace(chr(10), ' ')}")
            await forward_with_card(_entity, event.message)
            
async def ensure_client_connected():
    """Убеждаемся что клиент подключен"""
    try:
        if not client.is_connected():
            log.info("🔌 Подключение к Telegram...")
            await client.start()
            
            # Проверяем подключение
            me = await client.get_me()
            log.info(f"✅ Подключен как: {me.first_name} (@{me.username})")
            return True
        else:
            log.info("✅ Telegram уже подключен")
            return True
    except Exception as e:
        log.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

        
async def main(mode: str):
    log.info("🚀 Запуск Telegram Scout")
    log.info(f"📋 Режим: {mode}")
    
    # Убеждаемся в подключении
    if not await ensure_client_connected():
        log.error("❌ Не удалось подключиться к Telegram")
        return
    
    # 🔗 ПОДКЛЮЧАЕМСЯ К TELEGRAM СНАЧАЛА
    if not client.is_connected():
        log.info("🔌 Подключение к Telegram...")
        await client.start()
        log.info("✅ Подключен к Telegram")
    
    if mode in ("scan", "both"):
        log.info("🔍 Начинаю поиск лидов...")
        await scan_history()
        if mode == "scan":
            log.info("✅ Сканирование завершено")
            return
    
    if mode in ("watch", "both"):
        log.info("👁️ Запускаю мониторинг новых сообщений...")
        await watch()
        log.info("🚀 Мониторинг активен (Ctrl+C для остановки)")
        await client.run_until_disconnected()

def run_telegram_bot():
    """Запуск Telegram бота в отдельном потоке"""
    try:
        with client:
            client.loop.run_until_complete(main("both"))
    except KeyboardInterrupt:
        log.info("👋 Остановка по команде пользователя")
    except Exception as e:
        log.error(f"⚠ Критическая ошибка: {e}")

def run_api_server():
    """Запуск API сервера"""
    socketio.run(api_app, host='0.0.0.0', port=8080, debug=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram scout via personal account")
    parser.add_argument("--mode",
                       choices=["scan", "watch", "both", "api"],
                       default="both",
                       help="Режим работы бота")
    args = parser.parse_args()
    
    if args.mode == "api":
        # Только API сервер
        run_api_server()
    else:
        # Только Telegram бот
        run_telegram_bot()
