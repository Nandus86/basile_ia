<template>
  <div class="dashboard flex-grow-1">
    
    <!-- Top Stats Row -->
    <v-row class="mb-5">
      <v-col cols="12" sm="6" md="3" v-for="(stat, i) in statCards" :key="i">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative" :class="stat.colorClass">
          <!-- Background Glow -->
          <div class="bg-glow" :style="{ background: stat.glowColor }"></div>
          
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium" style="color: rgba(255,255,255,0.55); letter-spacing: 0.04em; text-transform: uppercase; font-size: 11px;">{{ stat.label }}</span>
            <div class="stat-icon-box" :style="{ background: stat.iconBg }">
              <v-icon :icon="stat.icon" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="d-flex justify-space-between align-end z-1">
            <div class="d-flex flex-column">
               <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ stat.value }}</h3>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Main Grid -->
    <v-row>
      <!-- Services Health -->
      <v-col cols="12" md="8" class="d-flex flex-column">
        <v-card class="glass-card flex-grow-1">
          <v-card-text class="pa-6">
            <div class="d-flex align-center justify-space-between mb-5">
              <h3 class="text-subtitle-1 font-weight-medium text-white d-flex align-center">
                <v-icon class="mr-2" size="20" color="primary">mdi-pulse</v-icon>
                Saúde dos Serviços
              </h3>
              <v-btn variant="text" size="small" color="primary" @click="fetchHealth" :loading="loadingHealth">
                <v-icon start size="16">mdi-refresh</v-icon>
                Atualizar
              </v-btn>
            </div>
            <v-table density="comfortable" class="services-table bg-transparent">
              <thead>
                <tr>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.4);">Serviço</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.4);">Status</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.4);">Latência</th>
                  <th class="text-caption font-weight-bold text-uppercase" style="color: rgba(255,255,255,0.4);">Uptime</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="service in services" :key="service.name" class="table-row">
                  <td class="text-body-2 text-white font-weight-medium py-3">
                    <div class="d-flex align-center">
                      <v-icon :color="service.iconColor" size="18" class="mr-2">{{ service.icon }}</v-icon>
                      {{ service.name }}
                    </div>
                  </td>
                  <td class="py-3">
                    <div class="d-flex align-center">
                      <div class="status-dot mr-2" :class="service.status === 'Online' ? 'dot-online' : 'dot-offline'"></div>
                      <span class="text-body-2" :class="service.status === 'Online' ? 'text-success' : 'text-error'">{{ service.status }}</span>
                    </div>
                  </td>
                  <td class="text-body-2 py-3" style="color: rgba(255,255,255,0.7);">{{ service.latency }}</td>
                  <td class="text-body-2 py-3" style="color: rgba(255,255,255,0.7);">{{ service.uptime }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Quick Actions Column -->
      <v-col cols="12" md="4" class="d-flex flex-column">
        <v-card class="glass-card flex-grow-1">
          <v-card-text class="pa-6 d-flex flex-column h-100">
            <h3 class="text-subtitle-1 font-weight-medium text-white mb-5 d-flex align-center">
              <v-icon class="mr-2" size="20" color="accent">mdi-lightning-bolt</v-icon>
              Ações Rápidas
            </h3>
            
            <div class="d-flex flex-column ga-3">
              <!-- Action 1 -->
              <div class="quick-action-btn primary-glow" @click="$router.push('/agents')">
                <div class="d-flex align-center">
                  <v-icon color="white" size="22" class="mr-3 opacity-90">mdi-plus-circle-outline</v-icon>
                  <div>
                    <span class="text-body-2 font-weight-bold text-white d-block">Novo Agente IA</span>
                    <span class="text-caption" style="color: rgba(255,255,255,0.5)">Crie e treine um novo agente</span>
                  </div>
                </div>
              </div>

               <!-- Action 2 -->
               <div class="quick-action-btn secondary-glow" @click="$router.push('/mcp')">
                <div class="d-flex align-center">
                  <v-icon color="white" size="22" class="mr-3 opacity-90">mdi-connection</v-icon>
                  <div>
                    <span class="text-body-2 font-weight-bold text-white d-block">Configurar MCP</span>
                    <span class="text-caption" style="color: rgba(255,255,255,0.5)">Integre ferramentas via MCP</span>
                  </div>
                </div>
              </div>

               <!-- Action 3 -->
               <div class="quick-action-btn neutral-glow" @click="$router.push('/documents')">
                <div class="d-flex align-center">
                  <v-icon color="white" size="22" class="mr-3 opacity-90">mdi-upload</v-icon>
                  <div>
                    <span class="text-body-2 font-weight-bold text-white d-block">Importar Dados</span>
                    <span class="text-caption" style="color: rgba(255,255,255,0.5)">Carregue dados na base RAG</span>
                  </div>
                </div>
              </div>

              <!-- Action 4 -->
               <div class="quick-action-btn neutral-glow" @click="$router.push('/chat')">
                <div class="d-flex align-center">
                  <v-icon color="white" size="22" class="mr-3 opacity-90">mdi-chat-processing-outline</v-icon>
                  <div>
                    <span class="text-body-2 font-weight-bold text-white d-block">Abrir Chat IA</span>
                    <span class="text-caption" style="color: rgba(255,255,255,0.5)">Teste seus agentes em tempo real</span>
                  </div>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import axios from '@/plugins/axios'

const loadingHealth = ref(false)

const agentCount = ref(0)
const mcpCount = ref(0)
const skillCount = ref(0)

const statCards = computed(() => [
  {
    label: 'Agentes Ativos',
    value: agentCount.value,
    icon: 'mdi-robot-outline',
    iconBg: 'linear-gradient(135deg, #7C3AED, #9D4EDD)',
    glowColor: 'linear-gradient(135deg, rgba(157, 78, 221, 0.3) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-purple',
  },
  {
    label: 'MCPs Configurados',
    value: mcpCount.value,
    icon: 'mdi-connection',
    iconBg: 'linear-gradient(135deg, #00A3FF, #00D1FF)',
    glowColor: 'linear-gradient(135deg, rgba(0, 209, 255, 0.2) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-cyan',
  },
  {
    label: 'Skills Criadas',
    value: skillCount.value,
    icon: 'mdi-star-shooting-outline',
    iconBg: 'linear-gradient(135deg, #F59E0B, #FBBF24)',
    glowColor: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-amber',
  },
  {
    label: 'Serviços Online',
    value: onlineCount.value + '/' + services.value.length,
    icon: 'mdi-check-network-outline',
    iconBg: 'linear-gradient(135deg, #00FC8B, #10B981)',
    glowColor: 'linear-gradient(135deg, rgba(0, 252, 139, 0.2) 0%, rgba(0,0,0,0) 60%)',
    colorClass: 'border-green',
  }
])

const services = ref([
  { name: 'PostgreSQL', status: 'Online', latency: '—', uptime: '99.99%', icon: 'mdi-database', iconColor: '#3B82F6' },
  { name: 'Redis', status: 'Online', latency: '—', uptime: '99.98%', icon: 'mdi-memory', iconColor: '#EF4444' },
  { name: 'Weaviate', status: 'Online', latency: '—', uptime: '99.95%', icon: 'mdi-vector-polyline', iconColor: '#10B981' },
  { name: 'Background Worker', status: 'Online', latency: '—', uptime: '99.9%', icon: 'mdi-cog-sync', iconColor: '#F59E0B' }
])

const onlineCount = computed(() => services.value.filter(s => s.status === 'Online').length)

const fetchHealth = async () => {
  loadingHealth.value = true
  try {
    const response = await axios.get('/health/dependencies')
    const deps = response.data.dependencies
    if (deps.postgresql) {
      services.value[0].status = deps.postgresql.status === 'healthy' ? 'Online' : 'Offline'
      services.value[0].latency = deps.postgresql.latency || '—'
    }
    if (deps.redis) {
      services.value[1].status = deps.redis.status === 'healthy' ? 'Online' : 'Offline'
      services.value[1].latency = deps.redis.latency || '—'
    }
    if (deps.weaviate) {
      services.value[2].status = deps.weaviate.status === 'healthy' ? 'Online' : 'Offline'
      services.value[2].latency = deps.weaviate.latency || '—'
    }
  } catch (error) {
    console.warn('Health check partial update')
  } finally {
    loadingHealth.value = false
  }
}

const fetchCounts = async () => {
  try {
    const [agentsRes, mcpsRes, skillsRes] = await Promise.allSettled([
      axios.get('/agents'),
      axios.get('/mcps'),
      axios.get('/skills/')
    ])
    if (agentsRes.status === 'fulfilled') agentCount.value = agentsRes.value.data.agents?.length || 0
    if (mcpsRes.status === 'fulfilled') mcpCount.value = mcpsRes.value.data.mcps?.length || 0
    if (skillsRes.status === 'fulfilled') skillCount.value = skillsRes.value.data.skills?.length || 0
  } catch (e) {
    console.warn('Count fetch partial failure')
  }
}

onMounted(() => {
  fetchHealth()
  fetchCounts()
})
</script>

<style scoped>
.z-1 { z-index: 1; position: relative; }
.relative { position: relative; }

.stat-icon-box {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.border-purple { border-top: 2px solid rgba(157, 78, 221, 0.5); }
.border-cyan { border-top: 2px solid rgba(0, 209, 255, 0.5); }
.border-amber { border-top: 2px solid rgba(245, 158, 11, 0.5); }
.border-green { border-top: 2px solid rgba(0, 252, 139, 0.5); }

.bg-glow {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  opacity: 0.7;
  z-index: 0;
  pointer-events: none;
}

/* Service Table */
.services-table th {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  background: transparent !important;
}

.services-table td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.03) !important;
  background: transparent !important;
}

