import sqlite3
import json
import logging
import os
from datetime import datetime

logging.basicConfig(filename='bot_system.log', level=logging.ERROR, format='%(asctime)s [%(levelname)s] %(message)s', encoding='utf-8')
DB_FILE = "bot_data.sqlite"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS json_store (key TEXT PRIMARY KEY, data TEXT)')
        conn.commit()
        conn.close()
    except Exception as e: logging.error(f"DB Init Error: {e}", exc_info=True)

def save_db(key, data_dict):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        json_str = json.dumps(data_dict, ensure_ascii=False)
        c.execute('REPLACE INTO json_store (key, data) VALUES (?, ?)', (key, json_str))
        conn.commit()
        conn.close()
    except Exception as e: logging.error(f"Save DB Error [{key}]: {e}", exc_info=True)

def load_db(key, default_val=None):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        c.execute('SELECT data FROM json_store WHERE key=?', (key,))
        row = c.fetchone()
        conn.close()
        if row: return json.loads(row[0])
    except Exception as e: logging.error(f"Load DB Error [{key}]: {e}", exc_info=True)
    return default_val if default_val else {}

init_db()

def migrate_old_json():
    if os.path.exists("config.json") and not load_db("config"):
        with open("config.json", "r", encoding='utf-8') as f:
            save_db("config", json.load(f))

migrate_old_json()