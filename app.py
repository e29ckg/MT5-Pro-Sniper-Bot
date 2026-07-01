import streamlit as st
import pandas as pd
import json
import os
import time
import datetime
import core_db
import plotly.graph_objects as go
from plotly.subplots import make_subplots # 🌟 เพิ่มตัวนี้สำหรับวาด Volume

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
st.set_page_config(page_title="Gemini One-Shot Sniper", layout="wide", initial_sidebar_state="expanded")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center;'>🔒 เข้าสู่ระบบ Gemini AI</h2>", unsafe_allow_html=True)
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
# 🗂️ 2. ระบบ Profile Selector
# ==========================================
st.sidebar.header("🏆 เลือกกลยุทธ์ (Trading Profile)")

# 🌟 ปรับโปรไฟล์ใหม่ เน้นไม้เดียวจบ
PROFILES = {
    "Sniper M5 (ไม้เดียวเน้นๆ)": {
        "timeframe": 5, "max_drawdown_usd": 20.0,
        "use_profit_lock": True
    },
    "Swing M15 (ถือยาวหน่อย)": {
        "timeframe": 15, "max_drawdown_usd": 50.0,
        "use_profit_lock": True
    },
    "กำหนดเอง (Custom)": None
}

if "current_profile" not in config:
    config["current_profile"] = "Sniper M5 (ไม้เดียวเน้นๆ)"
    for k, v in PROFILES["Sniper M5 (ไม้เดียวเน้นๆ)"].items():
        config[k] = v
    save_json(CONFIG_FILE, config)

if "profile_selector" not in st.session_state:
    st.session_state.profile_selector = config["current_profile"]

def on_profile_change():
    new_prof = st.session_state.profile_selector
    config["current_profile"] = new_prof
    if PROFILES.get(new_prof) is not None:
        for k, v in PROFILES[new_prof].items():
            config[k] = v
    save_json(CONFIG_FILE, config)

def on_param_change():
    st.session_state.profile_selector = "กำหนดเอง (Custom)"
    config["current_profile"] = "กำหนดเอง (Custom)"
    save_json(CONFIG_FILE, config)

selected_profile = st.sidebar.selectbox(
    "รูปแบบการเทรด", 
    list(PROFILES.keys()), 
    key="profile_selector",
    on_change=on_profile_change
)

st.sidebar.markdown("---")

# ==========================================
# ⚙️ เมนูตั้งค่าพารามิเตอร์ (Sidebar)
# ==========================================
st.sidebar.header("🧠 1. ตั้งค่า AI (Gemini)")
config['gemini_api_key'] = st.sidebar.text_input("Gemini API Key", value=config.get('gemini_api_key', ''), type="password", on_change=on_param_change)

st.sidebar.header("🧠 1.1 ตั้งค่ารุ่นของ AI (Gemini Model)")
model_options = ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-3.5-flash", "gemini-1.5-pro", "gemini-2.5-pro", "gemini-3.5-pro"]
current_model = config.get('gemini_model', 'gemini-1.5-flash')
if current_model not in model_options:
    current_model = "gemini-1.5-flash"

config['gemini_model'] = st.sidebar.selectbox(
    "เลือกรุ่นของ AI",
    options=model_options,
    index=model_options.index(current_model),
    on_change=on_param_change
)
st.sidebar.caption("💡 **Flash** = รวดเร็วและเสถียร (แนะนำ) | **Pro** = วิเคราะห์ลึกซึ้ง (แต่อาจเจอคิวเต็มบ่อยกว่า)")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 2. ตั้งค่าพื้นฐาน")
config['symbol'] = st.sidebar.text_input("Symbol", config.get('symbol', 'XAUUSDm'), on_change=on_param_change)
config['magic_number'] = int(st.sidebar.number_input("Magic Number", value=config.get('magic_number', 888888), step=1, on_change=on_param_change))

tf_options = {5: "M5 (จุดเข้า)", 15: "M15 (จุดเข้า)"}
current_tf_name = tf_options.get(config.get('timeframe', 5), "M5 (จุดเข้า)")
selected_tf_name = st.sidebar.selectbox("Timeframe สำหรับหาจุดเข้า", list(tf_options.values()), index=list(tf_options.values()).index(current_tf_name), on_change=on_param_change)
config['timeframe'] = [k for k, v in tf_options.items() if v == selected_tf_name][0]
st.sidebar.caption("💡 ไทม์เฟรม H1 บอทจะใช้ดูเทรนด์หลักอัตโนมัติ")

