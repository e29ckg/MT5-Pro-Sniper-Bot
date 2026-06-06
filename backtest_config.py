import MetaTrader5 as mt5
import pandas as pd
import json
import os

CONFIG_FILE = "config.json"

# ==========================================
# 🛠️ 1. ฟังก์ชันโหลด Config
# ==========================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
    return None

# ==========================================
# 🚀 2. ระบบ Backtest หลัก
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

    # ดึงค่าจาก Config มาใช้งาน
    symbol = config['symbol']
    tf_code = config['timeframe']
    
    # 🌟 ตั้งค่าเฉพาะสำหรับจำลองพอร์ต (ปรับแก้ตรงนี้ได้เลย)
    BARS_TO_TEST = 10000 
    INITIAL_BALANCE = 100.0 
    CONTRACT_SIZE = 100.0 # สำหรับ XAUUSDm ปกติคือ 100

    print(f"📥 กำลังโหลดกราฟย้อนหลัง {symbol} จำนวน {BARS_TO_TEST} แท่ง...")
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, BARS_TO_TEST)
    mt5.shutdown()
    
    if rates is None:
        print(f"❌ ดึงข้อมูล {symbol} ไม่สำเร็จ!")
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"✅ โหลดข้อมูลสำเร็จ เริ่มต้นจำลองการเทรดด้วยทุน ${INITIAL_BALANCE}...")

    balance = INITIAL_BALANCE
    positions = [] 
    basket_history = [] 

    # เริ่มลูปจำลอง (เริ่มที่แท่ง 25 เพื่อให้มีข้อมูลย้อนหลังพอคำนวณ)
    for i in range(25, len(df)):
        current_bar = df.iloc[i]
        current_price = current_bar['close'] # ใช้ราคาปิดแท่งเป็นราคาปัจจุบันในการจำลอง
        
        # ----------------------------------------
        # 🧹 1. อัปเดต PnL รวมของทุกออเดอร์ในหน้าตัก
        # ----------------------------------------
        total_pnl = 0.0
        for pos in positions:
            if pos['type'] == 'buy':
                pos['floating_pnl'] = (current_price - pos['entry_price']) * CONTRACT_SIZE * pos['lot']
            else:
                pos['floating_pnl'] = (pos['entry_price'] - current_price) * CONTRACT_SIZE * pos['lot']
            total_pnl += pos['floating_pnl']

        # ----------------------------------------
        # 🎯 2. ตรวจสอบเงื่อนไข Basket Close
        # ----------------------------------------
        if len(positions) > 0:
            closed_basket = False
            status = ""
            
            if total_pnl >= config['quick_profit_target']:
                closed_basket = True
                status = "Win (TP Basket)"
            elif total_pnl <= -abs(config['max_drawdown_usd']):
                closed_basket = True
                status = "Loss (Panic Close)"
                
            if closed_basket:
                balance += total_pnl
                basket_history.append({
                    'close_time': current_bar['time'],
                    'trades_count': len(positions),
                    'net_pnl': total_pnl,
                    'status': status
                })
                positions.clear() 
                
                if balance <= 0:
                    print(f"\n💥 [MARGIN CALL] พอร์ตแตกที่แท่ง {current_bar['time']}! ยอดคงเหลือ: ${balance:.2f}")
                    break 
                
                continue 

        # ----------------------------------------
        # 🚑 3. ตรวจสอบการยิงไม้แก้ (DCA)
        # ----------------------------------------
        if 0 < len(positions) < config['max_positions']:
            latest_pos = positions[-1]
            drag = (latest_pos['entry_price'] - current_price) if latest_pos['type'] == 'buy' else (current_price - latest_pos['entry_price'])
                
            if drag >= config['dca_step_usd']:
                new_lot = round(latest_pos['lot'] * config['dca_lot_mult'], 2)
                positions.append({
                    'type': latest_pos['type'],
                    'entry_price': current_price,
                    'lot': new_lot,
                    'floating_pnl': 0.0
                })
                continue # ถ้ายิงแก้แล้ว ข้ามไปรอแท่งถัดไป

        # ----------------------------------------
        # 🚀 4. ตรวจจับสัญญาณเข้าเทรดไม้แรก (X-Sniper + EMA200)
        # ----------------------------------------
        if len(positions) == 0:
            # 💡 คำนวณเส้น EMA 200 ของข้อมูลทั้งหมดที่มีจนถึงแท่งปัจจุบัน
            # (ใช้ min_periods=1 เพื่อป้องกัน Error ช่วงแรกที่แท่งเทียนไม่ถึง 200)
            ema_200 = df['close'].iloc[:i].ewm(span=200, adjust=False, min_periods=1).mean().iloc[-1]
            
            closed_5_highs = df['high'].iloc[i-5:i].values
            closed_5_lows = df['low'].iloc[i-5:i].values
            
            is_x_below = (closed_5_lows[2] == min(closed_5_lows)) 
            is_x_above = (closed_5_highs[2] == max(closed_5_highs))
            
            kz10_low = df['low'].iloc[i-11:i].min()
            kz10_high = df['high'].iloc[i-11:i].max()
            
            signal = None
            use_ema = config.get('use_ema_filter', True)
            
            # 🟢 เงื่อนไขฝั่ง Buy (ต้องอยู่เหนือ EMA 200 ถ้าระบบเปิดใช้งาน)
            ema_buy_condition = (current_price > ema_200) if use_ema else True
            
            if is_x_below and ema_buy_condition:
                recent_high = df['high'].iloc[i-9:i].max() 
                x_low = closed_5_lows[2]
                drop_usd = recent_high - x_low
                bounce_usd = current_price - x_low
                bounce_ratio = bounce_usd / drop_usd if drop_usd > 0 else 0
                
                if (drop_usd <= config['max_gap_usd']) and (bounce_ratio >= config['min_bounce_ratio']) and (x_low <= kz10_low):
                    signal = 'buy'

            # 🔴 เงื่อนไขฝั่ง Sell (ต้องอยู่ใต้ EMA 200 ถ้าระบบเปิดใช้งาน)
            ema_sell_condition = (current_price < ema_200) if use_ema else True

            if is_x_above and ema_sell_condition:
                recent_low = df['low'].iloc[i-9:i].min()
                x_high = closed_5_highs[2]
                pump_usd = x_high - recent_low
                pullback_usd = x_high - current_price
                bounce_ratio = pullback_usd / pump_usd if pump_usd > 0 else 0
                
                if (pump_usd <= config['max_gap_usd']) and (bounce_ratio >= config['min_bounce_ratio']) and (x_high >= kz10_high):
                    signal = 'sell'

            if signal:
                positions.append({
                    'type': signal,
                    'entry_price': current_price,
                    'lot': config['start_lot'],
                    'floating_pnl': 0.0
                })

    # ==========================================
    # 📊 5. สรุปผลลัพธ์การ Backtest
    # ==========================================
    total_baskets = len(basket_history)
    print("\n" + "="*50)
    print("🏆 สรุปผลการทดสอบย้อนหลัง (Config Sync)")
    print("="*50)
    
    if total_baskets > 0:
        win_baskets = [b for b in basket_history if b['net_pnl'] > 0]
        loss_baskets = [b for b in basket_history if b['net_pnl'] <= 0]
        win_rate = (len(win_baskets) / total_baskets) * 100
        net_profit = balance - INITIAL_BALANCE
        
        print(f"💰 ทุนเริ่มต้น: ${INITIAL_BALANCE:.2f} | ยอดคงเหลือ: ${balance:.2f}")
        print(f"📈 กำไรสุทธิ: ${net_profit:.2f}")
        print(f"🧺 จำนวนรอบที่เทรด (Baskets): {total_baskets} รอบ")
        print(f"🟢 รวบตึงสำเร็จ (Win): {len(win_baskets)} รอบ | 🔴 ตัดไฟฉุกเฉิน (Loss): {len(loss_baskets)} รอบ")
        print(f"🎯 อัตราชนะต่อรอบ (Win Rate): {win_rate:.2f}%")
        print("="*50)
        
        # แสดงประวัติการเข้าเทรด 5 รอบล่าสุด
        print("📝 ประวัติการเทรด 5 รอบล่าสุด:")
        for b in basket_history[-5:]:
            print(f"   [{b['close_time']}] {b['status']} | ไม้สะสม: {b['trades_count']} | PnL: ${b['net_pnl']:.2f}")
    else:
        print("⚠️ ไม่พบสัญญาณเข้าเทรดเลย! ลองปรับพารามิเตอร์ในหน้าเว็บ (เช่น Max Gap, Min Bounce) ให้กว้างขึ้นดูครับ")

if __name__ == "__main__":
    run_backtest()