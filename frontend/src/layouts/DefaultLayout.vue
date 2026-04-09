<template>
  <v-app class="app-layout">
    <!-- Sidebar Navigation -->
    <v-navigation-drawer
      v-model="drawer"
      :rail="rail"
      :permanent="!mobile"
      :temporary="mobile"
      class="sidebar-drawer"
      elevation="0"
      width="270"
      rail-width="72"
    >
      <!-- Logo Area -->
      <div class="d-flex align-center pa-5 mb-1 logo-area">
        <div class="logo-icon-wrapper mr-3">
          <v-icon color="white" size="26">mdi-graphql</v-icon>
        </div>
        <div v-show="!rail" class="logo-text d-flex flex-column justify-center mt-1">
          <h1 class="text-subtitle-1 font-weight-bold text-white mb-0" style="letter-spacing: 0.01em; line-height: 1;">Basile IA</h1>
          <span class="text-caption font-weight-medium" style="color: rgba(255,255,255,0.5); font-size: 11px !important;">Orchestrator</span>
        </div>
        <v-spacer />
        <v-btn
          v-show="!rail && !mobile"
          icon
          variant="text"
          size="x-small"
          color="white"
          class="sidebar-toggle-btn"
          @click="rail = !rail"
        >
          <v-icon size="18" style="opacity: 0.5">mdi-chevron-left</v-icon>
        </v-btn>
      </div>

      <!-- Gradient Accent Line -->
      <div class="sidebar-accent-line"></div>

      <!-- Menu Section -->
      <div class="px-3 mt-4">
        <v-list density="comfortable" nav class="sidebar-menu">
          <v-list-item
            v-for="(item, i) in menuItems"
            :key="i"
            :value="item"
            :to="item.to"
            :prepend-icon="item.icon"
            rounded="lg"
            class="mb-1 menu-item"
            active-class="active-menu-item"
          >
            <v-list-item-title class="text-body-2 font-weight-medium">{{ item.title }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </div>

      <!-- Bottom Footer -->
      <template v-slot:append>
        <div class="sidebar-footer" v-show="!rail">
          <div class="d-flex align-center justify-center mb-3">
            <span class="version-badge">v0.0.12</span>
          </div>
          <div class="d-flex align-center pa-3">
            <v-avatar size="32" class="mr-3 border-avatar">
              <v-img src="https://ui-avatars.com/api/?name=Fernando&background=2C303E&color=fff&bold=true"></v-img>
            </v-avatar>
            <span class="text-body-2 text-white font-weight-medium" style="opacity: 0.8">Fernando</span>
            <v-spacer />
            <v-btn icon variant="text" size="x-small" color="white" style="opacity: 0.4">
              <v-icon size="18">mdi-cog-outline</v-icon>
            </v-btn>
          </div>
        </div>

        <!-- Expand button when rail mode -->
        <div v-show="rail" class="d-flex justify-center pa-3">
          <v-btn
            icon
            variant="text"
            size="small"
            color="white"
            class="sidebar-toggle-btn"
            @click="rail = false"
          >
            <v-icon size="18" style="opacity: 0.5">mdi-chevron-right</v-icon>
          </v-btn>
        </div>
      </template>
    </v-navigation-drawer>

    <!-- Main Content -->
    <v-main class="app-main">
      <div class="main-content-wrapper">
        <!-- Top Header Bar -->
        <header class="dashboard-header d-flex align-center justify-space-between px-8 py-5">
          <!-- Mobile menu button -->
          <v-btn
            v-if="mobile"
            icon
            variant="text"
            color="white"
            class="mr-3 d-md-none"
            @click="drawer = !drawer"
          >
            <v-icon>mdi-menu</v-icon>
          </v-btn>

          <div class="d-flex align-center">
            <h1 class="text-h6 font-weight-bold text-white mb-0" style="letter-spacing: -0.01em;">
              {{ currentPageTitle }}
            </h1>
          </div>

          <div class="header-tools d-flex align-center ga-3">
            <v-text-field
              prepend-inner-icon="mdi-magnify"
              placeholder="Buscar..."
              variant="solo-filled"
              density="compact"
              hide-details
              flat
              rounded="pill"
              class="glass-search d-none d-md-flex"
              min-width="220"
            ></v-text-field>

            <div class="d-flex align-center ga-1">
              <v-btn icon variant="text" size="small" color="white" class="opacity-60 icon-btn-hover">
                <v-icon size="20">mdi-bell-outline</v-icon>
              </v-btn>

              <v-menu offset-y transition="slide-y-transition">
                <template v-slot:activator="{ props }">
                  <v-btn v-bind="props" variant="text" height="36" class="user-btn px-2 d-flex align-center ml-1">
                    <v-avatar size="26" class="mr-2 border-avatar">
                       <v-img src="https://ui-avatars.com/api/?name=F&background=2C303E&color=fff"></v-img>
                    </v-avatar>
                    <span class="text-caption font-weight-medium text-white d-none d-sm-block text-capitalize">Fernando</span>
                    <v-icon size="14" class="ml-1 opacity-50" color="white">mdi-chevron-down</v-icon>
                  </v-btn>
                </template>
                <v-list bg-color="#111625" class="border-thin" rounded="lg">
                  <v-list-item prepend-icon="mdi-white-balance-sunny" @click="toggleTheme" title="Alternar Tema" density="compact"></v-list-item>
                  <v-list-item prepend-icon="mdi-logout" title="Sair" color="error" density="compact"></v-list-item>
                </v-list>
              </v-menu>
            </div>
          </div>
        </header>

        <!-- Router View -->
        <div class="dashboard-content-wrapper px-8 pb-8 flex-grow-1">
          <router-view v-slot="{ Component }">
            <transition name="page-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </div>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme, useDisplay } from 'vuetify'

const route = useRoute()
const theme = useTheme()
const { mobile } = useDisplay()
const drawer = ref(true)
const rail = ref(false)

const menuItems = [
  { title: 'Dashboard', icon: 'mdi-view-dashboard-outline', to: '/' },
  { title: 'Workflows', icon: 'mdi-sitemap-outline', to: '/workflows' },
  { title: 'Acompanhamento', icon: 'mdi-chart-timeline-variant', to: '/acompanhamento' },
  { title: 'Chat IA', icon: 'mdi-chat-processing-outline', to: '/chat' },
  { title: 'Meus Agentes', icon: 'mdi-robot-outline', to: '/agents' },
  { title: 'Disparador', icon: 'mdi-rocket-launch-outline', to: '/disparador' },
  { title: 'Conhecimento', icon: 'mdi-book-open-page-variant-outline', to: '/documents' },
  { title: 'Integraes MCP', icon: 'mdi-connection', to: '/mcp' },
  { title: 'Criador de Skills', icon: 'mdi-star-shooting-outline', to: '/skills' },
  { title: 'Bases de Informaes', icon: 'mdi-database-search', to: '/information-bases' },
  { title: 'Base VFS (RAG 3.0)', icon: 'mdi-file-document-multiple-outline', to: '/vfs-knowledge' },
  { title: 'Gerenciar Memrias', icon: 'mdi-memory', to: '/memory' },
  { title: 'Banco de Dados', icon: 'mdi-database-outline', to: '/database' },
  { title: 'Configuraes de IA', icon: 'mdi-cog-box', to: '/ia-settings' },
  { title: 'Backup & Restore', icon: 'mdi-database-export-outline', to: '/backup-restore' }
]

const pageTitleMap = {
  '/': 'Ol, Fernando ',
  '/workflows': 'Workflows Visuais',
  '/acompanhamento': 'Acompanhamento',
  '/chat': 'Chat IA',
  '/agents': 'Meus Agentes',
  '/disparador': 'Disparador',
  '/documents': 'Base de Conhecimento',
  '/mcp': 'Integraes MCP',
  '/skills': 'Criador de Skills',
  '/information-bases': 'Bases de Informaes',
  '/vfs-knowledge': 'Base VFS (RAG 3.0)',
  '/memory': 'Gerenciar Memrias',
  '/database': 'Banco de Dados',
  '/ia-settings': 'Configuraes de IA',
  '/backup-restore': 'Backup & Restore'
}

const currentPageTitle = computed(() => pageTitleMap[route.path] || 'Basile IA')

const toggleTheme = () => {
  theme.global.name.value = theme.global.current.value.dark ? 'basileTheme' : 'basileDarkTheme'
}
</script>

<style scoped lang="scss">
.app-layout {
  font-family: 'Inter', sans-serif;
  background: #02040D !important;
}

/* ── Sidebar ── */
.sidebar-drawer {
  background: linear-gradient(180deg, rgba(10, 13, 22, 0.97) 0%, rgba(7, 10, 19, 0.99) 100%) !important;
  border-right: 1px solid rgba(255, 255, 255, 0.04) !important;
  z-index: 100;
}

.logo-icon-wrapper {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #7C3AED 0%, #9D4EDD 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(124, 58, 237, 0.35);
}

.logo-text h1 {
  background: linear-gradient(to right, #ffffff, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar-accent-line {
  height: 1px;
  margin: 0 20px;
  background: linear-gradient(90deg, transparent, rgba(157, 78, 221, 0.4), rgba(0, 242, 254, 0.2), transparent);
}

.sidebar-menu {
  background: transparent !important;
  
  .menu-item {
    color: rgba(255, 255, 255, 0.45) !important;
    transition: all 0.25s ease;
    margin-bottom: 2px;
    padding-left: 18px;
    height: 44px;
    
    &:hover {
      color: rgba(255, 255, 255, 0.85) !important;
      background: rgba(255, 255, 255, 0.03) !important;
    }
    
    :deep(.v-list-item__prepend .v-icon) {
      opacity: 0.7;
      margin-right: 14px;
      font-size: 20px;
    }
  }
}

.active-menu-item {
  background: linear-gradient(90deg, rgba(124, 58, 237, 0.7) 0%, rgba(124, 58, 237, 0) 100%) !important;
  color: #FFFFFF !important;
  border-left: 3px solid #9D4EDD;
  border-radius: 0 10px 10px 0 !important;
  margin-left: -12px;
  padding-left: 27px !important;
  
  :deep(.v-list-item__prepend .v-icon) {
    color: #FFFFFF !important;
    opacity: 1 !important;
    filter: drop-shadow(0 0 6px rgba(255,255,255,0.4));
  }
}

.sidebar-toggle-btn {
  &:hover {
    background: rgba(255, 255, 255, 0.06) !important;
  }
}

.sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  padding-top: 12px;
}

/* ── Main Content ── */
.app-main {
  background: transparent !important;
}

.main-content-wrapper {
  max-width: 1440px;
  margin: 0 auto;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.dashboard-header {
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(2, 4, 13, 0.6);
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

/* Search */
.glass-search {
  :deep(.v-field) {
    border-radius: 28px !important;
    background: rgba(20, 24, 40, 0.7) !important;
    border: 1px solid rgba(255, 255, 255, 0.04);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.15) !important;
    color: rgba(255,255,255,0.7);
    font-size: 13px;
    transition: all 0.3s ease;
    
    &:hover, &.v-field--focused {
      background: rgba(30, 35, 55, 0.85) !important;
      border-color: rgba(157, 78, 221, 0.35);
      box-shadow: 0 0 12px rgba(157, 78, 221, 0.15), inset 0 2px 4px rgba(0,0,0,0.15) !important;
    }

    .v-field__prepend-inner {
      opacity: 0.4;
    }
  }
}

.opacity-60 { opacity: 0.6; }
.opacity-50 { opacity: 0.5; }

.icon-btn-hover {
  transition: all 0.2s ease;
  &:hover {
    opacity: 1 !important;
    background: rgba(255,255,255,0.05);
  }
}

.border-avatar {
  border: 1px solid rgba(255,255,255,0.08);
}

.user-btn {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.04);
  background: rgba(20, 24, 40, 0.4);
  transition: all 0.2s ease;
  
  &:hover {
    background: rgba(30, 35, 55, 0.7);
    border-color: rgba(255,255,255,0.08);
  }
}

/* ── Page Transition ── */
.page-fade-enter-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.page-fade-leave-active {
  transition: opacity 0.2s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-fade-leave-to {
  opacity: 0;
}
</style>
