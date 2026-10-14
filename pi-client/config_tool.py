#!/usr/bin/env python3
"""
Industrial IoT Edge Gateway - Configuration & HTTPS Cloud Validation Tool
Supports interactive CLI wizard, command-line arguments, and a lightweight Web UI portal.
Allows engineers to configure Device Name, Device UUID, API Key, HTTPS URL, PLC IP,
and define/manage all 19+ Siemens S7-1200 Sensor Tags and Memory Mappings.
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error
import ssl
import argparse
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config_plc.json")

# ANSI Colors
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_GREEN = "\033[1;32m"
CLR_RED = "\033[1;31m"
CLR_YELLOW = "\033[1;33m"
CLR_CYAN = "\033[1;36m"
CLR_GRAY = "\033[0;90m"


def load_config(file_path=CONFIG_FILE):
    if not os.path.exists(file_path):
        print(f"{CLR_RED}Error: Configuration file not found at {file_path}{CLR_RESET}")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"{CLR_RED}Error parsing {file_path}: {e}{CLR_RESET}")
        return None


def save_config(cfg, file_path=CONFIG_FILE, create_backup=True):
    try:
        if create_backup and os.path.exists(file_path):
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return True, "Configuration saved successfully."
    except Exception as e:
        return False, f"Failed to save configuration: {e}"


def mask_key(key):
    if not key or len(key) < 12:
        return key or "(not set)"
    return f"{key[:8]}...{key[-6:]}"


def test_https_connection(base_url, device_id, api_key, timeout_sec=10):
    """Test live HTTPS Cloud API endpoint and validate TLS/authentication."""
    base_url = (base_url or "").rstrip("/")
    if not base_url:
        return False, 0, "Base URL is empty."
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        return False, 0, "Base URL must start with http:// or https://"

    target_url = f"{base_url}/edge/devices/{device_id}"
    headers = {
        "x-api-key": api_key,
        "User-Agent": "IoT-Gateway-ConfigTool/1.0",
        "Accept": "application/json"
    }

    req = urllib.request.Request(target_url, headers=headers, method="GET")
    start_time = time.time()
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            return True, elapsed_ms, data
    except urllib.error.HTTPError as he:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        try:
            body = he.read().decode("utf-8")
        except Exception:
            body = ""
        msg = f"HTTP {he.code} {he.reason}"
        if he.code == 401:
            msg += " - API Key is invalid or unauthorized!"
        elif he.code == 404:
            msg += " - Device ID not registered on Cloud!"
        elif body:
            msg += f" ({body[:100]})"
        return False, elapsed_ms, msg
    except urllib.error.URLError as ue:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        return False, elapsed_ms, f"Network/DNS error: {ue.reason}"
    except Exception as ex:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        return False, elapsed_ms, str(ex)


def display_config(cfg):
    dev_id = cfg.get("deviceId", "(none)")
    dev_name = cfg.get("deviceName", "(none)")
    api = cfg.get("api", {})
    base_url = api.get("baseUrl", "(none)")
    api_key = api.get("apiKey", "")
    hb_sec = api.get("heartbeatIntervalSec", 30)
    tx_sec = api.get("transmissionIntervalSec", 60)
    plc = cfg.get("plc", {})
    plc_ip = plc.get("ip", "(none)")
    plc_port = plc.get("port", 102)
    tag_count = len(cfg.get("tags", []))

    print(f"\n{CLR_CYAN}{CLR_BOLD}{'='*75}{CLR_RESET}")
    print(f"{CLR_BOLD}⚙️  IoT Edge Gateway — Active Configuration ({CONFIG_FILE}){CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}{'='*75}{CLR_RESET}")
    print(f"  {CLR_BOLD}Device Name:{CLR_RESET}      {CLR_GREEN}{dev_name}{CLR_RESET}")
    print(f"  {CLR_BOLD}Device UUID:{CLR_RESET}      {dev_id}")
    print(f"  {CLR_BOLD}Cloud API URL:{CLR_RESET}    {base_url}")
    print(f"  {CLR_BOLD}API Key:{CLR_RESET}          {mask_key(api_key)}")
    print(f"  {CLR_BOLD}Heartbeat Rate:{CLR_RESET}   Every {hb_sec} seconds")
    print(f"  {CLR_BOLD}Batch Rate:{CLR_RESET}       Every {tx_sec} seconds")
    print(f"  {CLR_BOLD}Target PLC:{CLR_RESET}       {plc_ip}:{plc_port} (Physical S7comm)")
    print(f"  {CLR_BOLD}Defined Sensors:{CLR_RESET}   {CLR_GREEN}{tag_count} Sensors configured{CLR_RESET}")
    print(f"{CLR_CYAN}{'='*75}{CLR_RESET}\n")


def display_sensors(cfg):
    tags = cfg.get("tags", [])
    print(f"\n{CLR_CYAN}{CLR_BOLD}{'='*85}{CLR_RESET}")
    print(f"{CLR_BOLD}📊 Defined PLC Sensors & Memory Mappings ({len(tags)} Sensors){CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}{'='*85}{CLR_RESET}")
    print(f"{CLR_BOLD}{'ID':<4} | {'Sensor Name':<24} | {'DB Address':<12} | {'Type':<6} | {'Unit':<8} | {'Description'}{CLR_RESET}")
    print(f"{CLR_GRAY}{'-'*85}{CLR_RESET}")
    for t in tags:
        t_id = str(t.get("id", "-"))
        name = t.get("name", "")
        addr = t.get("address", "")
        dtype = t.get("type", "")
        unit = t.get("unit", "")
        desc = t.get("desc", "")
        print(f"{t_id:<4} | {CLR_GREEN}{name:<24}{CLR_RESET} | {addr:<12} | {dtype:<6} | {unit:<8} | {desc}")
    print(f"{CLR_CYAN}{'='*85}{CLR_RESET}\n")


def restart_gateway_service():
    print(f"{CLR_YELLOW}Restarting plc-gateway systemd service...{CLR_RESET}")
    res = os.system("sudo systemctl restart plc-gateway")
    if res == 0:
        print(f"{CLR_GREEN}✓ Service plc-gateway restarted successfully.{CLR_RESET}")
    else:
        print(f"{CLR_RED}⚠️ Failed to restart plc-gateway service (exit code {res}).{CLR_RESET}")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# --- Web UI Configurator (Pure Python Standard Library) ---
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IoT Edge Gateway Configurator</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }
    .container { max-width: 960px; margin: 0 auto; }
    .header {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header h1 { font-size: 1.5rem; font-weight: 700; color: #60a5fa; }
    .header p { color: var(--muted); font-size: 0.9rem; }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      background: #1e3a8a;
      color: #93c5fd;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }
    .card-title {
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn {
      padding: 8px 16px;
      border-radius: 8px;
      border: none;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      font-size: 0.85rem;
    }
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-success { background: var(--success); color: white; }
    .btn-success:hover { background: #059669; }
    .btn-warning { background: var(--warning); color: #000; }
    .btn-warning:hover { background: #d97706; }
    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { background: #dc2626; }
    .form-group { margin-bottom: 18px; }
    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    input[type="text"], input[type="number"], select {
      width: 100%;
      padding: 10px 14px;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: white;
      font-size: 0.95rem;
      font-family: monospace;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: var(--primary); }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }
    .actions {
      display: flex;
      gap: 12px;
      margin-top: 24px;
      flex-wrap: wrap;
    }
    .result-box {
      margin-top: 20px;
      padding: 16px;
      border-radius: 8px;
      font-family: monospace;
      font-size: 0.85rem;
      display: none;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .result-box.success {
      display: block;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--success);
      color: #34d399;
    }
    .result-box.error {
      display: block;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--danger);
      color: #f87171;
    }
    .result-box.info {
      display: block;
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid var(--primary);
      color: #93c5fd;
    }
    table.sensor-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      font-size: 0.85rem;
    }
    table.sensor-table th {
      background: #0f172a;
      color: var(--muted);
      text-align: left;
      padding: 10px;
      border-bottom: 1px solid var(--border);
    }
    table.sensor-table td {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
    }
    table.sensor-table input, table.sensor-table select {
      padding: 6px 8px;
      font-size: 0.85rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>🍓 IoT Edge Gateway Web Configurator</h1>
        <p>Siemens S7-1200 Physical PLC & Railway Cloud API Interface</p>
      </div>
      <div>
        <span class="badge" id="serviceBadge">Ready</span>
      </div>
    </div>

    <!-- Device & Cloud Credentials -->
    <div class="card">
      <div class="card-title">🏷️ Device Identification & Cloud Connection</div>
      <div class="grid-2">
        <div class="form-group">
          <label>Device Name (ชื่ออุปกรณ์)</label>
          <input type="text" id="deviceName" placeholder="e.g. GSE-PROTO-1">
        </div>
        <div class="form-group">
          <label>Device UUID (Cloud Identifier)</label>
          <input type="text" id="deviceId" placeholder="4045f327-2776-4f34-977e-64e307db648f">
        </div>
      </div>

      <div class="form-group">
        <label>Cloud API Base URL (HTTPS)</label>
        <input type="text" id="baseUrl" placeholder="https://epc-edge-api-dev.up.railway.app/api">
      </div>

      <div class="form-group">
        <label>Cloud API Key (x-api-key)</label>
        <input type="text" id="apiKey" placeholder="gs_17ed8df023f46e38...">
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label>Heartbeat Interval (Seconds)</label>
          <input type="number" id="heartbeatIntervalSec" value="30">
        </div>
        <div class="form-group">
          <label>Telemetry Batch Interval (Seconds)</label>
          <input type="number" id="transmissionIntervalSec" value="60">
        </div>
      </div>

      <div class="card-title" style="margin-top: 16px;">🏭 Physical Siemens S7-1200 PLC Connection</div>
      <div class="grid-2">
        <div class="form-group">
          <label>Siemens PLC IP Address</label>
          <input type="text" id="plcIp" value="192.168.2.2">
        </div>
        <div class="form-group">
          <label>S7comm TCP Port</label>
          <input type="number" id="plcPort" value="102">
        </div>
      </div>

      <div class="actions">
        <button class="btn btn-primary" onclick="testHttps()">🔍 Test Live HTTPS Connection</button>
        <button class="btn btn-success" onclick="saveConfiguration()">💾 Save Configuration</button>
        <button class="btn btn-warning" onclick="saveAndRestart()">🚀 Save & Restart Gateway</button>
      </div>

      <div id="resultBox" class="result-box"></div>
    </div>

    <!-- Sensor Definitions & Memory Map -->
    <div class="card">
      <div class="card-title" style="justify-content: space-between;">
        <span>📊 Sensor Definitions & Memory Map (<span id="sensorCount">0</span> Defined)</span>
        <button class="btn btn-primary" onclick="addSensorRow()">+ Add Sensor Tag</button>
      </div>
      <p style="color: var(--muted); font-size: 0.85rem; margin-bottom: 12px;">
        Define which physical sensor each PLC Data Block address maps to, its engineering unit, and description.
      </p>

      <div style="overflow-x: auto;">
        <table class="sensor-table">
          <thead>
            <tr>
              <th style="width: 50px;">ID</th>
              <th style="width: 180px;">Sensor Name</th>
              <th style="width: 110px;">DB Address</th>
              <th style="width: 90px;">Type</th>
              <th style="width: 80px;">Unit</th>
              <th>Description / Label</th>
              <th style="width: 60px;"></th>
            </tr>
          </thead>
          <tbody id="sensorRows"></tbody>
        </table>
      </div>

      <div class="actions">
        <button class="btn btn-success" onclick="saveConfiguration()">💾 Save Sensor Definitions</button>
        <button class="btn btn-warning" onclick="saveAndRestart()">🚀 Save & Restart Gateway</button>
      </div>
    </div>
  </div>

  <script>
    let globalTags = [];

    function showResult(text, type) {
      const box = document.getElementById('resultBox');
      box.textContent = text;
      box.className = 'result-box ' + type;
    }

    function renderSensorRows(tags) {
      const tbody = document.getElementById('sensorRows');
      tbody.innerHTML = '';
      tags.forEach((t, index) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><input type="number" class="t-id" value="${t.id || (index+1)}" style="width: 45px;"></td>
          <td><input type="text" class="t-name" value="${t.name || ''}" placeholder="sensor_name"></td>
          <td><input type="text" class="t-addr" value="${t.address || ''}" placeholder="DB1.DBD0"></td>
          <td>
            <select class="t-type">
              <option value="REAL" ${t.type==='REAL'?'selected':''}>REAL</option>
              <option value="DINT" ${t.type==='DINT'?'selected':''}>DINT</option>
              <option value="INT" ${t.type==='INT'?'selected':''}>INT</option>
              <option value="BOOL" ${t.type==='BOOL'?'selected':''}>BOOL</option>
              <option value="WORD" ${t.type==='WORD'?'selected':''}>WORD</option>
              <option value="DWORD" ${t.type==='DWORD'?'selected':''}>DWORD</option>
              <option value="STRING" ${t.type==='STRING'?'selected':''}>STRING</option>
            </select>
          </td>
          <td><input type="text" class="t-unit" value="${t.unit || ''}" placeholder="°C, A, bar"></td>
          <td><input type="text" class="t-desc" value="${t.desc || ''}" placeholder="Description"></td>
          <td style="text-align: center;">
            <button class="btn btn-danger" style="padding: 4px 8px; font-size: 0.75rem;" onclick="removeSensorRow(${index})">✕</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
      document.getElementById('sensorCount').textContent = tags.length;
    }

    function addSensorRow() {
      const tbody = document.getElementById('sensorRows');
      const rows = collectSensors();
      const nextId = rows.length > 0 ? Math.max(...rows.map(r => r.id || 0)) + 1 : 1;
      rows.push({
        id: nextId,
        name: `sensor_${nextId}`,
        address: `DB1.DBD${(nextId-1)*4}`,
        type: 'REAL',
        unit: '',
        desc: `Sensor #${nextId}`
      });
      renderSensorRows(rows);
    }

    function removeSensorRow(index) {
      const rows = collectSensors();
      rows.splice(index, 1);
      renderSensorRows(rows);
    }

    function collectSensors() {
      const rows = [];
      const trs = document.querySelectorAll('#sensorRows tr');
      trs.forEach(tr => {
        rows.push({
          id: parseInt(tr.querySelector('.t-id').value, 10) || 1,
          name: tr.querySelector('.t-name').value.trim(),
          address: tr.querySelector('.t-addr').value.trim(),
          type: tr.querySelector('.t-type').value,
          unit: tr.querySelector('.t-unit').value.trim(),
          desc: tr.querySelector('.t-desc').value.trim()
        });
      });
      return rows;
    }

    async function loadConfig() {
      try {
        const res = await fetch('/api/config');
        const cfg = await res.json();
        document.getElementById('deviceName').value = cfg.deviceName || '';
        document.getElementById('deviceId').value = cfg.deviceId || '';
        document.getElementById('baseUrl').value = (cfg.api && cfg.api.baseUrl) || '';
        document.getElementById('apiKey').value = (cfg.api && cfg.api.apiKey) || '';
        document.getElementById('heartbeatIntervalSec').value = (cfg.api && cfg.api.heartbeatIntervalSec) || 30;
        document.getElementById('transmissionIntervalSec').value = (cfg.api && cfg.api.transmissionIntervalSec) || 60;
        document.getElementById('plcIp').value = (cfg.plc && cfg.plc.ip) || '192.168.2.2';
        document.getElementById('plcPort').value = (cfg.plc && cfg.plc.port) || 102;
        globalTags = cfg.tags || [];
        renderSensorRows(globalTags);
        document.getElementById('serviceBadge').textContent = 'Config Loaded';
      } catch (err) {
        showResult('Failed to load configuration: ' + err, 'error');
      }
    }

    function collectForm() {
      return {
        deviceName: document.getElementById('deviceName').value.trim(),
        deviceId: document.getElementById('deviceId').value.trim(),
        baseUrl: document.getElementById('baseUrl').value.trim(),
        apiKey: document.getElementById('apiKey').value.trim(),
        heartbeatIntervalSec: parseInt(document.getElementById('heartbeatIntervalSec').value, 10) || 30,
        transmissionIntervalSec: parseInt(document.getElementById('transmissionIntervalSec').value, 10) || 60,
        plcIp: document.getElementById('plcIp').value.trim(),
        plcPort: parseInt(document.getElementById('plcPort').value, 10) || 102,
        tags: collectSensors()
      };
    }

    async function testHttps() {
      const data = collectForm();
      showResult('Testing HTTPS connection to ' + data.baseUrl + '...', 'info');
      try {
        const res = await fetch('/api/test-https', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        const out = await res.json();
        if (out.ok) {
          showResult(`✅ HTTPS Connection Successful! (${out.latency_ms} ms)\\nCloud Status: ${out.details.status || 'OK'}\\nDevice: ${out.details.name} (Model: ${out.details.model})\\nLast Seen: ${out.details.last_seen_at}`, 'success');
        } else {
          showResult(`❌ HTTPS Connection Failed (${out.latency_ms} ms): ${out.error}`, 'error');
        }
      } catch (err) {
        showResult('Network error when contacting local server: ' + err, 'error');
      }
    }

    async function saveConfiguration() {
      const data = collectForm();
      showResult('Saving configuration and sensor definitions...', 'info');
      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        const out = await res.json();
        if (out.ok) {
          showResult(`✅ Configuration and ${data.tags.length} Sensor Definitions saved successfully to config_plc.json!`, 'success');
        } else {
          showResult('❌ Failed to save: ' + out.error, 'error');
        }
      } catch (err) {
        showResult('Error saving configuration: ' + err, 'error');
      }
    }

    async function saveAndRestart() {
      await saveConfiguration();
      showResult('Restarting plc-gateway service...', 'info');
      try {
        const res = await fetch('/api/restart', { method: 'POST' });
        const out = await res.json();
        if (out.ok) {
          showResult('✅ Saved and restarted plc-gateway service successfully! Telemetry streaming is live.', 'success');
        } else {
          showResult('⚠️ Service restart warning: ' + out.error, 'warning');
        }
      } catch (err) {
        showResult('Restart request failed: ' + err, 'error');
      }
    }

    loadConfig();
  </script>
</body>
</html>
"""


class ConfigWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/config":
            cfg = load_config() or {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            req_data = json.loads(post_body)
        except Exception:
            req_data = {}

        if self.path == "/api/test-https":
            base_url = req_data.get("baseUrl")
            dev_id = req_data.get("deviceId")
            api_key = req_data.get("apiKey")
            ok, latency_ms, result = test_https_connection(base_url, dev_id, api_key)
            resp = {
                "ok": ok,
                "latency_ms": latency_ms,
                "details": result if ok else None,
                "error": result if not ok else None
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        elif self.path == "/api/config":
            cfg = load_config() or {}
            if "deviceName" in req_data:
                cfg["deviceName"] = req_data["deviceName"]
            if "deviceId" in req_data:
                cfg["deviceId"] = req_data["deviceId"]
            if "api" not in cfg:
                cfg["api"] = {}
            if "baseUrl" in req_data:
                cfg["api"]["baseUrl"] = req_data["baseUrl"]
            if "apiKey" in req_data:
                cfg["api"]["apiKey"] = req_data["apiKey"]
            if "heartbeatIntervalSec" in req_data:
                cfg["api"]["heartbeatIntervalSec"] = int(req_data["heartbeatIntervalSec"])
            if "transmissionIntervalSec" in req_data:
                cfg["api"]["transmissionIntervalSec"] = int(req_data["transmissionIntervalSec"])
            if "plc" not in cfg:
                cfg["plc"] = {}
            if "plcIp" in req_data:
                cfg["plc"]["ip"] = req_data["plcIp"]
            if "plcPort" in req_data:
                cfg["plc"]["port"] = int(req_data["plcPort"])
            if "tags" in req_data and isinstance(req_data["tags"], list):
                cfg["tags"] = req_data["tags"]

            ok, msg = save_config(cfg)
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "error": msg if not ok else None}).encode("utf-8"))

        elif self.path == "/api/restart":
            res = os.system("sudo systemctl restart plc-gateway")
            ok = (res == 0)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "exitCode": res}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_web_server(port=8080):
    local_ip = get_local_ip()
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, ConfigWebHandler)
    print(f"\n{CLR_GREEN}{CLR_BOLD}{'='*70}{CLR_RESET}")
    print(f"{CLR_BOLD}🌐 IoT Edge Gateway Web Configurator Running!{CLR_RESET}")
    print(f"{CLR_GREEN}{'='*70}{CLR_RESET}")
    print(f"  Access the configuration dashboard from any browser:")
    print(f"    • Local URL:    {CLR_CYAN}http://localhost:{port}{CLR_RESET}")
    print(f"    • Network URL:  {CLR_CYAN}http://{local_ip}:{port}{CLR_RESET}")
    print(f"  Press {CLR_YELLOW}Ctrl+C{CLR_RESET} to stop the web server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{CLR_YELLOW}Stopping Web Configurator...{CLR_RESET}")
        httpd.server_close()


