<template>
  <div>
    <h2>Dashboard</h2>

    <!-- Not connected: OAuth + Manual -->
    <template v-if="!connection.connected && !oauthActive && !serverPickerActive">
      <div class="card">
        <h3>Sign in to Plex</h3>
        <p class="text-muted" style="margin-bottom: 16px">
          Sign in with your Plex account to get started.
        </p>
        <button class="btn btn-primary" @click="startOAuth" :disabled="oauthStarting">
          {{ oauthStarting ? 'Starting...' : 'Sign in with Plex' }}
        </button>
        <p v-if="connectionError" class="error-text">{{ connectionError }}</p>
      </div>

      <div class="card">
        <button class="btn btn-outline btn-sm" @click="showManual = !showManual">
          {{ showManual ? 'Hide manual login' : 'Use manual token instead' }}
        </button>
        <div v-if="showManual" style="margin-top: 16px">
          <div class="form-group">
            <label>Plex Server URL</label>
            <input type="text" v-model="plexUrl" placeholder="http://localhost:32400" />
          </div>
          <div class="form-group">
            <label>Plex Token</label>
            <input type="password" v-model="plexToken" placeholder="Your Plex token" />
          </div>
          <button class="btn btn-primary" @click="connectManual" :disabled="connecting">
            {{ connecting ? 'Connecting...' : 'Connect' }}
          </button>
        </div>
      </div>
    </template>

    <!-- OAuth: Waiting -->
    <div v-if="oauthActive" class="card">
      <h3>Waiting for Plex sign-in...</h3>
      <p class="text-muted">
        A Plex sign-in window should have opened. Complete the sign-in there, then return here.
      </p>
      <div class="progress-bar" style="margin: 16px 0">
        <div class="progress-fill" style="width: 100%; animation: pulse 1.5s infinite"></div>
      </div>
      <p class="text-muted text-xs">
        Didn't see a popup?
        <a :href="oauthUrl" target="_blank" style="color: var(--accent)">Click here to open the sign-in page.</a>
      </p>
      <button class="btn btn-outline btn-sm" @click="cancelOAuth" style="margin-top: 8px">Cancel</button>
      <p v-if="connectionError" class="error-text">{{ connectionError }}</p>
    </div>

    <!-- Server Picker -->
    <div v-if="serverPickerActive && !connection.connected" class="card">
      <h3>Select a Plex Server</h3>
      <p class="text-muted" style="margin-bottom: 12px">
        Signed in as <strong>{{ oauthUsername }}</strong>. Choose which server to manage:
      </p>
      <div v-if="loadingServers" class="text-muted">Loading servers...</div>
      <div v-else class="server-list">
        <button
          v-for="srv in servers"
          :key="srv.machine_id"
          class="server-row"
          @click="connectToServer(srv)"
          :disabled="connecting"
          type="button"
        >
          <div class="server-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
              <line x1="6" y1="6" x2="6.01" y2="6"></line>
              <line x1="6" y1="18" x2="6.01" y2="18"></line>
            </svg>
          </div>
          <div class="server-info">
            <span class="server-name">{{ srv.name }}</span>
            <span class="badge" :class="srv.owned ? 'badge-change' : ''">
              {{ srv.owned ? 'owned' : 'shared' }}
            </span>
          </div>
          <div class="server-arrow">&#8250;</div>
        </button>
      </div>
      <p v-if="!loadingServers && servers.length === 0" class="text-muted">
        No Plex servers found on this account.
      </p>
      <div style="margin-top: 12px; display: flex; align-items: center; gap: 12px">
        <button class="btn btn-outline btn-sm" @click="serverPickerActive = false; oauthUsername = ''">Back</button>
        <span v-if="connecting" class="text-muted">Connecting...</span>
      </div>
      <p v-if="connectionError" class="error-text">{{ connectionError }}</p>
    </div>

    <!-- Connected Status -->
    <div v-if="connection.connected" class="card">
      <div class="card-header">
        <h3>Connected to {{ connection.serverName }}</h3>
        <button class="btn btn-sm btn-outline" @click="disconnect">Disconnect</button>
      </div>
      <p class="text-muted">Server version: {{ connection.serverVersion }}</p>
    </div>

    <!-- Libraries -->
    <div v-if="connection.connected">
      <h3>Libraries</h3>
      <div class="card-grid">
        <div v-for="lib in libraries" :key="lib.key" class="card library-card">
          <div class="card-header">
            <h4>{{ lib.title }}</h4>
            <span class="badge">{{ lib.type }}</span>
          </div>
          <p>{{ lib.item_count }} items</p>
          <div class="card-actions">
            <button class="btn btn-primary btn-sm" @click="startScan(lib)"
                    title="Check for better poster options and recommend changes">
              Scan
            </button>
            <button class="btn btn-outline btn-sm" @click="startScan(lib, true)"
                    title="Re-evaluate all items, even ones that were previously skipped or look fine">
              Force Rescan
            </button>
          </div>
        </div>
      </div>
      <p v-if="libraries.length === 0 && !loadingLibraries" class="text-muted">
        No poster-capable libraries found.
      </p>
    </div>

    <!-- Active Scan Progress -->
    <div v-if="activeScan" class="card scan-progress-card">
      <h3>Scanning: {{ activeScan.library }}</h3>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: (activeScan.progress_pct || 0) + '%' }"></div>
      </div>
      <p class="text-muted">
        {{ activeScan.processed_items || 0 }} / {{ activeScan.total_items || 0 }} items processed
        ({{ activeScan.progress_pct || 0 }}%)
      </p>
      <p v-if="activeScan.status === 'complete'" class="text-success">
        Scan complete!
        {{ activeScan.changes }} changes recommended,
        {{ activeScan.skipped }} skipped,
        {{ activeScan.failed }} failed.
        <router-link :to="{ name: 'scan', query: { job_id: activeScan.job_id } }">View Results</router-link>
      </p>
    </div>

    <!-- Recent Jobs -->
    <div v-if="connection.connected && jobs.length > 0">
      <h3>Recent Scans</h3>
      <table class="table">
        <thead>
          <tr>
            <th>Library</th>
            <th>Status</th>
            <th>Items</th>
            <th>Changes</th>
            <th>Started</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.job_id">
            <td>{{ job.library }}</td>
            <td><span class="badge" :class="'badge-' + job.status">{{ job.status }}</span></td>
            <td>{{ job.total_items }}</td>
            <td>{{ job.changes }}</td>
            <td>{{ formatDate(job.started_at) }}</td>
            <td style="display: flex; gap: 4px;">
              <router-link
                :to="{ name: 'scan', query: { job_id: job.job_id } }"
                class="btn btn-sm btn-outline"
              >View</router-link>
              <button class="btn btn-sm btn-outline" style="color: var(--error); border-color: var(--error);"
                      @click="deleteJob(job.job_id)"
                      title="Delete this scan">&#10005;</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api.js'
