import React, { useState, useEffect } from 'react';
import { Routes, Route, Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { fetchModels, refreshModels } from './services/models';
import ProjectCard from './components/ProjectCard';
import ProjectView from './components/ProjectView';
import ModelSelector from './components/ModelSelector';
import './index.css';

function App() {
  const [models, setModels] = useState([]);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      const data = await fetchModels();
      setModels(data.models || []);
    } catch (err) {
      console.error('Error loading models:', err);
    }
  };

  const handleRefreshModels = async () => {
    try {
      const data = await refreshModels();
      setModels(data.models || []);
      alert('Models refreshed successfully');
    } catch (err) {
      console.error('Error refreshing models:', err);
      alert('Failed to refresh models');
    }
  };

  return (
    <div className="container">
      <header className="header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>NCrew - Agentic Harness</h1>
          <button className="button" onClick={handleRefreshModels}>
            Refresh Models
          </button>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<Home models={models} />} />
        <Route path="/project/:projectId" element={<ProjectView models={models} />} />
      </Routes>
    </div>
  );
}

function Home({ models }) {
  const [projects, setProjects] = useState([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProject, setNewProject] = useState({
    name: '',
    path: '',
    worktreePrefix: 'task-',
    defaultModel: null
  });

  useEffect(() => {
    fetchProjects();
    const interval = setInterval(fetchProjects, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchProjects = async () => {
    try {
      const res = await axios.get('/api/projects');
      setProjects(res.data);
    } catch (err) {
      console.error('Error fetching projects:', err);
    }
  };

  const handleAddProject = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/api/projects', newProject);
      setShowAddForm(false);
      setNewProject({ name: '', path: '', worktreePrefix: 'task-', defaultModel: null });
      fetchProjects();
    } catch (err) {
      console.error('Error adding project:', err);
      alert(err.response?.data?.error || 'Failed to add project');
    }
  };

  const handleModelSelect = (modelFullName) => {
    if (!modelFullName) {
      setNewProject({ ...newProject, defaultModel: null });
      return;
    }

    const model = models.find(m => m.fullName === modelFullName);
    if (model) {
      setNewProject({
        ...newProject,
        defaultModel: {
          agenticHarness: 'opencode',
          modelProvider: model.provider,
          modelName: model.name
        }
      });
    }
  };

  const selectedDefaultModel = newProject.defaultModel
    ? `${newProject.defaultModel.modelProvider}/${newProject.defaultModel.modelName}`
    : '';

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Projects</h2>
        <button
          className="button primary"
          onClick={() => setShowAddForm(true)}
        >
          + Add Project
        </button>
      </div>

      {showAddForm && (
        <div className="card">
          <form onSubmit={handleAddProject}>
            <input
              className="input"
              type="text"
              placeholder="Project Name"
              value={newProject.name}
              onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
              required
            />
            <input
              className="input"
              type="text"
              placeholder="Project Path (absolute)"
              value={newProject.path}
              onChange={(e) => setNewProject({ ...newProject, path: e.target.value })}
              required
            />
            <input
              className="input"
              type="text"
              placeholder="Worktree Prefix (default: task-)"
              value={newProject.worktreePrefix}
              onChange={(e) => setNewProject({ ...newProject, worktreePrefix: e.target.value })}
            />
            <label className="label">Default Model:</label>
            <ModelSelector
              models={models}
              selectedModel={selectedDefaultModel}
              onSelect={handleModelSelect}
            />
            <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
              <button type="submit" className="button primary">Add Project</button>
              <button
                type="button"
                className="button"
                onClick={() => {
                  setShowAddForm(false);
                  setNewProject({ name: '', path: '', worktreePrefix: 'task-', defaultModel: null });
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {projects.length === 0 ? (
        <div className="card">
          <p>No projects yet. Add your first project to get started.</p>
        </div>
      ) : (
        projects.map((project) => (
          <Link key={project.id} to={`/project/${project.id}`} style={{ textDecoration: 'none' }}>
            <ProjectCard project={project} />
          </Link>
        ))
      )}
    </div>
  );
}

export default App;
