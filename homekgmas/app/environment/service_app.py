"""Standalone visualization and control app for the dynamic home simulator."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.core.config import build_settings
from app.environment.dynamic_environment import DynamicHomeEnvironment
from app.environment.web_environment import WebHomeEnvironment
from app.planning.action import PlannedAction


class ActionBatchRequest(BaseModel):
    """Request payload for applying multiple device actions."""

    actions: list[PlannedAction] = Field(default_factory=list)


class TickRequest(BaseModel):
    """Manual simulator tick request."""

    minutes: float = 5.0


class WebActionRequest(BaseModel):
    """Request payload for one normalized web action."""

    action_key: str


def _build_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Home Simulator Dashboard</title>
  <style>
    :root {
      --bg: #f6f1e8;
      --panel: rgba(255, 255, 255, 0.78);
      --line: rgba(60, 54, 44, 0.14);
      --ink: #2f2920;
      --muted: #73685a;
      --accent: #e77b49;
      --accent-soft: rgba(231, 123, 73, 0.14);
      --shadow: 0 18px 42px rgba(47, 41, 32, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(231, 123, 73, 0.22), transparent 28%),
        radial-gradient(circle at top right, rgba(84, 138, 120, 0.16), transparent 26%),
        linear-gradient(160deg, #f7f1e5 0%, #efe4d3 46%, #e7dccb 100%);
      padding: 28px;
    }
    .shell {
      max-width: 1180px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .hero {
      padding: 24px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      flex-wrap: wrap;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      max-width: 720px;
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      font: inherit;
      cursor: pointer;
      color: white;
      background: var(--accent);
      box-shadow: 0 10px 24px rgba(231, 123, 73, 0.26);
    }
    button.secondary {
      color: var(--ink);
      background: var(--accent-soft);
      box-shadow: none;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }
    .panel {
      padding: 20px;
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 18px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .stat {
      padding: 14px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.56);
      border: 1px solid var(--line);
    }
    .label {
      display: block;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .value {
      font-size: 24px;
      font-weight: 700;
    }
    .table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .table td {
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    .table td:first-child {
      color: var(--muted);
      width: 42%;
    }
    .mono {
      font-family: "SFMono-Regular", "Menlo", monospace;
      font-size: 13px;
    }
    .device-list {
      display: grid;
      gap: 10px;
    }
    .device {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.52);
      border-radius: 18px;
      padding: 14px;
    }
    .device strong {
      display: block;
      margin-bottom: 6px;
    }
    @media (max-width: 980px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <h1>Dynamic Home Simulator</h1>
        <p>Outdoor weather drifts slowly over time. Indoor sensors respond to the weather together with AC, lighting, and music device settings.</p>
      </div>
      <div class="actions">
        <button id="step">Advance 15 min</button>
        <button class="secondary" id="reset">Reset</button>
      </div>
    </section>

    <div class="grid">
      <section class="panel">
        <h2>Outdoor</h2>
        <div class="stats" id="outdoor-stats"></div>
      </section>
      <section class="panel">
        <h2>Indoor Sensors</h2>
        <div class="stats" id="sensor-stats"></div>
      </section>
      <section class="panel">
        <h2>Time</h2>
        <table class="table">
          <tbody id="time-table"></tbody>
        </table>
      </section>
    </div>

    <div class="grid">
      <section class="panel">
        <h2>Furniture State</h2>
        <div class="device-list" id="device-list"></div>
      </section>
      <section class="panel">
        <h2>Occupancy</h2>
        <table class="table">
          <tbody id="occupancy-table"></tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Raw Snapshot</h2>
        <pre class="mono" id="raw-state"></pre>
      </section>
    </div>
  </div>

  <script>
    async function loadState() {
      const response = await fetch('/api/state');
      const state = await response.json();
      render(state);
    }

    function stat(label, value) {
      return `<div class="stat"><span class="label">${label}</span><span class="value">${value}</span></div>`;
    }

    function row(label, value) {
      return `<tr><td>${label}</td><td>${value}</td></tr>`;
    }

    function render(state) {
      const outdoor = state.outdoor;
      const sensors = state.sensors;
      const devices = state.devices;

      document.getElementById('outdoor-stats').innerHTML = [
        stat('Weather', outdoor.weather),
        stat('Outdoor Temp', `${outdoor.outdoor_temperature_c.toFixed(1)} C`),
        stat('Outdoor Light', `${outdoor.outdoor_light_level}%`),
        stat('Humidity', `${outdoor.humidity_pct}%`),
        stat('Wind', `${outdoor.wind_speed_mps.toFixed(1)} m/s`),
        stat('Cloud Cover', `${outdoor.cloud_cover_pct}%`)
      ].join('');

      document.getElementById('sensor-stats').innerHTML = [
        stat('Living Room Temp', `${sensors.room_temperature_c.toFixed(1)} C`),
        stat('Bedroom Temp', `${sensors.bedroom_temperature_c.toFixed(1)} C`),
        stat('Room Humidity', `${sensors.room_humidity_pct}%`),
        stat('Ambient Light', `${sensors.ambient_light_level}%`)
      ].join('');

      document.getElementById('time-table').innerHTML = [
        row('Sim Time', sensors.current_time),
        row('Time Of Day', sensors.time_of_day),
        row('Quiet Hours', sensors.quiet_hours ? 'true' : 'false')
      ].join('');

      document.getElementById('occupancy-table').innerHTML = Object.entries(sensors.occupancy)
        .map(([room, occupied]) => row(room, occupied ? 'occupied' : 'empty'))
        .join('');

      const deviceCards = [];
      Object.entries(devices.air_conditioners).forEach(([id, device]) => {
        deviceCards.push(`<div class="device"><strong>${id}</strong><div class="mono">${JSON.stringify(device, null, 2)}</div></div>`);
      });
      Object.entries(devices.lights).forEach(([id, device]) => {
        deviceCards.push(`<div class="device"><strong>${id}</strong><div class="mono">${JSON.stringify(device, null, 2)}</div></div>`);
      });
      deviceCards.push(`<div class="device"><strong>music_player</strong><div class="mono">${JSON.stringify(devices.music_player, null, 2)}</div></div>`);
      document.getElementById('device-list').innerHTML = deviceCards.join('');

      document.getElementById('raw-state').textContent = JSON.stringify(state, null, 2);
    }

    document.getElementById('step').addEventListener('click', async () => {
      await fetch('/api/tick', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({minutes: 15})
      });
      loadState();
    });

    document.getElementById('reset').addEventListener('click', async () => {
      await fetch('/api/reset', {method: 'POST'});
      loadState();
    });

    loadState();
    setInterval(loadState, 2000);
  </script>
</body>
</html>"""


