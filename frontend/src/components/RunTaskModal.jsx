import React, { useState } from 'react';
import ModelSelector from './ModelSelector';

export default function RunTaskModal({ task, model, models, onRun, onCancel }) {
  const [selectedModel, setSelectedModel] = useState(model?.fullName || '');

  const handleRun = () => {
    if (!selectedModel) {
      alert('Please select a model');
      return;
    }

    const [modelProvider, modelName] = selectedModel.split('/');
    onRun(task.id, {
      agenticHarness: 'opencode',
      modelProvider,
      modelName
    });
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>Run Task: {task.title}</h2>
        
        <div className="modal-body">
          <label className="label">Select Model:</label>
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onSelect={setSelectedModel}
          />
          
          <p style={{ color: '#666', fontSize: '14px', marginTop: '10px' }}>
            Default model: {model?.fullName || 'Not set'}
          </p>
        </div>
        
        <div className="modal-footer">
          <button className="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="button primary" onClick={handleRun}>
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
