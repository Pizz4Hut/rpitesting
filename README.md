# 🏭 Siemens S7-1200 IoT Edge Gateway (Raspberry Pi 4)
## ระบบส่งข้อมูลจากเครื่องจักรขึ้น HTTP REST API พร้อม Redundancy & Heartbeat 2 ทิศทาง

ระบบ IoT Edge Gateway ออกแบบมาสำหรับติดตั้งบน **Raspberry Pi 4** เพื่อดึงข้อมูลจาก **PLC Siemens S7-1200** ผ่าน S7comm Protocol (TCP Port 102) และส่งข้อมูลไปยัง **HTTP REST API** ตามข้อกำหนดใน TOR โดยมีระบบ **Redundancy (Store-and-Forward SQLite)** และ **Two-way Heartbeat** เพื่อความเสถียรสูงสุด ป้องกันข้อมูลสูญหาย 100%

---

## 📌 สรุปภาพรวมและผังระบบ (System Architecture)

```
[ Siemens S7-1200 PLC ] (192.168.0.10:102)
          │
          │ LAN 1 (eth0: 192.168.0.50 / 0.51)
          ▼
[ Raspberry Pi 4 Edge Gateway ]
  ├─ gse-proto-1 (Master Gateway)
  └─ gse-proto-2 (Redundant Backup)
          │
          │ LAN 2 (eth1 / Wi-Fi)
          ▼
   Switching Hub ──► [ Mac / Workstation / Internet Router ]
          │
          ▼
[ HTTP/HTTPS REST API Endpoint ]
```

---

## ⚙️ คุณสมบัติเด่นของระบบ (Core Features)

1. **ดึงข้อมูล Siemens S7-1200 (19 Tags)**:
   - สื่อสารผ่าน S7comm protocol (Port 102) อ้างอิง Direct DB Addressing (`DB1.DBD0`, `DB1.DBW4`, `DB1.DBX60.0` ฯลฯ)
2. **ระบบ Redundancy: Store-and-Forward (SQLite WAL Mode)**:
   - หากยิง HTTP API ไม่สำเร็จ หรือเครือข่ายอินเทอร์เน็ตหลุด ข้อมูลจะไม่สูญหาย แต่จะถูกพักเก็บใน SQLite database (`buffer.db`) ภายในตัวบอร์ด Pi
   - เมื่อระบบเครือข่ายกลับมาเชื่อมต่อได้ ตัว Replay Drainer จะดึงข้อมูลย้อนหลังส่งขึ้น API เป็นชุด (Batch Replay) ตามลำดับเวลา FIFO โดยคง Timestamp ดั้งเดิม
3. **ระบบ Heartbeat 2 ทิศทาง (Two-way Heartbeat)**:
   - **Gateway ⟷ Cloud/Server**: ส่ง Heartbeat Ping ทุกๆ 30 วินาที ผ่าน HTTP POST รายงาน CPU Temp, RAM, Disk, สถานะการเชื่อมต่อ PLC และจำนวนคิวออฟไลน์ที่ค้างอยู่
   - **Gateway ⟷ PLC**: สลับบิต Lifebit (`DB1.DBX0.0`) ทุกๆ 5 วินาที เพื่อให้ Ladder Logic ใน PLC ตรวจจับได้ หาก Gateway หยุดทำงาน PLC สามารถส่ง Alarm เตือนหน้าตู้ได้ทันที
4. **ตรวจจับ Hardware Profile อัตโนมัติ (MAC Address & Serial Number)**:
   - มีคำสั่ง `python3 plc_gateway.py --info` เพื่อแสดง MAC Address ของทั้ง 2 พอร์ต LAN และ Serial Number ที่อ่านจากชิป CPU BCM2711 อัตโนมัติ เพื่อนำไปลงทะเบียน Firewall / MAC Filtering

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

