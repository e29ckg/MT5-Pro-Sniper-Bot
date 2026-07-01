import sqlite3
import json
import logging
import os
from datetime import datetime

# ตั้งค่า Logging
logging.basicConfig(filename='bot_system.log', level=logging.ERROR, format='%(asctime)s [%(levelname)s] %(message)s', encoding='utf-8')
DB_FILE = "bot_data.sqlite"

def get_db_connection():
    """ฟังก์ชันกลางสำหรับเชื่อมต่อ DB และเปิดโหมด WAL (สำคัญมากสำหรับการทำงานแบบ Concurrency)"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL;') 
    return conn

def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('CREATE TABLE IF NOT EXISTS json_store (key TEXT PRIMARY KEY, data TEXT)')
            conn.commit()
    except Exception as e: 
        logging.error(f"DB Init Error: {e}", exc_info=True)

def save_db(key, data_dict):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            json_str = json.dumps(data_dict, ensure_ascii=False)
            c.execute('REPLACE INTO json_store (key, data) VALUES (?, ?)', (key, json_str))
            conn.commit()
    except Exception as e: 
        logging.error(f"Save DB Error [{key}]: {e}", exc_info=True)

def load_db(key, default_val=None):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT data FROM json_store WHERE key=?', (key,))
            row = c.fetchone()
            
        if row: 
            return json.loads(row[0])
            
    except Exception as e: 
        logging.error(f"Load DB Error [{key}]: {e}", exc_info=True)
        
    return default_val if default_val is not None else {}

init_db()

def migrate_old_json():
    if os.path.exists("config.json") and not load_db("config"):
        try:
            with open("config.json", "r", encoding='utf-8') as f:
                save_db("config", json.load(f))
        except Exception as e:
            logging.error(f"Migration Error: {e}")

migrate_old_json()