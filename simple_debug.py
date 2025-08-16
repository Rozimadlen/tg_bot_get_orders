#!/usr/bin/env python3
"""
Простая диагностика базы данных
"""

import os
import sqlite3
from datetime import datetime

def main():
    print("🚀 ПРОСТАЯ ДИАГНОСТИКА БД")
    print("=" * 50)
    
    # 1. Создаем папку data если нет
    os.makedirs('data', exist_ok=True)
    print("✅ Папка data создана/проверена")
    
    # 2. Создаем новую БД с тестовыми данными
    new_db_path = 'data/shared_bot.sqlite'
    print(f"🔧 Создание новой БД: {new_db_path}")
    
    conn = sqlite3.connect(new_db_path)
    cursor = conn.cursor()
    
    # Создаем таблицы
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_source TEXT NOT NULL,
            chat_title TEXT,
            sender_id INTEGER,
            sender_name TEXT,
            message_text TEXT NOT NULL,
            quality_score INTEGER,
            quality_label TEXT,
            quality_reasons TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            responded BOOLEAN DEFAULT FALSE,
            response_text TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase TEXT UNIQUE NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            hits_count INTEGER DEFAULT 0
        )
    ''')
    
    print("✅ Таблицы созданы")
    
    # 3. Добавляем тестовые данные
    print("🧪 Добавление тестовых данных:")
    
    # Ключевые слова
    test_keywords = [
        "ищу видеопродюсера",
        "нужен видеомонтажер",
        "требуется оператор",
        "кто делает видео"
    ]
    
    for keyword in test_keywords:
        try:
            cursor.execute('INSERT INTO keywords (phrase) VALUES (?)', (keyword,))
            print(f"  ✅ Ключевое слово: {keyword}")
        except sqlite3.IntegrityError:
            print(f"  ⚠️ Уже есть: {keyword}")
    
    # Лиды
    test_leads = [
        ("@test_chat", "Тестовый чат", 12345, "Иван Петров",
         "Ищу видеопродюсера для YouTube канала. Бюджет 200к",
         6, "🔥 ГОРЯЧИЙ ЛИД", '["Упоминает бюджет"]'),
        
        ("@creative_group", "Creative Group", 23456, "Мария",
         "Нужен монтажер для рекламного ролика срочно",
         3, "🟡 ХОРОШИЙ ЛИД", '["Срочная потребность"]'),
        
        ("@business_chat", "Business Chat", 34567, "Алексей",
         "Кто занимается видео для соцсетей?",
         1, "🟢 ОБЫЧНЫЙ ЛИД", '[]'),
        
        ("@freelance_hub", "Freelance Hub", 45678, "Анна",
         "Ищу профессионального видеографа для корпоративного фильма",
         5, "🔥 ГОРЯЧИЙ ЛИД", '["Ищет профессионала", "Корпоративный заказ"]'),
        
        ("@video_chat", "Video Chat", 56789, "Дмитрий",
         "Требуется оператор на мероприятие",
         4, "🟡 ХОРОШИЙ ЛИД", '["Конкретная задача"]')
    ]
    
    for lead_data in test_leads:
        cursor.execute('''
            INSERT INTO leads (chat_source, chat_title, sender_id, sender_name, 
                             message_text, quality_score, quality_label, quality_reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', lead_data)
        print(f"  ✅ Лид: {lead_data[3]} - {lead_data[6]}")
    
    conn.commit()
    
    # 4. Проверяем что данные добавились
    cursor.execute("SELECT COUNT(*) FROM leads")
    leads_count = cursor.fetchone()[0]
    print(f"📋 Лидов в БД: {leads_count}")
    
    cursor.execute("SELECT COUNT(*) FROM keywords")
    keywords_count = cursor.fetchone()[0]
    print(f"🔑 Ключевых слов: {keywords_count}")
    
    conn.close()
    
    print("🎉 Тестовые данные созданы!")

if __name__ == "__main__":
    main()
