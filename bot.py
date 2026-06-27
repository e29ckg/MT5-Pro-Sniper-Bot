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
    return core_db.load_db('config')

def update_activity(config, msg):
    config['current_activity'] = msg
    core_db.save_db('config', config)

def save_live_status(data):
    data['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    core_db.save_db('live_status', data)

def send_telegram_msg(config, message, current_price=0.0):
    if not config.get('telegram_enabled'): return
    token = config.get('telegram_token')
    chat_id = config.get('telegram_chat_id')
    if not token or not chat_id: return
    try:
        machine_name = socket.gethostname()
    except:
        machine_name = "Unknown_PC"
        
    if current_price > 0:
        full_message = f"🖥️ <b>[{machine_name}]</b>\n{message}\n💰 <b>ราคาปัจจุบัน:</b> {current_price:.2f}"
    else:
        full_message = f"🖥️ <b>[{machine_name}]</b>\n{message}"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": full_message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

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
        except Exception as e: return False 

    for event in news_cache["data"]:
        if event['country'] == 'USD' and event['impact'] == 'High':
            try:
                news_time = datetime.strptime(event['date'], "%Y-%m-%dT%H:%M:%S%z")
                news_time_utc = news_time.astimezone(timezone.utc).replace(tzinfo=None)
                time_diff_mins = (news_time_utc - now).total_seconds() / 60.0
                if -15 <= time_diff_mins <= 15: return True
            except: continue
    return False

def get_dynamic_lot(config):
    base_lot = config.get('start_lot', 0.01)
    if not config.get('use_auto_lot', False): return base_lot
    account_info = mt5.account_info()
    if account_info is None: return base_lot
    balance = account_info.balance
    step = config.get('auto_lot_step', 100.0)
    multiplier = balance / step if step > 0 else 1
    return max(0.01, round(base_lot * multiplier, 2))

def send_order(config, symbol, order_type, lot, magic, current_price=0.0):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None: return False
    price = tick.ask if order_type == 'buy' else tick.bid
    type_code = mt5.ORDER_TYPE_BUY if order_type == 'buy' else mt5.ORDER_TYPE_SELL
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(lot),
        "type": type_code, "price": price, "deviation": 20, "magic": int(magic),
        "comment": "Bot_Pro_V6", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        update_activity(config, "ยิงออเดอร์ไม่สำเร็จ กำลังลองใหม่...")
        send_telegram_msg(config, f"❌ <b>ยิงออเดอร์ไม่สำเร็จ</b>\nคู่เงิน: {symbol}\nสาเหตุ: {result.comment}", current_price)
        return False
        
    update_activity(config, f"เปิดออเดอร์ {order_type.upper()} ขนาด {lot} Lot สำเร็จ")
    send_telegram_msg(config, f"✅ <b>เปิดออเดอร์ใหม่สำเร็จ</b>\n📈 คู่เงิน: {symbol}\n🛒 ฝั่ง: {order_type.upper()}\n⚖️ ขนาด: {lot} Lot", current_price)
    return True

def close_all_positions(config, symbol, magic, reason_msg, current_price=0.0):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None: return
    closed_count = 0
    total_profit = 0.0
    for pos in positions:
        if pos.magic == int(magic):
            tick = mt5.symbol_info_tick(symbol)
            if tick is None: continue
            type_code = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": pos.volume,
                "type": type_code, "position": pos.ticket, "price": price,
                "deviation": 20, "magic": int(magic), "comment": "Basket_Close",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                total_profit += (pos.profit + pos.swap)
                
    if closed_count > 0:
        update_activity(config, f"รวบตึงตะกร้าเรียบร้อย กำไร ${total_profit:.2f}")
        send_telegram_msg(config, f"🧹 <b>{reason_msg}</b>\nปิดไปทั้งหมด: {closed_count} ออเดอร์\n💵 PnL สุทธิ: ${total_profit:.2f}", current_price)
        history_file = "trade_history.json"
        try:
            hist_data = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, "r", encoding='utf-8') as f: hist_data = json.load(f)
                except: pass
            hist_data.append({
                "เวลาปิด": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "คู่เงิน": symbol,
                "สถานะ": reason_msg.replace(" 🎯", "").replace(" 🚨", "").replace(" 🛡️", "").replace(" ☠️", ""),
                "ไม้สะสม": closed_count, "กำไร/ขาดทุน": round(total_profit, 2)
            })
            with open(history_file, "w", encoding='utf-8') as f: json.dump(hist_data, f, indent=4, ensure_ascii=False)
        except: pass

