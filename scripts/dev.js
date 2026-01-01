const net = require('net');
const path = require('path');
const { spawn } = require('child_process');

function getNpmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const tester = net.createServer();

    tester.once('error', (err) => {
      if (err && err.code === 'EADDRINUSE') return resolve(false);
      resolve(false);
    });

    tester.once('listening', () => {
      tester.close(() => resolve(true));
    });

    tester.listen(port);
  });
}

async function findFreePort(startPort, maxAttempts = 50) {
  const base = Number(startPort);
  if (!Number.isInteger(base) || base <= 0) {
    throw new Error(`Invalid start port: ${startPort}`);
  }

  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const port = base + offset;
    // eslint-disable-next-line no-await-in-loop
    if (await isPortFree(port)) return port;
  }

  throw new Error(`No free port found in range ${base}-${base + maxAttempts - 1}`);
}

function prefixStream(stream, prefix, target) {
  if (!stream) return;

  let buffered = '';
  stream.on('data', (chunk) => {
    buffered += chunk.toString();
    let idx = buffered.indexOf('\n');
    while (idx !== -1) {
      const line = buffered.slice(0, idx + 1);
      buffered = buffered.slice(idx + 1);
      target.write(`${prefix}${line}`);
      idx = buffered.indexOf('\n');
    }
  });

  stream.on('end', () => {
    if (buffered) target.write(`${prefix}${buffered}\n`);
  });
}

async function main() {
  const requestedBackendPortRaw = process.env.NCREW_BACKEND_PORT || process.env.PORT || process.env.NCREW_PORT || '3001';
  const parsedRequested = Number.parseInt(String(requestedBackendPortRaw), 10);
  const requestedBackendPort = Number.isInteger(parsedRequested) && parsedRequested > 0 ? parsedRequested : 3001;

  const backendPort = await findFreePort(requestedBackendPort, 50);
  const backendUrl = `http://localhost:${backendPort}`;

  const repoRoot = path.join(__dirname, '..');
  const backendEntry = path.join(repoRoot, 'backend', 'server.js');
  const frontendCwd = path.join(repoRoot, 'frontend');

  if (backendPort !== requestedBackendPort) {
    process.stdout.write(`[dev] Backend port ${requestedBackendPort} is busy, using ${backendPort} instead.\n`);
  }
  process.stdout.write(`[dev] Vite proxy target: ${backendUrl}\n`);

  const backend = spawn(process.execPath, [backendEntry], {
    env: { ...process.env, PORT: String(backendPort) },
    stdio: ['inherit', 'pipe', 'pipe']
  });

  const frontend = spawn(getNpmCommand(), ['run', 'dev'], {
    cwd: frontendCwd,
    env: { ...process.env, VITE_BACKEND_URL: backendUrl },
    stdio: ['inherit', 'pipe', 'pipe']
  });

  prefixStream(backend.stdout, '[backend] ', process.stdout);
  prefixStream(backend.stderr, '[backend] ', process.stderr);
  prefixStream(frontend.stdout, '[frontend] ', process.stdout);
  prefixStream(frontend.stderr, '[frontend] ', process.stderr);

  let closing = false;
  const closeAll = (signal) => {
    if (closing) return;
    closing = true;
    backend.kill(signal);
    frontend.kill(signal);
  };

  process.on('SIGINT', () => closeAll('SIGINT'));
  process.on('SIGTERM', () => closeAll('SIGTERM'));

  let backendExit = null;
  let frontendExit = null;
  const maybeExit = () => {
    if (!backendExit || !frontendExit) return;

    // Prefer a non-zero exit code if any process failed.
    const code = (backendExit.code ?? 0) || (frontendExit.code ?? 0);
    process.exit(code);
  };

  backend.on('exit', (code, signal) => {
    backendExit = { code, signal };
    if (!closing) closeAll('SIGTERM');
    maybeExit();
  });

  frontend.on('exit', (code, signal) => {
    frontendExit = { code, signal };
    if (!closing) closeAll('SIGTERM');
    maybeExit();
  });
}

main().catch((err) => {
  console.error('[dev] Failed to start:', err);
  process.exit(1);
});
