<template>
  <div class="memory-manager flex-grow-1">

    <!-- Top Stats -->
    <v-row class="mb-5">
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-cyan">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(0, 209, 255, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Conversas STM</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #00A3FF, #00D1FF)">
              <v-icon icon="mdi-message-text-clock-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ stmKeys.length }}</h3>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-purple">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(157, 78, 221, 0.3) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Memórias Vetoriais</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #7C3AED, #9D4EDD)">
              <v-icon icon="mdi-brain" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ vectorMemories.length }}</h3>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-amber">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Sessões MTM</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #F59E0B, #FBBF24)">
              <v-icon icon="mdi-database-clock-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ mtmSessions.length }}</h3>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-amber">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Jobs Redis</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #F59E0B, #FBBF24)">
              <v-icon icon="mdi-briefcase-clock-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ jobKeys.length }}</h3>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-green">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(0, 252, 139, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Coleções Weaviate</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #00FC8B, #10B981)">
              <v-icon icon="mdi-database-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">{{ vectorCollections.length }}</h3>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Tabs -->
    <v-card class="glass-card">
      <v-tabs v-model="activeTab" bg-color="transparent" color="#9D4EDD" slider-color="#9D4EDD">
        <v-tab value="stm" class="text-white">
          <v-icon start size="18">mdi-message-text-clock-outline</v-icon>
          Conversas (STM)
        </v-tab>
        <v-tab value="mtm" class="text-white">
          <v-icon start size="18">mdi-database-clock-outline</v-icon>
          Histórico (MTM)
        </v-tab>
        <v-tab value="jobs" class="text-white">
          <v-icon start size="18">mdi-briefcase-clock-outline</v-icon>
          Jobs Redis
        </v-tab>
        <v-tab value="vector" class="text-white">
          <v-icon start size="18">mdi-brain</v-icon>
          Memória Vetorial
        </v-tab>
      </v-tabs>

      <v-divider style="border-color: rgba(255,255,255,0.05)"></v-divider>

      <v-card-text class="pa-6">

        <!-- ── STM Tab ── -->
        <v-window v-model="activeTab">
          <v-window-item value="stm">
            <div class="d-flex align-center justify-space-between mb-4">
              <div class="d-flex align-center ga-3">
                <v-text-field
                  v-model="stmSearch"
                  prepend-inner-icon="mdi-magnify"
                  placeholder="Filtrar por session ID..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  rounded="lg"
                  class="search-field"
                  style="max-width: 340px"
                ></v-text-field>
              </div>
              <div class="d-flex ga-2">
                <v-btn color="primary" variant="tonal" size="small" @click="fetchStmKeys" :loading="loadingStm">
                  <v-icon start size="16">mdi-refresh</v-icon> Atualizar
                </v-btn>
                <v-btn
                  color="error"
                  variant="tonal"
                  size="small"
                  :disabled="selectedStmKeys.length === 0"
                  @click="deleteSelectedStm"
                >
                  <v-icon start size="16">mdi-delete-outline</v-icon>
                  Apagar ({{ selectedStmKeys.length }})
                </v-btn>
              </div>
            </div>

            <v-data-table
              v-model="selectedStmKeys"
              :headers="stmHeaders"
              :items="filteredStmKeys"
              :loading="loadingStm"
              item-value="key"
              show-select
              items-per-page="15"
              class="memory-table bg-transparent"
              hover
            >
              <template #item.key="{ item }">
                <div class="d-flex align-center">
                  <v-icon size="16" class="mr-2" color="#00D1FF">mdi-key-variant</v-icon>
                  <span class="text-body-2 font-weight-medium text-white key-text">{{ item.key }}</span>
                </div>
              </template>
              <template #item.size="{ item }">
                <v-chip size="small" variant="tonal" color="info">{{ item.size }} msgs</v-chip>
              </template>
              <template #item.ttl="{ item }">
                <span class="text-body-2" style="color: rgba(255,255,255,0.6)">
                  {{ item.ttl > 0 ? formatTTL(item.ttl) : 'Sem expiração' }}
                </span>
              </template>
              <template #item.actions="{ item }">
                <div class="d-flex ga-1">
                  <v-btn icon variant="text" size="x-small" color="info" @click="viewStmKey(item)">
                    <v-icon size="18">mdi-eye-outline</v-icon>
                    <v-tooltip activator="parent" location="top">Visualizar</v-tooltip>
                  </v-btn>
                  <v-btn icon variant="text" size="x-small" color="error" @click="deleteStmKey(item)">
                    <v-icon size="18">mdi-delete-outline</v-icon>
                    <v-tooltip activator="parent" location="top">Apagar</v-tooltip>
                  </v-btn>
                </div>
              </template>
            </v-data-table>
          </v-window-item>

          <!-- ── MTM Tab ── -->
          <v-window-item value="mtm">
            <div class="d-flex align-center justify-space-between mb-4">
              <div class="d-flex align-center ga-3">
                <v-text-field
                  v-model="mtmSearch"
                  prepend-inner-icon="mdi-magnify"
                  placeholder="Filtrar por session ID..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  rounded="lg"
                  class="search-field"
                  style="max-width: 340px"
                ></v-text-field>
              </div>
              <div class="d-flex ga-2">
                <v-btn color="primary" variant="tonal" size="small" @click="fetchMtmSessions" :loading="loadingMtm">
                  <v-icon start size="16">mdi-refresh</v-icon> Atualizar
                </v-btn>
                <v-btn
                  color="error"
                  variant="tonal"
                  size="small"
                  :disabled="selectedMtmSessions.length === 0"
                  @click="deleteSelectedMtm"
                >
                  <v-icon start size="16">mdi-delete-outline</v-icon>
                  Apagar ({{ selectedMtmSessions.length }})
                </v-btn>
              </div>
            </div>

            <v-data-table
              v-model="selectedMtmSessions"
              :headers="mtmHeaders"
              :items="filteredMtmSessions"
              :loading="loadingMtm"
              item-value="session_id"
              show-select
              items-per-page="15"
              class="memory-table bg-transparent"
              hover
            >
              <template #item.session_id="{ item }">
                <div class="d-flex align-center">
                  <v-icon size="16" class="mr-2" color="#FBBF24">mdi-account-circle-outline</v-icon>
                  <span class="text-body-2 font-weight-medium text-white key-text">{{ item.session_id }}</span>
                </div>
              </template>
              <template #item.agent_id="{ item }">
                <v-chip size="small" variant="tonal" color="purple" class="font-weight-medium">
                  {{ item.agent_id ? item.agent_id.substring(0, 8) + '...' : '—' }}
                </v-chip>
              </template>
              <template #item.total_messages="{ item }">
                <v-chip size="small" variant="tonal" color="info">{{ item.total_messages }} msgs</v-chip>
              </template>
              <template #item.last_interaction="{ item }">
                <span class="text-body-2" style="color: rgba(255,255,255,0.6)">
                  {{ formatDate(item.last_interaction) }}
                </span>
              </template>
              <template #item.actions="{ item }">
                <div class="d-flex ga-1">
                  <v-btn icon variant="text" size="x-small" color="info" @click="viewMtmSession(item)">
                    <v-icon size="18">mdi-eye-outline</v-icon>
                    <v-tooltip activator="parent" location="top">Visualizar</v-tooltip>
                  </v-btn>
                  <v-btn icon variant="text" size="x-small" color="error" @click="deleteMtmSession(item)">
                    <v-icon size="18">mdi-delete-outline</v-icon>
                    <v-tooltip activator="parent" location="top">Apagar</v-tooltip>
                  </v-btn>
                </div>
              </template>
            </v-data-table>
          </v-window-item>

          <!-- ── Jobs Tab ── -->
          <v-window-item value="jobs">
            <div class="d-flex align-center justify-space-between mb-4">
              <v-text-field
                v-model="jobSearch"
                prepend-inner-icon="mdi-magnify"
                placeholder="Filtrar jobs..."
                variant="outlined"
                density="compact"
                hide-details
                rounded="lg"
                class="search-field"
                style="max-width: 340px"
              ></v-text-field>
              <div class="d-flex ga-2">
                <v-btn color="primary" variant="tonal" size="small" @click="fetchJobKeys" :loading="loadingJobs">
                  <v-icon start size="16">mdi-refresh</v-icon> Atualizar
                </v-btn>
                <v-btn
                  color="error" variant="tonal" size="small"
                  :disabled="selectedJobKeys.length === 0"
                  @click="deleteSelectedJobs"
                >
                  <v-icon start size="16">mdi-delete-outline</v-icon>
                  Apagar ({{ selectedJobKeys.length }})
                </v-btn>
              </div>
            </div>

            <v-data-table
              v-model="selectedJobKeys"
              :headers="jobHeaders"
              :items="filteredJobKeys"
              :loading="loadingJobs"
              item-value="key"
              show-select
              items-per-page="15"
              class="memory-table bg-transparent"
              hover
            >
              <template #item.key="{ item }">
                <div class="d-flex align-center">
                  <v-icon size="16" class="mr-2" color="#FBBF24">mdi-briefcase-outline</v-icon>
                  <span class="text-body-2 font-weight-medium text-white key-text">{{ item.key }}</span>
                </div>
              </template>
              <template #item.ttl="{ item }">
                <span class="text-body-2" style="color: rgba(255,255,255,0.6)">
                  {{ item.ttl > 0 ? formatTTL(item.ttl) : 'Sem expiração' }}
                </span>
              </template>
              <template #item.actions="{ item }">
                <div class="d-flex ga-1">
                  <v-btn icon variant="text" size="x-small" color="info" @click="viewStmKey(item)">
                    <v-icon size="18">mdi-eye-outline</v-icon>
                  </v-btn>
                  <v-btn icon variant="text" size="x-small" color="error" @click="deleteStmKey(item)">
                    <v-icon size="18">mdi-delete-outline</v-icon>
                  </v-btn>
                </div>
              </template>
            </v-data-table>
          </v-window-item>

          <!-- ── Vector Memory Tab ── -->
          <v-window-item value="vector">
            <div class="d-flex align-center justify-space-between mb-4 flex-wrap ga-3">
              <div class="d-flex ga-3 flex-wrap align-center">
                <v-tabs v-model="vectorSubType" density="compact" bg-color="transparent" color="primary" slider-color="primary" class="mr-4">
                  <v-tab value="contacts" size="small">Contatos</v-tab>
                  <v-tab value="agent" size="small">Auto-Agente</v-tab>
                </v-tabs>

                <v-text-field
                  v-model="vectorSearch"
                  prepend-inner-icon="mdi-magnify"
                  placeholder="Filtrar por conteúdo..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  rounded="lg"
                  class="search-field"
                  style="max-width: 240px"
                ></v-text-field>
                
                <v-text-field
                  v-if="vectorSubType === 'contacts'"
                  v-model="vectorContactFilter"
                  prepend-inner-icon="mdi-account-outline"
                  placeholder="Contact ID..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  rounded="lg"
                  class="search-field"
                  style="max-width: 180px"
                ></v-text-field>
                
                <v-select
                  v-model="vectorTypeFilter"
                  :items="memoryTypeOptions"
                  label="Tipo"
                  variant="outlined"
                  density="compact"
                  hide-details
                  rounded="lg"
                  class="search-field"
                  style="max-width: 160px"
                ></v-select>
              </div>
              <div class="d-flex ga-2">
                <v-btn color="primary" variant="tonal" size="small" @click="fetchActiveVectorTab" :loading="loadingVector">
                  <v-icon start size="16">mdi-refresh</v-icon> Atualizar
                </v-btn>
                <v-btn
                  color="error" variant="tonal" size="small"
                  :disabled="selectedVectorMemories.length === 0"
                  @click="deleteSelectedVector"
                >
                  <v-icon start size="16">mdi-delete-outline</v-icon>
                  Apagar ({{ selectedVectorMemories.length }})
                </v-btn>
              </div>
            </div>

            <v-data-table
              v-model="selectedVectorMemories"
              :headers="vectorSubType === 'contacts' ? vectorHeaders : agentVectorHeaders"
              :items="vectorSubType === 'contacts' ? filteredVectorMemories : filteredAgentMemories"
              :loading="loadingVector"
              item-value="uuid"
              show-select
              items-per-page="15"
              class="memory-table bg-transparent"
              hover
            >
              <template #item.memory_type="{ item }">
                <v-chip size="x-small" :color="getMemoryTypeColor(item.memory_type)" variant="tonal" class="font-weight-bold">
                  <v-icon start size="12">{{ getMemoryTypeIcon(item.memory_type) }}</v-icon>
                  {{ getMemoryTypeLabel(item.memory_type) }}
                </v-chip>
              </template>
              <template #item.contact_id="{ item }">
                <v-chip size="small" variant="tonal" color="info" class="font-weight-medium">
                  {{ item.contact_id ? item.contact_id.substring(0, 12) + '...' : '—' }}
                </v-chip>
              </template>
              <template #item.agent_id="{ item }">
                <v-chip size="small" variant="tonal" color="purple" class="font-weight-medium">
                  {{ item.agent_id ? item.agent_id.substring(0, 8) + '...' : '—' }}
                </v-chip>
              </template>
              <template #item.content="{ item }">
                <span class="text-body-2 text-white memory-content">{{ item.content }}</span>
              </template>
              <template #item.created_at="{ item }">
                <span class="text-body-2" style="color: rgba(255,255,255,0.5)">
                  {{ formatDate(item.created_at) }}
                </span>
              </template>
              <template #item.actions="{ item }">
                <v-btn icon variant="text" size="x-small" color="error" @click="deleteVectorMemory(item)">
                  <v-icon size="18">mdi-delete-outline</v-icon>
                  <v-tooltip activator="parent" location="top">Apagar</v-tooltip>
                </v-btn>
              </template>
            </v-data-table>
          </v-window-item>
        </v-window>
      </v-card-text>
    </v-card>

    <!-- View Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="750" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important">
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" size="20" color="#00D1FF">mdi-key-variant</v-icon>
          <span class="text-subtitle-1 font-weight-bold text-white">{{ detailKey }}</span>
          <v-spacer />
          <v-btn icon variant="text" size="small" @click="detailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider style="border-color: rgba(255,255,255,0.05)"></v-divider>
        <v-card-text class="pa-5" style="max-height: 550px; overflow-y: auto;">
          <div v-if="detailData?.messages" class="d-flex flex-column ga-3">
            <div
              v-for="(msg, idx) in detailData.messages"
              :key="idx"
              class="message-bubble pa-3 rounded-lg"
              :class="msg.role === 'user' ? 'user-msg' : 'assistant-msg'"
            >
              <div class="d-flex align-center mb-1">
                <v-icon size="14" class="mr-1" :color="msg.role === 'user' ? '#00D1FF' : '#9D4EDD'">
                  {{ msg.role === 'user' ? 'mdi-account' : 'mdi-robot' }}
                </v-icon>
                <span class="text-caption font-weight-bold text-uppercase" style="opacity: 0.7">{{ msg.role }}</span>
                <span v-if="msg.created_at || msg.timestamp" class="text-caption ml-2" style="opacity: 0.4">
                  {{ formatDate(msg.created_at || msg.timestamp) }}
                </span>
              </div>
              <div class="text-body-2 text-white" style="white-space: pre-wrap; word-break: break-word;">{{ msg.content }}</div>
            </div>
          </div>
          <div v-else-if="detailData?.data">
            <pre class="text-body-2 text-white" style="white-space: pre-wrap; word-break: break-word; background: rgba(255,255,255,0.03); padding: 16px; border-radius: 8px;">{{ typeof detailData.data === 'object' ? JSON.stringify(detailData.data, null, 2) : detailData.data }}</pre>
          </div>
          <div v-else class="text-center pa-8">
            <v-progress-circular indeterminate color="primary" size="32"></v-progress-circular>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Confirm Delete Dialog -->
    <v-dialog v-model="confirmDialog" max-width="440">
      <v-card class="glass-card" style="background: #0D1117 !important">
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" color="error" size="22">mdi-alert-circle-outline</v-icon>
          <span class="text-subtitle-1 font-weight-bold text-white">Confirmar Exclusão</span>
        </v-card-title>
        <v-card-text class="pa-5 pt-0">
          <p class="text-body-2 text-white" style="opacity: 0.8">{{ confirmMessage }}</p>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="confirmDialog = false">Cancelar</v-btn>
          <v-btn color="error" variant="flat" @click="confirmAction" :loading="deleting">Apagar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar" :color="snackColor" timeout="3000" location="bottom right">
      {{ snackMessage }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from '@/plugins/axios'

// ── State ──
const activeTab = ref('stm')
const loadingStm = ref(false)
const loadingMtm = ref(false)
const loadingJobs = ref(false)
const loadingVector = ref(false)
const deleting = ref(false)

const stmKeys = ref([])
const mtmSessions = ref([])
const jobKeys = ref([])
const vectorMemories = ref([])
const agentSelfMemories = ref([])
const vectorCollections = ref([])

const vectorSubType = ref('contacts')
const vectorTypeFilter = ref('all')
const memoryTypeOptions = [
  { title: 'Todos', value: 'all' },
  { title: 'Fato', value: 'fact' },
  { title: 'Correção', value: 'correction' },
  { title: 'Preferência', value: 'preference' }
]

const selectedStmKeys = ref([])
const selectedMtmSessions = ref([])
const selectedJobKeys = ref([])
const selectedVectorMemories = ref([])

const stmSearch = ref('')
const mtmSearch = ref('')
const jobSearch = ref('')
const vectorSearch = ref('')
const vectorContactFilter = ref('')

// Dialog
const detailDialog = ref(false)
const detailKey = ref('')
const detailData = ref(null)

const confirmDialog = ref(false)
const confirmMessage = ref('')
let pendingConfirmAction = null

const snackbar = ref(false)
const snackMessage = ref('')
const snackColor = ref('success')

// ── Headers ──
const stmHeaders = [
  { title: 'Chave (Session ID)', key: 'key', sortable: true },
  { title: 'Mensagens', key: 'size', sortable: true, width: '120px' },
  { title: 'TTL', key: 'ttl', sortable: true, width: '140px' },
  { title: 'Ações', key: 'actions', sortable: false, width: '100px', align: 'center' },
]

const jobHeaders = [
  { title: 'Chave (Job ID)', key: 'key', sortable: true },
  { title: 'TTL', key: 'ttl', sortable: true, width: '140px' },
  { title: 'Ações', key: 'actions', sortable: false, width: '100px', align: 'center' },
]

const vectorHeaders = [
  { title: 'Tipo', key: 'memory_type', sortable: true, width: '120px' },
  { title: 'Contato', key: 'contact_id', sortable: true, width: '160px' },
  { title: 'Agente', key: 'agent_id', sortable: true, width: '140px' },
  { title: 'Conteúdo', key: 'content', sortable: false },
  { title: 'Criado em', key: 'created_at', sortable: true, width: '160px' },
  { title: 'Ações', key: 'actions', sortable: false, width: '80px', align: 'center' },
]

const agentVectorHeaders = [
  { title: 'Tipo', key: 'memory_type', sortable: true, width: '120px' },
  { title: 'Agente', key: 'agent_id', sortable: true, width: '160px' },
  { title: 'Conteúdo', key: 'content', sortable: false },
  { title: 'Criado em', key: 'created_at', sortable: true, width: '160px' },
  { title: 'Ações', key: 'actions', sortable: false, width: '80px', align: 'center' },
]

const mtmHeaders = [
  { title: 'Session ID', key: 'session_id', sortable: true },
  { title: 'Agente', key: 'agent_id', sortable: true, width: '140px' },
  { title: 'Mensagens', key: 'total_messages', sortable: true, width: '130px' },
  { title: 'Última Interação', key: 'last_interaction', sortable: true, width: '180px' },
  { title: 'Ações', key: 'actions', sortable: false, width: '100px', align: 'center' },
]

// ── Computed ──
const filteredStmKeys = computed(() => {
  if (!stmSearch.value) return stmKeys.value
  const s = stmSearch.value.toLowerCase()
  return stmKeys.value.filter(k => k.key.toLowerCase().includes(s))
})

const filteredJobKeys = computed(() => {
  if (!jobSearch.value) return jobKeys.value
  const s = jobSearch.value.toLowerCase()
  return jobKeys.value.filter(k => k.key.toLowerCase().includes(s))
})

const filteredVectorMemories = computed(() => {
  let items = vectorMemories.value
  if (vectorSearch.value) {
    const s = vectorSearch.value.toLowerCase()
    items = items.filter(m => m.content.toLowerCase().includes(s))
  }
  if (vectorContactFilter.value) {
    const c = vectorContactFilter.value.toLowerCase()
    items = items.filter(m => m.contact_id.toLowerCase().includes(c))
  }
  if (vectorTypeFilter.value !== 'all') {
    items = items.filter(m => m.memory_type === vectorTypeFilter.value)
  }
  return items
})

const filteredAgentMemories = computed(() => {
  let items = agentSelfMemories.value
  if (vectorSearch.value) {
    const s = vectorSearch.value.toLowerCase()
    items = items.filter(m => m.content.toLowerCase().includes(s))
  }
  if (vectorTypeFilter.value !== 'all') {
    items = items.filter(m => m.memory_type === vectorTypeFilter.value)
  }
  return items
})

const filteredMtmSessions = computed(() => {
  if (!mtmSearch.value) return mtmSessions.value
  const s = mtmSearch.value.toLowerCase()
  return mtmSessions.value.filter(k => k.session_id.toLowerCase().includes(s))
})

// ── Helpers ──
function formatTTL(seconds) {
  if (seconds < 0) return 'Sem expiração'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}min`
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return dateStr
  }
}

function showSnack(msg, color = 'success') {
  snackMessage.value = msg
  snackColor.value = color
  snackbar.value = true
}

function getMemoryTypeColor(type) {
  const colors = {
    fact: 'info',
    correction: 'error',
    preference: 'warning'
  }
  return colors[type] || 'grey'
}

function getMemoryTypeIcon(type) {
  const icons = {
    fact: 'mdi-information-outline',
    correction: 'mdi-alert-circle-outline',
    preference: 'mdi-heart-outline'
  }
  return icons[type] || 'mdi-brain'
}

function getMemoryTypeLabel(type) {
  const labels = {
    fact: 'Fato',
    correction: 'Correção',
    preference: 'Preferência'
  }
  return labels[type] || type
}

// ── Fetch ──
async function fetchStmKeys() {
  loadingStm.value = true
  try {
    const res = await axios.get('/memory/stm/keys', { params: { pattern: 'conversation:*', count: 500 } })
    stmKeys.value = res.data.keys || []
  } catch (e) {
    showSnack('Erro ao buscar chaves STM', 'error')
  } finally {
    loadingStm.value = false
  }
}

async function fetchJobKeys() {
  loadingJobs.value = true
  try {
    const res = await axios.get('/memory/stm/keys', { params: { pattern: 'job:*', count: 500 } })
    jobKeys.value = res.data.keys || []
  } catch (e) {
    showSnack('Erro ao buscar jobs', 'error')
  } finally {
    loadingJobs.value = false
  }
}

async function fetchVectorMemories() {
  loadingVector.value = true
  try {
    const res = await axios.get('/memory/vector/memories', { params: { limit: 200 } })
    vectorMemories.value = res.data.memories || []
  } catch (e) {
    showSnack('Erro ao buscar memórias vetoriais', 'error')
  } finally {
    loadingVector.value = false
  }
}

async function fetchAgentSelfMemories() {
  loadingVector.value = true
  try {
    const res = await axios.get('/memory/vector/agent-memories', { params: { limit: 200 } })
    agentSelfMemories.value = res.data.memories || []
  } catch (e) {
    showSnack('Erro ao buscar memórias de auto-aprendizado', 'error')
  } finally {
    loadingVector.value = false
  }
}

function fetchActiveVectorTab() {
  if (vectorSubType.value === 'contacts') {
    fetchVectorMemories()
  } else {
    fetchAgentSelfMemories()
  }
}

async function fetchVectorCollections() {
  try {
    const res = await axios.get('/memory/vector/collections')
    vectorCollections.value = res.data.collections || []
  } catch { /* silent */ }
}

async function fetchMtmSessions() {
  loadingMtm.value = true
  try {
    const res = await axios.get('/memory/mtm/sessions', { params: { limit: 500 } })
    mtmSessions.value = res.data.sessions || []
  } catch (e) {
    showSnack('Erro ao buscar sessões MTM', 'error')
  } finally {
    loadingMtm.value = false
  }
}

async function viewMtmSession(item) {
  detailKey.value = item.session_id
  detailData.value = null
  detailDialog.value = true
  try {
    const res = await axios.get(`/memory/mtm/sessions/${item.session_id}`)
    detailData.value = res.data
  } catch (e) {
    detailData.value = { data: 'Erro ao carregar dados' }
  }
}

function deleteMtmSession(item) {
  confirmMessage.value = `Tem certeza que deseja apagar toda a conversa da sessão "${item.session_id}"? (${item.total_messages} mensagens)`
  pendingConfirmAction = async () => {
    await axios.delete(`/memory/mtm/sessions/${item.session_id}`)
    showSnack(`Sessão "${item.session_id}" apagada`)
    fetchMtmSessions()
  }
  confirmDialog.value = true
}

function deleteSelectedMtm() {
  const count = selectedMtmSessions.value.length
  confirmMessage.value = `Tem certeza que deseja apagar ${count} sessão(ões) selecionada(s)? Esta ação é irreversível.`
  pendingConfirmAction = async () => {
    for (const sid of selectedMtmSessions.value) {
      await axios.delete(`/memory/mtm/sessions/${sid}`)
    }
    showSnack(`${count} sessão(ões) apagada(s)`)
    selectedMtmSessions.value = []
    fetchMtmSessions()
  }
  confirmDialog.value = true
}

// ── View ──
async function viewStmKey(item) {
  detailKey.value = item.key
  detailData.value = null
  detailDialog.value = true
  try {
    const res = await axios.get(`/memory/stm/keys/${item.key}`)
    detailData.value = res.data
  } catch (e) {
    detailData.value = { data: 'Erro ao carregar dados' }
  }
}

// ── Delete ──
function deleteStmKey(item) {
  confirmMessage.value = `Tem certeza que deseja apagar a chave "${item.key}"? Esta ação é irreversível.`
  pendingConfirmAction = async () => {
    await axios.delete(`/memory/stm/keys/${item.key}`)
    showSnack(`Chave "${item.key}" apagada`)
    fetchStmKeys()
    fetchJobKeys()
  }
  confirmDialog.value = true
}

function deleteSelectedStm() {
  const count = selectedStmKeys.value.length
  confirmMessage.value = `Tem certeza que deseja apagar ${count} chave(s) selecionada(s)? Esta ação é irreversível.`
  pendingConfirmAction = async () => {
    await axios.delete('/memory/stm/keys', { data: selectedStmKeys.value })
    showSnack(`${count} chave(s) apagada(s)`)
    selectedStmKeys.value = []
    fetchStmKeys()
  }
  confirmDialog.value = true
}

function deleteSelectedJobs() {
  const count = selectedJobKeys.value.length
  confirmMessage.value = `Tem certeza que deseja apagar ${count} job(s) selecionado(s)?`
  pendingConfirmAction = async () => {
    await axios.delete('/memory/stm/keys', { data: selectedJobKeys.value })
    showSnack(`${count} job(s) apagado(s)`)
    selectedJobKeys.value = []
    fetchJobKeys()
  }
  confirmDialog.value = true
}

function deleteVectorMemory(item) {
  confirmMessage.value = `Apagar esta memória vetorial? (Contact: ${item.contact_id?.substring(0, 12)}...)`
  pendingConfirmAction = async () => {
    await axios.delete(`/memory/vector/memories/${item.uuid}`)
    showSnack('Memória vetorial apagada')
    fetchVectorMemories()
  }
  confirmDialog.value = true
}

function deleteSelectedVector() {
  const count = selectedVectorMemories.value.length
  const isAgent = vectorSubType.value === 'agent'
  confirmMessage.value = `Tem certeza que deseja apagar ${count} memória(s) ${isAgent ? 'de auto-aprendizado' : 'vetorial(is)'}?`
  pendingConfirmAction = async () => {
    if (isAgent) {
      for (const uuid of selectedVectorMemories.value) {
        await axios.delete(`/memory/vector/agent-memories/${uuid}`)
      }
    } else {
      await axios.delete('/memory/vector/memories', { data: selectedVectorMemories.value })
    }
    showSnack(`${count} memória(s) apagada(s)`)
    selectedVectorMemories.value = []
    fetchActiveVectorTab()
  }
  confirmDialog.value = true
}

async function confirmAction() {
  if (!pendingConfirmAction) return
  deleting.value = true
  try {
    await pendingConfirmAction()
  } catch (e) {
    showSnack('Erro ao apagar: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    deleting.value = false
    confirmDialog.value = false
    pendingConfirmAction = null
  }
}

// ── Init ──
onMounted(() => {
  fetchStmKeys()
  fetchMtmSessions()
  fetchJobKeys()
  fetchActiveVectorTab()
  fetchVectorCollections()
})
</script>

<style scoped>
.z-1 { z-index: 1; position: relative; }
.relative { position: relative; }

.stat-label {
  color: rgba(255,255,255,0.55);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 11px;
}

.stat-icon-box {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.border-cyan { border-top: 2px solid rgba(0, 209, 255, 0.5); }
.border-purple { border-top: 2px solid rgba(157, 78, 221, 0.5); }
.border-amber { border-top: 2px solid rgba(245, 158, 11, 0.5); }
.border-green { border-top: 2px solid rgba(0, 252, 139, 0.5); }

.bg-glow {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  opacity: 0.7;
  z-index: 0;
  pointer-events: none;
}

.key-text {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px !important;
  letter-spacing: -0.02em;
}

.memory-content {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 400px;
}

.search-field :deep(.v-field) {
  background: rgba(20, 24, 40, 0.7) !important;
  border-color: rgba(255, 255, 255, 0.06) !important;
}

.search-field :deep(.v-field:hover),
.search-field :deep(.v-field--focused) {
  border-color: rgba(157, 78, 221, 0.4) !important;
}

/* Table styling */
.memory-table :deep(th) {
  color: rgba(255,255,255,0.4) !important;
  font-size: 11px !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid rgba(255,255,255,0.05) !important;
  background: transparent !important;
}

.memory-table :deep(td) {
  border-bottom: 1px solid rgba(255,255,255,0.03) !important;
  background: transparent !important;
}

.memory-table :deep(tr:hover td) {
  background: rgba(157, 78, 221, 0.04) !important;
}

/* Message bubbles */
.message-bubble {
  border: 1px solid rgba(255,255,255,0.05);
}

.user-msg {
  background: rgba(0, 163, 255, 0.06);
  border-left: 3px solid rgba(0, 209, 255, 0.5);
}

.assistant-msg {
  background: rgba(157, 78, 221, 0.06);
  border-left: 3px solid rgba(157, 78, 221, 0.5);
}
</style>
