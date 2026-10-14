#!/usr/bin/env python3
"""
Siemens S7-1200 PLC Communication Driver (Production Physical Mode)
Connects directly to Siemens S7-1200 PLC via S7comm protocol (TCP Port 102).
Converts raw PLC memory bytes (Big-Endian) into engineering sensor values.
Simulation mode is completely disabled on gateway — only real physical PLC data is accepted.
"""

import time
import struct
import logging
import re
import socket
import concurrent.futures

logger = logging.getLogger("PLCDriver")

# Check if snap7 is installed
try:
    import snap7
    from snap7.util import get_bool, get_int, get_real, get_dint, get_string, set_bool
    from snap7.snap7types import Areas
    HAS_SNAP7 = True
except ImportError:
    HAS_SNAP7 = False


def unpack_plc_bytes(raw_bytes, data_type="REAL", bit=0):
    """
    Converts raw Siemens S7 Big-Endian memory bytes into human-readable engineering values.
    Supports REAL (Float32), DINT (Int32), DWORD (UInt32), INT (Int16), WORD (UInt16), BOOL, and STRING.
    """
    if not raw_bytes:
        return None
    data_type = str(data_type).upper()
    try:
        if data_type == "REAL":
            # IEEE 754 32-bit single precision float (Big-Endian)
            return round(struct.unpack(">f", raw_bytes[:4])[0], 2)
        elif data_type == "DINT":
            # 32-bit signed integer
            return struct.unpack(">i", raw_bytes[:4])[0]
        elif data_type == "DWORD":
            # 32-bit unsigned integer
            return struct.unpack(">I", raw_bytes[:4])[0]
        elif data_type == "INT":
            # 16-bit signed integer
            return struct.unpack(">h", raw_bytes[:2])[0]
        elif data_type == "WORD":
            # 16-bit unsigned integer
            return struct.unpack(">H", raw_bytes[:2])[0]
        elif data_type == "BOOL":
            # Bit extraction: bit 0 to 7 of first byte
            byte_val = raw_bytes[0]
            return bool((byte_val >> bit) & 1)
        elif data_type == "STRING":
            # Siemens S7 String layout: [0]=max_len, [1]=actual_len, [2..]=characters
            if len(raw_bytes) >= 2:
                actual_len = raw_bytes[1]
                return raw_bytes[2:2 + actual_len].decode("latin1", errors="replace")
            return raw_bytes.decode("latin1", errors="replace")
        else:
            return round(struct.unpack(">f", raw_bytes[:4])[0], 2)
    except Exception as e:
        logger.warning(f"Failed to unpack {data_type} bytes {raw_bytes.hex()}: {e}")
        return None


def pack_plc_bytes(data_type, value, bit=0):
    """
    Packs engineering value into Siemens S7 Big-Endian bytes.
    Useful for testing, dry-runs, and simulating realistic PLC memory packets.
    """
    data_type = str(data_type).upper()
    try:
        if data_type == "REAL":
            return struct.pack(">f", float(value))
        elif data_type == "DINT":
            return struct.pack(">i", int(value))
        elif data_type == "DWORD":
            return struct.pack(">I", int(value))
        elif data_type == "INT":
            return struct.pack(">h", int(value))
        elif data_type == "WORD":
            return struct.pack(">H", int(value))
        elif data_type == "BOOL":
            val_bit = 1 if bool(value) else 0
            return bytes([val_bit << bit])
        elif data_type == "STRING":
            s_bytes = str(value).encode("latin1", errors="replace")
            max_len = 254
            act_len = len(s_bytes)
            return bytes([max_len, act_len]) + s_bytes
        else:
            return struct.pack(">f", float(value))
    except Exception as e:
        logger.warning(f"Failed to pack {data_type} value '{value}': {e}")
        return b"\x00\x00\x00\x00"


