<template>
  <div>
    <!-- Not connected: OAuth + Manual -->
    <template v-if="!connection.connected && !oauthActive && !serverPickerActive">
      <div class="dash-welcome">
        <h2>Welcome to PosterPilot</h2>
        <p class="text-muted">Connect to your Plex server to get started.</p>
      </div>

      <div class="card" style="max-width: 480px">
        <h3>Sign in to Plex</h3>
        <p class="text-muted" style="margin-bottom: 16px">
          Sign in with your Plex account to get started.
        </p>
        <button class="btn btn-primary" @click="startOAuth" :disabled="oauthStarting">
          {{ oauthStarting ? 'Starting...' : 'Sign in with Plex' }}
        </button>
        <p v-if="connectionError" class="error-text">{{ connectionError }}</p>
      </div>

      <div class="card" style="max-width: 480px">
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
    <div v-if="oauthActive" class="card" style="max-width: 480px">
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
    <div v-if="serverPickerActive && !connection.connected" class="card" style="max-width: 540px">
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

    <!-- ═══ Connected Dashboard ═══ -->
    <template v-if="connection.connected">

      <!-- Header -->
      <div class="dash-header">
        <div class="dash-header-left">
          <h2 style="margin: 0">Dashboard</h2>
          <div class="dash-server-tag">
            <span class="dash-server-dot"></span>
            <span>{{ connection.serverName }}</span>
            <span class="text-muted text-xs">{{ connection.serverVersion }}</span>
          </div>
        </div>
        <button class="btn btn-outline btn-sm" @click="disconnect">Disconnect</button>
      </div>

      <!-- Active Scan Progress -->
      <div v-if="scanState.active" class="dash-scan-active card">
        <div class="dash-scan-header">
          <div>
            <h3 style="margin: 0">
              {{ scanState.status === 'complete' ? 'Scan Complete' : scanState.status === 'failed' ? 'Scan Failed' : 'Scanning...' }}
            </h3>
            <span class="text-muted text-xs">{{ scanState.library }}</span>
          </div>
          <span class="badge" :class="'badge-' + scanState.status">
            {{ scanState.status }}
          </span>
        </div>
        <div class="progress-bar" style="margin: 12px 0 6px">
          <div class="progress-fill" :style="{ width: (scanState.progressPct || 0) + '%' }"></div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span class="text-muted text-xs">
            {{ scanState.processed || 0 }} / {{ scanState.total || 0 }} items
          </span>
          <span class="text-muted text-xs">{{ scanState.progressPct || 0 }}%</span>
        </div>
        <router-link v-if="scanState.status === 'complete'"
                     :to="{ name: 'scan', query: { job_id: scanState.jobId } }"
                     class="btn btn-primary btn-sm" style="margin-top: 10px">
          View Results
        </router-link>
      </div>

      <!-- Libraries -->
      <div class="dash-section">
        <h3 class="dash-section-title">Libraries</h3>
        <div class="dash-lib-grid">
          <div v-for="lib in libraries" :key="lib.key" class="dash-lib-card">
            <div class="dash-lib-top">
              <div class="dash-lib-icon">
                <svg v-if="lib.type === 'movie'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                  <line x1="7" y1="2" x2="7" y2="22"></line>
                  <line x1="17" y1="2" x2="17" y2="22"></line>
                  <line x1="2" y1="12" x2="22" y2="12"></line>
                  <line x1="2" y1="7" x2="7" y2="7"></line>
                  <line x1="2" y1="17" x2="7" y2="17"></line>
                  <line x1="17" y1="7" x2="22" y2="7"></line>
                  <line x1="17" y1="17" x2="22" y2="17"></line>
                </svg>
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="7" width="20" height="15" rx="2" ry="2"></rect>
                  <polyline points="17 2 12 7 7 2"></polyline>
                </svg>
              </div>
              <span class="dash-lib-type">{{ lib.type }}</span>
            </div>
            <h4 class="dash-lib-name">{{ lib.title }}</h4>
            <div class="dash-lib-count">
              <span class="dash-lib-count-num">{{ lib.item_count.toLocaleString() }}</span>
              <span class="dash-lib-count-label">items</span>
            </div>
            <div v-if="getLibLastScan(lib.title)" class="dash-lib-lastscan">
              <span class="text-muted text-xs">Last scan {{ formatRelative(getLibLastScan(lib.title).started_at) }}</span>
              <span v-if="getLibLastScan(lib.title).changes > 0" class="text-success text-xs">
                {{ getLibLastScan(lib.title).changes }} changes
              </span>
            </div>
            <div class="dash-lib-actions">
              <button class="btn btn-primary btn-sm" @click="startScan(lib)"
                      title="Check for better poster options">
                Scan
              </button>
              <button class="btn btn-outline btn-sm" @click="startScan(lib, true)"
                      title="Re-evaluate all items">
                Force Rescan
              </button>
            </div>
          </div>
        </div>
        <p v-if="libraries.length === 0 && !loadingLibraries" class="text-muted">
          No poster-capable libraries found.
        </p>
      </div>

      <!-- Recent Scans -->
      <div v-if="jobs.length > 0" class="dash-section">
        <h3 class="dash-section-title">Recent Scans</h3>
        <div class="dash-jobs">
          <div v-for="job in jobs" :key="job.job_id" class="dash-job-row">
            <div class="dash-job-main">
              <span class="dash-job-lib">{{ job.library }}</span>
              <span class="badge" :class="'badge-' + job.status">{{ job.status }}</span>
            </div>
            <div class="dash-job-meta">
              <span>{{ job.total_items.toLocaleString() }} items</span>
              <span class="dash-job-sep">&middot;</span>
              <span :class="{ 'text-success': job.changes > 0 }">{{ job.changes }} changes</span>
              <span class="dash-job-sep">&middot;</span>
              <span>{{ formatRelative(job.started_at) }}</span>
            </div>
            <div class="dash-job-actions">
              <router-link
                :to="{ name: 'scan', query: { job_id: job.job_id } }"
                class="btn btn-sm btn-outline"
              >View</router-link>
              <button class="btn btn-sm btn-outline dash-job-delete"
                      @click="deleteJob(job.job_id)"
                      title="Delete this scan">&#10005;</button>
            </div>
          </div>
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import api from '../api.js'
import { useConnection } from '../composables/useConnection.js'
import { useToast } from '../composables/useToast.js'
import { useScanProgress } from '../composables/useScanProgress.js'

