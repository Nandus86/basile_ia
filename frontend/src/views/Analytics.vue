<template>
  <v-container fluid class="analytics-container pa-6">
    <v-row>
      <v-col cols="12">
        <div class="d-flex align-center justify-space-between mb-6">
          <div>
            <h1 class="text-h4 font-weight-bold mb-2">Analytics & Relatórios</h1>
            <p class="text-subtitle-1 text-medium-emphasis">
              Visão geral de engajamento e relatórios do Basile.
            </p>
          </div>
          <div class="d-flex align-center ga-3">
            <v-btn color="secondary" variant="outlined" prepend-icon="mdi-cog" @click="openConfig">
              Configurar Analistas
            </v-btn>
            <v-btn color="primary" prepend-icon="mdi-refresh" @click="handleRefresh">
              Atualizar
            </v-btn>
          </div>
        </div>
      </v-col>
    </v-row>

    <v-tabs v-model="activeTab" bg-color="surface" class="mb-6 border-radius-xl elevation-2">
      <v-tab value="users">Usuários</v-tab>
      <v-tab value="churches">Igrejas Locais</v-tab>
      <v-tab value="system">Sistema Global</v-tab>
    </v-tabs>

    <v-window v-model="activeTab" class="bg-transparent" style="overflow: visible;">
      <v-window-item value="users">

    <v-row>
      <v-col cols="12" md="4" class="mb-2">
        <v-text-field
          v-model="search"
          label="Buscar por ID da Sessão ou Nome"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          @update:model-value="onSearch"
        ></v-text-field>
      </v-col>
      <v-spacer></v-spacer>
      <v-col cols="12" md="3" class="mb-2 d-flex align-center">
        <v-text-field
          v-model="targetDate"
          type="date"
          label="Data Retroativa (Opcional)"
          variant="outlined"
          density="compact"
          hide-details
          class="mr-2"
        ></v-text-field>
        <v-btn
          color="warning"
          prepend-icon="mdi-play-box-multiple"
          :loading="runningAll"
          @click="runAllManual"
          :disabled="!targetDate"
        >
          Rodar Todos
        </v-btn>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-card class="elevation-2 border-radius-xl">
          <v-card-text class="pa-0">
            <v-data-table-server
              :headers="headers"
              :items="users"
              :items-length="totalItems"
              :loading="loading"
              v-model:items-per-page="itemsPerPage"
              v-model:page="page"
              @update:options="fetchAnalytics"
              class="elevation-0"
              hover
            >
              <template v-slot:item.name="{ item }">
                <span class="font-weight-medium">{{ (item.raw || item).profile_data?.__zona_crm?.first_name || (item.raw || item).profile_data?.__zona_crm?.['Nome Completo'] || (item.raw || item).profile_data?.__zona_crm?.name || (item.raw || item).profile_data?.__zona_crm?.nome || 'Desconhecido' }}</span>
              </template>
              <template v-slot:item.church="{ item }">
                {{ (item.raw || item).profile_data?.__zona_crm?.church_name || (item.raw || item).profile_data?.__zona_crm?.['Igreja Sede'] || (item.raw || item).profile_data?.__zona_crm?.church_id || (item.raw || item).church_id || 'Não Informada' }}
              </template>
              <template v-slot:item.engagement_score="{ item }">
                <v-chip
                  :color="getScoreColor((item.raw || item).engagement_score)"
                  size="small"
                  class="font-weight-medium"
                >
                  {{ (item.raw || item).engagement_score }}
                </v-chip>
              </template>
              <template v-slot:item.care_priority="{ item }">
                <v-chip
                  :color="getPriorityColor((item.raw || item).care_priority)"
                  size="small"
                  class="text-uppercase font-weight-bold"
                >
                  {{ (item.raw || item).care_priority }}
                </v-chip>
              </template>
              <template v-slot:item.last_seen_at="{ item }">
                {{ formatDate((item.raw || item).last_seen_at) }}
              </template>
              <template v-slot:item.actions="{ item }">
                <v-btn 
                  icon="mdi-play" 
                  size="small" 
                  variant="text" 
                  color="success" 
                  :loading="runningSessions[(item.raw || item).session_id]"
                  @click="runAgent((item.raw || item).session_id)"
                  title="Rodar Analista Agora"
                ></v-btn>
                <v-btn icon="mdi-eye" size="small" variant="text" color="primary" @click="viewDetails(item.raw || item)"></v-btn>
              </template>
            </v-data-table-server>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-window-item>

      <v-window-item value="churches">
        <ChurchReports ref="churchReportsRef" />
      </v-window-item>

      <v-window-item value="system">
        <SystemReports ref="systemReportsRef" />
      </v-window-item>
    </v-window>

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
    <v-dialog v-model="configDialog" max-width="800px">
      <v-card>
        <v-card-title class="text-h5 bg-surface pa-4 d-flex justify-space-between align-center">
          Configurações de Analytics
          <v-btn icon="mdi-close" variant="text" @click="configDialog = false"></v-btn>
        </v-card-title>
        
        <v-tabs v-model="configTab" bg-color="surface">
          <v-tab value="motor">Motor de IA</v-tab>
          <v-tab value="crm">Mapeamento CRM</v-tab>
          <v-tab value="metrics">Mapeamento Métricas</v-tab>
        </v-tabs>

        <v-card-text class="pa-4" style="min-height: 300px; max-height: 60vh; overflow-y: auto;">
          <v-window v-model="configTab">
            <!-- ABA 1: MOTOR DE IA -->
            <v-window-item value="motor">
              <v-form ref="configForm">
                <v-row class="mt-2">
                  <v-col cols="12">
                    <v-switch
                      v-model="config.is_active"
                      label="Motor Analista Ativo"
                      color="primary"
                    ></v-switch>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="config.agent_id"
                      :items="availableAgents"
                      item-title="name"
                      item-value="id"
                      label="Agente Analista de Usuários"
                      placeholder="Ex: Agente Analista de Perfis"
                      variant="outlined"
                      :disabled="!config.is_active"
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="2">
                    <v-text-field
                      v-model="config.cron_time"
                      label="Horário"
                      type="time"
                      variant="outlined"
                      :disabled="!config.is_active"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-text-field
                      v-model="config.user_webhook_url"
                      label="Webhook Saída (Usuário)"
                      placeholder="https://sua-automacao.com/webhook"
                      variant="outlined"
                      :disabled="!config.is_active"
                      clearable
                    ></v-text-field>
                  </v-col>

                  <v-col cols="12">
                    <v-combobox
                      v-model="config.allowed_endpoints"
                      :items="availablePaths"
                      multiple
                      chips
                      closable-chips
                      clearable
                      prepend-inner-icon="mdi-filter-variant"
                      label="Endpoints / Paths de Entrada dos Usuários"
                      placeholder="Selecione ou digite os paths... (Deixe vazio para rastrear todos)"
                      hint="Apenas mensagens recebidas através destes endpoints serão contabilizadas como interações válidas do usuário."
                      persistent-hint
                      variant="outlined"
                      :disabled="!config.is_active"
                    ></v-combobox>
                  </v-col>
                  
                  <v-col cols="12">
                    <v-divider class="my-2"></v-divider>
                    <h4 class="text-subtitle-1 mb-2">Motor de Relatórios: Igrejas</h4>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="config.church_agent_id"
                      :items="availableAgents"
                      item-title="name"
                      item-value="id"
                      label="Agente Supervisor da Igreja"
                      placeholder="Ex: Agente Pastor"
                      variant="outlined"
                      :disabled="!config.is_active"
                      clearable
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="2">
                    <v-text-field
                      v-model="config.church_report_time"
                      label="Horário"
                      type="time"
                      variant="outlined"
                      :disabled="!config.is_active"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-text-field
                      v-model="config.church_webhook_url"
                      label="Webhook Saída (Igreja)"
                      placeholder="https://sua-automacao.com/webhook"
                      variant="outlined"
                      :disabled="!config.is_active"
                      clearable
                    ></v-text-field>
                  </v-col>

                  <v-col cols="12">
                    <v-divider class="my-2"></v-divider>
                    <h4 class="text-subtitle-1 mb-2">Motor de Relatórios: Sistema Global</h4>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="config.system_agent_id"
                      :items="availableAgents"
                      item-title="name"
                      item-value="id"
                      label="Agente Diretor do Sistema"
                      placeholder="Ex: Agente Diretor"
                      variant="outlined"
                      :disabled="!config.is_active"
                      clearable
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="2">
                    <v-text-field
                      v-model="config.system_report_time"
                      label="Horário"
                      type="time"
                      variant="outlined"
                      :disabled="!config.is_active"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-text-field
                      v-model="config.system_webhook_url"
                      label="Webhook Saída (Sistema)"
                      placeholder="https://sua-automacao.com/webhook"
                      variant="outlined"
                      :disabled="!config.is_active"
                      clearable
                    ></v-text-field>
                  </v-col>
                </v-row>
              </v-form>
            </v-window-item>

            <!-- ABA 2: MAPEAMENTO CRM -->
            <v-window-item value="crm">
              <div class="d-flex justify-space-between align-center mb-4 mt-2">
                <div>
                  <h3 class="text-subtitle-1 font-weight-bold">Campos do CRM</h3>
                  <p class="text-caption text-medium-emphasis">Configure quais chaves do Payload preenchem a Zona CRM.</p>
                </div>
                <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="addMapping('crm')">Adicionar Campo</v-btn>
              </div>
              
              <v-row v-for="(item, index) in config.crm_mapping" :key="'crm'+index" class="align-center mb-2">
                <v-col cols="12" md="5" class="py-1">
                  <v-text-field v-model="item.dest_key" label="Chave de Destino (Ex: Nome)" variant="outlined" density="compact" hide-details></v-text-field>
                </v-col>
                <v-col cols="12" md="6" class="py-1">
                  <v-text-field v-model="item.source_path" label="Caminho no Payload (Ex: member.fullname)" variant="outlined" density="compact" hide-details></v-text-field>
                </v-col>
                <v-col cols="12" md="1" class="py-1 text-center">
                  <v-btn icon="mdi-delete" color="error" variant="text" size="small" @click="removeMapping('crm', index)"></v-btn>
                </v-col>
              </v-row>
              <div v-if="config.crm_mapping.length === 0" class="text-center pa-4 text-medium-emphasis">
                Nenhum mapeamento configurado. O sistema usará os campos padrão (Nome, Telefone, Igreja, etc).
              </div>
            </v-window-item>

            <!-- ABA 3: MAPEAMENTO MÉTRICAS -->
            <v-window-item value="metrics">
              <div class="d-flex justify-space-between align-center mb-4 mt-2">
                <div>
                  <h3 class="text-subtitle-1 font-weight-bold">Métricas Extras</h3>
                  <p class="text-caption text-medium-emphasis">Extraia dados brutos do Payload para a Zona de Métricas (Apenas valores diretos).</p>
                </div>
                <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="addMapping('metrics')">Adicionar Campo</v-btn>
              </div>
              
              <v-row v-for="(item, index) in config.metrics_mapping" :key="'met'+index" class="align-center mb-2">
                <v-col cols="12" md="5" class="py-1">
                  <v-text-field v-model="item.dest_key" label="Chave de Destino (Ex: ID da Origem)" variant="outlined" density="compact" hide-details></v-text-field>
                </v-col>
                <v-col cols="12" md="6" class="py-1">
                  <v-text-field v-model="item.source_path" label="Caminho no Payload (Ex: origin_id)" variant="outlined" density="compact" hide-details></v-text-field>
                </v-col>
                <v-col cols="12" md="1" class="py-1 text-center">
                  <v-btn icon="mdi-delete" color="error" variant="text" size="small" @click="removeMapping('metrics', index)"></v-btn>
                </v-col>
              </v-row>
              <div v-if="config.metrics_mapping.length === 0" class="text-center pa-4 text-medium-emphasis">
                Nenhum mapeamento extra. O sistema contará sessões automaticamente.
              </div>
            </v-window-item>
          </v-window>
        </v-card-text>
        
        <v-divider></v-divider>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="configDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveConfig" :loading="savingConfig">Salvar Configuração</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    
    <!-- Snackbar for notifications -->
    <v-snackbar v-model="snackbar" :color="snackbarColor" timeout="3000">
      {{ snackbarText }}
      <template v-slot:actions>
        <v-btn variant="text" icon="mdi-close" @click="snackbar = false"></v-btn>
      </template>
    </v-snackbar>
  </v-container>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import axios from '@/plugins/axios'
