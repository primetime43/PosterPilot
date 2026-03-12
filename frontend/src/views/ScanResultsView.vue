<template>
  <div>
    <div class="page-header">
      <h2>Scan Results</h2>
      <div class="header-actions">
        <input type="text" placeholder="Search titles..." v-model="searchQuery"
               class="search-input" @input="filterItems" />
        <select v-model="filterAction" @change="filterItems" class="filter-select">
          <option value="all">All</option>
          <option value="change">Changes</option>
          <option value="uploaded">Uploaded</option>
          <option value="broken">Broken</option>
          <option value="skip">Skipped</option>
          <option value="no_alternatives">No Alternatives</option>
          <option value="failed">Failed</option>
          <option value="locked">Locked</option>
        </select>
        <button v-if="filterAction !== 'all'" class="btn btn-outline btn-sm"
                @click="filterAction = 'all'; filterItems()">
          Clear Filter
        </button>
      </div>
    </div>

    <!-- No job -->
    <div v-if="!job" class="card">
      <p class="text-muted">No scan results to display. Start a scan from the Dashboard.</p>
    </div>

    <!-- Job Summary -->
    <div v-if="job" class="card summary-card">
      <div class="summary-grid">
        <button class="summary-item" :class="{ 'summary-active': filterAction === 'all' }"
                @click="filterAction = 'all'; filterItems()">
          <span class="summary-value">{{ job.total_items || 0 }}</span>
          <span class="summary-label">Total Items</span>
        </button>
        <button class="summary-item summary-change" :class="{ 'summary-active': filterAction === 'change' }"
                @click="filterAction = 'change'; filterItems()">
          <span class="summary-value">{{ unappliedChanges }}</span>
          <span class="summary-label">Changes</span>
        </button>
        <button class="summary-item summary-skip" :class="{ 'summary-active': filterAction === 'skip' }"
                @click="filterAction = 'skip'; filterItems()">
          <span class="summary-value">{{ job.skipped || 0 }}</span>
          <span class="summary-label">Skipped</span>
        </button>
        <button class="summary-item summary-locked" :class="{ 'summary-active': filterAction === 'locked' }"
                @click="filterAction = 'locked'; filterItems()">
          <span class="summary-value">{{ lockedCount }}</span>
          <span class="summary-label">Locked</span>
        </button>
        <button class="summary-item summary-fail" :class="{ 'summary-active': filterAction === 'failed' }"
                @click="filterAction = 'failed'; filterItems()">
          <span class="summary-value">{{ job.failed || 0 }}</span>
          <span class="summary-label">Failed</span>
        </button>
        <button class="summary-item summary-uploaded" :class="{ 'summary-active': filterAction === 'uploaded' }"
                @click="filterAction = 'uploaded'; filterItems()"
                title="Posters uploaded by Kometa or manually — review for quality">
          <span class="summary-value">{{ uploadedCount }}</span>
          <span class="summary-label">Uploaded</span>
        </button>
        <button class="summary-item summary-broken" :class="{ 'summary-active': filterAction === 'broken' }"
                @click="filterAction = 'broken'; filterItems()">
          <span class="summary-value">{{ brokenCount }}</span>
          <span class="summary-label">Broken</span>
        </button>
        <button class="summary-item summary-noalt" :class="{ 'summary-active': filterAction === 'no_alternatives' }"
                @click="filterAction = 'no_alternatives'; filterItems()">
          <span class="summary-value">{{ noAltCount }}</span>
          <span class="summary-label">No Alts</span>
        </button>
      </div>

      <div class="legend">
        <span class="legend-item"><span class="badge badge-change">Change</span> A better poster was found</span>
        <span class="legend-item"><span class="badge badge-uploaded">Uploaded</span> Poster uploaded by Kometa or manually</span>
        <span class="legend-item"><span class="badge badge-broken">Broken</span> Poster missing or corrupt (often from stale Kometa uploads)</span>
        <span class="legend-item"><span class="badge badge-locked">Locked</span> Poster field is locked in Plex</span>
        <span class="legend-item"><span class="badge badge-skip">Skip</span> Current poster is already the best</span>
        <span class="legend-item"><span class="badge badge-no_alternatives">No Alts</span> No other posters available</span>
      </div>

      <div class="card-actions">
        <button class="btn btn-primary" @click="confirmApplyAll"
                :disabled="applying || unappliedChanges === 0">
          Apply All Changes
        </button>
        <button class="btn btn-outline" @click="confirmApplySelected"
                :disabled="applying || selectedItems.length === 0">
          Apply Selected ({{ selectedItems.length }})
        </button>
        <button class="btn btn-outline" @click="applyAll(true)"
                :disabled="applying || unappliedChanges === 0">
          Dry Run All
        </button>
        <button class="btn btn-outline" @click="selectAll">Select All</button>
        <button class="btn btn-outline" @click="deselectAll"
                :disabled="selectedItems.length === 0">
          Deselect All
        </button>
        <button class="btn btn-outline" @click="exportResults">Export JSON</button>
      </div>

      <!-- Apply Progress -->
      <div v-if="applying" class="apply-progress" style="margin-top: 16px">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px">
          <span class="text-muted">
            Applying changes... {{ applyProgress.processed }} / {{ applyProgress.total }}
          </span>
          <span class="text-muted">{{ applyProgress.pct }}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: applyProgress.pct + '%' }"></div>
        </div>
        <div style="display: flex; gap: 16px; margin-top: 6px">
          <span class="text-success text-xs">Applied: {{ applyProgress.applied }}</span>
          <span v-if="applyProgress.failed > 0" class="error-text text-xs">Failed: {{ applyProgress.failed }}</span>
        </div>
      </div>

    </div>

    <!-- Pagination Top -->
    <div v-if="filteredItems.length > 0" class="pagination-bar">
      <div class="pagination-info">
        <span class="text-muted text-xs">
          {{ (currentPage - 1) * perPage + 1 }}–{{ Math.min(currentPage * perPage, filteredItems.length) }}
          of {{ filteredItems.length }}
        </span>
        <select v-model.number="perPage" class="filter-select pagination-per-page" @change="currentPage = 1">
          <option :value="50">50 / page</option>
          <option :value="100">100 / page</option>
          <option :value="200">200 / page</option>
        </select>
      </div>
      <div class="pagination-controls">
        <button class="btn btn-outline btn-sm" :disabled="currentPage <= 1" @click="currentPage = 1">&laquo;</button>
        <button class="btn btn-outline btn-sm" :disabled="currentPage <= 1" @click="currentPage--">&lsaquo;</button>
        <span class="text-muted text-xs">Page {{ currentPage }} / {{ totalPages }}</span>
        <button class="btn btn-outline btn-sm" :disabled="currentPage >= totalPages" @click="currentPage++">&rsaquo;</button>
        <button class="btn btn-outline btn-sm" :disabled="currentPage >= totalPages" @click="currentPage = totalPages">&raquo;</button>
      </div>
    </div>

    <!-- Results Grid -->
    <div v-if="filteredItems.length > 0" class="results-grid">
      <div v-for="item in paginatedItems" :key="item.rating_key"
           class="result-card" :class="['action-' + item.action, { 'card-selected': isSelected(item.rating_key), 'card-selectable': item.action === 'change' }]"
           @click="item.action === 'change' && toggleSelect(item.rating_key)">
        <div class="result-header">
          <div class="result-title">
            <h4 :title="item.title + (item.year ? ' (' + item.year + ')' : '')">{{ item.title }}{{ item.year ? ' (' + item.year + ')' : '' }}</h4>
          </div>
          <div class="result-badges">
            <span class="badge" :class="'badge-' + item.action">{{ actionLabel(item.action) }}</span>
            <span v-if="item.is_uploaded" class="badge badge-uploaded">Uploaded</span>
            <span v-if="item.is_likely_broken" class="badge badge-broken" :title="item.broken_reason">Broken</span>
            <span v-if="item.is_locked" class="badge badge-locked">Locked</span>
          </div>
        </div>
        <div class="poster-compare">
          <div class="poster-slot">
            <p class="poster-label">Current</p>
            <img v-if="item.current_poster_url" :src="item.current_poster_url" alt="Current poster"
                 class="poster-thumb" loading="lazy" @error="($event.target.style.display = 'none')" />
            <div v-else class="poster-placeholder">No image</div>
            <div class="poster-details">
              <span v-if="item.current_score != null" class="poster-score">{{ item.current_score?.toFixed(1) }}</span>
              <span v-if="item.current_provider" class="poster-provider">{{ item.current_provider }}</span>
            </div>
          </div>
          <div v-if="item.best_candidate_url && item.action === 'change'" class="poster-arrow">&#8594;</div>
          <div v-if="item.best_candidate_url" class="poster-slot">
            <p class="poster-label">Recommended</p>
            <img :src="item.best_candidate_url" alt="Recommended poster"
                 class="poster-thumb" loading="lazy" @error="($event.target.style.display = 'none')" />
            <div class="poster-details">
              <span class="poster-score poster-score-better">{{ item.best_candidate_score?.toFixed(1) }}</span>
              <span v-if="item.best_candidate_provider" class="poster-provider">{{ item.best_candidate_provider }}</span>
            </div>
          </div>
        </div>
        <div class="result-footer">
          <span class="text-muted text-xs">{{ item.num_candidates }} candidate{{ item.num_candidates !== 1 ? 's' : '' }}</span>
          <span v-if="item.applied" class="text-success text-xs">Applied</span>
          <span v-if="item.error" class="error-text text-xs">{{ item.error }}</span>
          <button class="btn btn-outline btn-sm" @click.stop="openPicker(item)"
                  title="View all poster candidates" style="color: var(--accent); border-color: var(--accent);">
            Posters
          </button>
          <button class="btn btn-outline btn-sm" @click.stop="showPosterInfo(item.rating_key)"
                  title="View raw poster metadata">Info</button>
        </div>
      </div>
    </div>

    <!-- Pagination Bottom -->
    <div v-if="totalPages > 1" class="pagination-bar">
      <div class="pagination-info">
        <span class="text-muted text-xs">
          {{ (currentPage - 1) * perPage + 1 }}–{{ Math.min(currentPage * perPage, filteredItems.length) }}
          of {{ filteredItems.length }}
        </span>
      </div>
      <div class="pagination-controls">
        <button class="btn btn-outline btn-sm" :disabled="currentPage <= 1" @click="goToPage(1)">&laquo;</button>
        <button class="btn btn-outline btn-sm" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">&lsaquo;</button>
        <span class="text-muted text-xs">Page {{ currentPage }} / {{ totalPages }}</span>
        <button class="btn btn-outline btn-sm" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">&rsaquo;</button>
        <button class="btn btn-outline btn-sm" :disabled="currentPage >= totalPages" @click="goToPage(totalPages)">&raquo;</button>
      </div>
    </div>

    <p v-if="job && filteredItems.length === 0" class="text-muted">
      No items match the current filter.
    </p>

    <!-- Candidate Picker Modal -->
    <div v-if="pickerOpen" class="modal-overlay" @click.self="pickerOpen = false">
      <div class="modal picker-modal" @click.stop>
        <div class="modal-header">
          <div>
            <h3>{{ pickerItem?.title }}{{ pickerItem?.year ? ' (' + pickerItem.year + ')' : '' }}</h3>
            <p class="text-muted text-xs">{{ pickerItem?.all_candidates?.length || 0 }} poster candidates</p>
          </div>
          <button class="modal-close" @click="pickerOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="picker-grid">
            <div v-for="c in pickerItem?.all_candidates || []" :key="c.rating_key"
                 class="picker-card" :class="{ 'picker-selected': c.selected, 'picker-best': c.rating_key === pickerItem?.best_candidate_key }">
              <img :src="c.thumb_url" alt="Poster" class="picker-thumb" loading="lazy"
                   @error="($event.target.style.display = 'none')" />
              <div class="picker-info">
                <div class="picker-score">{{ c.score?.toFixed(1) }}</div>
                <span v-if="c.provider" class="poster-provider">{{ c.provider }}</span>
                <span v-if="c.selected" class="badge badge-change" style="font-size: 0.6rem">Current</span>
                <span v-if="c.rating_key === pickerItem?.best_candidate_key" class="badge badge-pending" style="font-size: 0.6rem">Best</span>
              </div>
              <div v-if="c.score_breakdown" class="picker-breakdown">
                <span v-for="(val, key) in c.score_breakdown" :key="key" class="text-muted text-xs">
                  {{ key }}: {{ typeof val === 'number' ? val.toFixed(1) : val }}
                </span>
              </div>
              <button v-if="!c.selected" class="btn btn-primary btn-sm picker-apply-btn"
                      :disabled="applyingCandidate === c.rating_key"
                      @click="applyPickedCandidate(c)">
                {{ applyingCandidate === c.rating_key ? 'Applying...' : 'Use This' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm Apply Modal -->
    <div v-if="confirmOpen" class="modal-overlay" @click.self="confirmOpen = false">
      <div class="modal" @click.stop style="max-width: 440px">
        <div class="modal-header">
          <h3>Confirm Apply</h3>
          <button class="modal-close" @click="confirmOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <p>{{ confirmMessage }}</p>
          <p class="text-muted text-xs" style="margin-top: 8px">
            This will replace posters on your Plex server. This action cannot be undone.
          </p>
          <div style="display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end">
            <button class="btn btn-outline btn-sm" @click="confirmOpen = false">Cancel</button>
            <button class="btn btn-primary btn-sm" @click="confirmProceed"
                    style="background: var(--error); border-color: var(--error);">
              Apply
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Poster Info Modal -->
    <div v-if="modalOpen" class="modal-overlay" @click.self="modalOpen = false" @keydown.escape="modalOpen = false">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>{{ modalTitle }}</h3>
          <button class="modal-close" @click="modalOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="modalLoading" class="text-muted">Loading...</div>
          <pre v-else class="modal-json">{{ modalJson }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api.js'
import { useToast } from '../composables/useToast.js'

const toast = useToast()

const route = useRoute()

// Re-load when the route query changes (e.g. navigating back from dashboard with a new job_id)
watch(
  () => route.query.job_id,
  (newId) => {
    if (newId) loadJob(newId)
  }
)

const job = ref(null)
const allItems = ref([])
const filteredItems = ref([])
const searchQuery = ref('')
const filterAction = ref('all')
const selectedItems = ref([])
const applying = ref(false)
const applyProgress = ref({ total: 0, processed: 0, pct: 0, applied: 0, failed: 0 })
let applyPollInterval = null

// Pagination
const currentPage = ref(1)
const perPage = ref(50)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredItems.value.length / perPage.value))
)