const toast = useToast()
const { state: scanState, startPolling: startScanPolling, checkForActive } = useScanProgress()

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
const jobs = ref([])

function getLibLastScan(libTitle) {
  return jobs.value.find((j) => j.library === libTitle && j.status === 'complete')
}

onMounted(async () => {
  await checkStatus()
  if (connection.connected) {
    await loadLibraries()
    await loadJobs()
    checkForActive()
  }
})

onUnmounted(() => {
  if (oauthPollInterval) clearInterval(oauthPollInterval)
})

// Watch shared scan state — reload jobs when scan completes
let toastFired = false
watch(
  () => scanState.status,
  (status) => {
    if (status === 'complete' && !toastFired) {
      toastFired = true
      toast.success('Scan complete: ' + scanState.library)
      loadJobs()
    } else if (status === 'failed' && !toastFired) {
      toastFired = true
      toast.error('Scan failed: ' + scanState.library)
      loadJobs()
    } else if (status === 'scanning') {
      toastFired = false
    }
  }
)

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
  jobs.value = []
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
    startScanPolling(data.job_id, lib.title)
    await loadJobs()
  } catch (e) {
    console.error('Failed to start scan:', e)
  }
}

async function deleteJob(jobId) {
  try {
    await api.deleteJob(jobId)
    await loadJobs()
  } catch (e) {
    console.error('Failed to delete job:', e)
  }
}

function formatRelative(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}
</script>
