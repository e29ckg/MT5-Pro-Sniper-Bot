import time
import os
import core_db
from datetime import datetime

# 💡 1. ปรับเวลาเพิ่มขึ้น! เพราะบอทหลักมีจังหวะหน่วงเวลา 300 วินาที
# ควรตั้งเผื่อให้บอททำงานและส่งข้อมูลกลับมา (แนะนำที่ 7-10 นาที)
MAX_DELAY_SECONDS = 450  # 450 วินาที = 7.5 นาที

def send_alert_if_enabled(msg):
    """ แอบส่งแจ้งเตือนเข้า Telegram ถ้าตั้งค่าไว้ """
    config = core_db.load_db("config")
    if config and config.get('telegram_enabled'):
        import requests, socket
        token = config.get('telegram_token')
        chat_id = config.get('telegram_chat_id')
        if token and chat_id:
            try:
                machine = socket.gethostname()
                payload = {"chat_id": chat_id, "text": f"🐕 <b>[Watchdog - {machine}]</b>\n{msg}", "parse_mode": "HTML"}
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=5)
            except: pass

print("🐕 [Watchdog] สุนัขเฝ้ายามเริ่มทำงานแล้ว! คอยตรวจจับบอทค้างทุกๆ 10 วินาที...")

while True:
    try:
        config = core_db.load_db("config")
        
        # ถ้าเราตั้งใจกดหยุดบอทเองจากหน้าเว็บ Watchdog จะไม่ยุ่ง
        if not config or config.get("bot_status") != "running":
            time.sleep(10)
            continue

        live_data = core_db.load_db("live_status")
        if live_data and "last_update" in live_data:
            last_update_str = live_data["last_update"]
            
            # 💡 2. ดัก Error กรณีรูปแบบเวลาเพี้ยน เพื่อไม่ให้ Watchdog พังซะเอง
            try:
                last_update = datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                time.sleep(10)
                continue
                
            now = datetime.now()
            
            # คำนวณว่าบอทเงียบไปกี่วินาทีแล้ว
            delay = (now - last_update).total_seconds()
            
            if delay > MAX_DELAY_SECONDS:
                alert_msg = f"🚨 <b>[SYSTEM ALERT]</b>\nบอทเงียบหายไป {delay:.0f} วินาที (เกินลิมิตที่ {MAX_DELAY_SECONDS}s)\nกำลังทำการ Restart บอทใหม่..."
                print(alert_msg)
                send_alert_if_enabled(alert_msg)
                
                # 1. ฆ่าโปรแกรม Bot ตัวเก่าที่ค้างอยู่ (อิงจากชื่อหน้าต่าง)
                os.system('taskkill /F /FI "WINDOWTITLE eq Bot_Backend*" /T >nul 2>&1')
                time.sleep(3)
                
                # 2. ปลุก Bot ขึ้นมาใหม่
                print("🔄 [Watchdog] กำลังเปิดระบบ Bot Backend ขึ้นมาใหม่...")
                # 💡 3. เช็คให้ชัวร์ว่าเปิดหน้าต่างใหม่ด้วยชื่อ "Bot_Backend" เพื่อให้รอบหน้า taskkill หาเจอ
                os.system('start "Bot_Backend" cmd /k "venv\\Scripts\\activate && python bot.py"')
                
                # 💡 4. พักให้บอทบูตเครื่องและวิเคราะห์กราฟให้เสร็จ 2 นาที ค่อยเริ่มเฝ้าใหม่
                time.sleep(120) 
        
        # วนรอบตรวจตราทุกๆ 10 วินาที
        time.sleep(10)
        
    except Exception as e:
        print(f"❌ [Watchdog Error] {e}")
        time.sleep(10)