def _build_web_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Web Agent Simulator</title>
  <style>
    :root {
      --bg: #f2eee6;
      --panel: rgba(255, 255, 255, 0.82);
      --panel-strong: rgba(255, 248, 238, 0.96);
      --line: rgba(65, 51, 35, 0.12);
      --ink: #2a241d;
      --muted: #6f6253;
      --accent: #b85d2f;
      --accent-soft: rgba(184, 93, 47, 0.12);
      --cool: #3f7c85;
      --warm: #d77a2c;
      --shadow: 0 22px 42px rgba(42, 36, 29, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(63, 124, 133, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(215, 122, 44, 0.18), transparent 30%),
        linear-gradient(180deg, #f6f3ed 0%, #ece6db 100%);
      padding: 28px;
    }
    .shell {
      max-width: 1440px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }
    .hero, .panel, .agent-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }
    .hero {
      padding: 24px;
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 18px;
      flex-wrap: wrap;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: clamp(30px, 4vw, 48px);
      line-height: 1;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      max-width: 760px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button, .link-pill {
      border: 0;
      border-radius: 999px;
      padding: 12px 16px;
      font: inherit;
      cursor: pointer;
      color: white;
      background: var(--accent);
      box-shadow: 0 10px 22px rgba(184, 93, 47, 0.22);
      text-decoration: none;
    }
    button.secondary, .link-pill.secondary {
      color: var(--ink);
      background: var(--accent-soft);
      box-shadow: none;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: 1.2fr 1fr 1fr;
      gap: 18px;
    }
    .panel {
      padding: 20px;
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 18px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .stat {
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.58);
    }
    .stat .label {
      display: block;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 11px;
      margin-bottom: 8px;
    }
    .stat .value {
      font-size: 24px;
      font-weight: 700;
    }
    .room-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }
    .room-card {
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
    }
    .room-card h3, .agent-card h3 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .metric-list {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      padding: 12px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(247, 243, 235, 0.92);
    }
    .metric strong {
      display: block;
      margin-bottom: 6px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .metric span {
      font-size: 22px;
      font-weight: 700;
    }
    .event-list {
      display: grid;
      gap: 10px;
      font-size: 14px;
    }
    .event-item {
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.58);
    }
    .agent-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }
    .agent-card {
      padding: 20px;
    }
    .agent-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .agent-sub {
      color: var(--muted);
      font-size: 13px;
    }
    .zones {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .zone {
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.56);
      padding: 14px;
    }
    .zone h4 {
      margin: 0 0 10px;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .state-box {
      padding: 10px 12px;
      border-radius: 14px;
      background: rgba(239, 232, 223, 0.88);
      font-family: "SFMono-Regular", "Menlo", monospace;
      font-size: 12px;
      white-space: pre-wrap;
      margin-bottom: 10px;
    }
    .button-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .button-grid button {
      padding: 10px 12px;
      font-size: 13px;
      box-shadow: none;
    }
    .button-grid button.room-living {
      background: var(--cool);
    }
    .button-grid button.room-bedroom {
      background: var(--warm);
    }
    .footnote {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    @media (max-width: 1100px) {
      .summary-grid, .agent-grid, .room-grid, .zones {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <h1>Web Agent Simulator</h1>
        <p>Use direct action buttons to test how each web agent changes its own state and how indoor conditions drift over time in response to outdoor conditions plus device activity.</p>
      </div>
      <div class="toolbar">
        <button id="web-step">Advance 10 min</button>
        <button id="web-reset" class="secondary">Reset Web State</button>
        <a href="/" class="link-pill secondary">Classic Simulator</a>
      </div>
    </section>

    <section class="summary-grid">
      <div class="panel">
        <h2>Outdoor</h2>
        <div class="stats" id="web-outdoor"></div>
      </div>
      <div class="panel">
        <h2>Simulation</h2>
        <div class="stats" id="web-meta"></div>
      </div>
      <div class="panel">
        <h2>Recent Events</h2>
        <div class="event-list" id="web-events"></div>
      </div>
    </section>

    <section class="room-grid">
      <div class="room-card">
        <h3>Living Room</h3>
        <div class="metric-list" id="room-living"></div>
      </div>
      <div class="room-card">
        <h3>Bedroom</h3>
        <div class="metric-list" id="room-bedroom"></div>
      </div>
    </section>

    <section class="panel">
      <h2>Agent Controls</h2>
      <p class="footnote">Each button applies one normalized action, updates the corresponding web-agent state immediately, then advances the environment a small step so you can observe gradual changes instead of instant jumps.</p>
      <div class="agent-grid" id="agent-grid"></div>
    </section>
  </div>

  <script>
    const agentTitleMap = {
      air_conditioner_agent: 'Air Conditioner Agent',
      window_agent: 'Window Agent',
      curtain_agent: 'Curtain Agent',
      fan_agent: 'Fan Agent',
      fresh_air_agent: 'Fresh Air Agent',
      dehumidifier_agent: 'Dehumidifier Agent',
      lighting_agent: 'Lighting Agent',
      computer_agent: 'Computer Agent'
    };

    const agentOrder = [
      'air_conditioner_agent',
      'window_agent',
      'curtain_agent',
      'fan_agent',
      'fresh_air_agent',
      'dehumidifier_agent',
      'lighting_agent',
      'computer_agent'
    ];

    const roomLabels = {
      living: 'Living',
      bedroom: 'Bedroom'
    };

    let catalog = [];
    let pendingActions = new Set();

    function stat(label, value) {
      return `<div class="stat"><span class="label">${label}</span><span class="value">${value}</span></div>`;
    }

    function metric(label, value) {
      return `<div class="metric"><strong>${label}</strong><span>${value}</span></div>`;
    }

    function agentStateKey(agentName) {
      return agentName.replace('_agent', '');
    }

    function stateText(value) {
      return JSON.stringify(value, null, 2);
    }

    async function loadCatalog() {
      const response = await fetch('/api/web/actions');
      catalog = await response.json();
    }

    async function loadState() {
      const response = await fetch('/api/web/state');
      const state = await response.json();
      render(state);
    }

    function render(state) {
      document.getElementById('web-outdoor').innerHTML = [
        stat('Weather', state.outdoor.weather),
        stat('Temp', `${state.outdoor.outdoor_temp.toFixed(1)} C`),
        stat('Humidity', `${state.outdoor.outdoor_humidity}%`),
        stat('Air', `${state.outdoor.outdoor_air}`),
        stat('Noise', `${state.outdoor.outdoor_noise}`),
        stat('Brightness', `${state.outdoor.outdoor_brightness}%`)
      ].join('');

      document.getElementById('web-meta').innerHTML = [
        stat('Time', state.meta.current_time),
        stat('Time Of Day', state.meta.time_of_day)
      ].join('');

      document.getElementById('web-events').innerHTML = state.recent_events
        .map((entry) => `<div class="event-item">${entry}</div>`)
        .join('');

      document.getElementById('room-living').innerHTML = [
        metric('Temp', `${state.indoor.living.temp.toFixed(1)} C`),
        metric('Humidity', `${state.indoor.living.humidity}%`),
        metric('Air', `${state.indoor.living.air}`),
        metric('Noise', `${state.indoor.living.noise}`),
        metric('Brightness', `${state.indoor.living.brightness}%`),
        metric('Energy', `${state.indoor.living.energy}`)
      ].join('');

      document.getElementById('room-bedroom').innerHTML = [
        metric('Temp', `${state.indoor.bedroom.temp.toFixed(1)} C`),
        metric('Humidity', `${state.indoor.bedroom.humidity}%`),
        metric('Air', `${state.indoor.bedroom.air}`),
        metric('Noise', `${state.indoor.bedroom.noise}`),
        metric('Brightness', `${state.indoor.bedroom.brightness}%`),
        metric('Energy', `${state.indoor.bedroom.energy}`)
      ].join('');

      const grouped = {};
      catalog.forEach((item) => {
        grouped[item.agent_name] = grouped[item.agent_name] || {living: [], bedroom: []};
        grouped[item.agent_name][item.room].push(item);
      });

      document.getElementById('agent-grid').innerHTML = agentOrder.map((agentName) => {
        const agentKey = agentStateKey(agentName);
        const agentState = state.agents[agentKey];
        const rooms = grouped[agentName] || {living: [], bedroom: []};
        return `
          <article class="agent-card">
            <div class="agent-header">
              <div>
                <h3>${agentTitleMap[agentName]}</h3>
                <div class="agent-sub">${agentName}</div>
              </div>
            </div>
            <div class="zones">
              ${['living', 'bedroom'].map((room) => `
                <section class="zone">
                  <h4>${roomLabels[room]}</h4>
                  <div class="state-box">${stateText(agentState[room])}</div>
                  <div class="button-grid">
                    ${rooms[room].map((action) => `
                      <button
                        class="room-${room}"
                        data-action="${action.action_key}"
                        title="${action.description}"
                        ${pendingActions.has(action.action_key) ? 'disabled' : ''}
                      >
                        ${action.label}
                      </button>
                    `).join('')}
                  </div>
                </section>
              `).join('')}
            </div>
          </article>
        `;
      }).join('');

      document.querySelectorAll('[data-action]').forEach((button) => {
        button.addEventListener('click', async () => {
          const actionKey = button.getAttribute('data-action');
          pendingActions.add(actionKey);
          try {
            await fetch('/api/web/actions', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({action_key: actionKey})
            });
          } finally {
            pendingActions.delete(actionKey);
            loadState();
          }
        });
      });
    }

    document.getElementById('web-step').addEventListener('click', async () => {
      await fetch('/api/web/tick', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({minutes: 10})
      });
      loadState();
    });

    document.getElementById('web-reset').addEventListener('click', async () => {
      await fetch('/api/web/reset', {method: 'POST'});
      loadState();
    });

    async function boot() {
      await loadCatalog();
      await loadState();
      setInterval(loadState, 2000);
    }

    boot();
  </script>
</body>
</html>"""


def create_simulator_app() -> FastAPI:
    """Create the standalone simulator service."""

    settings = build_settings()
    environment = DynamicHomeEnvironment.from_config_paths(
        sensors_config_path=settings.sensors_config_path,
        devices_config_path=settings.devices_config_path,
        simulator_config_path=settings.simulator_config_path,
    )
    web_environment = WebHomeEnvironment()

    app = FastAPI(title=f"{settings.project_name}-simulator")
    app.state.environment = environment
    app.state.web_environment = web_environment

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return _build_dashboard_html()

    @app.get("/web", response_class=HTMLResponse)
    def web_dashboard() -> str:
        return _build_web_dashboard_html()

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return environment.snapshot_payload()

    @app.post("/api/actions")
    def apply_actions(request: ActionBatchRequest) -> dict[str, Any]:
        environment.apply_actions(request.actions)
        return environment.snapshot_payload()

    @app.post("/api/tick")
    def tick(request: TickRequest) -> dict[str, Any]:
        environment.tick(request.minutes)
        return environment.snapshot_payload()

    @app.post("/api/reset")
    def reset() -> dict[str, Any]:
        environment.reset()
        return environment.snapshot_payload()

    @app.get("/api/web/state")
    def get_web_state() -> dict[str, Any]:
        return web_environment.snapshot_payload()

    @app.get("/api/web/actions")
    def get_web_actions() -> list[dict[str, Any]]:
        return web_environment.action_catalog_payload()

    @app.post("/api/web/actions")
    def apply_web_action(request: WebActionRequest) -> dict[str, Any]:
        return web_environment.apply_action(request.action_key)

    @app.post("/api/web/tick")
    def tick_web(request: TickRequest) -> dict[str, Any]:
        return web_environment.tick(request.minutes)

    @app.post("/api/web/reset")
    def reset_web() -> dict[str, Any]:
        return web_environment.reset()

    return app


app = create_simulator_app()
