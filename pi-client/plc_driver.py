#!/usr/bin/env python3
"""
Siemens S7-1200 PLC Communication Driver
Supports reading memory blocks (DB, M, I, Q) via S7comm protocol (port 102).
Uses python-snap7 when installed, and provides high-fidelity simulation mode
for testing without physical hardware (compliant with TOR Section 2.3).
"""

import time
import struct
import logging
import random
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
        self.simulate = simulate or (not HAS_SNAP7)
        self.client = None
        self.connected = False
        self.last_lifebit_state = False
        self._sim_data = {}

        if not HAS_SNAP7 and not simulate:
            logger.warning("python-snap7 not found on this system. Operating in SIMULATION mode.")
            self.simulate = True

    def connect(self):
        """Establishes connection to Siemens S7-1200 PLC."""
        if self.simulate:
            self.connected = True
            logger.info(f"Connected to SIMULATED S7-1200 PLC at {self.ip}")
            return True

        try:
            self.client = snap7.client.Client()
            self.client.connect(self.ip, self.rack, self.slot, self.port)
            self.connected = self.client.get_connected()
            if self.connected:
                logger.info(f"Connected to Siemens S7-1200 at {self.ip} (Rack: {self.rack}, Slot: {self.slot})")
            return self.connected
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to PLC at {self.ip}: {e}")
            return False

    def disconnect(self):
        """Disconnects from PLC."""
        if self.client and not self.simulate:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.connected = False

    def is_connected(self):
        """Checks connection status."""
        if self.simulate:
            return True
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
        """
        Reads a single tag defined by tag_config dictionary:
        {
          "name": "motor_temperature",
          "address": "DB1.DBD0",
          "type": "REAL",
          "unit": "°C"
        }
        """
        address = tag_config.get("address", "")
        data_type = tag_config.get("type", "REAL").upper()
        name = tag_config.get("name", address)

        if self.simulate:
            return self._read_simulated_tag(name, address, data_type, tag_config.get("unit", ""))

        parsed = self.parse_address(address)
        if not parsed:
            logger.error(f"Invalid Siemens address syntax: {address}")
            return None

        try:
            if not self.is_connected():
                self.connect()
                if not self.is_connected():
                    return None

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
                val = struct.unpack(">H", raw_bytes[:2])[0]

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
            logger.error(f"Error reading tag {name} ({address}): {e}")
            self.connected = False
            return {
                "name": name,
                "address": address,
                "type": data_type,
                "value": None,
                "unit": tag_config.get("unit", ""),
                "quality": "BAD",
                "error": str(e),
                "timestamp": int(time.time() * 1000)
            }

    def read_all_tags(self, tag_list):
        """Reads multiple tags and returns a structured dictionary."""
        results = {}
        for tag_cfg in tag_list:
            tag_name = tag_cfg.get("name", tag_cfg.get("address"))
            val_info = self.read_tag(tag_cfg)
            if val_info:
                results[tag_name] = val_info
        return results

    def toggle_plc_lifebit(self, lifebit_address="DB1.DBX0.0"):
        """
        Toggles PLC Lifebit for Heartbeat (Gateway -> PLC).
        Allows PLC Ladder Logic to detect if Gateway is running.
        """
        self.last_lifebit_state = not self.last_lifebit_state
        new_state = self.last_lifebit_state

        if self.simulate:
            return True, new_state

        parsed = self.parse_address(lifebit_address)
        if not parsed or parsed["area"] != "DB":
            return False, new_state

        try:
            if not self.is_connected():
                self.connect()

            # Read 1 byte, set bit, write back
            db_num = parsed["db"]
            start = parsed["start"]
            bit = parsed["bit"]

            raw = self.client.read_area(Areas.DB, db_num, start, 1)
            set_bool(raw, 0, bit, new_state)
            self.client.write_area(Areas.DB, db_num, start, raw)
            return True, new_state
        except Exception as e:
            logger.warning(f"Failed to toggle PLC Lifebit ({lifebit_address}): {e}")
            return False, new_state

    def _read_simulated_tag(self, name, address, data_type, unit):
        """Generates realistic industrial sensor and state values for simulation test."""
        now = time.time()
        # Seed pseudo-random variations with continuity
        if name not in self._sim_data:
            self._sim_data[name] = {
                "val": 50.0,
                "step": 0.5,
                "min": 10.0,
                "max": 100.0,
                "counter": 1250
            }

        sim = self._sim_data[name]

        if data_type == "BOOL":
            val = True if (int(now / 30) % 2 == 0) else False
        elif "TEMP" in name.upper() or unit == "°C":
            # Realistic temperature fluctuation 60°C - 75°C
            val = round(65.0 + 5.0 * (random.uniform(-1.0, 1.0)), 2)
        elif "PRESSURE" in name.upper() or unit == "bar":
            # Realistic hydraulic/pneumatic pressure 110 - 130 bar
            val = round(120.0 + random.uniform(-4.0, 4.0), 2)
        elif "SPEED" in name.upper() or "RPM" in unit.upper() or "M/MIN" in unit.upper():
            # Line speed / spindle RPM
            val = round(45.0 + random.uniform(-1.5, 1.5), 1)
        elif "CURRENT" in name.upper() or unit == "A":
            val = round(14.2 + random.uniform(-0.8, 0.8), 2)
        elif "VOLTAGE" in name.upper() or unit == "V":
            val = round(380.0 + random.uniform(-2.0, 2.0), 1)
        elif "COUNT" in name.upper() or "TOTAL" in name.upper():
            sim["counter"] += random.choice([0, 1, 2])
            val = int(sim["counter"])
        elif "DEFECT" in name.upper():
            val = int(sim.get("defects", 14) + (1 if random.random() < 0.05 else 0))
            sim["defects"] = val
        elif data_type == "REAL":
            val = round(random.uniform(10.0, 100.0), 2)
        elif data_type in ("INT", "DINT", "WORD"):
            val = int(random.randint(100, 999))
        else:
            val = "RUNNING"

        return {
            "name": name,
            "address": address,
            "type": data_type,
            "value": val,
            "unit": unit,
            "quality": "GOOD",
            "timestamp": int(now * 1000)
        }
