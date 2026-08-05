<template>
  <v-container fluid class="analytics-container pa-6">
    <v-row>
      <v-col cols="12">
        <div class="d-flex align-center justify-space-between mb-6">
          <div>
            <h1 class="text-h4 font-weight-bold mb-2">User Analytics</h1>
            <p class="text-subtitle-1 text-medium-emphasis">
              Visão geral do engajamento e curadoria inteligente dos usuários.
            </p>
          </div>
          <div class="d-flex align-center ga-3">
            <v-btn color="secondary" variant="outlined" prepend-icon="mdi-cog" @click="openConfig">
              Configurar Analista
            </v-btn>
            <v-btn color="primary" prepend-icon="mdi-refresh" @click="fetchAnalytics">
              Atualizar
            </v-btn>
          </div>
        </div>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-card class="elevation-2 border-radius-xl">
          <v-card-text class="pa-0">
            <v-data-table
              :headers="headers"
              :items="users"
              :loading="loading"
              class="elevation-0"
              hover
            >
              <template v-slot:item.engagement_score="{ item }">
                <v-chip
                  :color="getScoreColor(item.engagement_score)"
                  size="small"
                  class="font-weight-medium"
                >
                  {{ item.engagement_score }}
                </v-chip>
              </template>
              <template v-slot:item.care_priority="{ item }">
                <v-chip
                  :color="getPriorityColor(item.care_priority)"
                  size="small"
                  class="text-uppercase font-weight-bold"
                >
                  {{ item.care_priority }}
                </v-chip>
              </template>
              <template v-slot:item.last_seen_at="{ item }">
                {{ formatDate(item.last_seen_at) }}
              </template>
              <template v-slot:item.actions="{ item }">
                <v-btn icon="mdi-eye" size="small" variant="text" color="primary" @click="viewDetails(item)"></v-btn>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Dialog for details -->
    <v-dialog v-model="dialog" max-width="800px">
      <v-card v-if="selectedUser">
        <v-card-title class="text-h5 bg-surface pa-4 d-flex justify-space-between align-center">
          Perfil Analítico
          <v-btn icon="mdi-close" variant="text" @click="dialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="pa-4">
          <v-row>
            <v-col cols="12" md="6">
              <h3 class="text-h6 mb-3">Snapshot CRM</h3>
              <pre class="bg-grey-darken-4 pa-3 rounded text-caption">{{ JSON.stringify(selectedUser.profile_data.__zona_crm, null, 2) }}</pre>
            </v-col>
            <v-col cols="12" md="6">
              <h3 class="text-h6 mb-3">Métricas</h3>
              <pre class="bg-grey-darken-4 pa-3 rounded text-caption">{{ JSON.stringify(selectedUser.profile_data.__zona_metricas, null, 2) }}</pre>
            </v-col>
            <v-col cols="12">
              <h3 class="text-h6 mb-3 text-primary">Aprendizado (IA)</h3>
              <pre class="bg-grey-darken-4 pa-3 rounded text-caption">{{ JSON.stringify(selectedUser.profile_data.__zona_aprendizado, null, 2) }}</pre>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Dialog for Config -->
    <v-dialog v-model="configDialog" max-width="600px">
      <v-card>
        <v-card-title class="text-h5 bg-surface pa-4 d-flex justify-space-between align-center">
          Configurar Agente Analista
          <v-btn icon="mdi-close" variant="text" @click="configDialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="pa-4">
          <v-form ref="configForm">
            <v-row>
              <v-col cols="12">
                <v-switch
                  v-model="config.is_active"
                  label="Motor Analista Ativo"
                  color="primary"
                ></v-switch>
              </v-col>
              <v-col cols="12" md="8">
                <v-select
                  v-model="config.agent_id"
                  :items="availableAgents"
                  item-title="name"
                  item-value="id"
                  label="Selecione o Agente Analista"
                  placeholder="Ex: Agente Analista de Perfis"
                  variant="outlined"
                  :disabled="!config.is_active"
                ></v-select>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="config.cron_time"
                  label="Horário de Disparo"
                  type="time"
                  variant="outlined"
                  :disabled="!config.is_active"
                ></v-text-field>
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="configDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveConfig" :loading="savingConfig">Salvar Configuração</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from '@/plugins/axios'

const loading = ref(false)
const users = ref([])
const dialog = ref(false)
const selectedUser = ref(null)

// Config states
const configDialog = ref(false)
const savingConfig = ref(false)
const availableAgents = ref([])
const config = ref({
  is_active: false,
  agent_id: null,
  cron_time: '03:00'
})

const headers = [
  { title: 'Sessão', key: 'session_id' },
  { title: 'Interações', key: 'interaction_count' },
  { title: 'Score', key: 'engagement_score' },
  { title: 'Prioridade', key: 'care_priority' },
  { title: 'Última Interação', key: 'last_seen_at' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'end' }
]

const getScoreColor = (score) => {
  if (score >= 70) return 'success'
  if (score >= 40) return 'warning'
  return 'error'
}

const getPriorityColor = (priority) => {
  switch (priority) {
    case 'critical': return 'error'
    case 'high': return 'warning'
    case 'medium': return 'info'
    default: return 'success'
  }
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('pt-BR')
}

const fetchAnalytics = async () => {
  loading.value = true
  try {
    const response = await axios.get(`/analytics/users`)
    users.value = response.data.users
  } catch (error) {
    console.error('Failed to fetch analytics:', error)
  } finally {
    loading.value = false
  }
}

const viewDetails = (user) => {
  selectedUser.value = user
  dialog.value = true
}

const openConfig = async () => {
  try {
    // Fetch available agents
    const agentsResp = await axios.get(`/agents`)
    availableAgents.value = agentsResp.data.agents || []
    
    // Fetch current config
    const configResp = await axios.get(`/analytics/config`)
    if (configResp.data) {
      config.value.is_active = configResp.data.is_active
      config.value.agent_id = configResp.data.agent_id
      config.value.cron_time = configResp.data.cron_time
    }
    
    configDialog.value = true
  } catch (error) {
    console.error('Failed to load config or agents', error)
  }
}

const saveConfig = async () => {
  savingConfig.value = true
  try {
    await axios.put(`/analytics/config`, config.value)
    configDialog.value = false
  } catch (error) {
    console.error('Failed to save config', error)
  } finally {
    savingConfig.value = false
  }
}

onMounted(() => {
  fetchAnalytics()
})
</script>

<style scoped>
.border-radius-xl {
  border-radius: 16px;
}
pre {
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
