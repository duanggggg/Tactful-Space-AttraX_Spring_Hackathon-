import React from 'react';
import { useTwinStore } from '../store/useTwinStore.js';

const quickActions = {
  'light.perimeter': [
    { label: '打开', action: 'set_on', params: { on: true } },
    { label: '40%', action: 'set_brightness', params: { brightness: 40 } },
    { label: '70%', action: 'set_brightness', params: { brightness: 70 } }
  ],
  'light.entry': [
    { label: '入口亮', action: 'set_on', params: { on: true } },
    { label: '入口灭', action: 'set_on', params: { on: false } }
  ],
  'door.main': [
    { label: '开门', action: 'open', params: { position: 100 } },
    { label: '关门', action: 'close', params: {} },
    { label: '解锁', action: 'unlock', params: {} },
    { label: '上锁', action: 'lock', params: {} }
  ],
  'window.north': [
    { label: '开 60%', action: 'open', params: { position: 60 } },
    { label: '关闭', action: 'close', params: {} }
  ],
  'curtain.front': [
    { label: '全开', action: 'open', params: { position: 100 } },
    { label: '45%', action: 'close', params: { position: 45 } },
    { label: '全闭', action: 'close', params: { position: 0 } }
  ],
  'ac.main': [
    { label: '制冷 24℃', action: 'set_temp', params: { temp: 24 } },
    { label: '关空调', action: 'power', params: { on: false } }
  ],
  'freshair.main': [
    { label: '通风高档', action: 'set_fan_speed', params: { fan_speed: 'high' } },
    { label: '普通模式', action: 'set_mode', params: { mode: 'normal' } }
  ],
  'screen.main': [
    { label: '欢迎页', action: 'set_mode', params: { mode: 'welcome' } },
    { label: '汇报页', action: 'set_mode', params: { mode: 'presentation' } }
  ],
  'robot.openclaw': [
    { label: '巡逻', action: 'start_patrol', params: {} },
    { label: '回桩', action: 'dock', params: {} }
  ]
};

function DeviceStateView({ device }) {
  const state = device?.state || {};
  return (
    <div className="device-state">
      {Object.entries(state).map(([key, value]) => (
        <div className="device-state-row" key={key}>
          <span>{key}</span>
          <span>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function ControlPanel() {
  const scenes = useTwinStore((state) => state.scenes);
  const devicesByDomain = useTwinStore((state) => state.devicesByDomain);
  const devices = useTwinStore((state) => state.devices);
  const selectedDeviceId = useTwinStore((state) => state.selectedDeviceId);
  const selectDevice = useTwinStore((state) => state.selectDevice);
  const sendCommand = useTwinStore((state) => state.sendCommand);
  const activateScene = useTwinStore((state) => state.activateScene);
  const publishOfficeEvent = useTwinStore((state) => state.publishOfficeEvent);

  const selectedDevice = devices.find((device) => device.id === selectedDeviceId);
  const selectedActions = quickActions[selectedDeviceId] || [];

  return (
    <aside className="panel left-panel">
      <div className="panel-section">
        <div className="section-title">场景</div>
        <div className="button-grid">
          {scenes.map((scene) => (
            <button key={scene.id} onClick={() => activateScene(scene.id)}>
              {scene.name}
            </button>
          ))}
        </div>
      </div>

      <div className="panel-section">
        <div className="section-title">快速广播</div>
        <div className="button-grid single">
          <button
            onClick={() =>
              publishOfficeEvent({
                type: 'avatar.say',
                zone: 'sync',
                status: 'executing',
                message: '正在同步 digital twin 场景变化',
                agent_id: 'openclaw-main'
              })
            }
          >
            推送 Office UI 事件
          </button>
        </div>
      </div>

      <div className="panel-section">
        <div className="section-title">设备目录</div>
        {Object.entries(devicesByDomain).map(([domain, domainDevices]) => (
          <div key={domain} className="domain-block">
            <div className="domain-title">{domain}</div>
            <div className="device-list">
              {domainDevices.map((device) => (
                <button
                  key={device.id}
                  className={device.id === selectedDeviceId ? 'device-pill active' : 'device-pill'}
                  onClick={() => selectDevice(device.id)}
                >
                  {device.name}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="panel-section">
        <div className="section-title">当前设备</div>
        {selectedDevice ? (
          <>
            <div className="selected-device-title">{selectedDevice.name}</div>
            <div className="selected-device-meta">
              <span>{selectedDevice.id}</span>
              <span>{selectedDevice.location}</span>
            </div>
            <div className="button-grid">
              {selectedActions.map((action) => (
                <button
                  key={action.label}
                  onClick={() => sendCommand(selectedDevice.id, action.action, action.params)}
                >
                  {action.label}
                </button>
              ))}
            </div>
            <DeviceStateView device={selectedDevice} />
          </>
        ) : (
          <div className="muted">请选择一个设备</div>
        )}
      </div>
    </aside>
  );
}
