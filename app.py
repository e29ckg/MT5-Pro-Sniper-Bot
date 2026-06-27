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

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center;'>🔒 เข้าสู่ระบบ MT5 Pro Bot</h2>", unsafe_allow_html=True)
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
# 🗂️ 2. ระบบ Profile Selector (อัจฉริยะ)
# ==========================================
st.sidebar.header("🏆 เลือกกลยุทธ์ (Trading Profile)")

PROFILES = {
    "M1 Sniper (สายซิ่ง)": {
        "timeframe": 1, "quick_profit_target": 2.0, "max_drawdown_usd": 20.0,
        "dca_step_usd": 4.5, "max_gap_usd": 7.0, "min_bounce_ratio": 0.35,
        "trailing_start_usd": 2.0, "trailing_step_usd": 1.0, "max_atr_value": 2.0
    },
    "M15 Swing (เน้นชัวร์)": {
        "timeframe": 15, "quick_profit_target": 8.0, "max_drawdown_usd": 40.0,
        "dca_step_usd": 15.0, "max_gap_usd": 20.0, "min_bounce_ratio": 0.30,
        "trailing_start_usd": 6.0, "trailing_step_usd": 2.0, "max_atr_value": 4.0
    },
    "กำหนดเอง (Custom)": None
}

# 💡 เซตค่าเริ่มต้นครั้งแรก ถ้ายังไม่มีในฐานข้อมูล
if "current_profile" not in config:
    config["current_profile"] = "M1 Sniper (สายซิ่ง)"
    for k, v in PROFILES["M1 Sniper (สายซิ่ง)"].items():
        config[k] = v
    save_json(CONFIG_FILE, config)

if "profile_selector" not in st.session_state:
    st.session_state.profile_selector = config["current_profile"]

# ฟังก์ชันจัดการเมื่อเปลี่ยนโปรไฟล์
def on_profile_change():
    new_prof = st.session_state.profile_selector
    config["current_profile"] = new_prof
    if PROFILES.get(new_prof) is not None:
        for k, v in PROFILES[new_prof].items():
            config[k] = v
    save_json(CONFIG_FILE, config)

# ฟังก์ชันจัดการเมื่อผู้ใช้ปรับตัวเลข "ด้วยตัวเอง" (เปลี่ยนเป็น Custom ทันที)
def on_param_change():
    st.session_state.profile_selector = "กำหนดเอง (Custom)"
    config["current_profile"] = "กำหนดเอง (Custom)"
    save_json(CONFIG_FILE, config)

selected_profile = st.sidebar.selectbox(
    "เลือกโหมดการเทรด", 
    list(PROFILES.keys()), 
    key="profile_selector",
    on_change=on_profile_change
)

if selected_profile != "กำหนดเอง (Custom)":
    st.sidebar.success(f"✅ โหลดการตั้งค่า: {selected_profile}")
else:
    st.sidebar.info("🛠️ โหมดกำหนดเอง (แก้ไขตัวเลขได้อิสระ)")

st.sidebar.markdown("---")

# ==========================================
# ⚙️ เมนูตั้งค่าพารามิเตอร์ (Sidebar)
# ==========================================
st.sidebar.header("⚙️ 1. ตั้งค่าพื้นฐาน")
config['symbol'] = st.sidebar.text_input("Symbol", config.get('symbol', 'XAUUSDm'))
config['magic_number'] = int(st.sidebar.number_input("Magic Number", value=config.get('magic_number', 888888), step=1))

tf_options = {1: "M1", 5: "M5", 15: "M15", 16385: "H1"}
current_tf_name = tf_options.get(config.get('timeframe', 1), "M1")
# 💡 สังเกตว่าผมใส่ on_change=on_param_change ไว้ทุกช่อง
selected_tf_name = st.sidebar.selectbox("Timeframe", list(tf_options.values()), index=list(tf_options.values()).index(current_tf_name), on_change=on_param_change)
config['timeframe'] = [k for k, v in tf_options.items() if v == selected_tf_name][0]

