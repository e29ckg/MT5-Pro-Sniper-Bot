import streamlit as st
import pandas as pd
import json
import os
import time
import datetime
import core_db
import plotly.graph_objects as go # 💡 นำเข้าเครื่องมือวาดกราฟ

# ==========================================
# 🛠️ 1. กำหนดตัวแปรและฟังก์ชันจัดการฐานข้อมูล
# ==========================================
CONFIG_FILE = "config"
LIVE_STATUS_FILE = "live_status"
HISTORY_FILE = "trade_history.json" # 💡 ประวัติยังเป็นไฟล์ json เพื่อให้รองรับการ append จาก bot.py

def load_json(key):
    return core_db.load_db(key)

def save_json(key, data):
    core_db.save_db(key, data)

# 💡 โหลด config ออกมาก่อน เพื่อให้ระบบ Password มองเห็นรหัสผ่าน
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
            st.info("💡 รหัสผ่านเริ่มต้นคือ: **admin123** (สามารถเปลี่ยนได้ที่เมนูด้านซ้ายหลังล็อกอิน)")
            
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
config['symbol'] = st.sidebar.text_input("Symbol", config.get('symbol', 'BTCUSDm'))
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
config['use_smart_dca'] = st.sidebar.checkbox("🧠 เปิดใช้ Smart DCA (รอสุดเทรนด์ค่อยแก้)", value=config.get('use_smart_dca', True))
st.sidebar.caption("ถ้าเปิด: จะยิงแก้ Buy เมื่อ RSI < 30 (Oversold) และ Sell เมื่อ RSI > 70 (Overbought) เท่านั้น")

st.sidebar.header("🎯 4. เงื่อนไข X-Sniper V6")
config['max_gap_usd'] = st.sidebar.number_input("Max Gap (USD)", value=config.get('max_gap_usd', 400.0), step=10.0)
config['min_bounce_ratio'] = st.sidebar.number_input("Min Bounce Ratio", value=config.get('min_bounce_ratio', 0.35), step=0.05)

st.sidebar.header("📈 5. ระบบกรองเทรนด์ (EMA 200)")
config['use_ema_filter'] = st.sidebar.checkbox("เปิดใช้ EMA 200 Filter", value=config.get('use_ema_filter', True))

st.sidebar.header("🛡️ 6. ระบบกันหน้าทุน (Trailing Stop)")
config['use_trailing'] = st.sidebar.checkbox("เปิดใช้งาน Trailing Stop", value=config.get('use_trailing', True))
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
st.sidebar.header("🔥 8. ฟีเจอร์ระดับโปร (Pro Features)")

st.sidebar.markdown("**📊 1. กรองความผันผวน (Volatility Filter)**")
config['max_spread_points'] = st.sidebar.number_input("สเปรดสูงสุด (Points)", value=config.get('max_spread_points', 5000), step=100)
config['use_atr_filter'] = st.sidebar.checkbox("เปิดใช้ ATR Filter (ป้องกันกราฟกระชาก)", value=config.get('use_atr_filter', True))
config['max_atr_value'] = st.sidebar.number_input("ค่า ATR (M1) สูงสุดที่ยอมรับได้", value=config.get('max_atr_value', 150.0), step=10.0)

st.sidebar.markdown("**📰 2. กรองข่าวเศรษฐกิจ (News Filter)**")
config['use_news_filter'] = st.sidebar.checkbox("หลบข่าวกล่องแดง (USD High Impact)", value=config.get('use_news_filter', False))
st.sidebar.caption("บอทจะหยุดยิงไม้แรกล่วงหน้า 15 นาที และหลังข่าวออก 15 นาที (อิงจาก ForexFactory)")

