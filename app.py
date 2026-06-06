import streamlit as st
import pandas as pd
import json
import os
import time
import datetime

CONFIG_FILE = "config.json"
LIVE_STATUS_FILE = "live_status.json"
HISTORY_FILE = "trade_history.json"

# ==========================================
# 🛠️ ฟังก์ชันจัดการไฟล์ Config & ข้อมูล
# ==========================================
def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_json(filename, data):
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

config = load_json(CONFIG_FILE)

# ==========================================
# 🎨 ตั้งค่าหน้าเว็บ (Compact Layout)
# ==========================================
st.set_page_config(page_title="MT5 Pro Sniper Bot", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# ⚙️ เมนูตั้งค่าพารามิเตอร์ (Sidebar)
# ==========================================
st.sidebar.header("⚙️ 1. ตั้งค่าพื้นฐาน")
config['symbol'] = st.sidebar.text_input("Symbol", config.get('symbol', 'XAUUSDm'))
config['magic_number'] = int(st.sidebar.number_input("Magic Number", value=config.get('magic_number', 999999), step=1))
tf_options = {1: "M1", 5: "M5", 15: "M15", 16385: "H1"}
current_tf_name = tf_options.get(config.get('timeframe', 1), "M1")
selected_tf_name = st.sidebar.selectbox("Timeframe", list(tf_options.values()), index=list(tf_options.values()).index(current_tf_name))
config['timeframe'] = [k for k, v in tf_options.items() if v == selected_tf_name][0]

st.sidebar.header("🌟 2. การตั้งค่ากลยุทธ์")
config['start_lot'] = st.sidebar.number_input("Start Lot (Base)", value=config.get('start_lot', 0.01), step=0.01)
config['quick_profit_target'] = st.sidebar.number_input("Quick Profit Target ($)", value=config.get('quick_profit_target', 5.0), step=0.5)
config['max_drawdown_usd'] = st.sidebar.number_input("Max Drawdown limit ($)", value=config.get('max_drawdown_usd', 20.0), step=1.0)

st.sidebar.header("🚑 3. โหมดแก้เกม (DCA)")
config['max_positions'] = int(st.sidebar.number_input("Max Positions", value=config.get('max_positions', 3), step=1))
config['dca_step_usd'] = st.sidebar.number_input("DCA Step (USD)", value=config.get('dca_step_usd', 3.5), step=0.5)
config['dca_lot_mult'] = st.sidebar.number_input("DCA Lot Multiplier", value=config.get('dca_lot_mult', 1.5), step=0.1)

st.sidebar.header("🎯 4. เงื่อนไข X-Sniper V6")
config['max_gap_usd'] = st.sidebar.number_input("Max Gap (USD)", value=config.get('max_gap_usd', 7.0), step=0.5)
config['min_bounce_ratio'] = st.sidebar.number_input("Min Bounce Ratio", value=config.get('min_bounce_ratio', 0.40), step=0.05)

st.sidebar.header("📈 5. ระบบกรองเทรนด์ (EMA 200)")
config['use_ema_filter'] = st.sidebar.checkbox("เปิดใช้ EMA 200 Filter", value=config.get('use_ema_filter', True))

st.sidebar.header("🛡️ 6. ระบบกันหน้าทุน (Trailing Stop)")
config['use_trailing'] = st.sidebar.checkbox("เปิดใช้งาน Trailing Stop", value=config.get('use_trailing', False))
config['trailing_start_usd'] = st.sidebar.number_input("เริ่มล็อกเมื่อกำไรถึง ($)", value=config.get('trailing_start_usd', 3.0), step=0.5)
config['trailing_step_usd'] = st.sidebar.number_input("ระยะถอยย่อ (Trailing Step $)", value=config.get('trailing_step_usd', 1.0), step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("⏰ 7. ตั้งเวลาทำงาน & ปิดจบวัน")
config['use_time_filter'] = st.sidebar.checkbox("จำกัดเวลาเข้าไม้แรก", value=config.get('use_time_filter', False))
start_str = config.get('start_time', '08:00')
end_str = config.get('end_time', '22:00')
start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
t_start = st.sidebar.time_input("เวลาเริ่มเทรด", value=start_t)
t_end = st.sidebar.time_input("เวลาหยุดเทรด", value=end_t)
config['start_time'] = t_start.strftime('%H:%M')
config['end_time'] = t_end.strftime('%H:%M')

st.sidebar.markdown("**🧹 โหมดจัดการออเดอร์ก่อนหมดวัน**")
config['enable_clear_mode'] = st.sidebar.checkbox("พยายามปิดเท่าทุนเมื่อนอกเวลา", value=config.get('enable_clear_mode', True))
config['enable_force_close'] = st.sidebar.checkbox("บังคับตัดออเดอร์ (Force Close)", value=config.get('enable_force_close', False))
force_close_str = config.get('force_close_time', '23:50')
force_t = datetime.datetime.strptime(force_close_str, '%H:%M').time()
t_force = st.sidebar.time_input("เวลาบังคับตัดจบ", value=force_t)
config['force_close_time'] = t_force.strftime('%H:%M')

st.sidebar.markdown("---")
# 💡 [อัปเกรด] ฟีเจอร์ระดับโปร
st.sidebar.header("🔥 8. ฟีเจอร์ระดับโปร (Pro Features)")
config['max_spread_points'] = st.sidebar.number_input("สเปรดสูงสุดที่ยอมรับได้ (Points)", value=config.get('max_spread_points', 200), step=10)
st.sidebar.caption("ป้องกันการเข้าออเดอร์ตอนข่าวแรงหรือช่วงข้ามวัน")

config['use_auto_lot'] = st.sidebar.checkbox("คำนวณ Lot อัตโนมัติตามทุน", value=config.get('use_auto_lot', False))
config['auto_lot_step'] = st.sidebar.number_input("ทุกๆ เงินทุน ($) เท่ากับ 1 Base Lot", value=config.get('auto_lot_step', 100.0), step=50.0)
st.sidebar.caption("ตัวอย่าง: ทุน $200 บอทจะใช้ Lot = Start Lot x 2")

st.sidebar.markdown("---")
st.sidebar.header("📱 9. Telegram")
config['telegram_enabled'] = st.sidebar.checkbox("แจ้งเตือน Telegram", value=config.get('telegram_enabled', False))
config['telegram_token'] = st.sidebar.text_input("Bot Token", value=config.get('telegram_token', ""), type="password")
config['telegram_chat_id'] = st.sidebar.text_input("Chat ID", value=config.get('telegram_chat_id', ""))

save_json(CONFIG_FILE, config)

# ==========================================
# 🚀 ส่วนควบคุมหลัก (Header)
# ==========================================
c_title, c_status, c_switch = st.columns([2, 2, 1])
c_title.title("🎛️ MT5 Pro Sniper Bot")

with c_status:
    if config.get("bot_status") == "running":
        st.success(f"🟢 **กำลังทำงาน:** {config.get('current_activity', 'เตรียมความพร้อม...')}")
    else:
        st.warning("🔴 **หยุดทำงาน (Standby)**")

with c_switch:
    is_running = config.get("bot_status") == "running"
    toggle_bot = st.toggle("🚀 เปิดระบบบอท", value=is_running)
    if toggle_bot != is_running:
        config["bot_status"] = "running" if toggle_bot else "stopped"
        save_json(CONFIG_FILE, config)
        st.rerun()

st.markdown("---")

# ==========================================
# 🗂️ ส่วนแสดงผล (Tabs)
# ==========================================
tab1, tab2 = st.tabs(["📡 เรดาร์เรียลไทม์ (Live Monitor)", "📊 สรุปประวัติการเทรด (History & PnL)"])

with tab1:
    auto_refresh = st.toggle("🔄 เปิดโหมดดูเรียลไทม์ (Auto-Refresh 1 วินาที)")
    refresh_rate = 1 if auto_refresh else None

    @st.fragment(run_every=refresh_rate)
    def render_live_dashboard():
        live_data = load_json(LIVE_STATUS_FILE)
        if not live_data:
            st.info("⏳ รอรับข้อมูลสแกนจากบอท...")
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📌 สัญลักษณ์", live_data.get("symbol", "-"))
        c2.metric("💰 ราคาปัจจุบัน", f"{live_data.get('current_price', 0):.2f}")
        c3.metric("🎯 โหมดปัจจุบัน", live_data.get("mode", "-"))
        c4.caption(f"⏱️ อัปเดตล่าสุด: {live_data.get('last_update', '-')}")

        details = live_data.get("details", {})
        
        if live_data.get("mode") == "SCANNING":
            pattern = details.get("pattern", "")
            if "Buy" in pattern: st.success(pattern)
            elif "Sell" in pattern: st.error(pattern)
            elif "บล็อก" in pattern or "นอกเวลา" in pattern or "สเปรด" in pattern: st.warning(pattern)
            else: st.info(pattern)
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("เทรนด์หลัก (EMA 200)", f"{details.get('ema_200', 0):.2f}")
            sc2.metric("สเปรดปัจจุบัน", f"{details.get('current_spread', 0):.0f} Points")
            sc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config['start_lot'])}")
            
            bounce_ratio = details.get("bounce_ratio", 0)
            target_bounce = details.get("target_bounce", 0.4)
            progress_val = max(0.0, min((bounce_ratio / target_bounce) if target_bounce > 0 else 0, 1.0))
            
            st.write(f"**แรงเด้งกลับ (Bounce Ratio):** {bounce_ratio:.2f} / เป้าหมาย: {target_bounce:.2f}")
            st.progress(progress_val)
            
        elif live_data.get("mode") == "HOLDING":
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("จำนวนไม้สะสม", f"{details.get('trades_count', 0)} / {config['max_positions']}")
            
            pnl = details.get("total_pnl", 0)
            target = details.get("tp_target", 0)
            hc2.metric("กำไร/ขาดทุนสุทธิ (รวม Swap)", f"${pnl:.2f}", f"เป้าปิด: ${target:.2f}")
            
            drag = details.get("drag_usd", 0)
            dca_step = details.get("dca_step_target", 0)
            hc3.metric("โดนลากล่าสุด", f"{drag:.2f} USD", f"จุดยิงแก้: {dca_step:.2f} USD")
            
            st.write("**ความคืบหน้าเข้าสู่เป้าหมาย (TP):**")
            tp_progress = min(max(pnl / target, 0.0), 1.0) if target > 0 else 0
            st.progress(tp_progress)

    render_live_dashboard()