st.sidebar.header("🌟 2. การตั้งค่ากลยุทธ์")
config['initial_balance'] = st.sidebar.number_input("เงินทุนเริ่มต้น ($) [Initial Balance]", value=config.get('initial_balance', 100.0), step=10.0, on_change=on_param_change)
config['start_lot'] = st.sidebar.number_input("Start Lot (Base)", value=config.get('start_lot', 0.01), step=0.01, on_change=on_param_change)
config['quick_profit_target'] = st.sidebar.number_input("Quick Profit Target ($)", value=config.get('quick_profit_target', 5.0), step=0.5, on_change=on_param_change)
config['max_drawdown_usd'] = st.sidebar.number_input("Max Drawdown limit ($)", value=config.get('max_drawdown_usd', 70.0), step=1.0, on_change=on_param_change)

st.sidebar.header("🛡️ 2.1 วินัยการเทรดประจำวัน")
config['daily_profit_target'] = st.sidebar.number_input("เป้ากำไรรายวัน ($) [พักเมื่อครบ]", value=config.get('daily_profit_target', 50.0), step=5.0, on_change=on_param_change)
config['daily_loss_limit'] = st.sidebar.number_input("ลิมิตขาดทุนรายวัน ($) [เลิกเมื่อถึง]", value=config.get('daily_loss_limit', 30.0), step=5.0, on_change=on_param_change)

st.sidebar.header("🚑 3. โหมดแก้เกม (DCA)")
config['max_positions'] = int(st.sidebar.number_input("Max Positions", value=config.get('max_positions', 3), step=1, on_change=on_param_change))
config['dca_step_usd'] = st.sidebar.number_input("DCA Step (USD)", value=config.get('dca_step_usd', 250.0), step=10.0, on_change=on_param_change)
config['dca_lot_mult'] = st.sidebar.number_input("DCA Lot Multiplier", value=config.get('dca_lot_mult', 1.5), step=0.1, on_change=on_param_change)
config['use_smart_dca'] = st.sidebar.checkbox("🧠 เปิดใช้ Smart DCA", value=config.get('use_smart_dca', True), on_change=on_param_change)

st.sidebar.header("🎯 4. เงื่อนไข X-Sniper V6")
config['max_gap_usd'] = st.sidebar.number_input("Max Gap (USD)", value=config.get('max_gap_usd', 400.0), step=10.0, on_change=on_param_change)
config['min_bounce_ratio'] = st.sidebar.number_input("Min Bounce Ratio", value=config.get('min_bounce_ratio', 0.35), step=0.05, on_change=on_param_change)

st.sidebar.header("🎯 4.1 Trailing Entry")
config['use_trailing_entry'] = st.sidebar.checkbox("เปิดใช้ Trailing Entry", value=config.get('use_trailing_entry', False), on_change=on_param_change)
config['trailing_entry_step_usd'] = st.sidebar.number_input("ระยะงัดกลับถึงจะยิง ($)", value=config.get('trailing_entry_step_usd', 1.0), step=0.5, on_change=on_param_change)

st.sidebar.header("📈 5. ระบบกรองเทรนด์ (EMA 200)")
config['use_ema_filter'] = st.sidebar.checkbox("เปิดใช้ EMA 200 Filter (จาก M5)", value=config.get('use_ema_filter', True), on_change=on_param_change)

