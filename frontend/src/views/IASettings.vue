<template>
  <div class="ia-settings-page d-flex flex-column h-100 w-100" style="padding: 0; width: 100%;">
    <!-- Header Area -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h2 class="text-h5 font-weight-bold text-white mb-1 d-flex align-center">
          <v-icon color="primary" class="mr-3" size="32">mdi-cog-box</v-icon>
          Configurações de IA
        </h2>
        <p class="text-subtitle-2 text-medium-emphasis mb-0">Gerencie provedores de IA e endpoints de Webhook personalizados.</p>
      </div>
    </div>

    <!-- Main Content Area -->
    <v-card class="settings-card glass-card flex-grow-1 d-flex flex-column">
      <v-tabs v-model="tab" color="primary" class="settings-tabs border-b px-4">
        <v-tab value="providers">Provedores de IA</v-tab>
        <v-tab value="webhooks">Endpoints (Webhooks)</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="flex-grow-1 overflow-auto pa-6">
        <!-- Providers Tab -->
        <v-window-item value="providers" class="h-100">
          <div class="d-flex justify-space-between align-center mb-6">
            <h3 class="text-h6 font-weight-medium text-white">Provedores Configurados</h3>
            <v-btn color="primary" prepend-icon="mdi-plus" class="glass-btn" @click="openProviderDialog()">
              Adicionar Provedor
            </v-btn>
          </div>

          <v-data-table
            :headers="providerHeaders"
            :items="providers"
            :loading="loadingProviders"
            class="glass-table bg-transparent"
            hover
          >
            <template v-slot:item.name="{ item }">
              <div class="d-flex align-center">
                <v-avatar size="32" class="mr-3 bg-white" variant="flat">
                  <v-img v-if="item.name.toLowerCase().includes('openai')" src="https://upload.wikimedia.org/wikipedia/commons/4/4d/OpenAI_Logo.svg" class="pa-1"></v-img>
                  <v-img v-else-if="item.name.toLowerCase().includes('anthropic')" src="https://upload.wikimedia.org/wikipedia/commons/7/78/Anthropic_logo.svg" class="pa-1"></v-img>
                  <v-icon v-else color="black">mdi-robot-outline</v-icon>
                </v-avatar>
                <span class="font-weight-medium text-capitalize">{{ item.name }}</span>
              </div>
            </template>
            <template v-slot:item.api_key_configured="{ item }">
              <v-chip size="small" :color="item.api_key_configured ? 'success' : 'error'" variant="tonal">
                {{ item.api_key_configured ? 'Configurada' : 'Pendente' }}
              </v-chip>
            </template>
            <template v-slot:item.is_active="{ item }">
              <v-switch
                v-model="item.is_active"
                color="success"
                density="compact"
                hide-details
                @change="toggleProviderStatus(item)"
              ></v-switch>
            </template>
            <template v-slot:item.actions="{ item }">
              <div class="d-flex ga-2">
                <v-btn icon="mdi-pencil" variant="text" size="small" color="primary" @click="openProviderDialog(item)"></v-btn>
                <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDeleteProvider(item)"></v-btn>
              </div>
            </template>
            <template v-slot:no-data>
              <div class="pa-8 text-center text-medium-emphasis">
                Nenhum provedor configurado. Clique em "Adicionar Provedor" para começar.
              </div>
            </template>
          </v-data-table>
        </v-window-item>

        <!-- Webhooks Tab -->
        <v-window-item value="webhooks" class="h-100">
          <div class="d-flex justify-space-between align-center mb-6">
            <h3 class="text-h6 font-weight-medium text-white">Webhooks Personalizados</h3>
            <v-btn color="primary" prepend-icon="mdi-plus" class="glass-btn" @click="openWebhookDialog()">
              Criar Webhook
            </v-btn>
          </div>

          <v-data-table
            :headers="webhookHeaders"
            :items="webhooks"
            :loading="loadingWebhooks"
            class="glass-table bg-transparent"
            hover
          >
            <template v-slot:item.path="{ item }">
              <v-chip variant="outlined" color="info" size="small" class="font-weight-medium">
                /webhook/{{ item.path }}
              </v-chip>
            </template>
            <template v-slot:item.require_token="{ item }">
              <v-chip size="small" :color="item.require_token ? 'warning' : 'success'" variant="tonal">
                <v-icon start size="14">{{ item.require_token ? 'mdi-lock' : 'mdi-lock-open-variant' }}</v-icon>
                {{ item.require_token ? 'Requer Token' : 'Público' }}
              </v-chip>
            </template>
            <template v-slot:item.sync_mode="{ item }">
              <v-chip size="small" :color="item.sync_mode ? 'purple' : 'info'" variant="tonal">
                {{ item.sync_mode ? 'Síncrono' : 'Fila (Job)' }}
              </v-chip>
            </template>
            <template v-slot:item.target_agent_id="{ item }">
              <span v-if="item.target_agent_id">{{ getAgentName(item.target_agent_id) }}</span>
              <v-chip v-else size="small" color="purple" variant="tonal">Orquestrador Global</v-chip>
            </template>
            <template v-slot:item.is_active="{ item }">
              <v-switch
                v-model="item.is_active"
                color="success"
                density="compact"
                hide-details
                @change="toggleWebhookStatus(item)"
              ></v-switch>
            </template>
            <template v-slot:item.actions="{ item }">
              <div class="d-flex ga-2">
                <v-btn icon="mdi-pencil" variant="text" size="small" color="primary" @click="openWebhookDialog(item)"></v-btn>
                <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDeleteWebhook(item)"></v-btn>
              </div>
            </template>
            <template v-slot:no-data>
              <div class="pa-8 text-center text-medium-emphasis">
                Nenhum webhook configurado. Clique em "Criar Webhook" para começar.
              </div>
            </template>
          </v-data-table>
        </v-window-item>
      </v-window>
    </v-card>

    <!-- Provider Dialog -->
    <v-dialog v-model="providerDialog" max-width="600" persistent>
      <v-card class="glass-dialog">
        <v-card-title class="pa-6 border-b d-flex align-center justify-space-between text-white">
          {{ editedProvider.id ? 'Editar Provedor' : 'Novo Provedor' }}
          <v-btn icon="mdi-close" variant="text" density="compact" @click="closeProviderDialog"></v-btn>
        </v-card-title>
        <v-card-text class="pa-6">
          <v-form ref="providerForm" v-model="providerFormValid">
            <v-text-field
              v-model="editedProvider.name"
              label="Nome do Serviço (ex: OpenAI, Anthropic, OpenRouter)"
              variant="outlined"
              :rules="[v => !!v || 'Nome é obrigatório']"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-text-field
              v-model="editedProvider.base_url"
              label="Base URL (Opcional - Custom Endpoint)"
              variant="outlined"
              placeholder="Ex: https://api.openai.com/v1"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-text-field
              v-model="editedProvider.api_key"
              label="API Key / Token"
              variant="outlined"
              type="password"
              :rules="editedProvider.id ? [] : [v => !!v || 'API Key é obrigatória']"
              :placeholder="editedProvider.id ? 'Deixe em branco para manter a atual' : ''"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-text-field
              v-model="editedProvider.default_model"
              label="Modelo Padrão (Opcional)"
              variant="outlined"
              placeholder="Ex: gpt-4o-mini"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-switch
              v-model="editedProvider.is_active"
              label="Ativo"
              color="success"
              hide-details
            ></v-switch>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-6 border-t">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeProviderDialog" class="mr-2 text-white">Cancelar</v-btn>
          <v-btn 
            color="primary" 
            variant="flat" 
            class="glass-btn px-6" 
            :loading="savingProvider" 
            :disabled="!providerFormValid"
            @click="saveProvider"
          >
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Webhook Dialog -->
    <v-dialog v-model="webhookDialog" max-width="600" persistent>
      <v-card class="glass-dialog">
        <v-card-title class="pa-6 border-b d-flex align-center justify-space-between text-white">
          {{ editedWebhook.id ? 'Editar Webhook' : 'Novo Webhook' }}
          <v-btn icon="mdi-close" variant="text" density="compact" @click="closeWebhookDialog"></v-btn>
        </v-card-title>
        <v-card-text class="pa-6">
          <v-form ref="webhookForm" v-model="webhookFormValid">
            <v-text-field
              v-model="editedWebhook.name"
              label="Nome Identificador"
              variant="outlined"
              placeholder="Ex: API Cliente A"
              :rules="[v => !!v || 'Nome é obrigatório']"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-text-field
              v-model="editedWebhook.path"
              label="Endpoint Path (Hash/Rota)"
              variant="outlined"
              prefix="/webhook/"
              placeholder="meu-agente-v1"
              :rules="[v => !!v || 'Path é obrigatório', v => !/\s/.test(v) || 'Não pode conter espaços']"
              class="mb-4 input-glass"
              bg-color="transparent"
            ></v-text-field>

            <v-autocomplete
              v-model="editedWebhook.target_agent_id"
              :items="agents"
              item-title="name"
              item-value="id"
              label="Agente Alvo (Deixe em branco para Orquestrador Global)"
              variant="outlined"
              clearable
              class="mb-4 input-glass"
              bg-color="transparent"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props" :subtitle="item.raw.description"></v-list-item>
              </template>
            </v-autocomplete>

            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-2 py-3 px-4 d-flex align-center">
                <v-icon class="mr-2" size="20">mdi-lock</v-icon>
                Autenticação
              </v-card-title>
              <v-divider></v-divider>
              <v-card-text class="pt-3 pb-3">
                <v-switch
                  v-model="editedWebhook.require_token"
                  label="Exigir Token de Autenticação (Bearer)"
                  color="primary"
                  hide-details
                  density="comfortable"
                ></v-switch>

                <v-expand-transition>
                  <div v-if="editedWebhook.require_token" class="mt-4">
                    <v-text-field
                      v-model="editedWebhook.access_token"
                      label="Token de Acesso (Bearer)"
                      variant="outlined"
                      type="password"
                      :rules="editedWebhook.require_token && !editedWebhook.id ? [v => !!v || 'Token é obrigatório'] : []"
                      :placeholder="editedWebhook.id ? 'Deixe em branco para manter o atual' : 'Defina um secret forte'"
                      prepend-inner-icon="mdi-key"
                      append-inner-icon="mdi-refresh"
                      @click:append-inner="generateToken"
                    ></v-text-field>
                  </div>
                </v-expand-transition>
              </v-card-text>
            </v-card>

            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-2 py-3 px-4 d-flex align-center">
                <v-icon class="mr-2" size="20">mdi-cog</v-icon>
                Configurações
              </v-card-title>
              <v-divider></v-divider>
              <v-card-text class="pt-3 pb-3">
                <v-switch
                  v-model="editedWebhook.sync_mode"
                  label="Processamento Síncrono (Ignorar fila de Jobs)"
                  color="purple"
                  hide-details
                  density="comfortable"
                ></v-switch>
                
                <v-switch
                  v-model="editedWebhook.is_active"
                  label="Webhook Ativo"
                  color="success"
                  hide-details
                  density="comfortable"
                  class="mt-3"
                ></v-switch>
              </v-card-text>
            </v-card>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-6 border-t">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeWebhookDialog" class="mr-2 text-white">Cancelar</v-btn>
          <v-btn 
            color="primary" 
            variant="flat" 
            class="glass-btn px-6" 
            :loading="savingWebhook" 
            :disabled="!webhookFormValid"
            @click="saveWebhook"
          >
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog.show" max-width="400">
      <v-card class="glass-dialog">
        <v-card-title class="text-h6 text-white pt-6 px-6">Confirmar Exclusão</v-card-title>
        <v-card-text class="px-6 py-4 text-medium-emphasis">
          Tem certeza que deseja excluir o item "{{ deleteDialog.item?.name }}"? Esta ação não pode ser desfeita.
        </v-card-text>
        <v-card-actions class="pa-6">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog.show = false" class="text-white">Cancelar</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.loading" @click="executeDelete">Excluir</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top right">
      {{ snackbar.message }}
      <template v-slot:actions>
        <v-btn icon="mdi-close" variant="text" @click="snackbar.show = false"></v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from '@/plugins/axios'

