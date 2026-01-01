const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs-extra');
const { exec, execFile, spawn } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

const {
  getNcrewHomeDir,
  getProjectsDir,
  getModelsCacheFile,
  getTaskLogsDir
} = require('./utils/paths');
const { initNcrewStructure } = require('./utils/init');
const { migrateOldSettings } = require('./utils/migrate');

const app = express();
const DEFAULT_PORT = 3001;
const envPortRaw = process.env.PORT ?? process.env.NCREW_BACKEND_PORT ?? process.env.NCREW_PORT;
const envPort = Number(envPortRaw);
const PORT = Number.isInteger(envPort) && envPort > 0 ? envPort : DEFAULT_PORT;
const SETTINGS_DIR = getProjectsDir();
const MODELS_CACHE_FILE = getModelsCacheFile();
const CACHE_TTL = 24 * 60 * 60 * 1000;
const RUNNING_TASKS = new Map();
const STAGES = ['Specification', 'Plan', 'Implementation', 'Verification'];

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend/dist')));

function getTaskKey(projectId, taskId) {
  return `${projectId}:${taskId}`;
}

function withFullName(model) {
  if (!model) return null;
  const modelProvider = model.modelProvider || model.provider;
  const modelName = model.modelName || model.name;
  if (!modelProvider || !modelName) return { ...model };
  return { ...model, fullName: `${modelProvider}/${modelName}` };
}

function normalizeStageForFileName(stage) {
  return String(stage || '').trim().toLowerCase();
}

function replaceAllLiteral(haystack, needle, replacement) {
  if (!needle) return haystack;
  return String(haystack).split(String(needle)).join(String(replacement));
}

function toPosixPath(filePath) {
  return String(filePath).split(path.sep).join(path.posix.sep);
}

async function ensureWorktreeTemplateFile(worktreePath, templateFileName) {
  const source = path.join(getNcrewHomeDir(), 'templates', templateFileName);
  const targetDir = path.join(worktreePath, '.ncrew', 'templates');
  const target = path.join(targetDir, templateFileName);
  await fs.ensureDir(targetDir);

  try {
    await fs.copy(source, target, { overwrite: true });
  } catch (error) {
    console.warn(`[NCrew] Failed to copy template into worktree: ${source} -> ${target}`, error);
  }

  return path.posix.join('.ncrew', 'templates', templateFileName);
}

function rewriteNcrewTemplatePathsInPrompt(prompt, replacements) {
  let result = String(prompt || '');

  const ncrewHome = getNcrewHomeDir();
  const mappings = [
    {
      variants: ['~/.ncrew/templates/spec.md', path.join(ncrewHome, 'templates', 'spec.md'), toPosixPath(path.join(ncrewHome, 'templates', 'spec.md'))],
      replacement: replacements.spec_template
    },
    {
      variants: ['~/.ncrew/templates/plan.md', path.join(ncrewHome, 'templates', 'plan.md'), toPosixPath(path.join(ncrewHome, 'templates', 'plan.md'))],
      replacement: replacements.plan_template
    }
  ];

  for (const { variants, replacement } of mappings) {
    if (!replacement) continue;
    for (const variant of variants) {
      if (!variant) continue;
      result = replaceAllLiteral(result, variant, replacement);
    }
  }

  return result;
}

async function fetchModels() {
  try {
    const { stdout } = await execAsync('opencode models');
    const lines = stdout.trim().split('\n');
    return lines.map(line => {
      const [provider, name] = line.split('/');
      return { provider, name, fullName: line };
    });
  } catch (error) {
    console.error('Error fetching models:', error);
    throw new Error('Failed to fetch models from opencode');
  }
}

function groupModelsByProvider(models) {
  const grouped = {};
  models.forEach(model => {
    if (!grouped[model.provider]) {
      grouped[model.provider] = [];
    }
    grouped[model.provider].push(model);
  });
  return grouped;
}

