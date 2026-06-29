<template>
  <div class="qa-eval-page flex-grow-1">
    <!-- Header Stats -->
    <v-row class="mb-5">
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-cyan">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(0, 209, 255, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Total Pares Q&A</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #00A3FF, #00D1FF)">
              <v-icon icon="mdi-forum-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">
              {{ stats.total_pairs || 0 }}
            </h3>
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-green">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Avaliados</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #059669, #10B981)">
              <v-icon icon="mdi-clipboard-check-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">
              {{ stats.total_evaluated || 0 }}
            </h3>
            <span class="text-caption" style="opacity: 0.7">{{ stats.evaluation_progress || 0 }}% concluído</span>
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-amber">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Média de Nota</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #D97706, #F59E0B)">
              <v-icon icon="mdi-star-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">
              {{ stats.average_score !== null ? stats.average_score : '--' }}
            </h3>
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card pa-5 d-flex flex-column justify-center relative border-purple">
          <div class="bg-glow" style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(0,0,0,0) 60%)"></div>
          <div class="d-flex justify-space-between align-start mb-3 z-1">
            <span class="text-caption font-weight-medium stat-label">Com Uso de Tool</span>
            <div class="stat-icon-box" style="background: linear-gradient(135deg, #7C3AED, #8B5CF6)">
              <v-icon icon="mdi-wrench-outline" size="22" color="white"></v-icon>
            </div>
          </div>
          <div class="z-1">
            <h3 class="text-h4 font-weight-bold text-white mb-0" style="line-height: 1; font-variant-numeric: tabular-nums;">
              {{ stats.total_with_tool_trace || 0 }}
            </h3>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Toolbar -->
    <v-card class="glass-card mb-5">
      <v-card-text class="d-flex align-center flex-wrap gap-4">
        <div class="d-flex align-center gap-2">
          <v-icon icon="mdi-filter-variant" color="primary"></v-icon>
          <span class="text-subtitle-2 text-medium-emphasis text-uppercase font-weight-bold tracking-widest">Filtros</span>
        </div>
        
        <v-divider vertical class="mx-2 hidden-sm-and-down"></v-divider>

        <v-autocomplete
          v-model="filters.agent_id"
          :items="agents"
          item-title="name"
          item-value="id"
          label="Agente"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="flex-grow-0"
          style="min-width: 200px"
          @update:model-value="fetchData"
        >
          <template v-slot:item="{ props, item }">
            <v-list-item v-bind="props" :title="item.raw.name">
              <template v-slot:prepend>
                <v-avatar size="24" color="primary" class="mr-2">
                  <span class="text-caption">{{ item.raw.name.charAt(0) }}</span>
                </v-avatar>
              </template>
            </v-list-item>
          </template>
        </v-autocomplete>
        
        <v-text-field
          v-model="filters.session_id"
          label="Session ID"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="flex-grow-0"
          style="min-width: 200px"
          @keyup.enter="fetchData"
          @click:clear="fetchData"
        ></v-text-field>

        <v-spacer></v-spacer>
        
        <v-btn 
          color="primary"
          variant="elevated" 
          prepend-icon="mdi-download"
          @click="exportData"
        >
          Exportar JSONL
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- Main Table -->
    <v-card class="glass-card">
      <v-data-table-server
        :headers="headers"
        :items="pairs"
        :items-length="totalPairs"
        :loading="loading"
        v-model:options="tableOptions"
        @update:options="fetchData"
        class="bg-transparent modern-table"
        hover
      >
        <template v-slot:item="{ item }">
          <tr @click="openDetails(item)" style="cursor: pointer;">
            <!-- Human -->
            <td class="py-3" style="max-width: 250px;">
              <div class="d-flex align-start gap-2">
                <v-avatar size="28" color="primary" class="mt-1 flex-shrink-0">
                  <v-icon icon="mdi-account" size="16" color="white"></v-icon>
                </v-avatar>
                <div class="text-truncate-2 text-body-2" :title="item.user_message?.content">
                  {{ item.user_message?.content || '[Sistema]' }}
                </div>
              </div>
            </td>

            <!-- AI -->
            <td class="py-3" style="max-width: 250px;">
              <div class="d-flex align-start gap-2">
                <v-avatar size="28" color="purple" class="mt-1 flex-shrink-0">
                  <v-icon icon="mdi-robot-outline" size="16" color="white"></v-icon>
                </v-avatar>
                <div>
                  <div class="text-truncate-2 text-body-2 mb-1" :title="item.assistant_message.content">
                    {{ item.assistant_message.content }}
                  </div>
                  <v-chip 
                    v-if="item.assistant_message.tool_trace" 
                    size="x-small" 
                    color="purple" 
                    variant="tonal"
                    prepend-icon="mdi-wrench-outline"
                  >
                    Tools ({{ item.assistant_message.tool_trace.tool_calls.length }})
                  </v-chip>
                </div>
              </div>
            </td>

            <!-- Classification Buttons -->
            <td class="py-3" @click.stop>
              <div class="d-flex gap-1 align-center">
                <v-btn
                  icon
                  size="small"
                  :variant="getEval(item).classification === 'relevant' ? 'elevated' : 'tonal'"
                  :color="getEval(item).classification === 'relevant' ? 'success' : 'default'"
                  @click="updateEval(item, 'classification', 'relevant')"
                  title="Relevante (Correta e boa)"
                >
                  <v-icon>mdi-thumb-up</v-icon>
                </v-btn>
                <v-btn
                  icon
                  size="small"
                  :variant="getEval(item).classification === 'indifferent' ? 'elevated' : 'tonal'"
                  :color="getEval(item).classification === 'indifferent' ? 'warning' : 'default'"
                  @click="updateEval(item, 'classification', 'indifferent')"
                  title="Indiferente (Ignorar)"
                >
                  <v-icon>mdi-minus</v-icon>
                </v-btn>
                <v-btn
                  icon
                  size="small"
                  :variant="getEval(item).classification === 'irrelevant' ? 'elevated' : 'tonal'"
                  :color="getEval(item).classification === 'irrelevant' ? 'error' : 'default'"
                  @click="updateEval(item, 'classification', 'irrelevant')"
                  title="Irrelevante (Errada ou ruim)"
                >
                  <v-icon>mdi-thumb-down</v-icon>
                </v-btn>
              </div>
            </td>

            <!-- Score -->
            <td class="py-3" @click.stop style="min-width: 150px;">
              <div class="d-flex align-center gap-2">
                <v-slider
                  :model-value="getEval(item).score || 0"
                  @update:model-value="(val) => updateEvalDebounced(item, 'score', val)"
                  min="0"
                  max="100"
                  step="5"
                  hide-details
                  class="flex-grow-1"
                  color="primary"
                  thumb-label
                ></v-slider>
                <span class="text-caption font-weight-bold" style="width: 30px; text-align: right">
                  {{ getEval(item).score || 0 }}
                </span>
              </div>
            </td>

            <!-- Topic -->
            <td class="py-3" @click.stop style="min-width: 200px;">
              <v-combobox
                :model-value="getEval(item).topic"
                @update:model-value="(val) => updateEvalDebounced(item, 'topic', val)"
                :items="availableTopics"
                label="Tema"
                variant="underlined"
                density="compact"
                hide-details
                placeholder="Ex: Financeiro"
              ></v-combobox>
            </td>
          </tr>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- Details Dialog -->
    <v-dialog v-model="detailsDialog" max-width="900" scrollable>
      <v-card class="glass-card" v-if="selectedPair">
        <v-card-title class="d-flex align-center justify-space-between pa-4 border-b">
          <div class="d-flex align-center gap-3">
            <v-icon icon="mdi-forum-outline" color="primary"></v-icon>
            <span class="font-weight-bold">Detalhes da Interação</span>
            <v-chip size="small" variant="outlined" color="primary" class="ml-2">
              Sessão: {{ selectedPair.session_id.substring(0, 8) }}...
            </v-chip>
          </div>
          <v-btn icon="mdi-close" variant="text" @click="detailsDialog = false"></v-btn>
        </v-card-title>

        <v-card-text class="pa-0" style="height: 600px;">
          <v-container fluid class="pa-6">
            <v-row>
              <!-- Left Col: Conversation & Trace -->
              <v-col cols="12" md="7">
                <div class="text-subtitle-2 text-medium-emphasis mb-4 text-uppercase tracking-widest font-weight-bold">
                  Transcrição
                </div>

                <!-- User Bubble -->
                <div v-if="selectedPair.user_message" class="d-flex flex-column align-end mb-6">
                  <div class="d-flex align-center gap-2 mb-1">
                    <span class="text-caption text-medium-emphasis">Humano</span>
                    <v-avatar size="24" color="primary">
                      <v-icon icon="mdi-account" size="14" color="white"></v-icon>
                    </v-avatar>
                  </div>
                  <v-sheet class="pa-4 rounded-xl rounded-tr-0 bg-primary-lighten text-body-1 shadow-sm text-pre-wrap" style="max-width: 90%;">
                    {{ selectedPair.user_message.content }}
                  </v-sheet>
                  <span class="text-caption text-medium-emphasis mt-1">{{ formatDate(selectedPair.user_message.created_at) }}</span>
                </div>

                <!-- Tools Bubble -->
                <div v-if="selectedPair.assistant_message.tool_trace" class="d-flex flex-column align-start mb-6">
                  <div class="d-flex align-center gap-2 mb-1">
                    <v-avatar size="24" color="purple" variant="tonal">
                      <v-icon icon="mdi-wrench-outline" size="14" color="purple"></v-icon>
                    </v-avatar>
                    <span class="text-caption text-purple font-weight-bold">Pensamento & Ferramentas</span>
                  </div>
                  <v-sheet class="pa-4 rounded-xl rounded-tl-0 bg-surface-variant text-body-2 shadow-sm" style="max-width: 90%; border: 1px solid rgba(124, 58, 237, 0.2);">
                    <div class="mb-2 text-caption">
                      <v-chip size="x-small" color="purple" variant="flat" class="mr-2">Modo: {{ selectedPair.assistant_message.tool_trace.execution_mode }}</v-chip>
                      <span class="text-medium-emphasis">Modelo: {{ selectedPair.assistant_message.tool_trace.model }}</span>
                    </div>
                    
                    <div v-for="(call, idx) in selectedPair.assistant_message.tool_trace.tool_calls" :key="idx" class="mb-3">
                      <div class="font-weight-bold text-purple-lighten-2 d-flex align-center gap-1">
                        <v-icon icon="mdi-function" size="14"></v-icon>
                        {{ call.name }}
                      </div>
                      <div class="bg-black pa-2 rounded mt-1 overflow-x-auto" style="font-family: monospace; font-size: 11px;">
                        <div class="text-grey">Args:</div>
                        <pre class="text-green">{{ JSON.stringify(call.args, null, 2) }}</pre>
                        
                        <div class="text-grey mt-2">Result:</div>
                        <div class="text-white text-pre-wrap" style="max-height: 100px; overflow-y: auto;">
                          {{ call.result_preview }}
                        </div>
                      </div>
                    </div>
                  </v-sheet>
                </div>

                <!-- AI Bubble -->
                <div class="d-flex flex-column align-start mb-6">
                  <div class="d-flex align-center gap-2 mb-1">
                    <v-avatar size="24" color="purple">
                      <v-icon icon="mdi-robot-outline" size="14" color="white"></v-icon>
                    </v-avatar>
                    <span class="text-caption text-medium-emphasis">Assistente</span>
                  </div>
                  <v-sheet class="pa-4 rounded-xl rounded-tl-0 bg-surface text-body-1 shadow-sm text-pre-wrap" style="max-width: 90%; border: 1px solid rgba(255,255,255,0.05);">
                    {{ selectedPair.assistant_message.content }}
                  </v-sheet>
                  <span class="text-caption text-medium-emphasis mt-1">{{ formatDate(selectedPair.assistant_message.created_at) }}</span>
                </div>
              </v-col>

              <!-- Right Col: Annotation Form -->
              <v-col cols="12" md="5" class="border-l pl-md-6">
                <div class="text-subtitle-2 text-medium-emphasis mb-4 text-uppercase tracking-widest font-weight-bold d-flex align-center gap-2">
                  <v-icon icon="mdi-pencil-box-outline" size="18"></v-icon>
                  Anotação
                </div>

                <v-card variant="flat" class="bg-surface-variant pa-4 rounded-lg mb-4">
                  <div class="text-caption mb-2">Classificação</div>
                  <div class="d-flex gap-2">
                    <v-btn
                      class="flex-grow-1"
                      :variant="getEval(selectedPair).classification === 'relevant' ? 'elevated' : 'tonal'"
                      :color="getEval(selectedPair).classification === 'relevant' ? 'success' : 'default'"
                      @click="updateEval(selectedPair, 'classification', 'relevant')"
                      prepend-icon="mdi-thumb-up"
                    >Relevante</v-btn>
                    <v-btn
                      class="flex-grow-1"
                      :variant="getEval(selectedPair).classification === 'indifferent' ? 'elevated' : 'tonal'"
                      :color="getEval(selectedPair).classification === 'indifferent' ? 'warning' : 'default'"
                      @click="updateEval(selectedPair, 'classification', 'indifferent')"
                      prepend-icon="mdi-minus"
                    >Indiferente</v-btn>
                    <v-btn
                      class="flex-grow-1"
                      :variant="getEval(selectedPair).classification === 'irrelevant' ? 'elevated' : 'tonal'"
                      :color="getEval(selectedPair).classification === 'irrelevant' ? 'error' : 'default'"
                      @click="updateEval(selectedPair, 'classification', 'irrelevant')"
                      prepend-icon="mdi-thumb-down"
                    >Irrelevante</v-btn>
                  </div>

                  <div class="mt-4">
                    <div class="text-caption mb-1 d-flex justify-space-between">
                      <span>Nota (Qualidade da Resposta)</span>
                      <span class="font-weight-bold text-primary">{{ getEval(selectedPair).score || 0 }}</span>
                    </div>
                    <v-slider
                      :model-value="getEval(selectedPair).score || 0"
                      @update:model-value="(val) => updateEvalDebounced(selectedPair, 'score', val)"
                      min="0"
                      max="100"
                      step="5"
                      hide-details
                      color="primary"
                    ></v-slider>
                  </div>

                  <div class="mt-2">
                    <v-combobox
                      :model-value="getEval(selectedPair).topic"
                      @update:model-value="(val) => updateEvalDebounced(selectedPair, 'topic', val)"
                      :items="availableTopics"
                      label="Tema/Categoria"
                      variant="outlined"
                      density="compact"
                      hide-details
                    ></v-combobox>
                  </div>
                </v-card>

                <div class="mb-4">
                  <div class="text-caption mb-1">Instrução de Ferramentas (Como a IA deveria ter agido)</div>
                  <v-textarea
                    :model-value="getEval(selectedPair).tool_instruction"
                    @update:model-value="(val) => updateEvalDebounced(selectedPair, 'tool_instruction', val)"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    auto-grow
                    hide-details
                    placeholder="Ex: O agente deveria ter usado consultar_financeiro para buscar faturas pagas..."
                  ></v-textarea>
                </div>

                <div>
                  <div class="text-caption mb-1">Resposta Esperada (Ideal)</div>
                  <v-textarea
                    :model-value="getEval(selectedPair).expected_response"
                    @update:model-value="(val) => updateEvalDebounced(selectedPair, 'expected_response', val)"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    hide-details
                    placeholder="Se a resposta foi irrelevante/ruim, escreva aqui a resposta ideal para treinamento..."
                  ></v-textarea>
                </div>

                <div class="mt-6 text-center text-caption text-medium-emphasis">
                  <v-icon icon="mdi-check-circle" color="success" size="14" class="mr-1"></v-icon>
                  Salvo automaticamente
                </div>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { qaEvalService } from '@/services/qaEvalService'