with tab2:
    hist_data = load_json(HISTORY_FILE)
    if isinstance(hist_data, list) and len(hist_data) > 0:
        df_hist = pd.DataFrame(hist_data)
        total_profit = df_hist['กำไร/ขาดทุน'].sum()
        total_trades = len(df_hist)
        win_count = len(df_hist[df_hist['กำไร/ขาดทุน'] > 0])
        loss_count = total_trades - win_count
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
        
        hc1, hc2, hc3, hc4 = st.columns(4)
        hc1.metric("💰 กำไรสุทธิรวม", f"${total_profit:.2f}")
        hc2.metric("🧺 จำนวนรอบเทรด", f"{total_trades} รอบ")
        hc3.metric("🎯 อัตราชนะ (Win Rate)", f"{win_rate:.0f}%")
        hc4.metric("📊 ชนะ / แพ้", f"{win_count} / {loss_count}")
        
        st.markdown("#### 📝 ตารางประวัติการปิดตะกร้า")
        df_hist_reversed = df_hist.iloc[::-1].reset_index(drop=True)
        st.dataframe(df_hist_reversed, use_container_width=True)
        
        if st.button("🗑️ ล้างประวัติการเทรด"):
            save_json(HISTORY_FILE, [])
            st.rerun()
    else:
        st.info("📭 ยังไม่มีประวัติการเทรด")