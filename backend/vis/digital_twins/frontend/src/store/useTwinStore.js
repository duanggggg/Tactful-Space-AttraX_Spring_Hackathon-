import { create } from 'zustand';
import { getBaseUrl, getJson, postJson } from '../api/client.js';

function mergeDeviceState(devices, deviceId, deviceState) {
  return devices.map((device) =>
    device.id === deviceId ? { ...device, state: { ...device.state, ...deviceState } } : device
  );
}

function groupByDomain(devices) {
  return devices.reduce((acc, device) => {
    const key = device.domain || 'other';
    acc[key] = acc[key] || [];
    acc[key].push(device);
    return acc;
  }, {});
}

function applyEvent(state, event) {
  let nextDevices = state.devices;
  let nextScene = state.activeScene;
  let nextTelemetry = state.telemetry;
  if (event.device_id && event.device_state) {
    nextDevices = mergeDeviceState(state.devices, event.device_id, event.device_state);
  }
  if (event.type === 'scene.activated' && event.scene) {
    nextScene = event.scene;
  }
  if (event.type === 'sensor.rain_changed' && event.device_state) {
    const weather = {
      ...(state.telemetry?.weather || {}),
      ...event.device_state
    };
    nextTelemetry = {
      ...(state.telemetry || {}),
      weather,
      updated_at: event.ts
    };
  }
  const recentEvents = [event, ...state.recentEvents].slice(0, 60);
  return {
    devices: nextDevices,
    activeScene: nextScene,
    telemetry: nextTelemetry,
    recentEvents
  };
}

export const useTwinStore = create((set, get) => ({
  baseUrl: getBaseUrl(),
  layout: null,
  devices: [],
  devicesByDomain: {},
  scenes: [],
  activeScene: 'manual',
  telemetry: null,
  recentEvents: [],
  selectedDeviceId: 'light.perimeter',
  connection: 'idle',
  loading: false,
  error: '',
  eventSource: null,

  async bootstrap() {
    set({ loading: true, error: '' });
    try {
      const [layout, devicesPayload, scenesPayload, telemetry] = await Promise.all([
        getJson('/api/v1/layout'),
        getJson('/api/v1/devices'),
        getJson('/api/v1/scenes'),
        getJson('/api/v1/telemetry')
      ]);
      const devices = devicesPayload.items || [];
      set({
        layout,
        devices,
        devicesByDomain: groupByDomain(devices),
        scenes: scenesPayload.items || [],
        activeScene: scenesPayload.active_scene || 'manual',
        telemetry,
        loading: false
      });
    } catch (error) {
      set({ error: error.message || String(error), loading: false, connection: 'error' });
    }
  },

  connectEventStream() {
    const current = get().eventSource;
    if (current) return;
    const eventSource = new EventSource(`${get().baseUrl}/api/v1/events/stream`);
    eventSource.onopen = () => set({ connection: 'connected' });
    eventSource.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data);
        set((state) => applyEvent(state, event));
      } catch (error) {
        console.error('Failed to parse event', error);
      }
    };
    eventSource.onerror = () => {
      set({ connection: 'reconnecting' });
    };
    set({ eventSource });
  },

  disconnectEventStream() {
    const source = get().eventSource;
    if (source) {
      source.close();
    }
    set({ eventSource: null, connection: 'idle' });
  },

  async refreshTelemetry() {
    try {
      const telemetry = await getJson('/api/v1/telemetry');
      set({ telemetry });
    } catch (error) {
      set({ error: error.message || String(error) });
    }
  },

  async refreshDevices() {
    try {
      const devicesPayload = await getJson('/api/v1/devices');
      const devices = devicesPayload.items || [];
      set({
        devices,
        devicesByDomain: groupByDomain(devices),
        activeScene: devicesPayload.active_scene || get().activeScene
      });
    } catch (error) {
      set({ error: error.message || String(error) });
    }
  },

  async sendCommand(deviceId, action, params = {}) {
    await postJson(`/api/v1/devices/${encodeURIComponent(deviceId)}/commands`, {
      action,
      params,
      source: 'ui.digital_twin'
    });
  },

  async activateScene(scene) {
    await postJson('/api/v1/scenes/activate', {
      scene,
      source: 'ui.digital_twin'
    });
  },

  async publishOfficeEvent(payload) {
    await postJson('/api/v1/office-ui/events', payload);
  },

  selectDevice(deviceId) {
    set({ selectedDeviceId: deviceId });
  }
}));