async function loadCachedModels() {
  try {
    if (await fs.pathExists(MODELS_CACHE_FILE)) {
      const cache = await fs.readJson(MODELS_CACHE_FILE);
      const now = new Date().getTime();
      const cachedAt = new Date(cache.cachedAt).getTime();
      
      if (now - cachedAt < CACHE_TTL) {
        return cache;
      }
    }
    return null;
  } catch (error) {
    console.error('Error loading cached models:', error);
    return null;
  }
}

async function saveCachedModels(models) {
  const now = new Date();
  const expiresAt = new Date(now.getTime() + CACHE_TTL);
  
  const cache = {
    models,
    cachedAt: now.toISOString(),
    expiresAt: expiresAt.toISOString()
  };
  
  await fs.writeJson(MODELS_CACHE_FILE, cache, { spaces: 2 });
  return cache;
}

function parseGitWorktreeListPorcelain(porcelainOutput) {
  const worktrees = [];
  const lines = String(porcelainOutput || '').split('\n');
  let current = null;

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line) continue;

    if (line.startsWith('worktree ')) {
      if (current) worktrees.push(current);
      current = {
        path: line.slice('worktree '.length).trim(),
        head: null,
        branch: null,
        detached: false
      };
      continue;
    }

    if (!current) continue;

    if (line.startsWith('HEAD ')) {
      current.head = line.slice('HEAD '.length).trim();
      continue;
    }

    if (line.startsWith('branch ')) {
      current.branch = line.slice('branch '.length).trim();
      continue;
    }

    if (line === 'detached') {
      current.detached = true;
    }
  }

  if (current) worktrees.push(current);
  return worktrees;
}

async function listGitWorktrees(projectPath) {
  const { stdout } = await execFileAsync('git', ['worktree', 'list', '--porcelain'], {
    cwd: projectPath
  });
  return parseGitWorktreeListPorcelain(stdout);
}

async function doesGitBranchExist(projectPath, branchName) {
  const ref = `refs/heads/${branchName}`;
  try {
    await execFileAsync('git', ['show-ref', '--verify', '--quiet', ref], {
      cwd: projectPath
    });
    return true;
  } catch (error) {
    if (error && (error.code === 1 || error.code === '1')) return false;
    throw error;
  }
}

async function createWorktree(projectPath, taskId, worktreePrefix) {
  const safePrefix = String(worktreePrefix || 'task-');
  const safeTaskId = String(taskId || '').replace(/[^a-zA-Z0-9._-]/g, '-');
  const branchName = `${safePrefix}${safeTaskId}`;
  const worktreesDir = path.join(projectPath, 'worktrees');
  const worktreePath = path.join(worktreesDir, branchName);
  
  try {
    await fs.ensureDir(worktreesDir);
    const worktrees = await listGitWorktrees(projectPath);
    const branchRef = `refs/heads/${branchName}`;
    const existingForBranch = worktrees.find(worktree => worktree.branch === branchRef);

    if (existingForBranch && existingForBranch.path) {
      return { branchName, worktreePath: existingForBranch.path };
    }

    const branchExists = await doesGitBranchExist(projectPath, branchName);
    const args = ['worktree', 'add', worktreePath];
    if (branchExists) args.push(branchName);
    else args.push('-b', branchName);

    await execFileAsync('git', args, { cwd: projectPath });
    return { branchName, worktreePath };
  } catch (error) {
    console.error('Error creating worktree:', error);
    throw new Error('Failed to create worktree');
  }
}

async function getStagePrompt(stage) {
  const stageName = String(stage || 'Specification').toLowerCase();
  const promptPath = path.join(getNcrewHomeDir(), 'stage_prompts', `${stageName}.md`);

  try {
    if (await fs.pathExists(promptPath)) {
      return await fs.readFile(promptPath, 'utf-8');
    }
  } catch (error) {
    console.error(`Error reading stage prompt for ${stage}:`, error);
  }

  return 'Please read and execute the task.';
}