st.sidebar.header("🛡️ 6. ระบบกันหน้าทุน (Trailing Stop)")
config['use_trailing'] = st.sidebar.checkbox("เปิดใช้งาน Trailing Stop", value=config.get('use_trailing', True), on_change=on_param_change)
config['trailing_start_usd'] = st.sidebar.number_input("เริ่มล็อกเมื่อกำไรถึง ($)", value=config.get('trailing_start_usd', 3.0), step=0.5, on_change=on_param_change)
config['trailing_step_usd'] = st.sidebar.number_input("ระยะถอยย่อ (Trailing Step $)", value=config.get('trailing_step_usd', 1.0), step=0.5, on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("⏰ 7. ตั้งเวลาทำงาน")
config['use_time_filter'] = st.sidebar.checkbox("จำกัดเวลาเข้าไม้แรก", value=config.get('use_time_filter', False), on_change=on_param_change)

start_str = config.get('start_time', '08:00')
end_str = config.get('end_time', '22:00')
start_t = datetime.datetime.strptime(start_str, '%H:%M').time()
end_t = datetime.datetime.strptime(end_str, '%H:%M').time()
t_start = st.sidebar.time_input("เวลาเริ่มเทรด", value=start_t, on_change=on_param_change)
t_end = st.sidebar.time_input("เวลาหยุดเทรด", value=end_t, on_change=on_param_change)
config['start_time'] = t_start.strftime('%H:%M')
config['end_time'] = t_end.strftime('%H:%M')

config['enable_clear_mode'] = st.sidebar.checkbox("พยายามปิดเท่าทุนเมื่อนอกเวลา", value=config.get('enable_clear_mode', True), on_change=on_param_change)
config['enable_force_close'] = st.sidebar.checkbox("บังคับตัดออเดอร์", value=config.get('enable_force_close', False), on_change=on_param_change)

force_close_str = config.get('force_close_time', '23:50')
force_t = datetime.datetime.strptime(force_close_str, '%H:%M').time()
t_force = st.sidebar.time_input("เวลาบังคับตัดจบ", value=force_t, on_change=on_param_change)
config['force_close_time'] = t_force.strftime('%H:%M')

st.sidebar.markdown("---")
st.sidebar.header("🔥 8. ฟีเจอร์ระดับโปร")
config['max_spread_points'] = st.sidebar.number_input("สเปรดสูงสุด (Points)", value=config.get('max_spread_points', 400), step=50, on_change=on_param_change)
config['use_atr_filter'] = st.sidebar.checkbox("เปิดใช้ ATR Filter", value=config.get('use_atr_filter', True), on_change=on_param_change)
config['max_atr_value'] = st.sidebar.number_input("ค่า ATR สูงสุด", value=config.get('max_atr_value', 150.0), step=10.0, on_change=on_param_change)
config['use_news_filter'] = st.sidebar.checkbox("หลบข่าวกล่องแดง", value=config.get('use_news_filter', True), on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("📱 9. Telegram")
config['telegram_enabled'] = st.sidebar.checkbox("แจ้งเตือน Telegram", value=config.get('telegram_enabled', False))
config['telegram_token'] = st.sidebar.text_input("Bot Token", value=config.get('telegram_token', ""), type="password")
config['telegram_chat_id'] = st.sidebar.text_input("Chat ID", value=config.get('telegram_chat_id', ""))

st.sidebar.markdown("---")
st.sidebar.header("🔒 10. ความปลอดภัย")
config['web_password'] = st.sidebar.text_input("เปลี่ยนรหัสผ่าน", value=config.get('web_password', 'admin123'), type="password")

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

# 🚨 ระบบปุ่มฉุกเฉิน (เพิ่มระบบยืนยันก่อนปิดป้องกันมือกดลั่น)
if "confirm_panic" not in st.session_state:
    st.session_state.confirm_panic = False

btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)

with btn_c1:
    if not st.session_state.confirm_panic:
        if st.button("💥 รวบปิดทุกไม้ทันที", type="primary", use_container_width=True):
            st.session_state.confirm_panic = True
            st.rerun()
    else:
        st.error("⚠️ แน่ใจหรือไม่?")
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ ยืนยัน", type="primary", use_container_width=True):
            save_json("ui_command", {"action": "PANIC_CLOSE"})
            st.toast("ส่งคำสั่งปิดทุกไม้เรียบร้อยแล้ว!", icon="🚨")
            st.session_state.confirm_panic = False
            st.rerun()
        if cc2.button("❌ ยกเลิก", use_container_width=True):
            st.session_state.confirm_panic = False
            st.rerun()

if config.get("use_smart_dca", True):
    if btn_c2.button("🛑 ระงับการยิงไม้แก้", use_container_width=True):
        save_json("ui_command", {"action": "PAUSE_DCA"})
        st.toast("ส่งคำสั่งระงับ DCA ชั่วคราว!", icon="🛑")
else:
    if btn_c2.button("▶️ กลับมายิงไม้แก้", use_container_width=True):
        save_json("ui_command", {"action": "RESUME_DCA"})
        st.toast("เปิดระบบ DCA ตามปกติ!", icon="▶️")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📡 เรดาร์เรียลไทม์", "📊 ประวัติการเทรด", "🔬 จำลอง Backtest (ด้วยค่าจริง)"])

with tab1:
    auto_refresh = st.toggle("🔄 เปิดโหมดดูเรียลไทม์ (Auto-Refresh 1 วินาที)")
    refresh_rate = 1 if auto_refresh else None

    @st.fragment(run_every=refresh_rate)
    def render_live_dashboard():
        live_data = load_json(LIVE_STATUS_FILE)
        fresh_config = load_json(CONFIG_FILE)
        
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
        
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("🏆 โปรไฟล์ปัจจุบัน", config.get("current_profile", "Custom").split(" ")[0])
        
        # 🌟 แก้ไข: ดึงเทรนด์จาก M5 แทน H1
        trend_m5 = live_data.get("details", {}).get("trend_m5", "รอข้อมูล...")
        b2.metric("📈 เทรนด์หลัก (M5)", f"🔥 {trend_m5}" if trend_m5 == "UP" else f"💧 {trend_m5}")
        
        if mode == "TRAILING_ENTRY":
            b3.markdown(f"**สถานะบอท:** <br><span style='color:orange;'>🎯 {mode} (กำลังง้าง)</span>", unsafe_allow_html=True)
        else:
            b3.markdown(f"**สถานะบอท:** <br>📡 {mode}", unsafe_allow_html=True)
            
        b4.caption(f"⏱️ อัปเดตล่าสุด:<br>{live_data.get('last_update', '-')}", unsafe_allow_html=True)

        details = live_data.get("details", {})
        
        if live_data.get("mode") == "SCANNING":
            pattern = details.get("pattern", "")
            if "Buy" in pattern: st.success(pattern)
            elif "Sell" in pattern: st.error(pattern)
            elif "บล็อก" in pattern or "สเปรด" in pattern or "ข่าว" in pattern: st.warning(pattern)
            elif "พักเทรด" in pattern: st.error(pattern) # 🌟 เพิ่มสีแดงให้สถานะพักเทรดรายวัน
            else: st.info(pattern)
            
            sc1, sc2, sc3 = st.columns(3)
            # 🌟 แก้ไข: ดึงค่าเส้นประคองเป็น M5
            sc1.metric("เส้นประคอง (EMA M5)", f"{details.get('ema_m5', details.get('ema_200', 0)):.2f}")
            sc2.metric("สเปรดปัจจุบัน", f"{details.get('current_spread', 0):.0f} Points")
            sc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config.get('start_lot', 0.01))}")
            
        elif live_data.get("mode") == "TRAILING_ENTRY":
            st.warning(details.get("pattern", "กำลังตามรอย..."))
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("จุดต่ำสุด/สูงสุด ที่เจอ", f"{details.get('extreme_price', 0):.2f}")
            tc2.metric("ระยะงัดกลับ (รอคอนเฟิร์ม)", f"{details.get('distance_to_entry', 0):.2f} / {details.get('target_step', 0):.2f} USD")
            tc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config.get('start_lot', 0.01))}")
            
            progress = min(max(details.get('distance_to_entry', 0) / details.get('target_step', 1), 0.0), 1.0)
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

        # ----------------------------------------
        # 📈 วาดกราฟแท่งเทียน (Live Candlestick) พร้อมจุดเข้า
        # ----------------------------------------
        chart_data = load_json("chart_data")
        if chart_data and len(chart_data) > 0:
            df_c = pd.DataFrame(chart_data)
            fig = go.Figure()
            
            # 1. แท่งเทียน
            fig.add_trace(go.Candlestick(x=df_c['time'], open=df_c['open'], high=df_c['high'], low=df_c['low'], close=df_c['close'], name='Price'))
            
            # 2. เส้น EMA 200 (M5) 🌟 แก้ไขให้อ่านค่าจาก M5
            if 'ema_m5' in df_c.columns:
                fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema_m5'], mode='lines', line=dict(color='orange', width=2), name='EMA 200 (M5)'))
            elif 'ema_200' in df_c.columns:
                fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema_200'], mode='lines', line=dict(color='orange', width=2), name='EMA 200'))
            
            # 3. วาดเส้นบอกจุดเข้าออเดอร์ (Buy/Sell)
            open_trades = details.get("open_trades", [])
            for trade in open_trades:
                t_color = "#00ff00" if trade["type"] == "buy" else "#ff0000"
                t_label = f" ◀ {trade['type'].upper()} ({trade['lot']}L) "
                fig.add_hline(
                    y=trade["price"], line_dash="dash", line_color=t_color, line_width=1.5,
                    annotation_text=t_label, annotation_position="left", 
                    annotation_font_color=t_color, annotation_font_size=12
                )

            # 🌟 แก้ไข Title กราฟเป็น M5
            fig.update_layout(title=f"📊 กราฟราคาล่าสุด {live_data.get('symbol', '')} พร้อม EMA (M5)", yaxis_title="Price", xaxis_rangeslider_visible=False, height=450, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark")
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

with tab3:
    import MetaTrader5 as mt5
    
    st.markdown("### 🔬 จำลองการเทรดด้วยการตั้งค่าปัจจุบัน (Live Config Backtester)")
    st.info(f"💡 ระบบจะใช้การตั้งค่าของโปรไฟล์ **{config.get('current_profile', 'Custom')}** ไปทดสอบย้อนหลัง")
    
    c_bars, c_btn = st.columns([1, 1])
    test_bars = c_bars.number_input("จำนวนแท่งเทียนที่ต้องการทดสอบย้อนหลัง", value=5000, step=1000)
    
    if c_btn.button("🚀 เริ่มการจำลอง (Start Backtest)", type="primary", use_container_width=True):
        if not mt5.initialize():
            st.error("❌ เชื่อมต่อ MT5 ไม่สำเร็จ กรุณาเปิดโปรแกรม MT5 ไว้ด้วยครับ!")
        else:
            with st.spinner("⏳ กำลังดึงข้อมูลและประมวลผล..."):
                # 1. ดึงการตั้งค่าสดๆ จากหน้าเว็บ
                symbol = config.get('symbol', 'XAUUSDm')
                timeframe_code = config.get('timeframe', 1)
                start_lot = config.get('start_lot', 0.01)
                target_usd = config.get('quick_profit_target', 5.0)
                max_loss_usd = -abs(config.get('max_drawdown_usd', 70.0))
                max_pos = config.get('max_positions', 3)
                dca_step = config.get('dca_step_usd', 2.0)
                dca_mult = config.get('dca_lot_mult', 1.5)
                max_gap = config.get('max_gap_usd', 10.0)
                min_bounce = config.get('min_bounce_ratio', 0.30)
                initial_balance = float(config.get('initial_balance', 100.0))
                
                # 🌟 ดึงค่าวินัยรายวันจาก Dashboard
                daily_profit_target = float(config.get('daily_profit_target', 50.0))
                daily_loss_limit = float(config.get('daily_loss_limit', 30.0))
                
                balance = initial_balance
                
                # 2. ดึงข้อมูลจาก MT5
                rates = mt5.copy_rates_from_pos(symbol, timeframe_code, 0, test_bars)
                mt5.shutdown()
                
                if rates is None or len(rates) < 100:
                    st.error("❌ ดึงข้อมูลกราฟไม่สำเร็จ หรือข้อมูลน้อยเกินไป")
                else:
                    df = pd.DataFrame(rates)
                    
                    # 🌟 [อัปเกรดใหม่] สร้างเส้น EMA 200 จำลองอ้างอิงจากไทม์เฟรม M5
                    # ถ้าลูกพี่เทสบนกราฟ M1 จะต้องใช้ระยะ 1000 แท่ง (200 แท่ง * 5 นาที) เพื่อให้ได้ค่าเท่า M5 เป๊ะๆ
                    tf_multiplier = 5 if timeframe_code == mt5.TIMEFRAME_M1 else 1 
                    df['ema_proxy'] = df['close'].ewm(span=200 * tf_multiplier, adjust=False).mean()
                    
                    records = df.to_dict('records')
                    
                    # 3. เริ่มลูปจำลองการเทรด
                    positions = []
                    history_pnl = []
                    equity_curve = [balance]
                    is_bankrupt = False
                    
                    last_date = None
                    day_pnl = 0.0
                    daily_blocked = False
                    
                    # 🌟 ดึงสวิตช์เปิด/ปิด EMA จากหน้าเว็บ
                    use_ema = config.get('use_ema_filter', True)
                    
                    for i in range(25, len(records)):
                        curr_bar = records[i]
                        
                        # 📅 ตรวจสอบการเปลี่ยนวันเพื่อรีเซ็ตวินัยประจำวัน
                        bar_date = datetime.datetime.fromtimestamp(curr_bar['time']).date()
                        if last_date is None:
                            last_date = bar_date
                            
                        if bar_date != last_date:
                            day_pnl = 0.0       
                            daily_blocked = False
                            last_date = bar_date
                        
                        total_pnl = 0.0
                        for p in positions:
                            diff = (curr_bar['close'] - p['entry']) if p['type'] == 'buy' else (p['entry'] - curr_bar['close'])
                            total_pnl += diff * 100 * p['lot']
                            
                        if len(positions) > 0:
                            if total_pnl >= target_usd or total_pnl <= max_loss_usd:
                                balance += total_pnl
                                day_pnl += total_pnl 
                                history_pnl.append(total_pnl)
                                positions.clear()
                                equity_curve.append(balance)
                                
                                if day_pnl >= daily_profit_target or day_pnl <= -abs(daily_loss_limit):
                                    daily_blocked = True 
                                
                                if balance <= 0:
                                    is_bankrupt = True
                                    break
                                continue
                                
                        if len(positions) > 0 and len(positions) < max_pos:
                            last_p = positions[-1]
                            drag = (last_p['entry'] - curr_bar['close']) if last_p['type'] == 'buy' else (curr_bar['close'] - last_p['entry'])
                            if drag >= dca_step:
                                positions.append({'type': last_p['type'], 'entry': curr_bar['close'], 'lot': last_p['lot'] * dca_mult})
                                
                        # 🎯 เช็ค X-Sniper + ระบบกรองเทรนด์ EMA M5
                        if len(positions) == 0 and not daily_blocked:
                            closed_5_highs = [records[idx]['high'] for idx in range(i-6, i-1)]
                            closed_5_lows = [records[idx]['low'] for idx in range(i-6, i-1)]
                            
                            # 🌟 เช็คว่าราคาปัจจุบันอยู่บนหรือล่างเส้น EMA M5
                            current_ema = curr_bar['ema_proxy']
                            ema_buy_condition = (curr_bar['close'] > current_ema) if use_ema else True
                            ema_sell_condition = (curr_bar['close'] < current_ema) if use_ema else True
                            
                            if closed_5_lows[2] == min(closed_5_lows) and ema_buy_condition: # 🟢 Bottom X + กรองเทรนด์ขาขึ้น
                                x_low = closed_5_lows[2]
                                recent_high = max([records[idx]['high'] for idx in range(i-9, i-1)])
                                drop = recent_high - x_low
                                bounce = curr_bar['close'] - x_low
                                ratio = bounce / drop if drop > 0 else 0
                                
                                if drop <= max_gap and ratio >= min_bounce:
                                    positions.append({'type': 'buy', 'entry': curr_bar['open'], 'lot': start_lot})
                                    
                            elif closed_5_highs[2] == max(closed_5_highs) and ema_sell_condition: # 🔴 Top X + กรองเทรนด์ขาลง
                                x_high = closed_5_highs[2]
                                recent_low = min([records[idx]['low'] for idx in range(i-21, i-1)])
                                pump = x_high - recent_low
                                pullback = x_high - curr_bar['close']
                                ratio = pullback / pump if pump > 0 else 0
                                
                                if pump <= max_gap and ratio >= min_bounce:
                                    positions.append({'type': 'sell', 'entry': curr_bar['open'], 'lot': start_lot})

                    # 4. สรุปผล
                    net_profit = balance - initial_balance
                    win_trades = len([p for p in history_pnl if p > 0])
                    loss_trades = len([p for p in history_pnl if p <= 0])
                    total_trades = win_trades + loss_trades
                    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
                    
                    if is_bankrupt:
                        st.error("☠️ BACKTEST FAILED: MARGIN CALL (พอร์ตแตกเกลี้ยงก่อนทดสอบจบ!)")
                    else:
                        st.success("✅ จำลองการเทรด (รวมกรองเทรนด์ M5) เสร็จสิ้น!")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("💰 กำไรสุทธิ", f"${net_profit:.2f}", f"จากทุน ${initial_balance}")
                    col2.metric("🧺 จำนวนรอบเทรด", f"{total_trades} รอบ")
                    col3.metric("🎯 Win Rate", f"{win_rate:.2f}%")
                    col4.metric("🔴 โดนตัดไฟ (Loss)", f"{loss_trades} ครั้ง")
                    
                    st.markdown("##### 📈 กราฟการเติบโตของพอร์ต (Equity Curve)")
                    st.line_chart(equity_curve)