import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import LogAnalysis from '../views/LogAnalysis.vue'
import Auth from '../components/Auth.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { requiresAuth: true }
  },
  {
    path: '/logs',
    name: 'LogAnalysis',
    component: LogAnalysis,
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: Auth
  },
  {
    path: '/auth/callback',
    name: 'AuthCallback',
    component: Auth
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard to check authentication
router.beforeEach((to, from, next) => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const token = localStorage.getItem('auth_token')
  
  if (requiresAuth && !token) {
    // Redirect to login page if trying to access a protected route without being authenticated
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router 