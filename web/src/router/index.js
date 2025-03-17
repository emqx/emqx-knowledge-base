import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import LogAnalysis from '../views/LogAnalysis.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/logs',
    name: 'LogAnalysis',
    component: LogAnalysis
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router 