.table-row:hover td {
  background: rgba(157, 78, 221, 0.03) !important;
}

.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.dot-online {
  background: #00FC8B;
  box-shadow: 0 0 8px #00FC8B;
  animation: pulse-dot 2.5s ease-in-out infinite;
}
.dot-offline {
  background: #FF0055;
  box-shadow: 0 0 8px #FF0055;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.4); }
}

/* Quick Actions */
.quick-action-btn {
  padding: 14px 16px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.opacity-90 { opacity: 0.9; }

.quick-action-btn.primary-glow {
  background: linear-gradient(135deg, rgba(85, 8, 206, 0.85) 0%, rgba(157, 78, 221, 0.45) 100%);
  border: 1px solid rgba(157, 78, 221, 0.6);
  box-shadow: inset 0 1px 12px rgba(255,255,255,0.08), 0 0 16px rgba(157,78,221,0.15);
}

.quick-action-btn.secondary-glow {
  background: linear-gradient(135deg, rgba(40, 0, 100, 0.7) 0%, rgba(123, 44, 191, 0.35) 100%);
  border: 1px solid rgba(123, 44, 191, 0.45);
}

.quick-action-btn.neutral-glow {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.quick-action-btn:hover {
  transform: translateY(-2px);
  filter: brightness(1.15);
  box-shadow: 0 6px 20px rgba(0,0,0,0.3), inset 0 1px 12px rgba(255,255,255,0.1);
}
</style>
