import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import ModelSelector from './ModelSelector';
import RunTaskModal from './RunTaskModal';

export default function ProjectView({ models }) {
  const { projectId } = useParams();
  const [tasks, setTasks] = useState([]);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runTask, setRunTask] = useState(null);

  useEffect(() => {
    fetchProject();
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, [projectId]);

  const fetchProject = async () => {
    try {
      const res = await axios.get('/api/projects');
      const foundProject = res.data.find(p => p.id === projectId);
      setProject(foundProject);
    } catch (err) {
      console.error('Error fetching project:', err);
    }
  };

  const fetchTasks = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`/api/projects/${projectId}/tasks`);
      setTasks(res.data);
    } catch (err) {
      console.error('Error fetching tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunClick = (task) => {
    setRunTask(task);
  };

  const handleRunConfirm = async (taskId, model) => {
    try {
      await axios.post(`/api/tasks/${taskId}/run`, { projectId, model });
      setRunTask(null);
      fetchTasks();
    } catch (err) {
      console.error('Error running task:', err);
      alert(err.response?.data?.error || 'Failed to start task');
    }
  };

  const handleModelChange = async (taskId, modelFullName) => {
    if (!modelFullName) return;

    const [modelProvider, modelName] = modelFullName.split('/');
    const model = {
      agenticHarness: 'opencode',
      modelProvider,
      modelName
    };

    try {
      await axios.put(`/api/tasks/${taskId}/model`, { projectId, model });
      fetchTasks();
    } catch (err) {
      console.error('Error updating task model:', err);
      alert('Failed to update task model');
    }
  };

  if (!project) {
    return <div className="container">Project not found</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <Link to="/" style={{ textDecoration: 'none', color: '#1976d2' }}>
          ← Back to Projects
        </Link>
      </div>

      <div className="card">
        <h2>{project.name}</h2>
        <p style={{ color: '#666', fontSize: '14px', marginTop: '8px' }}>
          {project.path}
        </p>
        <p style={{ color: '#999', fontSize: '12px', marginTop: '8px' }}>
          Worktree prefix: {project.worktreePrefix}
        </p>
        {project.defaultModel && (
          <p style={{ color: '#666', fontSize: '12px', marginTop: '8px' }}>
            Default model: {project.defaultModel.modelProvider}/{project.defaultModel.modelName}
          </p>
        )}
      </div>

      <h3>Tasks ({tasks.length})</h3>

      {loading ? (
        <div className="card">Loading tasks...</div>
      ) : tasks.length === 0 ? (
        <div className="card">
          No tasks found. Create tasks in <code>.memory_bank/tasks/</code> folder.
        </div>
      ) : (
        tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            models={models}
            onRunClick={handleRunClick}
            onModelChange={handleModelChange}
          />
        ))
      )}

      {runTask && (
        <RunTaskModal
          task={runTask}
          model={runTask.model}
          models={models}
          onRun={handleRunConfirm}
          onCancel={() => setRunTask(null)}
        />
      )}
    </div>
  );
}

function TaskCard({ task, models, onRunClick, onModelChange }) {
  const statusClass = task.status.toLowerCase();

  return (
    <div className={`card ${statusClass === 'failed' ? 'error' : ''}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <h4>{task.title}</h4>
          <div style={{ marginTop: '8px', display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span className={`status-badge ${statusClass}`}>{task.status}</span>
            <span style={{ color: '#999', fontSize: '12px' }}>
              Priority: {task.priority}
            </span>
          </div>
          {task.model && (
            <div style={{ marginTop: '10px' }}>
              <label className="label" style={{ fontSize: '12px' }}>Model:</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '5px' }}>
                <ModelSelector
                  models={models}
                  selectedModel={task.model?.fullName || ''}
                  onSelect={(modelFullName) => onModelChange(task.id, modelFullName)}
                />
                <span style={{ color: '#999', fontSize: '12px' }}>
                  {task.model?.fullName}
                </span>
              </div>
            </div>
          )}
        </div>
        <button
          className={`button ${task.status === 'Running' ? 'success' : 'primary'}`}
          onClick={() => onRunClick(task)}
          disabled={task.status === 'Running'}
          style={{ marginLeft: '20px' }}
        >
          {task.status === 'Running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  );
}
