import { createRouter, createWebHashHistory } from 'vue-router'

import DashboardView from './views/DashboardView.vue'
import ScanResultsView from './views/ScanResultsView.vue'
import SettingsView from './views/SettingsView.vue'
import LogsView from './views/LogsView.vue'

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/scan', name: 'scan', component: ScanResultsView },
  { path: '/settings', name: 'settings', component: SettingsView },
  { path: '/logs', name: 'logs', component: LogsView },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
