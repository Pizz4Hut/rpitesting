#!/usr/bin/env bash
# ==============================================================================
# Siemens S7-1200 Industrial IoT Edge Gateway
# All-in-One Zero-Touch Installer & Interactive Terminal Management Hub
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_CLIENT_DIR="${SCRIPT_DIR}/pi-client"
CONFIG_FILE="${PI_CLIENT_DIR}/config_plc.json"

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

get_rpi_serial() {
    if [ -f "/proc/cpuinfo" ]; then
        grep Serial /proc/cpuinfo | awk '{print $3}' | tr -d '\n'
    else
        echo "UNKNOWN"
    fi
}

get_primary_mac() {
    if command -v ip &> /dev/null; then
        ip link show eth0 2>/dev/null | awk '/ether/ {print $2}' || echo "UNKNOWN"
    else
        echo "UNKNOWN"
    fi
}

detect_profile_name() {
    local serial="$(get_rpi_serial)"
    local mac="$(get_primary_mac | tr '[:upper:]' '[:lower:]')"

    if [ "$serial" = "1000000091f9071a" ] || [ "$mac" = "98:fe:54:63:34:ca" ]; then
        echo "GSE-PROTO-1 (Master)"
    elif [ "$serial" = "100000001b657629" ] || [ "$mac" = "98:fe:54:63:35:a5" ]; then
        echo "GSE-PROTO-2 (Backup)"
    else
        echo "Auto-Detect (${serial: -8})"
    fi
}

get_service_status() {
    if command -v systemctl &> /dev/null; then
        if systemctl is-active --quiet plc-gateway 2>/dev/null; then
            echo -e "${GREEN}● RUNNING (24/7 Active)${NC}"
        elif systemctl is-failed --quiet plc-gateway 2>/dev/null; then
            echo -e "${RED}● FAILED${NC}"
        else
            echo -e "${YELLOW}○ STOPPED${NC}"
        fi
    else
        echo -e "${CYAN}○ NOT INSTALLED (Non-systemd)${NC}"
    fi
}

get_target_plc_ip() {
    if [ -f "${CONFIG_FILE}" ]; then
        python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('plc',{}).get('ip','auto'))" 2>/dev/null || echo "Unknown"
    else
        echo "Not Configured"
    fi
}

