import MetaTrader5 as mt5
import pandas as pd
import itertools
import time
from datetime import datetime

# ==========================================
# ⚙️ 1. ตั้งค่าพารามิเตอร์ที่จะให้บอทสุ่มหา (Grid Search)
# ==========================================
# 💡 สามารถเพิ่ม/ลดตัวเลขในวงเล็บได้ (ยิ่งใส่เยอะ ยิ่งใช้เวลาคำนวณนาน)
PARAMS_GRID = {
    'quick_profit_target': [0.5, 10.0, 15.0],          # เป้ากำไร (TP)
    'max_drawdown_usd': [10.0, 100.0, 150.0],           # จุดตัดไฟ (SL)
    'max_positions': [3],                         # จำนวนไม้สูงสุด (ล็อคไว้ที่ 3 ไม้เพื่อความปลอดภัย)
    'dca_step_usd': [50.0, 100.0, 200.0],        # ระยะยิงแก้ (USD)
    'max_gap_usd': [400.0, 500.0, 600.0],         # ความกว้างของคลื่นที่ยอมรับได้
    'min_bounce_ratio': [0.25, 0.30, 0.35, 0.40]        # เปอร์เซ็นต์แรงเด้งกลับ
}

# ตั้งค่าคงที่สำหรับการทดสอบ
SYMBOL = "BTCUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
BARS_TO_TEST = 5000            # จำนวนแท่งเทียนย้อนหลังที่จะใช้เทสต์
INITIAL_BALANCE = 500.0        # ทุนจำลอง
START_LOT = 0.01
DCA_LOT_MULT = 1.5
USE_EMA_FILTER = True

# ==========================================
# 🧠 2. ฟังก์ชันจำลองการเทรด (อัปเดตโหมด Fast Scalping)
# ==========================================
def simulate_strategy(df, params, contract_size):
    balance = INITIAL_BALANCE
    positions = []
    basket_history = []
    basket_max_pnl = 0.0
    
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
                pos['floating_pnl'] = (current_price - pos['entry_price']) * contract_size * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_price) * contract_size * pos['lot']
            total_pnl += pos['floating_pnl']

        # 2. โหมดถือออเดอร์ (เช็คปิดตะกร้า)
        if len(positions) > 0:
            latest_pos = positions[-1]
            drag = (latest_pos['entry_price'] - current_price) if latest_pos['type'] == 'buy' else (current_price - latest_pos['entry_price'])
            
            if total_pnl > basket_max_pnl:
                basket_max_pnl = total_pnl

            closed_basket = False
            
            # Trailing Stop
            trailing_start = 8.0 # สมมติค่าคงที่สำหรับ Trailing 
            trailing_step = 3.0
            locked_profit = basket_max_pnl - trailing_step
            if (basket_max_pnl >= trailing_start) and (total_pnl <= locked_profit):
                closed_basket = True
            
            # TP / SL ปกติ
            elif total_pnl >= tp_target:
                closed_basket = True
            elif total_pnl <= sl_target:
                closed_basket = True
                
            if closed_basket:
                balance += total_pnl
                basket_history.append({'net_pnl': total_pnl})
                positions.clear() 
                basket_max_pnl = 0.0
                
                if balance <= 0: 
                    return balance, len(basket_history), 0
                continue 

            # 3. ยิงไม้แก้ (DCA)
            if len(positions) < max_pos and drag >= dca_step:
                new_lot = round(latest_pos['lot'] * DCA_LOT_MULT, 2)
                positions.append({
                    'type': latest_pos['type'],
                    'entry_price': current_price,
                    'lot': new_lot,
                    'floating_pnl': 0.0
                })

        # 4. หาสัญญาณ X-Sniper (โหมด 3 แท่งเทียน จมูกไว)
        else:
            basket_max_pnl = 0.0
            
            closed_3_highs = df['high'].iloc[i-3:i].values
            closed_3_lows = df['low'].iloc[i-3:i].values
            is_x_below = (closed_3_lows[1] == min(closed_3_lows)) 
            is_x_above = (closed_3_highs[1] == max(closed_3_highs))
            
            kz10_low = df['low'].iloc[i-7:i].min()
            kz10_high = df['high'].iloc[i-7:i].max()
            
            ema_200 = df['ema_200'].iloc[i]
            
            signal = None
            ema_buy_condition = (current_price > ema_200) if USE_EMA_FILTER else True
            ema_sell_condition = (current_price < ema_200) if USE_EMA_FILTER else True
            
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
# 🚀 3. เริ่มกระบวนการค้นหา (Optimizer)
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
            
        final_balance, trades, win_rate = simulate_strategy(df, params, contract_size)
        net_profit = final_balance - INITIAL_BALANCE
        
        # เก็บเฉพาะแบบที่เทรดเกิน 5 รอบ เพื่อกรองค่าที่บังเอิญเทรดน้อยแล้วได้กำไร
        if trades >= 5:
            results.append({
                'Profit': net_profit,
                'WinRate': win_rate,
                'Trades': trades,
                'Params': params
            })

    print(f"✅ ประมวลผลเสร็จสิ้น! ใช้เวลา {time.time() - start_time:.2f} วินาที\n")
    
    if not results:
        print("⚠️ ไม่พบการตั้งค่าไหนที่ทำกำไรและเทรดรอดเลย ลองปรับช่วงพารามิเตอร์ให้กว้างขึ้นครับ")
        return
        
    # จัดอันดับตามกำไร (Profit) จากมากไปน้อย
    results.sort(key=lambda x: x['Profit'], reverse=True)
    
    print("🏆 TOP 5 การตั้งค่าที่ดีที่สุดสำหรับ BTC (อิงจากกำไรสุทธิ):")
    print("="*70)
    for i, res in enumerate(results[:5]):
        print(f"อันดับที่ {i+1}: กำไร ${res['Profit']:.2f} | Win Rate: {res['WinRate']:.0f}% | เทรด: {res['Trades']} รอบ")
        p = res['Params']
        print(f"   👉 [TP: {p['quick_profit_target']}, SL: {p['max_drawdown_usd']}, "
              f"DCA: {p['dca_step_usd']}, Gap: {p['max_gap_usd']}, Bounce: {p['min_bounce_ratio']}]")
        print("-" * 70)
        
if __name__ == "__main__":
    run_optimizer()