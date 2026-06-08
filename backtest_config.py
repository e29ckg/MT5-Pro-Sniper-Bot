import MetaTrader5 as mt5
import pandas as pd
import json
import os
from datetime import datetime

CONFIG_FILE = "config.json"

# ==========================================
# 🛠️ 1. ฟังก์ชันโหลด Config และ Indicators
# ==========================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
    return None

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

# ==========================================
# 🚀 2. ระบบ Backtest หลัก (Fast Scalping + Smart DCA)
# ==========================================
def run_backtest():
    config = load_config()
    if not config:
        print("❌ ไม่พบไฟล์ config.json โปรดรันหน้าเว็บ app.py เพื่อสร้างไฟล์ก่อน")
        return

    print("🤖 กำลังเชื่อมต่อ MT5 เพื่อดึงข้อมูล...")
    if not mt5.initialize():
        print("❌ เชื่อมต่อ MT5 ไม่สำเร็จ! โปรดเปิดโปรแกรม MT5 ไว้")
        return

    symbol = config['symbol']
    tf_code = config['timeframe']
    
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        print(f"❌ ไม่พบข้อมูลสัญลักษณ์ {symbol}")
        mt5.shutdown()
        return
    contract_size = sym_info.trade_contract_size

    # 🌟 ทุนเริ่มต้นและจำนวนแท่งที่ต้องการทดสอบ
    INITIAL_BALANCE = 100.0 
    BARS_TO_TEST = 500

    print(f"📥 กำลังโหลดกราฟย้อนหลัง {symbol} จำนวน {BARS_TO_TEST} แท่ง...")
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, BARS_TO_TEST)
    mt5.shutdown()
    
    if rates is None:
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # 💡 คำนวณ Indicators ทั้งหมดรวดเดียวเพื่อความเร็วในการทำ Backtest
    print("🧠 กำลังคำนวณ EMA 200, RSI 14 และ ATR 14...")
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['rsi_14'] = calculate_rsi(df['close'], 14)
    df['atr_14'] = calculate_atr(df, 14)
    
    print(f"✅ โหลดข้อมูลสำเร็จ เริ่มต้นจำลองการเทรดด้วยทุน ${INITIAL_BALANCE}...")

    balance = INITIAL_BALANCE
    positions = [] 
    basket_history = [] 
    basket_max_pnl = 0.0
    last_force_close_date = None

    for i in range(250, len(df)):
        current_bar = df.iloc[i]
        current_price = current_bar['close'] 
        current_time = current_bar['time']
        current_t = current_time.time()
        today_str = current_time.strftime("%Y-%m-%d")
        
        current_ema = current_bar['ema_200']
        current_rsi = current_bar['rsi_14']
        current_atr = current_bar['atr_14']

        # ตั้งค่าเวลา
        force_str = config.get('force_close_time', '23:50')
        force_t = datetime.strptime(force_str, '%H:%M').time()
        start_str = config.get('start_time', '08:00')
        end_str = config.get('end_time', '22:00')
        start_t = datetime.strptime(start_str, '%H:%M').time()
        end_t = datetime.strptime(end_str, '%H:%M').time()
        
        is_trading_time = True
        if config.get('use_time_filter', False):
            if start_t < end_t: is_trading_time = start_t <= current_t <= end_t
            else: is_trading_time = current_t >= start_t or current_t <= end_t

        # ----------------------------------------
        # 1. อัปเดต PnL ล่าสุด
        # ----------------------------------------
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_price - pos['entry_price']) * contract_size * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_price) * contract_size * pos['lot']
            total_pnl += pos['floating_pnl']

        # ----------------------------------------
        # 2. โหมดถือออเดอร์ (Holding / TP / SL / DCA)
        # ----------------------------------------
        if len(positions) > 0:
            latest_pos = positions[-1]
            drag = (latest_pos['entry_price'] - current_price) if latest_pos['type'] == 'buy' else (current_price - latest_pos['entry_price'])
            
            if total_pnl > basket_max_pnl:
                basket_max_pnl = total_pnl

            closed_basket = False
            close_reason = ""
            tp_target = config.get('quick_profit_target', 5.0) # 💡 เน้นเป้า 5 เหรียญ

            if config.get('enable_force_close', False) and (current_t.hour == force_t.hour and current_t.minute >= force_t.minute):
                if last_force_close_date != today_str:
                    closed_basket = True; close_reason = "Force Close ☠️"
                    last_force_close_date = today_str

            if not closed_basket and config.get('use_time_filter', False) and config.get('enable_clear_mode', True):
                if not is_trading_time and total_pnl >= 0.5:
                    closed_basket = True; close_reason = "Break-Even 🧹"

            # 🛡️ Trailing Stop (เป้าหลักของการเล่นสั้น)
            if not closed_basket and config.get('use_trailing', True):
                trailing_start = config.get('trailing_start_usd', 3.0) # 💡 เริ่มล็อกที่ 3 เหรียญ
                trailing_step = config.get('trailing_step_usd', 1.0)
                locked_profit = basket_max_pnl - trailing_step
                
                if (basket_max_pnl >= trailing_start) and (total_pnl <= locked_profit):
                    closed_basket = True; close_reason = f"Trailing Stop 🛡️ [Max: ${basket_max_pnl:.2f}]"

            if not closed_basket:
                if total_pnl >= tp_target:
                    closed_basket = True; close_reason = "TP Basket 🎯"
                elif total_pnl <= -abs(config.get('max_drawdown_usd', 100.0)):
                    closed_basket = True; close_reason = "Panic Close 🚨"

            if closed_basket:
                balance += total_pnl
                basket_history.append({
                    'close_time': current_time,
                    'trades_count': len(positions),
                    'net_pnl': total_pnl,
                    'status': close_reason
                })
                positions.clear() 
                basket_max_pnl = 0.0
                if balance <= 0: break 
                continue 

            # 🚑 Smart DCA ด้วย RSI
            if len(positions) < config.get('max_positions', 3) and drag >= config.get('dca_step_usd', 250.0):
                use_smart_dca = config.get('use_smart_dca', True)
                is_rsi_safe = True
                
                if use_smart_dca:
                    if latest_pos['type'] == 'buy' and current_rsi > 30:
                        is_rsi_safe = False # รอ Oversold
                    elif latest_pos['type'] == 'sell' and current_rsi < 70:
                        is_rsi_safe = False # รอ Overbought

                if is_rsi_safe:
                    new_lot = round(latest_pos['lot'] * config.get('dca_lot_mult', 1.5), 2)
                    positions.append({
                        'type': latest_pos['type'],
                        'entry_price': current_price,
                        'lot': new_lot,
                        'floating_pnl': 0.0
                    })

        # ----------------------------------------
        # 3. โหมดค้นหาสัญญาณ (Scanning)
        # ----------------------------------------
        else:
            basket_max_pnl = 0.0
            if config.get('use_time_filter', False) and not is_trading_time:
                continue

            # 💡 บล็อกความผันผวนด้วย ATR
            if config.get('use_atr_filter', True) and current_atr > config.get('max_atr_value', 150.0):
                continue

            closed_3_highs = df['high'].iloc[i-3:i].values
            closed_3_lows = df['low'].iloc[i-3:i].values
            is_x_below = (closed_3_lows[1] == min(closed_3_lows)) 
            is_x_above = (closed_3_highs[1] == max(closed_3_highs))
            
            kz10_low = df['low'].iloc[i-7:i].min()
            kz10_high = df['high'].iloc[i-7:i].max()
            
            use_ema = config.get('use_ema_filter', True)
            ema_buy_condition = (current_price > current_ema) if use_ema else True
            ema_sell_condition = (current_price < current_ema) if use_ema else True
            
            signal = None
            max_gap = config.get('max_gap_usd', 400.0)
            min_bounce = config.get('min_bounce_ratio', 0.35)
            
            if is_x_below and ema_buy_condition:
                recent_high = df['high'].iloc[i-6:i].max() 
                x_low = closed_3_lows[1]
                drop_usd = recent_high - x_low
                bounce_usd = current_price - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                if (drop_usd <= max_gap) and (bounce_ratio >= min_bounce) and (x_low <= kz10_low):
                    signal = 'buy'

            elif is_x_above and ema_sell_condition:
                recent_low = df['low'].iloc[i-6:i].min()
                x_high = closed_3_highs[1]
                pump_usd = x_high - recent_low
                pullback_usd = x_high - current_price
                bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                
                if (pump_usd <= max_gap) and (bounce_ratio >= min_bounce) and (x_high >= kz10_high):
                    signal = 'sell'

            if signal:
                base_lot = config.get('start_lot', 0.01)
                if config.get('use_auto_lot', False):
                    step = config.get('auto_lot_step', 500.0)
                    multiplier = balance / step if step > 0 else 1
                    next_lot = max(0.01, round(base_lot * multiplier, 2))
                else:
                    next_lot = base_lot

                positions.append({
                    'type': signal,
                    'entry_price': current_price,
                    'lot': next_lot,
                    'floating_pnl': 0.0
                })

    # ==========================================
    # 📊 4. สรุปผลลัพธ์
    # ==========================================
    total_baskets = len(basket_history)
    print("\n" + "="*65)
    print("🏆 สรุปผลการทดสอบย้อนหลัง (Scalping + Smart DCA + ATR)")
    print("="*65)
    
    if total_baskets > 0:
        win_baskets = [b for b in basket_history if b['net_pnl'] > 0]
        loss_baskets = [b for b in basket_history if b['net_pnl'] <= 0]
        win_rate = (len(win_baskets) / total_baskets) * 100
        net_profit = balance - INITIAL_BALANCE
        
        print(f"💰 ทุนเริ่มต้น: ${INITIAL_BALANCE:.2f} | ยอดคงเหลือ: ${balance:.2f}")
        print(f"📈 กำไรสุทธิ: ${net_profit:.2f}")
        print(f"🧺 จำนวนรอบที่เทรด: {total_baskets} รอบ")
        print(f"🟢 ปิดกำไร (TP / Trailing): {len(win_baskets)} รอบ")
        print(f"🔴 ปิดขาดทุน (SL / Force Close): {len(loss_baskets)} รอบ")
        print(f"🎯 อัตราชนะต่อรอบ (Win Rate): {win_rate:.2f}%")
        print("="*65)
        
        print("📝 ประวัติการเทรด 5 รอบล่าสุด:")
        for b in basket_history[-5:]:
            print(f"   [{b['close_time']}] {b['status']} | PnL: ${b['net_pnl']:.2f} | ถือ {b['trades_count']} ไม้")
    else:
        print("⚠️ ไม่พบสัญญาณเข้าเทรดเลย! (ATR หรือ สเปรดอาจจะตั้งค่าแคบไป)")

if __name__ == "__main__":
    run_backtest()