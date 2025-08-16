import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Импортируем общую базу данных
from shared_db import db

# Создаем Flask приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Веб-маршруты
@app.route('/')
def dashboard():
    """Главная страница с дашбордом"""
    return render_template('dashboard.html')

@app.route('/api/status')
def get_status():
    """API: Получить статус бота"""
    stats = db.get_leads_stats()
    return jsonify({
        'telegram_connected': True,  # Можно проверить статус бота
        'ai_connected': bool(os.getenv("TOGETHER_API_KEY")),
        'monitoring_active': True,
        **stats
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    """API: Управление настройками бота"""
    if request.method == 'POST':
        data = request.json
        # Здесь можно сохранить настройки в БД
        print(f"🔧 Настройки обновлены: {data}")
        return jsonify({'status': 'success', 'settings': data})
    
    # Возвращаем текущие настройки (из config.json)
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
        return jsonify(settings)
    except FileNotFoundError:
        return jsonify({})

@app.route('/api/leads')
def get_leads():
    """API: Получить список лидов"""
    limit = request.args.get('limit', 20, type=int)
    leads = db.get_recent_leads(limit)
    return jsonify(leads)

@app.route('/api/keywords', methods=['GET', 'POST', 'DELETE'])
def manage_keywords():
    """API: Управление ключевыми словами"""
    if request.method == 'POST':
        # Добавить новое ключевое слово
        data = request.json
        phrase = data.get('phrase', '').strip().lower()
        
        if phrase:
            success = db.add_keyword(phrase)
            if success:
                return jsonify({'status': 'success', 'message': 'Ключевое слово добавлено'})
            else:
                return jsonify({'status': 'error', 'message': 'Такое ключевое слово уже существует'})
        
        return jsonify({'status': 'error', 'message': 'Пустое ключевое слово'})
    
    elif request.method == 'DELETE':
        # Удалить ключевое слово
        phrase = request.args.get('phrase')
        success = db.remove_keyword(phrase)
        if success:
            return jsonify({'status': 'success', 'message': 'Ключевое слово удалено'})
        else:
            return jsonify({'status': 'error', 'message': 'Ключевое слово не найдено'})
    
    # Получить все ключевые слова
    keywords = db.get_keywords()
    return jsonify(keywords)

@app.route('/api/test-keyword', methods=['POST'])
def test_keyword():
    """API: Тестирование ключевых слов"""
    data = request.json
    message = data.get('message', '')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Сообщение не может быть пустым'})
    
    # Тестируем совпадение
    keywords = db.get_keywords()
    hit = False
    text_lower = message.lower()
    
    for phrase in keywords:
        if phrase in text_lower:
            hit = True
            break
    
    # Анализируем качество (упрощенная версия)
    quality = analyze_lead_quality_simple(message)
    
    return jsonify({
        'status': 'success',
        'hit': hit,
        'quality': quality,
        'message': 'Совпадение найдено' if hit else 'Совпадений не найдено'
    })

def analyze_lead_quality_simple(text: str) -> dict:
    """Упрощенный анализ качества лида"""
    score = 0
    reasons = []
    text_lower = text.lower()
    
    # Положительные сигналы
    positive = [
        ("бюджет", 3, "💰 Упоминает бюджет"),
        ("срочно", 2, "⚡ Срочная потребность"),
        ("опытного", 2, "⭐ Ищет опытного"),
        ("профессионал", 2, "⭐ Ищет профессионала"),
    ]
    
    for signal, points, reason in positive:
        if signal in text_lower:
            score += points
            reasons.append(reason)
    
    # Негативные сигналы
    negative = [
        ("бесплатно", -5, "🚫 Ищет бесплатно"),
        ("дешево", -2, "💸 Ищет дешево"),
        ("стажер", -2, "👶 Ищет стажера"),
    ]
    
    for signal, points, reason in negative:
        if signal in text_lower:
            score += points
            reasons.append(reason)
    
    # Определяем качество
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

@app.route('/api/chat-sources', methods=['GET', 'POST', 'DELETE'])
def manage_chat_sources():
    """API: Управление источниками чатов"""
    if request.method == 'POST':
        # Добавить новый источник
        data = request.json
        chat_id = data.get('chat_id', '').strip()
        chat_name = data.get('chat_name', chat_id)
        
        if chat_id:
            success = db.add_chat_source(chat_id, chat_name)
            if success:
                return jsonify({'status': 'success', 'message': 'Источник чата добавлен'})
            else:
                return jsonify({'status': 'error', 'message': 'Такой источник уже существует'})
        
        return jsonify({'status': 'error', 'message': 'Пустой ID чата'})
    
    elif request.method == 'DELETE':
        # Удалить источник
        chat_id = request.args.get('chat_id')
        success = db.remove_chat_source(chat_id)
        if success:
            return jsonify({'status': 'success', 'message': 'Источник чата удален'})
        else:
            return jsonify({'status': 'error', 'message': 'Источник не найден'})
    
    # Получить все источники
    sources = db.get_chat_sources()
    return jsonify(sources)

@app.route('/api/pending-responses')
def get_pending_responses():
    """API: Получить отложенные ответы"""
    responses = db.get_pending_responses()
    return jsonify(responses)

@app.route('/api/response-action', methods=['POST'])
def handle_response_action():
    """API: Обработка действий с ответами (отправить/отклонить/редактировать)"""
    data = request.json
    response_id = data.get('response_id')
    action = data.get('action')  # approve, reject, edit
    edited_text = data.get('edited_text', '')
    
    if action == 'approve':
        db.update_response_status(response_id, 'approved')
        message = 'Ответ одобрен и будет отправлен'
        
    elif action == 'reject':
        db.update_response_status(response_id, 'rejected')
        message = 'Ответ отклонен'
        
    elif action == 'edit':
        db.update_response_status(response_id, 'pending', edited_text)
        message = 'Ответ отредактирован'
    
    return jsonify({'status': 'success', 'message': message})

@app.route('/api/analytics')
def get_analytics():
    """API: Получить данные для аналитики"""
    # Получаем статистику за неделю
    weekly_stats = []
    for i in range(7):
        date = datetime.now().date() - timedelta(days=i)
        stats = db.get_leads_stats(1)  # За один день
        weekly_stats.append({
            'date': date.strftime('%Y-%m-%d'),
            'hot': stats.get('hot_leads', 0),
            'good': stats.get('good_leads', 0),
            'normal': stats.get('normal_leads', 0)
        })
    
    # Эффективность ответов
    total_stats = db.get_leads_stats(7)  # За неделю
    response_data = {
        'responded': total_stats.get('responded', 0),
        'not_responded': total_stats.get('total_leads', 0) - total_stats.get('responded', 0)
    }
    
    return jsonify({
        'weekly_leads': weekly_stats,
        'response_efficiency': response_data
    })

@app.route('/api/export')
def export_data():
    """API: Экспорт данных"""
    format_type = request.args.get('format', 'csv')
    days = request.args.get('days', 7, type=int)
    
    # Получаем данные
    leads = db.get_recent_leads(1000)  # Максимум 1000 лидов
    
    if format_type == 'csv':
        # Здесь можно добавить логику создания CSV файла
        pass
    elif format_type == 'json':
        # Здесь можно добавить логику создания JSON файла
        pass
    
    return jsonify({
        'status': 'success',
        'message': f'Экспорт в формате {format_type} за {days} дней готов',
        'download_url': f'/download/export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{format_type}'
    })

@app.route('/api/scan-leads', methods=['POST'])
def trigger_scan():
    """API: Запуск сканирования лидов"""
    try:
        # Здесь можно добавить логику запуска сканирования
        # Пока просто возвращаем успех
        print("🔍 Запрос на сканирование лидов получен")
        
        return jsonify({
            'status': 'success',
            'message': 'Сканирование запущено (функция в разработке)'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка запуска сканирования: {str(e)}'
        })

# WebSocket события
# Глобальная переменная для хранения активных соединений
active_connections = set()

@socketio.on('connect')
def handle_connect():
    """Клиент подключился к WebSocket"""
    print('🔗 Клиент подключился к WebSocket')
    active_connections.add(request.sid)
    emit('status', {'message': 'Подключено к серверу', 'type': 'success'})

@socketio.on('disconnect')
def handle_disconnect():
    """Клиент отключился от WebSocket"""
    print('❌ Клиент отключился от WebSocket')
    active_connections.discard(request.sid)

@socketio.on('new_lead')
def handle_new_lead(data):
    """Обработка нового лида от Telegram бота"""
    print(f"📨 Получен новый лид: {data.get('message_text', '')[:50]}...")
    
    # Передаем всем подключенным клиентам
    socketio.emit('lead_update', data)
    
    # Обновляем live feed если он активен
    socketio.emit('live_feed_update', {
        'type': 'new_lead',
        'data': data
    })

@socketio.on('start_monitoring')
def handle_start_monitoring():
    """Запустить мониторинг"""
    emit('monitoring_status', {'active': True, 'message': 'Мониторинг запущен'})
    print('▶️ Мониторинг запущен через WebSocket')

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """Остановить мониторинг"""
    emit('monitoring_status', {'active': False, 'message': 'Мониторинг остановлен'})
    print('⏸️ Мониторинг остановлен через WebSocket')

def create_html_template():
    """Создает папку templates если её нет"""
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("📁 Создана папка templates")
    
    if not os.path.exists('templates/dashboard.html'):
        print("⚠️ Файл templates/dashboard.html не найден!")
        print("📝 Переместите dashboard.html в папку templates/")
        return False
    
    return True

def add_test_data():
    """Добавляет тестовые данные в базу (ИСПРАВЛЕНО)"""
    try:
        # Добавляем тестовые ключевые слова
        test_keywords = [
            "ищу видеопродюсера", "нужен видеомонтажер", "требуется оператор",
            "кто делает видео", "видеограф нужен", "ищу видеографа"
        ]
        
        for keyword in test_keywords:
            db.add_keyword(keyword)
        
        # ИСПРАВЛЕНО: правильный формат вызова add_lead
        test_leads = [
            {
                "chat_source": "@videomaker_chat",
                "sender_id": 12345,
                "sender_name": "Иван Петров",
                "message_text": "Ищу видеопродюсера для YouTube канала про путешествия. Бюджет 200к",
                "quality_score": 6,
                "quality_label": "🔥 ГОРЯЧИЙ ЛИД",
                "quality_reasons": ["💰 Упоминает бюджет", "⭐ Ищет профессионала"],
                "chat_name": "Video Makers"
            },
            {
                "chat_source": "@creative_group",
                "sender_id": 23456,
                "sender_name": "Мария",
                "message_text": "Нужен монтажер для рекламного ролика",
                "quality_score": 3,
                "quality_label": "🟡 ХОРОШИЙ ЛИД",
                "quality_reasons": ["⚡ Срочная потребность"],
                "chat_name": "Creative Group"
            },
            {
                "chat_source": "@business_chat",
                "sender_id": 34567,
                "sender_name": "Алексей",
                "message_text": "Кто занимается видео для соцсетей?",
                "quality_score": 1,
                "quality_label": "🟢 ОБЫЧНЫЙ ЛИД",
                "quality_reasons": [],
                "chat_name": "Business Chat"
            },
            {
                "chat_source": "@freelance_hub",
                "sender_id": 45678,
                "sender_name": "Анна",
                "message_text": "Требуется оператор на свадебную съемку",
                "quality_score": 4,
                "quality_label": "🟡 ХОРОШИЙ ЛИД",
                "quality_reasons": ["🎬 Конкретная задача"],
                "chat_name": "Freelance Hub"
            }
        ]
        
        for lead_data in test_leads:
            db.add_lead(**lead_data)  # Используем ** для распаковки словаря
        
        print("✅ Тестовые данные добавлены")
        
    except Exception as e:
        print(f"⚠️ Ошибка добавления тестовых данных: {e}")

if __name__ == '__main__':
    print("🚀 Запуск веб-сервера для Telegram Bot Dashboard")
    print("="*60)
    
    # Создаем папку templates и проверяем HTML
    if not create_html_template():
        print("🔗 После создания файла запустите сервер снова")
        exit(1)
    
    # Добавляем тестовые данные
    add_test_data()
    
    print("✅ Сервер готов к запуску!")
    print("🌐 Откройте в браузере: http://localhost:8080")
    print("📊 Dashboard будет доступен по этому адресу")
    print("🔄 Для остановки нажмите Ctrl+C")
    print("="*60)
    
    # Запускаем сервер
    try:
        socketio.run(app, host='0.0.0.0', port=8080, debug=False)
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен")
