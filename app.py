import streamlit as st
import pandas as pd
import json
import os
import time
import datetime
import core_db
import plotly.graph_objects as go 

# ==========================================
# 🛠️ 1. กำหนดตัวแปรและฟังก์ชันจัดการฐานข้อมูล
# ==========================================
CONFIG_FILE = "config"
LIVE_STATUS_FILE = "live_status"
HISTORY_FILE = "trade_history.json" 

def load_json(key):
    return core_db.load_db(key)

def save_json(key, data):
    core_db.save_db(key, data)

config = load_json(CONFIG_FILE)
if not config:
    config = {}

# ==========================================
# 🎨 ตั้งค่าหน้าเว็บ (Compact Layout)
# ==========================================
st.set_page_config(page_title="MT5 Pro Sniper Bot", layout="wide", initial_sidebar_state="expanded")

# ----------------------------------------
# 🔒 ระบบตรวจสอบรหัสผ่าน (Login System)
# ----------------------------------------
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center;'>🔒 เข้าสู่ระบบ MT5 Pro Bot</h2>", unsafe_allow_html=True)
            st.info("💡 รหัสผ่านเริ่มต้นคือ: **admin123**")
            pwd = st.text_input("🔑 รหัสผ่าน (Password):", type="password")
            if st.button("🔓 เข้าสู่ระบบ (Login)", use_container_width=True):
                if pwd == config.get("web_password", "admin123"):
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ รหัสผ่านไม่ถูกต้อง! (Incorrect Password)")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# ⚙️ เมนูตั้งค่าพารามิเตอร์ (Sidebar)
# ==========================================
st.sidebar.header("⚙️ 1. ตั้งค่าพื้นฐาน")
config['symbol'] = st.sidebar.text_input("Symbol", config.get('symbol', 'XAUUSDm'))
config['magic_number'] = int(st.sidebar.number_input("Magic Number", value=config.get('magic_number', 888888), step=1))
tf_options = {1: "M1", 5: "M5", 15: "M15", 16385: "H1"}
current_tf_name = tf_options.get(config.get('timeframe', 1), "M1")
selected_tf_name = st.sidebar.selectbox("Timeframe", list(tf_options.values()), index=list(tf_options.values()).index(current_tf_name))
config['timeframe'] = [k for k, v in tf_options.items() if v == selected_tf_name][0]

st.sidebar.header("🌟 2. การตั้งค่ากลยุทธ์")
config['start_lot'] = st.sidebar.number_input("Start Lot (Base)", value=config.get('start_lot', 0.01), step=0.01)
config['quick_profit_target'] = st.sidebar.number_input("Quick Profit Target ($)", value=config.get('quick_profit_target', 5.0), step=0.5)
config['max_drawdown_usd'] = st.sidebar.number_input("Max Drawdown limit ($)", value=config.get('max_drawdown_usd', 70.0), step=1.0)

st.sidebar.header("🚑 3. โหมดแก้เกม (DCA)")
config['max_positions'] = int(st.sidebar.number_input("Max Positions", value=config.get('max_positions', 3), step=1))
config['dca_step_usd'] = st.sidebar.number_input("DCA Step (USD)", value=config.get('dca_step_usd', 250.0), step=10.0)
config['dca_lot_mult'] = st.sidebar.number_input("DCA Lot Multiplier", value=config.get('dca_lot_mult', 1.5), step=0.1)
config['use_smart_dca'] = st.sidebar.checkbox("🧠 เปิดใช้ Smart DCA", value=config.get('use_smart_dca', True))

st.sidebar.header("🎯 4. เงื่อนไข X-Sniper V6")
config['max_gap_usd'] = st.sidebar.number_input("Max Gap (USD)", value=config.get('max_gap_usd', 400.0), step=10.0)
config['min_bounce_ratio'] = st.sidebar.number_input("Min Bounce Ratio", value=config.get('min_bounce_ratio', 0.35), step=0.05)

# 💡 [เพิ่มใหม่] Trailing Entry
st.sidebar.header("🎯 4.1 Trailing Entry (จ้องตะปบเข้า)")
config['use_trailing_entry'] = st.sidebar.checkbox("เปิดใช้ Trailing Entry", value=config.get('use_trailing_entry', False))
config['trailing_entry_step_usd'] = st.sidebar.number_input("ระยะงัดกลับถึงจะยิง ($)", value=config.get('trailing_entry_step_usd', 1.0), step=0.5)
st.sidebar.caption("ถ้าราคาไหลต่อ บอทจะเลื่อนจุดรอเข้าตามไปเรื่อยๆ จนกว่ากราฟจะงัดกลับตามระยะนี้ถึงจะเข้าออเดอร์")

st.sidebar.header("📈 5. ระบบกรองเทรนด์ (EMA 200)")
config['use_ema_filter'] = st.sidebar.checkbox("เปิดใช้ EMA 200 Filter", value=config.get('use_ema_filter', True))