st.sidebar.markdown("**💰 3. การจัดการ Lot**")
config['use_auto_lot'] = st.sidebar.checkbox("คำนวณ Lot อัตโนมัติ", value=config.get('use_auto_lot', False))
config['auto_lot_step'] = st.sidebar.number_input("ทุกๆ เงินทุน ($) เท่ากับ 1 Base Lot", value=config.get('auto_lot_step', 500.0), step=50.0)

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

# 🚨 แผงควบคุมฉุกเฉิน (Panic Panel)
st.markdown("### 🚨 แผงควบคุมฉุกเฉิน (Manual Override)")
btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)

if btn_c1.button("💥 รวบปิดทุกไม้ทันที (Panic Close)", type="primary", use_container_width=True):
    save_json("ui_command", {"action": "PANIC_CLOSE"})
    st.toast("ส่งคำสั่งปิดทุกไม้เรียบร้อยแล้ว!", icon="🚨")

if config.get("use_smart_dca", True):
    if btn_c2.button("🛑 ระงับการยิงไม้แก้ (Pause DCA)", use_container_width=True):
        save_json("ui_command", {"action": "PAUSE_DCA"})
        st.toast("ส่งคำสั่งระงับ DCA ชั่วคราว!", icon="🛑")
else:
    if btn_c2.button("▶️ กลับมายิงไม้แก้ (Resume DCA)", use_container_width=True):
        save_json("ui_command", {"action": "RESUME_DCA"})
        st.toast("เปิดระบบ DCA ตามปกติ!", icon="▶️")

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
            elif "บล็อก" in pattern or "นอกเวลา" in pattern or "สเปรด" in pattern or "กระชาก" in pattern or "ข่าว" in pattern: st.warning(pattern)
            else: st.info(pattern)
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("เทรนด์หลัก (EMA 200)", f"{details.get('ema_200', 0):.2f}")
            sc2.metric("สเปรดปัจจุบัน", f"{details.get('current_spread', 0):.0f} Points")
            sc3.metric("ขนาด Lot ไม้ถัดไป", f"{details.get('next_lot', config.get('start_lot', 0.01))}")
            
            bounce_ratio = details.get("bounce_ratio", 0)
            target_bounce = details.get("target_bounce", 0.35)
            progress_val = max(0.0, min((bounce_ratio / target_bounce) if target_bounce > 0 else 0, 1.0))
            
            st.write(f"**แรงเด้งกลับ (Bounce Ratio):** {bounce_ratio:.2f} / เป้าหมาย: {target_bounce:.2f}")
            st.progress(progress_val)
            
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
        # 📈 วาดกราฟแท่งเทียน (Live Candlestick)
        # ----------------------------------------
        chart_data = load_json("chart_data")
        if chart_data and len(chart_data) > 0:
            df_c = pd.DataFrame(chart_data)
            
            fig = go.Figure()
            # 1. วาดแท่งเทียน
            fig.add_trace(go.Candlestick(
                x=df_c['time'], open=df_c['open'], high=df_c['high'], low=df_c['low'], close=df_c['close'],
                name='Price'
            ))
            # 2. วาดเส้น EMA 200 (ถ้ามี)
            if 'ema_200' in df_c.columns:
                fig.add_trace(go.Scatter(
                    x=df_c['time'], y=df_c['ema_200'], 
                    mode='lines', line=dict(color='orange', width=2), name='EMA 200'
                ))
            
            fig.update_layout(
                title=f"📊 กราฟราคาล่าสุด {live_data.get('symbol', '')} พร้อม EMA 200",
                yaxis_title="Price",
                xaxis_rangeslider_visible=False,
                height=450,
                margin=dict(l=20, r=20, t=40, b=20),
                template="plotly_dark"
            )
            st.plotly_chart(fig, use_container_width=True)

    render_live_dashboard()

with tab2:
    def load_history():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return []

    hist_data = load_history()
    
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
            with open(HISTORY_FILE, "w", encoding='utf-8') as f:
                json.dump([], f)
            st.rerun()
    else:
        st.info("📭 ยังไม่มีประวัติการเทรด")