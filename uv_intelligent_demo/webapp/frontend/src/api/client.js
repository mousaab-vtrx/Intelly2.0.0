const API_PORT = 8000;
export const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;

async function parseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || payload.message || `Request failed with status ${response.status}`;
  } catch (_err) {
    return `Request failed with status ${response.status}`;
  }
}

export async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function fetchOptionalJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}