import { useConnection } from '../composables/useConnection.js'
import { useToast } from '../composables/useToast.js'

const toast = useToast()

const { state: connection, setConnected, setDisconnected, checkStatus } = useConnection()

// Manual login
const showManual = ref(false)
const plexUrl = ref('')
const plexToken = ref('')
const connecting = ref(false)
const connectionError = ref('')

// OAuth
const oauthActive = ref(false)
const oauthStarting = ref(false)
const oauthUrl = ref('')
const oauthUsername = ref('')
let oauthPollInterval = null

// Server picker
const serverPickerActive = ref(false)
const servers = ref([])
const loadingServers = ref(false)

// Libraries & scans
const libraries = ref([])
const loadingLibraries = ref(false)
const activeScan = ref(null)
let scanPollInterval = null
const jobs = ref([])

onMounted(async () => {
  await checkStatus()
  if (connection.connected) {
    await loadLibraries()
    await loadJobs()
  }
})

onUnmounted(() => {
  if (oauthPollInterval) clearInterval(oauthPollInterval)
  if (scanPollInterval) clearInterval(scanPollInterval)
})

// OAuth flow
async function startOAuth() {
  oauthStarting.value = true
  connectionError.value = ''
  try {
    const data = await api.startOAuth()
    if (data.error) {
      connectionError.value = data.error
      oauthStarting.value = false
      return
    }
    oauthUrl.value = data.oauth_url
    oauthActive.value = true
    window.open(data.oauth_url, 'PlexOAuth', 'width=800,height=700,menubar=no,toolbar=no')
    pollOAuth()
  } catch (e) {
    connectionError.value = 'Failed to start OAuth: ' + e.message
  }
  oauthStarting.value = false
}

