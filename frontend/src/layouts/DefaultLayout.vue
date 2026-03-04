<template>
  <v-app class="app-layout">
    <!-- Sidebar Navigation -->
    <v-navigation-drawer
      v-model="drawer"
      :rail="rail"
      permanent
      class="sidebar-drawer"
      elevation="0"
      width="280"
      rail-width="72"
    >
      <!-- Logo Area -->
      <div class="d-flex align-center pa-5 mb-2 logo-area">
        <div class="logo-icon-wrapper mr-3">
          <v-icon color="white" size="28" style="filter: drop-shadow(0 0 10px rgba(157,78,221,0.8));">mdi-graphql</v-icon>
        </div>
        <div v-show="!rail" class="logo-text d-flex flex-column justify-center mt-1">
          <h1 class="text-subtitle-1 font-weight-bold text-white mb-0" style="letter-spacing: 0.01em; line-height: 1;">Basile IA</h1>
          <span class="text-caption font-weight-medium" style="color: rgba(255,255,255,0.7); font-size: 11px !important;">Orchestrator</span>
        </div>
      </div>

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
            class="mb-2 menu-item"
            active-class="active-menu-item"
          >
            <v-list-item-title class="text-body-2 font-weight-medium">{{ item.title }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </div>

      <!-- Bottom Settings / User -->
      <template v-slot:append>
        <div class="pa-4 d-flex align-center sidebar-footer-user" v-show="!rail">
          <v-btn icon variant="text" size="small" color="white" class="mr-2">
            <v-icon size="20" style="opacity: 0.6">mdi-cog-outline</v-icon>
          </v-btn>
          <v-avatar size="32" class="mr-3">
            <v-img src="https://ui-avatars.com/api/?name=Fernando&background=2C303E&color=fff&bold=true"></v-img>
          </v-avatar>
          <span class="text-body-2 text-white font-weight-medium">Fernando</span>
        </div>
      </template>
    </v-navigation-drawer>

    <!-- Main Content Background + Glass Pane Wrap -->
    <v-main class="app-main d-flex align-center justify-center">
      <!-- The inner glass pane matching the mock -->
      <div class="glass-container w-100 h-100 d-flex flex-column relative">
        <!-- Top Custom Header Inside the Pane -->
        <header class="dashboard-header d-flex align-center justify-space-between px-8 py-6">
          <h1 class="text-h5 font-weight-bold text-white mb-0" style="letter-spacing: -0.02em;">
            Olá, Fernando 👋
          </h1>
          <div class="header-tools d-flex align-center ga-4">
            <v-text-field
              prepend-inner-icon="mdi-magnify"
              placeholder="Buscar..."
              variant="solo-filled"
              density="compact"
              hide-details
              flat
              rounded="pill"
              class="glass-search"
              min-width="260"
            ></v-text-field>

            <div class="d-flex align-center ga-2 ml-4">
              <v-btn icon variant="text" size="small" color="white" class="opacity-70 icon-btn-hover">
                <v-icon size="22">mdi-bell-outline</v-icon>
              </v-btn>
              <v-btn icon variant="text" size="small" color="white" class="opacity-70 icon-btn-hover">
                <v-icon size="22">mdi-help-circle-outline</v-icon>
              </v-btn>
              <v-menu offset-y transition="slide-y-transition" class="ml-2">
                <template v-slot:activator="{ props }">
                  <v-btn v-bind="props" variant="text" height="40" class="user-btn px-2 d-flex align-center">
                    <v-avatar size="28" class="mr-2 border-avatar">
                       <v-img src="https://ui-avatars.com/api/?name=F&background=2C303E&color=fff"></v-img>
                    </v-avatar>
                    <span class="text-caption font-weight-medium text-white d-none d-sm-block text-capitalize">Fernando</span>
                    <v-icon size="16" class="ml-1 opacity-70" color="white">mdi-chevron-down</v-icon>
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

        <!-- Router View injects Dashboard -->
        <div class="dashboard-content-wrapper px-8 pb-8 flex-grow-1">
          <router-view v-slot="{ Component }">
            <transition name="fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </div>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'

const route = useRoute()
const theme = useTheme()
const drawer = ref(true)
const rail = ref(false)

const menuItems = [
  { title: 'Dashboard', icon: 'mdi-view-dashboard-outline', to: '/' },
  { title: 'Chat IA', icon: 'mdi-chat-processing-outline', to: '/chat' },
  { title: 'Meus Agentes', icon: 'mdi-robot-outline', to: '/agents' },
  { title: 'Conhecimento', icon: 'mdi-book-open-page-variant-outline', to: '/documents' },
  { title: 'Integrações MCP', icon: 'mdi-connection', to: '/mcp' },
  { title: 'Banco de Dados', icon: 'mdi-database-outline', to: '/database' },
  { title: 'Configurações de IA', icon: 'mdi-cog-box', to: '/ia-settings' }
]

const toggleTheme = () => {
  theme.global.name.value = theme.global.current.value.dark ? 'basileTheme' : 'basileDarkTheme'
}
</script>

<style scoped lang="scss">
.app-layout {
  font-family: 'Inter', sans-serif;
  background: #02040D !important; /* Deepest black background for the whole page */
}

/* ── Sidebar ── */
.sidebar-drawer {
  background: transparent !important;
  border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
  box-shadow: 10px 0 30px rgba(0,0,0,0.5);
  z-index: 100;
}

.logo-text h1 {
  background: -webkit-linear-gradient(to right, #ffffff, #a78bfa);
  background: linear-gradient(to right, #ffffff, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar-menu {
  background: transparent !important;
  
  .menu-item {
    color: rgba(255, 255, 255, 0.5) !important;
    transition: all 0.3s ease;
    margin-bottom: 6px;
    padding-left: 20px;
    
    &:hover {
      color: rgba(255, 255, 255, 0.9) !important;
      background: rgba(255, 255, 255, 0.03) !important;
    }
    
    :deep(.v-list-item__prepend .v-icon) {
      opacity: 0.8;
      margin-right: 14px;
      font-size: 20px;
    }
  }
}

.active-menu-item {
  background: linear-gradient(90deg, rgba(124, 58, 237, 0.8) 0%, rgba(124, 58, 237, 0) 100%) !important;
  color: #FFFFFF !important;
  border-left: 3px solid #9D4EDD;
  border-radius: 0 8px 8px 0 !important;
  margin-left: -12px;
  padding-left: 29px !important;
  
  :deep(.v-list-item__prepend .v-icon) {
    color: #FFFFFF !important;
    opacity: 1 !important;
    filter: drop-shadow(0 0 5px rgba(255,255,255,0.5));
  }
}

/* ── Glass Container ── */
.glass-container {
  max-width: 1400px;
  margin: 0 auto;
  border-radius: 20px;
  background: radial-gradient(circle at top left, rgba(26, 30, 48, 0.8) 0%, rgba(13, 16, 27, 0.9) 100%);
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow: 
    inset 1px 1px 1px rgba(255, 255, 255, 0.05),
    0 20px 50px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  position: relative;
}

/* App Header Search Area */
.glass-search {
  :deep(.v-field) {
    border-radius: 28px !important;
    background: rgba(20, 24, 40, 0.8) !important;
    border: 1px solid rgba(255, 255, 255, 0.05);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.2) !important;
    color: rgba(255,255,255,0.8);
    font-size: 13px;
    transition: all 0.3s ease;
    
    &:hover, &.v-field--focused {
      background: rgba(30, 35, 55, 0.9) !important;
      border-color: rgba(157, 78, 221, 0.4);
      box-shadow: 0 0 10px rgba(157, 78, 221, 0.2), inset 0 2px 4px rgba(0,0,0,0.2) !important;
    }

    .v-field__prepend-inner {
      opacity: 0.5;
    }
  }
}

.opacity-70 {
  opacity: 0.7;
}

.icon-btn-hover:hover {
  opacity: 1 !important;
  background: rgba(255,255,255,0.05);
}

.border-avatar {
  border: 1px solid rgba(255,255,255,0.1);
}

.user-btn {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(20, 24, 40, 0.5);
  
  &:hover {
    background: rgba(30, 35, 55, 0.8);
    border-color: rgba(255,255,255,0.1);
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
