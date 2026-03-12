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
})

async function checkStatus() {
  try {
    const data = await api.getStatus()
    state.connected = data.connected
    state.serverName = data.server_name || ''
    state.serverVersion = data.version || ''
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
}

export function useConnection() {
  return {
    state: readonly(state),
    checkStatus,
    setConnected,
    setDisconnected,
  }
}