import ChurchReports from './ChurchReports.vue'
import SystemReports from './SystemReports.vue'

const activeTab = ref('users')
const churchReportsRef = ref(null)
const systemReportsRef = ref(null)

const loading = ref(false)
const users = ref([])
const dialog = ref(false)
const selectedUser = ref(null)
const runningSessions = ref({})
const runningAll = ref(false)
const targetDate = ref(new Date().toISOString().substring(0, 10))

const search = ref('')
const page = ref(1)
const itemsPerPage = ref(50)
const totalItems = ref(0)

const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')

const showSnackbar = (text, color = 'success') => {
  snackbarText.value = text
  snackbarColor.value = color
  snackbar.value = true
}

// Config states
const configTab = ref('motor')
const configDialog = ref(false)
const savingConfig = ref(false)
const availableAgents = ref([])
const availablePaths = ref([])
const config = ref({
  is_active: false,
  agent_id: null,
  church_agent_id: null,
  system_agent_id: null,
  cron_time: '03:00',
  church_report_time: '04:00',
  system_report_time: '04:30',
  user_webhook_url: null,
  church_webhook_url: null,
  system_webhook_url: null,
  allowed_endpoints: [],
  crm_mapping: [],
  metrics_mapping: []
})

const headers = [
  { title: 'Sessão', key: 'session_id' },
  { title: 'Nome', key: 'name' },
  { title: 'Igreja', key: 'church' },
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

let searchTimeout = null
const onSearch = () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    page.value = 1
    fetchAnalytics()
  }, 500)
}

