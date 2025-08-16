import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import threading

class SharedDatabase:
    """Единая база данных для Telegram бота и веб-интерфейса"""
    
    def __init__(self, db_path='data/shared_bot.sqlite'):
        # Создаем папку data если её нет
        os.makedirs('data', exist_ok=True)
        
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        """Создает все необходимые таблицы"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица лидов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_source TEXT NOT NULL,
                    chat_title TEXT,
                    sender_id INTEGER,
                    sender_name TEXT,
                    message_text TEXT NOT NULL,
                    message_id INTEGER,
                    quality_score INTEGER,
                    quality_label TEXT,
                    quality_reasons TEXT, -- JSON array
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    responded BOOLEAN DEFAULT FALSE,
                    response_text TEXT,
                    response_timestamp DATETIME,
                    response_type TEXT, -- 'ai', 'manual', 'edited'
                    forwarded BOOLEAN DEFAULT FALSE,
                    forwarded_timestamp DATETIME
                )
            ''')
            
            # Таблица ключевых слов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase TEXT UNIQUE NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    hits_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_hit_at DATETIME
                )
            ''')
            
            # Таблица источников чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT UNIQUE NOT NULL,
                    chat_name TEXT,
                    chat_type TEXT, -- 'group', 'supergroup', 'channel'
                    active BOOLEAN DEFAULT TRUE,
                    leads_count INTEGER DEFAULT 0,
                    last_lead_time DATETIME,
                    last_scan_time DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица отложенных ответов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER REFERENCES leads(id),
                    ai_response TEXT NOT NULL,
                    edited_response TEXT,
                    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'sent'
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed_at DATETIME,
                    sent_at DATETIME
                )
            ''')
            
            # Таблица настроек системы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    type TEXT, -- 'string', 'int', 'bool', 'json'
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица статистики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date DATE PRIMARY KEY,
                    total_leads INTEGER DEFAULT 0,
                    hot_leads INTEGER DEFAULT 0,
                    good_leads INTEGER DEFAULT 0,
                    normal_leads INTEGER DEFAULT 0,
                    low_quality_leads INTEGER DEFAULT 0,
                    responses_sent INTEGER DEFAULT 0,
                    ai_responses INTEGER DEFAULT 0,
                    manual_responses INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для производительности
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_timestamp ON leads(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_quality ON leads(quality_score)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_chat_source ON leads(chat_source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_active ON keywords(active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_responses(status)')
            
            conn.commit()
            conn.close()
            print(f"✅ Общая база данных инициализирована: {self.db_path}")
    
    def add_lead(self, chat_source: str, sender_id: int,
                 sender_name: str, message_text: str, quality_score: int,
                 quality_label: str, quality_reasons: List[str] = None, chat_name: str = None) -> int:
        """Добавляет новый лид в базу"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            reasons_str = json.dumps(quality_reasons, ensure_ascii=False) if quality_reasons else '[]'
            # Если chat_name не передан, используем chat_source
            if not chat_name:
                chat_name = chat_source
            
            cursor.execute('''
                INSERT INTO leads (chat_source, chat_title, sender_id, sender_name, 
                                 message_text, quality_score, quality_label, quality_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_source, chat_name, sender_id, sender_name,
                  message_text, quality_score, quality_label, reasons_str))
            
            lead_id = cursor.lastrowid
            
            # Обновляем статистику чата
            cursor.execute('''
                INSERT OR REPLACE INTO chat_sources (chat_id, chat_name, active, 
                                                    leads_count, last_lead_time)
                VALUES (?, ?, TRUE, 
                       COALESCE((SELECT leads_count FROM chat_sources WHERE chat_id = ?), 0) + 1,
                       ?)
            ''', (chat_source, chat_name, chat_source, datetime.now()))
            
            # Обновляем дневную статистику
            today = datetime.now().date()
            cursor.execute('''
                INSERT OR REPLACE INTO daily_stats (date, total_leads, hot_leads, good_leads, normal_leads, low_quality_leads)
                VALUES (?, 
                       COALESCE((SELECT total_leads FROM daily_stats WHERE date = ?), 0) + 1,
                       COALESCE((SELECT hot_leads FROM daily_stats WHERE date = ?), 0) + ?,
                       COALESCE((SELECT good_leads FROM daily_stats WHERE date = ?), 0) + ?,
                       COALESCE((SELECT normal_leads FROM daily_stats WHERE date = ?), 0) + ?,
                       COALESCE((SELECT low_quality_leads FROM daily_stats WHERE date = ?), 0) + ?)
            ''', (today, today, today,
                  1 if quality_score >= 5 else 0,  # hot
                  today, 1 if 2 <= quality_score < 5 else 0,  # good
                  today, 1 if 0 <= quality_score < 2 else 0,  # normal
                  today, 1 if quality_score < 0 else 0))  # low
            
            conn.commit()
            conn.close()
            
            print(f"💾 Лид добавлен в БД: ID={lead_id}, качество={quality_label}")
            return lead_id
    
    def get_recent_leads(self, limit: int = 10, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Получает последние лиды"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            date_from = datetime.now() - timedelta(hours=hours_back)
            
            cursor.execute('''
                SELECT id, chat_source, chat_title, sender_id, sender_name, 
                       message_text, quality_score, quality_label, quality_reasons,
                       timestamp, responded, response_text
                FROM leads 
                WHERE timestamp >= ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (date_from, limit))
            
            leads = []
            for row in cursor.fetchall():
                try:
                    reasons = json.loads(row[8]) if row[8] else []
                except:
                    reasons = row[8].split(', ') if row[8] else []
                
                lead = {
                    'id': row[0],
                    'chat_source': row[1],
                    'chat_title': row[2] or row[1],
                    'sender_id': row[3],
                    'sender_name': row[4],
                    'message_text': row[5],
                    'quality_score': row[6],
                    'quality_label': row[7],
                    'quality_reasons': reasons,
                    'timestamp': row[9],
                    'responded': bool(row[10]),
                    'response_text': row[11]
                }
                leads.append(lead)
            
            conn.close()
            return leads
    
    def get_leads_stats(self, days: int = 1) -> Dict[str, Any]:
        """Получает статистику лидов"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            date_from = datetime.now() - timedelta(days=days)
            
            # Общая статистика
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN quality_score >= 5 THEN 1 ELSE 0 END) as hot,
                       SUM(CASE WHEN quality_score >= 2 AND quality_score < 5 THEN 1 ELSE 0 END) as good,
                       SUM(CASE WHEN quality_score >= 0 AND quality_score < 2 THEN 1 ELSE 0 END) as normal,
                       SUM(CASE WHEN quality_score < 0 THEN 1 ELSE 0 END) as low,
                       SUM(CASE WHEN responded = 1 THEN 1 ELSE 0 END) as responded
                FROM leads 
                WHERE timestamp >= ?
            ''', (date_from,))
            
            row = cursor.fetchone()
            
            total_leads = row[0] or 0
            response_rate = round((row[5] / total_leads * 100) if total_leads > 0 else 0, 1)
            
            stats = {
                'total_leads': total_leads,
                'hot_leads': row[1] or 0,
                'good_leads': row[2] or 0,
                'normal_leads': row[3] or 0,
                'low_quality_leads': row[4] or 0,
                'responded': row[5] or 0,
                'response_rate': response_rate
            }
            
            conn.close()
            return stats
    
    def add_keyword(self, phrase: str) -> bool:
        """Добавляет ключевое слово"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('INSERT INTO keywords (phrase) VALUES (?)', (phrase.lower().strip(),))
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                conn.close()
                return False
    
    def remove_keyword(self, phrase: str) -> bool:
        """Удаляет ключевое слово"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM keywords WHERE phrase = ?', (phrase.lower().strip(),))
            affected = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return affected > 0
    
    def get_keywords(self, active_only: bool = True) -> List[str]:
        """Получает список ключевых слов"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if active_only:
                cursor.execute('SELECT phrase FROM keywords WHERE active = 1 ORDER BY hits_count DESC, phrase')
            else:
                cursor.execute('SELECT phrase FROM keywords ORDER BY hits_count DESC, phrase')
            
            keywords = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            return keywords
    
    def keyword_hit(self, phrase: str):
        """Отмечает попадание по ключевому слову"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE keywords 
                SET hits_count = hits_count + 1, last_hit_at = ?
                WHERE phrase = ?
            ''', (datetime.now(), phrase.lower().strip()))
            
            conn.commit()
            conn.close()
    
    def add_pending_response(self, lead_id: int, ai_response: str) -> int:
        """Добавляет отложенный ответ"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO pending_responses (lead_id, ai_response)
                VALUES (?, ?)
            ''', (lead_id, ai_response))
            
            response_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return response_id
    
    def get_pending_responses(self) -> List[Dict[str, Any]]:
        """Получает отложенные ответы"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT pr.id, pr.lead_id, l.message_text, l.quality_label, l.chat_source,
                       pr.ai_response, pr.edited_response, pr.status, pr.created_at
                FROM pending_responses pr
                JOIN leads l ON pr.lead_id = l.id
                WHERE pr.status = 'pending'
                ORDER BY pr.created_at DESC
            ''')
            
            responses = []
            for row in cursor.fetchall():
                response = {
                    'id': row[0],
                    'lead_id': row[1],
                    'lead_message': row[2],
                    'quality_label': row[3],
                    'chat_source': row[4],
                    'ai_response': row[5],
                    'edited_response': row[6],
                    'status': row[7],
                    'created_at': row[8]
                }
                responses.append(response)
            
            conn.close()
            return responses
    
    def update_response_status(self, response_id: int, status: str, edited_text: str = None):
        """Обновляет статус ответа"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if edited_text:
                cursor.execute('''
                    UPDATE pending_responses 
                    SET status = ?, edited_response = ?, processed_at = ?
                    WHERE id = ?
                ''', (status, edited_text, datetime.now(), response_id))
            else:
                cursor.execute('''
                    UPDATE pending_responses 
                    SET status = ?, processed_at = ?
                    WHERE id = ?
                ''', (status, datetime.now(), response_id))
            
            conn.commit()
            conn.close()
    
    def mark_lead_responded(self, lead_id: int, response_text: str, response_type: str = 'ai'):
        """Отмечает лид как отвеченный"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE leads 
                SET responded = 1, response_text = ?, response_timestamp = ?, response_type = ?
                WHERE id = ?
            ''', (response_text, datetime.now(), response_type, lead_id))
            
            # Обновляем дневную статистику
            today = datetime.now().date()
            response_field = f"{response_type}_responses"
            if response_field in ['ai_responses', 'manual_responses']:
                cursor.execute(f'''
                    UPDATE daily_stats 
                    SET responses_sent = responses_sent + 1, {response_field} = {response_field} + 1
                    WHERE date = ?
                ''', (today,))
            
            conn.commit()
            conn.close()
    
    def get_chat_sources(self) -> List[Dict[str, Any]]:
        """Получает источники чатов"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT chat_id, chat_name, chat_type, active, leads_count, 
                       last_lead_time, last_scan_time, created_at
                FROM chat_sources 
                ORDER BY leads_count DESC, chat_name
            ''')
            
            sources = []
            for row in cursor.fetchall():
                source = {
                    'chat_id': row[0],
                    'chat_name': row[1],
                    'chat_type': row[2],
                    'active': bool(row[3]),
                    'leads_count': row[4],
                    'last_lead_time': row[5],
                    'last_scan_time': row[6],
                    'created_at': row[7]
                }
                sources.append(source)
            
            conn.close()
            return sources
    
    def add_chat_source(self, chat_id: str, chat_name: str = None, chat_type: str = None) -> bool:
        """Добавляет источник чата"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO chat_sources (chat_id, chat_name, chat_type)
                    VALUES (?, ?, ?)
                ''', (chat_id, chat_name or chat_id, chat_type))
                
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                conn.close()
                return False
    
    def remove_chat_source(self, chat_id: str) -> bool:
        """Удаляет источник чата"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM chat_sources WHERE chat_id = ?', (chat_id,))
            affected = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return affected > 0
    
    def get_setting(self, key: str, default=None):
        """Получает настройку системы"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT value, type FROM system_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            
            conn.close()
            
            if not row:
                return default
            
            value, value_type = row
            
            if value_type == 'int':
                return int(value)
            elif value_type == 'bool':
                return value.lower() == 'true'
            elif value_type == 'json':
                return json.loads(value)
            else:
                return value
    
    def set_setting(self, key: str, value, value_type: str = 'string'):
        """Устанавливает настройку системы"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if value_type == 'json':
                value_str = json.dumps(value, ensure_ascii=False)
            elif value_type == 'bool':
                value_str = str(value).lower()
            else:
                value_str = str(value)
            
            cursor.execute('''
                INSERT OR REPLACE INTO system_settings (key, value, type, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (key, value_str, value_type, datetime.now()))
            
            conn.commit()
            conn.close()
    
    def get_analytics_data(self, days: int = 7) -> Dict[str, Any]:
        """Получает данные для аналитики"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Данные по дням
            cursor.execute('''
                SELECT date, total_leads, hot_leads, good_leads, normal_leads, low_quality_leads,
                       responses_sent, ai_responses, manual_responses
                FROM daily_stats 
                WHERE date >= DATE('now', '-{} days')
                ORDER BY date
            '''.format(days))
            
            daily_data = []
            for row in cursor.fetchall():
                daily_data.append({
                    'date': row[0],
                    'total_leads': row[1],
                    'hot_leads': row[2],
                    'good_leads': row[3],
                    'normal_leads': row[4],
                    'low_quality_leads': row[5],
                    'responses_sent': row[6],
                    'ai_responses': row[7],
                    'manual_responses': row[8]
                })
            
            # Общая эффективность ответов
            cursor.execute('''
                SELECT 
                    SUM(responses_sent) as total_responses,
                    SUM(ai_responses) as ai_responses,
                    SUM(manual_responses) as manual_responses,
                    SUM(total_leads) - SUM(responses_sent) as not_responded
                FROM daily_stats 
                WHERE date >= DATE('now', '-{} days')
            '''.format(days))
            
            efficiency_row = cursor.fetchone()
            
            conn.close()
            
            return {
                'daily_data': daily_data,
                'response_efficiency': {
                    'total_responses': efficiency_row[0] or 0,
                    'ai_responses': efficiency_row[1] or 0,
                    'manual_responses': efficiency_row[2] or 0,
                    'not_responded': efficiency_row[3] or 0
                }
            }

# Создаем глобальный экземпляр базы данных
db = SharedDatabase()

# Функции-помощники для обратной совместимости
def get_db():
    """Возвращает экземпляр базы данных"""
    return db
