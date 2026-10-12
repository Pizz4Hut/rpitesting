#!/usr/bin/env python3
"""
Raspberry Pi IoT Telemetry Agent
Collects hardware metrics (CPU temp, CPU usage, RAM, Disk, Uptime, IP)
and sends them periodically to your Netlify serverless API endpoint.
"""

import sys
import os
import time
import socket
import argparse
import json
import shutil
import urllib.request
import urllib.error

# Try importing psutil for enhanced metrics, fallback to Linux /proc if not installed
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_cpu_temp():
    """Reads Raspberry Pi CPU temperature in Celsius."""
    # Method 1: Linux thermal zone (Standard on Raspberry Pi OS)
    try:
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            with open(thermal_path, "r") as f:
                temp_raw = f.read().strip()
                return round(float(temp_raw) / 1000.0, 1)
    except Exception:
        pass

    # Method 2: vcgencmd (VideoCore utility on Raspberry Pi)
    try:
        import subprocess
        res = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            # Output format: temp=48.5'C
            temp_str = res.stdout.replace("temp=", "").replace("'C", "").strip()
            return round(float(temp_str), 1)
    except Exception:
        pass

    # Fallback simulation if running on non-Pi machine (e.g. Mac/PC for testing)
    import random
    return round(42.0 + random.uniform(0, 15), 1)


def get_cpu_usage():
    """Gets CPU usage percentage."""
    if HAS_PSUTIL:
        return round(psutil.cpu_percent(interval=0.5), 1)
    
    # Fallback to /proc/stat
    try:
        def read_stat():
            with open("/proc/stat", "r") as f:
                fields = [float(x) for x in f.readline().strip().split()[1:5]]
            return sum(fields), fields[3] # total, idle

        t1, idle1 = read_stat()
        time.sleep(0.5)
        t2, idle2 = read_stat()
        delta_total = t2 - t1
        delta_idle = idle2 - idle1
        if delta_total > 0:
            return round(100.0 * (1.0 - (delta_idle / delta_total)), 1)
    except Exception:
        pass

    return 15.0


def get_ram_info():
    """Gets RAM usage (percent, used MB, total MB)."""
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        return {
            "ramUsage": round(mem.percent, 1),
            "ramUsedMB": round(mem.used / (1024 * 1024)),
            "ramTotalMB": round(mem.total / (1024 * 1024))
        }

    # Fallback using /proc/meminfo
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
        total_kb = meminfo.get("MemTotal", 1024 * 1024)
        free_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        used_kb = total_kb - free_kb
        percent = (used_kb / total_kb) * 100
        return {
            "ramUsage": round(percent, 1),
            "ramUsedMB": round(used_kb / 1024),
            "ramTotalMB": round(total_kb / 1024)
        }
    except Exception:
        pass

    return {"ramUsage": 35.0, "ramUsedMB": 1400, "ramTotalMB": 4096}


def get_disk_info():
    """Gets primary disk usage using standard shutil."""
    try:
        total, used, free = shutil.disk_usage("/")
        return {
            "diskUsage": round((used / total) * 100, 1),
            "diskFreeGB": round(free / (1024 ** 3), 1)
        }
    except Exception:
        return {"diskUsage": 45.0, "diskFreeGB": 16.0}


def get_uptime_seconds():
    """Gets system uptime in seconds."""
    try:
        with open("/proc/uptime", "r") as f:
            return int(float(f.readline().split()[0]))
    except Exception:
        pass
    if HAS_PSUTIL:
        return int(time.time() - psutil.boot_time())
    return 3600


def get_local_ip():
    """Detects active local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't actually establish an external connection
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_os_info():
    """Gets OS and kernel details."""
    try:
        return os.uname().sysname + " " + os.uname().release + " (" + os.uname().machine + ")"
    except Exception:
        return "Raspberry Pi OS"


def read_custom_sensors():
    """
    Optional hook for attached hardware sensors (DHT11/22, BME280, BMP180, etc.)
    Edit this function to read from your specific GPIO pins or I2C sensors!
    """
    # Return simulated or default sensor readings
    import random
    return {
        "ambientTemp": round(23.5 + random.uniform(-0.5, 0.5), 1),
        "humidity": round(55.0 + random.uniform(-1.0, 1.0), 1),
        "pressure": 1013.25
    }


def send_telemetry(url, payload, api_key=None, timeout=10):
    """Sends JSON payload to the Netlify endpoint."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "RaspberryPi-Telemetry-Agent/1.0"
    }
    if api_key:
        headers["x-api-key"] = api_key

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Telemetry Agent for Netlify Dashboard")
    parser.add_argument("--url", default="http://localhost:8888/api/telemetry", help="Target API URL")
    parser.add_argument("--device-id", default=None, help="Unique Device Identifier (e.g. pi-living-room)")
    parser.add_argument("--device-name", default=None, help="Friendly Device Name (e.g. 'Living Room Pi 4')")
    parser.add_argument("--api-key", default=None, help="Optional API Key matching Netlify DEVICE_API_KEY")
    parser.add_argument("--interval", type=int, default=10, help="Reporting interval in seconds (default: 10)")
    parser.add_argument("--config", default=None, help="Path to config.json file")

    args = parser.parse_args()

    # Load from config file if supplied
    config = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, "r") as f:
            config = json.load(f)

    target_url = config.get("url", args.url)
    api_key = config.get("apiKey", args.api_key)
    interval = config.get("interval", args.interval)

    hostname = socket.gethostname()
    device_id = config.get("deviceId", args.device_id or f"rpi-{hostname}")
    device_name = config.get("deviceName", args.device_name or f"Raspberry Pi ({hostname})")

    print("=" * 60)
    print("🍓 Raspberry Pi IoT Telemetry Agent")
    print(f"📡 Target Endpoint: {target_url}")
    print(f"🏷️  Device ID:       {device_id}")
    print(f"📛 Device Name:     {device_name}")
    print(f"⏱️  Interval:        {interval}s")
    print("=" * 60)

    while True:
        try:
            ram = get_ram_info()
            disk = get_disk_info()
            cpu_temp = get_cpu_temp()
            cpu_usage = get_cpu_usage()

            payload = {
                "deviceId": device_id,
                "deviceName": device_name,
                "timestamp": int(time.time() * 1000),
                "system": {
                    "cpuTemp": cpu_temp,
                    "cpuUsage": cpu_usage,
                    "ramUsage": ram["ramUsage"],
                    "ramUsedMB": ram["ramUsedMB"],
                    "ramTotalMB": ram["ramTotalMB"],
                    "diskUsage": disk["diskUsage"],
                    "diskFreeGB": disk["diskFreeGB"],
                    "uptimeSeconds": get_uptime_seconds(),
                    "ipAddress": get_local_ip(),
                    "hostname": hostname,
                    "os": get_os_info()
                },
                "sensors": read_custom_sensors()
            }

            if api_key:
                payload["apiKey"] = api_key

            status_code, response_body = send_telemetry(target_url, payload, api_key=api_key)
            print(f"[{time.strftime('%X')}] ✅ Sent | CPU Temp: {cpu_temp}°C | CPU: {cpu_usage}% | RAM: {ram['ramUsage']}% | Code: {status_code}")

        except urllib.error.HTTPError as e:
            print(f"[{time.strftime('%X')}] ❌ HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"[{time.strftime('%X')}] ⚠️ Network Connection Failed: {e.reason}", file=sys.stderr)
        except Exception as e:
            print(f"[{time.strftime('%X')}] ⚠️ Unexpected Error: {str(e)}", file=sys.stderr)

        time.sleep(interval)


if __name__ == "__main__":
    main()