def format_sensor_reading(tag_config, raw_bytes, parsed_address=None):
    """
    Transforms raw memory bytes into an enriched sensor record with full metadata.
    """
    name = tag_config.get("name", tag_config.get("address", "unknown"))
    data_type = tag_config.get("type", "REAL").upper()
    address = tag_config.get("address", "")
    bit = 0
    if parsed_address:
        bit = parsed_address.get("bit", 0)

    val = unpack_plc_bytes(raw_bytes, data_type, bit=bit)
    raw_hex = raw_bytes.hex().upper() if raw_bytes else ""

    return {
        "sensor_id": tag_config.get("id"),
        "sensor_name": name,
        "sensor_label": tag_config.get("desc", name),
        "address": address,
        "type": data_type,
        "value": val,
        "unit": tag_config.get("unit", ""),
        "raw_hex": raw_hex,
        "quality": "GOOD" if val is not None else "BAD",
        "timestamp": int(time.time() * 1000)
    }



def probe_s7_plc(ip, port=102, timeout=0.25):
    """
    Actively probes target IP on Port 102 using ISO-on-TCP (COTP) Connection Request packet.
    If the remote device is a Siemens S7 PLC, it responds with a COTP Connection Confirm packet (0x03 0x00 ... 0xD0).
    Returns (is_plc, latency_ms, details).
    """
    cotp_cr = bytes([
        0x03, 0x00, 0x00, 0x16,  # TPKT Header (Version 3, length 22)
        0x11,                    # COTP Length 17
        0xe0,                    # COTP CR PDU type
        0x00, 0x00,              # Destination reference
        0x00, 0x01,              # Source reference
        0x00,                    # Class 0
        0xc1, 0x02, 0x01, 0x00,  # Calling TSAP
        0xc2, 0x02, 0x01, 0x02,  # Called TSAP (Rack 0, Slot 1)
        0xc0, 0x01, 0x0a         # TPDU size 1024
    ])

    start_time = time.time()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.sendall(cotp_cr)
        resp = s.recv(1024)
        latency_ms = round((time.time() - start_time) * 1000, 1)
        s.close()

        if len(resp) >= 6 and resp[0] == 0x03 and resp[1] == 0x00 and resp[5] == 0xd0:
            return True, latency_ms, "Siemens S7 PLC (COTP Verified)"
        elif len(resp) >= 4 and resp[0] == 0x03 and resp[1] == 0x00:
            return True, latency_ms, "Siemens S7comm Compatible Device"
        else:
            return True, latency_ms, "Port 102 Open (ISO-TSAP)"
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False, 0.0, None


def get_discovery_subnets(extra_subnets=None):
    """
    Collects candidate subnets from local network interfaces + standard industrial subnets.
    """
    subnets = set()
    # Standard Siemens PLC subnets
    subnets.add("192.168.2")
    subnets.add("192.168.0")
    subnets.add("192.168.1")

    # Local active socket interface
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        parts = local_ip.split(".")
        if len(parts) == 4 and not parts[0].startswith("127"):
            subnets.add(f"{parts[0]}.{parts[1]}.{parts[2]}")
    except Exception:
        pass

    # Read from hostname -I on Linux
    try:
        import subprocess
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=1)
        if out.returncode == 0:
            for ip in out.stdout.split():
                parts = ip.strip().split(".")
                if len(parts) == 4 and not parts[0].startswith("127"):
                    subnets.add(f"{parts[0]}.{parts[1]}.{parts[2]}")
    except Exception:
        pass

    if extra_subnets:
        for s in extra_subnets:
            subnets.add(s.strip())

    return list(subnets)