function pollOAuth() {
  if (oauthPollInterval) clearInterval(oauthPollInterval)
  oauthPollInterval = setInterval(async () => {
    try {
      const data = await api.checkOAuth()
      if (data.status === 'authenticated') {
        clearInterval(oauthPollInterval)
        oauthPollInterval = null
        oauthActive.value = false
        oauthUsername.value = data.username || data.email || ''
        serverPickerActive.value = true
        await loadServers()
      } else if (data.status === 'expired' || data.status === 'error') {
        clearInterval(oauthPollInterval)
        oauthPollInterval = null
        oauthActive.value = false
        connectionError.value = data.error || 'OAuth failed'
      }
    } catch (e) {
      clearInterval(oauthPollInterval)
      oauthPollInterval = null
      oauthActive.value = false
      connectionError.value = 'OAuth check failed: ' + e.message
    }
  }, 2000)
}

function cancelOAuth() {
  if (oauthPollInterval) {
    clearInterval(oauthPollInterval)
    oauthPollInterval = null
  }
  api.cancelOAuth()
  oauthActive.value = false
  connectionError.value = ''
}

async function loadServers() {
  loadingServers.value = true
  try {
    const data = await api.getServers()
    servers.value = data.servers || []
  } catch (e) {
    connectionError.value = 'Failed to load servers: ' + e.message
  }
  loadingServers.value = false
}

async function connectToServer(srv) {
  connecting.value = true
  connectionError.value = ''
  try {
    const data = await api.connectToServer(srv.machine_id)
    if (data.connected) {
      setConnected(data.server_name, data.version)
      serverPickerActive.value = false
      toast.success(`Connected to ${data.server_name}`)
      await loadLibraries()
    } else {
      connectionError.value = data.error
    }
  } catch (e) {
    connectionError.value = 'Failed to connect: ' + e.message
  }
  connecting.value = false
}

async function connectManual() {
  connecting.value = true
  connectionError.value = ''
  try {
    const data = await api.connectManual(plexUrl.value, plexToken.value)
    if (data.connected) {
      setConnected(data.server_name, data.version)
      toast.success(`Connected to ${data.server_name}`)
      await loadLibraries()
    } else {
      connectionError.value = data.error
    }
  } catch (e) {
    connectionError.value = 'Failed to connect: ' + e.message
  }
  connecting.value = false
}

async function disconnect() {
  await api.disconnect()
  setDisconnected()
  libraries.value = []
  serverPickerActive.value = false
  oauthUsername.value = ''
}

async function loadLibraries() {
  loadingLibraries.value = true
  try {
    const data = await api.getLibraries()
    libraries.value = data.libraries || []
  } catch (e) {
    console.error('Failed to load libraries:', e)
  }
  loadingLibraries.value = false
}

async function loadJobs() {
  try {
    const data = await api.getJobs()
    jobs.value = (data.jobs || []).reverse()
  } catch {}
}

async function startScan(lib, forceRefresh = false) {
  try {
    const data = await api.startScan(lib.key, lib.title, forceRefresh)
    activeScan.value = {
      job_id: data.job_id,
      library: lib.title,
      status: 'scanning',
      progress_pct: 0,
      processed_items: 0,
      total_items: 0,
    }
    pollScanStatus(data.job_id)
  } catch (e) {
    console.error('Failed to start scan:', e)
  }
}

function pollScanStatus(jobId) {
  if (scanPollInterval) clearInterval(scanPollInterval)
  scanPollInterval = setInterval(async () => {
    try {
      const data = await api.getScanStatus(jobId)
      activeScan.value = data
      if (data.status === 'complete' || data.status === 'failed') {
        clearInterval(scanPollInterval)
        scanPollInterval = null
        if (data.status === 'complete') {
          toast.success(`Scan complete: ${data.changes} changes found`)
        } else {
          toast.error(`Scan failed: ${data.error || 'Unknown error'}`)
        }
        await loadJobs()
      }
    } catch {
      clearInterval(scanPollInterval)
      scanPollInterval = null
    }
  }, 1500)
}

async function deleteJob(jobId) {
  try {
    await api.deleteJob(jobId)
    await loadJobs()
  } catch (e) {
    console.error('Failed to delete job:', e)
  }
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}
</script>
