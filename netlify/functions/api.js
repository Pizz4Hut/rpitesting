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

    // 2. Telemetry ingestion (POST /telemetry or root POST)
    if ((requestPath === '/telemetry' || requestPath === '/') && method === 'POST') {
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
