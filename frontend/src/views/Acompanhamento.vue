<template>
  <div class="tracking-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-chart-timeline-variant</v-icon>
        </div>
        <div class="header-text">
          <h1>Acompanhamento e Rastreio</h1>
          <p>Monitore requisições, status dos jobs e webhooks processados</p>
        </div>
      </div>
      <v-btn color="primary" @click="fetchData" :loading="loading" prepend-icon="mdi-refresh" elevation="3">
        Atualizar
      </v-btn>
    </div>

    <!-- Charts Section -->
    <v-row class="mb-6">
      <v-col cols="12" md="6">
        <v-card class="glass-card h-100">
          <v-card-text class="pa-6">
            <h3 class="text-subtitle-1 font-weight-medium text-white mb-4 d-flex align-center">
              <v-icon class="mr-2" size="20" color="primary">mdi-chart-donut</v-icon>
              Status dos Jobs Processados
            </h3>
            <template v-if="statsLoading">
              <div class="d-flex justify-center py-12">
                <v-progress-circular indeterminate color="primary"></v-progress-circular>
              </div>
            </template>
            <template v-else-if="statusChartSeries.length > 0">
              <apexchart type="donut" width="100%" height="280" :options="statusChartOptions" :series="statusChartSeries" id="statusChart"></apexchart>
            </template>
            <template v-else>
              <div class="text-center py-12 text-medium-emphasis">Nenhum dado encontrado</div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
      
      <v-col cols="12" md="6">
        <v-card class="glass-card h-100">
          <v-card-text class="pa-6">
            <h3 class="text-subtitle-1 font-weight-medium text-white mb-4 d-flex align-center">
              <v-icon class="mr-2" size="20" color="info">mdi-chart-bar</v-icon>
              Top 5 Webhooks Processados
            </h3>
            <template v-if="statsLoading">
              <div class="d-flex justify-center py-12">
                <v-progress-circular indeterminate color="primary"></v-progress-circular>
              </div>
            </template>
            <template v-else-if="pathChartSeries[0].data.length > 0">
              <apexchart type="bar" height="280" :options="pathChartOptions" :series="pathChartSeries" id="pathChart"></apexchart>
            </template>
            <template v-else>
              <div class="text-center py-12 text-medium-emphasis">Nenhum dado encontrado</div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Data Table -->
    <v-card class="glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-history</v-icon>
        <span class="text-white font-weight-medium">Histórico de Webhooks</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="searchPath"
          prepend-inner-icon="mdi-magnify"
          placeholder="Buscar por Path..."
          variant="outlined"
          density="compact"
          hide-details
          class="mr-3"
          style="max-width: 260px"
          @keyup.enter="fetchLogs"
        ></v-text-field>
        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          label="Status"
          variant="outlined"
          density="compact"
          hide-details
          style="max-width: 180px"
          clearable
          @update:model-value="fetchLogs"
        ></v-select>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="logs"
        :loading="loading"
        :items-per-page="itemsPerPage"
        :server-items-length="totalItems"
        v-model:page="page"
        @update:options="handleOptionsUpdate"
        hover
        class="bg-transparent"
      >
        <template v-slot:item.created_at="{ item }">
          <span class="text-body-2">{{ formatDate(item.created_at) }}</span>
        </template>
        
        <template v-slot:item.status="{ item }">
          <v-chip :color="getStatusColor(item.status)" size="small" variant="tonal">
            <v-icon start size="12">{{ getStatusIcon(item.status) }}</v-icon>
            {{ item.status.toUpperCase() }}
          </v-chip>
        </template>
        
        <template v-slot:item.duration_ms="{ item }">
          <span v-if="item.duration_ms" class="text-body-2">
            <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
            {{ item.duration_ms }} ms
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-eye" @click="openJobDetails(item)">
            Abrir Job
          </v-btn>
        </template>
      </v-data-table>
    </v-card>

    <!-- Job Details Dialog -->
    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card v-if="selectedJob">
        <v-card-title class="bg-primary text-white d-flex align-center px-6 py-4">
          <v-icon class="mr-2" color="white">mdi-identifier</v-icon>
          <span class="text-body-1 font-weight-bold">Job: {{ selectedJob.job_id }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" color="white"></v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-row class="mb-4">
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Path do Webhook</div>
              <v-chip variant="outlined" color="info" size="small">{{ selectedJob.webhook_path }}</v-chip>
            </v-col>
            <v-col cols="12" sm="3">
              <div class="text-caption text-medium-emphasis mb-1">Status</div>
              <v-chip :color="getStatusColor(selectedJob.status)" size="small" variant="tonal">
                {{ selectedJob.status.toUpperCase() }}
              </v-chip>
            </v-col>
            <v-col cols="12" sm="3">
              <div class="text-caption text-medium-emphasis mb-1">Duração</div>
              <span class="font-weight-medium">{{ selectedJob.duration_ms ? selectedJob.duration_ms + ' ms' : '—' }}</span>
            </v-col>
          </v-row>

          <v-divider class="mb-4"></v-divider>

          <!-- Request -->
          <div class="d-flex align-center justify-space-between mb-2">
            <h3 class="text-subtitle-2 font-weight-bold text-primary">Payload de Entrada (Request)</h3>
            <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.request_data)"></v-btn>
          </div>
          <v-sheet class="pa-4 rounded-lg overflow-auto code-sheet mb-4" max-height="250">
            <pre class="text-caption">{{ formatJSON(selectedJob.request_data) }}</pre>
          </v-sheet>

          <!-- Response -->
          <div class="d-flex align-center justify-space-between mb-2">
            <h3 class="text-subtitle-2 font-weight-bold" :class="selectedJob.status === 'failed' ? 'text-error' : 'text-success'">Payload de Saída (Response)</h3>
            <v-btn v-if="selectedJob.response_data || selectedJob.error_message" size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.response_data || selectedJob.error_message)"></v-btn>
          </div>
          <v-sheet v-if="selectedJob.response_data" class="pa-4 rounded-lg overflow-auto code-sheet" max-height="250">
            <pre class="text-caption">{{ formatJSON(selectedJob.response_data) }}</pre>
          </v-sheet>
          <v-alert v-else-if="selectedJob.error_message" type="error" variant="tonal" class="rounded-lg">
            <pre style="white-space: pre-wrap; font-family: monospace;" class="text-caption">{{ selectedJob.error_message }}</pre>
          </v-alert>
          <div v-else class="text-medium-emphasis font-italic text-body-2">Sem resposta gerada.</div>

          <!-- Test Result (Internal Mode) -->
          <div v-if="testResult" class="mt-6">
            <v-divider class="mb-4"></v-divider>
            <div class="d-flex align-center justify-space-between mb-2">
              <h3 class="text-subtitle-2 font-weight-bold text-info">
                <v-icon size="small" class="mr-1">mdi-flask</v-icon>
                Resultado do Teste (Interno)
              </h3>
              <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(testResult)"></v-btn>
            </div>
            <v-sheet class="pa-4 rounded-lg overflow-auto code-sheet" max-height="300" style="border: 1px solid rgba(0, 209, 255, 0.3);">
              <pre class="text-caption" style="color: #00D1FF;">{{ formatJSON(testResult) }}</pre>
            </v-sheet>
          </div>
          <!-- Human Response Input -->
          <div v-if="showHumanInput" class="mt-4">
            <v-divider class="mb-4"></v-divider>
            <h3 class="text-subtitle-2 font-weight-bold text-warning mb-2">
              <v-icon size="small" class="mr-1">mdi-account-voice</v-icon>
              Human Response
            </h3>
            <v-textarea
              v-model="humanText"
              variant="outlined"
              placeholder="Digite a mensagem que será enviada como resposta..."
              rows="3"
              auto-grow
              hide-details
            ></v-textarea>
            <div class="d-flex justify-end mt-2 gap-2">
              <v-btn size="small" variant="text" @click="showHumanInput = false; humanText = ''">Cancelar</v-btn>
              <v-btn
                size="small"
                color="warning"
                variant="flat"
                prepend-icon="mdi-send"
                :loading="sendingHuman"
                :disabled="!humanText.trim()"
                @click="sendHumanResponse"
              >
                Enviar Resposta
              </v-btn>
            </div>
          </div>
        </v-card-text>
        
        <v-card-actions class="pa-4 border-t d-flex flex-wrap gap-2">
          <v-btn
            color="info"
            variant="tonal"
            prepend-icon="mdi-flask"
            :loading="testingJob"
            @click="testCurrentJob"
          >
            Testar Job
          </v-btn>
          <v-btn
            v-if="selectedJob.callback_url && selectedJob.response_data"
            color="success"
            variant="tonal"
            prepend-icon="mdi-send-variant"
            :loading="resendingJob"
            @click="resendCurrentJob"
          >
            Reenviar
          </v-btn>
          <v-btn
            v-if="selectedJob.callback_url"
            color="warning"
            variant="tonal"
            prepend-icon="mdi-account-voice"
            @click="showHumanInput = !showHumanInput"
          >
            Human Response
          </v-btn>
          <div class="text-caption text-medium-emphasis ms-2 me-auto align-self-center">
            (Roda internamente, não aciona webhook de saída)
          </div>
          <v-btn
            v-if="selectedJob.status === 'in_progress' || selectedJob.status === 'queued'"
            color="error"
            variant="flat"
            prepend-icon="mdi-stop-circle-outline"
            :loading="abortingJob"
            @click="abortCurrentJob"
          >
            Abortar Job
          </v-btn>
          <v-btn color="primary" variant="text" @click="dialog = false" :disabled="testingJob || abortingJob || resendingJob || sendingHuman">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axiosInstance from '@/plugins/axios'