const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * perPage.value
  return filteredItems.value.slice(start, start + perPage.value)
})

const unappliedChanges = computed(() =>
  allItems.value.filter((i) => i.action === 'change' && !i.applied).length
)

const lockedCount = ref(0)
const uploadedCount = ref(0)
const brokenCount = ref(0)
const noAltCount = ref(0)

// Confirm dialog
const confirmOpen = ref(false)
const confirmMessage = ref('')
let confirmAction = null

// Candidate picker
const pickerOpen = ref(false)
const pickerItem = ref(null)
const applyingCandidate = ref(null)

// Modal
const modalOpen = ref(false)
const modalTitle = ref('')
const modalJson = ref('')
const modalLoading = ref(false)

onMounted(() => {
  loadInitial()
})

async function loadInitial() {
  const jobId = route.query.job_id
  if (jobId) {
    await loadJob(jobId)
  } else {
    await loadLatestJob()
  }
}

async function loadLatestJob() {
  try {
    const data = await api.getJobs()
    if (data.jobs && data.jobs.length > 0) {
      const sorted = [...data.jobs].reverse()
      const latest = sorted[0]
      if (latest.status === 'complete') {
        await loadJob(latest.job_id)
      }
    }
  } catch {}
}

onUnmounted(() => {
  if (applyPollInterval) clearInterval(applyPollInterval)
})

