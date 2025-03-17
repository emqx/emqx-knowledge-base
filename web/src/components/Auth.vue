<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const isAuthenticated = ref(false)
const router = useRouter()

onMounted(async () => {
  // Check for OAuth callback
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  
  if (code) {
    try {
      const response = await fetch('/auth/callback', {
        method: 'POST',
        body: JSON.stringify({ code })
      })
      const data = await response.json()
      
      if (data.token) {
        sessionStorage.setItem('github_token', data.token)
        isAuthenticated.value = true
        router.push('/')
      }
    } catch (error) {
      console.error('Authentication failed:', error)
    }
  }
})

const login = () => {
  const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID
  const redirectUri = `${window.location.origin}/auth/callback`
  window.location.href = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&scope=read:org`
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-gray-100">
    <div class="p-8 bg-white rounded-lg shadow-md">
      <h1 class="mb-6 text-2xl font-bold text-center">EMQX Knowledge Base</h1>
      <button
        v-if="!isAuthenticated"
        @click="login"
        class="flex items-center justify-center w-full px-4 py-2 space-x-2 text-white bg-gray-900 rounded hover:bg-gray-800"
      >
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
        </svg>
        <span>Sign in with GitHub</span>
      </button>
    </div>
  </div>
</template> 