import VueApexCharts from 'vue3-apexcharts'
import ApexCharts from 'apexcharts'

const apexchart = VueApexCharts

// Loading
const loading = ref(false)
const statsLoading = ref(false)

// Charts — Dark themed
const statusChartSeries = ref([])
const statusChartOptions = ref({
  chart: {
    type: 'donut',
    fontFamily: 'Inter, sans-serif',
    background: 'transparent',
    events: {
      legendClick: (chartContext, seriesIndex, config) => {
        chartContext.hideSeries(config.globals.colors[seriesIndex])
      }
    }
  },
  labels: [],
  colors: ['#00FC8B', '#FF0055', '#FFB800', '#00D1FF'],
  plotOptions: { pie: { donut: { size: '68%', labels: { show: true, total: { show: true, label: 'Total', color: 'rgba(255,255,255,0.6)', formatter: (w) => w.globals.seriesTotals.reduce((a, b) => a + b, 0) } } } } },
  dataLabels: { enabled: false },
  legend: { position: 'bottom', labels: { colors: 'rgba(255,255,255,0.6)' } },
  stroke: { width: 2, colors: ['#070a13'] },
      tooltip: { theme: 'dark', y: { formatter: (val, opts) => `${val} (${((val / opts.config.series.reduce((a, b) => a + b, 0)) * 100).toFixed(1)}%)` } },
  responsive: [{
    breakpoint: 480,
    options: {
      chart: { height: 220 },
      legend: { position: 'right' }
    }
  }]
})