def main():
    print("🤖 กำลังเริ่มต้นระบบ Bot Backend...")
    if not mt5.initialize():
        print("❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
        return
        
    bot_was_running = False
    basket_max_pnl = 0.0
    last_force_close_date = None 
    pending_entry = None

    while True:
        config = load_config()
        if not config:
            time.sleep(2)
            continue
            
        symbol = config.get('symbol', 'XAUUSDm')
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.bid if tick else 0.0

        account_info = mt5.account_info()
        current_balance = account_info.balance if account_info else 0.0
        current_equity = account_info.equity if account_info else 0.0

        cmd = core_db.load_db("ui_command")
        if cmd and cmd.get("action"):
            action = cmd["action"]
            magic_number = config.get('magic_number', 0)
            
            if action == "PANIC_CLOSE":
                close_all_positions(config, symbol, magic_number, "กดปุ่มฉุกเฉิน รวบปิดทันที! 🚨", current_price)
                basket_max_pnl = 0.0
                pending_entry = None 
            elif action == "PAUSE_DCA":
                config["use_smart_dca"] = False
                update_activity(config, "หยุดยิงไม้แก้ (Pause DCA) ชั่วคราว!")
            elif action == "RESUME_DCA":
                config["use_smart_dca"] = True
                update_activity(config, "กลับมายิงไม้แก้ตามปกติ")
            core_db.save_db("ui_command", {})
        
        is_running = config.get("bot_status") == "running"
        if is_running and not bot_was_running:
            send_telegram_msg(config, "🟢 <b>Bot Started</b>\nระบบบอทเทรดเริ่มทำงานแล้ว!", current_price)
            update_activity(config, "บอทเริ่มเดินเครื่องแล้ว...")
            bot_was_running = True
        elif not is_running and bot_was_running:
            send_telegram_msg(config, "🔴 <b>Bot Stopped</b>\nระบบบอทเทรดหยุดทำงานชั่วคราว!", current_price)
            update_activity(config, "หยุดการทำงาน (Standby)")
            bot_was_running = False
            pending_entry = None
        
        if not is_running:
            save_live_status({"status": "stopped", "message": "บอทกำลังพักผ่อน (Stopped)"})
            time.sleep(2)
            continue
            
        magic_number = config['magic_number']
        tf_code = config['timeframe']
        
        positions = mt5.positions_get(symbol=symbol)
        bot_positions = [p for p in positions if p.magic == int(magic_number)] if positions else []
        bot_positions.sort(key=lambda x: x.ticket) 
        total_pnl = sum([(p.profit + p.swap) for p in bot_positions])

        # 🌟 ==========================================
        # 🛡️ ระบบตรวจสอบวินัยการเทรดประจำวัน (Daily Prop Firm Limit)
        # ==========================================
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        history_deals = mt5.history_deals_get(today_start, datetime.now())
        
        today_pnl = 0.0
        if history_deals:
            for deal in history_deals:
                if deal.magic == int(magic_number):
                    today_pnl += (deal.profit + deal.commission + deal.swap)
        
        daily_blocked = False
        block_reason = ""
        daily_profit_target = config.get('daily_profit_target', 50.0)
        daily_loss_limit = -abs(config.get('daily_loss_limit', 30.0))

        if today_pnl >= daily_profit_target:
            daily_blocked = True
            block_reason = f"บรรลุเป้าหมายรายวัน (+${today_pnl:.2f})"
        elif today_pnl <= daily_loss_limit:
            daily_blocked = True
            block_reason = f"ทะลุลิมิตขาดทุนรายวัน (${today_pnl:.2f})"
            
        # เคลียร์ pending entry ทันทีถ้าโดนบล็อกวินัยรายวัน
        if daily_blocked and len(bot_positions) == 0 and pending_entry is not None:
            pending_entry = None
            update_activity(config, f"⚠️ ยกเลิกออเดอร์รอยิง: {block_reason}")

        live_data = {
            "status": "running", "symbol": symbol, "current_price": current_price,
            "balance": current_balance, "equity": current_equity, "mode": "", "details": {}
        }
        
        # ----------------------------------------
        # 1. โหมดถือออเดอร์ (Holding) - ยิงไม้แก้และปิดกำไรได้ตามปกติ
        # ----------------------------------------
        if len(bot_positions) > 0:
            live_data["mode"] = "HOLDING"
            pending_entry = None 
            latest_pos = bot_positions[-1]
            drag = (latest_pos.price_open - current_price) if latest_pos.type == mt5.ORDER_TYPE_BUY else (current_price - latest_pos.price_open)
            
            current_t = datetime.now()
            today_str = current_t.strftime("%Y-%m-%d")
            
            if config.get('enable_force_close', False):
                force_t = datetime.strptime(config.get('force_close_time', '23:50'), '%H:%M').time()
                if current_t.hour == force_t.hour and current_t.minute >= force_t.minute:
                    if last_force_close_date != today_str:
                        close_all_positions(config, symbol, magic_number, "บังคับตัดจบวัน (Force Close) ☠️", current_price)
                        basket_max_pnl = 0.0
                        last_force_close_date = today_str
                        continue

            if config.get('use_time_filter', False) and config.get('enable_clear_mode', True):
                start_t = datetime.strptime(config.get('start_time', '08:00'), '%H:%M').time()
                end_t = datetime.strptime(config.get('end_time', '22:00'), '%H:%M').time()
                curr_time_only = current_t.time()
                is_trading_time = (start_t <= curr_time_only <= end_t) if start_t < end_t else (curr_time_only >= start_t or curr_time_only <= end_t)
                if not is_trading_time:
                    update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | 🧹 เคลียร์พอร์ต (รอปิด >= $0.5)")
                    live_data["details"]["tp_target"] = 0.5
                    if total_pnl >= 0.5:
                        close_all_positions(config, symbol, magic_number, "เคลียร์พอร์ตก่อนหมดวัน (Break-Even) 🧹", current_price)
                        basket_max_pnl = 0.0
                        continue
            
            if total_pnl > basket_max_pnl: basket_max_pnl = total_pnl
            
            open_trades = [{"type": "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell", "price": p.price_open, "lot": p.volume} for p in bot_positions]
            
            live_data["details"].update({
                "trades_count": len(bot_positions), "total_pnl": total_pnl, "max_pnl_reached": basket_max_pnl,
                "drag_usd": drag, "dca_step_target": config['dca_step_usd'], "tp_target": config['quick_profit_target'],
                "open_trades": open_trades 
            })
            update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | PnL: ${total_pnl:.2f} | Max PnL: ${basket_max_pnl:.2f}")
            
            if config.get('use_trailing', False) and (basket_max_pnl >= config.get('trailing_start_usd', 3.0)) and (total_pnl <= basket_max_pnl - config.get('trailing_step_usd', 1.0)):
                close_all_positions(config, symbol, magic_number, f"ล็อกกำไร (Trailing Stop) 🛡️", current_price)
                basket_max_pnl = 0.0
                continue
            
            if total_pnl >= config['quick_profit_target']:
                close_all_positions(config, symbol, magic_number, "รวบตึง (TP Basket) 🎯", current_price)
                basket_max_pnl = 0.0
                continue
            elif total_pnl <= -abs(config['max_drawdown_usd']):
                close_all_positions(config, symbol, magic_number, "ตัดไฟฉุกเฉิน (Panic Close) 🚨", current_price)
                basket_max_pnl = 0.0
                continue
            
            elif len(bot_positions) < config['max_positions'] and drag >= config['dca_step_usd']:
                df_dca = pd.DataFrame(mt5.copy_rates_from_pos(symbol, tf_code, 0, 100))
                current_rsi_dca = calculate_rsi(df_dca['close'], 14).iloc[-1]
                is_rsi_safe = True
                
                if config.get('use_smart_dca', True):
                    if latest_pos.type == mt5.ORDER_TYPE_BUY and current_rsi_dca > 30: is_rsi_safe = False 
                    elif latest_pos.type == mt5.ORDER_TYPE_SELL and current_rsi_dca < 70: is_rsi_safe = False 

                if is_rsi_safe:
                    send_order(config, symbol, 'buy' if latest_pos.type == mt5.ORDER_TYPE_BUY else 'sell', round(latest_pos.volume * config['dca_lot_mult'], 2), magic_number, current_price)
                else:
                    update_activity(config, f"ถืออยู่ {len(bot_positions)} ไม้ | รอ RSI สุดเทรนด์ ({current_rsi_dca:.1f})")

        # ----------------------------------------
        # 2. โหมด Trailing Entry (จ้องตะปบเข้าไม้แรก)
        # ----------------------------------------
        elif pending_entry is not None:
            live_data["mode"] = "TRAILING_ENTRY"
            trail_step = config.get('trailing_entry_step_usd', 1.0)
            is_executed = False
            
            if pending_entry['type'] == 'buy':
                if current_price < pending_entry['extreme_price']:
                    pending_entry['extreme_price'] = current_price
                elif current_price >= pending_entry['extreme_price'] + trail_step:
                    is_executed = True
            else: 
                if current_price > pending_entry['extreme_price']:
                    pending_entry['extreme_price'] = current_price
                elif current_price <= pending_entry['extreme_price'] - trail_step:
                    is_executed = True
                    
            # ดึงเทรนด์ H1 เพื่อป้องกันการง้างรอสวนเทรนด์หลัก
            rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 210)
            if rates_h1 is not None:
                current_ema_h1 = pd.DataFrame(rates_h1)['close'].ewm(span=200, adjust=False).mean().iloc[-1]
                if config.get('use_ema_filter', True):
                    if pending_entry['type'] == 'buy' and current_price < current_ema_h1:
                        pending_entry = None 
                    elif pending_entry['type'] == 'sell' and current_price > current_ema_h1:
                        pending_entry = None 
            
            if pending_entry:
                distance = abs(current_price - pending_entry['extreme_price'])
                msg = f"⏳ กำลังตามรอย {pending_entry['type'].upper()}... (งัดกลับ {distance:.2f} / {trail_step:.2f})"
                update_activity(config, msg)
                live_data["details"] = {
                    "pattern": msg, "extreme_price": pending_entry['extreme_price'],
                    "distance_to_entry": distance, "target_step": trail_step, "next_lot": pending_entry['lot']
                }
                
                if is_executed:
                    send_order(config, symbol, pending_entry['type'], pending_entry['lot'], magic_number, current_price)
                    pending_entry = None
            else:
                update_activity(config, "⚠️ ยกเลิกการตามรอย (กราฟเปลี่ยนเทรนด์ H1)")

        # ----------------------------------------
        # 3. โหมดค้นหาสัญญาณ (Scanning)
        # ----------------------------------------
        else:
            basket_max_pnl = 0.0 
            live_data["mode"] = "SCANNING"
            
            # 🛑 ติดบล็อก Daily Limit หรือ Profit Target
            if daily_blocked:
                msg_block = f"🛑 พักเทรด: {block_reason}"
                update_activity(config, msg_block)
                live_data["details"] = {"pattern": msg_block}
                save_live_status(live_data)
                time.sleep(2)
                continue
            
            current_t = datetime.now().time()
            is_trading_time = True
            
            if config.get('use_time_filter', False):
                start_t = datetime.strptime(config.get('start_time', '08:00'), '%H:%M').time()
                end_t = datetime.strptime(config.get('end_time', '22:00'), '%H:%M').time()
                is_trading_time = (start_t <= current_t <= end_t) if start_t < end_t else (current_t >= start_t or current_t <= end_t)
            
            if config.get('use_time_filter', False) and not is_trading_time:
                msg_time = f"⏳ นอกเวลาเทรด"
                update_activity(config, msg_time)
                live_data["details"] = {"pattern": msg_time}
                save_live_status(live_data)
                time.sleep(1)
                continue
                
            update_activity(config, f"กำลังสแกนหาสัญญาณ X-Sniper...")
            
            rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 210)
            ema_h1 = current_price
            trend_status = "SIDEWAYS"
            if rates_h1 is not None:
                df_h1 = pd.DataFrame(rates_h1)
                ema_h1_series = df_h1['close'].ewm(span=200, adjust=False).mean()
                ema_h1 = ema_h1_series.iloc[-1]
                trend_status = "UP" if current_price > ema_h1 else "DOWN"

            rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, 300)
            
            if rates is not None and len(rates) >= 250:
                df = pd.DataFrame(rates)
                
                df_chart = df.iloc[-60:].copy()
                df_chart['time'] = pd.to_datetime(df_chart['time'], unit='s') + pd.Timedelta(hours=7)
                df_chart['time'] = df_chart['time'].dt.strftime('%H:%M:%S')
                df_chart['ema_h1'] = ema_h1 
                core_db.save_db("chart_data", df_chart.to_dict(orient="records"))
                
                df['rsi_14'] = calculate_rsi(df['close'], 14)
                df['atr_14'] = calculate_atr(df, 14)
                
                current_atr = df['atr_14'].iloc[-1]
                
                closed_3_highs = df['high'].iloc[-4:-1].values
                closed_3_lows = df['low'].iloc[-4:-1].values
                is_x_below = (closed_3_lows[1] == min(closed_3_lows)) 
                is_x_above = (closed_3_highs[1] == max(closed_3_highs))
                kz10_low = df['low'].iloc[-7:-1].min()
                kz10_high = df['high'].iloc[-7:-1].max()
                
                use_ema = config.get('use_ema_filter', True)
                ema_buy_condition = (current_price > ema_h1) if use_ema else True
                ema_sell_condition = (current_price < ema_h1) if use_ema else True

                sym_info = mt5.symbol_info(symbol)
                spread_points = (tick.ask - tick.bid) / sym_info.point if tick and sym_info else 0
                is_market_safe = True
                warning_msg = ""
                
                if spread_points > config.get('max_spread_points', 500):
                    is_market_safe, warning_msg = False, f"⚠️ สเปรดถ่างสูง ({spread_points:.0f})"
                elif config.get('use_atr_filter', True) and current_atr > config.get('max_atr_value', 150.0):
                    is_market_safe, warning_msg = False, f"⚠️ กราฟกระชากแรง (ATR: {current_atr:.1f})"
                elif config.get('use_news_filter', False) and check_news_impact():
                    is_market_safe, warning_msg = False, "🚨 ข่าวกล่องแดง USD เข้า"

                next_lot = get_dynamic_lot(config)
                scan_details = {
                    "trend_h1": trend_status, "ema_h1": float(ema_h1), "current_spread": spread_points, 
                    "next_lot": next_lot, "pattern": warning_msg if not is_market_safe else "กำลังฟอร์มตัว...", 
                    "bounce_ratio": 0.0, "target_bounce": config.get('min_bounce_ratio', 0.35)
                }

                signal = None                
                if is_x_below and ema_buy_condition:
                    drop_usd = df['high'].iloc[-6:-1].max() - closed_3_lows[1]
                    bounce_ratio = (current_price - closed_3_lows[1]) / drop_usd if drop_usd > 0 else 0
                    scan_details["pattern"] = "📉 โซนรอ Buy" if is_market_safe else warning_msg
                    scan_details["bounce_ratio"] = float(bounce_ratio)
                    if is_market_safe and (drop_usd <= config.get('max_gap_usd', 400.0)) and (bounce_ratio >= config.get('min_bounce_ratio', 0.35)) and (closed_3_lows[1] <= kz10_low):
                        signal = 'buy'

                elif is_x_above and ema_sell_condition:
                    pump_usd = closed_3_highs[1] - df['low'].iloc[-6:-1].min()
                    bounce_ratio = (closed_3_highs[1] - current_price) / pump_usd if pump_usd > 0 else 0
                    scan_details["pattern"] = "📈 โซนรอ Sell" if is_market_safe else warning_msg
                    scan_details["bounce_ratio"] = float(bounce_ratio)
                    if is_market_safe and (pump_usd <= config.get('max_gap_usd', 400.0)) and (bounce_ratio >= config.get('min_bounce_ratio', 0.35)) and (closed_3_highs[1] >= kz10_high):
                        signal = 'sell'
                        
                live_data["details"] = scan_details

                if signal:
                    if config.get('use_trailing_entry', False):
                        pending_entry = {'type': signal, 'extreme_price': current_price, 'lot': next_lot}
                        update_activity(config, f"จับสัญญาณ {signal.upper()} ได้! เริ่มโหมดจ้องตะปบ (Trailing)")
                    else:
                        send_order(config, symbol, signal, next_lot, magic_number, current_price)
                        time.sleep(2)
        
        save_live_status(live_data)
        time.sleep(1)

if __name__ == "__main__":
    main()