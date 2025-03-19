import { createRouter, createWebHistory } from "vue-router";
import Assistant from "../views/Assistant.vue";
import Auth from "../components/Auth.vue";

const routes = [
  {
    path: "/",
    name: "Assistant",
    component: Assistant,
    meta: { requiresAuth: true },
  },
  {
    path: "/login",
    name: "Login",
    component: Auth,
  },
  {
    path: "/auth/callback",
    name: "AuthCallback",
    component: Auth,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// Navigation guard to check authentication
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth);
  const token = localStorage.getItem("auth_token");

  if (requiresAuth && !token) {
    // Redirect to login page if trying to access a protected route without being authenticated
    next({ name: "Login" });
  } else {
    next();
  }
});

export default router;
