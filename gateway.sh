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
        echo "GSE-PROTO-1 (Master Active)"
    elif [ "$serial" = "100000001b657629" ] || [ "$mac" = "98:fe:54:63:35:a5" ]; then
        echo "GSE-PROTO-2 (Backup Standby)"
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
    echo -e "${BOLD}[1/7] 🎯 Detecting Hardware Profile & CPU Serial...${NC}"
    local detected="$(detect_profile_name)"
    echo -e "      👉 Detected Board: ${GREEN}${detected}${NC}"
    
    if [ "$detected" = "GSE-PROTO-1 (Master Active)" ]; then
        if [ -f "${PI_CLIENT_DIR}/config_proto1.json" ]; then
            cp "${PI_CLIENT_DIR}/config_proto1.json" "${CONFIG_FILE}"
            echo -e "      [✓] Bound Configuration Preset: ${GREEN}GSE-PROTO-1${NC}"
        fi
    elif [ "$detected" = "GSE-PROTO-2 (Backup Standby)" ]; then
        if [ -f "${PI_CLIENT_DIR}/config_proto2.json" ]; then
            cp "${PI_CLIENT_DIR}/config_proto2.json" "${CONFIG_FILE}"
            echo -e "      [✓] Bound Configuration Preset: ${GREEN}GSE-PROTO-2${NC}"
        fi
    fi

    # Step 2: System Packages
    echo ""
    echo -e "${BOLD}[2/7] 📦 Checking & Installing Required OS Packages...${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -y
        sudo apt-get install -y python3 python3-pip python3-psutil sqlite3 libsnap7-dev git watchdog curl
        echo -e "      [✓] System dependencies installed successfully."
    else
        echo -e "      ${YELLOW}[i] Skipping apt-get (apt manager not found)${NC}"
    fi

    # Step 3: Python Libraries
    echo ""
    echo -e "${BOLD}[3/7] 🐍 Installing Python Packages (python-snap7, requests)...${NC}"
    pip3 install python-snap7 requests --break-system-packages 2>/dev/null || pip3 install python-snap7 requests 2>/dev/null || true
    echo -e "      [✓] Python packages verified and ready."

    # Step 4: Hardware Watchdog
    echo ""
    echo -e "${BOLD}[4/7] 🛡️  Enabling Hardware Watchdog (BCM2711)...${NC}"
    if [ -f "/etc/modules" ]; then
        if ! grep -q "bcm2835_wdt" /etc/modules; then
            echo "bcm2835_wdt" | sudo tee -a /etc/modules > /dev/null
        fi
        echo -e "      [✓] Hardware Watchdog module registered in /etc/modules."
    fi

    # Step 5: Global CLI Toolbox
    echo ""
    echo -e "${BOLD}[5/7] 🧰 Installing Global CLI Toolbox to /usr/local/bin...${NC}"
    if [ -f "${PI_CLIENT_DIR}/install_toolbox.sh" ]; then
        sudo bash "${PI_CLIENT_DIR}/install_toolbox.sh" > /dev/null
        # Link gateway command directly
        sudo ln -sf "${SCRIPT_DIR}/gateway.sh" /usr/local/bin/gateway
        sudo chmod +x /usr/local/bin/gateway
        echo -e "      [✓] System-wide commands (gateway, plc-toolbox, plc-info, etc.) installed."
    fi

    # Step 6: Scan for PLC
    echo ""
    echo -e "${BOLD}[6/7] 🔍 Scanning Local Subnet for Siemens S7-1200 PLC (Port 102)...${NC}"
    python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --discover || true

    # Step 7: Systemd Service Registration & Start
    echo ""
    echo -e "${BOLD}[7/7] ⚙️  Registering & Starting Systemd 24/7 Background Service...${NC}"
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
        echo -e "      [✓] Service 'plc-gateway' enabled and started 24/7."
    fi

    echo ""
    echo -e "${BOLD}${GREEN}========================================================================${NC}"
    echo -e "${BOLD}${GREEN}🎉 Zero-Touch Setup Complete! Edge Gateway is running in the background.${NC}"
    echo -e "   • Check Service Status: ${YELLOW}plc-status${NC}  or  ${YELLOW}gateway --status${NC}"
    echo -e "   • View Live Logs:       ${YELLOW}plc-logs${NC}"
    echo -e "   • Open Control Hub:     ${YELLOW}gateway${NC}"
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
    echo -e "${BOLD}Select Batch Package Inspection Mode:${NC}"
    echo "  [1] Live PLC Acquisition & Decoding"
    echo "  [2] Simulated Data Dry-Run Inspection"
    echo "  [3] Live PLC Read & Immediate Cloud API Transmission"
    echo "  [4] Simulated Dry-Run & Cloud API Transmission Test"
    echo ""
    read -p "Please select [1-4]: " p_choice

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
            echo "Operation cancelled."
            ;;
    esac
}

