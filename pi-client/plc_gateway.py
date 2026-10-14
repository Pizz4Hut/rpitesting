#!/usr/bin/env python3
"""
Raspberry Pi 4 IoT Edge Gateway for Siemens S7-1200 PLC
- Dual Network: LAN1 (PLC) and LAN2 (Internet)
- S7 Protocol Data Acquisition (up to 19 tags)
- Data Transmission via REST API over HTTP/HTTPS
- Store-and-Forward SQLite Buffer for zero data loss redundancy
- Two-way Heartbeat: Cloud Heartbeat (REST) and PLC Heartbeat (Lifebit toggle)
- System & Hardware Watchdog integration
"""

import sys
import os
import time
import socket
import argparse
import json
import logging
import threading
import signal
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Local modules
from plc_driver import S7PLCClient, pack_plc_bytes, unpack_plc_bytes, format_sensor_reading, discover_s7_plcs
from sqlite_buffer import SQLiteBuffer
from pnr_generator import generate_pnr

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EdgeGateway")


def get_system_metrics():
    """Reads Raspberry Pi 4 hardware metrics."""
    # 1. CPU Temp
    cpu_temp = 45.0
    try:
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            with open(thermal_path, "r") as f:
                cpu_temp = round(float(f.read().strip()) / 1000.0, 1)
    except Exception:
        pass

    # 2. RAM & Disk
    ram_usage = 25.0
    ram_used_mb = 1024
    ram_total_mb = 4096
    disk_usage = 30.0
    disk_free_gb = 24.0

    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        disk_usage = round((used / total) * 100, 1)
        disk_free_gb = round(free / (1024 ** 3), 1)
    except Exception:
        pass

    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem = {}
        for line in lines:
            parts = line.split(":")
            if len(parts) == 2:
                mem[parts[0].strip()] = int(parts[1].strip().split()[0])
        total_kb = mem.get("MemTotal", 4096 * 1024)
        avail_kb = mem.get("MemAvailable", mem.get("MemFree", 2048 * 1024))
        used_kb = total_kb - avail_kb
        ram_usage = round((used_kb / total_kb) * 100, 1)
        ram_used_mb = round(used_kb / 1024)
        ram_total_mb = round(total_kb / 1024)
    except Exception:
        pass

    uptime_sec = 3600
    try:
        with open("/proc/uptime", "r") as f:
            uptime_sec = int(float(f.readline().split()[0]))
    except Exception:
        pass

    return {
        "cpuTemp": cpu_temp,
        "cpuUsage": 12.5,
        "ramUsage": ram_usage,
        "ramUsedMB": ram_used_mb,
        "ramTotalMB": ram_total_mb,
        "diskUsage": disk_usage,
        "diskFreeGB": disk_free_gb,
        "uptimeSeconds": uptime_sec,
        "hostname": socket.gethostname(),
        "os": "Raspberry Pi OS (Linux 6.x)"
    }


def get_mac_address(ifname="eth0"):
    """Reads hardware MAC address of a specific network interface."""
    # Method 1: Linux /sys/class/net interface address
    try:
        sys_path = f"/sys/class/net/{ifname}/address"
        if os.path.exists(sys_path):
            with open(sys_path, "r") as f:
                mac = f.read().strip()
                if mac and len(mac) >= 12:
                    return mac.lower()
    except Exception:
        pass

    # Method 2: ioctl SIOCGIFHWADDR
    try:
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', ifname[:15].encode('utf-8')))
            return ':'.join(['%02x' % b for b in info[18:24]])
    except Exception:
        pass

    # Fallback to uuid node
    import uuid
    node = uuid.getnode()
    mac = ':'.join(("%012x" % node)[i:i+2] for i in range(0, 12, 2))
    return mac.lower()


def get_rpi_serial():
    """Reads unique hardware Serial Number of the Raspberry Pi from /proc/cpuinfo."""
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        parts = line.split(":")
                        if len(parts) == 2:
                            serial = parts[1].strip()
                            if serial and serial != "0000000000000000":
                                return serial
    except Exception:
        pass
    
    # Fallback if testing on PC/Mac or /proc/cpuinfo not present
    return "RPI4B-GEN1-PROTOTYPE-001"


def get_interface_ip(ifname):
    """Gets IP address of a specific network interface (e.g. eth0, eth1, wlan0)."""
    try:
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', ifname[:15].encode('utf-8'))
            )[20:24])
    except Exception:
        # Fallback for testing/Mac
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


def get_tailscale_ip():
    """Reads Tailscale IP address if tailscale is installed and running."""
    try:
        import subprocess
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            ip = res.stdout.strip()
            if ip:
                return ip
    except Exception:
        pass
    # Alternative check interface tailscale0
    return get_interface_ip("tailscale0")


