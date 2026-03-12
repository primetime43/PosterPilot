<template>
  <div class="toast-container">
    <div v-for="t in toasts" :key="t.id"
         class="toast" :class="['toast-' + t.type, { 'toast-fading': t.fading }]"
         @click="dismiss(t.id)">
      {{ t.message }}
    </div>
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast.js'

const { toasts, dismiss } = useToast()
</script>
