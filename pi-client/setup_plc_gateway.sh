#!/usr/bin/env bash
# ==============================================================================
# Raspberry Pi 4 - Siemens S7-1200 Edge Gateway Automated Setup Script
# Installs python dependencies, python-snap7, dual ethernet config, and systemd service
# ==============================================================================

set -e

echo "======================================================================"
echo "🍓 Setting up Raspberry Pi 4 Edge Gateway for Siemens S7-1200 PLC"
echo "======================================================================"

# 1. Update OS packages
echo "📦 [1/5] Updating system packages and installing prerequisites..."
sudo apt update
sudo apt install -y python3 python3-pip python3-psutil sqlite3 libsnap7-dev git watchdog

# 2. Install Python Dependencies
echo "🐍 [2/5] Installing Python libraries (python-snap7, requests)..."
pip3 install python-snap7 requests --break-system-packages || pip3 install python-snap7 requests

# 3. Configure Hardware Watchdog for RPi 4
echo "🛡️  [3/5] Configuring Hardware Watchdog (BCM2711)..."
if ! grep -q "bcm2835_wdt" /etc/modules; then
    echo "bcm2835_wdt" | sudo tee -a /etc/modules
fi

# 4. Permissions & Environment
echo "🔧 [4/5] Setting up permissions..."
chmod +x plc_gateway.py
chmod +x plc_simulator.py

# 5. Install Systemd Service
echo "⚙️  [5/5] Registering systemd background service..."
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

sudo tee /etc/systemd/system/plc-gateway.service > /dev/null <<EOF
[Unit]
Description=Siemens S7-1200 IoT Edge Gateway Service
After=network-online.target time-sync.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=/usr/bin/python3 ${CURRENT_DIR}/plc_gateway.py --config ${CURRENT_DIR}/config_plc.json
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
echo "✅ Systemd service 'plc-gateway' installed, enabled, and started!"
echo "To view live logs: sudo journalctl -u plc-gateway -f"


echo "======================================================================"
echo "🎉 Setup complete! You can now start or test the gateway:"
echo "   Test with Mock PLC:      python3 plc_gateway.py --mock --interval 10"
echo "   Run Burn-in Simulation:  python3 plc_simulator.py --hours 24"
echo "   Start 24/7 Service:      sudo systemctl start plc-gateway"
echo "======================================================================"
