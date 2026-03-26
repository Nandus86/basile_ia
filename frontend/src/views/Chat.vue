<template>
  <div class="chat-wrapper glass-card d-flex flex-column fill-height">
    <!-- Chat Toolbar -->
    <v-toolbar color="transparent" density="compact" class="chat-toolbar border-b">
      <v-btn icon color="medium-emphasis" @click="showSettings = !showSettings">
        <v-icon>{{ showSettings ? 'mdi-backburger' : 'mdi-menu' }}</v-icon>
        <v-tooltip activator="parent" location="bottom">Toggle Settings</v-tooltip>
      </v-btn>
      
      <v-toolbar-title class="ml-2">
        <div class="d-flex align-center">
          <v-icon color="primary" class="mr-2">mdi-chat-processing</v-icon>
          <span class="text-subtitle-1 font-weight-bold d-none d-sm-flex">Chat Playground</span>
          
          <v-chip class="ml-2 ml-sm-4 d-none d-sm-inline-flex" size="x-small" :color="selectedAgentId ? 'primary' : 'secondary'" variant="tonal">
            {{ getAgentName(selectedAgentId) || 'Auto Orchestrator' }}
          </v-chip>
          
          <v-chip class="ml-2" size="x-small" :color="getLevelColor(userAccessLevel)" variant="outlined">
            {{ getLevelLabel(userAccessLevel) }}
          </v-chip>
        </div>
      </v-toolbar-title>

      <v-spacer></v-spacer>

      <v-btn icon color="error" variant="text" @click="clearChat">
        <v-icon>mdi-delete-sweep-outline</v-icon>
        <v-tooltip activator="parent" location="bottom">Limpar Chat</v-tooltip>
      </v-btn>
    </v-toolbar>

    <v-layout class="flex-grow-1 overflow-hidden position-relative">
      <!-- Settings Sidebar -->
      <v-navigation-drawer
        v-model="showSettings"
        width="320"
        :temporary="mobile"
        :permanent="!mobile"
        class="settings-drawer border-e"
        elevation="0"
      >
        <v-list class="pa-4 bg-transparent" lines="two">
          <v-list-subheader class="text-uppercase font-weight-bold text-caption mb-2">Configuração da Sessão</v-list-subheader>
          
          <!-- Session -->
          <v-card variant="outlined" class="mb-4 rounded-lg bg-surface">
            <v-card-text class="pa-3">
              <v-text-field
                v-model="sessionId"
                label="Session ID"
                density="compact"
                variant="plain"
                hide-details
                readonly
                append-inner-icon="mdi-identifier"
              >
                <template v-slot:append>
                  <v-btn icon="mdi-refresh" variant="text" size="small" color="primary" @click="regenerateSession"></v-btn>
                </template>
              </v-text-field>
            </v-card-text>
          </v-card>

          <!-- Access Level -->
          <div class="mb-6">
            <div class="text-caption text-medium-emphasis mb-2 font-weight-medium">NÍVEL DE ACESSO</div>
            <v-btn-toggle
              v-model="userAccessLevel"
              mandatory
              density="compact"
              color="primary"
              variant="outlined"
              class="d-flex flex-wrap w-100 rounded-lg overflow-hidden"
              divided
            >
              <v-btn value="minimum" class="flex-grow-1 text-caption">Mínimo</v-btn>
              <v-btn value="normal" class="flex-grow-1 text-caption">Normal</v-btn>
              <v-btn value="pro" class="flex-grow-1 text-caption">Pro</v-btn>
              <v-btn value="premium" class="flex-grow-1 text-caption">Premium</v-btn>
            </v-btn-toggle>
          </div>

          <!-- Agent Selector -->
          <div class="mb-6">
            <div class="text-caption text-medium-emphasis mb-2 font-weight-medium">AGENTE ESPECÍFICO</div>
            <v-select
              v-model="selectedAgentId"
              :items="agentOptions"
              item-title="name"
              item-value="id"
              placeholder="Orquestrador Automático (Padrão)"
              variant="outlined"
              density="compact"
              hide-details
              bg-color="surface"
              clearable
              rounded="lg"
            >
              <template v-slot:item="{ item, props }">
                <v-list-item v-bind="props" :subtitle="getLevelLabel(item.raw.access_level)">
                  <template v-slot:prepend>
                     <v-icon :color="getLevelColor(item.raw.access_level)">mdi-robot</v-icon>
                  </template>
                </v-list-item>
              </template>
            </v-select>
          </div>

          <!-- Context Data -->
          <div class="mb-4">
             <div class="d-flex align-center justify-space-between mb-2">
               <div class="text-caption text-medium-emphasis font-weight-medium">SIMULADOR DE WEBHOOK (JSON)</div>
               <v-btn variant="text" size="x-small" color="primary" @click="contextDialog = true">Editar</v-btn>
             </div>
             <v-card 
               variant="tonal" 
               color="secondary" 
               class="rounded-lg pa-2 cursor-pointer context-preview"
               @click="contextDialog = true"
               link
             >
               <pre class="text-caption ma-0 text-truncate">{{ contextDataJson || '{}' }}</pre>
             </v-card>
          </div>
        </v-list>

        <!-- Stats Footer -->
        <template v-slot:append>
          <div class="pa-4 bg-surface-light border-t">
            <div class="d-flex justify-space-between text-caption mb-1">
              <span class="text-medium-emphasis">Última Latência:</span>
              <span :class="getLatencyColor(lastProcessingTime)">{{ lastProcessingTime.toFixed(0) }}ms</span>
            </div>
            <div class="d-flex justify-space-between text-caption">
              <span class="text-medium-emphasis">Agente Usado:</span>
              <span class="font-weight-medium text-truncate" style="max-width: 120px">{{ lastAgentUsed || '-' }}</span>
            </div>
          </div>
        </template>
      </v-navigation-drawer>

      <!-- Main Chat Area -->
      <v-main class="chat-main fill-height d-flex flex-column position-relative" style="background: transparent;">
        <!-- Messages Scroll Area -->
        <div class="messages-scroll-area flex-grow-1 overflow-y-auto px-4 py-6" ref="messagesContainer">
          <v-container class="pa-0" style="max-width: 800px;">
            
            <!-- Empty State -->
            <div v-if="messages.length === 0" class="empty-state text-center py-12 opacity-60">
              <v-avatar color="primary" variant="tonal" size="80" class="mb-6">
                <v-icon size="40">mdi-robot-excited-outline</v-icon>
              </v-avatar>
              <h2 class="text-h5 font-weight-bold mb-2">Como posso ajudar hoje?</h2>
              <p class="text-body-1 mb-8 text-medium-emphasis">Selecione um prompt abaixo ou digite sua pergunta.</p>
              
              <div class="d-flex flex-wrap justify-center gap-3">
                <v-card
                  v-for="prompt in quickPrompts"
                  :key="prompt"
                  class="prompt-card px-4 py-3"
                  variant="outlined"
                  link
                  @click="sendQuickPrompt(prompt)"
                >
                  {{ prompt }}
                </v-card>
              </div>
            </div>

            <!-- Messages List -->
            <div v-else class="messages-list d-flex flex-column gap-6">
              <div
                v-for="(msg, index) in messages"
                :key="index"
                class="message-row d-flex gap-4"
                :class="{ 'justify-end': msg.role === 'user' }"
              >
                <!-- Assistant Avatar -->
                <v-avatar 
                   v-if="msg.role === 'assistant'" 
                   color="surface" 
                   size="36" 
                   class="elevation-1 align-self-start mt-1"
                >
                  <v-icon size="20" color="primary">mdi-robot</v-icon>
                </v-avatar>

                <!-- Message Bubble -->
                <div class="message-bubble-wrapper" :class="{ 'user-wrapper': msg.role === 'user' }">
                   <div class="d-flex align-center mb-1 ml-1" v-if="msg.role !== 'user'">
                     <span class="text-caption font-weight-bold text-primary mr-2">{{ msg.agent || 'Basile AI' }}</span>
                     <span class="text-xs text-medium-emphasis">{{ msg.time }}</span>
                   </div>
                   
                   <v-sheet
                     class="message-bubble pa-4 text-body-1"
                     :color="msg.role === 'user' ? 'primary' : 'surface'"
                     elevation="1"
                     rounded="lg"
                   >
                     <div v-if="msg.role === 'assistant'" v-html="formatMessage(msg.content)" class="markdown-content"></div>
                     <div v-else>{{ msg.content }}</div>
                   </v-sheet>
                   
                   <!-- Metadata Footer and Thumbs -->
                   <div class="d-flex align-center justify-space-between mt-1 mr-1" v-if="msg.role === 'assistant'">
                     <div>
                       <!-- Thumbs Buttons -->
                       <v-btn
                         v-if="!msg.feedback"
                         icon="mdi-thumb-up-outline"
                         size="x-small"
                         variant="text"
                         color="success"
                         class="mr-1"
                         @click="submitFeedback(msg, 'positive')"
                         :loading="msg.feedbackLoading === 'positive'"
                         :disabled="!!msg.feedbackLoading"
                         title="Resposta excelente. O agente deve aprender este padrão."
                       ></v-btn>
                       <v-btn
                         v-if="!msg.feedback"
                         icon="mdi-thumb-down-outline"
                         size="x-small"
                         variant="text"
                         color="error"
                         @click="submitFeedback(msg, 'negative')"
                         :loading="msg.feedbackLoading === 'negative'"
                         :disabled="!!msg.feedbackLoading"
                         title="Resposta ruim. O agente deve evitar este padrão."
                       ></v-btn>
                       <!-- Feedback registered indicator -->
                       <span v-if="msg.feedback === 'positive'" class="text-caption text-success ml-1"><v-icon size="small" class="mr-1">mdi-check-circle</v-icon> Aprendizado salvo</span>
                       <span v-if="msg.feedback === 'negative'" class="text-caption text-error ml-1"><v-icon size="small" class="mr-1">mdi-alert-circle</v-icon> Correção salva</span>
                     </div>
                     
                     <span v-if="msg.processingTime" class="text-xs text-disabled d-flex align-center justify-end">
                       <v-icon size="10" class="mr-1">mdi-timer-outline</v-icon>
                       {{ (msg.processingTime / 1000).toFixed(2) }}s
                     </span>
                   </div>
                </div>

                <!-- User Avatar -->
                <v-avatar 
                   v-if="msg.role === 'user'" 
                   color="primary-darken-1" 
                   size="36"
                   class="align-self-start mt-1 elevation-1"
                >
                  <span class="text-caption font-weight-bold text-white">EU</span>
                </v-avatar>
              </div>

              <!-- Loading Indicator -->
              <div v-if="loading" class="d-flex gap-4">
                 <v-avatar color="surface" size="36" class="elevation-1">
                   <v-progress-circular indeterminate color="primary" size="20" width="2"></v-progress-circular>
                 </v-avatar>
                 <div class="typing-indicator-bubble bg-surface rounded-lg px-4 py-3 elevation-1">
                   <span class="dot"></span>
                   <span class="dot"></span>
                   <span class="dot"></span>
                 </div>
              </div>
            </div>
            
            <div style="height: 100px;"></div> <!-- Spacer for footer -->
          </v-container>
        </div>

        <!-- Sticky Footer Input -->
        <div class="chat-input-footer bg-surface border-t py-4">
          <v-container style="max-width: 800px;" class="px-4">
            <v-textarea
              v-model="inputMessage"
              placeholder="Digite sua mensagem aqui..."
              variant="outlined"
              rounded="xl"
              auto-grow
              rows="1"
              max-rows="6"
              hide-details
              bg-color="background"
              class="chat-input"
              density="comfortable"
              @keydown.enter.exact.prevent="sendMessage"
              @keydown.enter.shift.exact="inputMessage += '\n'"
              :disabled="loading"
              autofocus
            >
              <template v-slot:append-inner>
                 <v-btn 
                   icon="mdi-send" 
                   variant="text" 
                   color="primary" 
                   @click="sendMessage"
                   :disabled="!inputMessage.trim() || loading"
                   class="mb-1"
                 ></v-btn>
              </template>
            </v-textarea>
            <div class="text-center mt-2">
              <span class="text-caption text-disabled">Pressione Enter para enviar, Shift+Enter para quebrar linha</span>
            </div>
          </v-container>
        </div>
      </v-main>
    </v-layout>

    <!-- Context Data Dialog -->
    <v-dialog v-model="contextDialog" maxWidth="600">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center px-6 py-4 border-b">
          <v-icon color="primary" class="mr-2">mdi-webhook</v-icon>
          Simulador de Webhook (JSON)
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="contextDialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="pa-0">
          <div class="bg-surface-light px-6 py-2 border-b">
            <p class="text-caption text-medium-emphasis mb-2">O JSON digitado abaixo será injetado na raiz do payload (junto com a mensagem do chat e a sessão). Você pode simular dados contextuais, transition_data, callback_url e metadados customizados.</p>
            <div class="d-flex gap-2 align-center">
              <span class="text-caption font-weight-bold">Presets:</span>
              <v-chip size="x-small" label link @click="applyContextPreset('church')">Apenas ContextData</v-chip>
              <v-chip size="x-small" label link @click="applyContextPreset('whatsapp')">Ex. WhatsApp</v-chip>
              <v-chip size="x-small" label link color="primary" @click="applyContextPreset('full_webhook')">Webhook Completo</v-chip>
              <v-separator vertical class="mx-1"></v-separator>
              <v-chip size="x-small" label link @click="applyContextPreset('clear')" color="error" variant="text">Limpar</v-chip>
            </div>
          </div>
          <div class="pa-4">
            <v-textarea
              v-model="contextDataJson"
              label="JSON"
              variant="outlined"
              rows="10"
              class="font-monospace"
              :rules="[validateContextJson]"
              :error-messages="contextDataError"
            ></v-textarea>
          </div>
        </v-card-text>
        <v-card-actions class="px-6 py-4 border-t bg-surface-light">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="contextDialog = false">Cancelar</v-btn>
          <v-btn color="primary" variant="flat" @click="saveContextData" :disabled="!!contextDataError">Salvar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Training Dialog (3 Boxes) -->
    <v-dialog v-model="trainingDialog" maxWidth="700" persistent>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center px-6 py-4 border-b">
          <v-icon :color="trainingType === 'positive' ? 'success' : 'error'" class="mr-2">
            {{ trainingType === 'positive' ? 'mdi-school' : 'mdi-shield-alert' }}
          </v-icon>
          Treinamento Manual (RLHF)
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="trainingDialog = false"></v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <p class="text-body-2 text-medium-emphasis mb-4">
            O feedback automático já foi salvo. Opcionalmente, adicione regras manuais nos campos abaixo.
          </p>

          <!-- Box 1: User Training -->
          <v-card variant="outlined" class="mb-4 rounded-lg">
            <v-card-text>
              <div class="d-flex align-center mb-2">
                <v-icon color="blue" size="20" class="mr-2">mdi-account</v-icon>
                <span class="text-subtitle-2 font-weight-medium">Regra do Usuário</span>
                <v-chip size="x-small" class="ml-2" color="blue" variant="tonal">contact_id</v-chip>
              </div>
              <v-textarea
                v-model="trainingForm.contact_rule"
                placeholder="Ex: Este usuário prefere respostas curtas e diretas."
                variant="outlined"
                density="compact"
                rows="2"
                auto-grow
                hide-details
              ></v-textarea>
            </v-card-text>
          </v-card>

          <!-- Box 2: Agent Training -->
          <v-card variant="outlined" class="mb-4 rounded-lg">
            <v-card-text>
              <div class="d-flex align-center mb-2">
                <v-icon color="purple" size="20" class="mr-2">mdi-robot</v-icon>
                <span class="text-subtitle-2 font-weight-medium">Regra do Agente</span>
                <v-chip size="x-small" class="ml-2" color="purple" variant="tonal">agent_id</v-chip>
              </div>
              <v-textarea
                v-model="trainingForm.agent_rule"
                placeholder="Ex: Sempre cumprimente o usuário pelo nome antes de responder."
                variant="outlined"
                density="compact"
                rows="2"
                auto-grow
                hide-details
              ></v-textarea>
            </v-card-text>
          </v-card>

          <!-- Box 3: Entity Training -->
          <v-card variant="outlined" class="rounded-lg" color="teal-lighten-5">
            <v-card-text>
              <div class="d-flex align-center mb-2">
                <v-icon color="teal" size="20" class="mr-2">mdi-domain</v-icon>
                <span class="text-subtitle-2 font-weight-medium">Regra da Entidade</span>
                <v-chip size="x-small" class="ml-2" color="teal" variant="tonal">entity_id</v-chip>
              </div>
              
              <v-text-field
                v-model="trainingForm.entity_path"
                label="Caminho do Payload"
                placeholder="$request.church._id"
                variant="outlined"
                density="compact"
                prepend-inner-icon="mdi-code-json"
                hide-details
                class="mb-3"
                @update:modelValue="resolveEntityPath"
              >
                <template v-slot:append-inner>
                  <v-chip 
                    v-if="trainingForm.resolved_entity_id" 
                    size="x-small" 
                    color="teal" 
                    variant="flat"
                  >
                    = {{ trainingForm.resolved_entity_id }}
                  </v-chip>
                  <v-icon v-else-if="trainingForm.entity_path" color="warning" size="small">mdi-alert-circle-outline</v-icon>
                </template>
              </v-text-field>
              
              <v-textarea
                v-model="trainingForm.entity_rule"
                placeholder="Ex: Para esta igreja, sempre usar tom formal e mencionar o pastor pelo nome."
                variant="outlined"
                density="compact"
                rows="2"
                auto-grow
                hide-details
                :disabled="!trainingForm.resolved_entity_id && !!trainingForm.entity_path"
              ></v-textarea>
              
              <p v-if="trainingForm.entity_path && !trainingForm.resolved_entity_id" class="text-caption text-warning mt-1">
                ⚠️ Caminho não encontrado no payload desta mensagem.
              </p>
            </v-card-text>
          </v-card>
        </v-card-text>
        
        <v-card-actions class="px-6 py-4 border-t bg-surface-light">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="trainingDialog = false">Pular</v-btn>
          <v-btn color="primary" variant="flat" @click="submitTraining">
            <v-icon start>mdi-brain</v-icon>
            Salvar Treinamento
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top center">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useDisplay } from 'vuetify'
import axios from '@/plugins/axios'