# ------------------------------------------------------------------------------
# Action: Service Management
# ------------------------------------------------------------------------------
action_service_management() {
    echo ""
    echo -e "${BOLD}Systemd 24/7 Background Service Management:${NC}"
    echo "  [1] Check Service Status"
    echo "  [2] Start Service"
    echo "  [3] Stop Service"
    echo "  [4] Restart Service"
    echo "  [5] Stream Live Journal Logs (Ctrl+C to exit)"
    echo ""
    read -p "Please select [1-5]: " s_choice

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
            echo -e "${CYAN}Streaming live journal logs (Press Ctrl+C to exit)...${NC}"
            sudo journalctl -u plc-gateway -f
            ;;
        *)
            echo "Cancelled."
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
        local count=$(python3 -c "import sqlite3; c=sqlite3.connect('$db_path'); print(c.execute('SELECT count(*) FROM telemetry_queue').fetchone()[0])" 2>/dev/null || echo "0")
        echo -e "📦 Current SQLite Offline Buffer queue depth: ${YELLOW}${count} records${NC}"
        echo ""
        read -p "Are you sure you want to purge the SQLite Buffer Database? (y/N): " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -f "$db_path" "${db_path}-wal" "${db_path}-shm"
            echo -e "${GREEN}✓ SQLite Buffer purged cleanly.${NC}"
        fi
    else
        echo -e "${GREEN}📦 SQLite Buffer is empty (no buffer.db file created yet).${NC}"
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
    echo -e "         • Auto-detect Profile, scan PLC, setup Watchdog & Systemd 24/7 service"
    echo ""
    echo -e "  ${BOLD}[ 2 ] 🔍 Auto-Scan & Discover PLC${NC}"
    echo -e "         • Discover Siemens S7-1200 on local subnet (Port 102) in 0.02s"
    echo ""
    echo -e "  ${BOLD}[ 3 ] ⚙️  Device & Network Configuration${NC}"
    echo -e "         • Modify Device Name, UUID, API Key, PLC IP, or launch Web Portal (:8080)"
    echo ""
    echo -e "  ${BOLD}[ 4 ] 📦 Inspect Raw Data & Web Batch Package${NC}"
    echo -e "         • View 19-sensor Hex-to-Engineering table & test Cloud API transmission"
    echo ""
    echo -e "  ${BOLD}[ 5 ] 🩺 Run 7-Point Self-Diagnosis${NC}"
    echo -e "         • Automated health check across Hardware, Network, PLC, Cloud & Buffer"
    echo ""
    echo -e "  ${BOLD}[ 6 ] 📊 Service Management & Live Logs${NC}"
    echo -e "         • Start, Stop, Restart or stream real-time journal logs"
    echo ""
    echo -e "  ${BOLD}[ 7 ] 🔄 1-Click Update from GitHub${NC}"
    echo -e "         • Pull latest repository commits and update system scripts"
    echo ""
    echo -e "  ${BOLD}[ 8 ] 🧹 Maintenance & Clean Buffer${NC}"
    echo -e "         • Inspect and manage offline SQLite store-and-forward queue"
    echo ""
    echo -e "  ${BOLD}[ 0 ] 🚪 Exit Console${NC}"
    echo ""
    echo -e "${BOLD}${CYAN}================================================================================${NC}"
}

while true; do
    show_menu
    read -p "Please select an option [0-8]: " choice

    case "$choice" in
        1)
            action_zero_touch_setup
            read -p "Press Enter to return to main menu..."
            ;;
        2)
            echo ""
            python3 "${PI_CLIENT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --discover
            echo ""
            read -p "Press Enter to return to main menu..."
            ;;
        3)
            echo ""
            python3 "${PI_CLIENT_DIR}/config_tool.py"
            read -p "Press Enter to return to main menu..."
            ;;
        4)
            action_inspect_package
            read -p "Press Enter to return to main menu..."
            ;;
        5)
            action_run_diagnose
            read -p "Press Enter to return to main menu..."
            ;;
        6)
            action_service_management
            read -p "Press Enter to return to main menu..."
            ;;
        7)
            action_update_github
            read -p "Press Enter to return to main menu..."
            ;;
        8)
            action_clean_buffer
            read -p "Press Enter to return to main menu..."
            ;;
        0)
            echo ""
            echo "Exiting Edge Gateway Hub. Goodbye!"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please choose [0-8].${NC}"
            sleep 1
            ;;
    esac
done
