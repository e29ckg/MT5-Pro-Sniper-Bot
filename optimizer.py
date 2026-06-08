import MetaTrader5 as mt5
import pandas as pd
import itertools
import time
from datetime import datetime

# ==========================================
# ⚙️ 1. พารามิเตอร์สำหรับ "ทองคำ (XAUUSD)" ทุน 100 USD
# ==========================================
PARAMS_GRID = {
    'quick_profit_target': [2.0, 3.0],             # เป้ากำไร (TP)
    'max_drawdown_usd': [15.0, 20.0],              # จุดตัดไฟ (SL) ไม่เกิน 20% ของพอร์ต
    'dca_step_usd': [2.5, 3.5, 4.5],               # ระยะยิงไม้แก้ (ราคาทองขยับกี่เหรียญ)
    'max_gap_usd': [3.0, 5.0, 7.0],                # ความกว้างของคลื่นสวิง
    'min_bounce_ratio': [0.35, 0.40],              # เปอร์เซ็นต์การเด้งกลับ
    'max_atr_value': [1.5, 2.0],                   # กรองความผันผวน (ATR ของทองจะอยู่ที่ 0.5 - 2.5)
    'trailing_start_usd': [1.5, 2.0]               # จุดเริ่มล็อกกำไร
}

# ตั้งค่าคงที่สำหรับการทดสอบ
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 30000           # จำลองย้อนหลัง 30,000 แท่ง (ประมาณ 1 เดือนสำหรับ M1)
INITIAL_BALANCE = 100.0        # ทุนตั้งต้น 100 USD
START_LOT = 0.01
DCA_LOT_MULT = 1.2             # ใช้ตัวคูณต่ำเพื่อความปลอดภัย
MAX_POSITIONS = 3
TRAILING_STEP = 0.5            # ระยะถอยย่อของ Trailing 

# ==========================================
# 🧠 2. ฟังก์ชันคำนวณอินดิเคเตอร์
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

# ==========================================
# 🚀 3. ฟังก์ชันจำลองการเทรด (Fast Scalping)
# ==========================================
def simulate_strategy(df, params, contract_size):
    balance = INITIAL_BALANCE
    positions = []
    basket_history = []
    basket_max_pnl = 0.0
    
    tp_target = params['quick_profit_target']
    sl_target = -abs(params['max_drawdown_usd'])
    dca_step = params['dca_step_usd']
    max_gap = params['max_gap_usd']
    min_bounce = params['min_bounce_ratio']
    max_atr = params['max_atr_value']
    trailing_start = params['trailing_start_usd']

    for i in range(250, len(df)):
        current_price = df['close'].iloc[i]
        current_ema = df['ema_200'].iloc[i]
        current_rsi = df['rsi_14'].iloc[i]
        current_atr = df['atr_14'].iloc[i]
        
        # 1. อัปเดต PnL
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_price - pos['entry_price']) * contract_size * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_price) * contract_size * pos['lot']
            total_pnl += pos['floating_pnl']

        # 2. โหมดถือออเดอร์
        if len(positions) > 0:
            latest_pos = positions[-1]
            drag = (latest_pos['entry_price'] - current_price) if latest_pos['type'] == 'buy' else (current_price - latest_pos['entry_price'])
            
            if total_pnl > basket_max_pnl:
                basket_max_pnl = total_pnl

            closed_basket = False
            
            # Trailing Stop
            locked_profit = basket_max_pnl - TRAILING_STEP
            if (basket_max_pnl >= trailing_start) and (total_pnl <= locked_profit):
                closed_basket = True
            
            # TP / SL 
            elif total_pnl >= tp_target:
                closed_basket = True
            elif total_pnl <= sl_target:
                closed_basket = True
                
            if closed_basket:
                balance += total_pnl
                basket_history.append({'net_pnl': total_pnl})
                positions.clear() 
                basket_max_pnl = 0.0
                if balance <= 0: return balance, len(basket_history), 0
                continue 

            # Smart DCA ด้วย RSI (รอสุดเทรนด์)
            if len(positions) < MAX_POSITIONS and drag >= dca_step:
                is_rsi_safe = True
                if latest_pos['type'] == 'buy' and current_rsi > 30:
                    is_rsi_safe = False
                elif latest_pos['type'] == 'sell' and current_rsi < 70:
                    is_rsi_safe = False

                if is_rsi_safe:
                    new_lot = round(latest_pos['lot'] * DCA_LOT_MULT, 2)
                    positions.append({
                        'type': latest_pos['type'],
                        'entry_price': current_price,
                        'lot': new_lot,
                        'floating_pnl': 0.0
                    })

        # 3. หาสัญญาณ X-Sniper
        else:
            basket_max_pnl = 0.0
            
            if current_atr > max_atr:
                continue # กรองกราฟกระชากแรง (ข่าว)

            closed_3_highs = df['high'].iloc[i-3:i].values
            closed_3_lows = df['low'].iloc[i-3:i].values
            is_x_below = (closed_3_lows[1] == min(closed_3_lows)) 
            is_x_above = (closed_3_highs[1] == max(closed_3_highs))
            
            kz10_low = df['low'].iloc[i-7:i].min()
            kz10_high = df['high'].iloc[i-7:i].max()
            
            signal = None
            ema_buy_condition = (current_price > current_ema)
            ema_sell_condition = (current_price < current_ema)
            
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
                positions.append({
                    'type': signal,
                    'entry_price': current_price,
                    'lot': START_LOT,
                    'floating_pnl': 0.0
                })

    # คำนวณ Win Rate
    total_baskets = len(basket_history)
    wins = len([b for b in basket_history if b['net_pnl'] > 0])
    win_rate = (wins / total_baskets) * 100 if total_baskets > 0 else 0
    
    return balance, total_baskets, win_rate

