<script setup>
import { ref } from 'vue'

const query = ref('')
const results = ref([])
const isLoading = ref(false)

const search = async () => {
  if (!query.value.trim()) return
  
  isLoading.value = true
  try {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${sessionStorage.getItem('github_token')}`
      },
      body: JSON.stringify({ query: query.value })
    })
    results.value = await response.json()
  } catch (error) {
    console.error('Search failed:', error)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto p-4">
    <div class="mb-8">
      <input
        v-model="query"
        @keyup.enter="search"
        type="text"
        placeholder="Search the knowledge base..."
        class="w-full px-4 py-2 text-lg border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>

    <div v-if="isLoading" class="flex justify-center">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
    </div>

    <div v-else-if="results.length" class="space-y-6">
      <div
        v-for="result in results"
        :key="result.id"
        class="p-4 bg-white rounded-lg shadow"
      >
        <h3 class="text-lg font-semibold mb-2">{{ result.title }}</h3>
        <p class="text-gray-600">{{ result.content }}</p>
        <div class="mt-2 text-sm text-gray-500">
          Last updated: {{ new Date(result.updated_at).toLocaleDateString() }}
        </div>
      </div>
    </div>

    <div
      v-else-if="query && !isLoading"
      class="text-center text-gray-500 mt-8"
    >
      No results found
    </div>
  </div>
</template> 