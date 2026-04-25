import React from 'react';
import { useTwinStore } from '../store/useTwinStore.js';

function formatNumber(value, suffix = '') {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '--';
  return `${Number(value).toFixed(1)}${suffix}`;
}

export default function HeaderBar() {
  const telemetry = useTwinStore((state) => state.telemetry);
  const connection = useTwinStore((state) => state.connection);
  const activeScene = useTwinStore((state) => state.activeScene);
  const devices = useTwinStore((state) => state.devices);

  const env = telemetry?.environment || {};
  const weather = telemetry?.weather || {};
  const power = telemetry?.power || {};

  return (
    <header className="header-bar">
      <div>
        <div className="eyebrow">Sunroom OpenClaw</div>
        <h1>Digital Twin Console</h1>
      </div>
      <div className="header-metrics">
        <div className="metric-chip">
          <span className={`status-dot ${connection}`}></span>
          连接：{connection}
        </div>
        <div className="metric-chip">场景：{activeScene}</div>
        <div className="metric-chip">设备：{devices.length}</div>
        <div className="metric-chip">温度：{formatNumber(env.temperature_c, '℃')}</div>
        <div className="metric-chip">CO₂：{env.co2_ppm ?? '--'} ppm</div>
        <div className="metric-chip">降雨：{weather.is_raining ? '是' : '否'}</div>
        <div className="metric-chip">功率：{power.estimated_watts ?? '--'} W</div>
      </div>
    </header>
  );
}
