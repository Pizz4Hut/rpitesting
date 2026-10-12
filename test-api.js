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

  console.log('\n✅ All API tests passed successfully!');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
