<template>
  <div class="dashboard flex-grow-1">
    
    <!-- Top Stats Row -->
    <v-row class="mb-4">
      <v-col cols="12" md="3" v-for="(stat, i) in statCards" :key="i">
        <v-card class="stat-card glass-card pa-4 d-flex flex-column justify-center relative border-gradient" :class="stat.colorClass">
          <!-- Background Glow -->
          <div class="bg-glow" :style="{ background: stat.glowColor }"></div>
          
          <div class="d-flex justify-space-between align-start mb-2 z-1">
            <span class="text-caption font-weight-medium" style="color: rgba(255,255,255,0.7);">{{ stat.label }}</span>
            <v-icon :icon="stat.icon" size="28" :color="stat.iconColor" style="filter: drop-shadow(0 0 10px currentColor);"></v-icon>
          </div>
          <div class="d-flex justify-space-between align-end z-1">
            <div class="d-flex flex-column">
               <h3 class="text-h4 font-weight-bold text-white mb-1" style="line-height: 1;">{{ stat.value }}</h3>
               <div class="d-flex align-center text-caption" :class="stat.changeUp ? 'text-success' : 'text-error'">
                 <v-icon size="14" class="mr-1">{{ stat.changeUp ? 'mdi-arrow-top-right' : 'mdi-arrow-bottom-right' }}</v-icon>
                 <span class="font-weight-bold">{{ stat.changeText }}</span>
                 <span style="color: rgba(255,255,255,0.4);" class="ml-1 font-weight-regular">vs yesterday</span>
               </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Main Grid -->
    <v-row>
      <!-- Services Health -->
      <v-col cols="12" md="8" class="d-flex flex-column">
        <v-card class="glass-card flex-grow-1 border-gradient-dark">
          <v-card-text class="pa-5">
            <h3 class="text-subtitle-1 font-weight-medium text-white mb-4">Saúde dos Serviços</h3>
            <v-table density="comfortable" class="services-table bg-transparent">
              <thead>
                <tr>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.5);">Serviço</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.5);">Status</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.5);">Latência</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.5);">Uptime</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="service in services" :key="service.name" class="table-row">
                  <td class="text-body-2 text-white font-weight-medium py-3">{{ service.name }}</td>
                  <td class="py-3">
                    <div class="d-flex align-center">
                      <div class="status-dot mr-2" :class="service.status === 'Online' ? 'dot-online' : 'dot-offline'"></div>
                      <span class="text-body-2" :class="service.status === 'Online' ? 'text-success' : 'text-error'">{{ service.status }}</span>
                    </div>
                  </td>
                  <td class="text-body-2 py-3" style="color: rgba(255,255,255,0.8);">{{ service.latency }}</td>
                  <td class="text-body-2 py-3" style="color: rgba(255,255,255,0.8);">{{ service.uptime }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Quick Actions Column -->
      <v-col cols="12" md="4" class="d-flex flex-column">
        <v-card class="glass-card flex-grow-1 border-gradient-dark">
          <v-card-text class="pa-5 d-flex flex-column h-100">
            <h3 class="text-subtitle-1 font-weight-medium text-white mb-4">Ações Rápidas</h3>
            
            <div class="d-flex flex-column ga-4">
              <!-- Action 1 -->
              <div class="quick-action-btn primary-glow" @click="$router.push('/agents')">
                <div class="d-flex align-center">
                  <v-icon color="white" class="mr-2 opacity-80">mdi-plus</v-icon>
                  <span class="text-body-1 font-weight-bold text-white tracking-wide">Novo Agente IA</span>
                </div>
                <p class="text-caption mt-1 mb-0 opacity-60 text-white">Crie e treine um novo agente com facilidade.</p>
              </div>

               <!-- Action 2 -->
               <div class="quick-action-btn secondary-glow" @click="$router.push('/mcp')">
                <div class="d-flex align-center">
                  <v-icon color="white" class="mr-2 opacity-80">mdi-connection</v-icon>
                  <span class="text-body-1 font-weight-bold text-white tracking-wide">Configurar MCP</span>
                </div>
                <p class="text-caption mt-1 mb-0 opacity-60 text-white">Integre novas ferramentas e serviços via MCP.</p>
              </div>

               <!-- Action 3 -->
               <div class="quick-action-btn neutral-glow border-only" @click="$router.push('/documents')">
                <div class="d-flex align-center">
                  <v-icon color="white" class="mr-2 opacity-80">mdi-upload</v-icon>
                  <span class="text-body-1 font-weight-bold text-white tracking-wide">Importar Dados</span>
                </div>
                <p class="text-caption mt-1 mb-0 opacity-60 text-white">Carregue novos dados para sua base de conhecimento.</p>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const stats = ref({
  agents: 3,
  mcps: 2,
  webhooks: 0,
  avgResponse: 0.24
})

const statCards = [
  {
    label: 'Agentes Ativos',
    value: stats.value.agents,
    icon: 'mdi-robot-outline',
    iconColor: '#C490FF',
    glowColor: 'linear-gradient(135deg, rgba(157, 78, 221, 0.4) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-purple',
    changeUp: true,
    changeText: '+2',
  },
  {
    label: 'MCPs Configurados',
    value: stats.value.mcps,
    icon: 'mdi-graph',
    iconColor: '#00D1FF',
    glowColor: 'linear-gradient(135deg, rgba(0, 209, 255, 0.3) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-cyan',
    changeUp: true,
    changeText: '+2',
  },
  {
    label: 'Webhooks Hoje',
    value: stats.value.webhooks,
    icon: 'mdi-webhook',
    iconColor: '#00F0FF',
    glowColor: 'linear-gradient(135deg, rgba(0, 240, 255, 0.2) 0%, rgba(255,0,85,0.2) 100%)',
    colorClass: 'border-teal-red',
    changeUp: false,
    changeText: '-5',
  },
  {
    label: 'Tempo Médio',
    value: stats.value.avgResponse + 's',
    icon: 'mdi-timer-outline',
    iconColor: '#00FC8B',
    glowColor: 'linear-gradient(135deg, rgba(0, 252, 139, 0.3) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-green',
    changeUp: true,
    changeText: 'Avg. response time',
  }
]

const services = ref([
  { name: 'PostgreSQL', status: 'Online', latency: '12ms', uptime: '99.99%' },
  { name: 'Redis', status: 'Online', latency: '5ms', uptime: '99.98%' },
  { name: 'Weaviate', status: 'Online', latency: '20ms', uptime: '99.95%' }
])

const fetchHealth = async () => {
  try {
    const response = await axios.get('/api/health/dependencies')
    const deps = response.data.dependencies
    // Using fake data to match mock if api works we can override
    if (deps.postgresql?.status === 'healthy') services.value[0] = { ...services.value[0], latency: deps.postgresql.latency }
    if (deps.redis?.status === 'healthy') services.value[1] = { ...services.value[1], latency: deps.redis.latency }
    if (deps.weaviate?.status === 'healthy') services.value[2] = { ...services.value[2], latency: deps.weaviate.latency }
  } catch (error) {
    console.error('Health check partial update')
  }
}

onMounted(() => {
  fetchHealth()
})
</script>

<style scoped>
.z-1 { z-index: 1; position: relative; }
.relative { position: relative; }
.glass-card {
  background: rgba(16, 20, 34, 0.6) !important;
  border-radius: 16px;
  box-shadow: 0 4px 30px rgba(0,0,0,0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  overflow: hidden;
}

.border-gradient-dark {
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.border-gradient, .border-purple, .border-cyan, .border-teal-red, .border-green {
  border: 1px solid rgba(255,255,255,0.04);
}

.border-purple { border-top: 1px solid rgba(157, 78, 221, 0.5); }
.border-cyan { border-top: 1px solid rgba(0, 209, 255, 0.5); }
.border-teal-red { border-top: 1px solid rgba(0, 240, 255, 0.3); }
.border-green { border-top: 1px solid rgba(0, 252, 139, 0.5); }

.bg-glow {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  opacity: 0.8;
  z-index: 0;
  pointer-events: none;
}

/* Service Table Specs */
.services-table th {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  background: transparent !important;
}

.services-table td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.03) !important;
  background: transparent !important;
}

.table-row:hover td {
  background: rgba(255, 255, 255, 0.02) !important;
}

.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.dot-online {
  background: #00FC8B;
  box-shadow: 0 0 10px #00FC8B;
  animation: pulse-dot 2s ease-in-out infinite;
}
.dot-offline {
  background: #FF0055;
  box-shadow: 0 0 10px #FF0055;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}

/* Quick Actions Button */
.quick-action-btn {
  padding: 16px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.opacity-80 { opacity: 0.8; }
.opacity-60 { opacity: 0.6; }
.tracking-wide { letter-spacing: 0.02em; }

.quick-action-btn.primary-glow {
  background: linear-gradient(135deg, rgba(85, 8, 206, 0.9) 0%, rgba(157, 78, 221, 0.5) 100%);
  border: 1px solid rgba(157, 78, 221, 0.8);
  box-shadow: inset 0 2px 20px rgba(255,255,255,0.1), 0 0 20px rgba(157,78,221,0.2);
}

.quick-action-btn.secondary-glow {
  background: linear-gradient(135deg, rgba(40, 0, 100, 0.8) 0%, rgba(123, 44, 191, 0.4) 100%);
  border: 1px solid rgba(123, 44, 191, 0.6);
  box-shadow: inset 0 2px 10px rgba(255,255,255,0.05);
}

.quick-action-btn.neutral-glow {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(157, 78, 221, 0.3);
}

.quick-action-btn:hover {
  transform: translateY(-2px);
  filter: brightness(1.2);
  box-shadow: 0 5px 20px rgba(0,0,0,0.5), inset 0 2px 20px rgba(255,255,255,0.2);
}

</style>