function replaceVariables(prompt, variables) {
  let result = prompt;

  for (const [key, value] of Object.entries(variables)) {
    const regex = new RegExp(`\\{${key}\\}`, 'g');
    result = result.replace(regex, value);
  }

  return result;
}

async function getModels(forceRefresh = false) {
  if (!forceRefresh) {
    const cached = await loadCachedModels();
    if (cached) {
      return cached;
    }
  }
  
  const models = await fetchModels();
  return await saveCachedModels(models);
}

async function readTaskHistory(tasksDir, taskId) {
  const historyFile = path.join(tasksDir, `${taskId}-history.json`);

  try {
    if (!await fs.pathExists(historyFile)) {
      return { history: [] };
    }

    const data = await fs.readJson(historyFile);
    if (!data || !Array.isArray(data.history)) {
      return { history: [] };
    }

    return data;
  } catch (error) {
    console.error('Error reading task history:', error);
    return { history: [] };
  }
}

async function appendHistoryEntry(tasksDir, taskId, entry) {
  const historyFile = path.join(tasksDir, `${taskId}-history.json`);
  const current = await readTaskHistory(tasksDir, taskId);
  current.history.push(entry);
  await fs.writeJson(historyFile, current, { spaces: 2 });
}

async function updateHistoryEntry(tasksDir, taskId, runId, updates) {
  const historyFile = path.join(tasksDir, `${taskId}-history.json`);
  const current = await readTaskHistory(tasksDir, taskId);
  const idx = current.history.findIndex(h => h.id === runId);
  if (idx < 0) return;
  current.history[idx] = { ...current.history[idx], ...updates };
  await fs.writeJson(historyFile, current, { spaces: 2 });
}

async function listTaskLogFiles(projectPath, taskId) {
  const logsDir = getTaskLogsDir(projectPath);
  if (!await fs.pathExists(logsDir)) return [];

  const files = await fs.readdir(logsDir);
  const prefix = `${taskId}-`;
  const escapedTaskId = String(taskId).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const logPattern = new RegExp('^' + escapedTaskId + '-(.+?)-(\\d+)\\.log$');
  return files
    .filter(f => f.startsWith(prefix) && f.endsWith('.log'))
    .map(file => {
      const match = file.match(logPattern);
      return {
        file,
        stage: match ? match[1] : null,
        timestamp: match ? Number(match[2]) : null
      };
    })
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
}

async function readLogFile(projectPath, logFile, maxBytes = 1024 * 1024) {
  const safeName = path.basename(logFile);
  if (safeName !== logFile) {
    throw new Error('Invalid log file name');
  }

  const logsDir = getTaskLogsDir(projectPath);
  const fullPath = path.join(logsDir, safeName);
  if (!await fs.pathExists(fullPath)) {
    throw new Error('Log file not found');
  }

  const stat = await fs.stat(fullPath);
  if (stat.size <= maxBytes) {
    return await fs.readFile(fullPath, 'utf-8');
  }

  const fd = await fs.open(fullPath, 'r');
  try {
    const buffer = Buffer.alloc(maxBytes);
    await fs.read(fd, buffer, 0, maxBytes, stat.size - maxBytes);
    return buffer.toString('utf-8');
  } finally {
    await fs.close(fd);
  }
}

