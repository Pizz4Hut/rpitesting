// Frontend Application Logic for Raspberry Pi Telemetry Dashboard

let currentDevices = [];
let selectedDeviceId = null;
let refreshTimer = null;
let tempChart = null;
let loadChart = null;

// DOM Elements
const statTotalDevices = document.getElementById('statTotalDevices');
const statOnlineDevices = document.getElementById('statOnlineDevices');
const statWarningDevices = document.getElementById('statWarningDevices');
const statOfflineDevices = document.getElementById('statOfflineDevices');
const deviceListPills = document.getElementById('deviceListPills');

const currentDeviceName = document.getElementById('currentDeviceName');
const currentDeviceStatusBadge = document.getElementById('currentDeviceStatusBadge');
const currentDeviceId = document.getElementById('currentDeviceId');
const currentDeviceIp = document.getElementById('currentDeviceIp');
const currentDeviceLastSeen = document.getElementById('currentDeviceLastSeen');
const currentDeviceOs = document.getElementById('currentDeviceOs');

const valCpuTemp = document.getElementById('valCpuTemp');
const valCpuTempF = document.getElementById('valCpuTempF');
const barCpuTemp = document.getElementById('barCpuTemp');
const valCpuUsage = document.getElementById('valCpuUsage');
const barCpuUsage = document.getElementById('barCpuUsage');
const valUptime = document.getElementById('valUptime');
const valRamUsage = document.getElementById('valRamUsage');
const barRamUsage = document.getElementById('barRamUsage');
const valRamUsed = document.getElementById('valRamUsed');
const valRamTotal = document.getElementById('valRamTotal');
const valDiskUsage = document.getElementById('valDiskUsage');
const barDiskUsage = document.getElementById('barDiskUsage');
const valDiskFree = document.getElementById('valDiskFree');

const valAmbientTemp = document.getElementById('valAmbientTemp');
const valHumidity = document.getElementById('valHumidity');
const valPressure = document.getElementById('valPressure');
const valCustomSensor = document.getElementById('valCustomSensor');
const eventsTableBody = document.getElementById('eventsTableBody');

// Format helpers
function formatUptime(seconds) {
  if (!seconds || isNaN(seconds)) return 'Unknown';
  const d = Math.floor(seconds / (3600 * 24));
  const h = Math.floor((seconds % (3600 * 24)) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${Math.floor(seconds % 60)}s`;
}

function timeAgo(timestamp) {
  if (!timestamp) return 'Never';
  const elapsed = Math.floor((Date.now() - timestamp) / 1000);
  if (elapsed < 5) return 'Just now';
  if (elapsed < 60) return `${elapsed}s ago`;
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ago`;
  if (elapsed < 86400) return `${Math.floor(elapsed / 3600)}h ago`;
  return `${Math.floor(elapsed / 86400)}d ago`;
}

// Chart Initialization
function initCharts() {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: {
        labels: { color: '#94a3b8', font: { size: 11 } }
      }
    },
    scales: {
      x: {
        grid: { color: '#1e293b' },
        ticks: { color: '#64748b', font: { size: 10 } }
      },
      y: {
        grid: { color: '#1e293b' },
        ticks: { color: '#64748b', font: { size: 10 } }
      }
    }
  };

  // Temperature Chart
  const ctxTemp = document.getElementById('tempChart').getContext('2d');
  tempChart = new Chart(ctxTemp, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'CPU Temp (°C)',
          borderColor: '#f97316',
          backgroundColor: 'rgba(249, 115, 22, 0.1)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          data: []
        },
        {
          label: 'Ambient Temp (°C)',
          borderColor: '#38bdf8',
          backgroundColor: 'transparent',
          borderDash: [4, 4],
          borderWidth: 1.5,
          tension: 0.35,
          data: []
        }
      ]
    },
    options: chartOptions
  });

  // Load Chart
  const ctxLoad = document.getElementById('loadChart').getContext('2d');
  loadChart = new Chart(ctxLoad, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'CPU Load (%)',
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99, 102, 241, 0.1)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          data: []
        },
        {
          label: 'RAM Usage (%)',
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.08)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          data: []
        }
      ]
    },
    options: chartOptions
  });
}

