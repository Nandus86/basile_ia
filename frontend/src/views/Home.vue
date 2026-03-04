<template>
  <div class="dashboard-container">
    <!-- Welcome Header -->
    <div class="d-flex flex-column flex-md-row align-md-center justify-space-between mb-8">
      <div>
        <h1 class="text-h4 font-weight-bold text-primary mb-1">
          Bem-vindo de volta, Fernando! 👋
        </h1>
        <p class="text-subtitle-1 text-medium-emphasis">
          Aqui está o que está acontecendo com seus agentes hoje.
        </p>
      </div>
      <div class="d-flex gap-3 mt-4 mt-md-0">
        <v-btn
          color="surface"
          variant="outlined"
          prepend-icon="mdi-download"
          class="text-none"
        >
          Exportar Relatório
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          class="text-none px-6"
          elevation="2"
          to="/agents"
        >
          Novo Agente
        </v-btn>
      </div>
    </div>

    <!-- Stats Grid -->
    <v-row>
      <v-col cols="12" sm="6" md="3" v-for="(stat, i) in stats" :key="i">
        <v-card class="stat-card fill-height" elevation="0">
          <v-card-text class="d-flex flex-column h-100 justify-space-between">
            <div class="d-flex justify-space-between align-start mb-4">
              <v-avatar
                :color="stat.color"
                variant="tonal"
                rounded="lg"
                size="48"
              >
                <v-icon :icon="stat.icon" size="24"></v-icon>
              </v-avatar>
              
              <v-chip
                size="x-small"
                :color="stat.trend > 0 ? 'success' : 'error'"
                variant="flat"
                class="font-weight-bold"
              >
                <v-icon start size="12">
                  {{ stat.trend > 0 ? 'mdi-arrow-up' : 'mdi-arrow-down' }}
                </v-icon>
                {{ Math.abs(stat.trend) }}%
              </v-chip>
            </div>
            
            <div>
              <div class="text-h4 font-weight-bold mb-1">{{ stat.value }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ stat.label }}</div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Main Content Grid -->
    <v-row class="mt-4">
      <!-- Activity Chart / Usage -->
      <v-col cols="12" md="8">
        <v-card class="fill-height chart-card" elevation="0">
          <v-card-title class="d-flex align-center py-4 px-6">
            <span class="text-h6 font-weight-bold">Uso de Tokens (24h)</span>
            <v-spacer></v-spacer>
            <v-btn-toggle
              v-model="chartPeriod"
              density="compact"
              variant="outlined"
              color="primary"
              divided
            >
              <v-btn value="day" size="small" class="text-none">Dia</v-btn>
              <v-btn value="week" size="small" class="text-none">Semana</v-btn>
            </v-btn-toggle>
          </v-card-title>
          
          <v-card-text class="px-6 pb-6">
            <div class="chart-box d-flex align-end justify-space-between pb-2 mb-4" style="height: 240px">
              <div
                v-for="(bar, i) in chartData"
                :key="i"
                class="chart-bar"
                :style="{ height: bar.height + '%', opacity: 0.5 + (i/24) }"
                :title="bar.value + ' tokens'"
              ></div>
            </div>
            <div class="d-flex justify-space-between text-caption text-medium-emphasis">
              <span>00:00</span>
              <span>06:00</span>
              <span>12:00</span>
              <span>18:00</span>
              <span>23:59</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- System Health / Status -->
      <v-col cols="12" md="4">
        <v-card class="fill-height status-card" elevation="0">
          <v-card-title class="text-h6 font-weight-bold py-4 px-6">Status do Sistema</v-card-title>
          <v-divider></v-divider>
          <v-list lines="two" bg-color="transparent">
            <v-list-item v-for="(service, i) in services" :key="i" class="py-3">
              <template v-slot:prepend>
                <div class="status-indicator mr-4">
                  <v-icon :color="service.status === 'online' ? 'success' : 'error'" size="12">mdi-circle</v-icon>
                  <div class="pulse-ring" v-if="service.status === 'online'"></div>
                </div>
              </template>
              
              <v-list-item-title class="font-weight-bold">{{ service.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ service.description }}</v-list-item-subtitle>
              
              <template v-slot:append>
                <v-chip size="x-small" :color="service.status === 'online' ? 'success' : 'error'" variant="tonal">
                  {{ service.latency }}ms
                </v-chip>
              </template>
            </v-list-item>
          </v-list>
          
          <v-card-text class="bg-surface-light rounded-lg ma-4 mt-0 pa-4 border-dashed">
            <div class="d-flex align-center justify-space-between mb-2">
              <span class="text-caption font-weight-bold text-uppercase">Armazenamento Vetorial</span>
              <span class="text-caption font-weight-bold">4.2GB / 10GB</span>
            </div>
            <v-progress-linear model-value="42" color="warning" height="8" rounded striped></v-progress-linear>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Recent Agents Grid -->
    <div class="d-flex align-center justify-space-between mt-8 mb-4">
      <h2 class="text-h5 font-weight-bold">Agentes Ativos</h2>
      <v-btn variant="text" color="primary" append-icon="mdi-arrow-right" to="/agents">Ver Todos</v-btn>
    </div>

    <v-row>
      <v-col cols="12" sm="6" md="4" lg="3" v-for="(agent, i) in activeAgents" :key="i">
        <v-card class="agent-card" elevation="0" link :to="'/agents'"> <!-- Directing to agents list for now -->
          <div class="agent-header pa-4" :style="`background: linear-gradient(135deg, ${agent.color}15, ${agent.color}05)`">
            <div class="d-flex justify-space-between align-start">
              <v-avatar :color="agent.color" size="48" class="elevation-2">
                 <v-icon color="white" size="24">{{ agent.icon }}</v-icon>
              </v-avatar>
              <v-menu>
                <template v-slot:activator="{ props }">
                  <v-btn icon="mdi-dots-vertical" variant="text" size="small" v-bind="props"></v-btn>
                </template>
                <v-list density="compact">
                  <v-list-item prepend-icon="mdi-pencil" title="Editar" link></v-list-item>
                  <v-list-item prepend-icon="mdi-pause" title="Pausar" link></v-list-item>
                </v-list>
              </v-menu>
            </div>
            <div class="mt-4">
              <h3 class="text-h6 font-weight-bold text-truncate">{{ agent.name }}</h3>
              <div class="text-caption text-medium-emphasis">{{ agent.role }}</div>
            </div>
          </div>
          
          <v-divider></v-divider>
          
          <div class="agent-footer pa-3 d-flex justify-space-between align-center">
            <div class="agent-stats d-flex gap-2">
              <v-chip size="x-small" variant="text" prepend-icon="mdi-message-text-outline">
                {{ agent.messages }} msgs
              </v-chip>
            </div>
            <v-avatar size="24" class="stacked-avatars">
              <v-img src="https://ui-avatars.com/api/?name=User+1&background=random"></v-img>
            </v-avatar>
          </div>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const chartPeriod = ref('day')

