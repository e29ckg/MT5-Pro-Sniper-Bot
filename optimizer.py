import MetaTrader5 as mt5
import pandas as pd
import itertools
import time

# ==========================================
# ⚙️ 1. ตั้งค่าพารามิเตอร์ที่จะให้บอทสุ่มหา (Grid Search)
# ==========================================
# คุณสามารถเพิ่มหรือลดตัวเลขในวงเล็บ [] ได้ตามต้องการ (ยิ่งใส่เยอะ ยิ่งใช้เวลาหานาน)
PARAMS_GRID = {
    'quick_profit_target': [3.0, 5.0, 7.0],       # เป้ากำไร (TP)
    'max_drawdown_usd': [15.0, 25.0, 40.0],       # จุดตัดไฟ (SL)
    'max_positions': [1, 2, 3],                   # จำนวนไม้ (1 = ไม่ DCA)
    'dca_step_usd': [5.0, 10.0],                  # ระยะยิงแก้ (USD)
    'max_gap_usd': [10.0, 15.0],                  # ความกว้างที่ยอมรับได้
    'min_bounce_ratio': [0.30, 0.40]              # แรงเด้งกลับ
}

# ตั้งค่าคงที่สำหรับการทดสอบ
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 10000
INITIAL_BALANCE = 100.0
CONTRACT_SIZE = 100.0
START_LOT = 0.01
DCA_LOT_MULT = 1.5
USE_EMA_FILTER = True

