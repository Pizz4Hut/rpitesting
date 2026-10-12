const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 8888;
const PUBLIC_DIR = path.resolve(__dirname, 'public');
const apiHandler = require('./netlify/functions/api').handler;

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;

  // Emulate Netlify Functions routing for /api/* and /.netlify/functions/api/*
  if (pathname.startsWith('/api') || pathname.startsWith('/.netlify/functions/api')) {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString();
    });

    req.on('end', async () => {
      try {
        const event = {
          httpMethod: req.method,
          path: pathname,
          rawUrl: `http://${req.headers.host}${req.url}`,
          headers: req.headers,
          queryStringParameters: parsedUrl.query,
          body: body || null
        };

        const result = await apiHandler(event, {});

        res.statusCode = result.statusCode || 200;
        if (result.headers) {
          Object.entries(result.headers).forEach(([k, v]) => res.setHeader(k, v));
        }
        res.end(result.body || '');
      } catch (err) {
        console.error('Server error handling function:', err);
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ error: 'Internal Server Error', message: err.message }));
      }
    });
    return;
  }

  // Serve static files from public/
  let filePath = path.join(PUBLIC_DIR, pathname === '/' ? 'index.html' : pathname);

  // Security: prevent directory traversal
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.statusCode = 403;
    res.end('Forbidden');
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      // Fallback to index.html for SPA if not found
      filePath = path.join(PUBLIC_DIR, 'index.html');
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    fs.readFile(filePath, (readErr, content) => {
      if (readErr) {
        res.statusCode = 404;
        res.end('Not Found');
        return;
      }

      res.statusCode = 200;
      res.setHeader('Content-Type', contentType);
      res.end(content);
    });
  });
});

server.listen(PORT, () => {
  console.log(`\n======================================================`);
  console.log(`🚀 Netlify Raspberry Pi IoT Dashboard is running!`);
  console.log(`📡 Local URL:   http://localhost:${PORT}`);
  console.log(`🔌 API Endpoint: http://localhost:${PORT}/api/telemetry`);
  console.log(`📊 Device List:  http://localhost:${PORT}/api/devices`);
  console.log(`======================================================\n`);
});
