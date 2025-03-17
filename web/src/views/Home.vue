<template>
  <div class="bg-white shadow sm:rounded-lg">
    <div class="px-4 py-5 sm:p-6">
      <h2 class="text-lg font-medium text-gray-900">Ask a Question</h2>
      <div class="mt-5">
        <textarea
          v-model="question"
          rows="4"
          class="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm p-3"
          placeholder="Type your question here..."
          @keydown="handleKeyDown"
        ></textarea>
        <div class="mt-1 text-xs text-gray-500">
          Press Enter to submit, Shift+Enter for a new line
        </div>
        
        <div class="mt-3 flex items-center space-x-4">
          <button
            @click="submitQuestion"
            :disabled="isLoading"
            class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <span v-if="isLoading">Processing...</span>
            <span v-else>Submit</span>
          </button>
          
          <div class="relative">
            <input
              type="file"
              ref="fileInput"
              @change="handleFileUpload"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              multiple
            />
            <button
              type="button"
              class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
              Attach Files
            </button>
          </div>
        </div>
        
        <!-- File attachments list -->
        <div v-if="selectedFiles.length > 0" class="mt-3">
          <h4 class="text-sm font-medium text-gray-700">Selected Files:</h4>
          <ul class="mt-2 space-y-2">
            <li v-for="(file, index) in selectedFiles" :key="index" class="flex items-center justify-between text-sm text-gray-600 bg-gray-50 p-2 rounded">
              <div class="flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>{{ file.name }} ({{ formatFileSize(file.size) }})</span>
              </div>
              <button @click="removeFile(index)" class="text-red-500 hover:text-red-700">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </li>
          </ul>
        </div>
      </div>
      
      <div v-if="error" class="mt-4 text-sm text-red-600">
        {{ error }}
      </div>
      
      <div v-if="answer" class="mt-6">
        <h3 class="text-lg font-medium text-gray-900">Answer</h3>
        <div class="mt-2 prose prose-sm max-w-none p-3 bg-gray-50 rounded-md">
          <div v-html="renderedAnswer"></div>
        </div>
        
        <div v-if="sources.length > 0" class="mt-4">
          <h4 class="text-sm font-medium text-gray-700">Sources:</h4>
          <ul class="mt-2 text-xs text-gray-500 list-disc pl-5">
            <li v-for="(source, index) in sources" :key="index">
              {{ source.content_snippet }}
            </li>
          </ul>
        </div>
        
        <div v-if="fileReferences.length > 0" class="mt-4">
          <h4 class="text-sm font-medium text-gray-700">File References:</h4>
          <ul class="mt-2 text-xs text-gray-500 list-disc pl-5">
            <li v-for="(file, index) in fileReferences" :key="index">
              {{ file.file_name }} ({{ file.file_type }})
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const question = ref('')
const answer = ref('')
const sources = ref([])
const fileReferences = ref([])
const isLoading = ref(false)
const error = ref('')
const fileInput = ref(null)
const selectedFiles = ref([])

// Compute the rendered markdown
const renderedAnswer = computed(() => {
  if (!answer.value) return ''
  // Parse markdown and sanitize HTML
  const html = marked.parse(answer.value)
  return DOMPurify.sanitize(html)
})

const handleKeyDown = (event) => {
  // If Enter is pressed without Shift, prevent default and submit
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitQuestion()
  }
  // If Shift+Enter, let the default behavior happen (new line)
}

const handleFileUpload = (event) => {
  const files = event.target.files
  if (files) {
    for (let i = 0; i < files.length; i++) {
      selectedFiles.value.push(files[i])
    }
  }
  // Reset the file input so the same file can be selected again
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const removeFile = (index) => {
  selectedFiles.value.splice(index, 1)
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const submitQuestion = async () => {
  if (!question.value.trim()) {
    error.value = 'Please enter a question'
    return
  }
  
  error.value = ''
  isLoading.value = true
  
  try {
    // Create a FormData object if there are files
    let requestData
    let requestOptions
    
    if (selectedFiles.value.length > 0) {
      const formData = new FormData()
      formData.append('question', question.value)
      
      selectedFiles.value.forEach((file, index) => {
        formData.append(`files`, file)
      })
      
      requestOptions = {
        method: 'POST',
        body: formData
      }
    } else {
      requestOptions = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: question.value }),
      }
    }
    
    const response = await fetch('/api/ask', requestOptions)
    
    if (!response.ok) {
      throw new Error(`Error: ${response.status}`)
    }
    
    const data = await response.json()
    answer.value = data.answer
    sources.value = data.sources || []
    fileReferences.value = data.file_sources || []
    
    // Clear selected files after successful submission
    selectedFiles.value = []
  } catch (err) {
    console.error('Error submitting question:', err)
    error.value = 'Failed to get an answer. Please try again later.'
  } finally {
    isLoading.value = false
  }
}
</script>

<style>
/* Add some basic styling for markdown elements */
.prose h1 {
  font-size: 1.5rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 1rem;
}

.prose h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 1.25rem;
  margin-bottom: 0.75rem;
}

.prose h3 {
  font-size: 1.125rem;
  font-weight: 600;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

.prose p {
  margin-bottom: 0.75rem;
}

.prose ul, .prose ol {
  margin-left: 1.5rem;
  margin-bottom: 0.75rem;
}

.prose ul {
  list-style-type: disc;
}

.prose ol {
  list-style-type: decimal;
}

.prose li {
  margin-bottom: 0.25rem;
}

.prose a {
  color: #4f46e5;
  text-decoration: underline;
}

.prose code {
  background-color: #f3f4f6;
  padding: 0.125rem 0.25rem;
  border-radius: 0.25rem;
  font-family: monospace;
}

.prose pre {
  background-color: #f3f4f6;
  padding: 0.75rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  margin-bottom: 0.75rem;
}

.prose blockquote {
  border-left: 4px solid #e5e7eb;
  padding-left: 1rem;
  font-style: italic;
  margin-bottom: 0.75rem;
}
</style> 