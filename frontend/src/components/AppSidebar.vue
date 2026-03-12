<template>
  <nav class="sidebar">
    <div class="sidebar-brand">
      <h1>PosterPilot</h1>
    </div>
    <ul class="sidebar-nav">
      <li><router-link to="/">Dashboard</router-link></li>
      <li><router-link to="/scan">Scan Results</router-link></li>
      <li><router-link to="/settings">Settings</router-link></li>
      <li><router-link to="/logs">Logs</router-link></li>
    </ul>
    <div v-if="scan.active" class="sidebar-scan">
      <div class="sidebar-scan-label">
        {{ scan.status === 'complete' ? 'Scan complete' : scan.status === 'failed' ? 'Scan failed' : 'Scanning...' }}
      </div>
      <div class="sidebar-scan-title">{{ scan.library }}</div>
      <div class="progress-bar" style="margin: 6px 0 2px">
        <div class="progress-fill" :style="{ width: scan.progressPct + '%' }"></div>
      </div>
      <div class="sidebar-scan-stats">{{ scan.processed }} / {{ scan.total }} ({{ scan.progressPct }}%)</div>
    </div>
    <div class="sidebar-footer">
      <button class="theme-toggle" @click="toggle" :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
        <span class="theme-toggle-icon">{{ theme === 'dark' ? '&#9788;' : '&#9790;' }}</span>
        <span>{{ theme === 'dark' ? 'Light mode' : 'Dark mode' }}</span>
      </button>
      <div class="connection-status" :class="{ connected: connection.connected }" style="margin-top: 10px">
        <span class="status-dot"></span>
        <span>{{ connection.connected ? 'Connected' : 'Disconnected' }}</span>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useConnection } from '../composables/useConnection.js'
import { useTheme } from '../composables/useTheme.js'
import { useScanProgress } from '../composables/useScanProgress.js'

const { state: connection } = useConnection()
const { theme, toggle } = useTheme()
const { state: scan } = useScanProgress()
</script>
