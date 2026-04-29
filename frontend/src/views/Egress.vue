<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

const results = ref([])
const totalResults = ref(0)
const loading = ref(false)
const serviceOnline = ref(null)
const statusFilter = ref(null)
const detailDialog = ref(false)
const selectedResult = ref(null)

const EGRESS_BASE = '/egress-api'

const egressAxios = axios.create({
  baseURL: EGRESS_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const headers = [
  { title: 'JOB ID', key: 'job_id' },
  { title: 'STATUS', key: 'status', align: 'center' },
  { title: 'TENTATIVAS', key: 'attempts', align: 'center' },
  { title: 'ERRO', key: 'last_error' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const statusOptions = [
  { title: 'Todos', value: null },
  { title: 'Pendente', value: 'pending' },
  { title: 'Processando', value: 'processing' },
  { title: 'Enviado', value: 'sent' },
  { title: 'Falha', value: 'failed' }
]

const sentCount = computed(() => results.value.filter(r => r.status === 'sent').length)
const failedCount = computed(() => results.value.filter(r => r.status === 'failed').length)
const pendingCount = computed(() => results.value.filter(r => r.status === 'pending' || r.status === 'processing').length)

const statusColor = (status) => {
  const map = {
    pending: 'warning',
    processing: 'info',
    sent: 'success',
    failed: 'error',
    unknown: 'grey'
  }
  return map[status] || 'grey'
}

const statusIcon = (status) => {
  const map = {
    pending: 'mdi-clock-outline',
    processing: 'mdi-loading mdi-spin',
    sent: 'mdi-check-circle-outline',
    failed: 'mdi-alert-circle-outline',
    unknown: 'mdi-help-circle-outline'
  }
  return map[status] || 'mdi-help-circle-outline'
}

const showSnackbar = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

const checkHealth = async () => {
  try {
    const res = await egressAxios.get('/health')
    serviceOnline.value = res.data?.status === 'healthy'
  } catch {
    serviceOnline.value = false
  }
}

const fetchResults = async () => {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    const res = await egressAxios.get('/status', { params })
    results.value = res.data.results
    totalResults.value = res.data.total
  } catch (err) {
    showSnackbar('Erro ao carregar resultados', 'error')
  } finally {
    loading.value = false
  }
}

const viewDetail = async (item) => {
  try {
    const res = await egressAxios.get(`/status/${item.job_id}`)
    selectedResult.value = res.data
    detailDialog.value = true
  } catch {
    showSnackbar('Erro ao buscar detalhes', 'error')
  }
}

const refreshData = () => {
  checkHealth()
  fetchResults()
}

onMounted(() => {
  checkHealth()
  fetchResults()
})
</script>

<template>
  <div class="egress-container">
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <v-avatar color="deep-orange" variant="tonal" rounded size="48" class="mr-4">
        <v-icon icon="mdi-logout-variant" size="24"></v-icon>
      </v-avatar>
      <div>
        <h2 class="text-h4 font-weight-bold">Saída (Egress)</h2>
        <div class="text-subtitle-1 text-medium-emphasis">
          Monitore resultados enviados via webhook
        </div>
      </div>
      <v-spacer></v-spacer>
      <v-chip
        :color="serviceOnline === true ? 'success' : serviceOnline === false ? 'error' : 'grey'"
        variant="tonal"
        class="mr-3"
        size="small"
      >
        <v-icon start size="12">mdi-circle</v-icon>
        {{ serviceOnline === true ? 'Online' : serviceOnline === false ? 'Offline' : 'Verificando...' }}
      </v-chip>
      <v-btn color="deep-orange" variant="tonal" prepend-icon="mdi-refresh" @click="refreshData">
        Atualizar
      </v-btn>
    </div>

    <!-- Stats -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">TOTAL RESULTADOS</div>
            <div class="text-h4 font-weight-bold">{{ totalResults }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">ENVIADOS</div>
            <div class="text-h4 font-weight-bold text-success">{{ sentCount }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">FALHAS</div>
            <div class="text-h4 font-weight-bold text-error">{{ failedCount }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">PENDENTES</div>
            <div class="text-h4 font-weight-bold text-warning">{{ pendingCount }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Filter -->
    <v-card class="glass-card mb-4" variant="flat">
      <v-card-text class="d-flex align-center gap-4">
        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          item-title="title"
          item-value="value"
          label="Filtrar por Status"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="max-width: 250px"
          @update:model-value="fetchResults"
        ></v-select>
        <v-spacer></v-spacer>
        <v-btn variant="tonal" color="primary" prepend-icon="mdi-refresh" size="small" @click="fetchResults">
          Recarregar
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <v-card class="glass-card" variant="flat">
      <v-data-table
        :headers="headers"
        :items="results"
        :loading="loading"
        hover
      >
        <template #item.job_id="{ item }">
          <span class="text-caption font-weight-medium" style="font-family: monospace;">
            {{ item.job_id?.substring(0, 16) }}...
          </span>
        </template>

        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
            <v-icon start size="14">{{ statusIcon(item.status) }}</v-icon>
            {{ item.status }}
          </v-chip>
        </template>

        <template #item.attempts="{ item }">
          <v-chip size="x-small" variant="outlined">{{ item.attempts }}x</v-chip>
        </template>

        <template #item.last_error="{ item }">
          <span v-if="item.last_error" class="text-caption text-error" style="max-width: 250px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            {{ item.last_error }}
          </span>
          <span v-else class="text-caption text-medium-emphasis">—</span>
        </template>

        <template #item.actions="{ item }">
          <v-btn icon variant="text" size="small" color="primary" @click="viewDetail(item)">
            <v-icon icon="mdi-eye-outline"></v-icon>
            <v-tooltip activator="parent" location="top">Detalhes</v-tooltip>
          </v-btn>
        </template>

        <template #no-data>
          <div class="text-center py-8">
            <v-icon icon="mdi-inbox-outline" size="48" color="grey" class="mb-2"></v-icon>
            <p class="text-medium-emphasis">Nenhum resultado encontrado</p>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="700">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-6 pb-4">
          <v-icon icon="mdi-information-outline" class="mr-2" color="primary"></v-icon>
          <span class="text-h5 font-weight-bold">Detalhes do Resultado</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="detailDialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="px-6 py-2" v-if="selectedResult">
          <v-row>
            <v-col cols="12" md="6">
              <div class="text-overline">Job ID</div>
              <div class="text-body-2 font-weight-medium" style="font-family: monospace; word-break: break-all;">{{ selectedResult.job_id }}</div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-overline">Status</div>
              <v-chip :color="statusColor(selectedResult.status)" size="small" variant="tonal">
                <v-icon start size="14">{{ statusIcon(selectedResult.status) }}</v-icon>
                {{ selectedResult.status }}
              </v-chip>
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-overline">Tentativas</div>
              <div class="text-body-2 font-weight-bold">{{ selectedResult.attempts }}</div>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div v-if="selectedResult.last_error">
            <div class="text-overline mb-1">Último Erro</div>
            <v-alert type="error" variant="tonal" density="compact" class="mb-3">
              {{ selectedResult.last_error }}
            </v-alert>
          </div>

          <v-row v-if="selectedResult.created_at || selectedResult.updated_at || selectedResult.sent_at">
            <v-col cols="12" md="4" v-if="selectedResult.created_at">
              <div class="text-overline">Criado em</div>
              <div class="text-caption">{{ new Date(selectedResult.created_at).toLocaleString('pt-BR') }}</div>
            </v-col>
            <v-col cols="12" md="4" v-if="selectedResult.updated_at">
              <div class="text-overline">Atualizado em</div>
              <div class="text-caption">{{ new Date(selectedResult.updated_at).toLocaleString('pt-BR') }}</div>
            </v-col>
            <v-col cols="12" md="4" v-if="selectedResult.sent_at">
              <div class="text-overline">Enviado em</div>
              <div class="text-caption">{{ new Date(selectedResult.sent_at).toLocaleString('pt-BR') }}</div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      location="top"
      :timeout="3000"
    >
      {{ snackbar.text }}
      <template v-slot:actions>
        <v-btn variant="text" @click="snackbar.show = false">Fechar</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<style scoped>
.egress-container {
  max-width: 1400px;
  margin: 0 auto;
}
.glass-card {
  background: rgba(var(--v-theme-surface), 0.7) !important;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(var(--v-border-color), 0.1);
}
.gap-2 {
  gap: 8px;
}
.gap-4 {
  gap: 16px;
}
</style>
