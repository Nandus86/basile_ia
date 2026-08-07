<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-2">Relatórios da Igreja</h1>
        <p class="text-subtitle-1 text-medium-emphasis">
          Visão executiva e saúde espiritual da comunidade local
        </p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-refresh" @click="fetchReports">
        Atualizar
      </v-btn>
    </div>

    <v-row class="mb-4">
      <v-col cols="12" md="3">
        <v-select
          v-model="selectedChurch"
          :items="churches"
          item-title="name"
          item-value="id"
          label="Igreja"
          variant="outlined"
          density="comfortable"
          @update:modelValue="fetchReports"
        ></v-select>
      </v-col>
      <v-col cols="12" md="3">
        <v-select
          v-model="periodType"
          :items="periodOptions"
          label="Período"
          variant="outlined"
          density="comfortable"
          @update:modelValue="fetchReports"
        ></v-select>
      </v-col>
      <v-col cols="12" md="6" class="d-flex align-center justify-end">
        <v-btn color="secondary" prepend-icon="mdi-flash" @click="generateManual" :disabled="!selectedChurch" :loading="generating">
          Gerar Relatório Agora
        </v-btn>
      </v-col>
    </v-row>

    <v-card class="glass-card mb-6" elevation="0">
      <v-data-table-server
        v-model:items-per-page="itemsPerPage"
        :headers="headers"
        :items="reports"
        :items-length="totalItems"
        :loading="loading"
        @update:options="fetchReports"
        class="elevation-0"
        hover
      >
        <template v-slot:item.period_start="{ item }">
          {{ formatDate((item.raw || item).period_start) }}
        </template>
        
        <template v-slot:item.status="{ item }">
          <v-chip
            :color="getStatusColor((item.raw || item).status)"
            size="small"
            class="text-uppercase font-weight-bold"
          >
            {{ (item.raw || item).status }}
          </v-chip>
        </template>

        <template v-slot:item.actions="{ item }">
          <v-btn icon="mdi-eye" size="small" variant="text" color="primary" @click="viewReport(item.raw || item)"></v-btn>
        </template>
      </v-data-table-server>
    </v-card>

    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card class="bg-surface">
        <v-card-title class="d-flex align-center justify-space-between pa-4 border-b">
          <div class="text-h6 font-weight-bold">
            Relatório: {{ selectedReport?.entity_name }} ({{ selectedReport?.period_type }})
          </div>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false"></v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6" style="background: rgba(0,0,0,0.2);">
          <div class="mb-6 d-flex ga-4">
            <v-chip color="info" variant="flat">
              <v-icon start>mdi-account-group</v-icon>
              {{ selectedReport?.stats?.total_users || 0 }} Membros
            </v-chip>
            <v-chip color="warning" variant="flat" v-if="selectedReport?.stats?.critical_cases">
              <v-icon start>mdi-alert</v-icon>
              {{ selectedReport?.stats?.critical_cases }} Casos Críticos
            </v-chip>
            <v-chip color="success" variant="flat" v-if="selectedReport?.stats?.avg_engagement_score">
              <v-icon start>mdi-thermometer</v-icon>
              Score Médio: {{ selectedReport?.stats?.avg_engagement_score }}
            </v-chip>
          </div>

          <div v-if="selectedReport?.report_content" class="report-content" style="white-space: pre-wrap; font-size: 15px; line-height: 1.6;">
            {{ selectedReport.report_content }}
          </div>
          <v-alert v-else type="info" variant="tonal">
            O conteúdo do relatório ainda está sendo processado ou não há dados suficientes.
          </v-alert>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { API_URL } from '@/config'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'

const churches = ref([])
const selectedChurch = ref(null)
const periodType = ref('daily')
const periodOptions = [
  { title: 'Diário', value: 'daily' },
  { title: 'Semanal', value: 'weekly' },
  { title: 'Mensal', value: 'monthly' }
]

const reports = ref([])
const totalItems = ref(0)
const itemsPerPage = ref(10)
const loading = ref(false)
const generating = ref(false)
const dialog = ref(false)
const selectedReport = ref(null)

const headers = [
  { title: 'Data do Relatório', key: 'period_start', align: 'start' },
  { title: 'Tipo', key: 'period_type' },
  { title: 'Status', key: 'status' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'end' }
]

const fetchChurches = async () => {
  try {
    const res = await axios.get(`${API_URL}/analytics/churches`)
    churches.value = res.data
    if (churches.value.length > 0) {
      selectedChurch.value = churches.value[0].id
      fetchReports()
    }
  } catch (error) {
    console.error('Error fetching churches', error)
  }
}

const fetchReports = async (options = {}) => {
  if (!selectedChurch.value) return
  
  const { page = 1, itemsPerPage: limit = 10 } = options
  const skip = (page - 1) * limit
  loading.value = true
  
  try {
    const res = await axios.get(`${API_URL}/analytics/reports`, {
      params: {
        level: 'church',
        period_type: periodType.value,
        entity_id: selectedChurch.value,
        skip,
        limit
      }
    })
    reports.value = res.data.reports
    totalItems.value = res.data.total
  } catch (error) {
    console.error('Error fetching reports', error)
  } finally {
    loading.value = false
  }
}

const generateManual = async () => {
  if (!selectedChurch.value) return
  generating.value = true
  try {
    const now = new Date()
    let start, end
    if (periodType.value === 'daily') {
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
      end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, -1)
    } else if (periodType.value === 'weekly') {
      const day = now.getDay()
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - day - 7)
      end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000 - 1)
    } else {
      start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
      end = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999)
    }

    await axios.post(`${API_URL}/analytics/reports/generate`, {
      level: 'church',
      period_type: periodType.value,
      entity_id: selectedChurch.value,
      entity_name: selectedChurch.value,
      start_time: start.toISOString(),
      end_time: end.toISOString()
    })
    
    setTimeout(() => fetchReports(), 1000)
  } catch (error) {
    console.error('Error generating report', error)
  } finally {
    generating.value = false
  }
}

const viewReport = (report) => {
  selectedReport.value = report
  dialog.value = true
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return format(new Date(dateStr), "dd 'de' MMMM, yyyy", { locale: ptBR })
}

const getStatusColor = (status) => {
  const map = {
    'pending': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'error'
  }
  return map[status] || 'grey'
}

onMounted(() => {
  fetchChurches()
})
</script>

<style scoped>
.glass-card {
  background: rgba(20, 24, 40, 0.4) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border-radius: 16px;
}
</style>
