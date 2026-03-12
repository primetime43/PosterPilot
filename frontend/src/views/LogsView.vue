<template>
  <div>
    <div class="page-header">
      <h2>Logs</h2>
      <div class="header-actions">
        <select v-model="levelFilter" @change="loadLogs" class="filter-select">
          <option value="">All Levels</option>
          <option value="DEBUG">Debug</option>
          <option value="INFO">Info</option>
          <option value="WARNING">Warning</option>
          <option value="ERROR">Error</option>
        </select>
        <button class="btn btn-outline btn-sm" @click="loadLogs">
          Refresh
        </button>
        <button class="btn btn-outline btn-sm" @click="toggleAutoRefresh">
          {{ autoRefresh ? 'Stop Auto-refresh' : 'Auto-refresh' }}
        </button>
        <button class="btn btn-outline btn-sm" style="color: var(--error);" @click="clearLogs">
          Clear Logs
        </button>
      </div>
    </div>

    <div class="card log-stats">
      <span class="text-muted text-xs">{{ total }} total lines</span>
      <span class="text-muted text-xs">Showing last {{ lines.length }}</span>
      <span v-if="autoRefresh" class="text-xs" style="color: var(--success);">Auto-refreshing every 3s</span>
    </div>

    <div class="log-container" ref="logContainer">
      <div v-if="loading && lines.length === 0" class="text-muted" style="padding: 20px;">Loading logs...</div>
      <div v-if="!loading && lines.length === 0" class="text-muted" style="padding: 20px;">No log entries found.</div>
      <div v-for="(line, idx) in lines" :key="idx"
           class="log-line" :class="getLineClass(line)">{{ line }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import api from '../api.js'
import { useToast } from '../composables/useToast.js'

const toast = useToast()

const lines = ref([])
const total = ref(0)
const loading = ref(false)
const levelFilter = ref('')
const autoRefresh = ref(false)
const logContainer = ref(null)
let refreshInterval = null

onMounted(async () => {
  await loadLogs()
  // Check if auto-refresh is enabled in settings
  try {
    const config = await api.getConfig()
    if (config.app?.log_auto_refresh) {
      autoRefresh.value = true
      refreshInterval = setInterval(loadLogs, 3000)
    }
  } catch {}
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})

async function loadLogs() {
  loading.value = true
  try {
    const data = await api.getLogs(500, levelFilter.value)
    lines.value = data.lines || []
    total.value = data.total || 0
    await nextTick()
    scrollToBottom()
  } catch (e) {
    console.error('Failed to load logs:', e)
  }
  loading.value = false
}

async function clearLogs() {
  try {
    await api.clearLogs()
    lines.value = []
    total.value = 0
    toast.success('Logs cleared')
  } catch (e) {
    toast.error('Failed to clear logs')
  }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    refreshInterval = setInterval(loadLogs, 3000)
  } else {
    if (refreshInterval) clearInterval(refreshInterval)
    refreshInterval = null
  }
}

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

function getLineClass(line) {
  if (line.includes('[ERROR]')) return 'log-error'
  if (line.includes('[WARNING]')) return 'log-warning'
  if (line.includes('[DEBUG]')) return 'log-debug'
  return ''
}
</script>
