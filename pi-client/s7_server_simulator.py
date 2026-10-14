#!/usr/bin/env python3
"""
Siemens S7-1200 Server Simulator (Port 102)
Turns a Raspberry Pi or PC into a dedicated Siemens S7-1200 PLC.
Simulates Data Block 1 (DB1) with 19 Tags and Lifebit Watchdog.
Compliant with TOR Section 2.3 (Simulation & Burn-in Test).
"""

import sys
import os
import time
import struct
import random
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [S7-PLC-SIM] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("S7ServerSim")

try:
    import snap7
    from snap7.server import Server
    HAS_SNAP7_SERVER = True
except ImportError:
    HAS_SNAP7_SERVER = False


class S7ServerSimulator:
    def __init__(self, port=102, db_number=1, db_size=128):
        self.port = port
        self.db_number = db_number
        self.db_size = db_size
        self.server = None
        self.running = False
        # Allocate DB buffer in memory
        self.db_data = bytearray(self.db_size)
        self.counter = 1000

    def start_server(self):
        """Starts the S7 Server on TCP port 102."""
        if not HAS_SNAP7_SERVER:
            logger.error("snap7 library not installed! Run: sudo apt install libsnap7-dev && pip3 install python-snap7")
            return False

        try:
            self.server = Server()
            # Register DB area
            self.server.register_area(snap7.snap7types.srvAreaDB, self.db_number, self.db_data)
            # Start server (requires root/sudo for port 102)
            self.server.start_to("0.0.0.0", tcp_port=self.port)
            self.running = True
            logger.info("=" * 65)
            logger.info(f"🏭 Siemens S7-1200 PLC Simulator Online!")
            logger.info(f"🔌 Listening on: 0.0.0.0:{self.port} (S7 Protocol)")
            logger.info(f"📦 Registered:   DB{self.db_number} (Size: {self.db_size} bytes, 19 Tags)")
            logger.info("=" * 65)
            return True
        except Exception as e:
            logger.error(f"Failed to start S7 Server: {e}")
            if "Permission denied" in str(e) or self.port < 1024:
                logger.error("Port 102 requires root privileges. Please run with: sudo python3 s7_server_simulator.py")
            return False

    def update_sensor_values(self):
        """Periodically updates 19 tags in DB1 with realistic industrial machine values."""
        while self.running:
            try:
                # Tag 1: Spindle Temp (REAL at DB1.DBD0) - 60°C to 72°C
                temp = round(64.0 + random.uniform(-2.5, 3.5), 2)
                struct.pack_into(">f", self.db_data, 0, temp)

                # Tag 2: Motor Current (REAL at DB1.DBD4) - 12A to 16A
                current = round(14.2 + random.uniform(-0.8, 0.8), 2)
                struct.pack_into(">f", self.db_data, 4, current)

                # Tag 3: Motor Voltage (REAL at DB1.DBD8) - 380V to 382V
                voltage = round(380.0 + random.uniform(-1.5, 1.5), 1)
                struct.pack_into(">f", self.db_data, 8, voltage)

                # Tag 4: Hydraulic Pressure (REAL at DB1.DBD12) - 118 to 124 bar
                hyd = round(120.0 + random.uniform(-2.0, 2.0), 1)
                struct.pack_into(">f", self.db_data, 12, hyd)

                # Tag 5: Pneumatic Pressure (REAL at DB1.DBD16) - 6.0 to 6.5 bar
                pneu = round(6.2 + random.uniform(-0.2, 0.2), 2)
                struct.pack_into(">f", self.db_data, 16, pneu)

                # Tag 6: Line Speed (REAL at DB1.DBD20) - 44 to 46 m/min
                speed = round(45.0 + random.uniform(-1.0, 1.0), 1)
                struct.pack_into(">f", self.db_data, 20, speed)

                # Tag 7: Vibration (REAL at DB1.DBD24) - 1.1 to 1.4 mm/s
                vib = round(1.25 + random.uniform(-0.1, 0.1), 2)
                struct.pack_into(">f", self.db_data, 24, vib)

                # Tag 8: Coolant Flow (REAL at DB1.DBD28) - 18 to 20 L/min
                flow = round(18.5 + random.uniform(-0.8, 0.8), 1)
                struct.pack_into(">f", self.db_data, 28, flow)

                # Tag 9: Coolant Temp (REAL at DB1.DBD32) - 22 to 25°C
                c_temp = round(23.5 + random.uniform(-1.0, 1.0), 1)
                struct.pack_into(">f", self.db_data, 32, c_temp)

                # Tag 10: Total Production (DINT at DB1.DBD36)
                self.counter += random.choice([0, 1])
                struct.pack_into(">i", self.db_data, 36, self.counter)

                # Tag 11: Good Parts (DINT at DB1.DBD40)
                good = max(0, self.counter - 12)
                struct.pack_into(">i", self.db_data, 40, good)

                # Tag 12: Defect Parts (DINT at DB1.DBD44)
                struct.pack_into(">i", self.db_data, 44, 12)

                # Tag 13: Cycle Time (REAL at DB1.DBD48) - 12.0 to 12.8 s
                cycle = round(12.4 + random.uniform(-0.3, 0.3), 1)
                struct.pack_into(">f", self.db_data, 48, cycle)

                # Tag 14: Target Cycle Time (REAL at DB1.DBD52) - 12.0 s
                struct.pack_into(">f", self.db_data, 52, 12.0)

                # Tag 15: Operating Hours (REAL at DB1.DBD56) - 1450.5 h
                struct.pack_into(">f", self.db_data, 56, 1450.5)

                # Tag 16: Machine Running (BOOL at DB1.DBX60.0) -> Byte 60, bit 0
                # Tag 17: Fault Alarm (BOOL at DB1.DBX60.1) -> Byte 60, bit 1
                # Tag 18: E-Stop OK (BOOL at DB1.DBX60.2) -> Byte 60, bit 2
                status_byte = 0b00000101  # Running=1, Fault=0, E-Stop=1
                self.db_data[60] = status_byte

                # Tag 19: Alarm Code (INT at DB1.DBW62) -> 0 (Normal)
                struct.pack_into(">h", self.db_data, 62, 0)

                # Read Gateway Lifebit from Gateway write (Byte 0, bit 0)
                lifebit_val = bool(self.db_data[0] & 0x01)

                logger.info(f"🔄 DB1 Updated | Spindle Temp: {temp}°C | Speed: {speed} m/min | Counter: {self.counter} | Gateway Lifebit: {int(lifebit_val)}")

            except Exception as e:
                logger.warning(f"Error updating simulated DB: {e}")

            time.sleep(2)

    def run(self):
        if not self.start_server():
            return
        try:
            self.update_sensor_values()
        except KeyboardInterrupt:
            logger.info("Stopping S7 Simulator Server...")
        finally:
            self.running = False
            if self.server:
                self.server.stop()
                self.server.destroy()
            logger.info("S7 Simulator Server Stopped.")


if __name__ == "__main__":
    sim = S7ServerSimulator(port=102, db_number=1, db_size=128)
    sim.run()
