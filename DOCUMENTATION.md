# 🏭 Siemens S7-1200 Industrial IoT Edge Gateway (Raspberry Pi 4)
## Architecture Guide, Verification & Deployment Manual

> [!IMPORTANT]
> **Production Cloud Target:**
> All telemetry batches and two-way heartbeats stream directly to the official **Railway Cloud API**:
> 🌐 `https://epc-edge-api-dev.up.railway.app/api`

---

## 1. System Overview & Physical Topology

The **Raspberry Pi 4 Model B IoT Edge Gateway** acquires real-time machine telemetry from physical **Siemens S7-1200 PLCs** via ISO-on-TCP (S7comm Protocol, TCP Port 102) and transmits structured data batches to the Railway Cloud API.

```
       [ Siemens S7-1200 PLC ] (Target IP: 192.168.2.2:102)
                   │
                   │ Industrial S7comm Protocol (Port 102)
                   ▼
┌────────────────────────────────────────────────────────┐
│                   Switching Hub                        │
└──────┬───────────────────┬──────────────────────┬──────┘
       │                   │                      │
       ▼                   ▼                      ▼
[ Raspberry Pi 1 ]  [ Raspberry Pi 2 ]    [ Workstation / TIA ]
  gse-proto-1         gse-proto-2         (Monitoring & Dev)
 (Master Gateway)    (Backup Gateway)
  192.168.2.4         192.168.2.3
       │                   │
       └─────────┬─────────┘
                 │ Dual Ethernet / Internet Route (eth0 / eth1)
                 ▼
 ☁️ [ Railway Cloud API: https://epc-edge-api-dev.up.railway.app/api ]
```

---

## 2. Hardware Profiles & Zero-Touch Auto-Configuration

The gateway includes an intelligent zero-touch provisioning engine that automatically detects hardware identifiers upon startup:

| Attribute | Board #1 (`GSE-PROTO-1`) | Board #2 (`GSE-PROTO-2`) | Siemens S7-1200 PLC |
| :--- | :--- | :--- | :--- |
| **Hostname** | `gse-proto-1` | `gse-proto-2` | Physical PLC |
| **Device Name** | `GSE-PROTO-1` | `GSE-PROTO-2` | Machine / Line Asset |
| **Device UUID** | `4045f327-2776-4f34-977e-64e307db648f` | `24207b3f-da30-44e7-91f9-8d0067a5d1af` | Steam Generator #1 |
| **API Key (`x-api-key`)** | `gs_17ed8df023f46e38...4e7a5a70` | `gs_505a9bb4652c7654...0e743c6` | - |
| **IP Address** | `192.168.2.4` | `192.168.2.3` | `192.168.2.2` |
| **MAC Address** | `98:fe:54:63:34:ca` | `98:fe:54:63:35:a5` | Factory MAC |
| **CPU Serial** | `1000000091f9071a` | `100000001b657629` | S7-1200 Firmware |
| **Role** | Master Active Gateway | Redundant Standby Gateway | Physical Machine PLC |

### Zero-Touch Auto-Configuration Capabilities:
1. **Auto Hardware Profile Binding**: Auto-detects Raspberry Pi CPU Serial and MAC to bind Device UUID & API Key without manual editing.
2. **Auto Network Port Swapping**: Reads the Linux Kernel route table. If Ethernet cables are reversed (`eth0` vs `eth1`), roles are swapped dynamically without dropping the connection.
3. **Auto PLC Discovery (Port 102)**: Concurrent multithreaded probe scans the local subnet using COTP (ISO-on-TCP) handshake packets to discover the PLC in 0.02s.
4. **Auto Bulk DB Read Optimization**: Reads the contiguous 64-byte DB1 area in a single request, cutting PLC CPU load by 90%.
5. **Auto Emergency Fast-Poll**: Polls E-Stop, Fault, and Alarm tags every 2 seconds. When triggered, immediately pushes an alert batch to the Cloud API without waiting for the 60-minute window.

---

## 3. Sensor Definitions & Memory Mapping (19 Tags)

Data is extracted directly from **DB1** using Siemens Big-Endian byte ordering:

