<template>
  <div class="bg-white shadow sm:rounded-lg">
    <div class="px-4 py-5 sm:p-6">
      <h2 class="text-lg font-medium text-gray-900">EMQX Log Analyzer</h2>
      <div class="mt-5">
        <textarea
          v-model="logText"
          rows="8"
          class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm p-3 font-mono"
          placeholder="Paste your EMQX log here..."
        ></textarea>

        <div class="mt-3 flex items-center space-x-4">
          <button
            @click="analyzeLog"
            :disabled="isLoading"
            class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <span v-if="isLoading">Processing...</span>
            <span v-else>Analyze Log</span>
          </button>

          <div class="relative">
            <input
              type="file"
              ref="fileInput"
              @change="handleFileUpload"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <button
              type="button"
              class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
              Upload Log File
            </button>
          </div>
        </div>
      </div>

      <div v-if="error" class="mt-4 text-sm text-red-600">
        {{ error }}
      </div>

      <div v-if="analysis" class="mt-6">
        <h3 class="text-lg font-medium text-gray-900">Analysis</h3>
        <div class="mt-2 prose prose-sm max-w-none p-3 bg-gray-50 rounded-md">
          <div v-html="renderedAnalysis"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const logText = ref('')
const analysis = ref('')
const isLoading = ref(false)
const error = ref('')
const fileInput = ref(null)

// Compute the rendered markdown
const renderedAnalysis = computed(() => {
  if (!analysis.value) return ''
  // Parse markdown and sanitize HTML
  const html = marked.parse(analysis.value)
  return DOMPurify.sanitize(html)
})

const handleFileUpload = (event) => {
  const file = event.target.files[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      logText.value = e.target.result
    }
    reader.readAsText(file)
  }
  // Reset the file input so the same file can be selected again
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const analyzeLog = async () => {
  if (!logText.value.trim()) {
    error.value = 'Please enter log text or upload a log file'
    return
  }

  error.value = ''
  isLoading.value = true

  try {
    // Create FormData if we have a file
    const formData = new FormData()
    formData.append('log_text', logText.value)

    const response = await fetch('/api/analyze-log', {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      throw new Error(`Error: ${response.status}`)
    }

    const data = await response.json()
    analysis.value = data.answer
  } catch (err) {
    console.error('Error analyzing log:', err)
    error.value = 'Failed to analyze the log. Please try again later.'
  } finally {
    isLoading.value = false
  }
}
</script>