import { agentService } from '@/services/agentService'
import _debounce from 'lodash/debounce' // Precisa instalar/ter lodash se não houver, ou implementamos manual

// Refs and Data
const loading = ref(false)
const pairs = ref([])
const totalPairs = ref(0)
const stats = ref({})
const availableTopics = ref([])
const agents = ref([])
const detailsDialog = ref(false)
const selectedPair = ref(null)

// Table Options
const tableOptions = ref({
  page: 1,
  itemsPerPage: 20,
})

// Filters
const filters = ref({
  agent_id: null,
  session_id: '',
})

// Headers
const headers = [
  { title: 'Pergunta Humana', key: 'user_message', sortable: false, width: '25%' },
  { title: 'Resposta IA', key: 'assistant_message', sortable: false, width: '25%' },
  { title: 'Classificação', key: 'eval.classification', sortable: false, align: 'center', width: '150px' },
  { title: 'Nota', key: 'eval.score', sortable: false, width: '150px' },
  { title: 'Tema', key: 'eval.topic', sortable: false },
]

// Methods
const fetchAgents = async () => {
  try {
    const response = await agentService.getAgents()
    agents.value = response.data
  } catch (error) {
    console.error("Error loading agents:", error)
  }
}

const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      page: tableOptions.value.page,
      page_size: tableOptions.value.itemsPerPage,
      agent_id: filters.value.agent_id || undefined,
      session_id: filters.value.session_id || undefined,
    }
    
    const [pairsRes, statsRes, topicsRes] = await Promise.all([
      qaEvalService.getPairs(params),
      qaEvalService.getStats({ agent_id: params.agent_id }),
      qaEvalService.getTopics()
    ])

    pairs.value = pairsRes.data.pairs
    totalPairs.value = pairsRes.data.total
    stats.value = statsRes.data
    availableTopics.value = topicsRes.data.topics.map(t => t.topic)
    
  } catch (error) {
    console.error("Error loading QA Eval data:", error)
  } finally {
    loading.value = false
  }
}