app.get('/api/projects', async (req, res) => {
  try {
    if (!await fs.pathExists(SETTINGS_DIR)) {
      await fs.ensureDir(SETTINGS_DIR);
      return res.json([]);
    }

    const files = await fs.readdir(SETTINGS_DIR);
    const projects = [];

    for (const file of files) {
      if (file.endsWith('.json')) {
        try {
          const content = await fs.readJson(path.join(SETTINGS_DIR, file));
          const projectPath = content.path;

          const isAccessible = await fs.pathExists(projectPath);
	          const project = {
	            id: file.replace('.json', ''),
	            name: content.name || file.replace('.json', ''),
	            path: projectPath,
	            worktreePrefix: content.worktreePrefix || 'task-',
	            defaultModel: withFullName(content.defaultModel || null),
	            isAccessible,
	            error: isAccessible ? null : 'Project path not accessible'
	          };
	          projects.push(project);
	        } catch (err) {
          console.error(`Error reading project config ${file}:`, err);
        }
      }
    }

    res.json(projects);
  } catch (err) {
    console.error('Error listing projects:', err);
    res.status(500).json({ error: 'Failed to list projects' });
  }
});

app.get('/api/projects/:projectId/tasks', async (req, res) => {
  try {
    const { projectId } = req.params;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');

    if (!await fs.pathExists(tasksPath)) {
      return res.json([]);
    }

    const files = await fs.readdir(tasksPath);
    const tasks = [];

    const defaultModel = config.defaultModel || {
      agenticHarness: 'opencode',
      modelProvider: 'opencode',
      modelName: 'claude-sonnet-4-5'
    };

    for (const file of files) {
      if (file.endsWith('.md')) {
        try {
          const fullPath = path.join(tasksPath, file);
          const content = await fs.readFile(fullPath, 'utf-8');
	          const taskId = file.replace('.md', '');
	          const frontmatter = parseFrontmatter(content);
	          const { title = taskId, status = 'New', priority = 'Medium' } = frontmatter;
	          const modelProvider = frontmatter.modelProvider || defaultModel.modelProvider;
	          const modelName = frontmatter.modelName || defaultModel.modelName;
	          const history = await readTaskHistory(tasksPath, taskId);

	          tasks.push({
	            id: taskId,
	            title,
	            status,
	            priority,
	            stage: frontmatter.stage || 'Specification',
	            startedAt: frontmatter.startedAt || null,
	            model: withFullName({
	              agenticHarness: frontmatter.agenticHarness || defaultModel.agenticHarness,
	              modelProvider,
	              modelName
	            }),
	            history: history.history,
	            executions: history.history,
	            logs: await listTaskLogFiles(config.path, taskId)
	          });
	        } catch (err) {
	          console.error(`Error reading task ${file}:`, err);
	        }
      }
    }

    res.json(tasks);
  } catch (err) {
    console.error('Error listing tasks:', err);
    res.status(500).json({ error: 'Failed to list tasks' });
  }
});

app.get('/api/models', async (req, res) => {
  try {
    const cache = await getModels();
    res.json(cache);
  } catch (error) {
    console.error('Error getting models:', error);
    res.status(503).json({ error: 'opencode not found in PATH or failed to execute' });
  }
});

app.post('/api/models/refresh', async (req, res) => {
  try {
    const cache = await getModels(true);
    res.json(cache);
  } catch (error) {
    console.error('Error refreshing models:', error);
    res.status(503).json({ error: 'opencode not found in PATH or failed to execute' });
  }
});

app.post('/api/projects', async (req, res) => {
  try {
    const { name, path: projectPath, worktreePrefix = 'task-', defaultModel } = req.body;

    if (!name || !projectPath) {
      return res.status(400).json({ error: 'Name and path are required' });
    }

    const isAccessible = await fs.pathExists(projectPath);
    if (!isAccessible) {
      return res.status(400).json({ error: 'Project path not accessible' });
    }

    if (defaultModel) {
      const modelsCache = await loadCachedModels();
      if (modelsCache) {
        const modelExists = modelsCache.models.some(m => m.fullName === `${defaultModel.modelProvider}/${defaultModel.modelName}`);
        if (!modelExists) {
          return res.status(400).json({ error: 'Selected model not available' });
        }
      }
    }

    const projectId = name.toLowerCase().replace(/\s+/g, '-');
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (await fs.pathExists(configPath)) {
      return res.status(400).json({ error: 'Project already exists' });
    }

    const projectConfig = {
      name,
      path: projectPath,
      worktreePrefix,
      createdAt: new Date().toISOString()
    };

    if (defaultModel) {
      projectConfig.defaultModel = defaultModel;
    }

    await fs.writeJson(configPath, projectConfig, { spaces: 2 });

	    res.json({
	      id: projectId,
	      name,
	      path: projectPath,
	      worktreePrefix,
	      isAccessible: true,
	      defaultModel: withFullName(defaultModel)
	    });
	  } catch (err) {
    console.error('Error creating project:', err);
    res.status(500).json({ error: 'Failed to create project' });
  }
});