// State
const tab = ref('providers')
const snackbar = reactive({ show: false, message: '', color: 'success' })

// Data
const providers = ref([])
const webhooks = ref([])
const agents = ref([])

// Loadings
const loadingProviders = ref(true)
const loadingWebhooks = ref(true)

// Headers
const providerHeaders = [
  { title: 'Provedor', key: 'name', sortable: true },
  { title: 'Base URL', key: 'base_url' },
  { title: 'Modelo Padrão', key: 'default_model' },
  { title: 'API Key', key: 'api_key_configured', sortable: false },
  { title: 'Status', key: 'is_active', sortable: false },
  { title: 'Ações', key: 'actions', sortable: false, align: 'end' },
]

const webhookHeaders = [
  { title: 'Nome', key: 'name', sortable: true },
  { title: 'Path / Rota', key: 'path', sortable: true },
  { title: 'Autenticação', key: 'require_token', sortable: false },
  { title: 'Modo Exec', key: 'sync_mode', sortable: false },
  { title: 'Alvo', key: 'target_agent_id', sortable: false },
  { title: 'Status', key: 'is_active', sortable: false },
  { title: 'Ações', key: 'actions', sortable: false, align: 'end' },
]

// Dialogs State
const providerDialog = ref(false)
const providerFormValid = ref(false)
const savingProvider = ref(false)
const editedProvider = ref({
  name: '',
  base_url: '',
  api_key: '',
  default_model: '',
  is_active: true
})

