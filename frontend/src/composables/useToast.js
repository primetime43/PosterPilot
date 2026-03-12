import { reactive, readonly } from 'vue'

const toasts = reactive([])
let nextId = 0

function show(message, type = 'info', duration = 4000) {
  const id = nextId++
  toasts.push({ id, message, type, fading: false })
  setTimeout(() => {
    const t = toasts.find((t) => t.id === id)
    if (t) t.fading = true
    setTimeout(() => {
      const idx = toasts.findIndex((t) => t.id === id)
      if (idx !== -1) toasts.splice(idx, 1)
    }, 300)
  }, duration)
}

function dismiss(id) {
  const t = toasts.find((t) => t.id === id)
  if (t) t.fading = true
  setTimeout(() => {
    const idx = toasts.findIndex((t) => t.id === id)
    if (idx !== -1) toasts.splice(idx, 1)
  }, 300)
}

export function useToast() {
  return {
    toasts: readonly(toasts),
    success: (msg, dur) => show(msg, 'success', dur),
    error: (msg, dur) => show(msg, 'error', dur ?? 6000),
    warning: (msg, dur) => show(msg, 'warning', dur),
    info: (msg, dur) => show(msg, 'info', dur),
    dismiss,
  }
}
