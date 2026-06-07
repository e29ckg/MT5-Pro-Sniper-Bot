import MetaTrader5 as mt5
import pandas as pd
import itertools
import time
from datetime import datetime

# ==========================================
# ⚙️ 1. ตั้งค่าพารามิเตอร์ที่จะให้บอทสุ่มหา (Grid Search)
# ==========================================
# 💡 เน้นสุ่มหาจุดสมดุลของโหมด Scalping (เล่นสั้น)
PARAMS_GRID = {
    'quick_profit_target': [4.0, 5.0, 6.0],        # เป้ากำไร (TP)
    'max_drawdown_usd': [50.0, 70.0, 100.0],       # จุดตัดไฟ (SL)
    'dca_step_usd': [200.0, 250.0, 300.0],         # ระยะยิงแก้ (USD)
    'max_gap_usd': [300.0, 400.0],                 # ความกว้างของคลื่น
    'min_bounce_ratio': [0.30, 0.35],              # เปอร์เซ็นต์แรงเด้ง
    'max_atr_value': [100.0, 150.0],               # ค่าความผันผวนสูงสุด (ATR)
    'trailing_start_usd': [2.5, 3.0]               # จุดเริ่มล็อกกำไร (Trailing)
}

# ตั้งค่าคงที่สำหรับการทดสอบ
SYMBOL = "BTCUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 10000           # จำลองย้อนหลัง 10,000 แท่ง
INITIAL_BALANCE = 500.0        
START_LOT = 0.01
DCA_LOT_MULT = 1.5
MAX_POSITIONS = 3
TRAILING_STEP = 1.0

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

            # Smart DCA ด้วย RSI
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
                continue # ข้ามถ้าราคากระชากแรง

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
        print("❌ เชื่อมต่อไม่ได้! โปรดเปิด MT5 ไว้")
        return

    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        print(f"❌ ไม่พบสัญลักษณ์ {SYMBOL}")
        mt5.shutdown()
        return
    contract_size = sym_info.trade_contract_size

    print(f"📥 กำลังโหลดข้อมูล {SYMBOL} จำนวน {BARS_TO_TEST} แท่ง... (ดึงครั้งเดียว)")
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
    
    print(f"🔍 พบการตั้งค่าที่ต้องทดสอบทั้งหมด {total_combos} รูปแบบ (อาจใช้เวลา 1-2 นาที...)")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        if idx % 50 == 0:
            print(f"⏳ ทดสอบไปแล้ว {idx}/{total_combos} รูปแบบ...")
            
        final_balance, trades, win_rate = simulate_strategy(df, params, contract_size)
        net_profit = final_balance - INITIAL_BALANCE
        
        # กรองเฉพาะค่าที่เทรดมากกว่า 10 รอบ เพื่อหาความเสถียร
        if trades >= 10:
            results.append({
                'Profit': net_profit,
                'WinRate': win_rate,
                'Trades': trades,
                'Params': params
            })

    print(f"✅ ประมวลผลเสร็จสิ้น! ใช้เวลา {time.time() - start_time:.2f} วินาที\n")
    
    if not results:
        print("⚠️ ไม่พบการตั้งค่าไหนที่ทำกำไรและเทรดรอดเลย ลองขยายช่วงตัวเลขใน PARAMS_GRID ครับ")
        return
        
    # จัดอันดับตามกำไรสุทธิสูงสุด
    results.sort(key=lambda x: x['Profit'], reverse=True)
    
    print("🏆 TOP 5 การตั้งค่าที่ดีที่สุดสำหรับ BTC (โหมดเล่นสั้น):")
    print("="*75)
    for i, res in enumerate(results[:5]):
        p = res['Params']
        print(f"🥇 อันดับที่ {i+1}: กำไรสุทธิ ${res['Profit']:.2f} | Win Rate: {res['WinRate']:.1f}% | เทรด: {res['Trades']} รอบ")
        print(f"   ⚙️ ตั้งค่า: [TP: {p['quick_profit_target']} | SL: {p['max_drawdown_usd']} | Trail-Start: {p['trailing_start_usd']}]")
        print(f"   ⚙️ ลอจิก: [DCA: {p['dca_step_usd']} | Gap: {p['max_gap_usd']} | Bounce: {p['min_bounce_ratio']} | ATR: {p['max_atr_value']}]")
        print("-" * 75)
        
if __name__ == "__main__":
    run_optimizer()