const webhookDialog = ref(false)
const webhookFormValid = ref(false)
const savingWebhook = ref(false)
const editedWebhook = ref({
  name: '',
  path: '',
  require_token: false,
  access_token: '',
  target_agent_id: null,
  sync_mode: false,
  is_active: true
})

const deleteDialog = reactive({
  show: false,
  type: null, // 'provider' | 'webhook'
  item: null,
  loading: false
})

const showMessage = (msg, color = 'success') => {
  snackbar.message = msg
  snackbar.color = color
  snackbar.show = true
}

// Data Fetching
const fetchProviders = async () => {
  loadingProviders.value = true
  try {
    const { data } = await axios.get('/ai-providers')
    providers.value = data.providers
  } catch (error) {
    console.error('Error fetching providers:', error)
    showMessage('Erro ao carregar os provedores', 'error')
  } finally {
    loadingProviders.value = false
  }
}

const fetchWebhooks = async () => {
  loadingWebhooks.value = true
  try {
    const { data } = await axios.get('/webhooks-config')
    webhooks.value = data.webhooks
  } catch (error) {
    console.error('Error fetching webhooks:', error)
    showMessage('Erro ao carregar configurações de webhooks', 'error')
  } finally {
    loadingWebhooks.value = false
  }
}

const fetchAgents = async () => {
  try {
    const { data } = await axios.get('/agents')
    const agentList = data.agents || []
    agents.value = agentList.map(agent => ({
      ...agent,
      name: agent.name || 'Agente sem nome'
    }))
  } catch (error) {
    console.error('Error fetching agents:', error)
  }
}