const fetchAnalytics = async () => {
  loading.value = true
  try {
    const skip = (page.value - 1) * itemsPerPage.value
    const params = {
      skip,
      limit: itemsPerPage.value,
      search: search.value || null
    }
    const response = await axios.get(`/analytics/users`, { params })
    users.value = response.data.users
    totalItems.value = response.data.total
  } catch (error) {
    console.error('Failed to fetch analytics:', error)
    showSnackbar('Erro ao carregar usuários.', 'error')
  } finally {
    loading.value = false
  }
}

const handleRefresh = () => {
  if (activeTab.value === 'users') {
    fetchAnalytics()
  } else if (activeTab.value === 'churches') {
    if (churchReportsRef.value?.fetchReports) churchReportsRef.value.fetchReports()
  } else if (activeTab.value === 'system') {
    if (systemReportsRef.value?.fetchReports) systemReportsRef.value.fetchReports()
  }
}

const runAgent = async (sessionId) => {
  runningSessions.value[sessionId] = true
  try {
    await axios.post(`/analytics/users/${sessionId}/run`)
    showSnackbar('Análise enviada para a fila de processamento!')
  } catch (error) {
    console.error('Failed to run agent:', error)
    const msg = error.response?.data?.detail || 'Erro ao iniciar análise'
    showSnackbar(msg, 'error')
  } finally {
    runningSessions.value[sessionId] = false
  }
}

