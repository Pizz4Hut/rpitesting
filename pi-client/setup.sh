#!/usr/bin/env bash
# Raspberry Pi Telemetry Agent Installer
set -e

echo "🍓 Installing Raspberry Pi Telemetry Agent..."

# Install required Python packages if needed
if command -v apt-get &> /dev/null; then
  echo "📦 Updating package lists & installing python3-pip..."
  sudo apt-get update -y
  sudo apt-get install -y python3-pip python3-psutil
fi

# Make script executable
chmod +x pi_agent.py

echo ""
echo "✅ Installation complete!"
echo "👉 To configure and start:"
echo "   plc-config"
echo "   sudo systemctl start plc-gateway"
echo ""
echo "👉 Or test the connection:"
echo "   plc-test"
echo "   plc-runtime"
