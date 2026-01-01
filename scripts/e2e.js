#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');

function getNpmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

function getNpxCommand() {
  return process.platform === 'win32' ? 'npx.cmd' : 'npx';
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function emptyDir(dirPath) {
  await fs.rm(dirPath, { recursive: true, force: true });
  await ensureDir(dirPath);
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => server.close(() => resolve(true)));
    server.listen(port);
  });
}

async function findFreePort(startPort, maxAttempts = 50) {
  const base = Number(startPort);
  if (!Number.isInteger(base) || base <= 0) throw new Error(`Invalid start port: ${startPort}`);
  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const port = base + offset;
    // eslint-disable-next-line no-await-in-loop
    if (await isPortFree(port)) return port;
  }
  throw new Error(`No free port found in range ${base}-${base + maxAttempts - 1}`);
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      ...options
    });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(' ')} exited with code ${code}`));
    });
  });
}

async function waitForHttpOk(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // ignore
    }
    if (Date.now() > deadline) {
      throw new Error(`Timed out waiting for ${url}`);
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(200);
  }
}

function taskFrontmatter({ title, stage, status, priority = 'Low', model }) {
  return [
    '---',
    `title: ${title}`,
    `stage: ${stage}`,
    `status: ${status}`,
    `priority: ${priority}`,
    'agenticHarness: opencode',
    `modelProvider: ${model.modelProvider}`,
    `modelName: ${model.modelName}`,
    '---',
    '',
    '# Description',
    '',
    'E2E fixture task.',
    ''
  ].join('\n');
}

function parseModelFullName(fullName) {
  const raw = String(fullName || '').trim();
  const parts = raw.split('/');
  if (parts.length < 2 || !parts[0] || !parts[1]) {
    throw new Error(`Invalid model full name: ${fullName}`);
  }
  return {
    fullName: raw,
    modelProvider: parts[0],
    modelName: parts.slice(1).join('/')
  };
}

async function setupProjectRepo(projectPath, model) {
  await ensureDir(projectPath);

  await runCommand('git', ['init'], { cwd: projectPath });
  await runCommand('git', ['config', 'user.email', 'ncrew-e2e@example.local'], { cwd: projectPath });
  await runCommand('git', ['config', 'user.name', 'NCrew E2E'], { cwd: projectPath });

  await fs.writeFile(path.join(projectPath, 'README.md'), '# NCrew E2E Project\n', 'utf-8');
  await fs.writeFile(
    path.join(projectPath, '.gitignore'),
    [
      'node_modules/',
      '.memory_bank/logs/',
      '.memory_bank/tasks/*-history.json',
      'worktrees/',
      ''
    ].join('\n'),
    'utf-8'
  );

  const tasksDir = path.join(projectPath, '.memory_bank', 'tasks');
  await ensureDir(tasksDir);

  await fs.writeFile(
    path.join(tasksDir, 'e2e-spec-run.md'),
    taskFrontmatter({ title: 'E2E Spec Run', stage: 'Specification', status: 'New', priority: 'Medium', model }),
    'utf-8'
  );

  await fs.writeFile(
    path.join(tasksDir, 'e2e-stop.md'),
    taskFrontmatter({ title: 'E2E Stop (Long Run)', stage: 'Plan', status: 'New', model }),
    'utf-8'
  );

  await fs.writeFile(
    path.join(tasksDir, 'e2e-next-stage.md'),
    taskFrontmatter({ title: 'E2E Next Stage', stage: 'Plan', status: 'Done', model }),
    'utf-8'
  );

  await fs.writeFile(
    path.join(tasksDir, 'e2e-last-stage.md'),
    taskFrontmatter({ title: 'E2E Last Stage', stage: 'Verification', status: 'Done', model }),
    'utf-8'
  );

  await runCommand('git', ['add', '.'], { cwd: projectPath });
  await runCommand('git', ['commit', '-m', 'E2E fixtures'], { cwd: projectPath });
}

async function main() {
  const repoRoot = path.resolve(__dirname, '..');
  const tmpRoot = path.join(repoRoot, '.tmp', 'e2e');
  const keepTmp = process.env.E2E_KEEP_TMP === '1' || process.env.E2E_KEEP_TMP === 'true';

  const modelFullName = process.env.E2E_MODEL_FULL_NAME || 'opencode/glm-4.7-free';
  const model = parseModelFullName(modelFullName);

  const ncrewHome = path.join(tmpRoot, 'ncrew-home');
  const projectPath = path.join(tmpRoot, 'project');
  const projectName = 'e2e-project';
  const projectId = projectName.toLowerCase().replace(/\s+/g, '-');
  const worktreePrefix = 'e2e-';

  const fakeBinDir = path.join(repoRoot, 'tests', 'e2e', 'bin');
  const fakeOpencode = path.join(fakeBinDir, 'opencode');
  await fs.chmod(fakeOpencode, 0o755);

  if (!keepTmp) {
    await emptyDir(tmpRoot);
  } else {
    await ensureDir(tmpRoot);
  }

  await setupProjectRepo(projectPath, model);

  // Build frontend for production (backend serves frontend/dist).
  await runCommand(getNpmCommand(), ['-C', 'frontend', 'run', 'build'], {
    cwd: repoRoot,
    env: { ...process.env }
  });

  const port = await findFreePort(Number(process.env.E2E_PORT || 4300), 200);
  const baseUrl = `http://127.0.0.1:${port}`;

  const backendEntry = path.join(repoRoot, 'backend', 'server.js');
  const serverEnv = {
    ...process.env,
    PORT: String(port),
    NCREW_HOME: ncrewHome,
    E2E_MODEL_FULL_NAME: model.fullName,
    PATH: `${fakeBinDir}${path.delimiter}${process.env.PATH || ''}`,
    FAKE_OPENCODE_SLEEP_MS: '50',
    FAKE_OPENCODE_SLOW_TASKS: 'e2e-stop',
    FAKE_OPENCODE_SLOW_MS: '30000'
  };

  const server = spawn(process.execPath, [backendEntry], {
    cwd: repoRoot,
    env: serverEnv,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  server.stdout.on('data', (chunk) => process.stdout.write(`[e2e-server] ${chunk}`));
  server.stderr.on('data', (chunk) => process.stderr.write(`[e2e-server] ${chunk}`));

  let serverExited = false;
  server.on('exit', () => {
    serverExited = true;
  });

  try {
    await waitForHttpOk(`${baseUrl}/api/projects`, 20_000);

    const playwrightArgs = ['playwright', 'test', '-c', 'playwright.e2e.config.js'];
    if (process.env.E2E_HEADED === '1' || process.env.E2E_HEADED === 'true') {
      playwrightArgs.push('--headed');
    }

    await runCommand(getNpxCommand(), playwrightArgs, {
      cwd: repoRoot,
      env: {
        ...process.env,
        E2E_BASE_URL: baseUrl,
        E2E_PROJECT_NAME: projectName,
        E2E_PROJECT_ID: projectId,
        E2E_PROJECT_PATH: projectPath,
        E2E_WORKTREE_PREFIX: worktreePrefix,
        E2E_MODEL_FULL_NAME: model.fullName
      }
    });
  } finally {
    if (!serverExited) {
      server.kill('SIGTERM');
      await sleep(800);
      if (!serverExited) server.kill('SIGKILL');
    }

    if (!keepTmp) {
      await fs.rm(tmpRoot, { recursive: true, force: true });
    }
  }
}

main().catch((err) => {
  console.error('[e2e] Failed:', err);
  process.exit(1);
});