const runAllManual = async () => {
  if (!targetDate.value) {
    showSnackbar('Selecione uma data.', 'warning')
    return
  }
  runningAll.value = true
  try {
    const res = await axios.post(`/analytics/users/run-all`, { target_date: targetDate.value })
    showSnackbar(res.data.message)
  } catch (error) {
    console.error('Failed to run all agents:', error)
    const msg = error.response?.data?.detail || 'Erro ao enfileirar análises'
    showSnackbar(msg, 'error')
  } finally {
    runningAll.value = false
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

    // Fetch available paths from tracking stats and webhooks
    try {
      const [statsResp, webhooksResp] = await Promise.allSettled([
        axios.get('/tracking/stats'),
        axios.get('/webhooks-config')
      ])
      const pathsSet = new Set([
        '/process',
        '/disparo/campaign',
        '/webhook/n8n',
        '/webhook/trigger/personalizado'
      ])
      if (statsResp.status === 'fulfilled' && statsResp.value.data?.by_path) {
        statsResp.value.data.by_path.forEach(p => { if (p.path) pathsSet.add(p.path) })
      }
      if (webhooksResp.status === 'fulfilled' && Array.isArray(webhooksResp.value.data)) {
        webhooksResp.value.data.forEach(w => {
          if (w.path) pathsSet.add(w.path.startsWith('/') ? w.path : `/webhook/${w.path}`)
        })
      }
      availablePaths.value = Array.from(pathsSet).sort()
    } catch (err) {
      console.error('Failed to fetch paths', err)
    }

    // Fetch current config
    const configResp = await axios.get(`/analytics/config`)
    if (configResp.data) {
      config.value.is_active = configResp.data.is_active
      config.value.agent_id = configResp.data.agent_id
      config.value.church_agent_id = configResp.data.church_agent_id
      config.value.system_agent_id = configResp.data.system_agent_id
      config.value.cron_time = configResp.data.cron_time || '03:00'
      config.value.church_report_time = configResp.data.church_report_time || '04:00'
      config.value.system_report_time = configResp.data.system_report_time || '04:30'
      config.value.user_webhook_url = configResp.data.user_webhook_url
      config.value.church_webhook_url = configResp.data.church_webhook_url
      config.value.system_webhook_url = configResp.data.system_webhook_url
      config.value.allowed_endpoints = configResp.data.allowed_endpoints || []
      config.value.crm_mapping = configResp.data.crm_mapping || []
      config.value.metrics_mapping = configResp.data.metrics_mapping || []
    }
    
    configDialog.value = true
  } catch (error) {
    console.error('Failed to load config or agents', error)
    showSnackbar('Erro ao carregar configurações.', 'error')
  }
}

const addMapping = (type) => {
  if (type === 'crm') {
    config.value.crm_mapping.push({ dest_key: '', source_path: '' })
  } else if (type === 'metrics') {
    config.value.metrics_mapping.push({ dest_key: '', source_path: '' })
  }
}

const removeMapping = (type, index) => {
  if (type === 'crm') {
    config.value.crm_mapping.splice(index, 1)
  } else if (type === 'metrics') {
    config.value.metrics_mapping.splice(index, 1)
  }
}

const saveConfig = async () => {
  savingConfig.value = true
  try {
    await axios.put(`/analytics/config`, config.value)
    showSnackbar('Configurações salvas e agendamentos atualizados com sucesso!', 'success')
    configDialog.value = false
  } catch (error) {
    console.error('Failed to save config', error)
    const msg = error.response?.data?.detail || 'Erro ao salvar configuração'
    showSnackbar(msg, 'error')
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
