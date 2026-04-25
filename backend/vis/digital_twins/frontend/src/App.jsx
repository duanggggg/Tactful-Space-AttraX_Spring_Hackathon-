import React, { useEffect } from 'react';
import SunroomCanvas from './scene/SunroomCanvas.jsx';
import { useTwinStore } from './store/useTwinStore.js';

export default function App() {
  const bootstrap = useTwinStore((state) => state.bootstrap);
  const connectEventStream = useTwinStore((state) => state.connectEventStream);
  const disconnectEventStream = useTwinStore((state) => state.disconnectEventStream);
  const refreshTelemetry = useTwinStore((state) => state.refreshTelemetry);
  const error = useTwinStore((state) => state.error);
  const loading = useTwinStore((state) => state.loading);

  useEffect(() => {
    bootstrap().then(() => connectEventStream());
    const timer = window.setInterval(() => {
      refreshTelemetry();
    }, 5000);
    return () => {
      window.clearInterval(timer);
      disconnectEventStream();
    };
  }, [bootstrap, connectEventStream, disconnectEventStream, refreshTelemetry]);

  return (
    <div className="app-shell">
      <main className="stage-panel fullscreen-stage">
        {loading ? <div className="overlay-message">正在加载 digital twin ...</div> : null}
        {error ? <div className="overlay-message error">{error}</div> : null}
        <SunroomCanvas />
      </main>
    </div>
  );
}