app.put('/api/projects/:id', async (req, res) => {
  try {
    const { name, worktreePrefix, defaultModel, confirmWorktreePrefixChange } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${req.params.id}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);

    const hasDefaultModelField = Object.prototype.hasOwnProperty.call(req.body, 'defaultModel');
    if (defaultModel && typeof defaultModel === 'object') {
      const modelsCache = await loadCachedModels();
      if (modelsCache) {
        const modelExists = modelsCache.models.some(m => m.fullName === `${defaultModel.modelProvider}/${defaultModel.modelName}`);
        if (!modelExists) {
          return res.status(400).json({ error: 'Selected model not available' });
        }
      }
    }

    if (name) {
      config.name = name;
    }

    if (worktreePrefix && worktreePrefix !== config.worktreePrefix) {
      const oldPrefix = config.worktreePrefix || 'task-';
      const worktreesPath = path.join(config.path, 'worktrees');
      if (await fs.pathExists(worktreesPath)) {
        const existingWorktrees = await fs.readdir(worktreesPath);
        const hasWorktreesWithOldPrefix = existingWorktrees.some(w => w.startsWith(oldPrefix));

        if (hasWorktreesWithOldPrefix && !confirmWorktreePrefixChange) {
          return res.json({
            warning: 'Changing worktree prefix will not affect existing worktrees. Old worktrees will remain.',
            requiresConfirmation: true,
            project: {
              id: req.params.id,
              name: name || config.name,
              path: config.path,
              worktreePrefix,
              defaultModel: withFullName(hasDefaultModelField ? defaultModel : config.defaultModel || null),
              isAccessible: await fs.pathExists(config.path)
            }
          });
        }
      }

      config.worktreePrefix = worktreePrefix;
    }

    if (hasDefaultModelField) {
      if (defaultModel === null) {
        delete config.defaultModel;
      } else if (defaultModel) {
        config.defaultModel = defaultModel;
      }
    }

    await fs.writeJson(configPath, config, { spaces: 2 });

    res.json({
      id: req.params.id,
      name: config.name,
      path: config.path,
      worktreePrefix: config.worktreePrefix,
      defaultModel: withFullName(config.defaultModel || null),
      isAccessible: await fs.pathExists(config.path)
    });
  } catch (err) {
    console.error('Error updating project:', err);
    res.status(500).json({ error: 'Failed to update project' });
  }
});

app.get('/api/tasks/:id/history', async (req, res) => {
  try {
    const { projectId } = req.query;
    if (!projectId) {
      return res.status(400).json({ error: 'projectId is required' });
    }

    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);
    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const history = await readTaskHistory(tasksPath, req.params.id);
    res.json(history);
  } catch (error) {
    console.error('Error getting task history:', error);
    res.status(500).json({ error: 'Failed to get task history' });
  }
});

app.get('/api/projects/:projectId/tasks/:taskId/logs', async (req, res) => {
  try {
    const { projectId, taskId } = req.params;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);
    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const logs = await listTaskLogFiles(config.path, taskId);
    res.json({ logs });
  } catch (error) {
    console.error('Error listing task logs:', error);
    res.status(500).json({ error: 'Failed to list task logs' });
  }
});

