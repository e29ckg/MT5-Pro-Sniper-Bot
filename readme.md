# 🎛️ MT5 Pro Sniper Bot (X-Sniper + DCA + Auto-Lot)
ระบบบอทเทรดอัตโนมัติสำหรับ MetaTrader 5 (MT5) ที่ผสานกลยุทธ์ X-Sniper V6 เข้ากับระบบจัดการความเสี่ยง (DCA & Trailing Stop) และมีหน้าเว็บ Dashboard ควบคุมการทำงานแบบ Real-time ด้วย Streamlit

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![MetaTrader 5](https://img.shields.io/badge/MetaTrader-5-orange)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)

---

## ✨ ฟีเจอร์หลัก (Key Features)
* **🎯 X-Sniper V6 Strategy:** สแกนหาจุดกลับตัวที่แม่นยำ (X-Below / X-Above) พร้อมระบบเช็คแรงเด้งกลับ (Bounce Ratio)
* **📈 EMA 200 Trend Filter:** กรองสัญญาณเทรดด้วยเส้นค่าเฉลี่ย 200 แท่ง เพื่อป้องกันการเทรดสวนเทรนด์หลัก
* **🚑 Smart DCA (Martingale):** ระบบแก้ไม้เมื่อผิดทาง สามารถตั้งระยะห่าง (DCA Step) และตัวคูณ Lot ได้
* **🛡️ Trailing Stop (Break-even):** ระบบเลื่อนจุดล็อกกำไรอัตโนมัติ เพื่อป้องกันกำไรหดหายเมื่อกราฟสวิงกลับ
* **⏰ Trading Hours & Clearance Mode:** กำหนดเวลาเริ่ม-หยุดเทรดได้ พร้อมระบบ "เคลียร์พอร์ตเท่าทุน" (Break-even) และ "บังคับตัดจบวัน" (Force Close) ก่อนตลาดปิด
* **🔥 Pro Features:** ตัวกรองสเปรดถ่าง (Spread Filter) และระบบคำนวณ Lot อัตโนมัติ (Auto-Lot Sizing) ตามขนาดทุน
* **📱 Telegram Notifications:** แจ้งเตือนการเปิด/ปิดออเดอร์ และสรุปกำไรผ่าน Telegram ทันที
* **📊 Live Dashboard:** แผงควบคุมผ่านหน้าเว็บ (Streamlit) ที่แสดงผลเรดาร์สแกนกราฟแบบเรียลไทม์ และสรุปประวัติการเทรด

---

## 🛠️ ข้อกำหนดเบื้องต้น (Prerequisites)
ก่อนติดตั้งระบบ กรุณาตรวจสอบว่าคอมพิวเตอร์ของคุณมีโปรแกรมเหล่านี้:
1. **Windows OS** (ไลบรารีของ MT5 รองรับเฉพาะระบบปฏิบัติการ Windows)
2. **Python 3.9 หรือสูงกว่า** (ตอนติดตั้งอย่าลืมติ๊ก `Add Python to PATH`)
3. **MetaTrader 5 (MT5)** (ต้องล็อกอินบัญชีเทรด และเปิดปุ่ม `Algo Trading` ด้านบนให้เป็นสีเขียว)

---

## 🚀 วิธีการติดตั้ง (Installation Guide)

### 1. โคลนโปรเจ็กต์นี้ (Clone Repository)
เปิดโปรแกรม Command Prompt (CMD) หรือ PowerShell แล้วพิมพ์:
```bash
git clone [https://github.com/ช](https://github.com/ช)ื่อผู้ใช้ของคุณ/MT5-Pro-Sniper-Bot.git
cd MT5-Pro-Sniper-Bot

```

### 2. สร้างสภาพแวดล้อมจำลอง (Virtual Environment)

เพื่อป้องกันไม่ให้แพ็กเกจตีกันกับโปรเจ็กต์อื่น:

```bash
python -m venv venv

```

เปิดใช้งาน (Activate) สภาพแวดล้อมจำลอง:

* **Command Prompt:** `venv\Scripts\activate.bat`
* **PowerShell:** `venv\Scripts\Activate.ps1`
*(หากสำเร็จ จะมีคำว่า `(venv)` ขึ้นที่หน้าบรรทัดคำสั่ง)*

### 3. ติดตั้งไลบรารีที่จำเป็น (Install Dependencies)

```bash
pip install -r requirements.txt

```

*(หมายเหตุ: หากไม่มีไฟล์ requirements.txt ให้ใช้คำสั่ง `pip install MetaTrader5 pandas streamlit requests` แทน)*

---

## 🎮 วิธีการใช้งาน (How to Run)

วิธีที่ง่ายที่สุดในการรันระบบคือการใช้ไฟล์ Launcher ที่เตรียมไว้ให้:

1. ดับเบิลคลิกที่ไฟล์ **`start.bat`**
2. ระบบจะเปิดหน้าต่าง Terminal ขึ้นมา 2 หน้าต่าง (รัน Backend และ Frontend)
3. เบราว์เซอร์จะเปิดหน้าเว็บ **Dashboard** ขึ้นมาโดยอัตโนมัติ
4. ไปที่โปรแกรม MT5 เปิดกราฟคู่เงินที่ต้องการเทรด (เช่น XAUUSDm) ทิ้งไว้
5. ในหน้า Dashboard ตรวจสอบการตั้งค่า (Lot, TP, SL, เวลาเทรด) ให้เรียบร้อย
6. กดปุ่ม **"🚀 เปิดระบบบอท"** ที่หน้าเว็บ เพื่อเริ่มต้นการทำงาน!

---

## 📂 โครงสร้างโปรเจ็กต์ (Project Structure)

* `app.py`: ไฟล์หลักสำหรับหน้าเว็บ Dashboard (Frontend - Streamlit)
* `bot.py`: ไฟล์ระบบหลังบ้าน (Backend) ทำหน้าที่เชื่อมต่อ MT5 สแกนกราฟ และยิงออเดอร์
* `backtest_config.py`: สคริปต์สำหรับจำลองผลการเทรดย้อนหลัง (อ่านค่าจาก config)
* `optimizer.py`: สคริปต์สุ่มหาการตั้งค่าพารามิเตอร์ที่ดีที่สุด (Grid Search)
* `start.bat`: ไฟล์สคริปต์สำหรับรันระบบทั้งหมดในคลิกเดียว
* `config.json`: (ถูกสร้างอัตโนมัติ) เก็บค่าพารามิเตอร์ต่างๆ
* `live_status.json`: (ถูกสร้างอัตโนมัติ) ไฟล์สื่อสารระหว่างบอทและหน้าเว็บ
* `trade_history.json`: (ถูกสร้างอัตโนมัติ) บันทึกประวัติการปิดตะกร้า

---

## ⚠️ คำเตือนความเสี่ยง (Disclaimer)

โปรเจ็กต์นี้สร้างขึ้นเพื่อเป็น **เครื่องมือทางการศึกษาและทดสอบกลยุทธ์เท่านั้น** การเทรดในตลาด Forex หรืออนุพันธ์มีความเสี่ยงสูงมาก ผู้พัฒนาไม่มีส่วนรับผิดชอบต่อความสูญเสียทางการเงินใดๆ ที่อาจเกิดขึ้นจากการใช้งานซอร์สโค้ดนี้ โปรดรันทดสอบบน **บัญชีทดลอง (Demo Account)** จนกว่าคุณจะมั่นใจในระบบและการตั้งค่าของคุณ