// Update charts with device telemetry history
function updateCharts(device) {
  if (!device || !device.history || !tempChart || !loadChart) return;

  const points = device.history.slice(-25);
  const labels = points.map(p => {
    const d = new Date(p.timestamp);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
  });

  const cpuTemps = points.map(p => p.cpuTemp ?? null);
  const ambientTemps = points.map(p => p.ambientTemp ?? null);
  const cpuLoads = points.map(p => p.cpuUsage ?? null);
  const ramLoads = points.map(p => p.ramUsage ?? null);

  tempChart.data.labels = labels;
  tempChart.data.datasets[0].data = cpuTemps;
  tempChart.data.datasets[1].data = ambientTemps;
  tempChart.update();

  loadChart.data.labels = labels;
  loadChart.data.datasets[0].data = cpuLoads;
  loadChart.data.datasets[1].data = ramLoads;
  loadChart.update();
}

// Fetch devices and dashboard data
async function fetchDevices() {
  const refreshIcon = document.getElementById('refreshIcon');
  if (refreshIcon) refreshIcon.classList.add('animate-spin');

  try {
    const res = await fetch('/api/devices');
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    currentDevices = data.devices || [];

    // Update KPI Counters
    const summary = data.summary || {};
    statTotalDevices.textContent = summary.total || 0;
    statOnlineDevices.textContent = summary.online || 0;
    statWarningDevices.textContent = (summary.warning || 0) + (summary.idle || 0);
    statOfflineDevices.textContent = summary.offline || 0;

    // Render Device Selection Pills
    renderDevicePills();

    // Default select first device if none selected
    if ((!selectedDeviceId || !currentDevices.find(d => d.id === selectedDeviceId)) && currentDevices.length > 0) {
      selectedDeviceId = currentDevices[0].id;
    }

    renderSelectedDevice();
    renderEvents(data.events || []);

  } catch (err) {
    console.error('Failed to fetch devices:', err);
  } finally {
    if (refreshIcon) {
      setTimeout(() => refreshIcon.classList.remove('animate-spin'), 400);
    }
  }
}

// Render pills for all devices
function renderDevicePills() {
  if (currentDevices.length === 0) {
    deviceListPills.innerHTML = `
      <div class="flex items-center space-x-2 text-xs text-slate-400 py-1">
        <i data-lucide="info" class="w-4 h-4 text-slate-500"></i>
        <span>No Raspberry Pi devices connected yet. Click <strong>"Simulate Pi"</strong> above to see sample data!</span>
      </div>`;
    lucide.createIcons();
    return;
  }

  deviceListPills.innerHTML = currentDevices.map(d => {
    const isSelected = d.id === selectedDeviceId;
    let dotColor = 'bg-emerald-400';
    if (d.computedStatus === 'warning') dotColor = 'bg-amber-400';
    if (d.computedStatus === 'offline') dotColor = 'bg-rose-400';
    if (d.computedStatus === 'idle') dotColor = 'bg-slate-400';

    return `
      <button 
        onclick="selectDevice('${d.id}')"
        class="flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
          isSelected 
            ? 'bg-surface-700 border-brand-500 text-white shadow-sm ring-1 ring-brand-500/30' 
            : 'bg-surface-800 border-surface-700/80 text-slate-300 hover:bg-surface-700 hover:text-white'
        }">
        <span class="w-2 h-2 rounded-full ${dotColor}"></span>
        <span>${escapeHtml(d.name || d.id)}</span>
      </button>
    `;
  }).join('');

  lucide.createIcons();
}

window.selectDevice = function(id) {
  selectedDeviceId = id;
  renderDevicePills();
  renderSelectedDevice();
};

