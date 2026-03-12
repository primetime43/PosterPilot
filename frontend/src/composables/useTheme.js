import { ref } from 'vue'

const theme = ref(localStorage.getItem('posterpilot-theme') || 'dark')

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value)
}

function toggle() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('posterpilot-theme', theme.value)
  applyTheme()
}

// Apply on load
applyTheme()

export function useTheme() {
  return { theme, toggle }
}