const { mobile } = useDisplay()

// UI State
const showSettings = ref(!mobile.value)
const contextDialog = ref(false)
const loading = ref(false)
const snackbar = reactive({ show: false, message: '', color: 'success' })
const messagesContainer = ref(null)

// Chat State
const messages = ref([])
const inputMessage = ref('')
const sessionId = ref(generateSessionId())
const userAccessLevel = ref('normal')
const selectedAgentId = ref(null)
const agents = ref([])
const lastProcessingTime = ref(0)
const lastAgentUsed = ref(null)

// Context Data
const contextDataJson = ref('')
const contextDataError = ref('')
let debounceTimer = null

// Constants
const quickPrompts = [
  'Olá! Quem é você?',
  'Analise este texto para mim...',
  'Crie um resumo sobre IA',
  'Me ajude com uma tarefa complexa'
]

// Computed
const agentOptions = computed(() => {
  return agents.value.map(a => ({
    id: a.id,
    name: a.name,
    access_level: a.access_level
  }))
})

// Methods
function generateSessionId() {
  return 'chat_' + Math.random().toString(36).substr(2, 9)
}

function regenerateSession() {
  sessionId.value = generateSessionId()
  messages.value = []
  lastProcessingTime.value = 0
  lastAgentUsed.value = null
  showNotification('Nova sessão criada', 'info')
}

