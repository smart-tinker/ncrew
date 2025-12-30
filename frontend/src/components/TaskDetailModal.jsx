import React from 'react';
import TaskTimer from './TaskTimer';

export default function TaskDetailModal({ task, onClose, onStopTask, onNextStage, models, onModelChange }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{task.title}</h2>
        
        {task.status === 'In Progress' && task.startedAt && (
          <div style={{ marginBottom: '20px', fontSize: '24px' }}>
            ⏱ <TaskTimer startTime={task.startedAt} />
          </div>
        )}

        <div className="modal-body">
          <div style={{ marginBottom: '10px' }}>
            <strong>Stage:</strong> {task.stage}
          </div>
          <div style={{ marginBottom: '10px' }}>
            <strong>Status:</strong> <span className={`status-badge ${task.status.toLowerCase()}`}>{task.status}</span>
          </div>
          <div style={{ marginBottom: '10px' }}>
            <strong>Priority:</strong> {task.priority}
          </div>
          {task.model && (
            <div style={{ marginBottom: '10px' }}>
              <strong>Model:</strong> {task.model.fullName}
            </div>
          )}

          <div style={{ marginTop: '20px', padding: '10px', background: '#f5f5f5', borderRadius: '4px' }}>
            <strong>Logs:</strong>
            <div style={{ fontFamily: 'monospace', fontSize: '12px', marginTop: '10px', maxHeight: '200px', overflow: 'auto' }}>
              {task.status === 'In Progress' ? 'Running...' : 'No logs available yet.'}
            </div>
          </div>
        </div>
        
        <div className="modal-footer">
          <button className="button" onClick={onClose}>
            Close
          </button>
          {task.status === 'Done' && task.stage !== 'Verification' && (
            <button className="button" onClick={() => onNextStage(task.id)}>
              Next Stage
            </button>
          )}
          {task.status === 'In Progress' && (
            <button className="button" style={{ backgroundColor: '#e74c3c', color: 'white' }} onClick={() => onStopTask(task.id)}>
              Stop
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
