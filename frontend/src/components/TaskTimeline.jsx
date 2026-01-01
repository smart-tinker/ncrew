import React from 'react';

function normalizeStatusClass(status) {
  return String(status || '').toLowerCase().replace(/\s+/g, '-');
}

function isRunningStatus(status) {
  return status === 'Running' || status === 'In Progress';
}

function formatDurationMs(ms) {
  if (ms == null) return null;
  const totalSeconds = Math.floor(ms / 1000);
  const seconds = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);

  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export default function TaskTimeline({ history, selectedLogFile, onSelectRun }) {
  const entries = Array.isArray(history) ? history : [];
  const now = Date.now();

  if (entries.length === 0) {
    return <div style={{ marginTop: '10px', color: '#999' }}>No executions yet.</div>;
  }

  const sorted = [...entries].sort((a, b) => {
    const aTime = a?.startedAt ? new Date(a.startedAt).getTime() : 0;
    const bTime = b?.startedAt ? new Date(b.startedAt).getTime() : 0;
    return aTime - bTime;
  });

  return (
    <div className="timeline">
      {sorted.map((entry) => {
        const statusClass = normalizeStatusClass(entry.status);
        const running = isRunningStatus(entry.status);
        const durationMs = entry.duration != null
          ? entry.duration
          : (running && entry.startedAt ? now - new Date(entry.startedAt).getTime() : null);

        const isSelected = selectedLogFile && entry.logFile === selectedLogFile;

        return (
          <div
            key={entry.id}
            className={`timeline-entry ${statusClass} ${isSelected ? 'selected' : ''}`}
            onClick={() => onSelectRun?.(entry)}
            role="button"
            tabIndex={0}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
              <div style={{ fontWeight: 700 }}>
                {entry.stage}
              </div>
              <div className={`status-badge ${statusClass}`}>{entry.status}</div>
            </div>

            <div style={{ marginTop: '6px', fontSize: '12px', color: '#666' }}>
              <div><strong>Model:</strong> {entry.model?.fullName || 'N/A'}</div>
              <div><strong>Started:</strong> {entry.startedAt ? new Date(entry.startedAt).toLocaleString() : 'N/A'}</div>
              {durationMs != null && (
                <div><strong>Duration:</strong> {formatDurationMs(durationMs)}</div>
              )}
              {entry.logFile && (
                <div><strong>Log:</strong> {entry.logFile}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