const pathChartSeries = ref([{ name: 'Requisições', data: [] }])
const pathChartOptions = ref({
  chart: {
    type: 'bar',
    toolbar: { show: true, tools: { download: true } },
    fontFamily: 'Inter, sans-serif',
    background: 'transparent'
  },
  plotOptions: { bar: { horizontal: true, borderRadius: 6, barHeight: '60%', dataLabels: { position: 'top' } } },
  dataLabels: { enabled: true, style: { colors: ['#fff'] }, formatter: (val) => `${val}` },
  xaxis: { categories: [], labels: { style: { colors: 'rgba(255,255,255,0.5)' } } },
  yaxis: { labels: { style: { colors: 'rgba(255,255,255,0.7)' } } },
  grid: { borderColor: 'rgba(255,255,255,0.04)' },
  colors: ['#9D4EDD'],
  tooltip: { theme: 'dark' },
  responsive: [{
    breakpoint: 768,
    options: {
      chart: { height: 240 },
      yaxis: { labels: { rotate: -90 } }
    }
  }]
})

// Data Table
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
  { title: 'Tempo', key: 'duration_ms', sortable: false },
  { title: 'Ação', key: 'actions', sortable: false, align: 'center' }
]

const dialog = ref(false)
const selectedJob = ref(null)
const snackbar = ref({ show: false, text: '', color: 'success' })

function exportDonut() {
  const chart = ApexCharts.getChartByID('statusChart')
  if (chart) {
    chart.exportToPng().then(url => {
      const link = document.createElement('a')
      link.download = 'status-chart.png'
      link.href = url
      link.click()
      showSnackbar('Gráfico exportado!', 'success')
    }).catch(() => showSnackbar('Erro ao exportar', 'error'))
  }
}

// Test mode references
const testingJob = ref(false)
const testResult = ref(null)

// Abort state
const abortingJob = ref(false)

// Resend state
const resendingJob = ref(false)

// Human Response state
const showHumanInput = ref(false)
const humanText = ref('')
const sendingHuman = ref(false)