const openDetails = (item) => {
  selectedPair.value = item
  detailsDialog.value = true
}

const getEval = (item) => {
  if (!item.evaluation) {
    // Initial empty state
    item.evaluation = {
      classification: 'indifferent',
      score: 50,
      topic: '',
      expected_response: '',
      tool_instruction: '',
    }
  }
  return item.evaluation
}

const saveEvaluation = async (item) => {
  try {
    const evalData = getEval(item)
    const payload = {
      message_id: item.assistant_message.id,
      pair_message_id: item.user_message?.id,
      agent_id: item.agent_id,
      session_id: item.session_id,
      original_question: item.user_message?.content || '[Sistema]',
      original_answer: item.assistant_message.content,
      tool_trace: item.assistant_message.tool_trace,
      ...evalData
    }
    
    const response = await qaEvalService.createEvaluation(payload)
    if (response.data.evaluation) {
      item.evaluation = response.data.evaluation
    }
    
    // Refresh stats implicitly silently
    qaEvalService.getStats({ agent_id: filters.value.agent_id }).then(res => {
      stats.value = res.data
    })
    
  } catch (error) {
    console.error("Error saving evaluation:", error)
  }
}

// Custom debouncer in case lodash is not available
const debounce = (fn, delay) => {
  let timeoutID = null
  return function () {
    clearTimeout(timeoutID)
    const args = arguments
    const that = this
    timeoutID = setTimeout(function () {
      fn.apply(that, args)
    }, delay)
  }
}

