import React from 'react';

export default function ProjectCard({ project }) {
  return (
    <div className={`card ${project.error ? 'error' : 'success'}`}>
      <h3>{project.name}</h3>
      <p style={{ color: '#666', fontSize: '14px', marginTop: '8px' }}>
        {project.path}
      </p>
      {project.error && (
        <p style={{ color: '#e74c3c', fontSize: '14px', marginTop: '8px' }}>
          ⚠️ {project.error}
        </p>
      )}
      {!project.error && (
        <p style={{ color: '#388e3c', fontSize: '14px', marginTop: '8px' }}>
          ✓ Project accessible
        </p>
      )}
      <p style={{ color: '#999', fontSize: '12px', marginTop: '8px' }}>
        Worktree prefix: {project.worktreePrefix}
      </p>
    </div>
  );
}
