#!/usr/bin/env bash
#!/usr/bin/env python3
"""
Siemens S7-1200 PLC Communication Driver (Production Physical Mode)
Connects directly to Siemens S7-1200 PLC via S7comm protocol (TCP Port 102).
Simulation mode is completely disabled — only real physical PLC data is accepted.
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

            # Unpack by data type
            if data_type == "BOOL":
                val = bool(get_bool(raw_bytes, 0, parsed["bit"]))
            elif data_type == "REAL":
                val = round(get_real(raw_bytes, 0), 2)
            elif data_type == "INT":
                val = get_int(raw_bytes, 0)
            elif data_type == "WORD":
                val = struct.unpack(">H", raw_bytes[:2])[0]
            elif data_type == "DINT":
                val = get_dint(raw_bytes, 0)
            elif data_type == "DWORD":
                val = struct.unpack(">I", raw_bytes[:4])[0]
            elif data_type == "STRING":
                val = get_string(raw_bytes, 0)
            else:
                val = round(get_real(raw_bytes, 0), 2)

            return {
                "name": name,
                "address": address,
                "type": data_type,
                "value": val,
                "unit": tag_config.get("unit", ""),
                "quality": "GOOD",
                "timestamp": int(time.time() * 1000)
            }
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
