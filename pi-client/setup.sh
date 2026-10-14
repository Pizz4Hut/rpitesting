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
echo "👉 To start immediately:"
echo "   python3 pi_agent.py --url https://YOUR-SITE.netlify.app/api/telemetry"
echo ""
echo "👉 To configure auto-start on boot with systemd:"
echo "   sudo cp pi-agent.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable --now pi-agent"
