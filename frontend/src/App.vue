<template>
  <AppSidebar />
  <main class="content">
    <router-view />
  </main>
  <ToastContainer />
</template>

<script setup>
import { onMounted } from 'vue'
import AppSidebar from './components/AppSidebar.vue'
import ToastContainer from './components/ToastContainer.vue'
import { useConnection } from './composables/useConnection.js'

const { checkStatus } = useConnection()

onMounted(() => {
  checkStatus()
})
</script>
