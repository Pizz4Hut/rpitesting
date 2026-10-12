# 🍓 Raspberry Pi IoT Netlify Telemetry Hub & Dashboard

A production-ready Netlify serverless website for receiving sensor and system telemetry from one or more Raspberry Pi devices, featuring a real-time monitoring dashboard and device status indicators.

---

## ✨ Features

- **Netlify Serverless API**: Lightweight serverless endpoints (`/api/telemetry`, `/api/devices`, `/api/devices/:id`) deployed on Netlify Functions with CORS enabled.
- **Real-Time IoT Dashboard**:
  - **Hardware Telemetry**: CPU Temperature (°C & °F), CPU Load (%), RAM Usage (%), Disk Free/Used (GB), System Uptime, IP Address, OS / Kernel.
  - **Device Status Indicators**: 🟢 **Online** (< 45s heartbeat), 🟡 **Idle / Warning** (high CPU temperature $\ge 75^\circ\text{C}$ or silent for 45s-2m), 🔴 **Offline** (> 2 minutes without heartbeat).
  - **Live Historical Charts**: Interactive time-series charts (Chart.js) for CPU Thermal Zone vs Ambient Temperature and CPU/RAM Load.
  - **Multi-Device Support**: Fleet monitoring with one-click device switching.
  - **Telemetry Log Stream**: Live table of incoming alerts and events.
  - **One-Click Simulator**: Test and demo live telemetry in your browser without hardware attached.
- **Plug-and-Play Raspberry Pi Client**:
  - Python 3 client (`pi-client/pi_agent.py`) that reads real Linux `/sys/class/thermal` thermal sensors, CPU/RAM/Disk stats, and custom GPIO / I2C sensors.
  - Resilient network retries with automatic reconnects.
  - Ready-to-use systemd service unit (`pi-agent.service`) to run continuously on boot.
- **Zero-Config Persistence**: Uses Netlify Blobs (`@netlify/blobs`) when deployed to Netlify, with an automatic local fallback for local development.

---

## 📁 Project Structure

```
├── netlify.toml               # Netlify configuration (functions, headers, rewrites)
├── package.json               # Project manifest
├── server.js                  # Local dev server (emulates Netlify Functions locally)
├── netlify/
│   └── functions/
│       ├── api.js             # Serverless handler for /api/* endpoints
│       └── storage.js         # Netlify Blobs + local memory storage adapter
├── public/
│   ├── index.html             # Responsive IoT dashboard (Tailwind CSS, Lucide icons)
│   ├── app.js                 # Dashboard logic, auto-refresh polling, Chart.js updates
│   └── styles.css             # Custom styles, badges, and animations
├── pi-client/
│   ├── pi_agent.py            # Python telemetry agent for Raspberry Pi
│   ├── setup.sh               # 1-click shell installer for Raspberry Pi OS
│   ├── pi-agent.service       # Systemd service for auto-start on boot
│   ├── requirements.txt       # Python dependencies (psutil, requests)
│   └── config.json.example    # Configuration template
└── README.md
```

---

## 🚀 Quick Start (Local Testing)

You can run and test the complete application locally right now:

### 1. Start the local server
```bash
npm start
# or: node server.js
```
Open **http://localhost:8888** in your browser.

### 2. Test in the browser
- Click **"Simulate Pi"** in the top navigation bar to generate instant sample telemetry for two Raspberry Pi devices.
- Notice the KPI counters, temperature gauges, and live charts updating in real-time!

### 3. Send test telemetry with `curl`
```bash
curl -X POST "http://localhost:8888/api/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "rpi-my-desk",
    "deviceName": "Desk Pi 4B",
    "system": {
      "cpuTemp": 49.2,
      "cpuUsage": 18.5,
      "ramUsage": 34.0,
      "ramUsedMB": 1390,
      "ramTotalMB": 4096,
      "diskUsage": 42.1,
      "diskFreeGB": 17.5,
      "uptimeSeconds": 72400,
      "ipAddress": "192.168.1.55"
    },
    "sensors": {
      "ambientTemp": 24.1,
      "humidity": 52.0
    }
  }'
```

---

## ☁️ Deploying to Netlify

### Option A: Via GitHub / GitLab / Bitbucket (Recommended)
1. Push this repository to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Raspberry Pi IoT Netlify site"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
2. Log in to [Netlify](https://app.netlify.com/).
3. Click **"Add new site"** &rarr; **"Import an existing project"**.
4. Select your repository.
5. Netlify will auto-detect settings from `netlify.toml`:
   - **Publish directory**: `public`
   - **Functions directory**: `netlify/functions`
6. Click **Deploy Site**. Your website will be live at `https://YOUR-SITE-NAME.netlify.app`!

### Option B: Via Netlify CLI
```bash
# Login to Netlify
npx netlify login

# Deploy
npx netlify deploy --prod
```

### 🔒 Optional: API Key Security
If you want to protect your `/api/telemetry` endpoint so only your devices can push data:
1. In the Netlify Dashboard, go to **Site settings &rarr; Environment variables**.
2. Add a new variable:
   - **Key**: `DEVICE_API_KEY`
   - **Value**: `YOUR_SECRET_TOKEN_123`
3. Provide this key in your Raspberry Pi configuration or pass header `x-api-key: YOUR_SECRET_TOKEN_123`.

---

## 🍓 Raspberry Pi Client Setup

### 1. Copy `pi-client` to your Raspberry Pi
Transfer the `pi-client` folder to your Raspberry Pi via SCP, Git, or USB:
```bash
scp -r pi-client pi@raspberrypi.local:/home/pi/
```

### 2. Run the quick installer
SSH into your Raspberry Pi:
```bash
ssh pi@raspberrypi.local
cd pi-client
chmod +x setup.sh
./setup.sh
```

### 3. Run the telemetry agent
```bash
python3 pi_agent.py \
  --url https://YOUR-NETLIFY-SITE.netlify.app/api/telemetry \
  --device-id rpi-living-room \
  --device-name "Living Room Pi" \
  --interval 10
```

### 4. Enable auto-start on boot (Systemd)
To ensure the telemetry agent runs continuously in the background:
```bash
# 1. Edit config.json with your Netlify URL:
cp config.json.example config.json
nano config.json

# 2. Install and enable the systemd service:
sudo cp pi-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-agent

# 3. Check status:
sudo systemctl status pi-agent
```

---

## 🔌 API Reference

### 1. `POST /api/telemetry`
Receives telemetry payload from devices.
- **Headers**:
  - `Content-Type: application/json`
  - `x-api-key: <optional_key>`
- **Payload Schema**:
```json
{
  "deviceId": "rpi-living-room",
  "deviceName": "Living Room Pi 4",
  "timestamp": 1728770000000,
  "system": {
    "cpuTemp": 48.5,
    "cpuUsage": 14.2,
    "ramUsage": 32.5,
    "ramUsedMB": 1330,
    "ramTotalMB": 4096,
    "diskUsage": 45.1,
    "diskFreeGB": 14.8,
    "uptimeSeconds": 86400,
    "ipAddress": "192.168.1.105",
    "hostname": "raspberrypi",
    "os": "Linux 6.1.21-v8+"
  },
  "sensors": {
    "ambientTemp": 23.4,
    "humidity": 55.2,
    "pressure": 1013.25
  }
}
```

### 2. `GET /api/devices`
Returns all registered devices, status metrics, and recent events.

### 3. `GET /api/devices/:id`
Returns real-time data and historical time-series for a single device.

### 4. `DELETE /api/devices/:id`
Deregisters and removes a device from the dashboard.

### 5. `POST /api/simulate`
Generates mock telemetry data for testing.
