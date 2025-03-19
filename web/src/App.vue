<template>
  <div class="min-h-screen bg-gray-50">
    <div class="max-w-7xl mx-auto py-4 sm:px-6 lg:px-8">
      <router-view v-if="authInitialized" />
      <div v-else class="flex justify-center items-center h-64">
        <div
          class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"
        ></div>
      </div>
    </div>
  </div>
</template>

<script>
import {
  ref,
  computed,
  onBeforeUnmount,
  onMounted,
  watch,
  nextTick,
  provide,
} from "vue";

export default {
  name: "App",
  setup() {
    const user = ref(null);
    const authInitialized = ref(false);

    // Provide user and logout to child components
    provide("user", user);

    const logout = () => {
      localStorage.removeItem("auth_token");
      user.value = null;
      // Use router to navigate
      window.location.href = "/login";
    };

    provide("logout", logout);

    const checkAuth = async () => {
      const token = localStorage.getItem("auth_token");

      if (!token) {
        user.value = null;
        authInitialized.value = true;
        return;
      }

      try {
        // Parse JWT token directly without making API call
        const parts = token.split(".");
        if (parts.length !== 3) {
          throw new Error("Invalid token format");
        }

        // Decode the base64-encoded payload
        const payload = JSON.parse(atob(parts[1]));

        // Check if token is expired
        const currentTime = Math.floor(Date.now() / 1000);
        if (payload.exp && payload.exp < currentTime) {
          console.error("Token expired");
          logout();
          return;
        }

        // Extract user info from token payload
        user.value = {
          username: payload.login,
          name: payload.name,
          avatar_url: payload.avatar_url,
          html_url: `https://github.com/${payload.login}`,
        };
      } catch (error) {
        console.error("Error parsing JWT token:", error);
        logout();
      } finally {
        authInitialized.value = true;
      }
    };

    const handleStorageChange = (event) => {
      // Check if auth_token has changed in another tab
      if (event.key === "auth_token") {
        checkAuth();
      }
    };

    // Lifecycle hooks
    onMounted(() => {
      checkAuth();
      window.addEventListener("storage", handleStorageChange);
    });

    onBeforeUnmount(() => {
      window.removeEventListener("storage", handleStorageChange);
    });

    return {
      user,
      authInitialized,
      logout,
      checkAuth,
    };
  },
};
</script>

<style>
/* Your global styles */
</style>
