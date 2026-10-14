# 🏭 Siemens S7-1200 Industrial IoT Edge Gateway (Raspberry Pi 4)
## ระบบส่งข้อมูลจากเครื่องจักรขึ้น HTTP REST API พร้อม Redundancy, Two-Way Heartbeat & PNR Tracking

ระบบ IoT Edge Gateway ออกแบบมาสำหรับติดตั้งบน **Raspberry Pi 4 Model B** เพื่อดึงข้อมูลจาก **PLC Siemens S7-1200** ผ่าน S7comm Protocol (TCP Port 102) และส่งข้อมูลไปยัง **HTTP REST API** ตามข้อกำหนดใน TOR โดยมีระบบ **Redundancy (Store-and-Forward SQLite WAL Mode)**, **Two-way Heartbeat (Gateway ⟷ Server & Gateway ⟷ PLC)**, และ **PNR Reference Code Generation (Crockford Base32 6 หลัก)** ป้องกันข้อมูลสูญหาย 100%

🌐 **Official Railway Cloud API:** [https://epc-edge-api-dev.up.railway.app/api](https://epc-edge-api-dev.up.railway.app/api)

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
                 │ HTTP POST Telemetry Batches & Heartbeat (SSL/TLS)
                 ▼
 ☁️ [ Official Railway Cloud API: https://epc-edge-api-dev.up.railway.app/api ]
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

---

### ขั้นตอนที่ 4: การตั้งค่าเชื่อมต่อ Cloud API (Railway Production Credentials)

ระบบได้เตรียมไฟล์คอนฟิกสำเร็จรูปที่ผูกกับ **Official API Key & Device ID** ของแต่ละบอร์ดไว้เรียบร้อยแล้ว:

> ⚠️ **หมายเหตุสำคัญก่อน Pull:** หากในบอร์ดเคยมีการแก้ไขหรือแตะไฟล์ `config_plc.json` ไว้ Git จะแจ้งเตือนและระงับการดึงไฟล์ใหม่ ทำให้มองไม่เห็นไฟล์ `config_proto1.json` **จำเป็นต้องสั่ง `git stash` เพื่อเคลียร์ค้างก่อนเสมอ**

#### 📌 สำหรับเครื่องที่ 1: `gse-proto-1` (Master Gateway)
* **Device ID:** `4045f327-2776-4f34-977e-64e307db648f`
* **API Key:** `gs_17ed8df023f46e3815c2cefd18ecab43e664bd187244012f0aed619c4e7a5a70`
* **API Base:** `https://epc-edge-api-dev.up.railway.app/api`
* **คำสั่งอัปเดตและเปิดใช้งานบนบอร์ด 1 (ทำตามลำดับ):**
  ```bash
  # 1. เข้าโฟลเดอร์ pi-client
  cd ~/edge-prototype-gen-1/pi-client

  # 2. เก็บพักไฟล์ที่เคยแก้ค้างไว้ เพื่อไม่ให้ Git ชนกัน
  git stash

  # 3. ดึงโค้ดและไฟล์คอนฟิกใหม่ล่าสุดจาก GitHub
  git pull origin main

  # 4. เช็คดูว่าไฟล์คอนฟิกตัวใหม่มาแล้วแน่นอน
  ls -la config_proto1.json

  # 5. นำคอนฟิกไปใช้งานและรีสตาร์ท Service
  cp config_proto1.json config_plc.json
  plc-restart
  ```

#### 📌 สำหรับเครื่องที่ 2: `gse-proto-2` (Redundant Backup)
* **Device ID:** `24207b3f-da30-44e7-91f9-8d0067a5d1af`
* **API Key:** `gs_505a9bb4652c76548e1f2c229ac3055a334b47e38e105192ce7dfb24d0e743c6`
* **API Base:** `https://epc-edge-api-dev.up.railway.app/api`
* **คำสั่งอัปเดตและเปิดใช้งานบนบอร์ด 2 (ทำตามลำดับ):**
  ```bash
  # 1. เข้าโฟลเดอร์ pi-client
  cd ~/edge-prototype-gen-1/pi-client

  # 2. เก็บพักไฟล์ที่เคยแก้ค้างไว้
  git stash

  # 3. ดึงโค้ดและไฟล์คอนฟิกใหม่ล่าสุดจาก GitHub
  git pull origin main

  # 4. เช็คดูว่าไฟล์คอนฟิกตัวใหม่มาแล้วแน่นอน
  ls -la config_proto2.json

  # 5. นำคอนฟิกไปใช้งานและรีสตาร์ท Service
  cp config_proto2.json config_plc.json
  plc-restart
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

## 🧰 IoT Edge Gateway CLI Toolbox (ชุดคำสั่งลัดประจำตู้คอนโทรล)

เพื่อให้วิศวกรหน้างานและผู้ดูแลระบบสามารถสั่งการได้สะดวกรวดเร็วที่สุด **โดยไม่ต้องจำชื่อโฟลเดอร์หรือพิมพ์ `cd` เข้าไปก่อน** ระบบได้ติดตั้งคำสั่งลัดระดับระบบ (Global Commands ใน `/usr/local/bin`) ไว้ให้ใช้งานได้จากทุกที่ใน Terminal ทันที:

### ⚙️ คำสั่งติดตั้งชุด Toolbox (รันครั้งเดียว):
```bash
cd ~/edge-prototype-gen-1/pi-client
./install_toolbox.sh
```

### 📋 สรุปรายการคำสั่ง Toolbox ที่ใช้งานได้ทันทีจากทุกโฟลเดอร์:

| คำสั่งลัด | ความสามารถและหน้าที่ | คำสั่งเดิมที่เทียบเท่า |
| :--- | :--- | :--- |
| **`plc-config`** | ⚙️ **ตั้งค่าระบบและทดสอบ HTTPS Cloud:** สลับ Preset 1/2, เปลี่ยน API Key/Device ID/URL หรือเปิด Web Configurator | `python3 config_tool.py` |
| **`plc-toolbox`** | 🧰 **เปิดสารบัญคำสั่งลัดทั้งหมด:** ดู Cheat Sheet คำสั่งทั้งหมดในหน้าเดียว | เมนูช่วยเหลือ |
| **`plc-runtime`** | ☁️ **ดูสถานะ Cloud Runtime สดๆ:** เช็คว่า Cloud Railway มองเห็นบอร์ดหรือไม่ | `curl Railway API` |
| **`plc-info`** | 🏷️ **แสดง Hardware Profile:** MAC Address, Serial, IP วงใน, Tailscale VPN | `python3 plc_gateway.py --info` |
| **`plc-diagnose`** | 🩺 **รันระบบตรวจสุขภาพ 7 จุด (Self-Diagnosis):** สรุปสถานะเขียว/เหลือง/แดง | `python3 plc_gateway.py --diagnose` |
| **`plc-test`** | 🚀 **ทดสอบดึงค่าและส่งขึ้น API (1 รอบ):** อ่าน PLC และยิง Cloud ทันที | `python3 plc_gateway.py --once` |
| **`plc-status`** | 🟢 **เช็คสถานะ Service 24/7:** ดูว่า Gateway กำลัง Active หรือไม่ | `sudo systemctl status plc-gateway` |
| **`plc-logs`** | 📜 **ดู Live Stream Logs:** มอนิเตอร์รอบส่ง Heartbeat และการอ่าน PLC สดๆ | `sudo journalctl -u plc-gateway -f` |
| **`plc-restart`** | 🔄 **รีสตาร์ท Gateway ทันที:** ปิดและเปิดระบบใหม่แบบนุ่มนวล | `sudo systemctl restart plc-gateway` |
| **`plc-start`** | ▶️ **สั่งเริ่มทำงาน Gateway Service:** เปิดการทำงานระดับ Systemd | `sudo systemctl start plc-gateway` |
| **`plc-stop`** | ⏹️ **สั่งหยุดการทำงาน Gateway Service:** หยุด Service ชั่วคราว | `sudo systemctl stop plc-gateway` |
| **`plc-buffer`** | 📦 **เช็คคิว SQLite Offline Buffer:** ดูจำนวนข้อมูลที่ค้างส่งและ PNR ล่าสุด | Query SQLite WAL |
| **`plc-burnin`** | 🔥 **รัน Burn-in Stability Test 24 ชม.:** ทดสอบความเสถียรตาม TOR 2.3 | `python3 plc_simulator.py` |
| **`plc-sim`** | 🏭 **สตาร์ทตัวจำลอง Siemens S7-1200 PLC:** รันเซิร์ฟเวอร์ Port 102 บนบอร์ด 3 | `sudo python3 s7_server_simulator.py` |

### 🛠️ คู่มือการใช้งาน `plc-config` (Interactive CLI & Web Configurator):

เครื่องมือสำหรับตรวจสอบและปรับแต่ง Device ID, API Key, HTTPS URL, Heartbeat/Batch Rate และ PLC IP อย่างสะดวกรวดเร็ว:

1. **โหมด Interactive เมนู (Wizard):**
   ```bash
   plc-config
   ```
   * เลือกเมนู `1` เพื่อสลับเป็นโปรไฟล์ **GSE-PROTO-1** ทันที
   * เลือกเมนู `2` เพื่อสลับเป็นโปรไฟล์ **GSE-PROTO-2** ทันที
   * เลือกเมนู `3` ถึง `7` เพื่อแก้ไข HTTPS URL, API Key, Device ID, หรือ PLC IP
   * เลือกเมนู `8` เพื่อทดสอบเชื่อมต่อ **Live HTTPS Cloud API**
   * เลือกเมนู `9` เพื่อเปิด **Web Configurator Dashboard**
   * เลือกเมนู `R` เพื่อรีสตาร์ท Service `plc-gateway`

2. **โหมดคำสั่งด่วน (Command-line Flags):**
   ```bash
   # สลับโปรไฟล์เป็น GSE-PROTO-1 ทันที
   plc-config --set-proto1 --restart

   # สลับโปรไฟล์เป็น GSE-PROTO-2 ทันที
   plc-config --set-proto2 --restart

   # ทดสอบการเชื่อมต่อ HTTPS Cloud API สดๆ
   plc-config --test

   # ดูการตั้งค่าปัจจุบันทั้งหมด
   plc-config --view

   # เปลี่ยน Cloud HTTPS Base URL
   plc-config --set-url "https://epc-edge-api-dev.up.railway.app/api"
   ```

3. **โหมด Web Configurator (ปรับแต่งผ่านเว็บเบราว์เซอร์):**
   ```bash
   plc-config --web
   ```
   * ระบบจะเปิด Web Server พอร์ต `8080` (เช่น `http://192.168.2.4:8080`)
   * สามารถเปิดผ่าน Browser บนโน้ตบุ๊กหรือมือถือในวง LAN เดียวกันเพื่อกดสลับโปรไฟล์, แก้ไขค่า API Key, และกดทดสอบ HTTPS ได้ด้วยคลิกเดียว

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
* **เช็คสถานะจาก Cloud Server ด้วยคำสั่งลัด:**
  ```bash
  plc-runtime
  ```
* **หรือเช็คตรงผ่าน Railway Cloud REST API:**
  ```bash
  curl -s -H "x-api-key: gs_17ed8df023f46e3815c2cefd18ecab43e664bd187244012f0aed619c4e7a5a70" \
    "https://epc-edge-api-dev.up.railway.app/api/edge/devices/4045f327-2776-4f34-977e-64e307db648f"
  ```
  *(จะตอบกลับ JSON ข้อมูลอุปกรณ์ พร้อม Cloud Status เช่น `"ACTIVE"` และ `"last_seen_at"`)*

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

## 🌐 การติดตั้ง Tailscale VPN สำหรับรีโมทควบคุมระยะไกล (Remote Setup & Maintenance)

เพื่อความสะดวกและปลอดภัยในการ SSH เข้าควบคุมบอร์ด Raspberry Pi จากที่ใดก็ได้ในโลก (ไม่ต้องเปิดพอร์ตหรือทำ Port Forwarding):

```bash
# 1. ติดตั้ง Tailscale บนตัวบอร์ด
sudo apt update && sudo apt install -y tailscale

# 2. เริ่มเชื่อมต่อและเปิดฟังก์ชัน Tailscale SSH
sudo tailscale up --ssh

# 3. นำลิงก์ล็อกอินที่ปรากฏบนหน้าจอไปเปิดในเบราว์เซอร์เพื่อยืนยันสิทธิ์
# 4. เช็คหมายเลข IP ของบอร์ดในวง Tailscale (IP วง 100.x.y.z)
tailscale ip -4
tailscale status
```

### 💻 คำสั่งสั่งการและดูแลรักษาระยะไกล (Remote Operations from Mac):
* **SSH เข้า Terminal ข้ามโลก:**
  ```bash
  ssh groundshift_supreme_admin@gse-proto-1
  ssh groundshift_supreme_admin@gse-proto-2
  ```
* **อัปเดตโค้ดและ Restart Service ทางไกล (1 บรรทัดจบ):**
  ```bash
  ssh groundshift_supreme_admin@gse-proto-1 "cd ~/edge-prototype-gen-1/pi-client && git pull && sudo systemctl restart plc-gateway"
  ```
* **รันตรวจเช็คสุขภาพระบบ (Self-Diagnosis) จากระยะไกล:**
  ```bash
  ssh groundshift_supreme_admin@gse-proto-1 "python3 ~/edge-prototype-gen-1/pi-client/plc_gateway.py --diagnose"
  ```
* **สตรีมดู Live Log ของตู้โรงงานแบบสดๆ บนจอคอมของคุณ:**
  ```bash
  ssh groundshift_supreme_admin@gse-proto-1 "sudo journalctl -u plc-gateway -f"
  ```
* **คัดลอกไฟล์คอนฟิกจากเครื่อง Mac ขึ้นไปทับบนบอร์ด Pi:**
  ```bash
  scp config_plc.json groundshift_supreme_admin@gse-proto-1:~/edge-prototype-gen-1/pi-client/
  ```

### 🌟 การเปิด Tailscale Subnet Router (เจาะทะลุไปถึงตู้ PLC Siemens หน้างาน):
หากต้องการให้โปรแกรม **Siemens TIA Portal บนคอมพิวเตอร์ของคุณ สามารถมองเห็นและโปรแกรม PLC S7-1200 (`192.168.2.2`) ที่ตั้งอยู่หน้างานโรงงานได้จากระยะไกล**:
1. บนบอร์ด Raspberry Pi ให้รันคำสั่งเปิดเป็น Subnet Router:
   ```bash
   sudo tailscale up --advertise-routes=192.168.2.0/24
   ```
2. บนหน้าเว็บ [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines):
   * คลิกปุ่ม `...` ที่ชื่อเครื่อง `gse-proto-1` &rarr; เลือก **Edit route settings**
   * ติ๊กถูกที่ช่อง **☑ `192.168.2.0/24`** &rarr; กด **Save**
3. เครื่องคอมพิวเตอร์ของคุณจะสามารถ Ping หรือเปิด TIA Portal ยิงตรงไปที่ IP `192.168.2.2:102` ของ PLC เสมือนนั่งอยู่หน้าตู้โรงงานทันที!

---

## 🔬 4 ด่านทดสอบพิสูจน์ระบบเสมือนจริง (Proof of Concept & Stress Testing Guide)

เพื่อพิสูจน์ให้เห็นจริงว่าระบบไม่ได้ทำงานแค่ใน Local และป้องกันข้อกังขาว่าระบบไม่ได้รันฟลุกๆ สามารถรันการทดสอบ 4 ด่านนี้ได้ทันที:

### ด่านที่ 1: พิสูจน์ว่าส่งข้อมูลขึ้น Cloud จริง (ไม่ใช่ Local)
1. บนบอร์ด Pi สามารถรันคำสั่งเช็คการเชื่อมต่อและการตอบกลับสดๆ จาก Cloud:
   ```bash
   plc-config --test
   ```
   * จะแสดงเวลา Latency ในหน่วย ms พร้อมสถานะ `Cloud Status: ACTIVE` และชื่อเครื่องที่ลงทะเบียนไว้
2. ตรวจสอบเส้นทางเครือข่ายไปยัง Cloud API Server:
   ```bash
   traceroute epc-edge-api-dev.up.railway.app
   ```
   * จะเห็นเส้นทาง Hop วิ่งข้ามอินเทอร์เน็ตสาธารณะออกไปยัง Cloud Infrastructure

### ด่านที่ 2: ดักจับแพ็กเก็ตโปรโตคอล S7comm (TCP Port 102) บนสาย LAN
พิสูจน์ว่าบอร์ด Gateway คุยกับบอร์ด PLC ด้วยโปรโตคอลอุตสาหกรรม Siemens ข้ามสายแลนจริง:
```bash
sudo apt install -y tcpdump
sudo tcpdump -i eth0 port 102 -n -X -c 5
```
* หน้าจอจะแสดงโครงสร้าง Hexadecimal ของ **ISO-on-TCP (COTP)** และ **S7comm Header** วิ่งข้ามสาย LAN จริงทุกรอบการอ่านค่า

### ด่านที่ 3: ทดสอบการอ่านค่าจากตู้ PLC จริง
1. เมื่อต่อสาย LAN กับตู้ PLC Siemens S7-1200 ที่ IP `192.168.2.2:102`
2. ทดสอบอ่านค่าและยิง Cloud ทันที 1 รอบ:
   ```bash
   plc-test
   ```
3. ผลลัพธ์ในหน้าจอจะแสดงค่าจริง 19 Tags ที่อ่านได้จาก Data Block พร้อมส่ง Telemetry Batch และ Heartbeat ขึ้น Cloud สำเร็จ (`HTTP 201 Created` / `HTTP 200 OK`)

### ด่านที่ 4: การทดสอบตัดเน็ตแต่ไม่ตัด PLC (พิสูจน์ Redundancy Store-and-Forward + PNR)
1. **ดึงสายแลนเส้นที่ต่ออินเทอร์เน็ตออก** (ให้บอร์ด Gateway ยังคุยกับ PLC ได้ แต่ต่อออกนอกไม่ได้)
2. รอประมาณ 1-2 นาที แล้วตรวจดูฐานข้อมูลออฟไลน์ในเครื่อง Gateway ด้วยคำสั่ง:
   ```bash
   plc-buffer
   ```
   * จะเห็นรายการข้อมูลพร้อมรหัส **PNR Code** ถูกกักเก็บใน SQLite (`buffer.db`) อย่างปลอดภัย
3. **เสียบสายแลนอินเทอร์เน็ตกลับเข้าที่:**
   * ภายใน 30 วินาที ตัว Replay Drainer จะดึงข้อมูลย้อนหลังทยอยส่งขึ้น Cloud API อัตโนมัติ และเคลียร์คิวในฐานข้อมูลกลับเป็น `0 Pending` โดยไม่มีข้อมูลสูญหาย 100%

---

## 📁 รายการไฟล์สำคัญใน `pi-client/`

| ชื่อไฟล์ | คำอธิบาย |
| :--- | :--- |
| `plc_config.py` / `plc-config` | เครื่องมือ Interactive CLI & Web ปรับแต่ง Device ID, API Key, HTTPS URL, สลับโปรไฟล์ Proto 1/2 และทดสอบ Live HTTPS |
| `install_toolbox.sh` | สคริปต์ติดตั้งคำสั่งลัดระดับระบบ (Global CLI Toolbox ใน `/usr/local/bin`) |
| `plc_gateway.py` | โปรแกรมหลักของ Gateway (ดึงค่า PLC, ส่ง Cloud Batches & Heartbeat, จัดการ Redundancy) |
| `plc_driver.py` | ไดรเวอร์ S7comm เชื่อมต่อตู้จริง Siemens S7-1200 (พอร์ต 102) พร้อมระบบตรวจจับสายหลุด |
| `sqlite_buffer.py` | ระบบฐานข้อมูล SQLite Store-and-Forward เก็บข้อมูลออฟไลน์ป้องกันข้อมูลสูญหาย |
| `pnr_generator.py` | โมดูลคำนวณรหัส PNR 6 หลัก Base32 (ตัด 0, 1, O, I) พร้อมระบบกันชน Collision-Free |
| `diagnose.py` | เครื่องมือตรวจเช็คสุขภาพระบบ วินิจฉัยปัญหา และให้คำแนะนำแก้ไขอัตโนมัติ (Self-Diagnosis) |
| `config_plc.json` | ไฟล์คอนฟิก IP, พอร์ต, ความถี่การส่ง, และตาราง Memory Map 19 Tags |
| `config_proto1.json` | ไฟล์ Preset คอนฟิกสำหรับเครื่อง GSE-PROTO-1 |
| `config_proto2.json` | ไฟล์ Preset คอนฟิกสำหรับเครื่อง GSE-PROTO-2 |
| `setup_plc_gateway.sh`| สคริปต์ 1-Click ติดตั้ง Dependencies และลงทะเบียน Service บน Raspberry Pi 4 |
| `s7_server_simulator.py`| โปรแกรมเปลี่ยน Raspberry Pi บอร์ด 3 ให้กลายเป็น Siemens S7-1200 PLC Server (Port 102) |
