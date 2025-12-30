import React, { useState } from 'react';
import ModelSelector from './ModelSelector';

export default function ProjectEditModal({ project, onSave, onCancel, models }) {
  const [name, setName] = useState(project.name);
  const [worktreePrefix, setWorktreePrefix] = useState(project.worktreePrefix || 'task-');
  const [selectedModel, setSelectedModel] = useState(project.defaultModel?.fullName || '');

  const handleSave = () => {
    if (!selectedModel) {
      onSave({ name, worktreePrefix, defaultModel: null });
      return;
    }

    const [modelProvider, modelName] = selectedModel.split('/');
    const defaultModel = {
      agenticHarness: 'opencode',
      modelProvider,
      modelName
    };

    onSave({ name, worktreePrefix, defaultModel });
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Edit Project</h2>

        <div className="modal-body">
          <label className="label">Name</label>
          <input
            className="input"
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
          />

          <label className="label">Worktree Prefix</label>
          <input
            className="input"
            type="text"
            value={worktreePrefix}
            onChange={e => setWorktreePrefix(e.target.value)}
          />

          <label className="label">Default Model</label>
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onSelect={setSelectedModel}
          />

          <div style={{ marginTop: '20px', padding: '10px', background: '#f5f5f5', borderRadius: '4px' }}>
            <strong>Path:</strong> {project.path} (read-only)
          </div>
        </div>

        <div className="modal-footer">
          <button className="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="button primary" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
