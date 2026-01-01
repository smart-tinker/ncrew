import React from 'react';
import axios from 'axios';
import TaskTimer from './TaskTimer';
import TaskTimeline from './TaskTimeline';

function normalizeStatusClass(status) {
  return String(status || '').toLowerCase().replace(/\s+/g, '-');
}

function isRunningStatus(status) {
  return status === 'Running' || status === 'In Progress';
}

function stageLabel(stage) {
  if (!stage) return 'Unknown';
  const s = String(stage);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function groupLogsByStage(logs) {
  const grouped = new Map();
  for (const log of logs) {
    const key = log.stage || 'unknown';
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(log);
  }
  for (const [key, arr] of grouped.entries()) {
    grouped.set(key, [...arr].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0)));
  }
  return grouped;
}

export default function TaskDetailModal({ projectId, task, onClose, onStopTask, onNextStage }) {
  const history = task.history || task.executions || [];
  const logs = task.logs || [];
  const running = isRunningStatus(task.status);
  const statusClass = normalizeStatusClass(task.status);

  const [selectedLogFile, setSelectedLogFile] = React.useState(null);
  const [logContent, setLogContent] = React.useState('');
  const [logLoading, setLogLoading] = React.useState(false);
  const [logError, setLogError] = React.useState(null);

  const fetchLog = React.useCallback(async () => {
    if (!projectId || !selectedLogFile) return;

    setLogLoading(true);
    setLogError(null);
    try {
      const res = await axios.get(`/api/projects/${projectId}/logs/${selectedLogFile}`, {
        responseType: 'text'
      });
      setLogContent(res.data || '');
    } catch (err) {
      console.error('Error fetching log:', err);
      setLogError(err.response?.data?.error || err.message || 'Failed to fetch log');
    } finally {
      setLogLoading(false);
    }
  }, [projectId, selectedLogFile]);

  React.useEffect(() => {
    if (selectedLogFile) return;
    const latestFromHistory = [...history].reverse().find(h => h?.logFile)?.logFile || null;
    const latestFromLogs = logs.length > 0 ? logs[logs.length - 1].file : null;
    setSelectedLogFile(latestFromHistory || latestFromLogs);
  }, [selectedLogFile, history, logs]);

  React.useEffect(() => {
    fetchLog();
  }, [fetchLog]);

  React.useEffect(() => {
    if (!running || !selectedLogFile) return;
    const interval = setInterval(() => {
      fetchLog();
    }, 1500);
    return () => clearInterval(interval);
  }, [running, selectedLogFile, fetchLog]);

  const groupedLogs = groupLogsByStage(logs);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{task.title}</h2>

        {running && task.startedAt && (
          <div style={{ marginBottom: '20px', fontSize: '24px' }}>
            ⏱ <TaskTimer startTime={task.startedAt} />
          </div>
        )}

        <div className="modal-body">
          <div style={{ marginBottom: '10px' }}>
            <strong>Stage:</strong> {task.stage}
          </div>
          <div style={{ marginBottom: '10px' }}>
            <strong>Status:</strong> <span className={`status-badge ${statusClass}`}>{task.status}</span>
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
            <strong>Timeline:</strong>
            <TaskTimeline
              history={history}
              selectedLogFile={selectedLogFile}
              onSelectRun={(run) => {
                if (run?.logFile) setSelectedLogFile(run.logFile);
              }}
            />
          </div>

          <div style={{ marginTop: '20px', padding: '10px', background: '#f5f5f5', borderRadius: '4px' }}>
            <strong>Logs:</strong>

            {logs.length === 0 ? (
              <div style={{ marginTop: '10px', color: '#999' }}>No logs available yet.</div>
            ) : (
              <div style={{ display: 'flex', gap: '12px', marginTop: '10px' }}>
                <div style={{ minWidth: '180px', maxWidth: '220px' }}>
                  {[...groupedLogs.entries()].map(([stage, stageLogs]) => (
                    <div key={stage} style={{ marginBottom: '12px' }}>
                      <div style={{ fontWeight: 700, fontSize: '12px', marginBottom: '6px' }}>
                        {stageLabel(stage)}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {stageLogs.map((log) => (
                          <button
                            key={log.file}
                            type="button"
                            className={`button ${selectedLogFile === log.file ? 'success' : ''}`}
                            style={{
                              textAlign: 'left',
                              padding: '6px 10px',
                              fontSize: '12px',
                              background: selectedLogFile === log.file ? '#388e3c' : '#eee',
                              color: selectedLogFile === log.file ? 'white' : '#333'
                            }}
                            onClick={() => setSelectedLogFile(log.file)}
                          >
                            {log.file}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ marginBottom: '8px', fontSize: '12px', color: '#666' }}>
                    <strong>Selected:</strong> {selectedLogFile || '—'}
                    {logLoading && <span> (loading...)</span>}
                    {logError && <span style={{ color: '#e74c3c' }}> ({logError})</span>}
                  </div>
                  <pre
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '12px',
                      margin: 0,
                      maxHeight: '260px',
                      overflow: 'auto',
                      padding: '10px',
                      background: '#111',
                      color: '#eee',
                      borderRadius: '6px'
                    }}
                  >
                    {logContent || (selectedLogFile ? 'Empty log.' : 'Select a log.')}
                  </pre>
                </div>
              </div>
            )}
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
          {running && (
            <button className="button" style={{ backgroundColor: '#e74c3c', color: 'white' }} onClick={() => onStopTask(task.id)}>
              Stop
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
