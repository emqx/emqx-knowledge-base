<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";

const isAuthenticated = ref(false);
const isLoading = ref(false);
const error = ref("");
const router = useRouter();

onMounted(async () => {
  // Check if we're already authenticated
  const token = localStorage.getItem("auth_token");
  if (token) {
    // Already logged in, redirect to home
    isAuthenticated.value = true;
    router.push("/");
    return;
  }

  // Check for OAuth callback
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");

  if (code) {
    isLoading.value = true;
    try {
      // The callback is now fully handled by the Lambda@Edge function
      // We just wait for the JWT token to be set in localStorage by the callback page
      // Display loading status until redirected
      error.value = "";
    } catch (e) {
      error.value = "Authentication failed. Please try again.";
      isLoading.value = false;
      console.error("Authentication failed:", e);
    }
  }
});

const login = async () => {
  try {
    // Fetch the client ID from the server instead of environment variables
    const configResponse = await fetch("/auth/config");
    const config = await configResponse.json();
    const clientId = config.clientId;

    // Redirect to GitHub OAuth
    const redirectUri = `${window.location.origin}/auth/callback`;
    window.location.href = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&scope=read:org`;
  } catch (e) {
    error.value = "Failed to start authentication. Please try again.";
    console.error("Login error:", e);
  }
};
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-gray-100">
    <div class="p-8 bg-white rounded-lg shadow-md max-w-md w-full">
      <h1 class="mb-6 text-2xl font-bold text-center text-indigo-600">
        EMQX Knowledge Base
      </h1>

      <div v-if="isLoading" class="text-center my-6">
        <div
          class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"
        ></div>
        <p class="mt-4 text-gray-600">Authenticating with GitHub...</p>
      </div>

      <div v-else-if="!isAuthenticated">
        <p class="mb-6 text-center text-gray-600">
          Please sign in with GitHub to access the knowledge base.
        </p>

        <button
          @click="login"
          class="flex items-center justify-center w-full px-4 py-3 space-x-2 text-white bg-gray-900 rounded-md hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-800 transition-colors"
        >
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path
              d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"
            />
          </svg>
          <span>Sign in with GitHub</span>
        </button>

        <div
          v-if="error"
          class="mt-4 p-3 text-sm text-red-600 bg-red-50 rounded-md"
        >
          {{ error }}
        </div>

        <div class="mt-6 text-xs text-gray-500">
          <p>
            You need to be a member of the specified GitHub organization to
            access this application.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
