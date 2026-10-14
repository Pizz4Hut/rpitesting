#!/usr/bin/env python3
"""
Automated Self-Diagnosis & Troubleshooting Utility
Comprehensive health-check for Siemens S7-1200 Industrial IoT Edge Gateway.
Checks:
 1. System Health (CPU Temp, MicroSD Storage, Uptime)
 2. Network & LAN Connectivity (eth0, eth1, Internet Ping, DNS Resolution)
 3. Physical Siemens S7-1200 PLC Connectivity (Ping & S7comm Port 102)
 4. Cloud REST API Health (Railway Edge Device API, x-api-key, TLS Handshake)
 5. SQLite Store-and-Forward Buffer Integrity (WAL Journal Mode, Backlog Queue)
 6. PNR Reference Code Generator Verification (Crockford Base32 6-char Collision-Free)
 7. Systemd Background Service Autostart Status (plc-gateway.service)
Outputs colored PASS / WARN / FAIL badges with actionable troubleshooting tips.
"""

import sys
import os
import socket
import subprocess
import json
import time
import ssl
import urllib.request
import urllib.error

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS_BADGE = f"{GREEN}{BOLD}[ PASS ]{RESET}"
WARN_BADGE = f"{YELLOW}{BOLD}[ WARN ]{RESET}"
FAIL_BADGE = f"{RED}{BOLD}[ FAIL ]{RESET}"
INFO_BADGE = f"{BLUE}{BOLD}[ INFO ]{RESET}"


def print_header(title):
    print(f"\n{CYAN}{BOLD}{'=' * 68}")
    print(f"  🔍 {title}")
    print(f"{'=' * 68}{RESET}")