# ------------------------------------------------------------------------------
# Action: 1-Click Zero-Touch Auto Install & Start
# ------------------------------------------------------------------------------
action_zero_touch_setup() {
    echo ""
    echo -e "${BOLD}${CYAN}========================================================================${NC}"
    echo -e "${BOLD}${CYAN}🚀 Executing 1-Click Zero-Touch Auto Installation & Provisioning${NC}"
    echo -e "${BOLD}${CYAN}========================================================================${NC}"
    echo ""

    # Step 1: Detect Hardware Profile
    echo -e "${BOLD}[1/7] 🎯 ตรวจจับลักษณะเฉพาะของบอร์ดฮาร์ดแวร์...${NC}"
    local detected="$(detect_profile_name)"
    echo -e "      👉 ตรวจพบบอร์ด: ${GREEN}${detected}${NC}"
    
    if [ "$detected" = "GSE-PROTO-1 (Master)" ]; then
        if [ -f "${PI_CLIENT_DIR}/config_proto1.json" ]; then
            cp "${PI_CLIENT_DIR}/config_proto1.json" "${CONFIG_FILE}"
            echo -e "      [✓] บันทึก Preset คอนฟิก: ${GREEN}GSE-PROTO-1${NC}"
        fi
    elif [ "$detected" = "GSE-PROTO-2 (Backup)" ]; then
        if [ -f "${PI_CLIENT_DIR}/config_proto2.json" ]; then
            cp "${PI_CLIENT_DIR}/config_proto2.json" "${CONFIG_FILE}"
            echo -e "      [✓] บันทึก Preset คอนฟิก: ${GREEN}GSE-PROTO-2${NC}"
        fi
    fi

    # Step 2: System Packages
    echo ""
    echo -e "${BOLD}[2/7] 📦 ตรวจสอบและติดตั้ง System Packages ที่จำเป็น...${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -y
        sudo apt-get install -y python3 python3-pip python3-psutil sqlite3 libsnap7-dev git watchdog curl
        echo -e "      [✓] ติดตั้ง System Dependencies เรียบร้อย"
    else
        echo -e "      ${YELLOW}[i] ข้าม apt-get (ตรวจไม่พบระบบ apt)${NC}"
    fi

    # Step 3: Python Libraries
    echo ""
    echo -e "${BOLD}[3/7] 🐍 ติดตั้ง Python Packages (python-snap7, requests)...${NC}"
    pip3 install python-snap7 requests --break-system-packages 2>/dev/null || pip3 install python-snap7 requests 2>/dev/null || true
    echo -e "      [✓] Python Libraries พร้อมใช้งาน"

    # Step 4: Hardware Watchdog
    echo ""
    echo -e "${BOLD}[4/7] 🛡️  เปิดใช้งาน Hardware Watchdog (BCM2711)...${NC}"
    if [ -f "/etc/modules" ]; then
        if ! grep -q "bcm2835_wdt" /etc/modules; then
            echo "bcm2835_wdt" | sudo tee -a /etc/modules > /dev/null
        fi
        echo -e "      [✓] Watchdog โมดูลลงทะเบียนเรียบร้อย"
    fi

    # Step 5: Global CLI Toolbox
    echo ""
    echo -e "${BOLD}[5/7] 🧰 ติดตั้ง Global CLI Toolbox เข้า /usr/local/bin...${NC}"
    if [ -f "${PI_CLIENT_DIR}/install_toolbox.sh" ]; then
        sudo bash "${PI_CLIENT_DIR}/install_toolbox.sh" > /dev/null
        # Link gateway command directly
        sudo ln -sf "${SCRIPT_DIR}/gateway.sh" /usr/local/bin/gateway
        sudo chmod +x /usr/local/bin/gateway
        echo -e "      [✓] คำสั่งระดับระบบ (gateway, plc-toolbox, plc-info ฯลฯ) พร้อมใช้งาน"
    fi

    # Step 6: Scan for PLC
    echo ""
    echo -e "${BOLD}[6/7] 🔍 สแกนค้นหาตู้ Siemens S7-1200 บนเครือข่ายอัตโนมัติ...${NC}"
    python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --discover || true

    # Step 7: Systemd Service Registration & Start
    echo ""
    echo -e "${BOLD}[7/7] ⚙️  ลงทะเบียนและเปิดใช้งาน Systemd Background Service (24/7)...${NC}"
    if [ -f "${PI_CLIENT_DIR}/setup_plc_gateway.sh" ]; then
        CURRENT_USER="${SUDO_USER:-$(whoami)}"
        sudo tee /etc/systemd/system/plc-gateway.service > /dev/null <<EOF
[Unit]
Description=Siemens S7-1200 IoT Edge Gateway Service
After=network-online.target time-sync.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PI_CLIENT_DIR}
ExecStart=/usr/bin/python3 ${PI_CLIENT_DIR}/plc_gateway.py --config ${CONFIG_FILE}
Restart=always
RestartSec=5s
Nice=-5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=plc-gateway

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable --now plc-gateway.service
        echo -e "      [✓] Service 'plc-gateway' สตาร์ตและพร้อมทำงานอัตโนมัติ 24/7!"
    fi

    echo ""
    echo -e "${BOLD}${GREEN}========================================================================${NC}"
    echo -e "${BOLD}${GREEN}🎉 การติดตั้ง Zero-Touch เสร็จสมบูรณ์ 100%! เกตเวย์กำลังทำงานในพื้นหลัง${NC}"
    echo -e "   • ดูสถานะการทำงาน:   ${YELLOW}plc-status${NC}  หรือ  ${YELLOW}gateway --status${NC}"
    echo -e "   • ดู Log แบบเรียลไทม์: ${YELLOW}plc-logs${NC}"
    echo -e "   • เปิดเมนูจัดการ:     ${YELLOW}gateway${NC}"
    echo -e "${BOLD}${GREEN}========================================================================${NC}"
    echo ""
}

# ------------------------------------------------------------------------------
# Action: Update from GitHub
# ------------------------------------------------------------------------------
action_update_github() {
    echo ""
    echo -e "${BOLD}${CYAN}🔄 Updating Edge Gateway to latest version from GitHub...${NC}"
    echo ""
    git -C "${SCRIPT_DIR}" stash || true
    git -C "${SCRIPT_DIR}" pull origin main
    if [ -f "${PI_CLIENT_DIR}/install_toolbox.sh" ]; then
        sudo bash "${PI_CLIENT_DIR}/install_toolbox.sh" > /dev/null
    fi
    sudo ln -sf "${SCRIPT_DIR}/gateway.sh" /usr/local/bin/gateway
    sudo chmod +x /usr/local/bin/gateway
    
    if command -v systemctl &> /dev/null && systemctl is-active --quiet plc-gateway 2>/dev/null; then
        echo -e "🔄 Restarting plc-gateway service..."
        sudo systemctl restart plc-gateway
    fi
    echo ""
    echo -e "${BOLD}${GREEN}✅ Update completed successfully!${NC}"
    echo ""
}

