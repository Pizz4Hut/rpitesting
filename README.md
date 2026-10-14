# 🏭 Siemens S7-1200 Industrial IoT Edge Gateway (Raspberry Pi 4)
## ระบบส่งข้อมูลจากเครื่องจักรขึ้น HTTP REST API พร้อม Redundancy, Two-Way Heartbeat & PNR Tracking

ระบบ IoT Edge Gateway ออกแบบมาสำหรับติดตั้งบน **Raspberry Pi 4 Model B** เพื่อดึงข้อมูลจาก **PLC Siemens S7-1200** ผ่าน S7comm Protocol (TCP Port 102) และส่งข้อมูลไปยัง **HTTP REST API** ตามข้อกำหนดใน TOR โดยมีระบบ **Redundancy (Store-and-Forward SQLite WAL Mode)**, **Two-way Heartbeat (Gateway ⟷ Server & Gateway ⟷ PLC)**, และ **PNR Reference Code Generation (Crockford Base32 6 หลัก)** ป้องกันข้อมูลสูญหาย 100%

🌐 **Live IoT Cloud Dashboard:** [https://rpi11232.netlify.app](https://rpi11232.netlify.app)

---

## 📌 สรุปภาพรวมและผังระบบจริงหน้างาน (Verified Physical Topology)

```
       [ Raspberry Pi บอร์ดที่ 3 ]
       (Siemens S7-1200 PLC Simulator: 192.168.2.2:102)
                   │
                   │ สาย LAN (S7comm Protocol)
                   ▼
┌────────────────────────────────────────────────────────┐
│                   Switching Hub                        │
└──────┬───────────────────┬──────────────────────┬──────┘
       │                   │                      │
       ▼                   ▼                      ▼
[ Raspberry Pi 1 ]  [ Raspberry Pi 2 ]    [ Mac Workstation ]
  gse-proto-1         gse-proto-2         (Monitoring & Dev)
 (Master Gateway)    (Backup Gateway)
  192.168.2.4         192.168.2.3
       │                   │
       └─────────┬─────────┘
                 │ HTTP POST Telemetry & Heartbeat (SSL/TLS)
                 ▼
 ☁️ [ Live Netlify Cloud API: https://rpi11232.netlify.app ]
```

---

## 📋 ข้อมูล Hardware & Network Profile ของอุปกรณ์ที่ทดสอบจริง

| ข้อมูลอุปกรณ์ | บอร์ดที่ 1 (Master) | บอร์ดที่ 2 (Backup) | บอร์ดที่ 3 (PLC Sim) |
| :--- | :--- | :--- | :--- |
| **Hostname** | `gse-proto-1` | `gse-proto-2` | `edge-gateway` |
| **User Account** | `groundshift_supreme_admin` | `groundshift_supreme_admin` | `dgpx` |
| **IP Address** | `192.168.2.4` | `192.168.2.3` | `192.168.2.2` |
| **MAC Address** | `98:fe:54:63:34:ca` | `98:fe:54:63:35:a5` | ประจำตัวบอร์ด 3 |
| **CPU Serial** | `1000000091f9071a` | `100000001b657629` | ชิป BCM2711 |
| **บทบาทในระบบ** | Master Edge Gateway | Redundant Standby Gateway | Siemens S7-1200 Server |
| **พอร์ตสื่อสาร** | S7 Port 102 / HTTP Out | S7 Port 102 / HTTP Out | TCP Port 102 (Listen) |

---

## ⚙️ คุณสมบัติเด่นของระบบ (Core Features)

1. **ดึงข้อมูล Siemens S7-1200 (19 Tags ตาม TOR ข้อ 2.2.1)**:
   - อ่านค่าผ่าน S7comm protocol (Port 102) อ้างอิง Direct DB Addressing (`DB1.DBD0` - `DB1.DBW62`)
   - รองรับ Data Types ครบถ้วน: `REAL`, `DINT`, `INT`, `BOOL`
2. **ระบบ Redundancy: Store-and-Forward (SQLite WAL Mode)**:
   - หากยิง HTTP API ไม่สำเร็จ หรือเน็ตตัด ข้อมูลจะไม่สูญหาย แต่จะถูกพักเก็บใน SQLite database (`buffer.db`) ภายในตัวบอร์ด Pi ทันที
   - เมื่อระบบเครือข่ายกลับมาเชื่อมต่อได้ ตัว Replay Drainer จะดึงข้อมูลย้อนหลังส่งขึ้น API เป็นชุด (Batch Replay) ตามลำดับเวลา FIFO โดยคง Timestamp ดั้งเดิม
3. **ระบบ Heartbeat 2 ทิศทาง (Two-way Dual Heartbeat)**:
   - **Gateway ⟷ Cloud/Server**: ส่ง Heartbeat Ping ทุกๆ 30 วินาที ผ่าน HTTP POST รายงาน CPU Temp, RAM, Disk, สถานะการเชื่อมต่อ PLC และจำนวนคิวออฟไลน์ที่ค้างอยู่
   - **Gateway ⟷ PLC**: สลับบิต Lifebit (`DB1.DBX0.0`) ทุกๆ 5 วินาที เพื่อให้ Ladder Logic ใน PLC ตรวจจับได้ หาก Gateway หยุดทำงาน PLC สามารถส่ง Alarm เตือนหน้าตู้ได้ทันที
4. **ระบบสร้างรหัสอ้างอิง PNR Code (Crockford Base32 6 หลัก แบบ Collision-Free)**:
   - คำนวณรหัส PNR 6 หลัก จากชุดอักขระ 32 ตัว `23456789ABCDEFGHJKLMNPQRSTUVWXYZ` (ตัด 0, 1, O, I ออกเพื่อกันความสับสน)
   - คำนวณจาก SHA-256 ของ `org_id` + `collected_at` + `sequence` + `nonce` และตรวจสอบความซ้ำซ้อนในฐานข้อมูล SQLite อัตโนมัติ
   - ประทับรหัส PNR ลงในฟิลด์ `"pnrCode"` และก้อน `"batch"` ของทุกชุดข้อมูลที่ส่งขึ้น API เพื่อใช้ยืนยันความถูกต้อง ป้องกันข้อมูลส่งซ้ำ (Anti-Duplication)
5. **ระบบตรวจเช็คสุขภาพอัตโนมัติ (Automated Self-Diagnosis & Troubleshooting)**:
   - สแกนสุขภาพระบบ 7 มิติผ่านคำสั่ง `python3 plc_gateway.py --diagnose` รายงานผลด้วย Badge สี [PASS], [WARN], [FAIL] พร้อมคำแนะนำวิธีแก้ปัญหา

---

## 📖 คู่มือการติดตั้งและตั้งค่าตั้งแต่เริ่มต้น (Step-by-Step Tutorial)

### ขั้นตอนที่ 1: การเตรียม SD Card ด้วย Raspberry Pi Imager
1. เสียบ MicroSD Card เข้ากับคอมพิวเตอร์ แล้วเปิดโปรแกรม **Raspberry Pi Imager**
2. เลือก OS: **Raspberry Pi OS (64-bit)**
3. ในหน้าต่างตั้งค่า OS Customisation ให้กำหนดค่าดังนี้:
   * **เครื่องที่ 1 (Master):**
     * Hostname: `gse-proto-1`
     * Username: `groundshift_supreme_admin`
     * Password: `abcd1234#`
   * **เครื่องที่ 2 (Backup):**
     * Hostname: `gse-proto-2`
     * Username: `groundshift_supreme_admin`
     * Password: `abcd1234#`
   * **แท็บ SERVICES (สำคัญมาก):**
     * ติ๊กถูกที่ **☑ "Enable SSH"** และเลือก **"Use password authentication"**
4. กด **Write** ลง SD Card แล้วนำไปใส่ใน Raspberry Pi 4

---

### ขั้นตอนที่ 2: การตั้งค่าความปลอดภัย (Deploy Key สำหรับ Private Repository)
เพื่อความปลอดภัยระดับองค์กร (Security Best Practice) โดยไม่ต้องเปิด Public:

1. **เชื่อมต่อ SSH เข้าบอร์ด:**
   ```bash
   ssh groundshift_supreme_admin@gse-proto-1.local
   # รหัสผ่าน: abcd1234#
   ```
2. **สร้าง SSH Key ประจำตัวบอร์ด:**
   ```bash
   ssh-keygen -t ed25519 -C "rpi-gateway" -N "" -f ~/.ssh/id_ed25519
   ```
3. **ดูกุญแจ Public Key:**
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
   *(คัดลอกข้อความยาวๆ ที่ขึ้นต้นด้วย `ssh-ed25519 AAAA......`)*
4. **นำไปใส่ใน GitHub:**
   * ไปที่: [https://github.com/Pizz4Hut/edge-prototype-gen-1/settings/keys](https://github.com/Pizz4Hut/edge-prototype-gen-1/settings/keys)
   * คลิก **Add deploy key**
   * **Title:** ใส่ชื่อเครื่อง เช่น `gse-proto-1` (หรือ `gse-proto-2`)
   * **Key:** วางข้อความที่ก๊อปมา
   * ⚠️ **ไม่ต้องติ๊ก Allow write access** (ให้สิทธิ์แค่ Read-only เพื่อความปลอดภัยสูงสุด)
   * คลิก **Add key**

---

### ขั้นตอนที่ 3: ดาวน์โหลดและติดตั้ง Edge Gateway
```bash
# 1. ติดตั้งไลบรารีพื้นฐานและ Snap7
sudo apt update && sudo apt install -y git libsnap7-dev libsnap7-1 python3-pip
sudo pip3 install python-snap7 --break-system-packages

# 2. Clone คลังโปรเจกต์ผ่าน SSH
git clone git@github.com:Pizz4Hut/edge-prototype-gen-1.git
cd edge-prototype-gen-1/pi-client

# 3. รันตัวติดตั้งและลงทะเบียน Background Service อัตโนมัติ
chmod +x setup_plc_gateway.sh
./setup_plc_gateway.sh

# 4. ดู Hardware Profile (MAC Address & Serial Number)
python3 plc_gateway.py --info
```

---

### ขั้นตอนที่ 4: การตั้งค่าไฟล์ `config_plc.json` (Device 1 vs Device 2)

#### 📌 สำหรับเครื่องที่ 1: `gse-proto-1` (Master Gateway)
```json
{
  "deviceId": "edge-prototype-gen1-001",
  "deviceName": "Edge Prototype Gen-1",
  "serialNumber": "auto",
  "api": {
    "telemetryUrl": "https://rpi11232.netlify.app/api/telemetry",
    "batchTelemetryUrl": "https://rpi11232.netlify.app/api/telemetry/batch",
    "heartbeatUrl": "https://rpi11232.netlify.app/api/heartbeat",
    "transmissionIntervalSec": 3600,
    "heartbeatIntervalSec": 30
  },
  "plc": {
    "ip": "192.168.2.2",
    "port": 102,
    "simulate": false
  }
}
```

#### 📌 สำหรับเครื่องที่ 2: `gse-proto-2` (Redundant Backup)
```json
{
  "deviceId": "gse-proto-2",
  "deviceName": "Edge Prototype Gateway 2 (Backup)",
  "serialNumber": "auto",
  "api": {
    "telemetryUrl": "https://rpi11232.netlify.app/api/telemetry",
    "batchTelemetryUrl": "https://rpi11232.netlify.app/api/telemetry/batch",
    "heartbeatUrl": "https://rpi11232.netlify.app/api/heartbeat",
    "transmissionIntervalSec": 3600,
    "heartbeatIntervalSec": 30
  },
  "plc": {
    "ip": "192.168.2.2",
    "port": 102,
    "simulate": false
  }
}
```

---

### ขั้นตอนที่ 5: การรันบอร์ดที่ 3 เป็น Siemens S7-1200 PLC Simulator (Port 102)

1. บนบอร์ดที่ 3 (`dgpx@edge-gateway` IP: `192.168.2.2`):
   ```bash
   sudo apt update && sudo apt install -y git libsnap7-dev libsnap7-1 python3-pip
   sudo pip3 install python-snap7 --break-system-packages
   git clone git@github.com:Pizz4Hut/edge-prototype-gen-1.git
   cd edge-prototype-gen-1/pi-client
   ```
2. รันจำลองตู้ PLC (ต้องใช้ `sudo` เพราะพอร์ต 102 เป็น Well-known port):
   ```bash
   sudo python3 s7_server_simulator.py
   ```
   * ตัวจำลองจะสร้าง **Data Block 1 (DB1)** ขนาด 128 ไบต์
   * ป้อนค่าจำลอง 19 Tags สดๆ ทุก 2 วินาที
   * อ่านค่าและตรวจสอบ **Gateway Lifebit (`DB1.DBX0.0`)** จาก Gateway ทั้ง 2 เครื่อง

---

## 🔍 การตรวจสอบสถานะและแก้ไขปัญหา (Troubleshooting & Verification)

### 1. วิธีเช็คสถานะ Heartbeat แบบ Real-time บนบอร์ด Pi:
```bash
sudo journalctl -u plc-gateway -f
```
* **สภาวะปกติ:** จะขึ้น `💓 Heartbeat OK (200) | PLC Connected: True | Queue: 0`
* **หากบอร์ด 3 (PLC) หลุด:** จะขึ้นเตือน `PLC Connected: False` ทันที

### 2. วิธีเช็คว่า Device 1 หลุดหรือไม่ (จากฝั่ง Device 2 หรือ Mac):
* **Ping ตรงข้ามเครื่องผ่าน Switching Hub:**
  ```bash
  ping -c 3 192.168.2.4
  ```
* **เช็คสถานะจาก Cloud Server ผ่าน cURL:**
  ```bash
  curl -s "https://rpi11232.netlify.app/api/devices/edge-prototype-gen1-001" | grep -o '"status":"[^"]*"'
  ```
  *(หากเครื่อง 1 ดับเกิน 2 นาที จะตอบกลับมาว่า `"status":"offline"`)*

### 3. รันระบบตรวจเช็คสุขภาพอัตโนมัติ (Automated Self-Diagnosis):
```bash
python3 plc_gateway.py --diagnose
```

---

## 🧪 การรัน Burn-in Stability Test (TOR ข้อ 2.3)

เพื่อทดสอบความเสถียรต่อเนื่อง 24–72 ชั่วโมง และออกรายงานผลตามข้อกำหนดใน TOR:

```bash
# รันแบบ Background ปล่อยเครื่องทำงานข้ามคืนได้เลย
nohup python3 plc_simulator.py --hours 24 --interval 10 --log burnin_24h.log > burnin.out 2>&1 &

# เปิดดูความคืบหน้าแบบ Real-time
tail -f burnin_24h.log
```

---

## 📁 รายการไฟล์สำคัญใน `pi-client/`

| ชื่อไฟล์ | คำอธิบาย |
| :--- | :--- |
| `plc_gateway.py` | โปรแกรมหลักของ Gateway (ดึงค่า PLC, ส่ง HTTP API, จัดการ Redundancy & Heartbeat) |
| `sqlite_buffer.py` | ระบบฐานข้อมูล SQLite Store-and-Forward เก็บข้อมูลออฟไลน์ป้องกันข้อมูลสูญหาย |
| `pnr_generator.py` | โมดูลคำนวณรหัส PNR 6 หลัก Base32 (ตัด 0, 1, O, I) พร้อมระบบกันชน Collision-Free |
| `diagnose.py` | เครื่องมือตรวจเช็คสุขภาพระบบ วินิจฉัยปัญหา และให้คำแนะนำแก้ไขอัตโนมัติ (Self-Diagnosis) |
| `s7_server_simulator.py`| โปรแกรมเปลี่ยน Raspberry Pi อีกตัวให้กลายเป็น Siemens S7-1200 PLC Server (Port 102) |
| `plc_driver.py` | ไดรเวอร์ S7comm รองรับ Siemens S7-1200 และโหมดจำลอง Simulation |
| `plc_simulator.py` | สคริปต์รัน Burn-in Test 24-72 ชม. และออกรายงานผล HTTP 200 OK |
| `config_plc.json` | ไฟล์คอนฟิก IP, พอร์ต, ความถี่การส่ง, และตาราง Memory Map 19 Tags |
| `setup_plc_gateway.sh`| สคริปต์ 1-Click ติดตั้ง Dependencies และลงทะเบียน Service บน Raspberry Pi 4 |
