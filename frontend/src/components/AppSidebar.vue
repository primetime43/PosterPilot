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
    <div class="sidebar-footer">
      <div class="connection-status" :class="{ connected: connection.connected }">
        <span class="status-dot"></span>
        <span>{{ connection.connected ? 'Connected' : 'Disconnected' }}</span>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useConnection } from '../composables/useConnection.js'

const { state: connection } = useConnection()
</script>