// ... Fetch Agents, Send Message (Similar logic, updated for UI) ...

function getLevelColor(level) {
  const map = { minimum: 'grey', normal: 'success', pro: 'warning', premium: 'purple' }
  return map[level] || 'grey'
}

function getLevelLabel(level) {
  return level.charAt(0).toUpperCase() + level.slice(1)
}

function getAgentName(id) {
  return agents.value.find(a => a.id === id)?.name
}

function getLatencyColor(ms) {
  if (ms < 1000) return 'text-success'
  if (ms < 3000) return 'text-warning'
  return 'text-error'
}

function formatMessage(text) {
  if (!text) return ''
  // Basic markdown standardizer
  let html = text
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/```([\s\S]*?)```/g, '<div class="code-block">$1</div>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    
  return html
}

function showNotification(msg, color = 'success') {
  snackbar.message = msg
  snackbar.color = color
  snackbar.show = true
}

// Context Data Logic
function validateContextJson(val) {
  if (!val.trim()) return true
  try {
    JSON.parse(val)
    return true
  } catch (e) {
    return e instanceof SyntaxError ? `Erro de sintaxe JSON: ${e.message}` : 'JSON inválido'
  }
}

function debounceValidate() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    const val = contextDataJson.value
    if (!val.trim()) {
      contextDataError.value = ''
      localStorage.removeItem('chat_context_data')
      return
    }
    try {
      JSON.parse(val)
      contextDataError.value = ''
      localStorage.setItem('chat_context_data', val)
    } catch (e) {
      contextDataError.value = e instanceof SyntaxError ? `Sintaxe inválida: ${e.message}` : 'JSON inválido'
    }
  }, 300)
}