// Render details of selected device
function renderSelectedDevice() {
  const device = currentDevices.find(d => d.id === selectedDeviceId);

  if (!device) {
    currentDeviceName.textContent = 'No Device Selected';
    currentDeviceStatusBadge.textContent = 'Offline';
    currentDeviceStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold status-offline';
    currentDeviceId.textContent = 'ID: -';
    currentDeviceIp.textContent = 'IP: -';
    currentDeviceLastSeen.textContent = 'Last seen: -';
    currentDeviceOs.textContent = 'OS: -';
    return;
  }

  // Header info
  currentDeviceName.textContent = device.name || device.id;
  currentDeviceId.textContent = `ID: ${device.id}`;
  currentDeviceIp.textContent = `IP: ${device.latest?.system?.ipAddress || 'Unknown'}`;
  currentDeviceLastSeen.textContent = `Last seen: ${timeAgo(device.lastSeen)}`;
  currentDeviceOs.textContent = `OS: ${device.latest?.system?.os || 'Raspberry Pi OS'}`;

  // Status Badge
  const status = device.computedStatus || 'offline';
  currentDeviceStatusBadge.textContent = status.toUpperCase();
  currentDeviceStatusBadge.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold status-${status}`;

  const sys = device.latest?.system || {};
  const sensors = device.latest?.sensors || {};

  // CPU Temperature
  const cpuTemp = sys.cpuTemp;
  if (cpuTemp !== null && cpuTemp !== undefined) {
    valCpuTemp.textContent = cpuTemp.toFixed(1);
    valCpuTempF.textContent = `${((cpuTemp * 9/5) + 32).toFixed(1)} °F`;
    barCpuTemp.style.width = `${Math.min(100, (cpuTemp / 100) * 100)}%`;
    if (cpuTemp >= 75) {
      barCpuTemp.className = 'bg-rose-500 h-2 rounded-full transition-all duration-500';
    } else if (cpuTemp >= 60) {
      barCpuTemp.className = 'bg-amber-500 h-2 rounded-full transition-all duration-500';
    } else {
      barCpuTemp.className = 'bg-emerald-500 h-2 rounded-full transition-all duration-500';
    }
  } else {
    valCpuTemp.textContent = '--';
    valCpuTempF.textContent = '-- °F';
    barCpuTemp.style.width = '0%';
  }

  // CPU Usage
  const cpuUsage = sys.cpuUsage;
  if (cpuUsage !== null && cpuUsage !== undefined) {
    valCpuUsage.textContent = cpuUsage.toFixed(1);
    barCpuUsage.style.width = `${Math.min(100, cpuUsage)}%`;
  } else {
    valCpuUsage.textContent = '--';
    barCpuUsage.style.width = '0%';
  }
  valUptime.textContent = formatUptime(sys.uptimeSeconds);

  // RAM Usage
  const ramUsage = sys.ramUsage;
  if (ramUsage !== null && ramUsage !== undefined) {
    valRamUsage.textContent = ramUsage.toFixed(1);
    barRamUsage.style.width = `${Math.min(100, ramUsage)}%`;
  } else {
    valRamUsage.textContent = '--';
    barRamUsage.style.width = '0%';
  }
  valRamUsed.textContent = sys.ramUsedMB ? `${sys.ramUsedMB} MB used` : '-- MB';
  valRamTotal.textContent = sys.ramTotalMB ? `${sys.ramTotalMB} MB total` : '-- MB';

  // Disk Usage
  const diskUsage = sys.diskUsage;
  if (diskUsage !== null && diskUsage !== undefined) {
    valDiskUsage.textContent = diskUsage.toFixed(1);
    barDiskUsage.style.width = `${Math.min(100, diskUsage)}%`;
  } else {
    valDiskUsage.textContent = '--';
    barDiskUsage.style.width = '0%';
  }
  valDiskFree.textContent = sys.diskFreeGB ? `${sys.diskFreeGB.toFixed(1)} GB Free` : '-- GB Free';

  // Sensors
  valAmbientTemp.textContent = sensors.ambientTemp ? `${sensors.ambientTemp} °C` : '--';
  valHumidity.textContent = sensors.humidity ? `${sensors.humidity} %` : '--';
  valPressure.textContent = sensors.pressure ? `${sensors.pressure} hPa` : '--';
  valCustomSensor.textContent = sensors.soilMoisture ? `${sensors.soilMoisture}% moisture` : (sensors.status || '--');

  // Charts
  updateCharts(device);
}

// Render Recent Events Table
function renderEvents(events) {
  if (!events || events.length === 0) {
    eventsTableBody.innerHTML = `
      <tr>
        <td colspan="4" class="py-4 text-center text-slate-500 italic">No events recorded yet.</td>
      </tr>`;
    return;
  }

  eventsTableBody.innerHTML = events.map(e => {
    let badgeClass = 'bg-blue-500/10 text-blue-400';
    if (e.type === 'warning') badgeClass = 'bg-amber-500/10 text-amber-400';
    if (e.type === 'error') badgeClass = 'bg-rose-500/10 text-rose-400';

    return `
      <tr class="hover:bg-surface-800/40 transition">
        <td class="py-2.5 px-3 text-slate-400 font-mono text-[11px]">${timeAgo(e.timestamp)}</td>
        <td class="py-2.5 px-3 font-medium text-slate-200">${escapeHtml(e.deviceName || e.deviceId)}</td>
        <td class="py-2.5 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${badgeClass}">${escapeHtml(e.type || 'info')}</span>
        </td>
        <td class="py-2.5 px-3 text-slate-300">${escapeHtml(e.message)}</td>
      </tr>
    `;
  }).join('');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.toString()
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Auto-Refresh handler
function setupAutoRefresh() {
  const select = document.getElementById('refreshIntervalSelect');
  const liveIndicator = document.getElementById('liveIndicator');

  function resetTimer() {
    if (refreshTimer) clearInterval(refreshTimer);
    const ms = parseInt(select.value, 10);
    if (ms > 0) {
      liveIndicator.classList.remove('hidden');
      refreshTimer = setInterval(fetchDevices, ms);
    } else {
      liveIndicator.classList.add('hidden');
    }
  }

  select.addEventListener('change', resetTimer);
  resetTimer();
}

// Action Button Handlers
document.getElementById('refreshBtn').addEventListener('click', fetchDevices);

document.getElementById('simulateBtn').addEventListener('click', async () => {
  const btn = document.getElementById('simulateBtn');
  btn.disabled = true;
  btn.innerHTML = `<span class="animate-spin mr-1">⚙️</span> Simulating...`;
  try {
    const res = await fetch('/api/simulate', { method: 'POST' });
    if (res.ok) {
      await fetchDevices();
    }
  } catch (e) {
    console.error('Simulation error:', e);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-3.5 h-3.5 mr-1"></i><span>Simulate Pi</span>`;
    lucide.createIcons();
  }
});