const stats = [
  { label: 'Agentes Ativos', value: '12', trend: 15, icon: 'mdi-robot', color: 'primary' },
  { label: 'Total de Conversas', value: '1,284', trend: 8.2, icon: 'mdi-chat-processing', color: 'info' },
  { label: 'Tokens Processados', value: '4.2M', trend: -2.4, icon: 'mdi-cpu-64-bit', color: 'warning' },
  { label: 'Documentos RAG', value: '856', trend: 12, icon: 'mdi-file-document-multiple', color: 'success' },
]

const services = [
  { name: 'Redis Cache', description: 'Conexão estável', status: 'online', latency: 4 },
  { name: 'PostgreSQL DB', description: 'Operacional', status: 'online', latency: 12 },
  { name: 'Weaviate Vector', description: 'Indexando', status: 'online', latency: 45 },
  { name: 'Background Worker', description: 'Processando filas', status: 'online', latency: 2 },
]

// Mock chart bars
const chartData = Array.from({ length: 24 }, (_, i) => ({
  height: Math.floor(Math.random() * 80) + 20,
  value: Math.floor(Math.random() * 5000)
}))

const activeAgents = [
  { name: 'Suporte Técnico', role: 'Atendimento N1', color: '#692c91', icon: 'mdi-headset', messages: 420 },
  { name: 'Vendas Pro', role: 'Conversão de Leads', color: '#16B1FF', icon: 'mdi-currency-usd', messages: 185 },
  { name: 'Secretária', role: 'Agendamento', color: '#FF4C51', icon: 'mdi-calendar-check', messages: 312 },
  { name: 'Researcher', role: 'Análise de Dados', color: '#FFB400', icon: 'mdi-magnify', messages: 89 },
]
</script>

<style scoped lang="scss">
.stat-card {
  border-radius: 16px;
  background-color: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), 0.05);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 24px rgba(0,0,0,0.06);
  }
}

.chart-card, .status-card {
  border-radius: 20px;
  background-color: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), 0.05);
}

.status-indicator {
  position: relative;
  
  .pulse-ring {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 2px solid rgb(var(--v-theme-success));
    animation: pulse 2s infinite;
  }
}

@keyframes pulse {
  0% { transform: translate(-50%, -50%) scale(0.8); opacity: 0.8; }
  100% { transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
}

.chart-bar {
  width: 3%;
  background: linear-gradient(to top, rgb(var(--v-theme-primary)), rgb(var(--v-theme-info)));
  border-radius: 4px;
  transition: height 0.4s ease;
  
  &:hover {
    opacity: 1 !important;
    filter: brightness(1.2);
  }
}

.agent-card {
  border-radius: 16px;
  border: 1px solid rgba(var(--v-border-color), 0.05);
  background-color: rgb(var(--v-theme-surface));
  transition: all 0.2s ease;
  
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(90, 90, 90, 0.08);
    border-color: rgb(var(--v-theme-primary), 0.3);
  }
}

.border-dashed {
  border: 1px dashed rgba(var(--v-border-color), 0.2) !important;
}
</style>