def discover_s7_plcs(target_subnets=None, port=102, timeout=0.25, max_workers=64):
    """
    Scans local networks concurrently for Siemens S7 PLCs on TCP Port 102.
    Returns list of discovered PLCs: [{"ip": ..., "port": ..., "latency_ms": ..., "details": ...}].
    """
    subnets = target_subnets or get_discovery_subnets()
    priority_ips = [
        "192.168.2.2",   # Primary physical target in project
        "192.168.0.1",   # Siemens factory default IP
        "192.168.0.2",
        "192.168.0.10",
        "192.168.1.1",
        "192.168.1.2",
        "192.168.1.10",
        "192.168.2.1",
        "192.168.2.10"
    ]

    all_ips = []
    for ip in priority_ips:
        if ip not in all_ips:
            all_ips.append(ip)

    for sn in subnets:
        for host in range(1, 255):
            candidate = f"{sn}.{host}"
            if candidate not in all_ips:
                all_ips.append(candidate)

    discovered = []

    def _worker(candidate_ip):
        ok, lat, desc = probe_s7_plc(candidate_ip, port=port, timeout=timeout)
        if ok:
            return {"ip": candidate_ip, "port": port, "latency_ms": lat, "details": desc}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, ip): ip for ip in all_ips}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                discovered.append(res)

    discovered.sort(key=lambda x: x["latency_ms"])
    return discovered


