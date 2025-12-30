import React from 'react';

export default function ModelSelector({ models, selectedModel, onSelect }) {
  if (!models || models.length === 0) {
    return <span className="text-sm text-gray-500">Loading models...</span>;
  }

  const grouped = models.reduce((acc, model) => {
    if (!acc[model.provider]) {
      acc[model.provider] = [];
    }
    acc[model.provider].push(model);
    return acc;
  }, {});

  const selectedProvider = selectedModel ? models.find(m => m.fullName === selectedModel)?.provider : null;

  return (
    <div className="model-selector">
      <select
        className="input"
        value={selectedModel || ''}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="">Select model...</option>
        {Object.entries(grouped).map(([provider, providerModels]) => (
          <optgroup key={provider} label={provider}>
            {providerModels.map(model => (
              <option key={model.fullName} value={model.fullName}>
                {model.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