const getAgentName = (id) => {
  const agent = agents.value.find(a => a.id === id)
  return agent ? agent.name : 'Desconhecido'
}

// Providers Logic
const openProviderDialog = (item = null) => {
  if (item) {
    editedProvider.value = { ...item, api_key: '' } // Clear key for edit
  } else {
    editedProvider.value = { name: '', base_url: '', api_key: '', default_model: '', is_active: true }
  }
  providerDialog.value = true
}

const closeProviderDialog = () => {
  providerDialog.value = false
  editedProvider.value = { name: '', base_url: '', api_key: '', default_model: '', is_active: true }
}

const saveProvider = async () => {
  if (!providerFormValid.value) return
  savingProvider.value = true
  
  try {
    const payload = { ...editedProvider.value }
    // Don't send empty api_key if editing
    if (payload.id && !payload.api_key) {
      delete payload.api_key
    }
    
    if (payload.id) {
      await axios.put(`/ai-providers/${payload.id}`, payload)
      showMessage('Provedor atualizado com sucesso!')
    } else {
      await axios.post('/ai-providers', payload)
      showMessage('Provedor cadastrado com sucesso!')
    }
    closeProviderDialog()
    fetchProviders()
  } catch (error) {
    showMessage(error.response?.data?.detail || 'Erro ao salvar provedor', 'error')
  } finally {
    savingProvider.value = false
  }
}

const toggleProviderStatus = async (item) => {
  try {
    await axios.put(`/ai-providers/${item.id}`, { is_active: item.is_active })
    showMessage(`Provedor ${item.is_active ? 'ativado' : 'desativado'}.`)
  } catch (error) {
    item.is_active = !item.is_active // revert
    showMessage('Erro ao alterar status', 'error')
  }
}

const confirmDeleteProvider = (item) => {
  deleteDialog.type = 'provider'
  deleteDialog.item = item
  deleteDialog.show = true
}