# ------------------------------------------------------------------------------
# Action: Diagnostics
# ------------------------------------------------------------------------------
action_run_diagnose() {
    echo ""
    python3 "${PI_CLIENT_DIR}/diagnose.py"
    echo ""
}

# ------------------------------------------------------------------------------
# Action: Inspect Package
# ------------------------------------------------------------------------------
action_inspect_package() {
    echo ""
    echo -e "${BOLD}เลือกรูปแบบการตรวจสอบ Batch Package:${NC}"
    echo "  [1] อ่านข้อมูลสดจากตู้ PLC จริง (Live PLC Read)"
    echo "  [2] จำลองข้อมูลจำลองสมจริง (Simulation Dry-Run)"
    echo "  [3] อ่านจาก PLC จริง และส่งขึ้น Railway Cloud API ทันที"
    echo "  [4] ส่งข้อมูลจำลองขึ้น Railway Cloud API ทันที"
    echo ""
    read -p "กรุณาเลือก [1-4]: " p_choice

    case "$p_choice" in
        1)
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --package
            ;;
        2)
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --package --sample
            ;;
        3)
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --package --send
            ;;
        4)
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --package --sample --send
            ;;
        *)
            echo "ยกเลิกคำสั่ง"
            ;;
    esac
}

# ------------------------------------------------------------------------------
# Action: Service Management
# ------------------------------------------------------------------------------
action_service_management() {
    echo ""
    echo -e "${BOLD}การจัดการ 24/7 Background Service:${NC}"
    echo "  [1] ตรวจสอบสถานะ (Status)"
    echo "  [2] สตาร์ตเซอร์วิส (Start)"
    echo "  [3] หยุดเซอร์วิส (Stop)"
    echo "  [4] รีสตาร์ตเซอร์วิส (Restart)"
    echo "  [5] ดู Live Streaming Logs (Ctrl+C เพื่อออก)"
    echo ""
    read -p "กรุณาเลือก [1-5]: " s_choice

    case "$s_choice" in
        1)
            sudo systemctl status plc-gateway
            ;;
        2)
            sudo systemctl start plc-gateway
            echo -e "${GREEN}✓ Started plc-gateway service.${NC}"
            ;;
        3)
            sudo systemctl stop plc-gateway
            echo -e "${YELLOW}✓ Stopped plc-gateway service.${NC}"
            ;;
        4)
            sudo systemctl restart plc-gateway
            echo -e "${GREEN}✓ Restarted plc-gateway service.${NC}"
            ;;
        5)
            echo -e "${CYAN}กำลังเชื่อมต่อ Live Log (กด Ctrl+C เพื่อออก)...${NC}"
            sudo journalctl -u plc-gateway -f
            ;;
        *)
            echo "ยกเลิก"
            ;;
    esac
}

# ------------------------------------------------------------------------------
# Action: Clean Buffer
# ------------------------------------------------------------------------------
action_clean_buffer() {
    local db_path="${PI_CLIENT_DIR}/buffer.db"
    echo ""
    if [ -f "$db_path" ]; then
        local count=$(python3 -c "import sqlite3; c=sqlite3.connect('$db_path'); print(c.execute('SELECT count(*) FROM buffer_records').fetchone()[0])" 2>/dev/null || echo "0")
        echo -e "📦 ฐานข้อมูล SQLite Buffer ปัจจุบันมีข้อมูลค้างอยู่: ${YELLOW}${count} records${NC}"
        echo ""
        read -p "คุณแน่ใจหรือไม่ว่าต้องการล้าง Buffer Database? (y/N): " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -f "$db_path" "${db_path}-wal" "${db_path}-shm"
            echo -e "${GREEN}✓ ล้าง SQLite Buffer เรียบร้อยแล้ว${NC}"
        fi
    else
        echo -e "${GREEN}📦 ไม่มีข้อมูลค้างใน SQLite Buffer (buffer.db ว่างเปล่า)${NC}"
    fi
    echo ""
}

# ------------------------------------------------------------------------------
# Non-Interactive Flags
# ------------------------------------------------------------------------------
if [ "$1" = "--auto" ] || [ "$1" = "-a" ]; then
    action_zero_touch_setup
    exit 0
elif [ "$1" = "--update" ] || [ "$1" = "-u" ]; then
    action_update_github
    exit 0
elif [ "$1" = "--diagnose" ] || [ "$1" = "-d" ]; then
    action_run_diagnose
    exit 0