app.get('/api/projects/:projectId/logs/:logFile', async (req, res) => {
  try {
    const { projectId, logFile } = req.params;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);
    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const content = await readLogFile(config.path, logFile);
    res.type('text/plain').send(content);
  } catch (error) {
    console.error('Error reading log file:', error);
    res.status(500).json({ error: 'Failed to read log file' });
  }
});

app.put('/api/tasks/:taskId/model', async (req, res) => {
  try {
    const { projectId, model } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const taskFile = path.join(tasksPath, `${req.params.taskId}.md`);

    if (!await fs.pathExists(taskFile)) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const content = await fs.readFile(taskFile, 'utf-8');
    const updates = {
      agenticHarness: model.agenticHarness,
      modelProvider: model.modelProvider,
      modelName: model.modelName
    };
    
    const updatedContent = updateFrontmatter(content, updates);
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    const frontmatter = parseFrontmatter(updatedContent);
    const defaultModel = config.defaultModel || {
      agenticHarness: 'opencode',
      modelProvider: 'opencode',
      modelName: 'claude-sonnet-4-5'
    };

	    res.json({
	      taskId: req.params.taskId,
	      model: {
	        agenticHarness: frontmatter.agenticHarness || defaultModel.agenticHarness,
	        modelProvider: frontmatter.modelProvider || defaultModel.modelProvider,
	        modelName: frontmatter.modelName || defaultModel.modelName,
	        fullName: `${frontmatter.modelProvider || defaultModel.modelProvider}/${frontmatter.modelName || defaultModel.modelName}`
	      }
	    });
	  } catch (err) {
    console.error('Error updating task model:', err);
    res.status(500).json({ error: 'Failed to update task model' });
  }
});

