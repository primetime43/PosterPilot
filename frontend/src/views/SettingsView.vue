<template>
  <div>
    <h2>Settings</h2>

    <!-- Plex Connection -->
    <div class="card">
      <h3>Plex Connection</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Server URL</label>
          <input type="text" v-model="config.plex.base_url" placeholder="http://localhost:32400" />
        </div>
        <div class="form-group">
          <label>Token</label>
          <div style="position: relative">
            <input :type="showToken ? 'text' : 'password'" v-model="config.plex.token"
                   placeholder="Plex token" style="padding-right: 40px" />
            <button type="button" class="token-toggle" @click="showToken = !showToken"
                    :title="showToken ? 'Hide token' : 'Show token'">
              {{ showToken ? 'Hide' : 'Show' }}
            </button>
          </div>
        </div>
        <div class="form-group">
          <label>Timeout (seconds)</label>
          <input type="number" v-model.number="config.plex.timeout" min="5" max="120" />
        </div>
      </div>
    </div>

    <!-- App Settings -->
    <div class="card">
      <h3>Application</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Host</label>
          <input type="text" v-model="config.app.host" />
        </div>
        <div class="form-group">
          <label>Port</label>
          <input type="number" v-model.number="config.app.port" min="1024" max="65535" />
        </div>
        <div class="form-group">
          <label>Log Level</label>
          <select v-model="config.app.log_level">
            <option>DEBUG</option>
            <option>INFO</option>
            <option>WARNING</option>
            <option>ERROR</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <label class="toggle-label">
          <input type="checkbox" v-model="config.app.dry_run" /> Dry run by default
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="config.app.skip_locked" /> Skip locked posters
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="config.app.force_replace" /> Force replace existing posters
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="config.app.log_auto_refresh" /> Auto-refresh logs page
        </label>
      </div>
    </div>

    <!-- Scoring Settings -->
    <div class="card">
      <h3>Poster Scoring</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Minimum Width (px)</label>
          <input type="number" v-model.number="config.scoring.min_width" min="0" />
        </div>
        <div class="form-group">
          <label>Minimum Height (px)</label>
          <input type="number" v-model.number="config.scoring.min_height" min="0" />
        </div>
        <div class="form-group">
          <label>Preferred Aspect Ratio</label>
          <input type="number" v-model.number="config.scoring.preferred_aspect_ratio"
                 step="0.01" min="0.1" max="2.0" />
          <small class="text-muted">Standard poster: 0.667 (2:3)</small>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Resolution Weight</label>
          <input type="number" v-model.number="config.scoring.resolution_weight" step="0.1" min="0" />
        </div>
        <div class="form-group">
          <label>Aspect Ratio Weight</label>
          <input type="number" v-model.number="config.scoring.aspect_ratio_weight" step="0.1" min="0" />
        </div>
        <div class="form-group">
          <label>Provider Weight</label>
          <input type="number" v-model.number="config.scoring.provider_weight" step="0.1" min="0" />
        </div>
      </div>
      <div class="form-row">
        <label class="toggle-label">
          <input type="checkbox" v-model="config.scoring.prefer_provider_posters" /> Prefer provider posters
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="config.scoring.penalize_landscape" /> Penalize landscape images
        </label>
      </div>
      <div class="form-group">
        <label>Provider Priority (comma separated)</label>
        <input type="text" v-model="providerPriorityStr" placeholder="tmdb,tvdb,gracenote,local,upload" />
      </div>
    </div>

    <!-- Library Filters -->
    <div class="card">
      <h3>Library Filters</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Whitelisted Libraries (comma separated, empty = all)</label>
          <input type="text" v-model="whitelistStr" placeholder="Movies, TV Shows" />
        </div>
        <div class="form-group">
          <label>Blacklisted Libraries (comma separated)</label>
          <input type="text" v-model="blacklistStr" placeholder="Music, Photos" />
        </div>
      </div>
    </div>

    <div class="card-actions">
      <button class="btn btn-primary" @click="save" :disabled="saving">
        {{ saving ? 'Saving...' : 'Save Settings' }}
      </button>
    </div>

    <!-- Ignore List -->
    <div class="card">
      <div class="card-header">
        <h3>Ignore List</h3>
        <span class="text-muted text-xs">{{ ignoreItems.length }} items</span>
      </div>
      <p class="text-muted" style="margin-bottom: 12px; font-size: 0.85rem">
        Items on this list will be skipped during scans — no poster changes will be suggested for them.
      </p>
      <div v-if="ignoreItems.length > 0" class="ignore-list">
        <div v-for="item in ignoreItems" :key="item.rating_key" class="ignore-item">
          <span class="ignore-title">{{ item.title || item.rating_key }}</span>
          <span class="text-muted text-xs">{{ item.rating_key }}</span>
          <button class="btn btn-outline btn-sm" @click="removeIgnored(item.rating_key)"
                  style="color: var(--error); border-color: var(--error); margin-left: auto;">
            Remove
          </button>
        </div>
      </div>
      <p v-else class="text-muted text-xs">No ignored items.</p>
      <div v-if="ignoreItems.length > 0" class="card-actions">
        <button class="btn btn-outline btn-sm" @click="clearIgnoreList"
                style="color: var(--error); border-color: var(--error);">
          Clear All
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api.js'
import { useToast } from '../composables/useToast.js'

