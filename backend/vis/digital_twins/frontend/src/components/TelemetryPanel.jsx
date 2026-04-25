import React from 'react';
import { useTwinStore } from '../store/useTwinStore.js';

function EventItem({ event }) {
  const payload = event.scene_name || event.message || event.action || event.type;
  return (
    <div className="event-item">
      <div className="event-topline">
        <span className="event-type">{event.type}</span>
        <span className="event-time">{new Date(event.ts).toLocaleTimeString()}</span>
      </div>
      <div className="event-payload">{payload}</div>
      {event.device_id ? <div className="event-meta">{event.device_id}</div> : null}
      {event.zone ? <div className="event-meta">zone: {event.zone}</div> : null}
    </div>
  );
}

export default function TelemetryPanel() {
  const telemetry = useTwinStore((state) => state.telemetry);
  const recentEvents = useTwinStore((state) => state.recentEvents);
  const refreshTelemetry = useTwinStore((state) => state.refreshTelemetry);

  const env = telemetry?.environment || {};
  const weather = telemetry?.weather || {};
  const occupancy = telemetry?.occupancy || {};
  const power = telemetry?.power || {};
  const comfort = telemetry?.comfort || {};

  return (
    <aside className="panel right-panel">
      <div className="panel-section">
        <div className="section-title with-action">
          <span>Telemetry</span>
          <button className="small-button" onClick={refreshTelemetry}>
            刷新
          </button>
        </div>
        <div className="kv-grid">
          <div>温度</div><div>{env.temperature_c ?? '--'} ℃</div>
          <div>湿度</div><div>{env.humidity_pct ?? '--'} %</div>
          <div>CO₂</div><div>{env.co2_ppm ?? '--'} ppm</div>
          <div>照度</div><div>{env.lux ?? '--'} lux</div>
          <div>PM2.5</div><div>{env.pm25 ?? '--'}</div>
          <div>占用</div><div>{occupancy.count ?? '--'} 人</div>
          <div>降雨</div><div>{weather.is_raining ? '是' : '否'}</div>
          <div>功率</div><div>{power.estimated_watts ?? '--'} W</div>
          <div>开窗</div><div>{comfort.window_position ?? '--'} %</div>
          <div>窗帘</div><div>{comfort.curtain_position ?? '--'} %</div>
        </div>
      </div>

      <div className="panel-section">
        <div className="section-title">最近事件</div>
        <div className="event-list">
          {recentEvents.length ? recentEvents.map((event) => <EventItem key={event.event_id} event={event} />) : <div className="muted">暂无事件</div>}
        </div>
      </div>
    </aside>
  );
}
