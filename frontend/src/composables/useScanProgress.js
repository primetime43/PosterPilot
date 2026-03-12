import { reactive, readonly } from 'vue'
import api from '../api.js'

const state = reactive({
  active: false,
  jobId: null,
  library: '',
  progressPct: 0,
  processed: 0,
  total: 0,
  status: '',
})

let pollInterval = null

function startPolling(jobId, library) {
  state.active = true
  state.jobId = jobId
  state.library = library
  state.progressPct = 0
  state.processed = 0
  state.total = 0
  state.status = 'scanning'

  if (pollInterval) clearInterval(pollInterval)
  pollInterval = setInterval(async () => {
    try {
      const data = await api.getScanStatus(jobId)
      state.progressPct = data.progress_pct || 0
      state.processed = data.processed_items || 0
      state.total = data.total_items || 0
      state.status = data.status
      state.library = data.library || library

      if (data.status === 'complete' || data.status === 'failed') {
        clearInterval(pollInterval)
        pollInterval = null
        // Keep showing for a few seconds then clear
        setTimeout(() => {
          state.active = false
        }, 5000)
      }
    } catch {
      clearInterval(pollInterval)
      pollInterval = null
      state.active = false
    }
  }, 1500)
}

function stop() {
  if (pollInterval) clearInterval(pollInterval)
  pollInterval = null
  state.active = false
}

export function useScanProgress() {
  return { state: readonly(state), startPolling, stop }
}
