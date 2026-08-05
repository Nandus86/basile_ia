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
          <v-btn color="primary" prepend-icon="mdi-refresh" @click="fetchAnalytics">
            Atualizar
          </v-btn>
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
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const loading = ref(false)
const users = ref([])
const dialog = ref(false)
const selectedUser = ref(null)

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
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const response = await axios.get(`${API_URL}/analytics/users`)
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