const toast = useToast()

const config = reactive({
  plex: { base_url: '', token: '', timeout: 30 },
  scoring: {
    min_width: 300,
    min_height: 450,
    preferred_aspect_ratio: 0.6667,
    aspect_ratio_tolerance: 0.15,
    prefer_provider_posters: true,
    provider_priority: [],
    resolution_weight: 1.0,
    aspect_ratio_weight: 1.5,
    provider_weight: 1.0,
    penalize_landscape: true,
    landscape_penalty: -5.0,
  },
  app: {
    host: '0.0.0.0',
    port: 8888,
    dry_run: true,
    skip_locked: true,
    force_replace: false,
    log_auto_refresh: false,
    log_level: 'INFO',
    whitelisted_libraries: [],
    blacklisted_libraries: [],
  },
})

const showToken = ref(false)
const providerPriorityStr = ref('')
const whitelistStr = ref('')
const blacklistStr = ref('')
const saving = ref(false)

// Ignore list
const ignoreItems = ref([])

onMounted(async () => {
  try {
    const data = await api.getConfig()
    if (data.plex) Object.assign(config.plex, data.plex)
    if (data.scoring) Object.assign(config.scoring, data.scoring)
    if (data.app) Object.assign(config.app, data.app)

    providerPriorityStr.value = (config.scoring.provider_priority || []).join(', ')
    whitelistStr.value = (config.app.whitelisted_libraries || []).join(', ')
    blacklistStr.value = (config.app.blacklisted_libraries || []).join(', ')
  } catch (e) {
    console.error('Failed to load config:', e)
  }
  await loadIgnoreList()
})

async function save() {
  saving.value = true

  config.scoring.provider_priority = providerPriorityStr.value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s)
  config.app.whitelisted_libraries = whitelistStr.value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s)
  config.app.blacklisted_libraries = blacklistStr.value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s)

  try {
    await api.updateConfig({
      scoring: config.scoring,
      app: config.app,
    })
    toast.success('Settings saved!')
  } catch (e) {
    toast.error('Failed to save: ' + e.message)
  }
  saving.value = false
}

async function loadIgnoreList() {
  try {
    const data = await api.getIgnoreList()
    ignoreItems.value = data.items || []
  } catch {}
}

async function removeIgnored(ratingKey) {
  try {
    await api.removeFromIgnoreList(ratingKey)
    ignoreItems.value = ignoreItems.value.filter((i) => i.rating_key !== ratingKey)
    toast.info('Item removed from ignore list')
  } catch (e) {
    toast.error('Failed to remove: ' + e.message)
  }
}

async function clearIgnoreList() {
  try {
    await api.clearIgnoreList()
    ignoreItems.value = []
    toast.info('Ignore list cleared')
  } catch (e) {
    toast.error('Failed to clear: ' + e.message)
  }
}
</script>