// Webhooks Logic
const generateToken = () => {
  editedWebhook.value.access_token = 'tk_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)
}

const openWebhookDialog = (item = null) => {
  if (item) {
    editedWebhook.value = { ...item, access_token: '' }
  } else {
    editedWebhook.value = { name: '', path: '', require_token: false, access_token: '', target_agent_id: null, sync_mode: false, is_active: true }
  }
  webhookDialog.value = true
}

const closeWebhookDialog = () => {
  webhookDialog.value = false
}

const saveWebhook = async () => {
  if (!webhookFormValid.value) return
  savingWebhook.value = true
  
  try {
    const payload = { ...editedWebhook.value }
    if (payload.id && !payload.access_token) {
      delete payload.access_token
    }
    
    if (payload.id) {
      await axios.put(`/webhooks-config/${payload.id}`, payload)
      showMessage('Webhook atualizado com sucesso!')
    } else {
      await axios.post('/webhooks-config', payload)
      showMessage('Webhook criado com sucesso!')
    }
    closeWebhookDialog()
    fetchWebhooks()
  } catch (error) {
    showMessage(error.response?.data?.detail || 'Erro ao salvar webhook', 'error')
  } finally {
    savingWebhook.value = false
  }
}

const toggleWebhookStatus = async (item) => {
  try {
    await axios.put(`/webhooks-config/${item.id}`, { is_active: item.is_active })
    showMessage(`Webhook ${item.is_active ? 'ativado' : 'desativado'}.`)
  } catch (error) {
    item.is_active = !item.is_active
    showMessage('Erro ao alterar status', 'error')
  }
}

const confirmDeleteWebhook = (item) => {
  deleteDialog.type = 'webhook'
  deleteDialog.item = item
  deleteDialog.show = true
}

// Common Delete
const executeDelete = async () => {
  deleteDialog.loading = true
  try {
    if (deleteDialog.type === 'provider') {
      await axios.delete(`/ai-providers/${deleteDialog.item.id}`)
      fetchProviders()
    } else {
      await axios.delete(`/webhooks-config/${deleteDialog.item.id}`)
      fetchWebhooks()
    }
    showMessage('Excluído com sucesso!')
    deleteDialog.show = false
  } catch (error) {
    showMessage('Erro ao excluir item', 'error')
  } finally {
    deleteDialog.loading = false
  }
}

onMounted(() => {
  fetchProviders()
  fetchWebhooks()
  fetchAgents()
})
</script>

<style scoped>
.ia-settings-page {
  animation: fadeIn 0.4s ease-out;
}

.settings-card {
  border-radius: 16px;
  background: rgba(20, 24, 40, 0.6) !important;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}

.settings-tabs {
  background: transparent !important;
  border-bottom-color: rgba(255, 255, 255, 0.05) !important;
}

.settings-tabs :deep(.v-tab) {
  text-transform: none;
  font-weight: 500;
  letter-spacing: 0;
  color: rgba(255, 255, 255, 0.6);
}

.settings-tabs :deep(.v-tab--selected) {
  color: #a78bfa;
}

.glass-btn {
  background: linear-gradient(135deg, rgba(157, 78, 221, 0.8) 0%, rgba(124, 58, 237, 0.8) 100%) !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 15px rgba(124, 58, 237, 0.3) !important;
  text-transform: none;
  font-weight: 600;
  letter-spacing: 0.5px;
  border-radius: 8px;
}

.glass-table :deep(th) {
  background: rgba(15, 18, 30, 0.8) !important;
  color: rgba(255, 255, 255, 0.7) !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.1em;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.glass-table :deep(td) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.02) !important;
  color: rgba(255, 255, 255, 0.8);
}

.glass-table :deep(tr:hover:not(.v-data-table__empty-wrapper)) {
  background: rgba(255, 255, 255, 0.03) !important;
}

.glass-dialog {
  background: rgba(20, 24, 40, 0.95) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6) !important;
}

.input-glass :deep(.v-field) {
  background: rgba(10, 12, 20, 0.5) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.9);
}

.input-glass :deep(.v-field--focused) {
  background: rgba(15, 18, 30, 0.8) !important;
  border-color: rgba(157, 78, 221, 0.5);
  box-shadow: 0 0 0 1px rgba(157, 78, 221, 0.5);
}

.border-b {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.border-t {
  border-top: 1px solid rgba(255, 255, 255, 0.05) !important;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
