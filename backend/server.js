const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs-extra');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

const {
  getProjectsDir,
  getModelsCacheFile,
  getTaskLogsDir
} = require('./utils/paths');
const { initNcrewStructure } = require('./utils/init');
const { migrateOldSettings } = require('./utils/migrate');

const app = express();
const PORT = 3001;
const SETTINGS_DIR = getProjectsDir();
const MODELS_CACHE_FILE = getModelsCacheFile();
const CACHE_TTL = 24 * 60 * 60 * 1000;
const RUNNING_TASKS = new Map();

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend/dist')));

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

async function createWorktree(projectPath, taskId, worktreePrefix) {
  const branchName = `${worktreePrefix}${taskId}`;
  const worktreePath = path.join(projectPath, 'worktrees', branchName);
  
  try {
    await execAsync(`git worktree add ${worktreePath} -b ${branchName}`, {
      cwd: projectPath
    });
    return { branchName, worktreePath };
  } catch (error) {
    console.error('Error creating worktree:', error);
    throw new Error('Failed to create worktree');
  }
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
            defaultModel: content.defaultModel || null,
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

          tasks.push({
            id: taskId,
            title,
            status,
            priority,
            model: {
              agenticHarness: frontmatter.agenticHarness || defaultModel.agenticHarness,
              modelProvider: frontmatter.modelProvider || defaultModel.modelProvider,
              modelName: frontmatter.modelName || defaultModel.modelName
            }
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
      defaultModel
    });
  } catch (err) {
    console.error('Error creating project:', err);
    res.status(500).json({ error: 'Failed to create project' });
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
        modelName: frontmatter.modelName || defaultModel.modelName
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

    const { branchName, worktreePath } = await createWorktree(
      config.path, 
      req.params.taskId, 
      config.worktreePrefix || 'task-'
    );

    const taskRelativePath = `.memory_bank/tasks/${req.params.taskId}.md`;
    const modelFullName = `${model.modelProvider}/${model.modelName}`;
    const prompt = `прочитай и выполни задачу из файла ${taskRelativePath}`;

    const { spawn } = require('child_process');
    const process = spawn('opencode', ['-m', modelFullName, 'run', prompt], {
      cwd: worktreePath
    });

    const taskContent = await fs.readFile(taskFile, 'utf-8');
    const updatedContent = updateFrontmatter(taskContent, { status: 'Running' });
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    const logsDir = getTaskLogsDir(config.path);
    await fs.ensureDir(logsDir);
    const logFile = path.join(logsDir, `${req.params.taskId}-${Date.now()}.log`);
    const logStream = fs.createWriteStream(logFile, { flags: 'a' });

    logStream.write(`[NCrew] Using model: ${modelFullName}\n`);
    logStream.write(`[NCrew] Worktree: ${worktreePath}\n`);
    logStream.write(`[NCrew] Task file: ${taskRelativePath}\n`);
    logStream.write(`[NCrew] Started at: ${new Date().toISOString()}\n`);
    logStream.write('---\n');

    process.stdout.on('data', (data) => {
      logStream.write(data);
    });

    process.stderr.on('data', (data) => {
      logStream.write(data);
    });

    process.on('close', (exitCode) => {
      logStream.write(`[NCrew] Exit code: ${exitCode}\n`);
      logStream.write(`[NCrew] Completed at: ${new Date().toISOString()}\n`);
      logStream.end();
      RUNNING_TASKS.delete(req.params.taskId);

      const newStatus = exitCode === 0 ? 'Done' : 'Failed';
      fs.readFile(taskFile, 'utf-8')
        .then(content => {
          const newContent = updateFrontmatter(content, { status: newStatus });
          return fs.writeFile(taskFile, newContent, 'utf-8');
        })
        .catch(err => console.error('Error updating task status:', err));
    });

    RUNNING_TASKS.set(req.params.taskId, { process, worktreePath, branchName });

    res.json({
      status: 'Running',
      message: 'Task started successfully',
      taskId: req.params.taskId,
      worktreePath,
      branchName
    });
  } catch (err) {
    console.error('Error starting task:', err);
    res.status(500).json({ error: 'Failed to start task', details: err.message });
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
  
  app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
})();

function parseFrontmatter(content) {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!frontmatterMatch) {
    return { status: 'New' };
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