watch(contextDataJson, debounceValidate)

onMounted(() => {
  fetchAgents()
  const savedContext = localStorage.getItem('chat_context_data')
  if (savedContext) {
    contextDataJson.value = savedContext
  }
})

function applyContextPreset(type) {
  if (type === 'clear') {
    contextDataJson.value = ''
    return
  }
  const presets = {
    church: {
      context_data: { nome: "Maria", grupo: "Louvor", id: 123 }
    },
    whatsapp: {
      client: "whatsapp",
      number: "551199999999",
      contact_name: "João da Silva",
      context_data: { ultima_compra: "2023-10-01" }
    },
    full_webhook: {
      context_data: { 
        tenant_id: "T-001",
        user_role: "admin",
        details: "dados de configuração que o Agente precisa ler livremente"
      },
      transition_data: {
        current_step: "suporte_nivel_2",
        ticket_id: "TK-908"
      },
      callback_url: "https://minha-api.com/webhook/callback",
      system: {
        baseUrl: "https://sistema.interno",
        token: "XYZ123..."
      },
      custom_metadata: "informação extra",
      channel: "web_widget"
    }
  }
  contextDataJson.value = JSON.stringify(presets[type], null, 2)
}

function saveContextData() {
  if (!contextDataError.value) contextDialog.value = false
}

