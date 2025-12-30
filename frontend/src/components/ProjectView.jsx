import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';

export default function ProjectView() {
  const { projectId } = useParams();
  const [tasks, setTasks] = useState([]);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);

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

  const handleRunTask = async (taskId) => {
    try {
      await axios.post(`/api/tasks/${taskId}/run`, { projectId });
      fetchTasks();
    } catch (err) {
      console.error('Error running task:', err);
      alert(err.response?.data?.error || 'Failed to start task');
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
            onRun={handleRunTask}
          />
        ))
      )}
    </div>
  );
}

function TaskCard({ task, onRun }) {
  const statusClass = task.status.toLowerCase();

  return (
    <div className={`card ${statusClass === 'failed' ? 'error' : ''}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h4>{task.title}</h4>
          <div style={{ marginTop: '8px', display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span className={`status-badge ${statusClass}`}>{task.status}</span>
            <span style={{ color: '#999', fontSize: '12px' }}>
              Priority: {task.priority}
            </span>
          </div>
        </div>
        <button
          className={`button ${task.status === 'Running' ? 'success' : 'primary'}`}
          onClick={() => onRun(task.id)}
          disabled={task.status === 'Running'}
        >
          {task.status === 'Running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  );
}