async function loadJob(jobId) {
  try {
    const data = await api.getScanStatus(jobId)
    job.value = data
    allItems.value = data.items || []
    lockedCount.value = allItems.value.filter((i) => i.is_locked).length
    uploadedCount.value = allItems.value.filter((i) => i.is_uploaded).length
    brokenCount.value = allItems.value.filter((i) => i.is_likely_broken).length
    noAltCount.value = allItems.value.filter((i) => i.action === 'no_alternatives').length
    filterItems()
  } catch (e) {
    console.error('Failed to load job:', e)
  }
}

function filterItems() {
  let items = allItems.value
  if (filterAction.value === 'locked') {
    items = items.filter((i) => i.is_locked)
  } else if (filterAction.value === 'uploaded') {
    items = items.filter((i) => i.is_uploaded)
  } else if (filterAction.value === 'broken') {
    items = items.filter((i) => i.is_likely_broken)
  } else if (filterAction.value !== 'all') {
    items = items.filter((i) => i.action === filterAction.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    items = items.filter((i) => i.title.toLowerCase().includes(q))
  }
  filteredItems.value = items
  currentPage.value = 1
}

function goToPage(page) {
  currentPage.value = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function isSelected(key) {
  return selectedItems.value.includes(key)
}

function toggleSelect(key) {
  if (isSelected(key)) {
    selectedItems.value = selectedItems.value.filter((k) => k !== key)
  } else {
    selectedItems.value.push(key)
  }
}

function selectAll() {
  selectedItems.value = filteredItems.value
    .filter((i) => i.action === 'change' && !i.applied)
    .map((i) => i.rating_key)
}

function deselectAll() {
  selectedItems.value = []
}

function confirmApplyAll() {
  confirmMessage.value = `Apply poster changes to ${unappliedChanges.value} items?`
  confirmAction = () => applyAll(false)
  confirmOpen.value = true
}

function confirmApplySelected() {
  confirmMessage.value = `Apply poster changes to ${selectedItems.value.length} selected items?`
  confirmAction = () => applySelected(false)
  confirmOpen.value = true
}

function confirmProceed() {
  confirmOpen.value = false
  if (confirmAction) confirmAction()
  confirmAction = null
}

async function applyAll(dryRun) {
  await _startApply({ dry_run: dryRun })
}

async function applySelected(dryRun) {
  await _startApply({ dry_run: dryRun, item_keys: selectedItems.value })
}

async function _startApply(body) {
  applying.value = true
  applyProgress.value = { total: 0, processed: 0, pct: 0, applied: 0, failed: 0 }
  try {
    const data = await api.startApply(job.value.job_id, body.dry_run, body.item_keys || null)
    if (data.error) {
      toast.error(data.error)
      applying.value = false
      return
    }
    _pollApply(data.apply_id, body.dry_run)
  } catch (e) {
    toast.error('Apply failed: ' + e.message)
    applying.value = false
  }
}

function _pollApply(applyId, dryRun) {
  if (applyPollInterval) clearInterval(applyPollInterval)
  applyPollInterval = setInterval(async () => {
    try {
      const data = await api.getApplyStatus(applyId)
      applyProgress.value = {
        total: data.total_items,
        processed: data.processed_items,
        pct: data.progress_pct,
        applied: data.applied_count,
        failed: data.failed_count,
      }
      if (data.status === 'complete' || data.status === 'failed') {
        clearInterval(applyPollInterval)
        applyPollInterval = null
        applying.value = false
        if (data.status === 'complete') {
          if (dryRun) {
            toast.info(`Dry run complete: ${data.applied_count} items would be changed`)
          } else {
            toast.success(`Applied ${data.applied_count} changes, ${data.failed_count} failed`)
            await loadJob(job.value.job_id)
          }
        } else {
          toast.error(data.error || 'Apply failed')
        }
      }
    } catch {
      clearInterval(applyPollInterval)
      applyPollInterval = null
      applying.value = false
      toast.error('Lost connection to apply job')
    }
  }, 500)
}

async function exportResults() {
  if (!job.value) return
  try {
    const data = await api.exportJob(job.value.job_id)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `posterpilot-scan-${job.value.job_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Export failed:', e)
  }
}

async function showPosterInfo(ratingKey) {
  modalOpen.value = true
  modalLoading.value = true
  modalTitle.value = 'Poster Info'
  modalJson.value = ''
  try {
    const data = await api.getItemPosters(ratingKey)
    modalTitle.value = (data.item?.title || 'Item') + ' — Poster Data'
    modalJson.value = JSON.stringify(data, null, 2)
  } catch (e) {
    modalJson.value = 'Error: ' + e.message
  }
  modalLoading.value = false
}

function openPicker(item) {
  pickerItem.value = {
    ...item,
    best_candidate_key: item.all_candidates?.find((c) =>
      item.best_candidate_score != null && c.score === item.best_candidate_score
    )?.rating_key || null,
  }
  applyingCandidate.value = null
  pickerOpen.value = true
}

async function applyPickedCandidate(candidate) {
  if (!job.value || !pickerItem.value) return
  applyingCandidate.value = candidate.rating_key
  try {
    const data = await api.applyCandidate(
      job.value.job_id,
      pickerItem.value.rating_key,
      candidate.rating_key
    )
    if (data.applied) {
      toast.success(`Poster applied for "${data.title}"`)
      pickerOpen.value = false
      await loadJob(job.value.job_id)
    } else if (data.error) {
      toast.error(data.error)
    }
  } catch (e) {
    toast.error('Failed to apply: ' + e.message)
  }
  applyingCandidate.value = null
}

function actionLabel(action) {
  const labels = {
    change: 'Change',
    skip: 'Skip',
    no_alternatives: 'No Alternatives',
    failed: 'Failed',
    locked: 'Locked',
  }
  return labels[action] || action
}
</script>