app.post('/api/tasks/:taskId/run', async (req, res) => {
  const { projectId, model } = req.body;
  
  try {
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const taskFile = path.join(tasksPath, `${req.params.taskId}.md`);

    if (!await fs.pathExists(taskFile)) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const runningKey = getTaskKey(projectId, req.params.taskId);
    if (RUNNING_TASKS.has(runningKey)) {
      return res.status(400).json({ error: 'Task already running' });
    }

    const { branchName, worktreePath } = await createWorktree(
      config.path,
      req.params.taskId,
      config.worktreePrefix || 'task-'
    );

    const taskRelativePath = `.memory_bank/tasks/${req.params.taskId}.md`;
    const modelFullName = `${model.modelProvider}/${model.modelName}`;
    const taskContent = await fs.readFile(taskFile, 'utf-8');
    const frontmatter = parseFrontmatter(taskContent);

    const stagePrompt = await getStagePrompt(frontmatter.stage);
    const variables = {
      task_file: taskRelativePath
    };

    if (frontmatter.stage === 'Specification') {
      variables.spec_template = await ensureWorktreeTemplateFile(worktreePath, 'spec.md');
    } else if (frontmatter.stage === 'Plan') {
      variables.plan_template = await ensureWorktreeTemplateFile(worktreePath, 'plan.md');
    }

    let finalPrompt = replaceVariables(stagePrompt, variables);
    finalPrompt = rewriteNcrewTemplatePathsInPrompt(finalPrompt, variables);

    const startedAt = new Date().toISOString();
    const timestamp = Date.now();
    const runId = `run-${timestamp}`;

	    const updatedContent = updateFrontmatter(taskContent, {
	      status: 'In Progress',
	      startedAt
	    });
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    const logsDir = getTaskLogsDir(config.path);
    await fs.ensureDir(logsDir);
    const stageForFile = normalizeStageForFileName(frontmatter.stage);
    const logFileName = `${req.params.taskId}-${stageForFile}-${timestamp}.log`;
    const logFile = path.join(logsDir, logFileName);
    const logStream = fs.createWriteStream(logFile, { flags: 'a' });

	    await appendHistoryEntry(tasksPath, req.params.taskId, {
	      id: runId,
	      stage: frontmatter.stage,
	      status: 'In Progress',
	      startedAt,
	      completedAt: null,
	      duration: null,
      model: withFullName({
        agenticHarness: model.agenticHarness,
        modelProvider: model.modelProvider,
        modelName: model.modelName
      }),
      logFile: logFileName
    });

    logStream.write(`[NCrew] Stage: ${frontmatter.stage}\n`);
    logStream.write(`[NCrew] Using model: ${modelFullName}\n`);
    logStream.write(`[NCrew] Worktree: ${worktreePath}\n`);
    logStream.write(`[NCrew] Task file: ${taskRelativePath}\n`);
    logStream.write(`[NCrew] Started at: ${startedAt}\n`);
    logStream.write(`[NCrew] Prompt:\n${finalPrompt}\n`);
    logStream.write('---\n');

    const childProcess = spawn('opencode', ['-m', modelFullName, 'run', finalPrompt], {
      cwd: worktreePath,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    const runningMeta = {
      childProcess,
      worktreePath,
      branchName,
      startedAt,
      runId,
      logFileName,
      stopped: false
    };
    RUNNING_TASKS.set(runningKey, runningMeta);

    childProcess.stdout.on('data', (data) => {
      logStream.write(data);
    });

    childProcess.stderr.on('data', (data) => {
      logStream.write(data);
    });

    childProcess.on('error', (error) => {
      logStream.write(`[NCrew] Process error: ${error.message}\n`);
      logStream.write(`[NCrew] Completed at: ${new Date().toISOString()}\n`);
      logStream.end();
      RUNNING_TASKS.delete(runningKey);

      const completedAt = new Date().toISOString();
      const duration = new Date(completedAt).getTime() - new Date(startedAt).getTime();

      updateHistoryEntry(tasksPath, req.params.taskId, runId, {
        status: 'Failed',
        completedAt,
        duration
      }).catch(err => console.error('Error updating history:', err));

      fs.readFile(taskFile, 'utf-8')
        .then(content => {
          const newContent = updateFrontmatter(content, { status: 'Failed' });
          return fs.writeFile(taskFile, newContent, 'utf-8');
        })
        .catch(err => console.error('Error updating task status:', err));
    });

    childProcess.on('close', (exitCode) => {
      logStream.write(`[NCrew] Exit code: ${exitCode}\n`);
      logStream.write(`[NCrew] Completed at: ${new Date().toISOString()}\n`);
      logStream.end();
      RUNNING_TASKS.delete(runningKey);

      const completedAt = new Date().toISOString();
      const duration = new Date(completedAt).getTime() - new Date(startedAt).getTime();

      const newStatus = runningMeta.stopped ? 'Failed' : (exitCode === 0 ? 'Done' : 'Failed');

      updateHistoryEntry(tasksPath, req.params.taskId, runId, {
        status: newStatus,
        completedAt,
        duration
      }).catch(err => console.error('Error updating history:', err));

      fs.readFile(taskFile, 'utf-8')
        .then(content => {
          const newContent = updateFrontmatter(content, { status: newStatus });
          return fs.writeFile(taskFile, newContent, 'utf-8');
        })
        .catch(err => console.error('Error updating task status:', err));
    });

	    res.json({
	      status: 'In Progress',
	      message: 'Task started successfully',
	      taskId: req.params.taskId,
	      worktreePath,
      branchName,
      startedAt
    });
  } catch (err) {
    console.error('Error starting task:', err);
    res.status(500).json({ error: 'Failed to start task', details: err.message });
  }
});

app.post('/api/tasks/:id/next-stage', async (req, res) => {
  try {
    const { projectId } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const taskFile = path.join(tasksPath, `${req.params.id}.md`);

    if (!await fs.pathExists(taskFile)) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const content = await fs.readFile(taskFile, 'utf-8');
    const frontmatter = parseFrontmatter(content);

    const currentIndex = STAGES.indexOf(frontmatter.stage);
    if (currentIndex === -1 || currentIndex === STAGES.length - 1) {
      return res.status(400).json({ error: 'Already at last stage' });
    }

    const nextStage = STAGES[currentIndex + 1];
    const updatedContent = updateFrontmatter(content, {
      stage: nextStage,
      status: 'New'
    });

    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    res.json({
      taskId: req.params.id,
      stage: nextStage,
      status: 'New'
    });
  } catch (err) {
    console.error('Error moving task to next stage:', err);
    res.status(500).json({ error: 'Failed to move task to next stage' });
  }
});

app.post('/api/tasks/:id/stop', async (req, res) => {
  try {
    const { projectId } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const taskFile = path.join(tasksPath, `${req.params.id}.md`);

    if (!await fs.pathExists(taskFile)) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const runningKey = getTaskKey(projectId, req.params.id);
    const runningTask = RUNNING_TASKS.get(runningKey);
    if (!runningTask) {
      return res.status(404).json({ error: 'Task not running' });
    }

    runningTask.stopped = true;
    runningTask.childProcess.kill();

    const content = await fs.readFile(taskFile, 'utf-8');
    const updatedContent = updateFrontmatter(content, { status: 'Failed' });
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    const completedAt = new Date().toISOString();
    const duration = new Date(completedAt).getTime() - new Date(runningTask.startedAt).getTime();
    await updateHistoryEntry(tasksPath, req.params.id, runningTask.runId, {
      status: 'Failed',
      completedAt,
      duration
    });

    res.json({
      taskId: req.params.id,
      status: 'Failed'
    });
  } catch (err) {
    console.error('Error stopping task:', err);
    res.status(500).json({ error: 'Failed to stop task' });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/dist/index.html'));
});

(async () => {
  try {
    await initNcrewStructure();
    await migrateOldSettings();
  } catch (error) {
    console.error('Failed to initialize NCrew structure:', error);
  }
  
  const server = app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });

  server.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE') {
      console.error(`[NCrew] Port ${PORT} is already in use.`);
      console.error('[NCrew] Stop the process using it, or set PORT / NCREW_BACKEND_PORT / NCREW_PORT to another value.');
    } else {
      console.error('[NCrew] Server failed to start:', err);
    }
    process.exit(1);
  });
})();