const doSaveEvalDebounced = debounce((item) => {
  saveEvaluation(item)
}, 600)

const updateEval = (item, field, value) => {
  const ev = getEval(item)
  ev[field] = value
  saveEvaluation(item) // Immediate save for classification buttons
}

const updateEvalDebounced = (item, field, value) => {
  const ev = getEval(item)
  ev[field] = value
  doSaveEvalDebounced(item) // Debounced save for sliders/text
}

const exportData = async () => {
  try {
    const response = await qaEvalService.exportData({
      min_score: 80,
      classification: 'relevant',
      format: 'jsonl'
    })
    
    // Create blob link to download
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    const dateStr = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19)
    link.setAttribute('download', `qa_eval_export_${dateStr}.jsonl`)
    document.body.appendChild(link)
    link.click()
    link.parentNode.removeChild(link)
    
  } catch (error) {
    console.error("Error exporting data:", error)
  }
}

const formatDate = (isoString) => {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString('pt-BR')
}

onMounted(() => {
  fetchAgents()
  fetchData()
})

</script>

<style scoped>
.text-truncate-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;  
  overflow: hidden;
}
.text-pre-wrap {
  white-space: pre-wrap;
}
.gap-1 { gap: 4px; }
.gap-2 { gap: 8px; }
.gap-3 { gap: 12px; }
.gap-4 { gap: 16px; }

.modern-table :deep(th) {
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7) !important;
}

.modern-table :deep(tr:hover) {
  background: rgba(255, 255, 255, 0.03) !important;
}

.bg-primary-lighten {
  background-color: rgba(var(--v-theme-primary), 0.15) !important;
}

.shadow-sm {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>
