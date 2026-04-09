<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from '@/plugins/axios'
import { mdiRocketLaunchOutline, mdiPlus, mdiTrashCanOutline, mdiPencilOutline } from '@mdi/js'

const configs = ref([])
const totalConfigs = ref(0)
const loading = ref(false)
const dialog = ref(false)
const deleteDialog = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)
const configToDelete = ref(null)

const webhookDialog = ref(false)
const webhookConfig = ref(null)

const agents = ref([])

const defaultItem = {
  name: '',
  path: '',
  api_key: '',
  buttons_enabled: false,
  buttons: [],
  image_enabled: false,
  messages_per_batch: 1,
  agent_id: null,
  start_time: '08:00',
  end_time: '22:00',
  start_delay_seconds: 0,
  min_variation_seconds: 5,
  max_variation_seconds: 15,
  triggers: [],
  index_max: 5,
  progress_callback_url: '',
  is_active: true
}

const editedItem = ref(JSON.parse(JSON.stringify(defaultItem)))
const isEditing = ref(false)

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const showPass = ref(false)

const activeStats = computed(() => configs.ref?.filter(c => c.is_active).length || 0)

const headers = [
  { title: 'NOME', key: 'name' },
  { title: 'ENDPOINT', key: 'path' },
  { title: 'AGENTE', key: 'agent_name' },
  { title: 'MSGS/BATCH', key: 'messages_per_batch' },
  { title: 'HORÁRIO', key: 'time_window', sortable: false },
  { title: 'STATUS', key: 'is_active' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const fetchConfigs = async () => {
  loading.value = true
  try {
    const res = await axios.get('/disparador-configs')
    configs.value = res.data.configs
    totalConfigs.value = res.data.total
  } catch (err) {
    showSnackbar('Erro ao carregar configurações', 'error')
  } finally {
    loading.value = false
  }
}

const fetchAgents = async () => {
  try {
    const res = await axios.get('/agents')
    agents.value = res.data.agents
  } catch (err) {
    console.error('Erro ao carregar agentes', err)
  }
}

const showSnackbar = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

const closeDialog = () => {
  dialog.value = false
  setTimeout(() => {
    editedItem.value = JSON.parse(JSON.stringify(defaultItem))
    isEditing.value = false
  }, 300)
}

const editConfig = (item) => {
  editedItem.value = JSON.parse(JSON.stringify(item))
  isEditing.value = true
  dialog.value = true
}

const confirmDelete = (item) => {
  configToDelete.value = item
  deleteDialog.value = true
}

const deleteConfig = async () => {
  if (!configToDelete.value) return
  isDeleting.value = true
  try {
    await axios.delete(`/disparador-configs/${configToDelete.value.id}`)
    showSnackbar('Configuração excluída com sucesso')
    await fetchConfigs()
  } catch (err) {
    showSnackbar('Erro ao excluir configuração', 'error')
  } finally {
    isDeleting.value = false
    deleteDialog.value = false
    configToDelete.value = null
  }
}

const saveConfig = async () => {
  isSaving.value = true
  try {
    if (isEditing.value) {
      await axios.put(`/disparador-configs/${editedItem.value.id}`, editedItem.value)
      showSnackbar('Configuração atualizada com sucesso')
    } else {
      await axios.post('/disparador-configs', editedItem.value)
      showSnackbar('Configuração criada com sucesso')
    }
    closeDialog()
    await fetchConfigs()
  } catch (err) {
    showSnackbar(err.response?.data?.detail || 'Erro ao salvar configuração', 'error')
  } finally {
    isSaving.value = false
  }
}

const addButton = () => {
  editedItem.value.buttons.push({ label: '', value: '', action: '' })
}

const removeButton = (index) => {
  editedItem.value.buttons.splice(index, 1)
}

const generateApiKey = () => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = 'dp_'
  for (let i = 0; i < 32; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  editedItem.value.api_key = result
}

const toggleActive = async (item) => {
  try {
    await axios.put(`/disparador-configs/${item.id}`, { is_active: item.is_active })
    showSnackbar(item.is_active ? 'Endpoint ativado' : 'Endpoint desativado')
  } catch (error) {
    item.is_active = !item.is_active
    showSnackbar('Erro ao alterar status', 'error')
  }
}

const openWebhookInfo = (item) => {
  webhookConfig.value = item
  webhookDialog.value = true
}

const copyPayload = async () => {
  try {
    await navigator.clipboard.writeText(generatedPayload.value)
    showSnackbar('JSON copiado com sucesso!')
  } catch {
    showSnackbar('Erro ao copiar', 'error')
  }
}

const webhookUrlStr = computed(() => {
  const origin = window.location.origin
  const path = webhookConfig.value?.path || 'slug_da_campanha'
  if (origin.includes('localhost')) {
    return 'http://localhost:8010/webhook/' + path
  }
  // Substitute the frontend subdomain for the disparador subdomain if applicable
  const disparadorHost = origin.replace('painel.', 'disparador.').replace('app.', 'disparador.')
  return disparadorHost + '/webhook/' + path
})

const generatedPayload = computed(() => {
  const cfg = webhookConfig.value
  if (!cfg) return '{}'
  
  const payload = {
    system: {
      apikey: cfg.api_key || "sua-api-key-se-configurada"
    },
    messages: [
      {
        connection_id: "instancia_whatsapp_id",
        user_name: "Nome do Cliente",
        number: "5511999999999",
        variables: {
          "exemplo_variavel": "Valor opcional para substituir no prompt"
        }
      }
    ]
  }
  
  return JSON.stringify(payload, null, 2)
})

onMounted(() => {
  fetchConfigs()
  fetchAgents()
})
</script>

<template>
  <div class="disparador-container">
    <div class="d-flex align-center mb-6">
      <v-avatar color="primary" variant="tonal" rounded size="48" class="mr-4">
        <v-icon :icon="mdiRocketLaunchOutline" size="24"></v-icon>
      </v-avatar>
      <div>
        <h2 class="text-h4 font-weight-bold">Disparador</h2>
        <div class="text-subtitle-1 text-medium-emphasis">
          Gerencie webhooks de disparo automatizado
        </div>
      </div>
      <v-spacer></v-spacer>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="dialog = true">
        Novo Disparo
      </v-btn>
    </div>

    <!-- Stats -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">TOTAL CONFIGS</div>
            <div class="text-h4 font-weight-bold">{{ totalConfigs }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">ATIVAS</div>
            <div class="text-h4 font-weight-bold text-success">{{ activeStats }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">CAMPANHAS HOJE</div>
            <div class="text-h4 font-weight-bold text-primary">--</div>
            <div class="text-caption text-medium-emphasis mt-1">Veja guia Acompanhamento</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="glass-card" variant="flat">
          <v-card-text>
            <div class="text-overline mb-1">MSGS ENVIADAS HOJE</div>
            <div class="text-h4 font-weight-bold text-info">--</div>
            <div class="text-caption text-medium-emphasis mt-1">Veja guia Acompanhamento</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Table -->
    <v-card class="glass-card" variant="flat">
      <v-data-table
        :headers="headers"
        :items="configs"
        :loading="loading"
        hover
      >
        <template #item.path="{ item }">
          <v-chip variant="outlined" color="primary" size="small">
            /webhook/{{ item.path }}
          </v-chip>
        </template>

        <template #item.time_window="{ item }">
          {{ item.start_time }} - {{ item.end_time }}
        </template>

        <template #item.is_active="{ item }">
          <v-switch
            v-model="item.is_active"
            color="success"
            density="compact"
            hide-details
            @change="toggleActive(item)"
          ></v-switch>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex justify-end gap-2">
            <v-btn
              icon
              variant="text"
              size="small"
              color="info"
              @click="openWebhookInfo(item)"
            >
              <v-icon icon="mdi-web"></v-icon>
              <v-tooltip activator="parent" location="top">Integração</v-tooltip>
            </v-btn>
            <v-btn
              icon
              variant="text"
              size="small"
              color="primary"
              @click="editConfig(item)"
            >
              <v-icon :icon="mdiPencilOutline"></v-icon>
              <v-tooltip activator="parent" location="top">Editar</v-tooltip>
            </v-btn>
            <v-btn
              icon
              variant="text"
              size="small"
              color="error"
              @click="confirmDelete(item)"
            >
              <v-icon :icon="mdiTrashCanOutline"></v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Form Dialog -->
    <v-dialog v-model="dialog" max-width="900" persistent>
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-6 pb-4">
          <span class="text-h5 font-weight-bold">{{ isEditing ? 'Editar' : 'Novo' }} Endpoint</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closeDialog"></v-btn>
        </v-card-title>
        
        <v-card-text class="px-6 py-2">
          <v-form @submit.prevent="saveConfig" id="config-form">
            <!-- Basic Info -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Informações Básicas</div>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedItem.name"
                  label="Nome da Campanha/Endpoint"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="editedItem.path"
                  label="Path (slug ex: campanha-abril)"
                  prefix="/webhook/"
                  variant="outlined"
                  required
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  v-model="editedItem.api_key"
                  label="API Key (Opcional - system.apikey)"
                  variant="outlined"
                  :type="showPass ? 'text' : 'password'"
                  :append-inner-icon="showPass ? 'mdi-eye-off' : 'mdi-eye'"
                  @click:append-inner="showPass = !showPass"
                  hint="Se preenchido, os requests devem conter esta chave no payload.system.apikey"
                >
                  <template v-slot:append>
                    <v-btn color="secondary" variant="tonal" @click="generateApiKey">
                      Gerar
                    </v-btn>
                  </template>
                </v-text-field>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Agent & Messages -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Roteamento e Volume</div>
            <v-row>
              <v-col cols="12" md="8">
                <v-autocomplete
                  v-model="editedItem.agent_id"
                  :items="agents"
                  item-title="name"
                  item-value="id"
                  label="Agente de Atendimento"
                  variant="outlined"
                  clearable
                ></v-autocomplete>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="editedItem.messages_per_batch"
                  type="number"
                  label="Mensagens por Disparo (Batch)"
                  variant="outlined"
                  min="1"
                ></v-text-field>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Media & Interaction -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Mídia e Interação Explicita</div>
            <v-row>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="editedItem.image_enabled"
                  color="primary"
                  label="Enviar Imagem Ativo"
                  hint="Fornece ao agente flag dispatcher_image_enabled"
                  persistent-hint
                ></v-switch>
              </v-col>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="editedItem.buttons_enabled"
                  color="primary"
                  label="Botões Ativos"
                ></v-switch>
              </v-col>
            </v-row>
            <v-expand-transition>
              <div v-if="editedItem.buttons_enabled" class="mt-4 bg-surface-variant pa-4 rounded-lg">
                <div class="d-flex align-center mb-3">
                  <span class="font-weight-medium">Configuração de Botões</span>
                  <v-spacer></v-spacer>
                  <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addButton">
                    Adicionar
                  </v-btn>
                </div>
                <div v-for="(btn, index) in editedItem.buttons" :key="index" class="d-flex gap-2 mb-2">
                  <v-text-field v-model="btn.label" label="Label" variant="outlined" density="compact" hide-details></v-text-field>
                  <v-text-field v-model="btn.value" label="Value" variant="outlined" density="compact" hide-details></v-text-field>
                  <v-btn icon color="error" variant="text" @click="removeButton(index)">
                    <v-icon :icon="mdiTrashCanOutline"></v-icon>
                  </v-btn>
                </div>
                <div v-if="editedItem.buttons.length === 0" class="text-caption text-medium-emphasis">
                  Nenhum botão adicionado.
                </div>
              </div>
            </v-expand-transition>

            <v-divider class="my-4"></v-divider>

            <!-- Timings -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Horários e Delays</div>
            <v-row>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="editedItem.start_time"
                  type="time"
                  label="Horário Início"
                  variant="outlined"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="editedItem.end_time"
                  type="time"
                  label="Horário Fim"
                  variant="outlined"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="editedItem.start_delay_seconds"
                  type="number"
                  label="Delay Inicial (s)"
                  variant="outlined"
                  min="0"
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="editedItem.min_variation_seconds"
                  type="number"
                  label="Variação Delay Minimo (s)"
                  variant="outlined"
                  min="0"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="editedItem.max_variation_seconds"
                  type="number"
                  label="Variação Delay Máximo (s)"
                  variant="outlined"
                  min="0"
                ></v-text-field>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Advanced -->
            <div class="text-subtitle-1 font-weight-bold mb-3">Avançado e Integração</div>
            <v-row>
              <v-col cols="12" md="8">
                <v-combobox
                  v-model="editedItem.triggers"
                  label="Triggers (Keywords internas)"
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  hint="Use enter para adicionar um novo. Passado ao agente como dispatcher_triggers."
                ></v-combobox>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="editedItem.index_max"
                  type="number"
                  label="Índice Máximo (Fisher-yates)"
                  variant="outlined"
                  min="1"
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-text-field
                  v-model="editedItem.progress_callback_url"
                  label="Progress Callback URL (Opcional)"
                  variant="outlined"
                  hint="Recebe webhooks com progresso do lote"
                ></v-text-field>
              </v-col>
            </v-row>

            <v-row>
              <v-col cols="12">
                <v-switch
                  v-model="editedItem.is_active"
                  color="success"
                  label="Pipeline Ativo"
                ></v-switch>
              </v-col>
            </v-row>

          </v-form>
        </v-card-text>

        <v-divider></v-divider>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeDialog" :disabled="isSaving">Cancelar</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            type="submit"
            form="config-form"
            :loading="isSaving"
            class="px-6"
          >
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Dialog -->
    <v-dialog v-model="deleteDialog" max-width="500">
      <v-card class="glass-card">
        <v-card-title class="text-h5 font-weight-bold error--text pa-6 pb-4">
          <v-icon icon="mdi-alert" color="error" class="mr-2"></v-icon>
          Confirmar Exclusão
        </v-card-title>
        <v-card-text class="px-6 py-2">
          Tem certeza que deseja excluir a configuração <strong>{{ configToDelete?.name }}</strong>?<br>
          Esta ação não pode ser desfeita.
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false" :disabled="isDeleting">Cancelar</v-btn>
          <v-btn
            color="error"
            variant="flat"
            @click="deleteConfig"
            :loading="isDeleting"
            class="px-6"
          >
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Webhook Info Dialog -->
    <v-dialog v-model="webhookDialog" max-width="700">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center px-6 py-4 bg-info">
          <v-icon class="mr-2" color="white">mdi-web</v-icon>
          <span class="text-white">Instruções de Integração</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="webhookDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <p class="mb-4">Envie os dados de lote (Batch) para a campanha <strong>{{ webhookConfig?.name }}</strong> utilizando a URL do seu serviço Disparador:</p>
          
          <v-sheet
            class="pa-4 mb-4 rounded bg-surface-variant text-body-2"
            elevation="1"
            style="font-family: monospace; overflow-x: auto;"
          >
            POST {{ webhookUrlStr }}
          </v-sheet>

          <div class="d-flex align-center justify-space-between mb-2">
            <p class="text-subtitle-2 mb-0">JSON Payload pronto para copiar:</p>
            <v-btn size="small" variant="tonal" color="primary" @click="copyPayload">
              <v-icon start size="16">mdi-content-copy</v-icon>
              Copiar JSON
            </v-btn>
          </div>
          <v-sheet
            class="pa-4 mb-4 rounded bg-surface-variant text-body-2"
            elevation="1"
            style="font-family: monospace; white-space: pre; overflow-x: auto; max-height: 400px; overflow-y: auto;"
          >
{{ generatedPayload }}
          </v-sheet>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            A lista <code>messages</code> recebe um array de contatos. O sistema processará o disparo respeitando a configuração de lotes ({{"{{"}} webhookConfig?.messages_per_batch {{"}}"}} por vez).
          </v-alert>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            A chave <code>variables</code> pode conter metadados extras dos contatos que você quer injetar no prompt do agente para fins de personalização na mensagem.
          </v-alert>
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
.disparador-container {
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
</style>
