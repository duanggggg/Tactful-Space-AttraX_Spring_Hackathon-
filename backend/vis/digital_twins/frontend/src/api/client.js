const DEFAULT_BASE_URL = import.meta.env.VITE_TWIN_BASE_URL || '';

export function getBaseUrl() {
  return DEFAULT_BASE_URL.replace(/\/$/, '');
}

async function parseResponse(response) {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function getJson(path) {
  const response = await fetch(`${getBaseUrl()}${path}`);
  return parseResponse(response);
}

export async function postJson(path, body) {
  const response = await fetch(`${getBaseUrl()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return parseResponse(response);
}
