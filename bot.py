import MetaTrader5 as mt5
import pandas as pd
import time
import json
import os
import requests
import socket
from datetime import datetime, timedelta, timezone
import math
import core_db

def load_config():
    # โหลดจากฐานข้อมูลแทนไฟล์
    return core_db.load_db('config')

def update_activity(config, msg):
    # เซฟลงฐานข้อมูล
    config['current_activity'] = msg
    core_db.save_db('config', config)

def save_live_status(data):
    # เซฟสถานะเรดาร์ลงฐานข้อมูล
    data['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    core_db.save_db('live_status', data)

def send_telegram_msg(config, message):
    if not config.get('telegram_enabled'): return
    token = config.get('telegram_token')
    chat_id = config.get('telegram_chat_id')
    if not token or not chat_id: return
    
    # 💡 ดึงราคาปัจจุบันเพิ่ม
    symbol = config.get('symbol', 'BTCUSDm')
    tick = mt5.symbol_info_tick(symbol)
    current_price = tick.bid if tick else 0.0
    
    try:
        machine_name = socket.gethostname()
    except:
        machine_name = "Unknown_PC"
        
    # 💡 เพิ่มราคาเข้าไปในข้อความ
    full_message = f"🖥️ <b>[{machine_name}]</b>\n{message}\n💰 <b>ราคาปัจจุบัน:</b> {current_price:.2f}"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": full_message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

# ==========================================
# 🧠 ฟังก์ชันคำนวณอินดิเคเตอร์ & ข่าว
# ==========================================
def calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

news_cache = {"data": [], "last_fetch": None}

def check_news_impact():
    global news_cache
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if news_cache["last_fetch"] is None or (now - news_cache["last_fetch"]).total_seconds() > 3600:
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                news_cache["data"] = response.json()
                news_cache["last_fetch"] = now
        except Exception as e:
            return False 

    for event in news_cache["data"]:
        if event['country'] == 'USD' and event['impact'] == 'High':
            try:
                news_time = datetime.strptime(event['date'], "%Y-%m-%dT%H:%M:%S%z")
                news_time_utc = news_time.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                time_diff_mins = (news_time_utc - now).total_seconds() / 60.0
                if -15 <= time_diff_mins <= 15:
                    return True
            except: continue
    return False

def get_dynamic_lot(config):
    base_lot = config.get('start_lot', 0.01)
    if not config.get('use_auto_lot', False):
        return base_lot
    account_info = mt5.account_info()
    if account_info is None:
        return base_lot
    balance = account_info.balance
    step = config.get('auto_lot_step', 100.0)
    multiplier = balance / step if step > 0 else 1
    new_lot = base_lot * multiplier
    return max(0.01, round(new_lot, 2))

def send_order(config, symbol, order_type, lot, magic):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None: return False
    price = tick.ask if order_type == 'buy' else tick.bid
    type_code = mt5.ORDER_TYPE_BUY if order_type == 'buy' else mt5.ORDER_TYPE_SELL
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": type_code,
        "price": price,
        "deviation": 20,
        "magic": int(magic),
        "comment": "Bot_Pro_V6",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = f"❌ <b>ยิงออเดอร์ไม่สำเร็จ</b>\nคู่เงิน: {symbol}\nสาเหตุ: {result.comment}"
        update_activity(config, "ยิงออเดอร์ไม่สำเร็จ กำลังลองใหม่...")
        send_telegram_msg(config, msg)
        return False
        
    msg = f"✅ <b>เปิดออเดอร์ใหม่สำเร็จ</b>\n📈 คู่เงิน: {symbol}\n🛒 ฝั่ง: {order_type.upper()}\n⚖️ ขนาด: {lot} Lot"
    update_activity(config, f"เปิดออเดอร์ {order_type.upper()} ขนาด {lot} Lot สำเร็จ")
    send_telegram_msg(config, msg)
    return True

def close_all_positions(config, symbol, magic, reason_msg):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None: return
    closed_count = 0
    total_profit = 0.0
    for pos in positions:
        if pos.magic == int(magic):
            tick = mt5.symbol_info_tick(symbol)
            type_code = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": type_code,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": int(magic),
                "comment": "Basket_Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                total_profit += (pos.profit + pos.swap)
                
    if closed_count > 0:
        msg = f"🧹 <b>{reason_msg}</b>\nปิดไปทั้งหมด: {closed_count} ออเดอร์\n💵 PnL สุทธิ: ${total_profit:.2f}"
        update_activity(config, f"รวบตึงตะกร้าเรียบร้อย กำไร ${total_profit:.2f}")
        send_telegram_msg(config, msg)
        
        history_file = "trade_history.json"
        try:
            hist_data = []
            if os.path.exists(history_file):
                with open(history_file, "r", encoding='utf-8') as f:
                    hist_data = json.load(f)
                    
            hist_data.append({
                "เวลาปิด": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "คู่เงิน": symbol,
                "สถานะ": reason_msg.replace(" 🎯", "").replace(" 🚨", ""),
                "ไม้สะสม": closed_count,
                "กำไร/ขาดทุน": round(total_profit, 2)
            })
            with open(history_file, "w", encoding='utf-8') as f:
                json.dump(hist_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving history: {e}")

def main():
    print("🤖 กำลังเริ่มต้นระบบ Bot Backend...")
    if not mt5.initialize():
        print("❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
        return
        
    bot_was_running = False
    basket_max_pnl = 0.0
    last_force_close_date = None 

    while True:
        config = load_config()
        if not config:
            time.sleep(2)
            continue

        # 🚨 เช็คคำสั่งฉุกเฉินจากหน้าเว็บ (Panic Buttons)
        cmd = core_db.load_db("ui_command")
        if cmd and cmd.get("action"):
            action = cmd["action"]
            if action == "PANIC_CLOSE":
                close_all_positions(config, symbol, magic_number, "กดปุ่มฉุกเฉิน รวบปิดทันที! 🚨")
                basket_max_pnl = 0.0
            elif action == "PAUSE_DCA":
                config["use_smart_dca"] = False
                update_activity(config, "หยุดยิงไม้แก้ (Pause DCA) ชั่วคราว!")
            elif action == "RESUME_DCA":
                config["use_smart_dca"] = True
                update_activity(config, "กลับมายิงไม้แก้ตามปกติ")
            
            # เคลียร์คำสั่งทิ้งหลังจากทำเสร็จ
            core_db.save_db("ui_command", {})
        
        is_running = config.get("bot_status") == "running"
        if is_running and not bot_was_running:
            send_telegram_msg(config, "🟢 <b>Bot Started</b>\nระบบบอทเทรดเริ่มทำงานแล้ว!")
            update_activity(config, "บอทเริ่มเดินเครื่องแล้ว...")
            bot_was_running = True
        elif not is_running and bot_was_running:
            send_telegram_msg(config, "🔴 <b>Bot Stopped</b>\nระบบบอทเทรดหยุดทำงานชั่วคราว!")
            update_activity(config, "หยุดการทำงาน (Standby)")
            bot_was_running = False
        
        if not is_running:
            save_live_status({"status": "stopped", "message": "บอทกำลังพักผ่อน (Stopped)"})
            time.sleep(2)
            continue
            
        symbol = config['symbol']
        magic_number = config['magic_number']
        tf_code = config['timeframe']
        
        positions = mt5.positions_get(symbol=symbol)
        bot_positions = []
        if positions:
            bot_positions = [p for p in positions if p.magic == int(magic_number)]
            bot_positions.sort(key=lambda x: x.ticket) 
            
        total_pnl = sum([(p.profit + p.swap) for p in bot_positions])
        
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.bid if tick else 0.0

        live_data = {
            "status": "running",
            "symbol": symbol,
            "current_price": current_price,
            "mode": "",
            "details": {}
        }
        
        # ----------------------------------------
        # 1. โหมดถือออเดอร์ (Holding / DCA)
        # ----------------------------------------
        if len(bot_positions) > 0:
            live_data["mode"] = "HOLDING"
            latest_pos = bot_positions[-1]
            pos_price = latest_pos.price_open
            drag = (pos_price - current_price) if latest_pos.type == mt5.ORDER_TYPE_BUY else (current_price - pos_price)
            
            current_t = datetime.now()
            today_str = current_t.strftime("%Y-%m-%d")
            
            if config.get('enable_force_close', False):
                force_str = config.get('force_close_time', '23:50')
                force_t = datetime.strptime(force_str, '%H:%M').time()
                if current_t.hour == force_t.hour and current_t.minute >= force_t.minute:
                    if last_force_close_date != today_str:
                        close_all_positions(config, symbol, magic_number, "บังคับตัดจบวัน (Force Close) ☠️")
                        basket_max_pnl = 0.0
                        last_force_close_date = today_str
                        continue

            use_time_filter = config.get('use_time_filter', False)
            if use_time_filter and config.get('enable_clear_mode', True):
                start_str = config.get('start_time', '08:00')
                end_str = config.get('end_time', '22:00')
                start_t = datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.strptime(end_str, '%H:%M').time()
                
                curr_time_only = current_t.time()
                if start_t < end_t:
                    is_trading_time = start_t <= curr_time_only <= end_t
                else:
                    is_trading_time = curr_time_only >= start_t or curr_time_only <= end_t
                    
                if not is_trading_time:
                    update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | 🧹 โหมดเคลียร์พอร์ต (รอปิด >= $0.5)")
                    live_data["details"]["tp_target"] = 0.5
                    if total_pnl >= 0.5:
                        close_all_positions(config, symbol, magic_number, "เคลียร์พอร์ตก่อนหมดวัน (Break-Even) 🧹")
                        basket_max_pnl = 0.0
                        time.sleep(2)
                        continue
            
            if total_pnl > basket_max_pnl:
                basket_max_pnl = total_pnl
            
            live_data["details"].update({
                "trades_count": len(bot_positions),
                "total_pnl": total_pnl,
                "max_pnl_reached": basket_max_pnl,
                "drag_usd": drag,
                "dca_step_target": config['dca_step_usd'],
                "tp_target": config['quick_profit_target']
            })
            update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | PnL: ${total_pnl:.2f} | Max PnL: ${basket_max_pnl:.2f}")
            
            # 🛡️ Trailing Stop (เก็บกำไรไว)
            use_trailing = config.get('use_trailing', False)
            trailing_start = config.get('trailing_start_usd', 3.0)
            trailing_step = config.get('trailing_step_usd', 1.0)
            locked_profit = basket_max_pnl - trailing_step
            
            if use_trailing and (basket_max_pnl >= trailing_start) and (total_pnl <= locked_profit):
                close_all_positions(config, symbol, magic_number, f"ล็อกกำไร (Trailing Stop) 🛡️ [Max: ${basket_max_pnl:.2f}]")
                basket_max_pnl = 0.0
                time.sleep(2)
                continue
            
            # 🎯 TP / SL 
            if total_pnl >= config['quick_profit_target']:
                close_all_positions(config, symbol, magic_number, "รวบตึง (TP Basket) 🎯")
                basket_max_pnl = 0.0
                time.sleep(2)
                continue
            elif total_pnl <= -abs(config['max_drawdown_usd']):
                close_all_positions(config, symbol, magic_number, "ตัดไฟฉุกเฉิน (Panic Close) 🚨")
                basket_max_pnl = 0.0
                time.sleep(2)
                continue
            
            # 🚑 ยิงแก้ (Smart DCA ด้วย RSI) - อุดรอยรั่วแล้ว
            elif len(bot_positions) < config['max_positions'] and drag >= config['dca_step_usd']:
                rates_dca = mt5.copy_rates_from_pos(symbol, tf_code, 0, 100)
                df_dca = pd.DataFrame(rates_dca)
                current_rsi_dca = calculate_rsi(df_dca['close'], 14).iloc[-1]
                
                use_smart_dca = config.get('use_smart_dca', True)
                is_rsi_safe = True
                
                if use_smart_dca:
                    if latest_pos.type == mt5.ORDER_TYPE_BUY and current_rsi_dca > 30:
                        is_rsi_safe = False # ควรรอให้ Oversold ก่อน
                    elif latest_pos.type == mt5.ORDER_TYPE_SELL and current_rsi_dca < 70:
                        is_rsi_safe = False # ควรรอให้ Overbought ก่อน

                if is_rsi_safe:
                    new_lot = round(latest_pos.volume * config['dca_lot_mult'], 2)
                    order_type = 'buy' if latest_pos.type == mt5.ORDER_TYPE_BUY else 'sell'
                    send_order(config, symbol, order_type, new_lot, magic_number)
                else:
                    update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | รอ RSI สุดเทรนด์ ({current_rsi_dca:.1f})")

        # ----------------------------------------
        # 2. โหมดค้นหาสัญญาณ (Scanning)
        # ----------------------------------------
        else:
            basket_max_pnl = 0.0 
            live_data["mode"] = "SCANNING"
            current_t = datetime.now().time()
            
            use_time_filter = config.get('use_time_filter', False)
            is_trading_time = True
            
            if use_time_filter:
                start_str = config.get('start_time', '08:00')
                end_str = config.get('end_time', '22:00')
                start_t = datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.strptime(end_str, '%H:%M').time()
                
                if start_t < end_t:
                    is_trading_time = start_t <= current_t <= end_t
                else:
                    is_trading_time = current_t >= start_t or current_t <= end_t
            
            if use_time_filter and not is_trading_time:
                msg_time = f"⏳ นอกเวลาเทรด (รอเวลา {start_str} - {end_str})"
                update_activity(config, msg_time)
                live_data["details"] = {"pattern": msg_time}
                save_live_status(live_data)
                time.sleep(1)
                continue
                
            update_activity(config, f"กำลังสแกนหาสัญญาณ X-Sniper...")
            
            rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, 1000)
            
            if rates is not None and len(rates) >= 250:
                df = pd.DataFrame(rates)

                # 💡 [อัปเกรด] ดึง 60 แท่งล่าสุด เซฟลงฐานข้อมูลให้หน้าเว็บวาดกราฟ
                df_chart = df.iloc[-60:].copy()
                df_chart['time'] = pd.to_datetime(df_chart['time'], unit='s').astype(str)
                # เซฟ EMA ไปด้วยเพื่อวาดลงกราฟ
                df_chart['ema_200'] = df['close'].ewm(span=200, adjust=False).mean().iloc[-60:]
                core_db.save_db("chart_data", df_chart.to_dict(orient="records"))
                
                # คำนวณอินดิเคเตอร์
                df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
                df['rsi_14'] = calculate_rsi(df['close'], 14)
                df['atr_14'] = calculate_atr(df, 14)
                
                current_ema_200 = df['ema_200'].iloc[-1]
                current_rsi = df['rsi_14'].iloc[-1]
                current_atr = df['atr_14'].iloc[-1]
                
                # โหมดจมูกไว (3 แท่งเทียน)
                closed_3_highs = df['high'].iloc[-4:-1].values
                closed_3_lows = df['low'].iloc[-4:-1].values
                is_x_below = (closed_3_lows[1] == min(closed_3_lows)) 
                is_x_above = (closed_3_highs[1] == max(closed_3_highs))
                
                kz10_low = df['low'].iloc[-7:-1].min()
                kz10_high = df['high'].iloc[-7:-1].max()
                
                use_ema = config.get('use_ema_filter', True)
                ema_buy_condition = (current_price > current_ema_200) if use_ema else True
                ema_sell_condition = (current_price < current_ema_200) if use_ema else True

                # 💡 [อัปเกรด] บล็อกความปลอดภัย (Safety Blocks)
                sym_info = mt5.symbol_info(symbol)
                spread_points = 0
                is_market_safe = True
                warning_msg = ""
                
                if tick and sym_info:
                    spread_points = (tick.ask - tick.bid) / sym_info.point
                    
                # 1. เช็คสเปรด
                if spread_points > config.get('max_spread_points', 5000):
                    is_market_safe = False
                    warning_msg = f"⚠️ สเปรดถ่างสูงเกินไป ({spread_points:.0f})"
                # 2. เช็ค ATR (ความผันผวน)
                elif config.get('use_atr_filter', True) and current_atr > config.get('max_atr_value', 150.0):
                    is_market_safe = False
                    warning_msg = f"⚠️ กราฟกระชากแรง (ATR: {current_atr:.1f})"
                # 3. เช็คข่าว
                elif config.get('use_news_filter', False) and check_news_impact():
                    is_market_safe = False
                    warning_msg = "🚨 ข่าวกล่องแดง USD เข้า บอทหยุดสแกน"

                next_lot = get_dynamic_lot(config)

                scan_details = {
                    "kz10_high": float(kz10_high),
                    "kz10_low": float(kz10_low),
                    "ema_200": float(current_ema_200),
                    "current_spread": spread_points,
                    "next_lot": next_lot,
                    "pattern": warning_msg if not is_market_safe else "กำลังฟอร์มตัว...",
                    "drop_pump_usd": 0.0,
                    "bounce_ratio": 0.0,
                    "target_gap": config['max_gap_usd'],
                    "target_bounce": config['min_bounce_ratio']
                }

                signal = None                
                if is_x_below and ema_buy_condition:
                    recent_high = df['high'].iloc[-6:-1].max()
                    x_low = closed_3_lows[1]
                    drop_usd = recent_high - x_low
                    bounce_usd = current_price - x_low
                    bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                    
                    scan_details["pattern"] = "📉 โซนรอ Buy (X-Below เหนือ EMA)" if is_market_safe else warning_msg
                    scan_details["drop_pump_usd"] = float(drop_usd)
                    scan_details["bounce_ratio"] = float(bounce_ratio)
                    
                    if is_market_safe and (drop_usd <= config['max_gap_usd']) and (bounce_ratio >= config['min_bounce_ratio']) and (x_low <= kz10_low):
                        signal = 'buy'

                elif is_x_above and ema_sell_condition:
                    recent_low = df['low'].iloc[-6:-1].min()
                    x_high = closed_3_highs[1]
                    pump_usd = x_high - recent_low
                    pullback_usd = x_high - current_price
                    bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                    
                    scan_details["pattern"] = "📈 โซนรอ Sell (X-Above ใต้ EMA)" if is_market_safe else warning_msg
                    scan_details["drop_pump_usd"] = float(pump_usd)
                    scan_details["bounce_ratio"] = float(bounce_ratio)
                    
                    if is_market_safe and (pump_usd <= config['max_gap_usd']) and (bounce_ratio >= config['min_bounce_ratio']) and (x_high >= kz10_high):
                        signal = 'sell'
                        
                elif is_x_below and not ema_buy_condition:
                    scan_details["pattern"] = "⚠️ เจอ X-Below แต่ถูกบล็อก (ราคาอยู่ใต้ EMA200)"
                elif is_x_above and not ema_sell_condition:
                    scan_details["pattern"] = "⚠️ เจอ X-Above แต่ถูกบล็อก (ราคาอยู่เหนือ EMA200)"

                live_data["details"] = scan_details

                if signal:
                    send_order(config, symbol, signal, next_lot, magic_number)
                    time.sleep(2)
        
        save_live_status(live_data)
        time.sleep(1)

if __name__ == "__main__":
    main()