# ==========================================
# 🧠 2. ฟังก์ชันจำลองการเทรด (เหมือน Backtest แต่เน้นความเร็ว)
# ==========================================
def simulate_strategy(df, params):
    balance = INITIAL_BALANCE
    positions = []
    basket_history = []
    
    tp_target = params['quick_profit_target']
    sl_target = -abs(params['max_drawdown_usd'])
    max_pos = params['max_positions']
    dca_step = params['dca_step_usd']
    max_gap = params['max_gap_usd']
    min_bounce = params['min_bounce_ratio']

    for i in range(250, len(df)):
        current_price = df['close'].iloc[i]
        
        # 1. อัปเดต PnL
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_price - pos['entry_price']) * CONTRACT_SIZE * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_price) * CONTRACT_SIZE * pos['lot']
            total_pnl += pos['floating_pnl']

        # 2. ตรวจสอบเงื่อนไข Basket Close
        if len(positions) > 0:
            closed_basket = False
            
            if total_pnl >= tp_target:
                closed_basket = True
            elif total_pnl <= sl_target:
                closed_basket = True
                
            if closed_basket:
                balance += total_pnl
                basket_history.append({'net_pnl': total_pnl})
                positions.clear() 
                
                if balance <= 0: # พอร์ตแตก หยุดจำลองทันที
                    return balance, len(basket_history), 0
                continue 

        # 3. ยิงไม้แก้ (DCA)
        if 0 < len(positions) < max_pos:
            latest_pos = positions[-1]
            drag = (latest_pos['entry_price'] - current_price) if latest_pos['type'] == 'buy' else (current_price - latest_pos['entry_price'])
                
            if drag >= dca_step:
                new_lot = round(latest_pos['lot'] * DCA_LOT_MULT, 2)
                positions.append({
                    'type': latest_pos['type'],
                    'entry_price': current_price,
                    'lot': new_lot,
                    'floating_pnl': 0.0
                })
                continue 

        # 4. หาสัญญาณ X-Sniper + EMA200
        if len(positions) == 0:
            closed_5_highs = df['high'].iloc[i-5:i].values
            closed_5_lows = df['low'].iloc[i-5:i].values
            
            is_x_below = (closed_5_lows[2] == min(closed_5_lows)) 
            is_x_above = (closed_5_highs[2] == max(closed_5_highs))
            
            kz10_low = df['low'].iloc[i-11:i].min()
            kz10_high = df['high'].iloc[i-11:i].max()
            
            ema_200 = df['ema_200'].iloc[i]
            
            signal = None
            ema_buy_condition = (current_price > ema_200) if USE_EMA_FILTER else True
            ema_sell_condition = (current_price < ema_200) if USE_EMA_FILTER else True
            
            if is_x_below and ema_buy_condition:
                recent_high = df['high'].iloc[i-9:i].max() 
                x_low = closed_5_lows[2]
                drop_usd = recent_high - x_low
                bounce_usd = current_price - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                if (drop_usd <= max_gap) and (bounce_ratio >= min_bounce) and (x_low <= kz10_low):
                    signal = 'buy'

            elif is_x_above and ema_sell_condition:
                recent_low = df['low'].iloc[i-9:i].min()
                x_high = closed_5_highs[2]
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
# 🚀 3. เริ่มกระบวนการค้นหา (Optimizer)
# ==========================================
def run_optimizer():
    print("🤖 กำลังเชื่อมต่อ MT5...")
    if not mt5.initialize():
        print("❌ เชื่อมต่อไม่ได้!")
        return

    print(f"📥 กำลังโหลดข้อมูล {SYMBOL} จำนวน {BARS_TO_TEST} แท่ง... (ดึงครั้งเดียว)")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_TEST)
    mt5.shutdown()
    
    if rates is None: return
    
    df = pd.DataFrame(rates)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean() # คำนวณ EMA รอไว้เลย
    
    # สร้างลิสต์ของรูปแบบที่เป็นไปได้ทั้งหมด
    keys, values = zip(*PARAMS_GRID.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    total_combos = len(combinations)
    
    print(f"🔍 พบการตั้งค่าที่ต้องทดสอบทั้งหมด {total_combos} รูปแบบ (อาจใช้เวลาสักครู่...)")
    
    results = []
    start_time = time.time()
    
    # วนลูปทดสอบทีละรูปแบบ
    for idx, params in enumerate(combinations):
        if idx % 20 == 0:
            print(f"⏳ ทดสอบไปแล้ว {idx}/{total_combos} รูปแบบ...")
            
        final_balance, trades, win_rate = simulate_strategy(df, params)
        net_profit = final_balance - INITIAL_BALANCE
        
        # เก็บเฉพาะแบบที่เทรดเกิน 10 รอบ เพื่อกรองค่าที่บังเอิญเทรดน้อยแล้วได้กำไร
        if trades > 10:
            results.append({
                'Profit': net_profit,
                'WinRate': win_rate,
                'Trades': trades,
                'Params': params
            })

    print(f"✅ ประมวลผลเสร็จสิ้น! ใช้เวลา {time.time() - start_time:.2f} วินาที\n")
    
    if not results:
        print("⚠️ ไม่พบการตั้งค่าไหนที่ทำกำไรและเทรดเกิน 10 รอบเลย ลองปรับช่วงพารามิเตอร์ให้กว้างขึ้นครับ")
        return
        
    # จัดอันดับตามกำไร (Profit) จากมากไปน้อย
    results.sort(key=lambda x: x['Profit'], reverse=True)
    
    print("🏆 TOP 5 การตั้งค่าที่ดีที่สุด (อิงจากกำไรสุทธิ):")
    print("="*60)
    for i, res in enumerate(results[:5]):
        print(f"อันดับที่ {i+1}: กำไร ${res['Profit']:.2f} | Win Rate: {res['WinRate']:.2f}% | เทรด: {res['Trades']} รอบ")
        p = res['Params']
        print(f"   👉 [TP: {p['quick_profit_target']}, SL: {p['max_drawdown_usd']}, MaxPos: {p['max_positions']}, "
              f"DCA: {p['dca_step_usd']}, Gap: {p['max_gap_usd']}, Bounce: {p['min_bounce_ratio']}]")
        print("-" * 60)
        
if __name__ == "__main__":
    run_optimizer()