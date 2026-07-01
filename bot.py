import MetaTrader5 as mt5
import pandas as pd
import time
import json
import os
import requests
import socket
from datetime import datetime, timedelta, timezone
import mplfinance as mpf
from PIL import Image
from google import genai
from google.genai import types
import core_db 

# ==========================================
# 🛠️ ฟังก์ชันช่วยเหลือ (Utility)
# ==========================================
def load_config(): return core_db.load_db('config') or {}
def save_live_status(data):
    data['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    core_db.save_db('live_status', data)

def update_activity(config, msg):
    config['current_activity'] = msg
    core_db.save_db('config', config)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_telegram_msg(config, message, current_price=0.0):
    if not config.get('telegram_enabled'): return
    token = config.get('telegram_token')
    chat_id = config.get('telegram_chat_id')
    if not token or not chat_id: return
    try:
        machine_name = socket.gethostname()
    except:
        machine_name = "Unknown_PC"
        
    full_message = f"🤖 <b>[Gemini AI - {machine_name}]</b>\n{message}\n💰 <b>ราคา:</b> {current_price:.2f}" if current_price > 0 else f"🤖 <b>[{machine_name}]</b>\n{message}"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": full_message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def get_dynamic_lot(config):
    base_lot = config.get('start_lot', 0.01)
    account_info = mt5.account_info()
    if account_info is None: return base_lot
    # ปรับ Lot อัตโนมัติ (สามารถเขียนสูตร MM เพิ่มเติมตรงนี้ได้)
    return base_lot

# ==========================================
# 🧠 ฟังก์ชัน Gemini AI Core
# ==========================================
def get_support_resistance(symbol):
    """ดึงแนวรับ-แนวต้านสำคัญจากไทม์เฟรม D1 (5 วันหลังสุด) และ H4 (15 แท่งหลังสุด)"""
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 5)
    rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 15)
    
    if rates_d1 is None or rates_h4 is None:
        return "Unknown", "Unknown", "Unknown", "Unknown"
        
    # หาจุดสูงสุด (Resistance) และต่ำสุด (Support)
    d1_res = max([r['high'] for r in rates_d1])
    d1_sup = min([r['low'] for r in rates_d1])
    
    h4_res = max([r['high'] for r in rates_h4])
    h4_sup = min([r['low'] for r in rates_h4])
    
    return d1_res, d1_sup, h4_res, h4_sup

def create_chart_image(symbol, timeframe, filename):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 60) # ดึง 60 แท่งให้เห็นภาพกว้างขึ้นนิดนึง
    if rates is None: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    
    # วาดกราฟและเซฟตามชื่อไฟล์ที่รับมา  # 🌟 ปรับ volume=True เพื่อวาดกราฟแท่ง Volume ไว้ด้านล่าง
    mpf.plot(df, type='candle', style='charles', volume=True, mav=(9, 21), savefig=filename)
    
    # อัปเดตข้อมูลขึ้นหน้าเว็บเฉพาะไทม์เฟรม M5 (เพื่อไม่ให้หน้าเว็บสับสน)
    if timeframe == mt5.TIMEFRAME_M5:
        df_web = df.reset_index()
        df_web['time'] = df_web['time'].dt.strftime('%H:%M:%S')
        df_web['ema_m5'] = df_web['close'].ewm(span=200, adjust=False).mean()
        core_db.save_db("chart_data", df_web.to_dict(orient="records"))
    
    return filename

