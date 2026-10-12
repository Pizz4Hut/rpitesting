/**
 * Storage adapter for Raspberry Pi IoT Telemetry.
 * Uses Netlify Blobs when available on Netlify,
 * with automatic fallback to local memory / file cache for local development.
 */

const fs = require('fs');
const path = require('path');

// Local in-memory cache
let inMemoryStore = {
  devices: {},
  events: []
};

// Local file path for persistent testing during local development
const LOCAL_STORAGE_DIR = path.resolve(process.cwd(), '.data');
const LOCAL_STORAGE_FILE = path.join(LOCAL_STORAGE_DIR, 'store.json');

// Attempt to load local file if exists
try {
  if (fs.existsSync(LOCAL_STORAGE_FILE)) {
    const raw = fs.readFileSync(LOCAL_STORAGE_FILE, 'utf8');
    inMemoryStore = JSON.parse(raw);
  }
} catch (e) {
  // Ignore on serverless read-only filesystems
}

function saveLocalStore() {
  try {
    if (!fs.existsSync(LOCAL_STORAGE_DIR)) {
      fs.mkdirSync(LOCAL_STORAGE_DIR, { recursive: true });
    }
    fs.writeFileSync(LOCAL_STORAGE_FILE, JSON.stringify(inMemoryStore, null, 2), 'utf8');
  } catch (e) {
    // Read-only filesystem in some serverless environments, inMemoryStore remains
  }
}

// Netlify Blobs helper
let blobsStore = null;
async function getBlobStore() {
  if (blobsStore) return blobsStore;
  try {
    // Only attempt if Netlify Blobs environment is active
    if (process.env.NETLIFY || process.env.NETLIFY_BLOBS_CONTEXT) {
      const { getStore } = require('@netlify/blobs');
      blobsStore = getStore('pi-telemetry-store');
      return blobsStore;
    }
  } catch (e) {
    // Blobs not available, fallback to memory
  }
  return null;
}

const MAX_HISTORY_POINTS = 60; // Keep up to 60 telemetry points per device
const OFFLINE_TIMEOUT_MS = 120000; // 2 minutes without data = Offline
const WARNING_TIMEOUT_MS = 45000;  // 45 seconds without data = Warning/Idle

function computeDeviceStatus(lastSeen, cpuTemp) {
  const age = Date.now() - (lastSeen || 0);
  if (age > OFFLINE_TIMEOUT_MS) return 'offline';
  if (cpuTemp && cpuTemp >= 75) return 'warning';
  if (age > WARNING_TIMEOUT_MS) return 'idle';
  return 'online';
}

async function getAllDevices() {
  const store = await getBlobStore();
  if (store) {
    try {
      const data = await store.get('devices', { type: 'json' });
      if (data) {
        // Update dynamic statuses
        Object.values(data).forEach(dev => {
          dev.computedStatus = computeDeviceStatus(dev.lastSeen, dev.latest?.system?.cpuTemp);
        });
        return data;
      }
    } catch (e) {
      console.warn('Blobs fetch error, using memory fallback:', e.message);
    }
  }

  // Update dynamic statuses in local store
  Object.values(inMemoryStore.devices).forEach(dev => {
    dev.computedStatus = computeDeviceStatus(dev.lastSeen, dev.latest?.system?.cpuTemp);
  });
  return inMemoryStore.devices;
}

async function getDevice(deviceId) {
  const devices = await getAllDevices();
  return devices[deviceId] || null;
}

async function saveTelemetry(payload) {
  const deviceId = (payload.deviceId || payload.id || 'raspberrypi-default').toString().trim();
  const deviceName = payload.deviceName || payload.name || deviceId;
  const timestamp = payload.timestamp || Date.now();

  const devices = await getAllDevices();
  const existing = devices[deviceId] || {
    id: deviceId,
    name: deviceName,
    firstSeen: timestamp,
    history: []
  };

  const cpuTemp = payload.system?.cpuTemp ?? payload.cpuTemp ?? null;
  const cpuUsage = payload.system?.cpuUsage ?? payload.cpuUsage ?? null;
  const ramUsage = payload.system?.ramUsage ?? payload.ramUsage ?? null;

  const historyPoint = {
    timestamp,
    cpuTemp,
    cpuUsage,
    ramUsage,
    ambientTemp: payload.sensors?.ambientTemp ?? null,
    humidity: payload.sensors?.humidity ?? null
  };

  const updatedHistory = [...(existing.history || []), historyPoint].slice(-MAX_HISTORY_POINTS);

  const updatedDevice = {
    id: deviceId,
    name: deviceName,
    firstSeen: existing.firstSeen || timestamp,
    lastSeen: timestamp,
    computedStatus: computeDeviceStatus(timestamp, cpuTemp),
    latest: {
      timestamp,
      system: {
        cpuTemp,
        cpuUsage,
        ramUsage,
        ramUsedMB: payload.system?.ramUsedMB ?? null,
        ramTotalMB: payload.system?.ramTotalMB ?? null,
        diskUsage: payload.system?.diskUsage ?? payload.diskUsage ?? null,
        diskFreeGB: payload.system?.diskFreeGB ?? payload.diskFreeGB ?? null,
        uptimeSeconds: payload.system?.uptimeSeconds ?? payload.uptime ?? null,
        ipAddress: payload.system?.ipAddress ?? payload.ip ?? 'Unknown',
        hostname: payload.system?.hostname ?? payload.hostname ?? deviceName,
        os: payload.system?.os ?? payload.os ?? 'Raspberry Pi OS'
      },
      sensors: payload.sensors || {},
      raw: payload
    },
    history: updatedHistory
  };

  devices[deviceId] = updatedDevice;

  // Add event log if high temp or new registration
  const event = {
    id: `${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
    deviceId,
    deviceName,
    timestamp,
    message: cpuTemp && cpuTemp >= 75 
      ? `High CPU Temperature Alert: ${cpuTemp}°C on ${deviceName}`
      : `Telemetry received from ${deviceName} (CPU: ${cpuTemp ?? 'N/A'}°C, Load: ${cpuUsage ?? 'N/A'}%)`,
    type: cpuTemp && cpuTemp >= 75 ? 'warning' : 'info'
  };

  // Persist
  const store = await getBlobStore();
  if (store) {
    try {
      await store.setJSON('devices', devices);
      let events = (await store.get('events', { type: 'json' })) || [];
      events.unshift(event);
      events = events.slice(0, 50);
      await store.setJSON('events', events);
    } catch (e) {
      console.warn('Blobs save error:', e.message);
    }
  }

  inMemoryStore.devices = devices;
  inMemoryStore.events.unshift(event);
  inMemoryStore.events = inMemoryStore.events.slice(0, 50);
  saveLocalStore();

  return updatedDevice;
}

async function getRecentEvents() {
  const store = await getBlobStore();
  if (store) {
    try {
      const events = await store.get('events', { type: 'json' });
      if (events) return events;
    } catch (e) {
      // fallback
    }
  }
  return inMemoryStore.events || [];
}

async function deleteDevice(deviceId) {
  const devices = await getAllDevices();
  if (devices[deviceId]) {
    delete devices[deviceId];
    const store = await getBlobStore();
    if (store) {
      try {
        await store.setJSON('devices', devices);
      } catch (e) {}
    }
    inMemoryStore.devices = devices;
    saveLocalStore();
    return true;
  }
  return false;
}

module.exports = {
  getAllDevices,
  getDevice,
  saveTelemetry,
  getRecentEvents,
  deleteDevice
};
