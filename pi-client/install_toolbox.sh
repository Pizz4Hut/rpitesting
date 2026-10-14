#!/usr/bin/env bash
# ==============================================================================
# IoT Edge Gateway CLI Toolbox Installer
# Installs handy global commands into /usr/local/bin
# Enables instant access from anywhere: plc-info, plc-diagnose, plc-logs, etc.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config_plc.json"
BUFFER_DB="${SCRIPT_DIR}/buffer.db"

echo "======================================================================"
echo "🧰 Installing Raspberry Pi IoT Edge Gateway CLI Toolbox"
echo "   Target Directory: ${SCRIPT_DIR}"
echo "======================================================================"

# 1. plc-info: Display Hardware Profile, MAC Addresses, Serial Number & Tailscale
sudo tee /usr/local/bin/plc-info > /dev/null <<EOF
#!/usr/bin/env bash
python3 "${SCRIPT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --info "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-info
echo "  [✓] /usr/local/bin/plc-info       -> Display MAC, Serial, IPs & VPN Profile"

# 2. plc-diagnose: Run 7-Point Automated Health & Network Diagnosis
sudo tee /usr/local/bin/plc-diagnose > /dev/null <<EOF
#!/usr/bin/env bash
python3 "${SCRIPT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --diagnose "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-diagnose
echo "  [✓] /usr/local/bin/plc-diagnose   -> 7-Point Self-Diagnostic Health Tool"

# 3. plc-test: Test single data acquisition & cloud transmission cycle
sudo tee /usr/local/bin/plc-test > /dev/null <<EOF
#!/usr/bin/env bash
python3 "${SCRIPT_DIR}/plc_gateway.py" --config "${CONFIG_FILE}" --once "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-test
echo "  [✓] /usr/local/bin/plc-test       -> Run 1 Data Acquisition & Transmit Cycle"

# 4. plc-status: Show live systemd service status
sudo tee /usr/local/bin/plc-status > /dev/null <<EOF
#!/usr/bin/env bash
sudo systemctl status plc-gateway "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-status
echo "  [✓] /usr/local/bin/plc-status     -> Show 24/7 Gateway Service Status"

# 5. plc-logs: Live stream journal logs
sudo tee /usr/local/bin/plc-logs > /dev/null <<EOF
#!/usr/bin/env bash
sudo journalctl -u plc-gateway -f "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-logs
echo "  [✓] /usr/local/bin/plc-logs       -> Stream Live Systemd Journal Logs"

# 6. plc-restart: Restart gateway service gracefully
sudo tee /usr/local/bin/plc-restart > /dev/null <<EOF
#!/usr/bin/env bash
echo "Restarting plc-gateway service..."
sudo systemctl restart plc-gateway
sleep 1
sudo systemctl status plc-gateway --no-pager
EOF
sudo chmod +x /usr/local/bin/plc-restart
echo "  [✓] /usr/local/bin/plc-restart    -> Restart Service Gracefully"

# 7. plc-start: Start gateway service
sudo tee /usr/local/bin/plc-start > /dev/null <<EOF
#!/usr/bin/env bash
echo "Starting plc-gateway service..."
sudo systemctl start plc-gateway
sleep 1
sudo systemctl status plc-gateway --no-pager
EOF
sudo chmod +x /usr/local/bin/plc-start
echo "  [✓] /usr/local/bin/plc-start      -> Start Gateway Service"

# 8. plc-stop: Stop gateway service
sudo tee /usr/local/bin/plc-stop > /dev/null <<EOF
#!/usr/bin/env bash
echo "Stopping plc-gateway service..."
sudo systemctl stop plc-gateway
echo "Stopped plc-gateway."
EOF
sudo chmod +x /usr/local/bin/plc-stop
echo "  [✓] /usr/local/bin/plc-stop       -> Stop Gateway Service"

# 9. plc-buffer: Inspect SQLite Store-and-Forward offline buffer
sudo tee /usr/local/bin/plc-buffer > /dev/null <<EOF
#!/usr/bin/env bash
python3 -c "
import sqlite3, os
db = '${BUFFER_DB}'
if not os.path.exists(db):
    print('📦 Buffer Database: Empty (no buffer.db file created yet).')
else:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(\"SELECT COUNT(*) FROM telemetry_queue WHERE status = 'pending';\")
    pending = cur.fetchone()[0]
    cur.execute(\"SELECT COUNT(*) FROM telemetry_queue;\")
    total = cur.fetchone()[0]
    print('======================================================================')
    print('📦 SQLite Store-and-Forward Offline Buffer Status')
    print('======================================================================')
    print(f'Database Path:     {db}')
    print(f'Pending Queue:     {pending} records awaiting transmission')
    print(f'Total Buffered:    {total} lifetime records')
    cur.execute(\"SELECT id, pnr_code, status, datetime(created_at, 'unixepoch', 'localtime') FROM telemetry_queue ORDER BY id DESC LIMIT 5;\")
    rows = cur.fetchall()
    if rows:
        print('-' * 70)
        print('Recent 5 Records:')
        for r in rows:
            print(f'  • ID: {r[0]:<5} | PNR: {r[1]} | Status: {r[2]:<8} | Time: {r[3]}')
    print('======================================================================')
"
EOF
sudo chmod +x /usr/local/bin/plc-buffer
echo "  [✓] /usr/local/bin/plc-buffer     -> Inspect SQLite Offline Buffer Queue"

# 10. plc-burnin: Run stability burn-in test
sudo tee /usr/local/bin/plc-burnin > /dev/null <<EOF
#!/usr/bin/env bash
python3 "${SCRIPT_DIR}/plc_simulator.py" --config "${CONFIG_FILE}" "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-burnin
echo "  [✓] /usr/local/bin/plc-burnin     -> Run Stability Burn-in Test Harness"

# 11. plc-sim: Start Siemens S7-1200 hardware server simulator on port 102
sudo tee /usr/local/bin/plc-sim > /dev/null <<EOF
#!/usr/bin/env bash
sudo python3 "${SCRIPT_DIR}/s7_server_simulator.py" "\$@"
EOF
sudo chmod +x /usr/local/bin/plc-sim
echo "  [✓] /usr/local/bin/plc-sim        -> Launch S7-1200 Simulator Server (Port 102)"

# 12. plc-runtime: Fetch and display live Cloud Runtime status from Railway
sudo tee /usr/local/bin/plc-runtime > /dev/null <<EOF
#!/usr/bin/env bash
python3 -c "
import json, urllib.request, os
cfg_path = '${CONFIG_FILE}'
if not os.path.exists(cfg_path):
    print('Configuration file not found.')
    exit(1)
with open(cfg_path) as f:
    cfg = json.load(f)
dev_id = cfg.get('deviceId')
base_url = cfg.get('api', {}).get('baseUrl', 'https://epc-edge-api-dev.up.railway.app/api').rstrip('/')
api_key = cfg.get('api', {}).get('apiKey', '')
url = f'{base_url}/edge/devices/{dev_id}'
req = urllib.request.Request(url, headers={'x-api-key': api_key, 'User-Agent': 'CLI-Toolbox'})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        print('======================================================================')
        print('☁️  Live Cloud Edge Runtime & Device Status (Railway API)')
        print('======================================================================')
        print(f'Device Name:      {data.get(\"name\")}')
        print(f'Device ID:        {data.get(\"id\")}')
        print(f'Serial Number:    {data.get(\"serial_number\")}')
        print(f'MAC Address:      {data.get(\"mac_address\")}')
        print(f'Model:            {data.get(\"model\")}')
        print(f'Cloud Status:     {data.get(\"status\")}')
        print(f'Last Seen At:     {data.get(\"last_seen_at\")}')
        asset = data.get('asset', {})
        if asset:
            print(f'Assigned Asset:   {asset.get(\"name\")} (ID: {asset.get(\"id\")})')
        print('======================================================================')
except Exception as e:
    print(f'Failed to fetch Cloud Runtime: {e}')
"
EOF
sudo chmod +x /usr/local/bin/plc-runtime
echo "  [✓] /usr/local/bin/plc-runtime    -> Check Live Cloud Runtime Status"

# 13. plc-toolbox: Summary of all commands
sudo tee /usr/local/bin/plc-toolbox > /dev/null <<EOF
#!/usr/bin/env bash
echo "======================================================================"
echo "🍓 Raspberry Pi IoT Edge Gateway — CLI Toolbox Menu"
echo "======================================================================"
echo "  plc-info       : Show Device ID, Serial Number, MAC addresses & VPN IP"
echo "  plc-diagnose   : Run 7-Point automated self-diagnostic health check"
echo "  plc-test       : Run 1 data acquisition & cloud transmission cycle"
echo "  plc-status     : Check systemd 24/7 background service status"
echo "  plc-logs       : Live stream gateway journal logs (Ctrl+C to exit)"
echo "  plc-restart    : Restart gateway service gracefully"
echo "  plc-start      : Start gateway service"
echo "  plc-stop       : Stop gateway service"
echo "  plc-runtime    : Check live Cloud Runtime status and last seen at"
echo "  plc-buffer     : Check SQLite Store-and-Forward offline buffer count"
echo "  plc-burnin     : Run 24h stability burn-in simulation"
echo "  plc-sim        : Start Siemens S7-1200 PLC server simulator (Port 102)"
echo "  plc-toolbox    : Display this command summary"
echo "======================================================================"
EOF
sudo chmod +x /usr/local/bin/plc-toolbox
echo "  [✓] /usr/local/bin/plc-toolbox    -> Display CLI Toolbox Cheat Sheet"

echo "======================================================================"
echo "🎉 CLI Toolbox installed successfully!"
echo "   Run 'plc-toolbox' from anywhere to see all available commands."
echo "======================================================================"