st.sidebar.header("🛡️ 6. ระบบกันหน้าทุน (Trailing Stop)")
config['use_trailing'] = st.sidebar.checkbox("เปิดใช้งาน Trailing Stop", value=config.get('use_trailing', True))
config['trailing_start_usd'] = st.sidebar.number_input("เริ่มล็อกเมื่อกำไรถึง ($)", value=config.get('trailing_start_usd', 3.0), step=0.5)
config['trailing_step_usd'] = st.sidebar.number_input("ระยะถอยย่อ (Trailing Step $)", value=config.get('trailing_step_usd', 1.0), step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("⏰ 7. ตั้งเวลาทำงาน")
config['use_time_filter'] = st.sidebar.checkbox("จำกัดเวลาเข้าไม้แรก", value=config.get('use_time_filter', False))
start_str = config.get('start_time', '08:00')
end_str = config.get('end_time', '22:00')
start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
t_start = st.sidebar.time_input("เวลาเริ่มเทรด", value=start_t)
t_end = st.sidebar.time_input("เวลาหยุดเทรด", value=end_t)
config['start_time'] = t_start.strftime('%H:%M')
config['end_time'] = t_end.strftime('%H:%M')
config['enable_clear_mode'] = st.sidebar.checkbox("พยายามปิดเท่าทุนเมื่อนอกเวลา", value=config.get('enable_clear_mode', True))
config['enable_force_close'] = st.sidebar.checkbox("บังคับตัดออเดอร์ (Force Close)", value=config.get('enable_force_close', False))
force_close_str = config.get('force_close_time', '23:50')
force_t = datetime.datetime.strptime(force_close_str, '%H:%M').time()
t_force = st.sidebar.time_input("เวลาบังคับตัดจบ", value=force_t)
config['force_close_time'] = t_force.strftime('%H:%M')

st.sidebar.markdown("---")
st.sidebar.header("🔥 8. ฟีเจอร์ระดับโปร")
config['max_spread_points'] = st.sidebar.number_input("สเปรดสูงสุด (Points)", value=config.get('max_spread_points', 400), step=50)
config['use_atr_filter'] = st.sidebar.checkbox("เปิดใช้ ATR Filter", value=config.get('use_atr_filter', True))
config['max_atr_value'] = st.sidebar.number_input("ค่า ATR สูงสุด", value=config.get('max_atr_value', 150.0), step=10.0)
config['use_news_filter'] = st.sidebar.checkbox("หลบข่าวกล่องแดง", value=config.get('use_news_filter', True))

st.sidebar.markdown("---")
st.sidebar.header("📱 9. Telegram")
config['telegram_enabled'] = st.sidebar.checkbox("แจ้งเตือน Telegram", value=config.get('telegram_enabled', False))
config['telegram_token'] = st.sidebar.text_input("Bot Token", value=config.get('telegram_token', ""), type="password")
config['telegram_chat_id'] = st.sidebar.text_input("Chat ID", value=config.get('telegram_chat_id', ""))

st.sidebar.markdown("---")
st.sidebar.header("🔒 10. ความปลอดภัย (Security)")
config['web_password'] = st.sidebar.text_input("เปลี่ยนรหัสผ่านเข้าเว็บ", value=config.get('web_password', 'admin123'), type="password")
st.sidebar.caption("ตั้งรหัสผ่านที่เดายากๆ เพื่อป้องกันคนนอกเข้ามาปรับบอท")
save_json(CONFIG_FILE, config)

# ==========================================
# 🚀 ส่วนควบคุมหลัก (Header)
# ==========================================
c_title, c_empty, c_switch = st.columns([2, 2, 1])
c_title.title("🎛️ MT5 Pro Sniper Bot")

with c_switch:
    is_running = config.get("bot_status") == "running"
    toggle_bot = st.toggle("🚀 เปิดระบบบอท", value=is_running)
    if toggle_bot != is_running:
        config["bot_status"] = "running" if toggle_bot else "stopped"
        save_json(CONFIG_FILE, config)
        st.rerun()

st.markdown("---")

btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
if btn_c1.button("💥 รวบปิดทุกไม้ทันที", type="primary", use_container_width=True):
    save_json("ui_command", {"action": "PANIC_CLOSE"})
    st.toast("ส่งคำสั่งปิดทุกไม้เรียบร้อยแล้ว!", icon="🚨")

if config.get("use_smart_dca", True):
    if btn_c2.button("🛑 ระงับการยิงไม้แก้", use_container_width=True):
        save_json("ui_command", {"action": "PAUSE_DCA"})
        st.toast("ส่งคำสั่งระงับ DCA ชั่วคราว!", icon="🛑")
else:
    if btn_c2.button("▶️ กลับมายิงไม้แก้", use_container_width=True):
        save_json("ui_command", {"action": "RESUME_DCA"})
        st.toast("เปิดระบบ DCA ตามปกติ!", icon="▶️")

st.markdown("---")

tab1, tab2 = st.tabs(["📡 เรดาร์เรียลไทม์", "📊 ประวัติการเทรด"])

with tab1:
    auto_refresh = st.toggle("🔄 เปิดโหมดดูเรียลไทม์ (Auto-Refresh 1 วินาที)")
    refresh_rate = 1 if auto_refresh else None

    @st.fragment(run_every=refresh_rate)
    def render_live_dashboard():
        live_data = load_json(LIVE_STATUS_FILE)
        fresh_config = load_json(CONFIG_FILE)
        # 💡 นำแถบสีเขียวมาแสดงผลแบบ Real-time ตรงนี้
        if fresh_config.get("bot_status") == "running":
            st.success(f"🟢 **กำลังทำงาน:** {fresh_config.get('current_activity', 'เตรียมความพร้อม...')}")
        else:
            st.warning("🔴 **หยุดทำงาน (Standby)**")

        if not live_data:
            st.info("⏳ รอรับข้อมูลสแกนจากบอท...")
            return

        st.markdown("##### 💳 ข้อมูลบัญชี (Account Info)")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("ยอดเงินคงเหลือ", f"${live_data.get('balance', 0.0):.2f}")
        a2.metric("ทุนสุทธิ (Equity)", f"${live_data.get('equity', 0.0):.2f}")
        a3.metric("📌 สัญลักษณ์", live_data.get("symbol", "-"))
        a4.metric("💰 ราคาปัจจุบัน", f"{live_data.get('current_price', 0):.2f}")
        
        st.markdown("---")
        mode = live_data.get('mode', '-')
        if mode == "TRAILING_ENTRY":
            st.markdown(f"##### 🎯 สถานะบอท: <span style='color:orange;'>{mode} (กำลังง้างรอเข้าออเดอร์)</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"##### 📡 สถานะบอท: {mode}")

        details = live_data.get("details", {})
        
        if live_data.get("mode") == "SCANNING":
            pattern = details.get("pattern", "")
            if "Buy" in pattern: st.success(pattern)
            elif "Sell" in pattern: st.error(pattern)
            elif "บล็อก" in pattern or "สเปรด" in pattern or "ข่าว" in pattern: st.warning(pattern)
            else: st.info(pattern)
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("เทรนด์หลัก (EMA 200)", f"{details.get('ema_200', 0):.2f}")
            sc2.metric("สเปรดปัจจุบัน", f"{details.get('current_spread', 0):.0f} Points")
            sc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config.get('start_lot', 0.01))}")
            
        elif live_data.get("mode") == "TRAILING_ENTRY":
            st.warning(details.get("pattern", "กำลังตามรอย..."))
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("จุดต่ำสุด/สูงสุด ที่เจอ", f"{details.get('extreme_price', 0):.2f}")
            tc2.metric("ระยะงัดกลับ (รอคอนเฟิร์ม)", f"{details.get('distance_to_entry', 0):.2f} / {details.get('target_step', 0):.2f} USD")
            tc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config.get('start_lot', 0.01))}")
            
            progress = min(max(details.get('distance_to_entry', 0) / details.get('target_step', 1), 0.0), 1.0)
            st.write("**ความคืบหน้าการงัดกลับ (Bounce Tracking):**")
            st.progress(progress)

        elif live_data.get("mode") == "HOLDING":
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("จำนวนไม้สะสม", f"{details.get('trades_count', 0)} / {config.get('max_positions', 3)}")
            pnl = details.get("total_pnl", 0)
            target = details.get("tp_target", 0)
            hc2.metric("กำไร/ขาดทุนสุทธิ (รวม Swap)", f"${pnl:.2f}", f"เป้าปิด: ${target:.2f}")
            drag = details.get("drag_usd", 0)
            dca_step = details.get("dca_step_target", 0)
            hc3.metric("โดนลากล่าสุด", f"{drag:.2f} USD", f"จุดยิงแก้: {dca_step:.2f} USD")
            
            st.write("**ความคืบหน้าเข้าสู่เป้าหมาย (TP):**")
            tp_progress = min(max(pnl / target, 0.0), 1.0) if target > 0 else 0
            st.progress(tp_progress)

        chart_data = load_json("chart_data")
        if chart_data and len(chart_data) > 0:
            df_c = pd.DataFrame(chart_data)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=df_c['time'], open=df_c['open'], high=df_c['high'], low=df_c['low'], close=df_c['close'], name='Price'))
            if 'ema_200' in df_c.columns:
                fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema_200'], mode='lines', line=dict(color='orange', width=2), name='EMA 200'))
            fig.update_layout(title=f"📊 กราฟราคาล่าสุด {live_data.get('symbol', '')} พร้อม EMA 200", yaxis_title="Price", xaxis_rangeslider_visible=False, height=450, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

    render_live_dashboard()

with tab2:
    def load_history():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding='utf-8') as f: return json.load(f)
            except: pass
        return []
    hist_data = load_history()
    if isinstance(hist_data, list) and len(hist_data) > 0:
        df_hist = pd.DataFrame(hist_data)
        total_profit = df_hist['กำไร/ขาดทุน'].sum()
        total_trades = len(df_hist)
        win_count = len(df_hist[df_hist['กำไร/ขาดทุน'] > 0])
        st.metric("💰 กำไรสุทธิรวม", f"${total_profit:.2f}")
        df_hist_reversed = df_hist.iloc[::-1].reset_index(drop=True)
        st.dataframe(df_hist_reversed, use_container_width=True)