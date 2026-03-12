/**
 * Centralized API client for PosterPilot backend.
 * All fetch calls go through here for consistent error handling.
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = await res.json()
  if (!res.ok && !data.error) {
    throw new Error(`HTTP ${res.status}`)
  }
  return data
}

export default {
  // OAuth
  startOAuth: () => request('/oauth/start', { method: 'POST' }),
  checkOAuth: () => request('/oauth/check'),
  cancelOAuth: () => request('/oauth/cancel', { method: 'POST' }),

  // Servers
  getServers: () => request('/servers'),

  // Connection
  connectToServer: (machineId) =>
    request('/connect/server', {
      method: 'POST',
      body: JSON.stringify({ machine_id: machineId }),
    }),
  connectManual: (baseUrl, token) =>
    request('/connect', {
      method: 'POST',
      body: JSON.stringify({ base_url: baseUrl, token }),
    }),
  disconnect: () => request('/disconnect', { method: 'POST' }),
  getStatus: () => request('/status'),

  // Libraries
  getLibraries: () => request('/libraries'),

  // Scanning
  startScan: (libraryKey, libraryTitle, forceRefresh = false) =>
    request('/scan', {
      method: 'POST',
      body: JSON.stringify({
        library_key: libraryKey,
        library_title: libraryTitle,
        force_refresh: forceRefresh,
      }),
    }),
  getScanStatus: (jobId) => request(`/scan/${jobId}`),

  // Jobs
  getJobs: () => request('/jobs'),

  // Apply
  startApply: (jobId, dryRun, itemKeys = null) =>
    request(`/apply/${jobId}`, {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun, item_keys: itemKeys }),
    }),
  getApplyStatus: (applyId) => request(`/apply/status/${applyId}`),
  applyCandidate: (jobId, itemKey, candidateKey) =>
    request(`/apply/${jobId}/${itemKey}/${candidateKey}`, { method: 'POST' }),

  // Export & manage
  exportJob: (jobId) => request(`/export/${jobId}`),
  deleteJob: (jobId) => request(`/jobs/${jobId}`, { method: 'DELETE' }),

  // Debug
  getItemPosters: (ratingKey) => request(`/item/${ratingKey}/posters`),

  // Logs
  getLogs: (lines = 500, level = '') =>
    request(`/logs?lines=${lines}${level ? '&level=' + level : ''}`),
  clearLogs: () => request('/logs/clear', { method: 'POST' }),

  // Ignore list
  getIgnoreList: () => request('/ignore'),
  addToIgnoreList: (items) =>
    request('/ignore', { method: 'POST', body: JSON.stringify({ items }) }),
  removeFromIgnoreList: (ratingKey) =>
    request(`/ignore/${ratingKey}`, { method: 'DELETE' }),
  clearIgnoreList: () => request('/ignore', { method: 'DELETE' }),

  // Config
  getConfig: () => request('/config'),
  updateConfig: (data) =>
    request('/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Thumbnail cache
  getCacheStats: () => request('/cache/stats'),
  clearCache: () => request('/cache/clear', { method: 'POST' }),
  thumbnailUrl: (originalUrl) =>
    `${BASE}/thumbnail?url=${encodeURIComponent(originalUrl)}`,
}
