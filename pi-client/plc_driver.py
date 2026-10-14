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



class S7PLCClient:
    def __init__(self, ip="192.168.0.10", rack=0, slot=1, port=102, simulate=False):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.port = port
        self.simulate = False  # Simulation completely disabled
        self.client = None
        self.connected = False
        self.last_lifebit_state = False

        if not HAS_SNAP7:
            logger.error("❌ ไม่พบไลบรารี python-snap7 ในระบบ! กรุณาติดตั้ง snap7 เพื่อเชื่อมต่อตู้ PLC จริง")

    def connect(self):
        """Establishes connection to physical Siemens S7-1200 PLC."""
        if not HAS_SNAP7:
            self.connected = False
            return False

        try:
            if not self.client:
                self.client = snap7.client.Client()
            if not self.client.get_connected():
                self.client.connect(self.ip, self.rack, self.slot, self.port)
            self.connected = self.client.get_connected()
            if self.connected:
                logger.info(f"✅ เชื่อมต่อตู้ PLC S7-1200 สำเร็จที่ {self.ip}:{self.port} (Rack: {self.rack}, Slot: {self.slot})")
            else:
                logger.warning(f"⚠️ [ไม่พบการเชื่อมต่อ PLC] ไม่สามารถติดต่อตู้ PLC S7-1200 ที่ {self.ip}:{self.port} ได้ กรุณาตรวจสอบสาย LAN หรือเปิดตู้ PLC")
            return self.connected
        except Exception as e:
            self.connected = False
            logger.warning(f"⚠️ [ไม่พบการเชื่อมต่อ PLC] ไม่สามารถเชื่อมต่อกับตู้ PLC S7-1200 ที่ {self.ip}:{self.port} ({e}) กรุณาตรวจสอบสายสัญญาณ")
            return False

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
        """Reads multiple tags from physical PLC. If disconnected, returns empty dict."""
        if not self.is_connected():
            self.connect()
            if not self.is_connected():
                logger.warning(f"⚠️ [ไม่มีข้อมูลจาก PLC] ขาดการเชื่อมต่อกับตู้ PLC S7-1200 ที่ IP {self.ip}:{self.port}! กรุณาเชื่อมต่อสาย LAN หรือเปิดตู้ PLC")
                return {}

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