elif [ "$1" = "--status" ] || [ "$1" = "-s" ]; then
    echo -e "Profile:  $(detect_profile_name)"
    echo -e "Service:  $(get_service_status)"
    echo -e "PLC IP:   $(get_target_plc_ip)"
    exit 0
elif [ "$1" = "--package" ] || [ "$1" = "-p" ]; then
    python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --package "${@:2}"
    exit 0
elif [ "$1" = "--discover" ]; then
    python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --discover "${@:2}"
    exit 0
fi

# ------------------------------------------------------------------------------
# Interactive Menu Loop
# ------------------------------------------------------------------------------
show_menu() {
    clear
    local profile="$(detect_profile_name)"
    local s_status="$(get_service_status)"
    local plc_ip="$(get_target_plc_ip)"
    local serial="$(get_rpi_serial)"

    echo -e "${BOLD}${CYAN}================================================================================${NC}"
    echo -e "${BOLD}🍓 SIEMENS S7-1200 IOT EDGE GATEWAY — CONTROL & INSTALLATION HUB${NC}"
    echo -e "   Hardware Profile: ${GREEN}${profile}${NC} | SN: ${YELLOW}${serial}${NC}"
    echo -e "   Target PLC IP:    ${CYAN}${plc_ip}${NC} | Service: ${s_status}"
    echo -e "   Cloud Target:     ${BLUE}https://epc-edge-api-dev.up.railway.app/api${NC}"
    echo -e "${BOLD}${CYAN}================================================================================${NC}"
    echo ""
    echo -e "  ${BOLD}[ 1 ] 🚀 1-Click Zero-Touch Auto Install & Start${NC}"
    echo -e "         • ตรวจจับ Profile, สแกนหา PLC, ลง Watchdog & Service 24/7 และเริ่มทำงานทันที"
    echo ""
    echo -e "  ${BOLD}[ 2 ] 🔍 Auto-Scan & Discover PLC${NC}"
    echo -e "         • สแกนหาตู้ Siemens S7-1200 ทั่ววง LAN (Port 102) ใน 0.02 วินาที"
    echo ""
    echo -e "  ${BOLD}[ 3 ] ⚙️  Device & Network Configuration${NC}"
    echo -e "         • แก้ไข Device Name, UUID, API Key, PLC IP หรือเปิด Web Configurator (:8080)"
    echo ""
    echo -e "  ${BOLD}[ 4 ] 📦 Inspect Raw Data & Web Batch Package${NC}"
    echo -e "         • ดูตารางแปลงค่า Hex 19 เซนเซอร์ และทดสอบยิงข้อมูลขึ้น Cloud API สดๆ"
    echo ""
    echo -e "  ${BOLD}[ 5 ] 🩺 Run 7-Point Self-Diagnosis${NC}"
    echo -e "         • ตรวจเช็คสุขภาพ ฮาร์ดแวร์, เน็ตเวิร์ก, PLC, Cloud, PNR และ Buffer"
    echo ""
    echo -e "  ${BOLD}[ 6 ] 📊 Service Management & Live Logs${NC}"
    echo -e "         • Start, Stop, Restart หรือดู Live Journal Streaming Logs"
    echo ""
    echo -e "  ${BOLD}[ 7 ] 🔄 1-Click Update from GitHub${NC}"
    echo -e "         • ดึงโค้ดเวอร์ชันล่าสุดจาก GitHub และอัปเดตระบบอัตโนมัติ"
    echo ""
    echo -e "  ${BOLD}[ 8 ] 🧹 Maintenance & Clean Buffer${NC}"
    echo -e "         • ตรวจสอบและล้างคิวข้อมูล SQLite Offline Buffer"
    echo ""
    echo -e "  ${BOLD}[ 0 ] 🚪 Exit (ออกจากเมนู)${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}================================================================================${NC}"
}

while true; do
    show_menu
    read -p "กรุณาเลือกเมนู [0-8]: " choice

    case "$choice" in
        1)
            action_zero_touch_setup
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        2)
            echo ""
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --discover
            echo ""
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        3)
            echo ""
            python3 "${PI_CLIENT_DIR}/config_tool.py"
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        4)
            action_inspect_package
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        5)
            action_run_diagnose
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        6)
            action_service_management
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        7)
            action_update_github
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        8)
            action_clean_buffer
            read -p "กด Enter เพื่อกลับสู่เมนูหลัก..."
            ;;
        0)
            echo ""
            echo "สวัสดีครับ! ขอบคุณที่ใช้งาน Edge Gateway Hub"
            exit 0
            ;;
        *)
            echo -e "${RED}ตัวเลือกไม่ถูกต้อง กรุณาเลือก 0-8${NC}"
            sleep 1
            ;;
    esac
done