> [!TIP]
> **หากเกิดปัญหา `Connection refused port 22`:**
> เกิดจากตอนเบิร์นลืมติ๊กเปิด SSH วิธีแก้คือถอด SD Card มาเสียบ Mac แล้วสร้างไฟล์เปล่าชื่อ `ssh` ไว้ที่ไดรฟ์บูต (`touch /Volumes/bootfs/ssh` หรือ `touch /Volumes/boot/ssh`) แล้วเสียบกลับเปิดเครื่องใหม่

---

### ขั้นตอนที่ 2: การต่อสายฮาร์ดแวร์ (Hardware Wiring)
* **พอร์ต LAN ในตัวบอร์ด Pi (`eth0`):** เสียบเข้าพอร์ต LAN ของ Siemens S7-1200 PLC
* **พอร์ต LAN เสริมผ่าน USB (`eth1`):** เสียบเข้า Switching Hub ร่วมกับสายแลนจาก Mac หรือ Router อินเทอร์เน็ต

---

### ขั้นตอนที่ 3: การตั้งค่าฝั่ง PLC Siemens S7-1200 (TIA Portal)
1. **เปิดฟังก์ชัน PUT/GET:**
   * เปิด TIA Portal &rarr; ไปที่ `Device Configuration` &rarr; ดับเบิลคลิก CPU S7-1200
   * ไปที่แท็บ `Properties` &rarr; `Protection & Security` &rarr; `Connection mechanisms`
   * ติ๊กถูกที่ **☑ "Permit access with PUT/GET communication from remote partner"**
2. **ปลด Optimized Block Access:**
   * คลิกขวาที่ Data Block `DB1` &rarr; เลือก `Properties` &rarr; แท็บ `Attributes`
   * **เอาเครื่องหมายถูกออก (Uncheck)** จากช่อง **☐ "Optimized block access"**
   * Compile และ Download ลง PLC

---

### ขั้นตอนที่ 4: การติดตั้งโปรแกรมบน Raspberry Pi
เชื่อมต่อ SSH เข้าไปยังบอร์ด Pi:
```bash
# สำหรับเครื่องที่ 1
ssh groundshift_supreme_admin@gse-proto-1.local

# สำหรับเครื่องที่ 2
ssh groundshift_supreme_admin@gse-proto-2.local
```
*(กรอกรหัสผ่าน: `abcd1234#`)*

เมื่อล็อกอินสำเร็จ ให้รันคำสั่งติดตั้งโปรเจกต์:

#### 🔐 4.1 ติดตั้ง Git และตั้งค่า Deploy Key (สำหรับคลัง Private Repository)
เนื่องจากโปรเจกต์เป็นงานความปลอดภัยสูงที่ต้องรักษาเป็น **Private Repository** แนะนำให้เชื่อมต่อผ่าน **Deploy Key (Read-only)** ตามมาตรฐานสากล:

1. **ติดตั้ง Git:**
   ```bash
   sudo apt update && sudo apt install -y git
   ```

2. **สร้าง SSH Key ประจำตัวบอร์ด Pi:**
   ```bash
   ssh-keygen -t ed25519 -C "rpi-gateway" -N "" -f ~/.ssh/id_ed25519
   ```

3. **ดูกุญแจ Public Key เพื่อนำไปใส่ใน GitHub:**
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
   *(คัดลอกข้อความทั้งหมดที่ขึ้นต้นด้วย `ssh-ed25519 AAAA...... rpi-gateway`)*