function parseFrontmatter(content) {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!frontmatterMatch) {
    return { stage: 'Specification', status: 'New' };
  }

  const frontmatter = frontmatterMatch[1];
  const lines = frontmatter.split('\n');
  const result = {};

  for (const line of lines) {
    const [key, ...valueParts] = line.split(':');
    if (key && valueParts.length > 0) {
      const value = valueParts.join(':').trim();
      result[key.trim()] = value.replace(/^"|"$/g, '');
    }
  }

  if (!result.stage) {
    result.stage = 'Specification';
  }

  if (!result.status) {
    result.status = 'New';
  }

  return result;
}

function updateFrontmatter(content, updates) {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
  
  if (frontmatterMatch) {
    let frontmatter = frontmatterMatch[1];
    const lines = frontmatter.split('\n');
    
    for (const [key, value] of Object.entries(updates)) {
      const keyIndex = lines.findIndex(line => line.trim().startsWith(`${key}:`));
      if (keyIndex >= 0) {
        lines[keyIndex] = `${key}: ${value}`;
      } else {
        lines.push(`${key}: ${value}`);
      }
    }
    
    frontmatter = lines.join('\n');
    return content.replace(frontmatterMatch[0], `---\n${frontmatter}\n---`);
  } else {
    const frontmatter = Object.entries(updates)
      .map(([key, value]) => `${key}: ${value}`)
      .join('\n');
    return `---\n${frontmatter}\n---\n\n${content}`;
  }
}
