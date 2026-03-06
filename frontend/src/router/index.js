import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue')
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/views/Agents.vue')
      },
      {
        path: 'mcp',
        name: 'MCP',
        component: () => import('@/views/MCP.vue')
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('@/views/Skills.vue')
      },
      {
        path: 'information-bases',
        name: 'InformationBases',
        component: () => import('@/views/InformationBases.vue')
      },
      {
        path: 'database',
        name: 'Database',
        component: () => import('@/views/Database.vue')
      },
      {
        path: 'documents',
        name: 'Documents',
        component: () => import('@/views/Documents.vue')
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/Chat.vue')
      },
      {
        path: 'ia-settings',
        name: 'IASettings',
        component: () => import('@/views/IASettings.vue')
      },
      {
        path: 'acompanhamento',
        name: 'Acompanhamento',
        component: () => import('@/views/Acompanhamento.vue')
      }
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
