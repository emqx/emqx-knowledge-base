<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Navigation -->
    <nav class="bg-white shadow">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex">
            <div class="flex-shrink-0 flex items-center">
              <h1 class="text-xl font-bold text-indigo-600">EMQX Knowledge Base</h1>
            </div>
            <div class="hidden sm:ml-6 sm:flex sm:space-x-8">
              <router-link to="/" class="border-transparent text-gray-900 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium">
                Home
              </router-link>
              <router-link to="/logs" class="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium">
                Log Analysis
              </router-link>
            </div>
          </div>
          <div class="hidden sm:ml-6 sm:flex sm:items-center">
            <!-- Show user info if logged in, otherwise show login button -->
            <div v-if="user" class="flex items-center">
              <img v-if="user.avatar_url" class="h-8 w-8 rounded-full" :src="user.avatar_url" alt="User avatar" />
              <span class="ml-2 text-sm font-medium text-gray-700">{{ user.name || user.username }}</span>
              <button @click="logout" class="ml-3 px-3 py-1 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors">
                Logout
              </button>
            </div>
            <router-link v-else to="/login" class="ml-3 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
              Login
            </router-link>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main content -->
    <div class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <router-view v-if="authInitialized" />
      <div v-else class="flex justify-center items-center h-64">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      user: null,
      authInitialized: false
    }
  },
  created() {
    // Listen for storage events to detect login/logout in other tabs
    window.addEventListener('storage', this.handleStorageChange);
  },
  mounted() {
    this.checkAuth();
  },
  beforeUnmount() {
    window.removeEventListener('storage', this.handleStorageChange);
  },
  provide() {
    return {
      logout: this.logout
    }
  },
  methods: {
    async checkAuth() {
      const token = localStorage.getItem('auth_token');
      
      if (!token) {
        this.user = null;
        this.authInitialized = true;
        return;
      }
      
      try {
        // Parse JWT token directly without making API call
        // JWT format is header.payload.signature
        const parts = token.split('.');
        if (parts.length !== 3) {
          throw new Error('Invalid token format');
        }
        
        // Decode the base64-encoded payload
        const payload = JSON.parse(atob(parts[1]));
        
        // Check if token is expired
        const currentTime = Math.floor(Date.now() / 1000);
        if (payload.exp && payload.exp < currentTime) {
          console.error('Token expired');
          this.logout();
          return;
        }
        
        // Extract user info from token payload
        this.user = {
          username: payload.login,
          name: payload.name,
          avatar_url: payload.avatar_url,
          html_url: `https://github.com/${payload.login}`
        };
      } catch (error) {
        console.error('Error parsing JWT token:', error);
        this.logout();
      } finally {
        this.authInitialized = true;
      }
    },
    handleStorageChange(event) {
      // Check if auth_token has changed in another tab
      if (event.key === 'auth_token') {
        this.checkAuth();
      }
    },
    logout() {
      localStorage.removeItem('auth_token');
      this.user = null;
      // Redirect to login page
      this.$router.push('/login');
    }
  }
}
</script>

<style>
/* Your global styles */
</style> 