// API Calls
async function fetchAgents() {
  try {
    const res = await axios.get('/agents')
    agents.value = res.data.agents
  } catch (e) {
    console.error(e)
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function sendMessage() {
  const text = inputMessage.value.trim()
  if (!text || loading.value) return
  
  const userMsg = {
    role: 'user',
    content: text,
    time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  }
  
  messages.value.push(userMsg)
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()
  
  try {
    // Base payload
    let payload = {
      message: text,
      session_id: sessionId.value,
      agent_id: selectedAgentId.value,
      user_access_level: userAccessLevel.value
    }
    
    // Injetar dados do simulador de webhook na raiz do payload
    if (contextDataJson.value) {
      try {
        const injectedData = JSON.parse(contextDataJson.value);
        payload = { ...payload, ...injectedData };
      } catch(e) {
        console.warn("JSON do simulador inválido", e);
      }
    }

    const res = await axios.post('/webhook/process', payload)
    
    // Get the payload that was sent (for entity path resolution later)
    const sentPayload = { ...payload }
    
    messages.value.push({
      role: 'assistant',
      content: res.data.response,
      agent: res.data.agent_used,
      agent_id: payload.agent_id,
      processingTime: res.data.processing_time_ms,
      time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
      jobPayload: sentPayload,
      // Feedback UI internal states
      feedback: null,
      feedbackLoading: null
    })
    
    lastProcessingTime.value = res.data.processing_time_ms
    lastAgentUsed.value = res.data.agent_used
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `Erro: ${e.message}`,
      time: new Date().toLocaleTimeString()
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

// Training Dialog State
const trainingDialog = ref(false)
const trainingMsg = ref(null)
const trainingType = ref(null)
const trainingForm = reactive({
  contact_rule: '',
  agent_rule: '',
  entity_rule: '',
  entity_path: '',
  resolved_entity_id: null
})

function resolveEntityPath() {
  const msg = trainingMsg.value
  const path = trainingForm.entity_path.trim()
  if (!path || !msg?.jobPayload) {
    trainingForm.resolved_entity_id = null
    return
  }
  let clean = path
  if (clean.startsWith('$request.')) clean = clean.substring('$request.'.length)
  const parts = clean.split('.')
  let current = msg.jobPayload
  for (const part of parts) {
    if (current && typeof current === 'object' && part in current) {
      current = current[part]
    } else {
      trainingForm.resolved_entity_id = null
      return
    }
  }
  trainingForm.resolved_entity_id = current != null ? String(current) : null
}

async function submitFeedback(msg, type) {
  const msgIndex = messages.value.indexOf(msg)
  if (msgIndex <= 0) return
  
  let userMessage = ''
  for (let i = msgIndex - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      userMessage = messages.value[i].content
      break
    }
  }
  
  msg.feedbackLoading = type
  let correctionNote = null
  
  if (type === 'negative') {
    correctionNote = window.prompt("Opcional: Descreva rapidamente o que o agente errou ou como deveria ter respondido.")
  }

  try {
    // 1) First, send auto-RLHF feedback
    const payload = {
      agent_id: msg.agent_id || selectedAgentId.value,
      session_id: sessionId.value,
      feedback_type: type,
      user_message: userMessage,
      agent_response: msg.content,
      correction_note: correctionNote
    }

    const res = await axios.post('/webhook/feedback', payload)
    if (res.data.success) {
      msg.feedback = type
      showNotification(res.data.message || 'Feedback RLHF salvo!', 'success')
    }
    
    // 2) Open training dialog for manual rules (3 boxes)
    trainingMsg.value = msg
    trainingMsg.value._userMessage = userMessage
    trainingType.value = type
    trainingForm.contact_rule = ''
    trainingForm.agent_rule = ''
    trainingForm.entity_rule = ''
    trainingForm.entity_path = ''
    trainingForm.resolved_entity_id = null
    trainingDialog.value = true
    
  } catch (error) {
    showNotification('Falha ao processar feedback: ' + (error.response?.data?.detail || error.message), 'error')
  } finally {
    msg.feedbackLoading = null
  }
}

async function submitTraining() {
  const msg = trainingMsg.value
  if (!msg) return
  
  const hasAnyRule = trainingForm.contact_rule.trim() || trainingForm.agent_rule.trim() || trainingForm.entity_rule.trim()
  if (!hasAnyRule) {
    trainingDialog.value = false
    return
  }
  
  try {
    const payload = {
      agent_id: msg.agent_id || selectedAgentId.value,
      session_id: sessionId.value,
      contact_rule: trainingForm.contact_rule.trim() || null,
      agent_rule: trainingForm.agent_rule.trim() || null,
      entity_rule: trainingForm.entity_rule.trim() || null,
      entity_path: trainingForm.entity_path.trim() || null,
      entity_id: trainingForm.resolved_entity_id,
      job_payload: msg.jobPayload || null,
      message_context: msg._userMessage || null
    }
    
    const res = await axios.post('/memory/train-dual', payload)
    if (res.data.status === 'success') {
      const parts = []
      if (res.data.saved_contact) parts.push('Usuário')
      if (res.data.saved_agent) parts.push('Agente')
      if (res.data.saved_entity) parts.push(`Entidade (${res.data.resolved_entity_id})`)
      showNotification(`Treinamento salvo: ${parts.join(', ')}`, 'success')
    }
  } catch (error) {
    showNotification('Erro no treinamento: ' + (error.response?.data?.detail || error.message), 'error')
  } finally {
    trainingDialog.value = false
  }
}


</script>

<style scoped lang="scss">
.chat-wrapper {
  background: rgba(16, 20, 34, 0.6) !important;
  border-radius: 16px;
  box-shadow: 0 4px 30px rgba(0,0,0,0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.chat-toolbar {
  z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(16, 20, 34, 0.4) !important;
  border-bottom: 1px solid rgba(255,255,255,0.05) !important;
}

.settings-drawer {
  background-color: rgba(16, 20, 34, 0.4) !important;
  backdrop-filter: blur(10px);
  border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
  
  :deep(.v-navigation-drawer__content) {
    overflow-y: auto;
  }
}

.messages-scroll-area {
  scroll-behavior: smooth;
  
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background-color: rgba(157, 78, 221, 0.3);
    border-radius: 10px;
    &:hover {
      background-color: rgba(157, 78, 221, 0.6);
    }
  }
}

.prompt-card {
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 14px;
  background-color: rgba(255,255,255,0.03);
  font-size: 14px;
  border: 1px solid rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.8);
  
  &:hover {
    border-color: #9D4EDD;
    background-color: rgba(157, 78, 221, 0.1);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(157, 78, 221, 0.2);
    color: #fff;
  }
}

.message-bubble {
  position: relative;
  max-width: 100%;
  border-bottom-left-radius: 4px !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(255, 255, 255, 0.03) !important;
  backdrop-filter: blur(5px);
  color: rgba(255,255,255,0.9);
}

.user-wrapper {
  max-width: 80%;
  
  .message-bubble {
    border-bottom-left-radius: 16px !important;
    border-bottom-right-radius: 4px !important;
    color: white;
    background: linear-gradient(135deg, rgba(157, 78, 221, 0.8), rgba(85, 8, 206, 0.6)) !important;
    border: 1px solid rgba(157, 78, 221, 0.4);
    box-shadow: 0 4px 16px rgba(157, 78, 221, 0.2);
  }
}

.markdown-content {
  line-height: 1.7;
  font-size: 14px;
  
  :deep(p) { margin-bottom: 0.5rem; }
  :deep(p:last-child) { margin-bottom: 0; }
  :deep(strong) { font-weight: 600; color: #fff; }
  :deep(code) { 
    font-family: 'JetBrains Mono', 'Fira Code', monospace; 
    font-size: 0.85em;
    background: rgba(157, 78, 221, 0.2);
    padding: 2px 6px;
    border-radius: 4px;
    color: #C77DFF;
  }
  :deep(.code-block) {
    background: rgba(0,0,0,0.4);
    color: #00FC8B;
    padding: 16px;
    border-radius: 12px;
    margin: 10px 0;
    white-space: pre-wrap;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    border: 1px solid rgba(255,255,255,0.06);
  }
}

.typing-indicator-bubble {
  display: flex;
  align-items: center;
  gap: 5px;
  background: rgba(255, 255, 255, 0.03) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(5px);
  
  .dot {
    width: 7px;
    height: 7px;
    background: linear-gradient(135deg, #00f2fe, #00FC8B);
    border-radius: 50%;
    animation: bounce 1.4s infinite ease-in-out both;
    
    &:nth-child(1) { animation-delay: -0.32s; }
    &:nth-child(2) { animation-delay: -0.16s; }
  }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.chat-input-footer {
  background: rgba(16, 20, 34, 0.6) !important;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255, 255, 255, 0.05) !important;
  position: sticky;
  bottom: 0;
  z-index: 5;
}

.chat-input :deep(.v-field) {
  background: rgba(0,0,0,0.4) !important;
  border: 1px solid rgba(255,255,255,0.05);
  color: #fff;
  transition: all 0.3s ease;
  
  &:hover, &.v-field--focused {
    background: rgba(30, 35, 55, 0.8) !important;
    border-color: rgba(157, 78, 221, 0.4);
    box-shadow: 0 0 10px rgba(157, 78, 221, 0.2);
  }
}

.font-monospace {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.context-preview {
  transition: all 0.2s ease;
  background: rgba(255,255,255,0.03) !important;
  border: 1px solid rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.8);
  
  &:hover {
    border-color: rgba(157, 78, 221, 0.3) !important;
  }
}
</style>
