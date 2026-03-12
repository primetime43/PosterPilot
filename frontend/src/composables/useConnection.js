import { reactive, readonly } from 'vue'
import api from '../api.js'

/**
 * Shared connection state across all views.
 * Singleton — all components share the same reactive object.
 */
const state = reactive({
  connected: false,
  serverName: '',
  serverVersion: '',
  platform: '',
  platformVersion: '',
  machineId: '',
  host: '',
  libraryCount: 0,
})

async function checkStatus() {
  try {
    const data = await api.getStatus()
    state.connected = data.connected
    state.serverName = data.server_name || ''
    state.serverVersion = data.version || ''
    state.platform = data.platform || ''
    state.platformVersion = data.platform_version || ''
    state.machineId = data.machine_id || ''
    state.host = data.host || ''
    state.libraryCount = data.library_count || 0
  } catch {
    state.connected = false
  }
}

function setConnected(name, version) {
  state.connected = true
  state.serverName = name
  state.serverVersion = version
}

function setDisconnected() {
  state.connected = false
  state.serverName = ''
  state.serverVersion = ''
  state.platform = ''
  state.platformVersion = ''
  state.machineId = ''
  state.host = ''
  state.libraryCount = 0
}

export function useConnection() {
  return {
    state: readonly(state),
    checkStatus,
    setConnected,
    setDisconnected,
  }
}
