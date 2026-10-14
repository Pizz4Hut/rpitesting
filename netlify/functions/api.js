const storage = require('./storage');

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-api-key',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Content-Type': 'application/json'
};

function jsonResponse(statusCode, data) {
  return {
    statusCode,
    headers: CORS_HEADERS,
    body: JSON.stringify(data)
  };
}

exports.handler = async (event, context) => {
  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 204,
      headers: CORS_HEADERS,
      body: ''
    };
  }

  try {
    // Normalize path
    let requestPath = event.path || '';
    // Strip /.netlify/functions/api prefix or /api prefix
    requestPath = requestPath
      .replace(/^\/\.netlify\/functions\/api/, '')
      .replace(/^\/api/, '');
    if (!requestPath || requestPath === '') requestPath = '/';

    const method = event.httpMethod.toUpperCase();

    // 1. Health check
    if (requestPath === '/health' && method === 'GET') {
      return jsonResponse(200, {
        status: 'ok',
        service: 'Raspberry Pi IoT Telemetry API',
        timestamp: new Date().toISOString()
      });
    }

    // 2. Heartbeat ingestion (POST /heartbeat)
    if (requestPath === '/heartbeat' && method === 'POST') {
      let body;
      try {
        body = JSON.parse(event.body || '{}');
      } catch (err) {
        return jsonResponse(400, { error: 'Invalid JSON payload' });
      }

      const requiredKey = process.env.DEVICE_API_KEY;
      if (requiredKey) {
        const providedKey = 
          event.headers['x-api-key'] || 
          event.headers['X-API-KEY'] || 
          body.apiKey ||
          (event.queryStringParameters && event.queryStringParameters.apiKey);

        if (!providedKey || providedKey !== requiredKey) {
          return jsonResponse(401, { error: 'Unauthorized: Invalid or missing x-api-key' });
        }
      }

      if (!body.deviceId && !body.id) {
        return jsonResponse(400, { error: "Missing required field 'deviceId'" });
      }

      const saved = await storage.saveHeartbeat(body);
      return jsonResponse(200, {
        success: true,
        message: 'Heartbeat acknowledged',
        deviceId: saved.id,
        receivedAt: new Date().toISOString()
      });
    }

    // 3. Telemetry ingestion (POST /telemetry or root POST)
    if ((requestPath === '/telemetry' || requestPath === '/' || requestPath === '/telemetry/batch') && method === 'POST') {
      let body;
      try {
        body = JSON.parse(event.body || '{}');
      } catch (err) {
        return jsonResponse(400, { error: 'Invalid JSON payload' });
      }

      // Optional API Key Verification
      const requiredKey = process.env.DEVICE_API_KEY;
      if (requiredKey) {
        const providedKey = 
          event.headers['x-api-key'] || 
          event.headers['X-API-KEY'] || 
          body.apiKey ||
          (event.queryStringParameters && event.queryStringParameters.apiKey);

        if (!providedKey || providedKey !== requiredKey) {
          return jsonResponse(401, { error: 'Unauthorized: Invalid or missing x-api-key' });
        }
      }

      // Batch ingestion (from Store-and-Forward backlog replay)
      if (Array.isArray(body) || (body.batch && Array.isArray(body.batch))) {
        const records = Array.isArray(body) ? body : body.batch;
        const savedIds = await storage.saveTelemetryBatch(records);
        return jsonResponse(201, {
          success: true,
          message: `Batch telemetry of ${savedIds.length} records processed`,
          count: savedIds.length,
          receivedAt: new Date().toISOString()
        });
      }

      if (!body.deviceId && !body.id) {
        return jsonResponse(400, {
          error: "Missing required field 'deviceId' (e.g. 'raspberrypi-lab-1')"
        });
      }

      const saved = await storage.saveTelemetry(body);
      return jsonResponse(201, {
        success: true,
        message: 'Telemetry received successfully',
        deviceId: saved.id,
        receivedAt: new Date().toISOString()
      });
    }

    // 3. Get all devices (GET /devices)
    if ((requestPath === '/devices' || requestPath === '/') && method === 'GET') {
      const devicesMap = await storage.getAllDevices();
      const devicesList = Object.values(devicesMap);
      const events = await storage.getRecentEvents();

      const summary = {
        total: devicesList.length,
        online: devicesList.filter(d => d.computedStatus === 'online').length,
        warning: devicesList.filter(d => d.computedStatus === 'warning').length,
        offline: devicesList.filter(d => d.computedStatus === 'offline').length,
        idle: devicesList.filter(d => d.computedStatus === 'idle').length
      };

      return jsonResponse(200, {
        devices: devicesList,
        summary,
        events: events.slice(0, 20),
        serverTime: Date.now()
      });
    }

    // 4. Device specific route (GET or DELETE /devices/:id)
    const deviceMatch = requestPath.match(/^\/devices\/([^/]+)$/);
    if (deviceMatch) {
      const targetId = decodeURIComponent(deviceMatch[1]);

      if (method === 'GET') {
        const device = await storage.getDevice(targetId);
        if (!device) {
          return jsonResponse(404, { error: `Device '${targetId}' not found` });
        }
        return jsonResponse(200, { device });
      }

      if (method === 'DELETE') {
        const deleted = await storage.deleteDevice(targetId);
        if (!deleted) {
          return jsonResponse(404, { error: `Device '${targetId}' not found` });
        }
        return jsonResponse(200, { success: true, message: `Device '${targetId}' deleted` });
      }
    }

    // 5. Simulator endpoint for quick testing without physical hardware
    if (requestPath === '/simulate' && method === 'POST') {
      const mockDevices = [
        {
          deviceId: 'edge-gateway-plc-01',
          deviceName: 'Siemens S7-1200 Edge Gateway',
          timestamp: Date.now(),
          system: {
            cpuTemp: +(46 + Math.random() * 8).toFixed(1),
            cpuUsage: +(12 + Math.random() * 15).toFixed(1),
            ramUsage: +(28 + Math.random() * 8).toFixed(1),
            ramUsedMB: 1146,
            ramTotalMB: 4096,
            diskUsage: 32.4,
            diskFreeGB: 21.6,
            uptimeSeconds: 86400 * 3 + 14200,
            ipAddress: '192.168.1.100',
            hostname: 'rpi4-plc-gateway',
            os: 'Linux 6.1.21-v8+ Raspberry Pi OS (64-bit)'
          },
          network: {
            lan1_plc: { interface: 'eth0', ip: '192.168.0.50', status: 'connected' },
            lan2_internet: { interface: 'eth1', ip: '192.168.1.100', status: 'up' }
          },
          redundancy: {
            bufferQueueDepth: 0,
            storeAndForwardActive: true,
            lastHeartbeat: Date.now()
          },
          plc: {
            connected: true,
            ip: '192.168.0.10',
            rack: 0,
            slot: 1,
            lifebit: Math.random() > 0.5 ? 1 : 0,
            tags: {
              spindle_temperature: { name: 'Main Spindle Temperature', address: 'DB1.DBD0', type: 'REAL', value: +(64.5 + Math.random() * 4).toFixed(1), unit: '°C', quality: 'GOOD' },
              motor_current: { name: 'Motor Phase Current', address: 'DB1.DBD4', type: 'REAL', value: +(14.2 + Math.random() * 1.5).toFixed(2), unit: 'A', quality: 'GOOD' },
              motor_voltage: { name: 'Supply Bus Voltage', address: 'DB1.DBD8', type: 'REAL', value: +(381.0 + Math.random() * 2).toFixed(1), unit: 'V', quality: 'GOOD' },
              hydraulic_pressure: { name: 'Hydraulic System Pressure', address: 'DB1.DBD12', type: 'REAL', value: +(120.4 + Math.random() * 4).toFixed(1), unit: 'bar', quality: 'GOOD' },
              pneumatic_pressure: { name: 'Pneumatic Air Pressure', address: 'DB1.DBD16', type: 'REAL', value: +(6.2 + Math.random() * 0.4).toFixed(2), unit: 'bar', quality: 'GOOD' },
              line_speed: { name: 'Conveyor Line Speed', address: 'DB1.DBD20', type: 'REAL', value: +(45.0 + Math.random() * 2).toFixed(1), unit: 'm/min', quality: 'GOOD' },
              vibration_level: { name: 'Spindle Bearing Vibration RMS', address: 'DB1.DBD24', type: 'REAL', value: +(1.24 + Math.random() * 0.2).toFixed(2), unit: 'mm/s', quality: 'GOOD' },
              coolant_flow_rate: { name: 'Coolant Liquid Flow Rate', address: 'DB1.DBD28', type: 'REAL', value: +(18.5 + Math.random() * 1.2).toFixed(1), unit: 'L/min', quality: 'GOOD' },
              coolant_temp: { name: 'Coolant Reservoir Temperature', address: 'DB1.DBD32', type: 'REAL', value: +(23.8 + Math.random() * 1.5).toFixed(1), unit: '°C', quality: 'GOOD' },
              total_production_count: { name: 'Total Output Production Units', address: 'DB1.DBD36', type: 'DINT', value: 4820, unit: 'pcs', quality: 'GOOD' },
              good_parts_count: { name: 'Passed Quality Units', address: 'DB1.DBD40', type: 'DINT', value: 4768, unit: 'pcs', quality: 'GOOD' },
              defect_parts_count: { name: 'Rejected Defect Units', address: 'DB1.DBD44', type: 'DINT', value: 52, unit: 'pcs', quality: 'GOOD' },
              cycle_time_current: { name: 'Current Cycle Duration', address: 'DB1.DBD48', type: 'REAL', value: +(12.4 + Math.random() * 0.8).toFixed(1), unit: 's', quality: 'GOOD' },
              cycle_time_target: { name: 'Target Standard Cycle Time', address: 'DB1.DBD52', type: 'REAL', value: 12.0, unit: 's', quality: 'GOOD' },
              machine_operating_hours: { name: 'Cumulative Running Hours', address: 'DB1.DBD56', type: 'REAL', value: 1428.5, unit: 'h', quality: 'GOOD' },
              machine_status_running: { name: 'Machine Run State', address: 'DB1.DBX60.0', type: 'BOOL', value: true, unit: 'state', quality: 'GOOD' },
              machine_status_fault: { name: 'Machine Fault Alarm Active', address: 'DB1.DBX60.1', type: 'BOOL', value: false, unit: 'state', quality: 'GOOD' },
              emergency_stop_ok: { name: 'Emergency Stop Healthy Status', address: 'DB1.DBX60.2', type: 'BOOL', value: true, unit: 'state', quality: 'GOOD' },
              active_alarm_code: { name: 'Active Fault Alarm Code', address: 'DB1.DBW62', type: 'INT', value: 0, unit: 'code', quality: 'GOOD' }
            }
          }
        },
        {
          deviceId: 'raspberry-pi-4-lab',
          deviceName: 'Pi 4B • Lab Server',
          timestamp: Date.now(),
          system: {
            cpuTemp: +(42 + Math.random() * 15).toFixed(1),
            cpuUsage: +(15 + Math.random() * 45).toFixed(1),
            ramUsage: +(38 + Math.random() * 20).toFixed(1),
            ramUsedMB: 1540,
            ramTotalMB: 4096,
            diskUsage: 54.2,
            diskFreeGB: 28.4,
            uptimeSeconds: 345600,
            ipAddress: '192.168.1.142',
            hostname: 'rpi4-lab',
            os: 'Linux 6.1.21-v8+ Debian 12'
          },
          sensors: {
            ambientTemp: +(24 + Math.random() * 4).toFixed(1),
            humidity: +(50 + Math.random() * 15).toFixed(1),
            pressure: 1012.4
          }
        },
        {
          deviceId: 'raspberry-pi-zero-2w-garden',
          deviceName: 'Pi Zero 2W • Greenhouse',
          timestamp: Date.now() - 15000,
          system: {
            cpuTemp: +(52 + Math.random() * 12).toFixed(1),
            cpuUsage: +(8 + Math.random() * 25).toFixed(1),
            ramUsage: +(45 + Math.random() * 10).toFixed(1),
            ramUsedMB: 230,
            ramTotalMB: 512,
            diskUsage: 31.8,
            diskFreeGB: 11.2,
            uptimeSeconds: 124500,
            ipAddress: '192.168.1.189',
            hostname: 'rpi-zero-garden',
            os: 'Linux 6.1.21-v7+ Raspberry Pi OS Lite'
          },
          sensors: {
            ambientTemp: +(29.5 + Math.random() * 3).toFixed(1),
            humidity: +(68 + Math.random() * 8).toFixed(1),
            soilMoisture: +(42 + Math.random() * 10).toFixed(1)
          }
        }
      ];

      for (const d of mockDevices) {
        await storage.saveTelemetry(d);
      }

      return jsonResponse(200, {
        success: true,
        message: 'Generated simulated Raspberry Pi telemetry data',
        devices: mockDevices.map(d => d.deviceId)
      });
    }

    return jsonResponse(404, {
      error: 'Not Found',
      availableEndpoints: [
        'POST /api/telemetry',
        'POST /api/heartbeat',
        'GET /api/devices',
        'GET /api/devices/:id',
        'DELETE /api/devices/:id',
        'POST /api/simulate',
        'GET /api/health'
      ]
    });

  } catch (error) {
    console.error('API Error:', error);
    return jsonResponse(500, {
      error: 'Internal Server Error',
      message: error.message
    });
  }
};
