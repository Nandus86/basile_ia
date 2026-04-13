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
      <div class="d-flex align-center ga-3">
        <div class="d-flex align-center ga-1" v-if="sseConnected">
          <span class="sse-dot"></span>
          <span class="text-caption text-success">Tempo real ativo</span>
        </div>
        <div class="d-flex align-center ga-1" v-else>
          <span class="sse-dot sse-offline"></span>
          <span class="text-caption text-medium-emphasis">Desconectado</span>
        </div>
        <v-btn color="primary" @click="fetchData" :loading="loading" prepend-icon="mdi-refresh" elevation="3">
          Atualizar
        </v-btn>
      </div>
    </div>

    <!-- Tabs Header -->
    <v-tabs v-model="activeTab" color="primary" class="mb-6">
      <v-tab value="webhooks">Webhooks</v-tab>
      <v-tab value="disparador">Disparador</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <v-window-item value="webhooks">
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
        :items-per-page-options="itemsPerPageOptions"
        :server-items-length="totalItems"
        v-model:page="page"
        show-current-page
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
          <div class="d-flex ga-1 justify-center">
            <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-eye" @click="openJobDetails(item)">
              Abrir Job
            </v-btn>
            <v-btn
              v-if="getSessionId(item)"
              icon
              variant="text"
              size="small"
              color="info"
              @click="viewStmFromJob(item)"
            >
              <v-icon size="18">mdi-message-text-clock-outline</v-icon>
              <v-tooltip activator="parent" location="top">Ver STM (Conversa)</v-tooltip>
            </v-btn>
            <v-btn
              v-if="getSessionId(item)"
              icon
              variant="text"
              size="small"
              color="warning"
              @click="viewMtmFromJob(item)"
            >
              <v-icon size="18">mdi-database-clock-outline</v-icon>
              <v-tooltip activator="parent" location="top">Ver MTM (Histórico)</v-tooltip>
            </v-btn>
          </div>
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
          <!-- Agent Control Buttons -->
          <v-btn
            color="error"
            variant="tonal"
            prepend-icon="mdi-robot-off"
            :loading="pausingAgent"
            @click="pauseAgent(null)"
            size="small"
          >
            Desativar Agente
          </v-btn>
          <div class="d-flex align-center ga-1">
            <v-btn
              color="error"
              variant="tonal"
              prepend-icon="mdi-timer-off"
              :loading="pausingAgent"
              :disabled="!pauseMinutes"
              @click="pauseAgent(pauseMinutes)"
              size="small"
            >
              Desativar por
            </v-btn>
            <v-text-field
              v-model.number="pauseMinutes"
              type="number"
              density="compact"
              variant="outlined"
              hide-details
              style="max-width: 75px"
              placeholder="min"
            />
          </div>
          <v-btn
            color="success"
            variant="tonal"
            prepend-icon="mdi-robot"
            :loading="activatingAgent"
            @click="activateAgent"
            size="small"
          >
            Ativar Agente
          </v-btn>
          <v-btn
            v-if="getSessionId(selectedJob)"
            color="teal"
            variant="tonal"
            prepend-icon="mdi-account-check"
            :loading="unblockingBot"
            @click="unblockBot(getSessionId(selectedJob))"
            size="small"
          >
            Não é BOT
          </v-btn>
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
          <v-btn color="primary" variant="text" @click="dialog = false" :disabled="testingJob || abortingJob || resendingJob || sendingHuman || pausingAgent || activatingAgent">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- STM/MTM Messages Dialog -->
    <v-dialog v-model="memoryDialog" max-width="750" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important">
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" size="20" :color="memoryDialogType === 'stm' ? '#00D1FF' : '#FBBF24'">
            {{ memoryDialogType === 'stm' ? 'mdi-message-text-clock-outline' : 'mdi-database-clock-outline' }}
          </v-icon>
          <span class="text-subtitle-1 font-weight-bold text-white">{{ memoryDialogTitle }}</span>
          <v-spacer />
          <v-btn icon variant="text" size="small" @click="memoryDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider style="border-color: rgba(255,255,255,0.05)"></v-divider>
        <v-card-text class="pa-5" style="max-height: 550px; overflow-y: auto;">
          <div v-if="memoryDialogLoading" class="d-flex justify-center py-12">
            <v-progress-circular indeterminate color="primary" size="32"></v-progress-circular>
          </div>
          <div v-else-if="memoryMessages.length > 0" class="d-flex flex-column ga-3">
            <div
              v-for="(msg, idx) in memoryMessages"
              :key="idx"
              class="memory-bubble pa-3 rounded-lg"
              :class="getMemoryBubbleClass(msg.role)"
            >
              <div class="d-flex align-center mb-1">
                <v-icon size="14" class="mr-1" :color="getMemoryIconColor(msg.role)">
                  {{ getMemoryIcon(msg.role) }}
                </v-icon>
                <span class="text-caption font-weight-bold text-uppercase" style="opacity: 0.7">{{ msg.role }}</span>
                <span v-if="msg.created_at || msg.timestamp" class="text-caption ml-2" style="opacity: 0.4">
                  {{ formatDate(msg.created_at || msg.timestamp) }}
                </span>
              </div>
              <div class="text-body-2 text-white" style="white-space: pre-wrap; word-break: break-word;">{{ msg.content }}</div>
            </div>
          </div>
          <div v-else class="text-center pa-8 text-medium-emphasis">
            Nenhuma mensagem encontrada para esta sessão.
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
      </v-window-item>

      <v-window-item value="disparador">
        <v-row class="mb-6 mt-2">
          <v-col cols="12" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">ATIVAS / PAUSADAS</div><div class="text-h4 text-primary">{{ dispStats.active_campaigns }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">ENVIADAS HOJE</div><div class="text-h4 text-success">{{ dispStats.total_sent }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">COMPLETAS</div><div class="text-h4 text-info">{{ dispStats.completed_campaigns }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">FALHAS (DLQ)</div><div class="text-h4 text-error">{{ dispStats.total_failed }}</div></v-card-text></v-card>
          </v-col>
        </v-row>
        
        <div class="d-flex align-center mb-4">
            <h3 class="text-subtitle-1 font-weight-bold">Campanhas em Execução</h3>
            <v-spacer></v-spacer>
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" size="small" @click="fetchDisparadorData" :loading="dispLoading">Atualizar</v-btn>
        </div>

        <v-card class="glass-card">
          <v-data-table :headers="dispHeaders" :items="dispCampaigns" :loading="dispLoading" hover>
            <template #item.service_id="{ item }"><v-chip size="small" variant="outlined">{{ item.service_id }}</v-chip></template>
            <template #item.status="{ item }">
              <v-chip :color="item.status === 'running' ? 'success' : item.status === 'paused' ? 'warning' : 'info'" size="small">
                {{ item.status.toUpperCase() }}
              </v-chip>
            </template>
            <template #item.percent="{ item }">
              <div class="d-flex align-center w-100">
                <v-progress-linear :model-value="item.percent" color="primary" height="8" rounded></v-progress-linear>
                <span class="text-caption ml-2 min-w-[40px]">{{ item.percent }}%</span>
              </div>
            </template>
            <template #item.actions="{ item }">
               <v-btn size="small" variant="text" icon="mdi-magnify" color="primary" @click="openDispDetails(item)"></v-btn>
            </template>
          </v-data-table>
        </v-card>
        
        <v-dialog v-model="dispDialog" max-width="700">
          <v-card v-if="dispSelected" class="glass-card">
             <v-card-title class="pa-6 border-b">
                Campanha: {{ dispSelected.service_id }}
                <v-chip size="small" class="ml-2" :color="dispSelected.status === 'running' ? 'success' : dispSelected.status === 'paused' ? 'warning' : 'info'">{{ dispSelected.status.toUpperCase() }}</v-chip>
             </v-card-title>
             <v-card-text class="pa-6">
                <v-row>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Total</div><div class="text-h6">{{ dispSelected.total }}</div></v-col>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Enviados</div><div class="text-h6 text-success">{{ dispSelected.sent }}</div></v-col>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Falhas</div><div class="text-h6 text-error">{{ dispSelected.failed }}</div></v-col>
                </v-row>
                <div class="my-6">
                    <div class="text-caption mb-1">Progresso ({{ dispSelected.percent }}%)</div>
                    <v-progress-linear :model-value="dispSelected.percent" color="primary" height="12" rounded></v-progress-linear>
                </div>
                <div v-if="dispReport">
                   <v-divider class="mb-4"></v-divider>
                   <div class="text-subtitle-2 mb-2 text-info">Relatório Final Disponível</div>
                   <div class="d-flex flex-wrap gap-4 mb-4">
                     <v-chip variant="outlined" color="success">Taxa Sucesso: {{ dispReport.success_rate }}%</v-chip>
                     <v-chip variant="outlined" color="error">DLQ: {{ dispReport.dlq_count }} contatos</v-chip>
                   </div>
                </div>
             </v-card-text>
             <v-card-actions class="pa-4 border-t">
                <v-btn v-if="dispSelected.status === 'running'" color="warning" prepend-icon="mdi-pause" variant="flat" @click="dispAction('pause')" :loading="dispActionLoading">Pausar</v-btn>
                <v-btn v-if="dispSelected.status === 'paused'" color="success" prepend-icon="mdi-play" variant="flat" @click="dispAction('resume')" :loading="dispActionLoading">Retomar</v-btn>
                <v-btn v-if="dispReport && dispReport.dlq_count > 0" color="error" prepend-icon="mdi-refresh" variant="flat" @click="dispAction('retry-dlq')" :loading="dispActionLoading">Reprocessar DLQ</v-btn>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="dispDialog = false">Fechar</v-btn>
             </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>
    </v-window>
    
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axiosInstance from '@/plugins/axios'
import VueApexCharts from 'vue3-apexcharts'
import ApexCharts from 'apexcharts'

const apexchart = VueApexCharts

const activeTab = ref('webhooks')

const dispStats = ref({ total_campaigns: 0, active_campaigns: 0, completed_campaigns: 0, total_sent: 0, total_failed: 0 })
const dispCampaigns = ref([])
const dispLoading = ref(false)
const dispDialog = ref(false)
const dispSelected = ref(null)
const dispReport = ref(null)
const dispActionLoading = ref(false)

const dispHeaders = [
  { title: 'SERVICE ID', key: 'service_id' },
  { title: 'STATUS', key: 'status' },
  { title: 'TOTAL', key: 'total' },
  { title: 'ENVIADAS', key: 'sent' },
  { title: 'FALHAS', key: 'failed' },
  { title: 'PROGRESSO', key: 'percent' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const fetchDisparadorData = async () => {
    dispLoading.value = true
    try {
       const [resStats, resCamp] = await Promise.all([
           axiosInstance.get('/disparador/dashboard/stats'),
           axiosInstance.get('/disparador/dashboard/campaigns')
       ])
       dispStats.value = resStats.data
       dispCampaigns.value = resCamp.data
    } catch (e) {
       console.error(e)
    } finally {
       dispLoading.value = false
    }
}

const openDispDetails = async (item) => {
    dispSelected.value = item
    dispReport.value = null
    dispDialog.value = true
    if (item.status === 'completed') {
        try {
            const res = await axiosInstance.get(`/disparador/dashboard/campaigns/${item.service_id}/report`)
            dispReport.value = res.data
        } catch (e) {}
    }
}

const dispAction = async (action) => {
    if (!dispSelected.value) return
    dispActionLoading.value = true
    try {
        await axiosInstance.post(`/disparador/campaigns/${dispSelected.value.service_id}/${action}`)
        if (action === 'retry-dlq') {
            dispReport.value.dlq_count = 0
            snackbar.value = { show: true, text: 'Contatos falhados reenfileirados.', color: 'success' }
        }
        await fetchDisparadorData()
        if (action !== 'retry-dlq') {
           const updated = dispCampaigns.value.find(c => c.service_id === dispSelected.value.service_id)
           if (updated) dispSelected.value = updated
        }
    } catch (e) {
        snackbar.value = { show: true, text: 'Erro ao executar ação.', color: 'error' }
    } finally {
        dispActionLoading.value = false
    }
}

// Loading
const loading = ref(false)
const statsLoading = ref(false)

// SSE
const sseConnected = ref(false)

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
const itemsPerPage = ref(50)
const itemsPerPageOptions = [
  { value: 20, title: '20' },
  { value: 50, title: '50' },
  { value: 100, title: '100' },
  { value: 200, title: '200' },
]
const searchPath = ref('')
const statusFilter = ref(null)
const statusOptions = ['completed', 'failed', 'queued', 'in_progress', 'buffered', 'paused']

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

// Agent Control state
const pauseMinutes = ref(null)
const pausingAgent = ref(false)
const activatingAgent = ref(false)
const unblockingBot = ref(false)

// STM/MTM Memory Dialog
const memoryDialog = ref(false)
const memoryDialogType = ref('stm')
const memoryDialogTitle = ref('')
const memoryDialogLoading = ref(false)
const memoryMessages = ref([])

// ── SSE Connection (fetch-based for auth header support) ──
let sseAbortController = null

function connectSSE() {
  disconnectSSE()
  sseAbortController = new AbortController()

  const baseUrl = axiosInstance.defaults?.baseURL || '/api'
  const token = localStorage.getItem('accessToken')
  const headers = { 'Accept': 'text/event-stream' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const doConnect = async () => {
    try {
      const res = await fetch(`${baseUrl}/tracking/stream`, {
        headers,
        signal: sseAbortController.signal,
      })

      if (!res.ok) {
        sseConnected.value = false
        scheduleReconnect()
        return
      }

      sseConnected.value = true
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          try {
            const payload = JSON.parse(raw)
            handleSSEEvent(payload)
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        sseConnected.value = false
        scheduleReconnect()
      }
    }
  }

  doConnect()
}

function scheduleReconnect() {
  setTimeout(() => {
    if (!sseAbortController?.signal.aborted) {
      connectSSE()
    }
  }, 5000)
}

function handleSSEEvent(payload) {
  const { event, data: jobData } = payload
  if (!jobData) return

  if (event === 'new_job') {
    const idx = logs.value.findIndex(j => j.job_id === jobData.job_id)
    if (idx !== -1) {
      logs.value[idx] = { ...logs.value[idx], ...jobData }
    } else {
      logs.value.unshift(jobData)
      totalItems.value += 1
    }
  } else if (event === 'job_updated') {
    const idx = logs.value.findIndex(j => j.job_id === jobData.job_id)
    if (idx !== -1) {
      logs.value[idx] = { ...logs.value[idx], ...jobData }
    } else {
      logs.value.unshift(jobData)
      totalItems.value += 1
    }
  }

  // Refresh stats occasionally
  if (Math.random() < 0.2) {
    fetchStats()
  }
}

function disconnectSSE() {
  if (sseAbortController) {
    sseAbortController.abort()
    sseAbortController = null
  }
  sseConnected.value = false
}

// ── Helpers ──
function getSessionId(item) {
  return item.request_data?.session_id || item.session_id || null
}

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
  testResult.value = null;
  showHumanInput.value = false;
  humanText.value = '';
  dialog.value = true 
}

// ── STM/MTM from Job ──
async function viewStmFromJob(item) {
  const sessionId = getSessionId(item)
  if (!sessionId) return
  
  memoryDialogType.value = 'stm'
  memoryDialogTitle.value = `STM - Conversa: ${sessionId}`
  memoryMessages.value = []
  memoryDialogLoading.value = true
  memoryDialog.value = true

  try {
    const key = `conversation:${sessionId}`
    const { data } = await axiosInstance.get(`/memory/stm/keys/${encodeURIComponent(key)}`)
    memoryMessages.value = data.messages || []
  } catch (e) {
    memoryMessages.value = []
    showSnackbar('Erro ao carregar conversa STM', 'error')
  } finally {
    memoryDialogLoading.value = false
  }
}

async function viewMtmFromJob(item) {
  const sessionId = getSessionId(item)
  if (!sessionId) return

  memoryDialogType.value = 'mtm'
  memoryDialogTitle.value = `MTM - Histórico: ${sessionId}`
  memoryMessages.value = []
  memoryDialogLoading.value = true
  memoryDialog.value = true

  try {
    const { data } = await axiosInstance.get(`/memory/mtm/sessions/${encodeURIComponent(sessionId)}`)
    memoryMessages.value = data.messages || []
  } catch (e) {
    memoryMessages.value = []
    showSnackbar('Erro ao carregar histórico MTM', 'error')
  } finally {
    memoryDialogLoading.value = false
  }
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

// ── Agent Control Functions ──
const pauseAgent = async (minutes) => {
  if (!selectedJob.value) return;
  pausingAgent.value = true;
  try {
    const body = minutes ? { timeout_minutes: Number(minutes) } : {};
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/pause-agent`, body);
    const modeText = data.mode === 'temporary' ? `por ${data.timeout_minutes} min` : 'permanentemente';
    showSnackbar(`Agente desativado ${modeText} para sessão ${data.session_id}`, 'warning');
  } catch (error) {
    console.error("Erro ao pausar agente:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao desativar agente', 'error');
  } finally {
    pausingAgent.value = false;
  }
}

const activateAgent = async () => {
  if (!selectedJob.value) return;
  activatingAgent.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/activate-agent`);
    showSnackbar(`Agente reativado para sessão ${data.session_id}`, 'success');
  } catch (error) {
    console.error("Erro ao ativar agente:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao ativar agente', 'error');
  } finally {
    activatingAgent.value = false;
  }
}

const unblockBot = async (sessionId) => {
  if (!sessionId) return
  unblockingBot.value = true
  try {
    await axiosInstance.delete(`/tracking/antibot/${sessionId}`)
    showSnackbar('Bloqueio Anti-Bot removido!', 'success')
  } catch (error) {
    console.error('Error unblocking bot:', error)
    showSnackbar('Erro ao remover bloqueio', 'error')
  } finally {
    unblockingBot.value = false
  }
}

// ── Memory Bubble Helpers ──
const getMemoryBubbleClass = (role) => ({
  'user': 'mem-user-msg',
  'assistant': 'mem-assistant-msg',
  'fromMe': 'mem-fromme-msg',
  'supportResponse': 'mem-support-msg',
}[role] || 'mem-user-msg')

const getMemoryIcon = (role) => ({
  'user': 'mdi-account',
  'assistant': 'mdi-robot',
  'fromMe': 'mdi-whatsapp',
  'supportResponse': 'mdi-headset',
}[role] || 'mdi-account')

const getMemoryIconColor = (role) => ({
  'user': '#00D1FF',
  'assistant': '#9D4EDD',
  'fromMe': '#25D366',
  'supportResponse': '#FBBF24',
}[role] || '#00D1FF')

const getStatusColor = (status) => ({ 'completed': 'success', 'failed': 'error', 'queued': 'warning', 'in_progress': 'info', 'buffered': 'purple', 'paused': 'orange' }[status] || 'grey')
const getStatusIcon = (status) => ({ 'completed': 'mdi-check', 'failed': 'mdi-close', 'queued': 'mdi-clock', 'in_progress': 'mdi-play', 'buffered': 'mdi-tray-full', 'paused': 'mdi-pause-circle' }[status] || 'mdi-help')
const formatDate = (d) => d ? new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
const formatJSON = (obj) => { try { return JSON.stringify(obj, null, 2) } catch { return obj } }

const copyToClipboard = (data) => {
  const text = typeof data === 'object' ? JSON.stringify(data, null, 2) : data
  navigator.clipboard.writeText(text).then(() => showSnackbar('Copiado!', 'success')).catch(() => showSnackbar('Erro ao copiar', 'error'))
}

const showSnackbar = (text, color = 'success') => { snackbar.value = { show: true, text, color } }

onMounted(() => { 
  fetchData()
  fetchDisparadorData()
  connectSSE()
})

onUnmounted(() => {
  disconnectSSE()
})
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

/* SSE indicator */
.sse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00FC8B;
  box-shadow: 0 0 6px rgba(0, 252, 139, 0.6);
  animation: sse-pulse 2s ease-in-out infinite;
}

.sse-offline {
  background: #FF0055;
  box-shadow: 0 0 6px rgba(255, 0, 85, 0.4);
  animation: none;
}

@keyframes sse-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Memory message bubbles */
.memory-bubble {
  border: 1px solid rgba(255,255,255,0.05);
}

.mem-user-msg {
  background: rgba(0, 163, 255, 0.06);
  border-left: 3px solid rgba(0, 209, 255, 0.5);
}

.mem-assistant-msg {
  background: rgba(157, 78, 221, 0.06);
  border-left: 3px solid rgba(157, 78, 221, 0.5);
}

.mem-fromme-msg {
  background: rgba(37, 211, 102, 0.08);
  border-left: 3px solid rgba(37, 211, 102, 0.5);
}

.mem-support-msg {
  background: rgba(251, 191, 36, 0.08);
  border-left: 3px solid rgba(251, 191, 36, 0.5);
}

/* Data table pagination footer */
:deep(.v-data-table-footer) {
  background: rgba(255, 255, 255, 0.02) !important;
  border-top: 1px solid rgba(255, 255, 255, 0.05) !important;
  padding: 8px 16px !important;
}

:deep(.v-data-table-footer__info) {
  color: rgba(255, 255, 255, 0.6) !important;
  font-size: 13px;
}

:deep(.v-data-table-footer__items-per-page .v-field) {
  background: rgba(255, 255, 255, 0.05) !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  color: rgba(255, 255, 255, 0.7) !important;
}

:deep(.v-data-table-footer__pagination .v-btn) {
  color: rgba(255, 255, 255, 0.6) !important;
}

:deep(.v-data-table-footer__pagination .v-btn:hover) {
  background: rgba(157, 78, 221, 0.15) !important;
  color: white !important;
}

:deep(.v-data-table-footer__pagination .v-btn--disabled) {
  color: rgba(255, 255, 255, 0.15) !important;
}
</style>
