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
if [ -f "plc-gateway.service" ]; then
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)
    
    # Adapt service path to current directory and user
    sed -i "s|/home/pi/rpitesting/pi-client|$CURRENT_DIR|g" plc-gateway.service
    sed -i "s|User=pi|User=$CURRENT_USER|g" plc-gateway.service

    sudo cp plc-gateway.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable plc-gateway.service
    echo "✅ Systemd service 'plc-gateway' installed and enabled!"
    echo "To start now: sudo systemctl start plc-gateway"
    echo "To view logs: sudo journalctl -u plc-gateway -f"
fi

echo "======================================================================"
echo "🎉 Setup complete! You can now start or test the gateway:"
echo "   Test with Mock PLC:      python3 plc_gateway.py --mock --interval 10"
echo "   Run Burn-in Simulation:  python3 plc_simulator.py --hours 24"
echo "   Start 24/7 Service:      sudo systemctl start plc-gateway"
echo "======================================================================"