document.getElementById('deleteDeviceBtn').addEventListener('click', async () => {
  if (!selectedDeviceId) return;
  if (!confirm(`Are you sure you want to remove device "${selectedDeviceId}" from the dashboard?`)) return;

  try {
    const res = await fetch(`/api/devices/${encodeURIComponent(selectedDeviceId)}`, { method: 'DELETE' });
    if (res.ok) {
      selectedDeviceId = null;
      await fetchDevices();
    }
  } catch (e) {
    alert('Failed to delete device');
  }
});

// Setup Guide Modal
const guideModal = document.getElementById('guideModal');
document.getElementById('openGuideBtn').addEventListener('click', () => {
  // Update quick test cmd with current origin
  const origin = window.location.origin;
  document.getElementById('quickTestCmd').innerHTML = `<code>python3 pi_agent.py --url ${origin}/api/telemetry --interval 10</code>`;
  guideModal.classList.remove('hidden');
});
document.getElementById('closeGuideBtn').addEventListener('click', () => guideModal.classList.add('hidden'));
document.getElementById('closeGuideBtn2').addEventListener('click', () => guideModal.classList.add('hidden'));

// API Docs Modal
const apiDocsModal = document.getElementById('apiDocsModal');
document.getElementById('openApiDocsBtn').addEventListener('click', () => apiDocsModal.classList.remove('hidden'));
document.getElementById('closeApiDocsBtn').addEventListener('click', () => apiDocsModal.classList.add('hidden'));
document.getElementById('closeApiDocsBtn2').addEventListener('click', () => apiDocsModal.classList.add('hidden'));

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  initCharts();
  fetchDevices();
  setupAutoRefresh();
});