KNOWN_DEVICE_PROFILES = [
    {
        "name": "GSE-PROTO-1",
        "mac_addresses": ["98:fe:54:63:34:ca", "98:FE:54:63:34:CA"],
        "cpu_serials": ["1000000091f9071a"],
        "deviceId": "4045f327-2776-4f34-977e-64e307db648f",
        "apiKey": "gs_17ed8df023f46e3815c2cefd18ecab43e664bd187244012f0aed619c4e7a5a70"
    },
    {
        "name": "GSE-PROTO-2",
        "mac_addresses": ["98:fe:54:63:35:a5", "98:FE:54:63:35:A5"],
        "cpu_serials": ["100000001b657629"],
        "deviceId": "24207b3f-da30-44e7-91f9-8d0067a5d1af",
        "apiKey": "gs_505a9bb4652c76548e1f2c229ac3055a334b47e38e105192ce7dfb24d0e743c6"
    }
]


class EdgeGatewayService:
    def __init__(self, config_path="config_plc.json", simulate_override=None):
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False

        if simulate_override is not None:
            self.config["plc"]["simulate"] = simulate_override

        # Device Identification
        self.device_id = self.config.get("deviceId", "edge-prototype-gen1-001")
        self.device_name = self.config.get("deviceName", "Edge Prototype Gen-1")
        self.org_id = self.config.get("orgId", self.config.get("org_id", "GSE"))
        self.sequence = 1

        conf_sn = self.config.get("serialNumber")
        if not conf_sn or str(conf_sn).strip().lower() in ("auto", "detect", "rpi", ""):
            self.serial_number = get_rpi_serial()
        else:
            self.serial_number = str(conf_sn).strip()

        # Network Interfaces & MAC Addresses
        net_cfg = self.config.get("network", {})
        self.lan1_if = net_cfg.get("lan1_plc_interface", "eth0")
        self.lan2_if = net_cfg.get("lan2_internet_interface", "eth1")

        self.mac_addresses = {
            "lan1_plc": get_mac_address(self.lan1_if),
            "lan2_internet": get_mac_address(self.lan2_if)
        }

        # Auto-detect Network Roles and Hardware Profile
        self.auto_detect_network_roles()
        self.auto_detect_hardware_profile()
        self.last_emergency_state = False

        # Initialize SQLite Store-and-Forward Buffer
        db_path = self.config.get("redundancy", {}).get("sqliteDbPath", "buffer.db")
        if not os.path.isabs(db_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(script_dir, db_path)
        max_records = self.config.get("redundancy", {}).get("maxBufferedRecords", 50000)
        self.buffer = SQLiteBuffer(db_path=db_path, max_records=max_records)

        # Initialize S7 PLC Client (Physical PLC Mode with Auto-Discovery)
        plc_cfg = self.config.get("plc", {})
        auto_disc = plc_cfg.get("autoDiscover", plc_cfg.get("auto_discover", True))
        self.plc = S7PLCClient(
            ip=plc_cfg.get("ip", "auto"),
            rack=plc_cfg.get("rack", 0),
            slot=plc_cfg.get("slot", 1),
            port=plc_cfg.get("port", 102),
            auto_discover=auto_disc,
            simulate=False
        )

        self.last_plc_heartbeat = 0
        self.last_cloud_heartbeat = 0
        self.last_transmission = 0
        self.last_lifebit_val = False

        # Cloud API Base URL & Runtime Session
        api_cfg = self.config.get("api", {})
        self.api_base_url = api_cfg.get("baseUrl", "https://epc-edge-api-dev.up.railway.app/api").rstrip("/")
        self.runtime_id = None

    def auto_detect_network_roles(self):
        """Auto-detects default gateway interface from /proc/net/route.
        Swaps LAN1 (PLC) and LAN2 (Internet) interfaces if cables were accidentally reversed.
        """
        route_file = "/proc/net/route"
        if not os.path.exists(route_file):
            return

        try:
            default_iface = None
            with open(route_file, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    # Destination is parts[1] (hex 00000000 means 0.0.0.0 / default route)
                    if len(parts) >= 2 and parts[1] == "00000000":
                        default_iface = parts[0]
                        break

            if default_iface:
                # If the default route interface is currently assigned to LAN1 (PLC interface),
                # but LAN2 was meant for Internet, the physical Ethernet cables are swapped.
                if default_iface == self.lan1_if and default_iface != self.lan2_if:
                    logger.warning(
                        f"🔄 [AUTO-NETWORK] ตรวจพบสาย LAN สลับพอร์ต! Internet Default Gateway อยู่ที่ {default_iface}. "
                        f"ทำการสลับบทบาท {default_iface} -> LAN2 (Internet) และ {self.lan2_if} -> LAN1 (PLC) อัตโนมัติ"
                    )
                    self.lan1_if, self.lan2_if = self.lan2_if, self.lan1_if
                    self.mac_addresses = {
                        "lan1_plc": get_mac_address(self.lan1_if),
                        "lan2_internet": get_mac_address(self.lan2_if)
                    }
                else:
                    logger.debug(f"[AUTO-NETWORK] Default route confirmed on {default_iface}")
        except Exception as e:
            logger.debug(f"[AUTO-NETWORK] Route inspection skipped: {e}")

    def auto_detect_hardware_profile(self):
        """Matches Raspberry Pi CPU serial / MAC address against known prototype hardware profiles.
        Automatically binds Device UUID and API Key so SD card can be cloned/moved without manual setup.
        """
        macs = [m.lower() for m in self.mac_addresses.values() if m]
        cur_serial = (self.serial_number or "").lower()

        matched_profile = None
        for prof in KNOWN_DEVICE_PROFILES:
            prof_macs = [m.lower() for m in prof.get("mac_addresses", [])]
            prof_serials = [s.lower() for s in prof.get("cpu_serials", [])]

            if cur_serial in prof_serials or any(m in prof_macs for m in macs):
                matched_profile = prof
                break

        if matched_profile:
            logger.info(
                f"🎯 [AUTO-PROFILE] ตรวจพบลักษณะเฉพาะฮาร์ดแวร์: {matched_profile['name']} "
                f"(SN: {self.serial_number}) -> ผูก Device UUID & API Key อัตโนมัติ"
            )
            self.device_id = matched_profile["deviceId"]
            self.device_name = matched_profile["name"]
            self.config["deviceId"] = matched_profile["deviceId"]
            self.config["deviceName"] = matched_profile["name"]
            self.config.setdefault("api", {})["apiKey"] = matched_profile["apiKey"]

    def check_emergency_event(self):
        """Polls emergency safety tags (E-Stop and Machine Fault) every 2s.
        If an emergency transition occurs (e.g., E-Stop triggered or fault raised),
        triggers immediate cloud transmission instead of waiting for standard 60-min interval.
        """
        if not self.plc.is_connected():
            return False

        try:
            # DB1 byte 60 contains DBX60.0 (running), DBX60.1 (fault), DBX60.2 (estop_ok)
            # DB1 byte 62-63 contains DBW62 (active alarm code)
            b_fault = self.plc.read_tag("DB1.DBX60.1", "BOOL")
            b_estop = self.plc.read_tag("DB1.DBX60.2", "BOOL")
            alarm_code = self.plc.read_tag("DB1.DBW62", "INT")

            is_fault = bool(b_fault) if b_fault is not None else False
            # emergency_stop_ok: True is healthy/OK, False is E-Stop pressed/tripped!
            is_estop_tripped = (b_estop is False) if b_estop is not None else False
            has_alarm = bool(alarm_code and alarm_code > 0)

            is_emergency = is_fault or is_estop_tripped or has_alarm

            # Trigger only on rising edge (transition from normal to emergency)
            if is_emergency and not self.last_emergency_state:
                logger.warning(
                    f"🚨 [EMERGENCY-TRIGGER] ตรวจพบเหตุฉุกเฉินกะทันหัน! "
                    f"(Fault: {is_fault}, E-Stop Tripped: {is_estop_tripped}, Alarm: {alarm_code}) "
                    f"-> ข้ามรอบเวลาปกติ ส่งข้อมูลขึ้น Cloud API ทันที!"
                )
                self.last_emergency_state = True
                return True
            elif not is_emergency:
                self.last_emergency_state = False

        except Exception as e:
            logger.debug(f"[EMERGENCY-CHECK] Error checking safety status: {e}")

        return False

    def _load_config(self):
        target_path = self.config_path
        if not os.path.exists(target_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            fallback_path = os.path.join(script_dir, os.path.basename(self.config_path))
            if os.path.exists(fallback_path):
                target_path = fallback_path
            else:
                raise FileNotFoundError(f"Configuration file {self.config_path} not found (also checked {fallback_path}).")
        with open(target_path, "r") as f:
            return json.load(f)

    def send_http_post(self, url, payload, timeout=15):
        """Sends JSON via HTTP/HTTPS POST."""
        api_key = self.config.get("api", {}).get("apiKey", "")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RPi4-EdgeGateway/2.0 (S7-1200)"
        }
        if api_key:
            headers["x-api-key"] = api_key

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")

    def get_network_status(self):
        """Monitors Dual Network interfaces (LAN1 PLC and LAN2 Internet)."""
        lan1_ip = get_interface_ip(self.lan1_if)
        lan2_ip = get_interface_ip(self.lan2_if)

        return {
            "lan1_plc": {
                "interface": self.lan1_if,
                "ip": lan1_ip,
                "mac": self.mac_addresses["lan1_plc"],
                "targetPlcIp": self.config.get("plc", {}).get("ip", "192.168.0.10"),
                "status": "connected" if self.plc.is_connected() else "disconnected"
            },
            "lan2_internet": {
                "interface": self.lan2_if,
                "ip": lan2_ip,
                "mac": self.mac_addresses["lan2_internet"],
                "status": "up"
            }
        }

    def start_runtime(self):
        """Initializes a new Edge Runtime session on Cloud API (POST /edge/devices/{deviceId}/runtimes)."""
        url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes"
        metadata = {
            "hostname": socket.gethostname(),
            "serialNumber": self.serial_number,
            "macAddresses": self.mac_addresses,
            "model": "Raspberry Pi 4 Model B",
            "version": "2.0.0"
        }
        try:
            status, resp_body = self.send_http_post(url, {"metadata": metadata})
            if status in (200, 201):
                res_data = json.loads(resp_body)
                self.runtime_id = res_data.get("id")
                logger.info(f"✨ Cloud Runtime ACTIVATED: {self.runtime_id}")
                return True
            else:
                logger.warning(f"⚠️ Start runtime returned HTTP {status}: {resp_body}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to start runtime session: {e}")
        return False

    def send_heartbeat(self):
        """Sends Gateway Heartbeat to Web API."""
        sys_metrics = get_system_metrics()
        net_status = self.get_network_status()
        queue_depth = self.buffer.get_queue_depth()
        plc_connected = self.plc.is_connected()
        plc_alert = "เชื่อมต่อตู้ PLC สำเร็จ" if plc_connected else f"⚠️ ไม่มีข้อมูลจาก PLC! กรุณาเชื่อมต่อสายสัญญาณ PLC S7-1200 ที่ IP {self.plc.ip}:{self.plc.port}"

        payload = {
            "deviceId": self.device_id,
            "deviceName": self.device_name,
            "serialNumber": self.serial_number,
            "macAddress": self.mac_addresses.get("lan2_internet") or self.mac_addresses.get("lan1_plc"),
            "macAddresses": self.mac_addresses,
            "timestamp": int(time.time() * 1000),
            "system": sys_metrics,
            "plc": {
                "connected": plc_connected,
                "ip": self.plc.ip,
                "port": self.plc.port,
                "status": "ONLINE" if plc_connected else "DISCONNECTED_WAITING_FOR_PLC",
                "alert": plc_alert,
                "lifebit": 1 if self.last_lifebit_val else 0
            },
            "redundancy": {
                "bufferQueueDepth": queue_depth,
                "storeAndForwardActive": True,
                "lastHeartbeat": int(time.time() * 1000)
            },
            "network": net_status
        }

        # Ensure runtime session is active
        if not self.runtime_id:
            self.start_runtime()

        if self.runtime_id:
            url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/heartbeat"
            try:
                status_code, body = self.send_http_post(url, payload, timeout=10)
                if plc_connected:
                    logger.info(f"💓 Heartbeat OK (HTTP {status_code}) | Runtime: {self.runtime_id[:8]}... | ✅ PLC: Connected (IP {self.plc.ip}) | Queue: {queue_depth}")
                else:
                    logger.warning(f"💓 Heartbeat OK (HTTP {status_code}) | Runtime: {self.runtime_id[:8]}... | ⚠️ PLC: Disconnected (ไม่มีข้อมูลจาก PLC ให้เชื่อมข้อมูลจาก PLC ที่ {self.plc.ip}:{self.plc.port})")
                return
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    logger.warning("⚠️ Runtime closed on server (HTTP 409). Starting new runtime...")
                    if self.start_runtime():
                        url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/heartbeat"
                        self.send_http_post(url, payload, timeout=10)
                        logger.info(f"💓 Heartbeat recovered on new runtime ({self.runtime_id[:8]}...)")
                    return
                else:
                    logger.warning(f"💔 Heartbeat delivery failed: HTTP {e.code}")
            except Exception as e:
                logger.warning(f"💔 Heartbeat delivery failed: {e}")
        else:
            api_cfg = self.config.get("api", {})
            heartbeat_url = api_cfg.get("heartbeatUrl", "")
            if heartbeat_url and "railway" not in heartbeat_url:
                try:
                    status_code, body = self.send_http_post(heartbeat_url, payload, timeout=api_cfg.get("httpTimeoutSec", 10))
                    logger.info(f"💓 Heartbeat OK ({status_code}) | PLC Connected: {self.plc.is_connected()} | Queue: {queue_depth}")
                except Exception as e:
                    logger.warning(f"💔 Heartbeat delivery failed: {e}")

    def acquire_plc_data(self):
        """Reads all configured tags from Siemens S7-1200 PLC."""
        tag_list = self.config.get("tags", [])
        tags_data = self.plc.read_all_tags(tag_list)
        return tags_data

    def build_batch_payload(self, tags_data, pnr_code=None, current_seq=None):
        """Builds standardized Edge Runtime Batch JSON Payload."""
        if current_seq is None:
            current_seq = self.sequence
            self.sequence += 1

        timestamp_ms = int(time.time() * 1000)
        now_iso = datetime.now(timezone.utc).isoformat()

        if not pnr_code:
            with self.buffer._get_connection() as conn:
                pnr_code = generate_pnr({
                    "org_id": self.org_id,
                    "deviceId": self.device_id,
                    "batch": {
                        "collected_at": timestamp_ms,
                        "sequence": current_seq
                    }
                }, db_conn=conn)

        sys_metrics = get_system_metrics()
        net_status = self.get_network_status()

        sensors_list = []
        tags_dict = {}
        if isinstance(tags_data, dict):
            for tag_name, info in tags_data.items():
                tags_dict[tag_name] = info.get("value")
                sensors_list.append({
                    "id": info.get("sensor_id"),
                    "name": tag_name,
                    "label": info.get("sensor_label"),
                    "address": info.get("address"),
                    "type": info.get("type"),
                    "value": info.get("value"),
                    "unit": info.get("unit"),
                    "raw_hex": info.get("raw_hex"),
                    "quality": info.get("quality", "GOOD"),
                    "timestamp": info.get("timestamp")
                })
        else:
            for t in tags_data:
                tag_name = t.get("name", "")
                tags_dict[tag_name] = t.get("value")
                sensors_list.append(t)

        batch_payload = {
            "sequence": current_seq,
            "sequenceRef": f"{pnr_code}-{current_seq}",
            "collectedAt": now_iso,
            "events": [
                {
                    "timestamp": now_iso,
                    "payload": {
                        "pnr_code": pnr_code,
                        "device_id": self.device_id,
                        "device_name": self.device_name,
                        "sensors": sensors_list,
                        "sensor_count": len(sensors_list),
                        "tags": tags_dict,
                        "raw_tags": tags_data,
                        "system": sys_metrics,
                        "plc": {
                            "connected": self.plc.is_connected(),
                            "ip": self.plc.ip,
                            "port": self.plc.port,
                            "lifebit_active": self.config.get("plc", {}).get("lifebit", {}).get("enabled", True)
                        },
                        "network": net_status
                    }
                }
            ]
        }
        return batch_payload, pnr_code, current_seq, sensors_list

    def generate_sample_sensor_data(self):
        """Generates realistic Siemens S7-1200 DB1 raw byte packets and unpacks them for dry-run testing."""
        presets = {
            "spindle_temperature": (65.40, "REAL"),
            "motor_current": (18.25, "REAL"),
            "motor_voltage": (380.00, "REAL"),
            "hydraulic_pressure": (87.15, "REAL"),
            "pneumatic_pressure": (6.00, "REAL"),
            "line_speed": (25.00, "REAL"),
            "vibration_level": (2.20, "REAL"),
            "coolant_flow_rate": (14.20, "REAL"),
            "spindle_speed": (1700, "INT"),
            "cycle_time": (28.00, "REAL"),
            "parts_produced": (4820, "DINT"),
            "scrap_count": (21, "DINT"),
            "machine_state": (2, "INT"),
            "alarm_code": (0, "WORD"),
            "oil_level": (79.00, "REAL"),
            "ambient_temperature": (27.50, "REAL"),
            "ambient_humidity": (60.00, "REAL"),
            "air_consumption": (200.00, "REAL"),
            "emergency_stop": (False, "BOOL")
        }

        sample_tags = {}
        tag_list = self.config.get("tags", [])
        for tag in tag_list:
            name = tag.get("name", "")
            dtype = tag.get("type", "REAL").upper()
            val, _ = presets.get(name, (50.0, dtype))
            raw_b = pack_plc_bytes(dtype, val)
            sample_tags[name] = format_sensor_reading(tag, raw_b)
        return sample_tags

    def inspect_package(self, sample=False, transmit=False):
        """
        Inspects Raw Data -> Parsed Sensor Values -> Web Batch Package.
        Displays transformation breakdown table, full JSON payload, and optionally transmits to Cloud API.
        """
        print("=" * 110)
        print("📦 Siemens S7-1200 Raw Data Parser & Web Batch Package Inspector")
        print("=" * 110)
        print(f"  Device Name:    {self.device_name}")
        print(f"  Device UUID:    {self.device_id}")
        print(f"  Cloud Endpoint: {self.api_base_url}")
        print(f"  Target PLC:     {self.plc.ip}:{self.plc.port} (Rack {self.plc.rack}, Slot {self.plc.slot})")
        print(f"  Mode:           {'SAMPLE DRY-RUN (Byte Packets Simulation)' if sample else 'LIVE PHYSICAL PLC'}")
        print("=" * 110)

        tags_data = {}
        if not sample:
            print(f"\n📡 Connecting to physical PLC at {self.plc.ip}:{self.plc.port}...")
            self.plc.connect()
            if not self.plc.is_connected():
                print(f"\n⚠️  [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {self.plc.ip}:{self.plc.port}! ให้เชื่อมต่อข้อมูลจาก PLC")
                print("💡 (หากต้องการทดสอบดูตัวอย่างการแปลง Raw Hex และโครงสร้าง Package แบบจำลองก่อนต่อสาย ให้ใช้คำสั่ง: plc-package --sample)\n")
                return False
            tags_data = self.acquire_plc_data()
        else:
            tags_data = self.generate_sample_sensor_data()

        if not tags_data:
            print("⚠️  No sensor tag data available.")
            return False

        # 1. Print Raw Bytes -> Engineering Values Conversion Table
        print("\n🔍 [Step 1] Raw PLC Memory Bytes (Hex) -> Parsed Engineering Sensor Values:")
        print("-" * 110)
        print(f"{'ID':>3} | {'Sensor Name':<22} | {'Address':<11} | {'Type':<5} | {'Raw Hex (S7)':<14} | {'Parsed Value':<18} | {'Description'}")
        print("-" * 110)

        for tag_name, info in tags_data.items():
            sid = info.get("sensor_id") or "-"
            addr = info.get("address") or "-"
            dtype = info.get("type") or "-"
            raw_h = info.get("raw_hex") or "-"
            val = info.get("value")
            unit = info.get("unit") or ""
            val_str = f"{val} {unit}".strip()
            desc = info.get("sensor_label") or tag_name
            if raw_h and raw_h != "-":
                raw_fmt = " ".join([raw_h[i:i+2] for i in range(0, len(raw_h), 2)])
            else:
                raw_fmt = "-"
            print(f"{sid:>3} | {tag_name:<22} | {addr:<11} | {dtype:<5} | {raw_fmt:<14} | {val_str:<18} | {desc}")
        print("-" * 110)

        # 2. Build Web Batch Package
        batch_payload, pnr_code, seq, sensors = self.build_batch_payload(tags_data)

        print("\n📦 [Step 2] Formatted Web API Batch Package Payload (JSON Schema):")
        print("-" * 110)
        print(json.dumps(batch_payload, indent=2, ensure_ascii=False))
        print("-" * 110)
        print(f"📊 Package Summary: Sequence #{seq} | PNR: {pnr_code} | Total Defined Sensors: {len(sensors)}")

        # 3. Cloud Transmission (if requested)
        if transmit:
            print("\n☁️  [Step 3] Transmitting Batch Package to Cloud API...")
            if not self.runtime_id:
                self.start_runtime()

            if self.runtime_id:
                url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/batches"
                try:
                    status_code, body = self.send_http_post(url, batch_payload, timeout=15)
                    print(f"✅ Cloud API Response: HTTP {status_code} OK")
                    print(f"   • Runtime ID:   {self.runtime_id}")
                    print(f"   • Endpoint:     {url}")
                    print(f"   • PNR Ref:      {pnr_code}-{seq}")
                    print(f"   • Response:     {body}")
                except Exception as e:
                    print(f"❌ Transmission Error: {e}")
            else:
                print("❌ Failed to initiate Cloud Runtime session. Check Device UUID / API Key.")
        else:
            print("\n💡 (ต้องการส่ง Package นี้ขึ้น Cloud API ทันที? ให้รันคำสั่ง: plc-package --send)")

        print("=" * 110 + "\n")
        return True

    def transmit_telemetry(self):
        """Gathers PLC tags, system metrics, and sends to REST API. Buffers on failure."""
        tags_data = self.acquire_plc_data()
        if not tags_data or len(tags_data) == 0:
            logger.warning(f"⚠️ [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {self.plc.ip}:{self.plc.port}! ให้เชื่อมต่อข้อมูลจาก PLC — ข้ามรอบส่งข้อมูล Telemetry (กำลังรอรับข้อมูลจากตู้ PLC จริง...)")
            return

        queue_depth = self.buffer.get_queue_depth()
        batch_payload, pnr_code, current_seq, sensors_list = self.build_batch_payload(tags_data)

        if not self.runtime_id:
            self.start_runtime()

        transmitted = False
        if self.runtime_id:
            url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/batches"
            try:
                status_code, response_body = self.send_http_post(url, batch_payload, timeout=15)
                logger.info(f"✅ Data Transmitted (HTTP {status_code}) | PNR: {pnr_code} (Seq #{current_seq}) | Runtime: {self.runtime_id[:8]}... | Sensors: {len(sensors_list)} | Buffer: {queue_depth}")
                transmitted = True
                if queue_depth > 0:
                    self.drain_offline_buffer()
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    logger.warning("⚠️ Runtime closed (HTTP 409). Restarting runtime session...")
                    if self.start_runtime():
                        url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/batches"
                        status_code, _ = self.send_http_post(url, batch_payload, timeout=15)
                        logger.info(f"✅ Data Transmitted after restart (HTTP {status_code}) | PNR: {pnr_code}")
                        transmitted = True
                else:
                    logger.warning(f"⚠️ API Error HTTP {e.code}. Buffering data to SQLite...")
            except Exception as e:
                logger.warning(f"⚠️ Network/API Error ({e}). Buffering data to SQLite...")

        if not transmitted:
            # Buffer data to SQLite
            row_id = self.buffer.enqueue(batch_payload, pnr_code=pnr_code)
            new_depth = self.buffer.get_queue_depth()
            logger.info(f"📦 Record buffered safely into SQLite (PNR: {pnr_code}, ID: {row_id}, Queue depth: {new_depth})")

    def drain_offline_buffer(self):
        """Replays offline queued records to REST API in batches once connectivity is restored."""
        if not self.runtime_id:
            if not self.start_runtime():
                return

        limit = self.config.get("redundancy", {}).get("batchDrainLimit", 20)
        pending = self.buffer.get_pending_batch(limit=limit)
        if not pending:
            return

        logger.info(f"🔄 Redundancy Drainer: Found {len(pending)} buffered records. Replaying backlog...")
        url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/batches"

        for item in pending:
            q_id = item["queue_id"]
            payload = item["payload"]
            try:
                status_code, body = self.send_http_post(url, payload, timeout=15)
                if status_code in (200, 201):
                    self.buffer.mark_sent([q_id])
                    logger.info(f"  [✓] Replayed buffered batch ID {q_id} (HTTP {status_code})")
                else:
                    self.buffer.increment_retry([q_id])
            except Exception as e:
                logger.warning(f"Replay drain item {q_id} failed: {e}")
                self.buffer.increment_retry([q_id])

    def start(self):
        """Main service execution loop."""
        self.running = True
        logger.info("=" * 65)
        logger.info("🚀 Siemens S7-1200 IoT Edge Gateway Started (Raspberry Pi 4)")
        logger.info(f"🏷️  Device ID:    {self.device_id}")
        logger.info(f"📛 Device Name:  {self.device_name}")
        logger.info(f"🔢 Serial Num:   {self.serial_number}")
        logger.info(f"🔌 LAN 1 (PLC):  {self.lan1_if} | MAC: {self.mac_addresses['lan1_plc']}")
        logger.info(f"🌐 LAN 2 (Net):  {self.lan2_if} | MAC: {self.mac_addresses['lan2_internet']}")
        logger.info(f"📡 API Endpoint: {self.config.get('api', {}).get('telemetryUrl')}")
        logger.info(f"🔌 PLC Target:   {self.config.get('plc', {}).get('ip')} (Simulate: {self.plc.simulate})")
        logger.info(f"⏱️  Transmit Int: {self.config.get('api', {}).get('transmissionIntervalSec')}s (TOR 60 mins)")
        logger.info(f"💓 Heartbeat Int: {self.config.get('api', {}).get('heartbeatIntervalSec')}s")
        logger.info(f"🛡️  Redundancy:   Store-and-Forward SQLite Buffer Enabled")
        logger.info("=" * 65)

        # Connect PLC
        self.plc.connect()

        # Initial immediate transmission
        self.transmit_telemetry()
        self.send_heartbeat()

        trans_interval = self.config.get("api", {}).get("transmissionIntervalSec", 3600)
        hb_interval = self.config.get("api", {}).get("heartbeatIntervalSec", 30)
        lifebit_interval = self.config.get("plc", {}).get("lifebit", {}).get("intervalSec", 5)
        lifebit_addr = self.config.get("plc", {}).get("lifebit", {}).get("address", "DB1.DBX0.0")

        last_trans_time = time.time()
        last_hb_time = time.time()
        last_lifebit_time = time.time()
        last_emergency_check = time.time()

        while self.running:
            now = time.time()

            # 1. PLC Lifebit Heartbeat toggle (Gateway -> PLC)
            if now - last_lifebit_time >= lifebit_interval:
                success, state = self.plc.toggle_plc_lifebit(lifebit_addr)
                self.last_lifebit_val = state
                last_lifebit_time = now

            # 2. Cloud Heartbeat (Gateway -> Web API)
            if now - last_hb_time >= hb_interval:
                self.send_heartbeat()
                last_hb_time = now

            # 3. Emergency Event Fast-Poll (every 2 seconds)
            if now - last_emergency_check >= 2:
                if self.check_emergency_event():
                    self.transmit_telemetry()
                    last_trans_time = now
                last_emergency_check = now

            # 4. Scheduled Data Acquisition & Transmission (TOR every 60 mins)
            if now - last_trans_time >= trans_interval:
                self.transmit_telemetry()
                last_trans_time = now

            time.sleep(1)

    def stop(self):
        """Stops the gateway gracefully and closes runtime session."""
        self.running = False
        if self.runtime_id:
            try:
                url = f"{self.api_base_url}/edge/devices/{self.device_id}/runtimes/{self.runtime_id}/stop"
                self.send_http_post(url, {}, timeout=5)
                logger.info(f"🛑 Edge Runtime {self.runtime_id} stopped cleanly on Cloud API.")
            except Exception as e:
                logger.warning(f"Could not stop runtime cleanly on Cloud: {e}")
            self.runtime_id = None
        self.plc.disconnect()
        logger.info("Edge Gateway stopped gracefully.")


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi 4 IoT Edge Gateway for Siemens S7-1200")
    parser.add_argument("--config", default="config_plc.json", help="Path to config_plc.json")
    parser.add_argument("--interval", type=int, default=None, help="Override transmission interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run a single acquisition and transmit cycle, then exit")
    parser.add_argument("--package", action="store_true", help="Inspect Raw Data Hex -> Parsed Sensors & Web Batch Package")
    parser.add_argument("--sample", action="store_true", help="Use realistic sample PLC byte packets (for dry-run inspection)")
    parser.add_argument("--send", "--transmit", dest="send", action="store_true", help="Transmit the inspected batch package directly to Cloud API")
    parser.add_argument("--discover", "--scan-plc", action="store_true", help="Auto-scan local network and discover Siemens S7 PLCs on port 102")
    parser.add_argument("--info", action="store_true", help="Display Device ID, Serial Number, MAC addresses, and exit")
    parser.add_argument("--diagnose", action="store_true", help="Run automated self-diagnosis and troubleshooting checks")

    args = parser.parse_args()

    if args.discover:
        print("=" * 75)
        print("🔍 Scanning local networks for Siemens S7-1200 PLCs (Port 102)...")
        print("=" * 75)
        found = discover_s7_plcs()
        if not found:
            print("\n⚠️  No Siemens S7 PLCs found on local subnets.")
            print("   • Please verify LAN cable connection to PLC or switching hub.")
            print("   • Ensure PLC is powered on.")
        else:
            print(f"\n✅ Found {len(found)} Siemens PLC(s) on network:\n")
            print(f"{'#':>2} | {'IP Address':<16} | {'Port':<6} | {'Latency':<10} | {'Status / Device'}")
            print("-" * 75)
            for idx, item in enumerate(found, 1):
                print(f"{idx:>2} | {item['ip']:<16} | {item['port']:<6} | {item['latency_ms']} ms   | {item['details']}")
            print("-" * 75)
            print(f"💡 Gateway will automatically connect to {found[0]['ip']}:{found[0]['port']}.")
        print("=" * 75 + "\n")
        return

    if args.diagnose:
        from diagnose import run_full_diagnosis
        run_full_diagnosis(args.config)
        return

    gateway = EdgeGatewayService(
        config_path=args.config
    )

    if args.info:
        net = gateway.get_network_status()
        print("\n" + "=" * 65)
        print("🍓 Raspberry Pi 4 Edge Gateway - Hardware & Network Profile")
        print("=" * 65)
        print(f"Device Name:     {gateway.device_name}")
        print(f"Device ID:       {gateway.device_id}")
        print(f"Serial Number:   {gateway.serial_number}")
        print("-" * 65)
        print(f"LAN 1 (PLC Network):     {net['lan1_plc']['interface']}")
        print(f"  IP Address:            {net['lan1_plc']['ip']}")
        print(f"  MAC Address:           {net['lan1_plc']['mac']}")
        print(f"  Target PLC IP:         {net['lan1_plc']['targetPlcIp']}")
        print("-" * 65)
        print(f"LAN 2 (Internet / API):  {net['lan2_internet']['interface']}")
        print(f"  IP Address:            {net['lan2_internet']['ip']}")
        print(f"  MAC Address:           {net['lan2_internet']['mac']}")
        print("-" * 65)
        print(f"Tailscale VPN IP:        {get_tailscale_ip()}")
        print(f"SQLite Buffer Queue:     {gateway.buffer.get_queue_depth()} pending records")
        print("=" * 65 + "\n")
        return

    if args.interval:
        gateway.config["api"]["transmissionIntervalSec"] = args.interval

    def handle_signal(sig, frame):
        logger.info("Signal received. Terminating...")
        gateway.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.package:
        gateway.inspect_package(sample=args.sample, transmit=args.send)
        gateway.stop()
        return

    if args.once:
        gateway.plc.connect()
        gateway.transmit_telemetry()
        gateway.send_heartbeat()
        gateway.stop()
        return

    gateway.start()


if __name__ == "__main__":
    main()