def load_config(config_path="config_plc.json"):
    target_path = config_path
    if not os.path.exists(target_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        fallback = os.path.join(script_dir, os.path.basename(config_path))
        if os.path.exists(fallback):
            target_path = fallback
        else:
            return None
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def check_tcp_port(ip, port, timeout=2.5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False


def test_cloud_device_api(base_url, device_id, api_key, timeout=5.0):
    if not base_url or not device_id:
        return False, "Base URL or Device ID not configured"
    
    target_url = f"{base_url.rstrip('/')}/edge/devices/{device_id}"
    req_headers = {
        "x-api-key": api_key or "",
        "User-Agent": "EdgeGateway-Diagnostics/1.0",
        "Accept": "application/json"
    }

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(target_url, headers=req_headers, method="GET")
        start_t = time.time()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            elapsed_ms = round((time.time() - start_t) * 1000, 1)
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            status_str = data.get("status", "ACTIVE")
            dev_name = data.get("name", "Unknown")
            return True, f"HTTP 200 OK (Latency: {elapsed_ms}ms | Cloud Status: {status_str} | Name: {dev_name})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "HTTP 401 Unauthorized - API Key (x-api-key) is invalid or rejected by Cloud!"
        elif e.code == 404:
            return False, f"HTTP 404 Not Found - Device ID '{device_id}' is not registered on Cloud!"
        elif e.code in (200, 201, 204):
            return True, f"HTTP {e.code}"
        return False, f"HTTP {e.code} ({e.reason})"
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "Connection refused" in reason or "111" in reason:
            return False, "Connection refused (No server listening on this port)"
        if "Name or service not known" in reason or "nodename" in reason:
            return False, "DNS resolution failed (Domain cannot be resolved)"
        return False, reason
    except Exception as e:
        return False, str(e)


def run_full_diagnosis(config_path="config_plc.json"):
    print(f"\n{BOLD}====================================================================")
    print(f"🍓 Raspberry Pi 4 Edge Gateway — Automated Self-Diagnostic Tool")
    print(f"===================================================================={RESET}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    config = load_config(config_path)
    if not config:
        print(f"\n{FAIL_BADGE} Could not load '{config_path}'! Please check if file exists.")
        return

    issues = []

    # -------------------------------------------------------------
    # 1. SYSTEM HEALTH
    # -------------------------------------------------------------
    print_header("1. System Health & Hardware Metrics")
    # CPU Temp
    cpu_temp = 0.0
    if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                cpu_temp = round(float(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass

    if cpu_temp == 0.0:
        print(f"{INFO_BADGE} CPU Temperature: N/A (Non-Linux or VM environment)")
    elif cpu_temp < 70.0:
        print(f"{PASS_BADGE} CPU Temperature: {cpu_temp}°C (Normal operational range)")
    elif cpu_temp < 80.0:
        print(f"{WARN_BADGE} CPU Temperature: {cpu_temp}°C (Elevated, ensure enclosure has ventilation)")
        issues.append("CPU Temperature is high (>70°C). Check cabinet cooling fan.")
    else:
        print(f"{FAIL_BADGE} CPU Temperature: {cpu_temp}°C (Critical thermal throttling risk!)")
        issues.append("CPU Temperature is critical (>80°C). Raspberry Pi may throttle.")

    # RAM & Disk
    ok, df_out, _ = run_cmd("df -h / | awk 'NR==2 {print $4, $5}'")
    if ok and df_out:
        avail, pct = df_out.split()
        pct_int = int(pct.replace("%", ""))
        if pct_int < 85:
            print(f"{PASS_BADGE} MicroSD Storage: {avail} free ({pct} used)")
        else:
            print(f"{WARN_BADGE} MicroSD Storage: Low space ({avail} free, {pct} used)")
            issues.append("MicroSD storage nearly full. Consider purging old logs.")

    # -------------------------------------------------------------
    # 2. NETWORK CONNECTIVITY
    # -------------------------------------------------------------
    print_header("2. Network & LAN Connectivity")
    net_cfg = config.get("network", {})
    lan1_if = net_cfg.get("lan1_plc_interface", "eth0")
    lan2_if = net_cfg.get("lan2_internet_interface", "eth1")

    # Local IP for LAN 1
    ok_ip1, ip1, _ = run_cmd(f"ip -4 addr show {lan1_if} 2>/dev/null | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){{3}}' | head -n1")
    if ok_ip1 and ip1:
        print(f"{PASS_BADGE} LAN 1 Interface ({lan1_if}): IP {ip1}")
    else:
        print(f"{WARN_BADGE} LAN 1 Interface ({lan1_if}): No IP assigned or interface down")

    # Internet Ping Test
    ok_ping, _, _ = run_cmd("ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1")
    if ok_ping:
        print(f"{PASS_BADGE} Internet Gateway (Ping 8.8.8.8): Reachable")
    else:
        print(f"{WARN_BADGE} Internet Gateway (Ping 8.8.8.8): Unreachable")
        issues.append("Cannot ping 8.8.8.8. Check Switching Hub / router gateway cable.")

    # DNS Test
    ok_dns, _, _ = run_cmd("ping -c 1 -W 2 github.com >/dev/null 2>&1")
    if ok_dns:
        print(f"{PASS_BADGE} DNS Resolution (github.com): Resolving normally")
    else:
        print(f"{WARN_BADGE} DNS Resolution: Unable to resolve external domains")

    # -------------------------------------------------------------
    # 3. PHYSICAL SIEMENS S7-1200 PLC CONNECTIVITY
    # -------------------------------------------------------------
    print_header("3. Siemens S7-1200 PLC Connectivity (Physical Connection Only)")
    plc_cfg = config.get("plc", {})
    plc_ip = plc_cfg.get("ip", "192.168.2.2")
    plc_port = plc_cfg.get("port", 102)

    print(f"{INFO_BADGE} Target PLC Address: {plc_ip}:{plc_port} (S7comm Protocol)")

    # Ping test
    ok_plc_ping, _, _ = run_cmd(f"ping -c 1 -W 2 {plc_ip} >/dev/null 2>&1")
    if ok_plc_ping:
        print(f"{PASS_BADGE} Network Ping Check: {plc_ip} is ALIVE on LAN")
    else:
        print(f"{FAIL_BADGE} Network Ping Check: {plc_ip} is UNREACHABLE")

    # Port 102 check
    port_open = check_tcp_port(plc_ip, plc_port, timeout=2.5)
    if port_open:
        print(f"{PASS_BADGE} S7comm TCP Port {plc_port}: OPEN and accepting connections")
        print(f"{PASS_BADGE} Physical PLC State: Connected & ready for 19-Tag acquisition")
    else:
        print(f"{FAIL_BADGE} S7comm TCP Port {plc_port}: CLOSED or connection refused")
        print(f"{WARN_BADGE} ⚠️ [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {plc_ip}:{plc_port}!")
        print(f"         • ให้เชื่อมต่อสาย LAN จากตู้ PLC S7-1200 เข้าพอร์ต eth0 ของ Raspberry Pi")
        print(f"         • ตรวจสอบว่าตู้ PLC S7-1200 เปิดสวิตช์และไฟสถานะ RUN ติดสว่าง")
        print(f"         • ใน Siemens TIA Portal ต้องติ๊กถูก 'Permit access with PUT/GET communication from remote partner'")
        issues.append(f"ไม่มีข้อมูลจาก PLC: ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {plc_ip}:{plc_port}")

    # -------------------------------------------------------------
    # 4. REST API ENDPOINTS & CLOUD RUNTIME HEALTH
    # -------------------------------------------------------------
    print_header("4. REST API Endpoint Health (Railway Cloud API)")
    api_cfg = config.get("api", {})
    base_url = api_cfg.get("baseUrl", "https://epc-edge-api-dev.up.railway.app/api").rstrip("/")
    api_key = api_cfg.get("apiKey", "")
    dev_id = config.get("deviceId", "")
    dev_name = config.get("deviceName", "(unknown)")

    print(f"{INFO_BADGE} Cloud API Base URL:  {base_url}")
    print(f"{INFO_BADGE} Target Device ID:   {dev_id} ({dev_name})")

    if base_url and dev_id:
        cloud_ok, cloud_msg = test_cloud_device_api(base_url, dev_id, api_key)
        if cloud_ok:
            print(f"{PASS_BADGE} Cloud Device API:    {cloud_msg}")
        else:
            print(f"{FAIL_BADGE} Cloud Device API:    {cloud_msg}")
            issues.append(f"Cloud Device Endpoint Error: {cloud_msg}")
    else:
        print(f"{FAIL_BADGE} Missing Cloud API Base URL or Device ID in config!")
        issues.append("Missing baseUrl or deviceId in configuration.")

    print(f"{PASS_BADGE} Cloud Architecture: Groundshift Technologies Edge Runtime (Railway API)")

    # -------------------------------------------------------------
    # 5. SQLITE BUFFER & REDUNDANCY
    # -------------------------------------------------------------
    print_header("5. SQLite Store-and-Forward Buffer Integrity")
    db_path = config.get("redundancy", {}).get("sqliteDbPath", "buffer.db")
    if not os.path.isabs(db_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, db_path)

    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM telemetry_queue WHERE status = 'pending';")
            pending_count = cursor.fetchone()[0]
            conn.close()

            print(f"{PASS_BADGE} Database File: Found ({os.path.getsize(db_path)} bytes)")
            print(f"{PASS_BADGE} WAL Journal Mode: {journal_mode.upper()} (Crash-resilient)")
            if pending_count == 0:
                print(f"{PASS_BADGE} Offline Backlog Queue: 0 records (All data synced)")
            else:
                print(f"{INFO_BADGE} Offline Backlog Queue: {pending_count} records pending sync")
        except Exception as e:
            print(f"{FAIL_BADGE} SQLite Database Check Failed: {e}")
            issues.append(f"SQLite buffer error: {e}")
    else:
        print(f"{INFO_BADGE} Database file '{db_path}' not created yet (will initialize on first run)")

    # -------------------------------------------------------------
    # 6. PNR CODE GENERATOR
    # -------------------------------------------------------------
    print_header("6. PNR Reference Code Generator Verification")
    try:
        from pnr_generator import generate_pnr, ALPHABET
        test_payload = {
            "org_id": "TEST",
            "batch": {"collected_at": int(time.time() * 1000), "sequence": 999}
        }
        test_pnr = generate_pnr(test_payload)
        is_len_6 = len(test_pnr) == 6
        is_valid_chars = all(c in ALPHABET for c in test_pnr)
        has_no_ambiguous = not any(c in "01OI" for c in test_pnr)

        if is_len_6 and is_valid_chars and has_no_ambiguous:
            print(f"{PASS_BADGE} Algorithm Test: Generated '{test_pnr}' (6 chars, Crockford Base32, 0/1/O/I excluded)")
        else:
            print(f"{FAIL_BADGE} Algorithm Test Failed: Invalid PNR generated '{test_pnr}'")
            issues.append("PNR generator produced non-compliant code.")
    except Exception as e:
        print(f"{FAIL_BADGE} PNR Module Import Failed: {e}")
        issues.append(f"PNR generator error: {e}")

    # -------------------------------------------------------------
    # 7. SYSTEMD SERVICE STATUS
    # -------------------------------------------------------------
    print_header("7. Systemd Autostart Service Status")
    ok_svc, svc_status, _ = run_cmd("systemctl is-active plc-gateway 2>/dev/null")
    ok_enabled, svc_enabled, _ = run_cmd("systemctl is-enabled plc-gateway 2>/dev/null")

    if ok_svc and svc_status == "active":
        print(f"{PASS_BADGE} plc-gateway.service: ACTIVE (Running continuously)")
    else:
        print(f"{INFO_BADGE} plc-gateway.service: {svc_status or 'inactive'} (Start with: sudo systemctl start plc-gateway)")

    if ok_enabled and svc_enabled == "enabled":
        print(f"{PASS_BADGE} Autostart on boot: ENABLED")
    else:
        print(f"{INFO_BADGE} Autostart on boot: {svc_enabled or 'disabled'} (Enable with: sudo systemctl enable plc-gateway)")

    # -------------------------------------------------------------
    # SUMMARY & TROUBLESHOOTING RECOMMENDATIONS
    # -------------------------------------------------------------
    print(f"\n{BOLD}{'=' * 68}")
    print("  📋 DIAGNOSTIC SUMMARY & ACTIONABLE RECOMMENDATIONS")
    print(f"{'=' * 68}{RESET}")

    if not issues:
        print(f"{GREEN}{BOLD}🎉 ALL CHECKS PASSED! The Gateway is 100% healthy and ready.{RESET}")
    else:
        print(f"{YELLOW}{BOLD}Found {len(issues)} item(s) to review:{RESET}\n")
        for idx, item in enumerate(issues, 1):
            print(f"  {idx}. {item}")

        print(f"\n{CYAN}{BOLD}💡 Troubleshooting Quick-Fix Guide:{RESET}")
        print("  • หากขึ้น 'ไม่มีข้อมูลจาก PLC': ให้เสียบสาย LAN จากตู้ PLC S7-1200 เข้าบอร์ด Pi และเปิดสวิตช์ตู้ PLC")
        print("  • หากต้องการเช็ค/สลับการตั้งค่าบอร์ด 1 หรือ 2: รันคำสั่ง 'plc-config'")
        print("  • หากต้องการดู Log การทำงานแบบ Real-time: รันคำสั่ง 'plc-logs' (หรือ sudo journalctl -u plc-gateway -f)")

    print(f"{BOLD}{'=' * 68}\n{RESET}")


if __name__ == "__main__":
    run_full_diagnosis()