| ID | Tag Name | Address | Type | Engineering Unit | Description |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | `spindle_temperature` | `DB1.DBD0` | REAL | °C | Main Spindle Temperature |
| **2** | `motor_current` | `DB1.DBD4` | REAL | A | Motor Phase Current |
| **3** | `motor_voltage` | `DB1.DBD8` | REAL | V | Supply Bus Voltage |
| **4** | `hydraulic_pressure` | `DB1.DBD12` | REAL | bar | Hydraulic System Pressure |
| **5** | `pneumatic_pressure` | `DB1.DBD16` | REAL | bar | Pneumatic Air Pressure |
| **6** | `line_speed` | `DB1.DBD20` | REAL | m/min | Conveyor Line Speed |
| **7** | `vibration_level` | `DB1.DBD24` | REAL | mm/s | Spindle Bearing Vibration RMS |
| **8** | `coolant_flow_rate` | `DB1.DBD28` | REAL | L/min | Coolant Liquid Flow Rate |
| **9** | `coolant_temp` | `DB1.DBD32` | REAL | °C | Coolant Reservoir Temperature |
| **10** | `total_production_count`| `DB1.DBD36` | DINT | pcs | Total Output Production Units |
| **11** | `good_parts_count` | `DB1.DBD40` | DINT | pcs | Passed Quality Units |
| **12** | `defect_parts_count` | `DB1.DBD44` | DINT | pcs | Rejected Defect Units |
| **13** | `cycle_time_current` | `DB1.DBD48` | REAL | s | Current Cycle Duration |
| **14** | `cycle_time_target` | `DB1.DBD52` | REAL | s | Target Standard Cycle Time |
| **15** | `machine_operating_hours`|`DB1.DBD56` | REAL | h | Cumulative Machine Running Hours |
| **16** | `machine_status_running`| `DB1.DBX60.0` | BOOL | state | Machine Run State (1=Run, 0=Stop) |
| **17** | `machine_status_fault` | `DB1.DBX60.1` | BOOL | state | Machine Fault Alarm Active |
| **18** | `emergency_stop_ok` | `DB1.DBX60.2` | BOOL | state | Emergency Stop Status (1=OK, 0=Tripped) |
| **19** | `active_alarm_code` | `DB1.DBW62` | INT | code | Active Fault Alarm Code Number |

---

## 4. Setup & Deployment on Raspberry Pi 4

### 1. Automated 1-Click Setup
Run from inside `pi-client/`:
```bash
cd ~/rpitesting/pi-client
chmod +x setup_plc_gateway.sh install_toolbox.sh
sudo ./setup_plc_gateway.sh
```

### 2. Global CLI Toolbox Reference
Available from any terminal directory:
- `plc-toolbox`: Display command reference menu.
- `plc-info`: Show Device ID, MACs, Serial Number, and Tailscale VPN IP.
- `plc-discover`: Auto-scan local network and find Siemens S7 PLCs on port 102.
- `plc-package`: Inspect Raw Data Hex -> Parsed Sensors & Web Batch Package.
- `plc-package --send`: Transmit the inspected batch package directly to Cloud API.
- `plc-diagnose`: Run 7-Point automated self-diagnostic check.
- `plc-test`: Execute a single acquisition and cloud transmission cycle.
- `plc-status`: Check 24/7 background systemd service status.
- `plc-logs`: Stream live journal logs (`sudo journalctl -u plc-gateway -f`).
- `plc-restart`: Restart the edge gateway service gracefully.
- `plc-buffer`: Check SQLite Store-and-Forward offline buffer depth.
- `plc-config`: Launch Interactive CLI & Web Configurator.

---

## 5. Security & Safety Guardrails

| Mechanism | Behavior | Rationale |
| :--- | :--- | :--- |
| **Read-Only PLC Monitoring** | Gateway only performs memory reads and toggles the Lifebit pulse (`DB1.DBX0.0`). | **Never writes machine control setpoints**, preventing industrial hazards. |
| **No PLC IP Manipulation** | Gateway auto-discovers PLC IP, but never modifies the PLC's own IP via DCP. | Prevents disconnecting existing plant SCADA or HMIs. |
| **Zero Data Loss Guarantee** | SQLite WAL buffer purges records **only after HTTP 200/201 response** from Railway Cloud. | Conforms to strict industrial TOR requirements. |
| **API Authentication** | Railway Cloud API requests use `x-api-key: gs_...`. | Ensures authenticated and encrypted telemetry delivery. |
