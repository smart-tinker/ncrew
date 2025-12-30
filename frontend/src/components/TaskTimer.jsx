import React, { useEffect, useState } from 'react';

export default function TaskTimer({ startTime }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startTime) return;

    const interval = setInterval(() => {
      const now = Date.now();
      const diff = now - new Date(startTime).getTime();
      setElapsed(Math.floor(diff / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime]);

  const hours = Math.floor(elapsed / 3600);
  const minutes = Math.floor((elapsed % 3600) / 60);
  const seconds = elapsed % 60;

  return (
    <span style={{ fontFamily: 'monospace', fontSize: '14px' }}>
      {String(hours).padStart(2, '0')}:{String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}
    </span>
  );
}