const fetchStats = async () => {
  statsLoading.value = true
  try {
    const { data } = await axiosInstance.get('/tracking/stats')
    const statusMap = { 'completed': '#00FC8B', 'failed': '#FF0055', 'queued': '#FFB800', 'in_progress': '#00D1FF' }
    if (data.by_status?.length > 0) {
      statusChartSeries.value = data.by_status.map(i => i.count)
      statusChartOptions.value = { ...statusChartOptions.value, labels: data.by_status.map(i => i.status.toUpperCase()), colors: data.by_status.map(i => statusMap[i.status] || '#666') }
    } else { statusChartSeries.value = [] }
    if (data.by_path?.length > 0) {
      pathChartSeries.value = [{ name: 'Requisições', data: data.by_path.map(i => i.count) }]
      pathChartOptions.value = { ...pathChartOptions.value, xaxis: { ...pathChartOptions.value.xaxis, categories: data.by_path.map(i => i.path) } }
    } else { pathChartSeries.value = [{ name: 'Requisições', data: [] }] }
  } catch (error) {
    showSnackbar('Erro ao carregar estatísticas', 'error')
  } finally { statsLoading.value = false }
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
    showSnackbar('Erro ao carregar logs', 'error')
  } finally { loading.value = false }
}

const fetchData = () => { fetchStats(); fetchLogs() }
const handleOptionsUpdate = ({ page: np, itemsPerPage: nip }) => { page.value = np; itemsPerPage.value = nip; fetchLogs() }
const openJobDetails = (job) => { 
  selectedJob.value = job; 
  testResult.value = null; // reset specific dialog tests 
  showHumanInput.value = false;
  humanText.value = '';
  dialog.value = true 
}

const testCurrentJob = async () => {
  if (!selectedJob.value) return;
  testingJob.value = true;
  testResult.value = null;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/test`);
    showSnackbar(`Job testado em ${data.processing_time_ms}ms`, 'success');
    testResult.value = data.test_response;
  } catch (error) {
    console.error("Erro no teste:", error);
    showSnackbar('Falha ao testar job internamente', 'error');
    if (error.response?.data?.detail) {
      testResult.value = { error: error.response.data.detail };
    }
  } finally {
    testingJob.value = false;
  }
}

const abortCurrentJob = async () => {
  if (!selectedJob.value) return;
  abortingJob.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/abort`);
    showSnackbar(data.message || 'Sinal de cancelamento enviado!', 'warning');
    // We optionally update local state to reflect it's aborted somewhat immediately
    selectedJob.value.status = 'failed';
    selectedJob.value.error_message = 'Aguardando cancelamento / Aborted by user';
  } catch (error) {
    console.error("Erro ao cancelar:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao abortar job', 'error');
  } finally {
    abortingJob.value = false;
  }
}

const resendCurrentJob = async () => {
  if (!selectedJob.value) return;
  resendingJob.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/resend`);
    showSnackbar(data.message || 'Response reenviado com sucesso!', 'success');
  } catch (error) {
    console.error("Erro ao reenviar:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao reenviar response', 'error');
  } finally {
    resendingJob.value = false;
  }
}

const sendHumanResponse = async () => {
  if (!selectedJob.value || !humanText.value.trim()) return;
  sendingHuman.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/human-response`, { human_text: humanText.value });
    showSnackbar(data.message || 'Human response enviada com sucesso!', 'success');
    showHumanInput.value = false;
    // Update local response_data to reflect the change
    if (selectedJob.value.response_data && 'result' in selectedJob.value.response_data) {
      selectedJob.value.response_data.result = humanText.value;
    }
    humanText.value = '';
  } catch (error) {
    console.error("Erro ao enviar human response:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao enviar human response', 'error');
  } finally {
    sendingHuman.value = false;
  }
}

const getStatusColor = (status) => ({ 'completed': 'success', 'failed': 'error', 'queued': 'warning', 'in_progress': 'info' }[status] || 'grey')
const getStatusIcon = (status) => ({ 'completed': 'mdi-check', 'failed': 'mdi-close', 'queued': 'mdi-clock', 'in_progress': 'mdi-play' }[status] || 'mdi-help')
const formatDate = (d) => d ? new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
const formatJSON = (obj) => { try { return JSON.stringify(obj, null, 2) } catch { return obj } }

const copyToClipboard = (data) => {
  const text = typeof data === 'object' ? JSON.stringify(data, null, 2) : data
  navigator.clipboard.writeText(text).then(() => showSnackbar('Copiado!', 'success')).catch(() => showSnackbar('Erro ao copiar', 'error'))
}

const showSnackbar = (text, color = 'success') => { snackbar.value = { show: true, text, color } }

onMounted(() => { fetchData() })
</script>

<style scoped>
.tracking-page {
  animation: pageEnter 0.45s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.code-sheet {
  background: rgba(5, 8, 16, 0.8) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.8);
}

.code-sheet pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
</style>