st.sidebar.markdown("---")
st.sidebar.header("🌟 3. การจัดการเงินทุน (MM)")
config['start_lot'] = st.sidebar.number_input("ขนาด Lot (ไม้เดียว)", value=config.get('start_lot', 0.01), step=0.01, on_change=on_param_change)
config['max_drawdown_usd'] = st.sidebar.number_input("ลิมิตขาดทุนสะสม ($)", value=config.get('max_drawdown_usd', 70.0), step=1.0, on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("🛡️ 4. ระบบเลื่อนบังหน้าทุน (เซฟพอร์ต)")
st.sidebar.info("📌 ปกป้องเงินทุนเมื่อราคาวิ่งถูกทาง")
config['use_profit_lock'] = st.sidebar.checkbox("เปิดใช้งานระบบป้องกันทุน", value=config.get('use_profit_lock', True), on_change=on_param_change)
config['profit_lock_style'] = st.sidebar.selectbox(
    "รูปแบบการล็อกกำไร", 
    ["ล็อกครั้งเดียว (One-Time)", "เลื่อนตามขั้นบันได (Step Trailing)"], 
    index=0 if config.get('profit_lock_style', 'ล็อกครั้งเดียว (One-Time)') == "ล็อกครั้งเดียว (One-Time)" else 1,
    on_change=on_param_change
)

config['profit_lock_percent'] = st.sidebar.number_input(
    "เปอร์เซ็นต์ล็อกกำไรด่านแรก (% ของระยะ TP)", 
    min_value=5, 
    max_value=45, 
    value=config.get('profit_lock_percent', 25), 
    step=5, 
    on_change=on_param_change
)

st.sidebar.markdown("---")
st.sidebar.header("🔥 5. ความปลอดภัย (Filters)")
config['max_spread_points'] = st.sidebar.number_input("สเปรดสูงสุด (Points)", value=config.get('max_spread_points', 400), step=50, on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("📱 6. Telegram")
config['telegram_enabled'] = st.sidebar.checkbox("แจ้งเตือน Telegram", value=config.get('telegram_enabled', False), on_change=on_param_change)
config['telegram_token'] = st.sidebar.text_input("Bot Token", value=config.get('telegram_token', ""), type="password", on_change=on_param_change)
config['telegram_chat_id'] = st.sidebar.text_input("Chat ID", value=config.get('telegram_chat_id', ""), on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("⏰ 7. ตั้งเวลาเทรด (ไม่ถือข้ามวัน)")
config['use_time_filter'] = st.sidebar.checkbox("เปิดใช้งานระบบเวลา", value=config.get('use_time_filter', False), on_change=on_param_change)
config['time_start'] = st.sidebar.text_input("เวลาเริ่มเทรด (HH:MM)", value=config.get('time_start', '06:00'), on_change=on_param_change)
config['time_end'] = st.sidebar.text_input("เวลาปิดออเดอร์ (HH:MM)", value=config.get('time_end', '23:50'), on_change=on_param_change)
st.sidebar.caption("🔥 **โหมดรีดกำไร:** 1 ชม. ก่อนถึงเวลาปิดออเดอร์ บอทจะบังคับเลื่อน SL แบบขั้นบันได เพื่อไล่เก็บกำไรให้มากที่สุด")

st.sidebar.markdown("---")
st.sidebar.header("📰 8. ระบบหลบข่าว (News Filter)")
config['use_news_filter'] = st.sidebar.checkbox("เปิดใช้งานระบบหลบข่าว (กล่องแดง)", value=config.get('use_news_filter', True), on_change=on_param_change)
config['news_currency'] = st.sidebar.text_input("สกุลเงินที่ต้องระวัง (เช่น USD)", value=config.get('news_currency', 'USD'), on_change=on_param_change)
config['news_pause_before'] = st.sidebar.number_input("หยุดเทรด 'ก่อน' ข่าว (นาที)", min_value=0, max_value=120, value=config.get('news_pause_before', 30), on_change=on_param_change)
config['news_pause_after'] = st.sidebar.number_input("หยุดเทรด 'หลัง' ข่าว (นาที)", min_value=0, max_value=120, value=config.get('news_pause_after', 30), on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("🎯 9. การจัดการกำไร/ขาดทุนรายวัน")
config['daily_profit_limit'] = st.sidebar.number_input("จำกัดกำไรสูงสุดต่อวัน ($)", value=config.get('daily_profit_limit', 1000.0), step=100.0, on_change=on_param_change)
config['daily_loss_limit'] = st.sidebar.number_input("จำกัดขาดทุนสูงสุดต่อวัน ($)", value=config.get('daily_loss_limit', 500.0), step=50.0, on_change=on_param_change)

st.sidebar.markdown("---")
st.sidebar.header("🔒 ตั้งค่าความปลอดภัย")
# ช่องเปลี่ยนรหัสผ่าน
new_pwd = st.sidebar.text_input("เปลี่ยนรหัสผ่านใหม่", value=config.get('web_password', 'admin123'), type="password")
if st.sidebar.button("💾 บันทึกรหัสผ่านใหม่"):
    config['web_password'] = new_pwd
    save_json(CONFIG_FILE, config)
    st.sidebar.success("บันทึกรหัสผ่านเรียบร้อย!")

save_json(CONFIG_FILE, config)

# ==========================================
# 🚀 ส่วนควบคุมหลัก (Header)
# ==========================================
c_title, c_empty, c_switch = st.columns([2, 2, 1])
c_title.title("🎯 AI Sniper Dashboard")

with c_switch:
    is_running = config.get("bot_status") == "running"
    toggle_bot = st.toggle("🚀 เปิดระบบบอท", value=is_running)
    if toggle_bot != is_running:
        config["bot_status"] = "running" if toggle_bot else "stopped"
        save_json(CONFIG_FILE, config)
        st.rerun()

st.markdown("---")

if "confirm_panic" not in st.session_state:
    st.session_state.confirm_panic = False

btn_c1, btn_c2 = st.columns([1, 3])
with btn_c1:
    if not st.session_state.confirm_panic:
        if st.button("💥 ปิดออเดอร์ฉุกเฉิน", type="primary", use_container_width=True):
            st.session_state.confirm_panic = True
            st.rerun()
    else:
        st.error("⚠️ แน่ใจหรือไม่?")
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ ยืนยัน", type="primary", use_container_width=True):
            save_json("ui_command", {"action": "PANIC_CLOSE"})
            st.toast("ส่งคำสั่งปิดออเดอร์เรียบร้อยแล้ว!", icon="🚨")
            st.session_state.confirm_panic = False
            st.rerun()
        if cc2.button("❌ ยกเลิก", use_container_width=True):
            st.session_state.confirm_panic = False
            st.rerun()

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📡 เรดาร์ & มุมมอง AI", "📊 ประวัติการเทรด", "🔬 จำลอง Backtest"])

with tab1:
    auto_refresh = st.toggle("🔄 เปิดโหมดดูเรียลไทม์ (Auto-Refresh 2 วินาที)")
    refresh_rate = 2 if auto_refresh else None

    @st.fragment(run_every=refresh_rate)
    def render_live_dashboard():
        live_data = load_json(LIVE_STATUS_FILE)
        fresh_config = load_json(CONFIG_FILE)
        
        mode = live_data.get('mode', '-')
        details = live_data.get("details", {})
        open_trades = details.get("open_trades", [])

        # 🌟 1. ดึงสถานะ BUY/SELL ไปโชว์ที่แถบแจ้งเตือนด้านบนสุดให้เห็นชัดๆ
        holding_badge = ""
        if mode == "HOLDING" and open_trades:
            trade_type = open_trades[0]['type'].upper()
            badge_icon = "📈 BUY" if trade_type == "BUY" else "📉 SELL"
            holding_badge = f" ➔ [ 💼 กำลังถือไม้ {badge_icon} ]"

        if fresh_config.get("bot_status") == "running":
            st.success(f"🟢 **สถานะ:** {fresh_config.get('current_activity', 'เตรียมความพร้อม...')}{holding_badge}")
        else:
            st.warning("🔴 **หยุดทำงาน (Standby)**")

        if not live_data:
            st.info("⏳ รอรับข้อมูลจากบอทหลังบ้าน...")
            return

        st.markdown("##### 💳 ข้อมูลบัญชี (Account Info)")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("ยอดเงินคงเหลือ", f"${live_data.get('balance', 0.0):.2f}")
        a2.metric("ทุนสุทธิ (Equity)", f"${live_data.get('equity', 0.0):.2f}")
        a3.metric("📌 สัญลักษณ์", live_data.get("symbol", "-"))
        a4.metric("💰 ราคาปัจจุบัน", f"{live_data.get('current_price', 0):.2f}")
        
        st.markdown("---")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("🏆 โปรไฟล์ปัจจุบัน", config.get("current_profile", "Custom").split(" ")[0])
        b2.metric("📈 สเปรด (Spread)", f"{details.get('current_spread', 0):.0f} Points")
        
        # 🌟 2. แต่งสีโหมดการทำงานให้สังเกตง่ายขึ้น
        mode_color = "#007bff" if mode == "SCANNING" else "#fd7e14" if mode == "HOLDING" else "gray"
        b3.markdown(f"**โหมดการทำงาน:** <br>📡 <span style='color:{mode_color}; font-weight:bold;'>{mode}</span>", unsafe_allow_html=True)
        b4.caption(f"⏱️ อัปเดตล่าสุด:<br>{live_data.get('last_update', '-')}", unsafe_allow_html=True)

        # แสดงแนวรับแนวต้านที่ดึงมาล่าสุด
        if "sr_data" in details:
            d1_res, d1_sup, h4_res, h4_sup = details["sr_data"]
            st.markdown("##### 🧱 โซนแนวรับ-แนวต้านสำคัญ (Major Key Levels)")
            sr1, sr2, sr3, sr4 = st.columns(4)
            sr1.metric("แนวต้าน D1 (Resistance)", f"{d1_res:.2f}" if d1_res != "Unknown" else "-")
            sr2.metric("แนวรับ D1 (Support)", f"{d1_sup:.2f}" if d1_sup != "Unknown" else "-")
            sr3.metric("แนวต้าน H4 (Resistance)", f"{h4_res:.2f}" if h4_res != "Unknown" else "-")
            sr4.metric("แนวรับ H4 (Support)", f"{h4_sup:.2f}" if h4_sup != "Unknown" else "-")

        # แสดงความเห็นของ AI
        ai_reason = details.get("ai_reason", "กำลังรวบรวมข้อมูล...")
        st.info(f"🧠 **มุมมองของ Gemini AI:** {ai_reason}")

        if "rr_ratio" in details:
            st.metric("📊 RR Ratio ของไม้ที่ AI แนะนำ", f"{details['rr_ratio']:.2f}")

        if mode == "HOLDING":
            st.markdown("##### 🎯 สถานะออเดอร์ปัจจุบัน (One-Shot)")
            hc1, hc2, hc3 = st.columns(3)
            pnl = details.get("total_pnl", 0)
            
            # 🌟 3. ใส่ไอคอนสีตามผลกำไร/ขาดทุน
            pnl_icon = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            hc1.metric("กำไร/ขาดทุน (รวม Swap)", f"{pnl_icon} ${pnl:.2f}")            
            
            if open_trades:
                trade = open_trades[0] # ดึงไม้แรกมาแสดง
                trade_type = trade['type'].upper()
                
                # 🌟 4. ใช้ HTML แต่งสีตัวอักษร BUY (เขียว) / SELL (แดง)
                trade_color = "#28a745" if trade_type == "BUY" else "#dc3545"
                trade_display = f"📈 BUY" if trade_type == "BUY" else f"📉 SELL"
                
                hc2.markdown(
                    f"**สถานะไม้:**<br>"
                    f"<span style='color:{trade_color}; font-size:18px; font-weight:bold;'>"
                    f"{trade_display} | {trade['lot']} Lot"
                    f"</span>", 
                    unsafe_allow_html=True
                )
                
                # เช็คสถานะการเลื่อน SL
                if any(keyword in ai_reason for keyword in ["เลื่อน SL", "ล็อกกำไร", "เซฟพอร์ต"]):
                    hc3.success("🛡️ บังหน้าทุนแล้ว (Risk-Free)")
                else:
                    hc3.warning("⏳ รอเข้าเงื่อนไขล็อกกำไร")

        # ----------------------------------------
        # 📈 กราฟพร้อม Volume (อัปเกรด Plotly)
        # ----------------------------------------
        chart_data = load_json("chart_data")
        if chart_data and len(chart_data) > 0:
            df_c = pd.DataFrame(chart_data)
            
            # 🌟 สร้างกราฟ 2 แถว (แถวบนราคา แถวล่าง Volume)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, subplot_titles=(f"กราฟราคาล่าสุด {live_data.get('symbol', '')}", "Volume"),
                                row_width=[0.2, 0.7])

            # 1. แท่งเทียน
            fig.add_trace(go.Candlestick(x=df_c['time'], open=df_c['open'], high=df_c['high'], low=df_c['low'], close=df_c['close'], name='Price'), row=1, col=1)
            
            # 2. เส้น EMA 200 (M5)
            if 'ema_m5' in df_c.columns:
                fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema_m5'], mode='lines', line=dict(color='orange', width=2), name='EMA 200 (M5)'), row=1, col=1)
            
            # 3. วาด Volume
            if 'volume' in df_c.columns:
                colors = ['#26a69a' if row['close'] >= row['open'] else '#ef5350' for index, row in df_c.iterrows()]
                fig.add_trace(go.Bar(x=df_c['time'], y=df_c['volume'], marker_color=colors, name='Volume'), row=2, col=1)

            # 4. วาดเส้นจุดเข้าออเดอร์ (ถ้ามี)
            open_trades = details.get("open_trades", [])
            for trade in open_trades:
                t_color = "#00ff00" if trade["type"] == "buy" else "#ff0000"
                t_label = f" ◀ {trade['type'].upper()} ({trade['lot']}L) "
                fig.add_hline(y=trade["price"], line_dash="dash", line_color=t_color, line_width=1.5, annotation_text=t_label, annotation_position="left", annotation_font_color=t_color, annotation_font_size=12, row=1, col=1)

            fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    render_live_dashboard()

with tab2:
    def load_history():
        if os.path.exists(HISTORY_FILE):
            # 🌟 เพิ่มบรรทัดนี้: เช็คว่าถ้าไฟล์ว่างเปล่าสนิท (0 bytes) ให้ข้ามการอ่านไปเลย
            if os.path.getsize(HISTORY_FILE) == 0:
                return []
                
            try:
                with open(HISTORY_FILE, "r", encoding='utf-8') as f: 
                    return json.load(f)
            except json.JSONDecodeError:
                # 🌟 ดัก Error กรณีไฟล์พังหรือไม่มีโครงสร้าง JSON ให้ส่งค่าว่างกลับไป
                return []
            except Exception as e:
                st.error(f"❌ อ่านไฟล์ประวัติไม่ได้: {e}") 
        return []

    hist_data = load_history()
    
    # ถ้ามีข้อมูลและเป็น List จริงๆ ค่อยแสดงตาราง
    if isinstance(hist_data, list) and len(hist_data) > 0:
        df_hist = pd.DataFrame(hist_data)
        
        # 🌟 ป้องกันแอปพัง ถ้าใน JSON ไม่มีคีย์ชื่อ 'กำไร/ขาดทุน'
        if 'กำไร/ขาดทุน' in df_hist.columns:
            total_profit = df_hist['กำไร/ขาดทุน'].sum()
        else:
            total_profit = 0.0
            st.warning("⚠️ พบข้อมูลประวัติ แต่ไม่พบคอลัมน์ที่ชื่อ 'กำไร/ขาดทุน'")
            
        st.metric("💰 กำไรสุทธิรวม (One-Shot Trades)", f"${total_profit:.2f}")
        
        # กลับด้านข้อมูลให้ไม้ล่าสุดอยู่บนสุด
        df_hist_reversed = df_hist.iloc[::-1].reset_index(drop=True)
        st.dataframe(df_hist_reversed, use_container_width=True)
        
    else:
        # 🌟 เพิ่มบรรทัดนี้ เพื่อบอกให้รู้ว่าทำไมถึงไม่มีตารางขึ้น
        st.info("📭 ยังไม่มีประวัติการเทรด หรือไฟล์ประวัติว่างเปล่า")

with tab3:
    st.markdown("### 🔬 จำลองการเทรดด้วย Gemini AI (Backtester)")
    st.warning("⚠️ **ข้อจำกัดในการจำลอง AI:** การทำ Backtest ด้วยกราฟ 2 Timeframe จะดึงโควต้า API เร็วมาก ฟังก์ชันนี้จึงถูกระงับเพื่อป้องกันการใช้โควต้าเกินความจำเป็นครับ แนะนำให้เปิด Demo รันทดสอบจริงจะแม่นยำที่สุด")