# ==========================================
# 📊 4. เริ่มกระบวนการค้นหา (Optimizer)
# ==========================================
def run_optimizer():
    print("🤖 กำลังเชื่อมต่อ MT5...")
    if not mt5.initialize():
        print("❌ เชื่อมต่อไม่ได้! โปรดเปิด MT5 ไว้และ Login บัญชี Exness")
        return

    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        print(f"❌ ไม่พบสัญลักษณ์ {SYMBOL}")
        mt5.shutdown()
        return
    contract_size = sym_info.trade_contract_size

    print(f"📥 กำลังโหลดข้อมูล {SYMBOL} จำนวน {BARS_TO_TEST} แท่งย้อนหลัง (ประมาณ 1 เดือน)...")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_TEST)
    mt5.shutdown()
    
    if rates is None: return
    
    df = pd.DataFrame(rates)
    
    print("🧠 กำลังคำนวณ EMA, RSI และ ATR ล่วงหน้าเพื่อความรวดเร็ว...")
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean() 
    df['rsi_14'] = calculate_rsi(df['close'], 14)
    df['atr_14'] = calculate_atr(df, 14)
    
    keys, values = zip(*PARAMS_GRID.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    total_combos = len(combinations)
    
    print(f"🔍 พบรูปแบบการตั้งค่าที่ต้องทดสอบทั้งหมด {total_combos} รูปแบบ...")
    print("⏳ อาจใช้เวลา 1-3 นาที โปรดรอสักครู่...")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        if idx % 100 == 0 and idx > 0:
            print(f"   ▶ ทดสอบไปแล้ว {idx}/{total_combos} รูปแบบ...")
            
        final_balance, trades, win_rate = simulate_strategy(df, params, contract_size)
        net_profit = final_balance - INITIAL_BALANCE
        
        # กรองเฉพาะรูปแบบที่มีการเทรดอย่างน้อย 5 รอบ (เพื่อให้มั่นใจว่าไม่ได้ฟลุ๊ค)
        if trades >= 5:
            results.append({
                'Profit': net_profit,
                'WinRate': win_rate,
                'Trades': trades,
                'Params': params
            })

    print(f"\n✅ ประมวลผลเสร็จสิ้น! ใช้เวลา {time.time() - start_time:.2f} วินาที\n")
    
    if not results:
        print("⚠️ ไม่พบการตั้งค่าไหนที่ทำกำไรและอยู่รอดใน 1 เดือนที่ผ่านมาเลยครับ (ตลาดอาจโหดเกินไป หรือ Gap แคบไป)")
        return
        
    # จัดอันดับตาม "กำไรสุทธิสูงสุด"
    results.sort(key=lambda x: x['Profit'], reverse=True)
    
    print("🏆 TOP 5 ชุดตัวเลขที่ดีที่สุดสำหรับ XAUUSDm (ทุน 100 USD):")
    print("="*80)
    for i, res in enumerate(results[:5]):
        p = res['Params']
        print(f"🥇 อันดับ {i+1}: กำไรสุทธิ {res['Profit']:+.2f} USD | ทุนจบที่ {INITIAL_BALANCE + res['Profit']:.2f} | Win Rate: {res['WinRate']:.1f}% | เทรด: {res['Trades']} รอบ")
        print(f"   ⚙️ ตั้งค่า: [เป้า TP: {p['quick_profit_target']} | ตัดไฟ SL: {p['max_drawdown_usd']} | Trail-Start: {p['trailing_start_usd']}]")
        print(f"   ⚙️ ลอจิก: [DCA: {p['dca_step_usd']} | Gap: {p['max_gap_usd']} | Bounce: {p['min_bounce_ratio']} | กรอง ATR: {p['max_atr_value']}]")
        print("-" * 80)
        
if __name__ == "__main__":
    run_optimizer()