def ask_gemini(api_key, img_h1_path, img_m5_path, current_price, current_spread, sr_data):
    if not api_key:
        return {"action": "HOLD", "reason": "รอการตั้งค่า API Key จากหน้าเว็บ..."}
        
    try:
        client = genai.Client(api_key=api_key)
        img_h1 = Image.open(img_h1_path)
        img_m5 = Image.open(img_m5_path)
        
        # แกะข้อมูลแนวรับแนวต้าน
        d1_res, d1_sup, h4_res, h4_sup = sr_data
        
        prompt = f"""
        You are an elite Gold (XAUUSD) trader specializing in precise Multi-Timeframe entries.
        Current market data: Current price {current_price}, Spread {current_spread}
        
        🌟 Major Key Levels (Support & Resistance):
        - Daily (D1) Level: Resistance = {d1_res} | Support = {d1_sup}
        - 4-Hour (H4) Level: Resistance = {h4_res} | Support = {h4_sup}
        
        I have provided 2 chart images (both include EMA 9, EMA 21, and a Volume indicator at the bottom):
        - Image 1: H1 Timeframe. Use this to determine the Macro Trend.
        - Image 2: M5 Timeframe. Use this to find a precise entry point aligning with the H1 trend.
        
        Trading Rules:
        1. NEVER trade against the H1 Macro Trend.
        2. Validate breakouts using the Volume indicator. If price breaks but volume is low, treat it as a fakeout.
        3. Respect Major Key Levels. Avoid BUYING right under Major Resistance, and avoid SELLING right above Major Support.
        4. Focus on high-confidence setups with strong R:R (Risk:Reward) ratio.

        You must respond STRICTLY in JSON format only. Do not include Markdown formatting (such as ```json) or any additional explanations. The structure must be exactly as follows:
        {{
            "action": "BUY", "SELL", or "HOLD",
            "sl_price": Stop Loss price (number),
            "tp_price": Take Profit target price (number),
            "rr_ratio": (number),
            "reason": "Explain your decision combining H1 trend, Volume, and Key levels in 1-2 sentences."
        }}
        Note: Only provide trades where rr_ratio is greater than 1.5.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_h1, img_m5],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
        
    except json.JSONDecodeError:
        return {"action": "HOLD", "reason": "AI ส่งข้อมูลกลับมาผิดรูปแบบ (ไม่ใช่ JSON)"}
    except Exception as e:
        return {"action": "HOLD", "reason": f"AI Error: {str(e)}"}

# ==========================================
# 🎯 ฟังก์ชันจัดการออเดอร์
# ==========================================
def send_order_with_sl_tp(config, symbol, order_type, lot, magic, sl, tp, current_price=0.0):
    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    
    if tick is None or sym_info is None: 
        return False
        
    # ดึงค่าทศนิยมของคู่เงินนั้นๆ (เช่น ทองคำมักจะเป็น 2 หรือ 3)
    digits = sym_info.digits
    
    # กำหนดราคาเข้าและปัดเศษทศนิยม
    price = tick.ask if order_type == 'buy' else tick.bid
    price = round(price, digits)
    
    type_code = mt5.ORDER_TYPE_BUY if order_type == 'buy' else mt5.ORDER_TYPE_SELL
    
    # ป้องกันกรณี AI ส่งค่า 0, None หรือส่งมาเป็น String
    try:
        sl_val = round(float(sl), digits) if sl else 0.0
        tp_val = round(float(tp), digits) if tp else 0.0
    except ValueError:
        sl_val = 0.0
        tp_val = 0.0
        
    request = {
        "action": mt5.TRADE_ACTION_DEAL, 
        "symbol": symbol, 
        "volume": float(lot),
        "type": type_code, 
        "price": price, 
        "sl": sl_val, 
        "tp": tp_val,
        "deviation": 20, 
        "magic": int(magic),
        "comment": "Gemini_AI", 
        "type_time": mt5.ORDER_TIME_GTC, 
        "type_filling": mt5.ORDER_FILLING_IOC, # หมายเหตุ: บางโบรกเกอร์บังคับใช้ mt5.ORDER_FILLING_FOK
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        update_activity(config, f"ยิงออเดอร์พลาด Code: {result.retcode} ({result.comment})")
        # ส่งแจ้งเตือนกรณี Error ด้วย จะได้รู้ว่าทำไมบอทไม่ยอมยิง
        send_telegram_msg(config, f"❌ <b>ยิงออเดอร์ไม่สำเร็จ</b>\nคู่เงิน: {symbol}\nรหัสข้อผิดพลาด: {result.retcode}\nรายละเอียด: {result.comment}", current_price)
        return False
        
    send_telegram_msg(config, f"✅ <b>Gemini เปิดออเดอร์แล้ว!</b>\n📈 คู่: {symbol}\n🛒 ฝั่ง: {order_type.upper()}\n⚖️ ขนาด: {lot} Lot\n🛡️ SL: {sl_val}\n🎯 TP: {tp_val}", current_price)
    return True

def modify_position_sl(config, ticket, symbol, new_sl, current_tp):
    """ฟังก์ชันสำหรับส่งคำสั่งเลื่อน Stop Loss ใน MT5"""
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None: return False
    
    position = mt5.positions_get(ticket=ticket)
    if not position: return False
    pos = position[0]
    
    new_sl_rounded = round(float(new_sl), sym_info.digits)
    new_tp_rounded = round(float(current_tp), sym_info.digits)
    current_sl_rounded = round(pos.sl, sym_info.digits)
    current_tp_rounded = round(pos.tp, sym_info.digits)
    
    # 🌟 ถ้าราคาเท่ากันเป๊ะ ให้คืนค่าเป็นคำว่า "ALREADY_SET" แทนคำว่า True
    if new_sl_rounded == current_sl_rounded and new_tp_rounded == current_tp_rounded:
        return "ALREADY_SET" 
        
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": symbol,
        "sl": new_sl_rounded,
        "tp": new_tp_rounded
    }
    
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return True
    else:
        print(f"เลื่อน SL ไม่สำเร็จ Code: {result.retcode}")
        return False

def check_time_status(config):
    """ตรวจสอบเวลาปัจจุบันว่าอยู่ในช่วงเทรด หรือต้องบังคับปิดออเดอร์"""
    use_time = config.get('use_time_filter', False)
    if not use_time:
        return True, False, False # can_trade, is_rush_hour, is_force_close
        
    time_start_str = config.get('time_start', '06:00')
    time_end_str = config.get('time_end', '23:50')
    
    try:
        now = datetime.now()
        # แปลงข้อความเป็นเวลาของวันนี้
        start_dt = datetime.strptime(time_start_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        end_dt = datetime.strptime(time_end_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
            
        time_left = (end_dt - now).total_seconds()
        
        can_trade = start_dt <= now < end_dt
        
        # รีดกำไร (Rush Hour): ช่วง 1 ชั่วโมง (3600 วินาที) ก่อนเวลาปิด
        is_rush_hour = 0 <= time_left <= 3600 and can_trade
        
        # บังคับปิด (Force Close): เมื่อเลยเวลาปิดไปแล้ว (แต่ไม่เกิน 1 ชม. เพื่อไม่ให้บอทค้างตอนเช้า)
        is_force_close = -3600 <= time_left < 0
        
        return can_trade, is_rush_hour, is_force_close
    except Exception as e:
        print(f"ตั้งค่าเวลาผิดพลาด: {e}")
        return True, False, False

def force_close_all_positions(symbol, magic_number):
    """ฟังก์ชันบังคับปิดทุกออเดอร์ทันที"""
    positions = mt5.positions_get(symbol=symbol, magic=magic_number)
    if positions is None or len(positions) == 0:
        return False
        
    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        action_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": symbol,
            "volume": pos.volume,
            "type": action_type,
            "price": price,
            "deviation": 20,
            "magic": magic_number,
            "comment": "Force Close - End of Day",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(request)
    return True

# ==========================================
# 🚀 ลูปการทำงานหลัก (Main Loop)
# ==========================================
def main():
    print("🤖 กำลังเริ่มต้นระบบ Gemini AI Backend...")
    if not mt5.initialize():
        print("❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
        return
        
    while True:       

        config = load_config()
        if not config or config.get("bot_status") != "running":
            save_live_status({"status": "stopped", "mode": "STANDBY", "details": {"ai_reason": "บอทกำลังพักผ่อน"}})
            time.sleep(5)
            continue
            
        symbol = config.get('symbol', 'XAUUSDm')
        magic_number = config.get('magic_number', 888888)
        tf_code = config.get('timeframe', mt5.TIMEFRAME_M5)
        api_key = config.get('gemini_api_key', '')
        
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            time.sleep(1)
            continue
            
        current_price = tick.bid
        sym_info = mt5.symbol_info(symbol)
        current_spread = (tick.ask - tick.bid) / sym_info.point if sym_info else 0

        account_info = mt5.account_info()
        balance = account_info.balance if account_info else 0.0
        equity = account_info.equity if account_info else 0.0

        positions = mt5.positions_get(symbol=symbol)
        bot_positions = [p for p in positions if p.magic == int(magic_number)] if positions else []
        
        # รวบรวมข้อมูลสถานะสำหรับส่งไปให้หน้าเว็บ (app.py)
        live_data = {
            "status": "running", "symbol": symbol, "current_price": current_price,
            "balance": balance, "equity": equity, "mode": "", 
            "details": {"current_spread": current_spread}
        }

        # 🌟 เช็คเวลาปัจจุบัน
        can_trade, is_rush_hour, is_force_close = check_time_status(config)
        
        # 🚨 บังคับตัดจบก่อนข้ามวัน
        if is_force_close and len(bot_positions) > 0:
            total_profit_loss = sum([(p.profit + p.swap) for p in bot_positions])
            
            if total_profit_loss > 0:
                result_icon = "🟢 กำไร"
            elif total_profit_loss < 0:
                result_icon = "🔴 ขาดทุน"
            else:
                result_icon = "⚪ เสมอตัว"
                
            update_activity(config, f"⏰ หมดเวลาเทรด! สั่งปิดออเดอร์ | ผลประกอบการ: ${total_profit_loss:.2f}")
            
            # สั่งบังคับปิดออเดอร์
            force_close_all_positions(symbol, magic_number)
            
            # 🌟 จัดหน้าตาข้อความสรุปผลส่งเข้า Telegram
            summary_msg = (
                f"⏰ หมดเวลาทำการ (Day Trade)\n"
                f"ระบบได้ทำการเคลียร์ออเดอร์ที่ค้างอยู่ทั้งหมดแล้ว\n"
                f"━━━━━━━━━━━━━━\n"
                f"📊 ผลประกอบการไม้สุดท้าย:\n"
                f"สถานะ: {result_icon}\n"
                f"ยอดสุทธิ: ${total_profit_loss:.2f}\n"
                f"━━━━━━━━━━━━━━\n"
                f"💤 บอทเข้าสู่โหมดสแตนด์บาย พักผ่อนได้เลยครับ!"
            )
            
            # ส่งแจ้งเตือน
            send_telegram_msg(config, summary_msg, current_price)
            
            time.sleep(2)
            continue # ปิดเสร็จให้ข้ามลูปไปเลย รอจนกว่าจะถึงเช้าวันใหม่

        # ----------------------------------------
        # โหมดที่ 1: มีออเดอร์ค้างอยู่ (Holding) - ไม้เดียวเน้นๆ
        # ----------------------------------------
        if len(bot_positions) > 0:
            live_data["mode"] = "HOLDING"
            total_pnl = sum([(p.profit + p.swap) for p in bot_positions])
            
            pos = bot_positions[-1] 
            
            # --- 🛡️ ระบบล็อกกำไร (Dynamic Break-Even & Step Trailing) ---
            use_profit_lock = config.get('use_profit_lock', True)
            lock_style = config.get('profit_lock_style', 'ล็อกครั้งเดียว (One-Time)')

            # 🌟 ถือออเดอร์มาถึงช่วง 1 ชั่วโมงสุดท้าย บังคับเปิดโหมด "ขั้นบันได" รีดกำไรทันที
            if is_rush_hour:
                lock_style = "เลื่อนตามขั้นบันได (Step Trailing)"
                update_activity(config, "🔥 โหมด Rush Hour: เปิด Step Trailing รีดกำไรโค้งสุดท้ายก่อนตลาดปิด!")

            lock_percent_val = config.get('profit_lock_percent', 25) / 100.0 
            
            if use_profit_lock and pos.tp > 0.0 and pos.sl > 0.0:
                is_sl_moved = False
                
                # 🟢 ฝั่ง BUY
                if pos.type == mt5.ORDER_TYPE_BUY:
                    tp_distance = pos.tp - pos.price_open
                    profit_distance = current_price - pos.price_open
                    
                    if tp_distance > 0:
                        target_sl = 0
                        log_percent = 0
                        
                        if lock_style == "เลื่อนตามขั้นบันได (Step Trailing)":
                            if profit_distance >= tp_distance * 0.90:
                                target_sl = pos.price_open + (tp_distance * 0.75)
                                log_percent = 75
                            elif profit_distance >= tp_distance * 0.75:
                                target_sl = pos.price_open + (tp_distance * 0.50)
                                log_percent = 50
                            elif profit_distance >= tp_distance * 0.50:
                                target_sl = pos.price_open + (tp_distance * lock_percent_val)
                                log_percent = int(lock_percent_val * 100)
                        else:
                            if profit_distance >= tp_distance * 0.50:
                                target_sl = pos.price_open + (tp_distance * lock_percent_val)
                                log_percent = int(lock_percent_val * 100)
                        
                        if target_sl > 0 and pos.sl < target_sl:
                            mod_result = modify_position_sl(config, pos.ticket, symbol, target_sl, pos.tp)
                            if mod_result == True: 
                                msg = f"🛡️ เซฟพอร์ต! เลื่อน SL บังหน้าทุน + ล็อกกำไร {log_percent}% ที่ราคา {target_sl:.2f}"
                                update_activity(config, msg)
                                send_telegram_msg(config, msg, current_price)
                                is_sl_moved = True
                
                # 🔴 ฝั่ง SELL
                elif pos.type == mt5.ORDER_TYPE_SELL:
                    tp_distance = pos.price_open - pos.tp
                    profit_distance = pos.price_open - current_price
                    
                    if tp_distance > 0:
                        target_sl = 0
                        log_percent = 0
                        
                        if lock_style == "เลื่อนตามขั้นบันได (Step Trailing)":
                            if profit_distance >= tp_distance * 0.90:
                                target_sl = pos.price_open - (tp_distance * 0.75)
                                log_percent = 75
                            elif profit_distance >= tp_distance * 0.75:
                                target_sl = pos.price_open - (tp_distance * 0.50)
                                log_percent = 50
                            elif profit_distance >= tp_distance * 0.50:
                                target_sl = pos.price_open - (tp_distance * lock_percent_val)
                                log_percent = int(lock_percent_val * 100)
                        else:
                            if profit_distance >= tp_distance * 0.50:
                                target_sl = pos.price_open - (tp_distance * lock_percent_val)
                                log_percent = int(lock_percent_val * 100)
                        
                        if target_sl > 0 and (pos.sl > target_sl or pos.sl == 0):
                            mod_result = modify_position_sl(config, pos.ticket, symbol, target_sl, pos.tp)
                            if mod_result == True: 
                                msg = f"🛡️ เซฟพอร์ต! เลื่อน SL บังหน้าทุน + ล็อกกำไร {log_percent}% ที่ราคา {target_sl:.2f}"
                                update_activity(config, msg)
                                send_telegram_msg(config, msg, current_price)
                                is_sl_moved = True

            # อัปเดตข้อมูลขึ้นหน้าเว็บ
            live_data["details"].update({
                "trades_count": len(bot_positions), "total_pnl": total_pnl,
                "ai_reason": "ถือไม้เดียวเน้นๆ กำลังรอชนเป้า (TP/SL) หรือรอเลื่อนบังหน้าทุน...",
                "open_trades": [{"type": "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell", "price": p.price_open, "lot": p.volume} for p in bot_positions]
            })
            
            update_activity(config, f"ถืออยู่ 1 ไม้ | PnL: ${total_pnl:.2f} | ล็อกหน้าทุน: ทำงานอัตโนมัติ")
            save_live_status(live_data)
            
            time.sleep(2)
            
        # ----------------------------------------
        # โหมดที่ 2: ว่างงาน หาสัญญาณใหม่ (Scanning)
        # ----------------------------------------
        else:
            live_data["mode"] = "SCANNING"
            is_market_safe = True
            
            # 🌟 ถ้านอกเวลาเทรด ห้ามเปิดออเดอร์ใหม่
            if not can_trade:
                is_market_safe = False
                update_activity(config, f"⏳ นอกเวลาทำการ (เริ่มเทรดอีกครั้งเวลา {config.get('time_start', '06:00')})")

            ai_status_msg = "กำลังวิเคราะห์ตลาด..."
            
            # 1. เช็ค Spread ลิมิต
            if current_spread > config.get('max_spread_points', 500):
                is_market_safe = False
                ai_status_msg = f"พักเทรดชั่วคราว: สเปรดถ่างรุนแรง ({current_spread:.0f})"
            
            # 2. ถ้าปลอดภัย ให้ AI อ่านกราฟ Multi-Timeframe + Volume + S/R
            if is_market_safe:
                update_activity(config, "🧠 ประมวลผล H1/M5 + Volume และดึงแนวรับแนวต้าน ส่งให้ AI...")
                
                chart_h1 = create_chart_image(symbol, mt5.TIMEFRAME_H1, "chart_h1.png")
                chart_m5 = create_chart_image(symbol, mt5.TIMEFRAME_M5, "chart_m5.png")
                
                # 🌟 ดึงข้อมูล S/R
                sr_data = get_support_resistance(symbol)
                live_data["details"]["sr_data"] = sr_data
                
                if chart_h1 and chart_m5:
                    decision = ask_gemini(api_key, chart_h1, chart_m5, current_price, current_spread, sr_data)
                    
                    action = decision.get("action", "HOLD")
                    reason = decision.get("reason", "ไม่มีเหตุผลระบุ")
                    
                    ai_status_msg = f"{action} -> {reason}"
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 มุมมอง AI: {ai_status_msg}")
                    
                    if action in ["BUY", "SELL"]:
                        rr = decision.get("rr_ratio", 0)
    
                        # 🛡️ เช็ค RR ขั้นต่ำ (เช่น ต้องมากกว่า 1.5 เท่า)
                        if rr < 1.5:
                            update_activity(config, f"❌ ปฏิเสธการเข้าออเดอร์: RR {rr} ต่ำเกินไป (ขั้นต่ำ 1.5)")
                            ai_status_msg = f"HOLD (Reject: RR {rr} ต่ำเกินไป)"
                        else:
                            # 🌟 แก้ไขแล้ว: ต้องเข้าเงื่อนไข RR ค่อยส่งคำสั่งยิง
                            lot = get_dynamic_lot(config)
                            sl = decision.get("sl_price", 0)
                            tp = decision.get("tp_price", 0)
                            
                            if sl != 0 and tp != 0:
                                success = send_order_with_sl_tp(config, symbol, action.lower(), lot, magic_number, sl, tp, current_price)
                                if success:
                                    update_activity(config, f"🎯 เข้า {action} เรียบร้อย | เหตุผล: {reason}")
                                    ai_status_msg = f"เข้าออเดอร์ {action} สำเร็จ! ({reason})"
                            else:
                                ai_status_msg = f"ยกเลิก {action} เนื่องจาก AI ไม่ได้กำหนด SL/TP อย่างชัดเจน"
            
            # อัปเดตเหตุผลของ AI กลับไปยังหน้าเว็บ
            live_data["details"]["ai_reason"] = ai_status_msg
            save_live_status(live_data)
            
            # หน่วงเวลา 3-5 นาทีเพื่อรอแท่งเทียนใหม่ ป้องกันการรัว API จนติด Rate Limit
            time.sleep(300) 

if __name__ == "__main__":
    main()