<template>
  <v-container fluid>
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h2 class="text-h4 font-weight-bold text-primary mb-1">Acompanhamento e Rastreio</h2>
        <p class="text-subtitle-1 text-medium-emphasis">Monitore o volume de requisições, status dos jobs e rastreie os dados e webhooks processados.</p>
      </div>
      <v-btn color="primary" @click="fetchData" :loading="loading" prepend-icon="mdi-refresh">
        Atualizar
      </v-btn>
    </div>

    <!-- Charts Section -->
    <v-row class="mb-6">
      <v-col cols="12" md="6">
        <v-card elevation="2" class="h-100 rounded-lg">
          <v-card-title class="font-weight-medium">Status dos Jobs Processados</v-card-title>
          <v-card-text class="d-flex justify-center flex-column align-center">
            <template v-if="statsLoading">
              <v-progress-circular indeterminate color="primary" class="my-6"></v-progress-circular>
            </template>
            <template v-else-if="statusChartSeries.length > 0">
              <apexchart type="donut" width="100%" height="300" :options="statusChartOptions" :series="statusChartSeries"></apexchart>
            </template>
            <template v-else>
              <div class="text-center my-10 text-medium-emphasis">Nenhum dado encontrado</div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
      
      <v-col cols="12" md="6">
        <v-card elevation="2" class="h-100 rounded-lg">
          <v-card-title class="font-weight-medium">Top 5 Webhooks Processados</v-card-title>
          <v-card-text>
            <template v-if="statsLoading">
              <v-progress-circular indeterminate color="primary" class="my-6 mx-auto d-block"></v-progress-circular>
            </template>
            <template v-else-if="pathChartSeries[0].data.length > 0">
              <apexchart type="bar" height="300" :options="pathChartOptions" :series="pathChartSeries"></apexchart>
            </template>
            <template v-else>
              <div class="text-center my-10 text-medium-emphasis">Nenhum dado encontrado</div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Data Table Section -->
    <v-card elevation="2" class="rounded-lg">
      <v-card-title class="d-flex align-center py-4 px-6 border-b">
        <span class="font-weight-medium">Histórico de Webhooks</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="searchPath"
          append-inner-icon="mdi-magnify"
          label="Buscar por Path"
          single-line
          hide-details
          density="compact"
          class="mr-4"
          style="max-width: 300px"
          @keyup.enter="fetchLogs"
        ></v-text-field>
        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          label="Status"
          dense
          outlined
          hide-details
          density="compact"
          style="max-width: 200px"
          clearable
          @update:model-value="fetchLogs"
        ></v-select>
      </v-card-title>
      
      <v-data-table
        :headers="headers"
        :items="logs"
        :loading="loading"
        :items-per-page="itemsPerPage"
        :server-items-length="totalItems"
        v-model:page="page"
        @update:options="handleOptionsUpdate"
        hover
      >
        <template v-slot:item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>
        
        <template v-slot:item.status="{ item }">
          <v-chip :color="getStatusColor(item.status)" size="small" label>
            {{ item.status.toUpperCase() }}
          </v-chip>
        </template>
        
        <template v-slot:item.duration_ms="{ item }">
          <span v-if="item.duration_ms">{{ item.duration_ms }} ms</span>
          <span v-else class="text-medium-emphasis">-</span>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            prepend-icon="mdi-eye"
            @click="openJobDetails(item)"
          >
            Abrir Job
          </v-btn>
        </template>
      </v-data-table>
    </v-card>

    <!-- Job Details Dialog -->
    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card v-if="selectedJob">
        <v-card-title class="bg-primary text-white d-flex align-center">
          <span class="text-h6">Job: {{ selectedJob.job_id }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false"></v-btn>
        </v-card-title>
        
        <v-card-text class="pt-4 pb-6" style="background-color: #f8fafc;">
          <v-row>
            <v-col cols="12" sm="6">
              <div class="text-subtitle-2 text-medium-emphasis mb-1">Path do Webhook</div>
              <div class="text-body-1 font-weight-medium mb-4">{{ selectedJob.webhook_path }}</div>
              
              <div class="text-subtitle-2 text-medium-emphasis mb-1">Data e Hora</div>
              <div class="text-body-1 mb-4">{{ formatDate(selectedJob.created_at) }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-subtitle-2 text-medium-emphasis mb-1">Status</div>
              <div class="mb-4">
                <v-chip :color="getStatusColor(selectedJob.status)" size="small" label class="mr-2">
                  {{ selectedJob.status.toUpperCase() }}
                </v-chip>
                <span v-if="selectedJob.duration_ms" class="text-caption">({{ selectedJob.duration_ms }} ms)</span>
              </div>
            </v-col>
          </v-row>

          <v-divider class="mb-4"></v-divider>

          <v-row>
            <v-col cols="12">
              <div class="d-flex align-center justify-space-between mb-2">
                <h3 class="text-subtitle-1 font-weight-bold text-primary">Payload de Entrada (Request)</h3>
                <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.request_data)"></v-btn>
              </div>
              <v-sheet class="pa-4 bg-grey-darken-4 rounded-lg overflow-auto" max-height="300">
                <pre class="text-white text-caption">{{ formatJSON(selectedJob.request_data) }}</pre>
              </v-sheet>
            </v-col>
            
            <v-col cols="12" class="mt-4">
              <div class="d-flex align-center justify-space-between mb-2">
                <h3 class="text-subtitle-1 font-weight-bold" :class="selectedJob.status === 'failed' ? 'text-error' : 'text-success'">Payload de Saída (Response) / Erro</h3>
                <v-btn v-if="selectedJob.response_data || selectedJob.error_message" size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.response_data || selectedJob.error_message)"></v-btn>
              </div>
              <v-sheet v-if="selectedJob.response_data" class="pa-4 bg-grey-darken-4 rounded-lg overflow-auto" max-height="300">
                <pre class="text-white text-caption">{{ formatJSON(selectedJob.response_data) }}</pre>
              </v-sheet>
              <v-alert v-else-if="selectedJob.error_message" type="error" variant="tonal" class="rounded-lg">
                <pre style="white-space: pre-wrap; font-family: monospace;" class="text-caption">{{ selectedJob.error_message }}</pre>
              </v-alert>
              <div v-else class="text-medium-emphasis font-italic">Sem resposta gerada (ainda processando ou ignorado).</div>
            </v-col>
          </v-row>
        </v-card-text>
        
        <v-card-actions class="pa-4 border-t">
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="text" @click="dialog = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axiosInstance from '@/plugins/axios'
import VueApexCharts from 'vue3-apexcharts'

