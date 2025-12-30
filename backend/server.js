const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs-extra');

const app = express();
const PORT = 3001;
const SETTINGS_DIR = path.join(__dirname, '../settings/projects');

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend/dist')));

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

    for (const file of files) {
      if (file.endsWith('.md')) {
        try {
          const fullPath = path.join(tasksPath, file);
          const content = await fs.readFile(fullPath, 'utf-8');
          const taskId = file.replace('.md', '');
          const { title = taskId, status = 'New', priority = 'Medium' } = parseFrontmatter(content);

          tasks.push({
            id: taskId,
            title,
            status,
            priority
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

app.post('/api/projects', async (req, res) => {
  try {
    const { name, path: projectPath, worktreePrefix = 'task-' } = req.body;

    if (!name || !projectPath) {
      return res.status(400).json({ error: 'Name and path are required' });
    }

    const isAccessible = await fs.pathExists(projectPath);
    if (!isAccessible) {
      return res.status(400).json({ error: 'Project path not accessible' });
    }

    const projectId = name.toLowerCase().replace(/\s+/g, '-');
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (await fs.pathExists(configPath)) {
      return res.status(400).json({ error: 'Project already exists' });
    }

    await fs.writeJson(configPath, {
      name,
      path: projectPath,
      worktreePrefix,
      createdAt: new Date().toISOString()
    }, { spaces: 2 });

    res.json({
      id: projectId,
      name,
      path: projectPath,
      worktreePrefix,
      isAccessible: true
    });
  } catch (err) {
    console.error('Error creating project:', err);
    res.status(500).json({ error: 'Failed to create project' });
  }
});

app.post('/api/tasks/:taskId/run', async (req, res) => {
  try {
    const { projectId } = req.body;
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

    res.json({
      status: 'Running',
      message: 'Task started successfully'
    });
  } catch (err) {
    console.error('Error starting task:', err);
    res.status(500).json({ error: 'Failed to start task' });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/dist/index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});

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