class S7PLCClient:
    def __init__(self, ip="192.168.2.2", rack=0, slot=1, port=102, auto_discover=True, simulate=False):
        self.configured_ip = ip
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.port = port or 102
        self.auto_discover = auto_discover
        self.simulate = False  # Simulation completely disabled
        self.client = None
        self.connected = False
        self.last_lifebit_state = False

        if not HAS_SNAP7:
            logger.error("❌ ไม่พบไลบรารี python-snap7 ในระบบ! กรุณาติดตั้ง snap7 เพื่อเชื่อมต่อตู้ PLC จริง")

    def connect(self):
        """Establishes connection to physical Siemens S7-1200 PLC with Auto-Discovery support."""
        if not HAS_SNAP7:
            self.connected = False
            return False

        is_auto_mode = str(self.ip).strip().lower() in ("auto", "detect", "discover", "scan", "")

        # 1. If in auto mode, scan network to find PLC automatically
        if is_auto_mode:
            logger.info("🔍 [Auto-Discovery] กำลังสแกนหาตู้ Siemens S7 PLC บนเครือข่ายอัตโนมัติ...")
            found_plcs = discover_s7_plcs()
            if found_plcs:
                best = found_plcs[0]
                self.ip = best["ip"]
                self.port = best["port"]
                logger.info(f"✨ [Auto-Discovery] ตรวจพบตู้ Siemens S7 PLC อัตโนมัติที่ IP {self.ip}:{self.port} (Latency: {best['latency_ms']}ms, {best['details']})!")
            else:
                logger.warning("⚠️ [Auto-Discovery] ไม่พบตู้ Siemens S7 PLC บนเครือข่าย! กรุณาตรวจสอบสาย LAN หรือเปิดตู้ PLC")
                self.connected = False
                return False

        # 2. Try direct connection to self.ip
        try:
            if not self.client:
                self.client = snap7.client.Client()
            if not self.client.get_connected():
                self.client.connect(self.ip, self.rack, self.slot, self.port)
            self.connected = self.client.get_connected()
            if self.connected:
                logger.info(f"✅ เชื่อมต่อตู้ PLC S7-1200 สำเร็จที่ {self.ip}:{self.port} (Rack: {self.rack}, Slot: {self.slot})")
                return True
        except Exception:
            self.connected = False

        # 3. If failed and auto_discover is enabled, search for online S7 PLC on network
        if not self.connected and self.auto_discover:
            logger.info(f"🔄 ไม่สามารถติดต่อ IP เดิม ({self.ip}:{self.port}) ได้ — กำลังสแกนหาตู้ PLC Siemens บนวง LAN อัตโนมัติ...")
            found_plcs = discover_s7_plcs()
            alternate_plcs = [p for p in found_plcs if p["ip"] != self.ip]
            if alternate_plcs:
                best = alternate_plcs[0]
                old_ip = self.ip
                self.ip = best["ip"]
                self.port = best["port"]
                logger.info(f"✨ [Auto-Discovery] ตรวจพบตู้ PLC Siemens อัตโนมัติที่ {self.ip}:{self.port} (Latency: {best['latency_ms']}ms)! สลับการเชื่อมต่อไปยัง IP นี้ทันที...")
                try:
                    self.client.connect(self.ip, self.rack, self.slot, self.port)
                    self.connected = self.client.get_connected()
                    if self.connected:
                        logger.info(f"✅ เชื่อมต่อตู้ PLC สำเร็จผ่าน Auto-Discovery ที่ {self.ip}:{self.port} (สลับอัตโนมัติจาก {old_ip})")
                        return True
                except Exception as ex:
                    logger.warning(f"⚠️ พยายามเชื่อมต่อ PLC ที่ตรวจพบอัตโนมัติ {self.ip} ไม่สำเร็จ: {ex}")

        if not self.connected:
            logger.warning(f"⚠️ [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {self.ip}:{self.port}! ให้เชื่อมต่อข้อมูลจาก PLC")
        return self.connected

    def disconnect(self):
        """Disconnects from PLC."""
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.connected = False

    def is_connected(self):
        """Checks real connection status."""
        if self.client:
            try:
                return self.client.get_connected()
            except Exception:
                return False
        return False

    def parse_address(self, address_str):
        """
        Parses Siemens address strings like:
        - DB1.DBD0   (DB 1, Double Word offset 0 -> Real or DInt)
        - DB1.DBW4   (DB 1, Word offset 4 -> Int or Word)
        - DB1.DBX12.0 (DB 1, Bit offset 12, bit 0 -> Bool)
        - MW100      (Memory Word 100)
        - M0.0       (Memory Bit 0.0)
        """
        addr = address_str.strip().upper()

        # DB Bit: DB1.DBX10.2
        m = re.match(r"^DB(\d+)\.DBX(\d+)\.([0-7])$", addr)
        if m:
            return {"area": "DB", "db": int(m.group(1)), "start": int(m.group(2)), "bit": int(m.group(3)), "size": 1}

        # DB Byte / Word / DWord: DB1.DBB0, DB1.DBW4, DB1.DBD8
        m = re.match(r"^DB(\d+)\.DB([BWD])(\d+)$", addr)
        if m:
            db = int(m.group(1))
            dtype = m.group(2)
            start = int(m.group(3))
            size = 1 if dtype == "B" else (2 if dtype == "W" else 4)
            return {"area": "DB", "db": db, "start": start, "bit": 0, "size": size}

        # Memory Bit: M10.2
        m = re.match(r"^M(\d+)\.([0-7])$", addr)
        if m:
            return {"area": "M", "db": 0, "start": int(m.group(1)), "bit": int(m.group(2)), "size": 1}

        # Memory Word: MW100, MD100
        m = re.match(r"^M([BWD])(\d+)$", addr)
        if m:
            dtype = m.group(1)
            start = int(m.group(2))
            size = 1 if dtype == "B" else (2 if dtype == "W" else 4)
            return {"area": "M", "db": 0, "start": start, "bit": 0, "size": size}

        return None

    def read_tag(self, tag_config):
        """Reads a single tag from physical Siemens S7-1200."""
        address = tag_config.get("address", "")
        data_type = tag_config.get("type", "REAL").upper()
        name = tag_config.get("name", address)

        if not self.is_connected():
            self.connect()
            if not self.is_connected():
                return None

        parsed = self.parse_address(address)
        if not parsed:
            logger.error(f"Invalid Siemens address syntax: {address}")
            return None

        try:
            area = Areas.DB if parsed["area"] == "DB" else Areas.MK
            db_number = parsed["db"]
            start = parsed["start"]
            size = parsed["size"]

            # Adjust read size for REAL / DINT / STRING
            if data_type in ("REAL", "DINT", "DWORD"):
                size = max(size, 4)
            elif data_type in ("INT", "WORD"):
                size = max(size, 2)
            elif data_type == "STRING":
                size = tag_config.get("max_length", 254) + 2

            raw_bytes = self.client.read_area(area, db_number, start, size)
            return format_sensor_reading(tag_config, raw_bytes, parsed)
        except Exception as e:
            logger.warning(f"⚠️ [อ่านค่า Tag ไม่สำเร็จ] {name} ({address}): {e}")
            self.connected = False
            return None

    def read_all_tags(self, tag_list):
        """Reads multiple tags from physical PLC with Bulk Read Optimization."""
        if not self.is_connected():
            self.connect()
            if not self.is_connected():
                logger.warning(f"⚠️ [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {self.ip}:{self.port}! กรุณาเชื่อมต่อสาย LAN หรือเปิดตู้ PLC")
                return {}

        # 1. Check if all tags belong to the same DB and can be read in a single bulk block
        parsed_tags = []
        same_db = True
        target_db = None

        for tag_cfg in tag_list:
            addr = tag_cfg.get("address", "")
            p = self.parse_address(addr)
            if not p or p["area"] != "DB":
                same_db = False
                break
            if target_db is None:
                target_db = p["db"]
            elif p["db"] != target_db:
                same_db = False
                break

            dtype = tag_cfg.get("type", "REAL").upper()
            size = p["size"]
            if dtype in ("REAL", "DINT", "DWORD"):
                size = max(size, 4)
            elif dtype in ("INT", "WORD"):
                size = max(size, 2)
            parsed_tags.append((tag_cfg, p, size))

        if same_db and parsed_tags and self.client:
            min_start = min(p["start"] for _, p, _ in parsed_tags)
            max_end = max(p["start"] + size for _, p, size in parsed_tags)
            total_bytes = max_end - min_start

            # If contiguous block is within standard S7 PDU payload limit (<= 256 bytes)
            if min_start == 0 and total_bytes <= 256:
                try:
                    raw_block = self.client.read_area(Areas.DB, target_db, min_start, total_bytes)
                    if raw_block and len(raw_block) >= total_bytes:
                        results = {}
                        for tag_cfg, p, size in parsed_tags:
                            tag_name = tag_cfg.get("name", tag_cfg.get("address"))
                            offset = p["start"] - min_start
                            raw_slice = raw_block[offset : offset + size]
                            val_info = format_sensor_reading(tag_cfg, raw_slice, p)
                            if val_info:
                                results[tag_name] = val_info
                        return results
                except Exception as e:
                    logger.debug(f"Bulk read fallback: {e}")

        # 2. Fallback to individual tag reads
        results = {}
        for tag_cfg in tag_list:
            tag_name = tag_cfg.get("name", tag_cfg.get("address"))
            val_info = self.read_tag(tag_cfg)
            if val_info:
                results[tag_name] = val_info
        return results

    def toggle_plc_lifebit(self, lifebit_address="DB1.DBX0.0"):
        """Toggles PLC Lifebit for Heartbeat (Gateway -> PLC)."""
        self.last_lifebit_state = not self.last_lifebit_state
        new_state = self.last_lifebit_state

        if not self.is_connected():
            self.connect()
            if not self.is_connected():
                return False, new_state

        parsed = self.parse_address(lifebit_address)
        if not parsed or parsed["area"] != "DB":
            return False, new_state

        try:
            db_num = parsed["db"]
            start = parsed["start"]
            bit = parsed["bit"]

            raw = self.client.read_area(Areas.DB, db_num, start, 1)
            set_bool(raw, 0, bit, new_state)
            self.client.write_area(Areas.DB, db_num, start, raw)
            return True, new_state
        except Exception as e:
            logger.warning(f"Failed to toggle PLC Lifebit ({lifebit_address}): {e}")
            self.connected = False
            return False, new_state