// Registration for components
const apexchart = VueApexCharts

// --- Loading States ---
const loading = ref(false)
const statsLoading = ref(false)

// --- Charts Data ---
const statusChartSeries = ref([])
const statusChartOptions = ref({
  chart: { type: 'donut', fontFamily: 'Inter, sans-serif' },
  labels: [],
  colors: ['#4CAF50', '#FF5252', '#FFC107', '#2196F3'],
  plotOptions: {
    pie: {
      donut: { size: '65%' }
    }
  },
  dataLabels: { enabled: true },
  legend: { position: 'bottom' }
})

const pathChartSeries = ref([{ name: 'Requisições', data: [] }])
const pathChartOptions = ref({
  chart: { type: 'bar', toolbar: { show: false }, fontFamily: 'Inter, sans-serif' },
  plotOptions: {
    bar: { horizontal: true, borderRadius: 4 }
  },
  dataLabels: { enabled: true },
  xaxis: { categories: [] },
  colors: ['#673ab7']
})

// --- Data Table ---
const logs = ref([])
const totalItems = ref(0)
const page = ref(1)
const itemsPerPage = ref(20)
const searchPath = ref('')
const statusFilter = ref(null)
const statusOptions = ['completed', 'failed', 'queued', 'in_progress']

const headers = [
  { title: 'Data/Hora', key: 'created_at', sortable: false },
  { title: 'Webhook Path', key: 'webhook_path', sortable: false },
  { title: 'Status', key: 'status', sortable: false },
  { title: 'Tempo (ms)', key: 'duration_ms', sortable: false },
  { title: 'Ação', key: 'actions', sortable: false, align: 'center' }
]

// --- Details Dialog ---
const dialog = ref(false)
const selectedJob = ref(null)

const snackbar = ref({ show: false, text: '', color: 'success' })

// --- Functions ---
const fetchStats = async () => {
  statsLoading.value = true
  try {
    const { data } = await axiosInstance.get('/tracking/stats')
    
    // Status Donut Chart mapped
    const statusMap = { 'completed': '#4CAF50', 'failed': '#FF5252', 'queued': '#FFC107', 'in_progress': '#2196F3' }
    if (data.by_status && data.by_status.length > 0) {
      statusChartSeries.value = data.by_status.map(i => i.count)
      statusChartOptions.value = {
        ...statusChartOptions.value,
        labels: data.by_status.map(i => i.status.toUpperCase()),
        colors: data.by_status.map(i => statusMap[i.status] || '#9E9E9E')
      }
    } else {
      statusChartSeries.value = []
    }
    
    // Path Bar Chart mapped
    if (data.by_path && data.by_path.length > 0) {
      pathChartSeries.value = [{
        name: 'Requisições',
        data: data.by_path.map(i => i.count)
      }]
      pathChartOptions.value = {
        ...pathChartOptions.value,
        xaxis: { categories: data.by_path.map(i => i.path) }
      }
    } else {
      pathChartSeries.value = [{ name: 'Requisições', data: [] }]
    }
    
  } catch (error) {
    showSnackbar('Erro ao carregar estatísticas dashboard', 'error')
    console.error(error)
  } finally {
    statsLoading.value = false
  }
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const skip = (page.value - 1) * itemsPerPage.value
    let url = `/tracking/logs?skip=${skip}&limit=${itemsPerPage.value}`
    if (statusFilter.value) url += `&status=${statusFilter.value}`
    if (searchPath.value) url += `&path=${searchPath.value}`
    
    const { data } = await axiosInstance.get(url)
    logs.value = data.items
    totalItems.value = data.total
  } catch (error) {
    showSnackbar('Erro ao carregar lista de jobs', 'error')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const fetchData = () => {
  fetchStats()
  fetchLogs()
}

const handleOptionsUpdate = ({ page: np, itemsPerPage: nip }) => {
  page.value = np
  itemsPerPage.value = nip
  fetchLogs()
}

const openJobDetails = (job) => {
  selectedJob.value = job
  dialog.value = true
}

// --- Utils ---
const getStatusColor = (status) => {
  const map = {
    'completed': 'success',
    'failed': 'error',
    'queued': 'warning',
    'in_progress': 'info'
  }
  return map[status] || 'grey'
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

const formatJSON = (obj) => {
  if (!obj) return ''
  try {
    return JSON.stringify(obj, null, 2)
  } catch (e) {
    return obj
  }
}

const copyToClipboard = (data) => {
  let text = typeof data === 'object' ? JSON.stringify(data, null, 2) : data;
  navigator.clipboard.writeText(text).then(() => {
    showSnackbar('Copiado para a área de transferência', 'success')
  }).catch(() => {
    showSnackbar('Erro ao copiar', 'error')
  })
}

const showSnackbar = (text, color) => {
  snackbar.value = { show: true, text, color }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
pre {
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