4. **เพิ่ม Deploy Key ใน GitHub:**
   * เปิดเบราว์เซอร์ไปที่: [github.com/Pizz4Hut/edge-prototype-gen-1/settings/keys](https://github.com/Pizz4Hut/edge-prototype-gen-1/settings/keys)
   * คลิก **Add deploy key**
   * **Title:** ใส่ชื่อเครื่อง เช่น `gse-proto-1` (หรือ `gse-proto-2`)
   * **Key:** วางข้อความกุญแจที่คัดลอกมา
   * ⚠️ **ไม่ต้องติ๊ก Allow write access** *(ปล่อยว่างไว้ เพื่อให้บอร์ดมีสิทธิ์แค่ Read-only ปลอดภัยสูงสุด 100%)*
   * คลิก **Add key**

---

#### 🚀 4.2 ดาวน์โหลดและติดตั้ง Edge Gateway
```bash
# 1. Clone คลังโปรเจกต์ผ่าน SSH (ปลอดภัยและไม่ต้องใส่รหัสผ่าน)
git clone git@github.com:Pizz4Hut/edge-prototype-gen-1.git
cd edge-prototype-gen-1/pi-client

# 2. รันสคริปต์ติดตั้งระบบอัตโนมัติ
chmod +x setup_plc_gateway.sh
./setup_plc_gateway.sh

# 3. ตรวจสอบ Hardware MAC Address และ Serial Number ประจำบอร์ด
python3 plc_gateway.py --info
```

ผลลัพธ์จะแสดงข้อมูลดังนี้:
```text
=================================================================
🍓 Raspberry Pi 4 Edge Gateway - Hardware & Network Profile
=================================================================
Device Name:     Edge Prototype Gen-1
Device ID:       gse-proto-1
Serial Number:   10000000a1b2c3d4 (อ่านจาก CPU RPi4 อัตโนมัติ)
-----------------------------------------------------------------
LAN 1 (PLC Network):     eth0
  IP Address:            192.168.0.50
  MAC Address:           b8:27:eb:11:22:33  <-- นำไปลงทะเบียนวง PLC
  Target PLC IP:         192.168.0.10:102
-----------------------------------------------------------------
LAN 2 (Internet / API):  eth1
  IP Address:            192.168.1.100
  MAC Address:           00:e0:4c:53:44:55  <-- นำไปส่งให้ IT ทำ Whitelist
=================================================================
```

---

---

### ขั้นตอนที่ 5: การตั้งค่าไฟล์ `config_plc.json` (Device 1 vs Device 2)

> [!IMPORTANT]
> **ทั้ง Device 1 และ Device 2 ใช้ Source Code เดียวกัน 100%** ต่างกันแค่ค่าคอนฟิกและ IP เท่านั้น

เปิดแก้ไขไฟล์ตั้งค่า:
```bash
nano config_plc.json
```

#### 📌 สำหรับเครื่องที่ 1: `gse-proto-1` (Master Gateway)
```json
{
  "deviceId": "gse-proto-1",
  "deviceName": "Edge Prototype Gateway 1 (Master)",
  "serialNumber": "auto",
  "network": {
    "lan1_plc_interface": "eth0",
    "lan1_plc_ip": "192.168.0.50",
    "lan2_internet_interface": "eth1",
    "lan2_internet_ip": "192.168.1.100"
  },
  "api": {
    "telemetryUrl": "http://YOUR_API_SERVER/api/telemetry",
    "batchTelemetryUrl": "http://YOUR_API_SERVER/api/telemetry/batch",
    "heartbeatUrl": "http://YOUR_API_SERVER/api/heartbeat",
    "transmissionIntervalSec": 3600,
    "heartbeatIntervalSec": 30
  },
  "plc": {
    "ip": "192.168.0.10",
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
  "network": {
    "lan1_plc_interface": "eth0",
    "lan1_plc_ip": "192.168.0.51",
    "lan2_internet_interface": "eth1",
    "lan2_internet_ip": "192.168.1.101"
  },
  "api": {
    "telemetryUrl": "http://YOUR_API_SERVER/api/telemetry",
    "batchTelemetryUrl": "http://YOUR_API_SERVER/api/telemetry/batch",
    "heartbeatUrl": "http://YOUR_API_SERVER/api/heartbeat",
    "transmissionIntervalSec": 3600,
    "heartbeatIntervalSec": 30
  },
  "plc": {
    "ip": "192.168.0.10",
    "simulate": false
  }
}
```

#### 📊 ตารางเปรียบเทียบการตั้งค่า (Configuration Summary):
| รายการ | เครื่องที่ 1 (`gse-proto-1`) | เครื่องที่ 2 (`gse-proto-2`) | หมายเหตุ |
| :--- | :--- | :--- | :--- |
| **บทบาท** | Master Gateway (ตัวหลัก) | Redundant Backup (ตัวสำรอง) | รันโค้ดเดียวกัน 100% |
| **`deviceId`** | `gse-proto-1` | `gse-proto-2` | ใช้ระบุตัวตนใน REST API |
| **`serialNumber`** | `"auto"` | `"auto"` | แต่ละบอร์ดจะอ่าน CPU Serial ไม่ซ้ำกัน |
| **`lan1_plc_ip`** | `192.168.0.50` | `192.168.0.51` | ต้องไม่ชนกันในวง PLC |
| **`lan2_internet_ip`** | `192.168.1.100` | `192.168.1.101` | หรือใช้ DHCP ตามระบบโรงงาน |
| **PLC Target** | `192.168.0.10:102` | `192.168.0.10:102` | ชี้เข้าหา PLC S7-1200 ตัวเดียวกัน |


---

### ขั้นตอนที่ 6: การทดสอบและการเปิดทำงานอัตโนมัติ 24/7

#### 1. ทดสอบรันดึงค่าและส่งขึ้น API (1 รอบ):
```bash
python3 plc_gateway.py --once
```

#### 2. ทดสอบ Burn-in Stability Test (24 - 72 ชั่วโมง ตาม TOR ข้อ 2.3):
```bash
python3 plc_simulator.py --hours 24 --interval 10 --log burnin_report.log
```

#### 3. เปิดให้ทำงานอัตโนมัติเป็น Background Service:
```bash
# เริ่มรัน Service
sudo systemctl start plc-gateway

# เช็คสถานะการทำงาน (ต้องขึ้นสีเขียว active running)
sudo systemctl status plc-gateway

# ดู Live Log การทำงาน
sudo journalctl -u plc-gateway -f
```

---

## 📁 รายการไฟล์สำคัญใน `pi-client/`

| ชื่อไฟล์ | คำอธิบาย |
| :--- | :--- |
| `plc_gateway.py` | โปรแกรมหลักของ Gateway (ดึงค่า PLC, ส่ง HTTP API, จัดการ Redundancy & Heartbeat) |
| `sqlite_buffer.py` | ระบบฐานข้อมูล SQLite Store-and-Forward เก็บข้อมูลออฟไลน์ป้องกันข้อมูลสูญหาย |
| `plc_driver.py` | ไดรเวอร์ S7comm รองรับ Siemens S7-1200 และโหมดจำลอง Simulation |
| `plc_simulator.py` | สคริปต์รัน Burn-in Test 24-72 ชม. และออกรายงานผล HTTP 200 OK |
| `config_plc.json` | ไฟล์คอนฟิก IP, พอร์ต, ความถี่การส่ง, และตาราง Memory Map 19 Tags |
| `plc-gateway.service`| ไฟล์ Unit Service สำหรับตั้งค่าให้ระบบทำงานอัตโนมัติ 24/7 บน systemd |
| `setup_plc_gateway.sh`| สคริปต์ 1-Click ติดตั้ง Dependencies และลงทะเบียน Service บน Raspberry Pi 4 |

---

## 🐙 การจัดการ Git Repository

โปรเจกต์นี้ผูก Remote สำหรับคลังหลักไว้เรียบร้อยแล้ว:
```bash
# Push ขึ้นคลังหลัก edge-prototype-gen-1
git add .
git commit -m "feat: complete S7-1200 Edge Gateway with Redundancy, Heartbeat, MAC, and Serial detection"
git push -u prototype main
```