# --- Sensor Management Interactive Submenu ---
def sensor_management_menu(cfg):
    while True:
        display_sensors(cfg)
        print(f"{CLR_BOLD}Sensor & Memory Map Actions:{CLR_RESET}")
        print(f"  [{CLR_CYAN}1{CLR_RESET}] ➕ เพิ่มเซนเซอร์ใหม่ (Define New Sensor)")
        print(f"  [{CLR_CYAN}2{CLR_RESET}] ✏️  แก้ไขข้อมูลเซนเซอร์ (Edit Sensor Definition)")
        print(f"  [{CLR_CYAN}3{CLR_RESET}] 🗑️  ลบเซนเซอร์ (Delete Sensor)")
        print(f"  [{CLR_CYAN}0{CLR_RESET}] ↩️  ย้อนกลับ (Back to Main Menu)")

        sub_choice = input(f"\n{CLR_BOLD}Enter choice [0-3]: {CLR_RESET}").strip()
        tags = cfg.setdefault("tags", [])

        if sub_choice == "0":
            break
        elif sub_choice == "1":
            print(f"\n{CLR_BOLD}--- Add New Sensor ---{CLR_RESET}")
            new_id = len(tags) + 1
            name = input("Enter Sensor Name (e.g. oil_tank_level): ").strip()
            if not name:
                print(f"{CLR_RED}Sensor name cannot be empty.{CLR_RESET}")
                continue
            addr = input("Enter PLC DB Address (e.g. DB1.DBD64): ").strip()
            dtype = input("Enter Data Type (REAL, DINT, INT, BOOL, WORD, STRING) [REAL]: ").strip().upper() or "REAL"
            unit = input("Enter Unit (e.g. °C, bar, mm, L): ").strip()
            desc = input("Enter Description / Label: ").strip()

            new_tag = {
                "id": new_id,
                "name": name,
                "address": addr,
                "type": dtype,
                "unit": unit,
                "desc": desc
            }
            tags.append(new_tag)
            save_config(cfg)
            print(f"{CLR_GREEN}✓ Added new sensor '{name}' (ID #{new_id}) successfully!{CLR_RESET}")
        elif sub_choice == "2":
            id_str = input("\nEnter Sensor ID or Name to edit: ").strip()
            matched = None
            for t in tags:
                if str(t.get("id")) == id_str or t.get("name") == id_str:
                    matched = t
                    break
            if not matched:
                print(f"{CLR_RED}Sensor '{id_str}' not found.{CLR_RESET}")
                continue
            print(f"Editing Sensor #{matched.get('id')} ({matched.get('name')}):")
            new_name = input(f"New Name [current: {matched.get('name')}]: ").strip()
            new_addr = input(f"New DB Address [current: {matched.get('address')}]: ").strip()
            new_type = input(f"New Type [current: {matched.get('type')}]: ").strip().upper()
            new_unit = input(f"New Unit [current: {matched.get('unit')}]: ").strip()
            new_desc = input(f"New Description [current: {matched.get('desc')}]: ").strip()

            if new_name: matched["name"] = new_name
            if new_addr: matched["address"] = new_addr
            if new_type: matched["type"] = new_type
            if new_unit: matched["unit"] = new_unit
            if new_desc: matched["desc"] = new_desc

            save_config(cfg)
            print(f"{CLR_GREEN}✓ Sensor #{matched.get('id')} updated successfully!{CLR_RESET}")
        elif sub_choice == "3":
            id_str = input("\nEnter Sensor ID to delete: ").strip()
            idx_to_del = None
            for i, t in enumerate(tags):
                if str(t.get("id")) == id_str or t.get("name") == id_str:
                    idx_to_del = i
                    break
            if idx_to_del is not None:
                del tags[idx_to_del]
                save_config(cfg)
                print(f"{CLR_GREEN}✓ Sensor deleted successfully!{CLR_RESET}")
            else:
                print(f"{CLR_RED}Sensor '{id_str}' not found.{CLR_RESET}")


