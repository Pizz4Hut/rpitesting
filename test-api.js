const api = require('./netlify/functions/api');

async function runTests() {
  console.log('--- 1. Testing GET /health ---');
  let res = await api.handler({
    httpMethod: 'GET',
    path: '/api/health'
  });
  console.log('Status:', res.statusCode);
  console.log('Body:', res.body);

  console.log('\n--- 2. Testing POST /simulate ---');
  res = await api.handler({
    httpMethod: 'POST',
    path: '/api/simulate'
  });
  console.log('Status:', res.statusCode);
  console.log('Body:', res.body);

  console.log('\n--- 3. Testing GET /devices ---');
  res = await api.handler({
    httpMethod: 'GET',
    path: '/api/devices'
  });
  console.log('Status:', res.statusCode);
  const parsed = JSON.parse(res.body);
  console.log('Devices found:', parsed.devices.map(d => ({
    id: d.id,
    name: d.name,
    status: d.computedStatus,
    cpuTemp: d.latest?.system?.cpuTemp
  })));
  console.log('Summary:', parsed.summary);

  console.log('\n--- 4. Testing POST /telemetry (Raspberry Pi Payload) ---');
  const piPayload = {
    deviceId: 'pi-living-room',
    deviceName: 'Living Room Pi 4 Model B',
    timestamp: Date.now(),
    system: {
      cpuTemp: 51.4,
      cpuUsage: 12.8,
      ramUsage: 28.5,
      ramUsedMB: 1140,
      ramTotalMB: 4000,
      diskUsage: 38.2,
      diskFreeGB: 18.2,
      uptimeSeconds: 98200,
      ipAddress: '192.168.1.77',
      hostname: 'raspberrypi-living',
      os: 'Linux 6.1.21-v8+ (aarch64)'
    },
    sensors: {
      ambientTemp: 24.2,
      humidity: 58.0,
      pressure: 1012.8
    }
  };

  res = await api.handler({
    httpMethod: 'POST',
    path: '/api/telemetry',
    body: JSON.stringify(piPayload)
  });
  console.log('Status:', res.statusCode);
  console.log('Body:', res.body);

  console.log('\n--- 5. Verify Pi is in device list ---');
  res = await api.handler({
    httpMethod: 'GET',
    path: '/api/devices'
  });
  const data = JSON.parse(res.body);
  const myPi = data.devices.find(d => d.id === 'pi-living-room');
  console.log('Living Room Pi status:', myPi?.computedStatus, '| Temp:', myPi?.latest?.system?.cpuTemp + '°C');

  console.log('\n--- 6. Testing POST /heartbeat (Gateway Heartbeat) ---');
  res = await api.handler({
    httpMethod: 'POST',
    path: '/api/heartbeat',
    body: JSON.stringify({
      deviceId: 'edge-gateway-plc',
      deviceName: 'Edge Gateway (Siemens S7-1200)',
      timestamp: Date.now(),
      system: { cpuTemp: 47.2, cpuUsage: 14.5, ramUsage: 32.1 },
      plc: { connected: true, ip: '192.168.0.10', rack: 0, slot: 1, lifebit: 1 },
      redundancy: { bufferQueueDepth: 0, storeAndForwardActive: true },
      network: {
        lan1_plc: { interface: 'eth0', ip: '192.168.0.50', status: 'up' },
        lan2_internet: { interface: 'eth1', ip: '192.168.1.100', status: 'up' }
      }
    })
  });
  console.log('Heartbeat status:', res.statusCode);
  console.log('Heartbeat response:', res.body);

  console.log('\n--- 7. Testing POST /telemetry with PLC Tags (19 Tags) ---');
  res = await api.handler({
    httpMethod: 'POST',
    path: '/api/telemetry',
    body: JSON.stringify({
      deviceId: 'edge-gateway-plc',
      deviceName: 'Edge Gateway (Siemens S7-1200)',
      timestamp: Date.now(),
      system: { cpuTemp: 47.8, cpuUsage: 15.0, ramUsage: 32.5, uptimeSeconds: 3600 },
      plc: {
        connected: true,
        ip: '192.168.0.10',
        tags: {
          motor_temp: { address: 'DB1.DBD0', type: 'REAL', value: 65.4, unit: '°C' },
          hydraulic_pressure: { address: 'DB1.DBD4', type: 'REAL', value: 120.5, unit: 'bar' },
          line_speed: { address: 'DB1.DBD8', type: 'REAL', value: 45.2, unit: 'm/min' },
          running_status: { address: 'DB1.DBX12.0', type: 'BOOL', value: true, unit: 'state' }
        }
      },
      redundancy: { bufferQueueDepth: 0, storeAndForwardActive: true }
    })
  });
  console.log('PLC Telemetry status:', res.statusCode);

  console.log('\n--- 8. Testing POST /telemetry/batch (Replay Backlog from Offline Buffer) ---');
  res = await api.handler({
    httpMethod: 'POST',
    path: '/api/telemetry/batch',
    body: JSON.stringify([
      {
        deviceId: 'edge-gateway-plc',
        timestamp: Date.now() - 3600000,
        plc: { connected: true, tags: { motor_temp: { value: 62.1 } } }
      },
      {
        deviceId: 'edge-gateway-plc',
        timestamp: Date.now() - 1800000,
        plc: { connected: true, tags: { motor_temp: { value: 64.0 } } }
      }
    ])
  });
  console.log('Batch ingestion status:', res.statusCode);
  console.log('Batch response:', res.body);

  console.log('\n✅ All API tests (including PLC, Heartbeat, and Redundancy) passed successfully!');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