# --- Interactive CLI Wizard ---
def interactive_menu():
    while True:
        cfg = load_config()
        if not cfg:
            print(f"{CLR_RED}Unable to load {CONFIG_FILE}. Exiting.{CLR_RESET}")
            sys.exit(1)

        display_config(cfg)
        print(f"{CLR_BOLD}Select an action:{CLR_RESET}")
        print(f"  [{CLR_CYAN}1{CLR_RESET}] 🏷️  ตั้งชื่ออุปกรณ์ (Set Device Name)")
        print(f"  [{CLR_CYAN}2{CLR_RESET}] 🆔 กำหนดรหัส Cloud Device UUID")
        print(f"  [{CLR_CYAN}3{CLR_RESET}] 🔑 กำหนด Cloud API Key (x-api-key)")
        print(f"  [{CLR_CYAN}4{CLR_RESET}] 🌐 กำหนด Cloud HTTPS Base URL")
        print(f"  [{CLR_CYAN}5{CLR_RESET}] 🏭 กำหนด IP ตู้ Siemens S7-1200 PLC")
        print(f"  [{CLR_CYAN}6{CLR_RESET}] ⏱️  กำหนดรอบเวลา Heartbeat & Batch Rate")
        print(f"  [{CLR_CYAN}S{CLR_RESET}] 📊 จัดการแท็กและกำหนดเซนเซอร์ (Define Sensors & Memory Map)")
        print(f"  [{CLR_CYAN}7{CLR_RESET}] 🔍 ทดสอบเชื่อมต่อ Live HTTPS Cloud API")
        print(f"  [{CLR_CYAN}8{CLR_RESET}] 🌐 เปิด Web Configurator Dashboard (พอร์ต 8080)")
        print(f"  [{CLR_CYAN}9{CLR_RESET}] 📦 ตรวจสอบการแปลง Raw Hex Data และ Web Batch Package (plc-package)")
        print(f"  [{CLR_CYAN}A{CLR_RESET}] 🔍 สแกนค้นหาตู้ Siemens PLC อัตโนมัติ (Auto-Discover PLC on Network)")
        print(f"  [{CLR_CYAN}R{CLR_RESET}] 🚀 รีสตาร์ท Gateway Service (systemctl restart plc-gateway)")
        print(f"  [{CLR_CYAN}0{CLR_RESET}] ออก (Exit)")

        choice = input(f"\n{CLR_BOLD}Enter choice [0-9, S, A, R]: {CLR_RESET}").strip().upper()

        if choice == "0":
            print("Exiting.")
            break
        elif choice == "1":
            current_name = cfg.get("deviceName", "")
            print(f"Current Device Name: {CLR_CYAN}{current_name}{CLR_RESET}")
            new_name = input("Enter new Device Name (e.g. GSE-PROTO-1): ").strip()
            if new_name:
                cfg["deviceName"] = new_name
                save_config(cfg)
                print(f"{CLR_GREEN}✓ Device Name updated to '{new_name}'.{CLR_RESET}")
        elif choice == "2":
            current_id = cfg.get("deviceId", "")
            print(f"Current Device UUID: {CLR_CYAN}{current_id}{CLR_RESET}")
            new_id = input("Enter new Device UUID: ").strip()
            if new_id:
                cfg["deviceId"] = new_id
                save_config(cfg)
                print(f"{CLR_GREEN}✓ Device UUID updated to '{new_id}'.{CLR_RESET}")
        elif choice == "3":
            current_key = cfg.get("api", {}).get("apiKey", "")
            print(f"Current API Key: {mask_key(current_key)}")
            val = input("Enter new API Key (press Enter to keep current): ").strip()
            if val:
                cfg.setdefault("api", {})["apiKey"] = val
                save_config(cfg)
                print(f"{CLR_GREEN}✓ API Key updated.{CLR_RESET}")
        elif choice == "4":
            current_url = cfg.get("api", {}).get("baseUrl", "")
            print(f"Current Base URL: {current_url}")
            val = input("Enter new HTTPS Base URL (press Enter to keep current): ").strip()
            if val:
                cfg.setdefault("api", {})["baseUrl"] = val
                save_config(cfg)
                print(f"{CLR_GREEN}✓ Cloud Base URL updated.{CLR_RESET}")
        elif choice == "5":
            p_ip = cfg.get("plc", {}).get("ip", "192.168.2.2")
            p_port = cfg.get("plc", {}).get("port", 102)
            print(f"Current PLC Target: {p_ip}:{p_port}")
            new_ip = input(f"Enter PLC IP address (type 'auto' for Automatic Discovery, or press Enter to keep {p_ip}): ").strip()
            new_port = input(f"Enter PLC Port (press Enter to keep {p_port}): ").strip()
            if new_ip:
                cfg.setdefault("plc", {})["ip"] = new_ip
                if new_ip.lower() == "auto":
                    cfg.setdefault("plc", {})["autoDiscover"] = True
            if new_port.isdigit():
                cfg.setdefault("plc", {})["port"] = int(new_port)
            save_config(cfg)
            print(f"{CLR_GREEN}✓ PLC connection updated.{CLR_RESET}")
        elif choice == "6":
            hb = cfg.get("api", {}).get("heartbeatIntervalSec", 30)
            tx = cfg.get("api", {}).get("transmissionIntervalSec", 60)
            print(f"Current Heartbeat Interval: {hb}s")
            print(f"Current Batch Interval:     {tx}s")
            new_hb = input("Enter Heartbeat Interval in seconds (default 30): ").strip()
            new_tx = input("Enter Batch Interval in seconds (default 60): ").strip()
            if new_hb.isdigit():
                cfg.setdefault("api", {})["heartbeatIntervalSec"] = int(new_hb)
            if new_tx.isdigit():
                cfg.setdefault("api", {})["transmissionIntervalSec"] = int(new_tx)
            save_config(cfg)
            print(f"{CLR_GREEN}✓ Intervals updated.{CLR_RESET}")
        elif choice == "S":
            sensor_management_menu(cfg)
        elif choice == "7":
            base_url = cfg.get("api", {}).get("baseUrl")
            dev_id = cfg.get("deviceId")
            api_key = cfg.get("api", {}).get("apiKey")
            print(f"\n{CLR_YELLOW}Testing HTTPS connection to {base_url}/edge/devices/{dev_id}...{CLR_RESET}")
            ok, latency_ms, result = test_https_connection(base_url, dev_id, api_key)
            if ok:
                print(f"{CLR_GREEN}✓ HTTPS Connection Validated! (Latency: {latency_ms} ms){CLR_RESET}")
                print(f"  • Cloud Status:  {result.get('status')}")
                print(f"  • Registered As: {result.get('name')} (Model: {result.get('model')})")
                print(f"  • Last Seen:     {result.get('last_seen_at')}")
                asset = result.get("asset", {})
                if asset:
                    print(f"  • Asset Name:    {asset.get('name')} (ID: {asset.get('id')})")
            else:
                print(f"{CLR_RED}✗ HTTPS Connection Failed ({latency_ms} ms): {result}{CLR_RESET}")
            input("\nPress Enter to continue...")
        elif choice == "8":
            run_web_server(8080)
        elif choice == "9":
            try:
                from plc_gateway import EdgeGatewayService
                gw = EdgeGatewayService(config_path=CONFIG_FILE)
                sub_c = input(f"Select mode: [1] Live Physical PLC, [2] Sample Dry-run (Default 1): ").strip()
                sample_mode = (sub_c == "2")
                gw.inspect_package(sample=sample_mode, transmit=False)
            except Exception as e:
                print(f"{CLR_RED}Failed to inspect package: {e}{CLR_RESET}")
            input("\nPress Enter to continue...")
        elif choice == "A":
            print(f"\n{CLR_YELLOW}🔍 Scanning local networks for Siemens S7-1200 PLCs (Port 102)...{CLR_RESET}")
            try:
                from plc_driver import discover_s7_plcs
                found = discover_s7_plcs()
                if not found:
                    print(f"\n{CLR_RED}⚠️  No Siemens S7 PLCs found on local subnets.{CLR_RESET}")
                    print("   • Please verify LAN cable connection to PLC or network switch.")
                    print("   • Ensure PLC is powered on.")
                else:
                    print(f"\n{CLR_GREEN}✅ Found {len(found)} Siemens PLC(s) on network:{CLR_RESET}\n")
                    print(f"{'#':>2} | {'IP Address':<16} | {'Port':<6} | {'Latency':<10} | {'Status / Device'}")
                    print("-" * 75)
                    for idx, item in enumerate(found, 1):
                        print(f"{idx:>2} | {item['ip']:<16} | {item['port']:<6} | {item['latency_ms']} ms   | {item['details']}")
                    print("-" * 75)
                    ans = input(f"\nDo you want to bind PLC to '{found[0]['ip']}:{found[0]['port']}'? [Y/n]: ").strip().lower()
                    if ans in ("", "y", "yes"):
                        cfg.setdefault("plc", {})["ip"] = found[0]["ip"]
                        cfg.setdefault("plc", {})["port"] = found[0]["port"]
                        cfg.setdefault("plc", {})["autoDiscover"] = True
                        save_config(cfg)
                        print(f"{CLR_GREEN}✓ PLC target updated to {found[0]['ip']}:{found[0]['port']} with Auto-Discovery enabled!{CLR_RESET}")
            except Exception as e:
                print(f"{CLR_RED}Auto-Discovery error: {e}{CLR_RESET}")
            input("\nPress Enter to continue...")
        elif choice == "R":
            restart_gateway_service()
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="IoT Edge Gateway Configuration & HTTPS Validation Tool")
    parser.add_argument("--view", "-v", action="store_true", help="Display current active configuration")
    parser.add_argument("--sensors", "--list-sensors", action="store_true", help="Display all defined sensors & memory map")
    parser.add_argument("--package", "--inspect-package", action="store_true", help="Inspect Raw Data Hex -> Parsed Sensors & Web Batch Package")
    parser.add_argument("--sample", action="store_true", help="Use realistic sample PLC byte packets (for dry-run inspection)")
    parser.add_argument("--discover-plc", "--discover", action="store_true", help="Auto-scan local network and discover Siemens S7 PLCs on port 102")
    parser.add_argument("--test", "-t", action="store_true", help="Test live HTTPS Cloud API connection")
    parser.add_argument("--set-name", "-n", type=str, help="Set Device Name (e.g. GSE-PROTO-1)")
    parser.add_argument("--set-id", "--set-device", type=str, help="Set Cloud Device UUID")
    parser.add_argument("--set-key", "-k", type=str, help="Set Cloud API Key (x-api-key)")
    parser.add_argument("--set-url", type=str, help="Set Cloud HTTPS Base URL")
    parser.add_argument("--set-plc-ip", type=str, help="Set Siemens PLC IP address")
    parser.add_argument("--restart", "-r", action="store_true", help="Restart plc-gateway service")
    parser.add_argument("--web", "-w", action="store_true", help="Launch local Web Configurator portal")
    parser.add_argument("--port", type=int, default=8080, help="Port for Web Configurator portal (default: 8080)")

    args = parser.parse_args()

    cfg = load_config()
    if not cfg:
        sys.exit(1)

    modified = False

    if args.set_name:
        cfg["deviceName"] = args.set_name
        modified = True
        print(f"{CLR_GREEN}✓ Device Name set to: {args.set_name}{CLR_RESET}")

    if args.set_id:
        cfg["deviceId"] = args.set_id
        modified = True
        print(f"{CLR_GREEN}✓ Device UUID set to: {args.set_id}{CLR_RESET}")

    if args.set_url:
        cfg.setdefault("api", {})["baseUrl"] = args.set_url
        modified = True
        print(f"{CLR_GREEN}✓ Cloud Base URL set to: {args.set_url}{CLR_RESET}")

    if args.set_key:
        cfg.setdefault("api", {})["apiKey"] = args.set_key
        modified = True
        print(f"{CLR_GREEN}✓ Cloud API Key updated.{CLR_RESET}")

    if args.set_plc_ip:
        cfg.setdefault("plc", {})["ip"] = args.set_plc_ip
        modified = True
        print(f"{CLR_GREEN}✓ PLC IP set to: {args.set_plc_ip}{CLR_RESET}")

    if modified:
        ok, msg = save_config(cfg)
        if not ok:
            print(f"{CLR_RED}Failed to save configuration: {msg}{CLR_RESET}")

    if args.restart:
        restart_gateway_service()

    if args.sensors:
        display_sensors(cfg)
        return

    if args.package:
        from plc_gateway import EdgeGatewayService
        gw = EdgeGatewayService(config_path=CONFIG_FILE)
        gw.inspect_package(sample=args.sample, transmit=False)
        return

    if args.discover_plc:
        from plc_driver import discover_s7_plcs
        print("=" * 75)
        print("🔍 Scanning local networks for Siemens S7-1200 PLCs (Port 102)...")
        print("=" * 75)
        found = discover_s7_plcs()
        if not found:
            print(f"\n{CLR_RED}⚠️  No Siemens S7 PLCs found on local subnets.{CLR_RESET}")
            print("   • Please verify LAN cable connection to PLC or network switch.")
            print("   • Ensure PLC is powered on.")
        else:
            print(f"\n{CLR_GREEN}✅ Found {len(found)} Siemens PLC(s) on network:{CLR_RESET}\n")
            print(f"{'#':>2} | {'IP Address':<16} | {'Port':<6} | {'Latency':<10} | {'Status / Device'}")
            print("-" * 75)
            for idx, item in enumerate(found, 1):
                print(f"{idx:>2} | {item['ip']:<16} | {item['port']:<6} | {item['latency_ms']} ms   | {item['details']}")
            print("-" * 75)
            print(f"💡 Run 'plc-config --set-plc-ip auto' to automatically bind to discovered PLC.")
        print("=" * 75 + "\n")
        return

    if args.view:
        display_config(cfg)
        return

    if args.test:
        base_url = cfg.get("api", {}).get("baseUrl")
        dev_id = cfg.get("deviceId")
        api_key = cfg.get("api", {}).get("apiKey")
        print(f"Testing HTTPS connection to {base_url}/edge/devices/{dev_id}...")
        ok, latency_ms, result = test_https_connection(base_url, dev_id, api_key)
        if ok:
            print(f"{CLR_GREEN}✓ HTTPS Connection Validated! (Latency: {latency_ms} ms){CLR_RESET}")
            print(f"  • Cloud Status:  {result.get('status')}")
            print(f"  • Registered As: {result.get('name')} (Model: {result.get('model')})")
            print(f"  • Last Seen:     {result.get('last_seen_at')}")
            asset = result.get("asset", {})
            if asset:
                print(f"  • Asset Name:    {asset.get('name')} (ID: {asset.get('id')})")
            sys.exit(0)
        else:
            print(f"{CLR_RED}✗ HTTPS Connection Failed ({latency_ms} ms): {result}{CLR_RESET}")
            sys.exit(1)

    if args.web:
        run_web_server(args.port)
        return

    if len(sys.argv) == 1:
        interactive_menu()


if __name__ == "__main__":
    main()
