<template>
  <div class="information-bases-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-database-search</v-icon>
        </div>
        <div class="header-text">
          <h1>Bases de Informações</h1>
          <p>Crie coleções de dados estruturados personalizáveis para injetar nos agentes</p>
        </div>
      </div>
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="openDialog()" elevation="3">
        Nova Base
      </v-btn>
    </div>

    <!-- Stats Cards -->
    <v-row class="mb-6">
      <v-col cols="12" md="4">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-format-list-bulleted</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ bases.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Total de Bases</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="4">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-check-circle</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ activeCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Bases Ativas</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Bases Table -->
    <v-card class="bases-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
        <span class="text-white">Lista de Bases</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          density="compact"
          placeholder="Buscar Base..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          hide-details
          style="max-width: 300px"
        ></v-text-field>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="filteredBases"
        :loading="loading"
        :items-per-page="10"
        class="bases-table"
      >
        <template v-slot:item.name="{ item }">
          <div class="d-flex align-center py-2">
            <v-avatar color="info" size="36" class="mr-3">
              <v-icon color="white" size="18">mdi-database</v-icon>
            </v-avatar>
            <div>
              <span class="font-weight-medium">{{ item.name }}</span>
              <p class="text-caption text-medium-emphasis mb-0">
                Código: {{ item.code }}
              </p>
            </div>
          </div>
        </template>
        
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            <v-icon start size="14">{{ item.is_active ? 'mdi-check' : 'mdi-close' }}</v-icon>
            {{ item.is_active ? 'Ativa' : 'Inativa' }}
          </v-chip>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1 justify-center">
            <v-btn icon variant="text" size="small" color="primary" @click="openDialog(item)">
              <v-icon size="20">mdi-pencil</v-icon>
              <v-tooltip activator="parent" location="top">Editar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="error" @click="confirmDelete(item)">
              <v-icon size="20">mdi-delete</v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="info" @click="openWebhookInfo(item)">
              <v-icon size="20">mdi-web</v-icon>
              <v-tooltip activator="parent" location="top">Webhook URL</v-tooltip>
            </v-btn>
          </div>
        </template>
        
        <template v-slot:no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-database-off-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhuma Base encontrada</p>
            <p class="text-body-2 text-medium-emphasis mb-4">Crie sua primeira base de informações para começar</p>
            <v-btn color="primary" @click="openDialog()">
              <v-icon start>mdi-plus</v-icon>
              Criar Base
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog" max-width="800" persistent>
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-primary">
          <v-icon class="mr-2" color="white">{{ editing ? 'mdi-pencil' : 'mdi-plus-circle' }}</v-icon>
          <span class="text-white">{{ editing ? 'Editar Base de Informações' : 'Criar Nova Base' }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="dialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-form ref="formRef" v-model="formValid">
            <v-row>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="formData.name"
                  label="Nome da Base"
                  placeholder="Ex: Produtos de Parceiros"
                  :rules="[v => !!v || 'Nome é obrigatório']"
                  prepend-inner-icon="mdi-tag-text-outline"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-switch
                  v-model="formData.is_active"
                  label="Ativa"
                  color="success"
                  hide-details
                ></v-switch>
              </v-col>
            </v-row>

            <v-text-field
              v-model="formData.code"
              label="Código (Usado na Webhook)"
              placeholder="Ex: PRODUTOS_V1"
              :rules="[v => !!v || 'Código é obrigatório']"
              :disabled="editing"
              prepend-inner-icon="mdi-code-brackets"
              hint="Código único sem espaços, por ex: MINHA_BASE. Não pode ser alterado depois."
              persistent-hint
            ></v-text-field>

            <v-alert type="info" variant="tonal" density="compact" class="mt-4 mb-4">
              A webhook utiliza estes schemas para validar o JSON recebido e injetar informações adicionais.
            </v-alert>

            <p class="text-subtitle-2 text-medium-emphasis mb-2">
              <v-icon size="18" class="mr-1">mdi-file-document-outline</v-icon>
              Schema do Conteúdo (Opcional, formato JSON Schema)
            </p>
            <v-textarea
              v-model="formData.content_schema"
              placeholder="{}"
              rows="4"
              variant="outlined"
              density="compact"
              style="font-family: monospace; font-size: 13px;"
            ></v-textarea>

            <p class="text-subtitle-2 text-medium-emphasis mb-2 mt-4">
              <v-icon size="18" class="mr-1">mdi-tag-multiple-outline</v-icon>
              Schema de Metadados (Opcional, formato JSON Schema)
            </p>
            <v-textarea
              v-model="formData.metadata_schema"
              placeholder="{}"
              rows="4"
              variant="outlined"
              density="compact"
              style="font-family: monospace; font-size: 13px;"
            ></v-textarea>

            <p class="text-subtitle-2 text-medium-emphasis mb-2 mt-4">
              <v-icon size="18" class="mr-1">mdi-key-chain</v-icon>
              Schema de Correlação (Opcional, regras de extração do user_id ex: {"target": "memberphone"})
            </p>
            <v-textarea
              v-model="formData.correlation_schema"
              placeholder='{ "target": "memberphone" }'
              rows="2"
              variant="outlined"
              density="compact"
              style="font-family: monospace; font-size: 13px;"
            ></v-textarea>

          </v-form>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="dialog = false" :disabled="saving">
            Cancelar
          </v-btn>
          <v-btn color="primary" @click="saveBase" :loading="saving" :disabled="saving || !formValid">
            <v-icon start>mdi-content-save</v-icon>
            {{ editing ? 'Atualizar' : 'Salvar Base' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-error">
          <v-icon class="mr-2" color="white">mdi-alert-circle</v-icon>
          <span class="text-white">Confirmar Exclusão</span>
        </v-card-title>
        
        <v-card-text class="pa-6 text-center">
          <v-icon size="64" color="error" class="mb-4">mdi-delete-alert</v-icon>
          <p class="text-h6">Deseja excluir esta Base?</p>
          <p class="text-body-2 text-medium-emphasis">
            <strong>{{ itemToDelete?.name }}</strong><br>
            A exclusão removerá o registro e as associações, mas as informações do banco vetorial continuarão inertes.
          </p>
        </v-card-text>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="deleteDialog = false">Cancelar</v-btn>
          <v-btn color="error" @click="deleteBase" :loading="deleting">
            <v-icon start>mdi-delete</v-icon>
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Webhook Info Dialog -->
    <v-dialog v-model="webhookDialog" max-width="700">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-info">
          <v-icon class="mr-2" color="white">mdi-web</v-icon>
          <span class="text-white">Instruções de Integração</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="webhookDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <p class="mb-4">Envie dados para a base <strong>{{ webhookBase?.name }}</strong> utilizando o endpoint da webhook:</p>
          
          <v-sheet
            class="pa-4 mb-4 rounded bg-surface-variant text-body-2"
            elevation="1"
            style="font-family: monospace; overflow-x: auto;"
          >
            POST {{ webhookUrl }}/information-bases/webhook
          </v-sheet>

          <div class="d-flex align-center justify-space-between mb-2">
            <p class="text-subtitle-2 mb-0">JSON Payload pronto para usar:</p>
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
            O campo <code>id</code> representa o usuário/contato. Quando um agente processar uma mensagem desse usuário, ele terá acesso automático ao conteúdo injetado via <code>data</code>.
          </v-alert>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            O campo <code>external_id</code> é opcional. O uso de um ID determinístico permite Update ou Replace seguro de vetores em vez de recriar chaves duplicadas (Upsert).
          </v-alert>
          <v-alert type="warning" variant="tonal" density="compact">
            <code>id_base</code> já está preenchido com o código desta base. Preencha os valores de exemplo com dados reais antes de enviar.
          </v-alert>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.message }}
      <template v-slot:actions>
        <v-btn variant="text" @click="snackbar.show = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '@/plugins/axios'

// State
const bases = ref([])
const loading = ref(false)
const search = ref('')

// Dialog
const dialog = ref(false)
const editing = ref(false)
const saving = ref(false)
const formValid = ref(false)
const formRef = ref(null)

const formData = reactive({
  id: null,
  name: '',
  code: '',
  content_schema: '{}',
  metadata_schema: '{}',
  correlation_schema: '{}',
  is_active: true
})

// Delete Dialog
const deleteDialog = ref(false)
const deleting = ref(false)
const itemToDelete = ref(null)

// Webhook Dialog
const webhookDialog = ref(false)
const webhookBase = ref(null)

// Snackbar
const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

const headers = [
  { title: 'Base', key: 'name', sortable: true },
  { title: 'Status', key: 'is_active', sortable: true, width: '100px' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '150px' }
]

// Computed
const filteredBases = computed(() => {
  if (!search.value) return bases.value
  const s = search.value.toLowerCase()
  return bases.value.filter(item => 
    item.name?.toLowerCase().includes(s) || 
    item.code?.toLowerCase().includes(s)
  )
})

const activeCount = computed(() => bases.value.filter(s => s.is_active).length)

const webhookUrl = computed(() => {
  return window.location.origin + '/api'
})

// Generate sample values from a JSON schema's properties
function generateSampleFromSchema(schema) {
  if (!schema || !schema.properties) return {}
  const sample = {}
  for (const [key, prop] of Object.entries(schema.properties)) {
    const t = prop.type || 'string'
    if (t === 'string') sample[key] = prop.description ? `<${prop.description}>` : `<${key}>`
    else if (t === 'number' || t === 'integer') sample[key] = 0
    else if (t === 'boolean') sample[key] = false
    else if (t === 'array') sample[key] = []
    else if (t === 'object') sample[key] = {}
    else sample[key] = `<${key}>`
  }
  return sample
}

const generatedPayload = computed(() => {
  const base = webhookBase.value
  if (!base) return '{}'
  const dataFields = generateSampleFromSchema(base.content_schema)
  const metaFields = generateSampleFromSchema(base.metadata_schema)
  const payload = {
    id_base: base.code || 'CODIGO_DA_BASE',
    id: '<identificador-do-usuario>',
    external_id: '<ID unico do documento (opicional)>',
    data: { ...dataFields, ...metaFields }
  }
  return JSON.stringify(payload, null, 2)
})

async function copyPayload() {
  try {
    await navigator.clipboard.writeText(generatedPayload.value)
    showSnackbar('JSON copiado para a área de transferência!')
  } catch {
    showSnackbar('Erro ao copiar', 'error')
  }
}

function showSnackbar(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function resetForm() {
  Object.assign(formData, {
    id: null,
    name: '',
    code: '',
    content_schema: '{}',
    metadata_schema: '{}',
    correlation_schema: '{}',
    is_active: true
  })
  if (formRef.value) formRef.value.resetValidation()
}

// API Methods
async function fetchBases() {
  loading.value = true
  try {
    const response = await axios.get('/information-bases')
    bases.value = response.data.information_bases || []
  } catch (error) {
    console.error('Error fetching information bases:', error)
    showSnackbar('Erro ao carregar bases de informações.', 'error')
  } finally {
    loading.value = false
  }
}

async function openDialog(base = null) {
  resetForm()
  if (base) {
    editing.value = true
    try {
      const response = await axios.get(`/information-bases/${base.id}`)
      const fullBase = response.data
      Object.assign(formData, {
        id: fullBase.id,
        name: fullBase.name,
        code: fullBase.code,
        content_schema: fullBase.content_schema ? JSON.stringify(fullBase.content_schema, null, 2) : '{}',
        metadata_schema: fullBase.metadata_schema ? JSON.stringify(fullBase.metadata_schema, null, 2) : '{}',
        correlation_schema: fullBase.correlation_schema ? JSON.stringify(fullBase.correlation_schema, null, 2) : '{}',
        is_active: fullBase.is_active ?? true
      })
    } catch (error) {
      console.error('Error fetching base details:', error)
      showSnackbar('Erro ao carregar detalhes da base', 'error')
      return
    }
  } else {
    editing.value = false
  }
  dialog.value = true
}

async function openWebhookInfo(base) {
  try {
    const response = await axios.get(`/information-bases/${base.id}`)
    webhookBase.value = response.data
  } catch (error) {
    webhookBase.value = base
  }
  webhookDialog.value = true
}

async function saveBase() {
  // Validate JSON blocks before saving
  let parsedContent = {}
  let parsedMeta = {}
  let parsedCorrelation = {}
  try {
    parsedContent = JSON.parse(formData.content_schema)
    parsedMeta = JSON.parse(formData.metadata_schema)
    parsedCorrelation = JSON.parse(formData.correlation_schema)
  } catch (e) {
    showSnackbar('Schema JSON inválido. Verifique a sintaxe.', 'error')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: formData.name,
      code: formData.code,
      content_schema: parsedContent,
      metadata_schema: parsedMeta,
      correlation_schema: parsedCorrelation,
      is_active: formData.is_active
    }
    
    if (editing.value) {
      await axios.put(`/information-bases/${formData.id}`, payload)
      showSnackbar('Base atualizada com sucesso!')
    } else {
      await axios.post('/information-bases', payload)
      showSnackbar('Base criada com sucesso!')
    }
    dialog.value = false
    await fetchBases()
  } catch (error) {
    console.error('Error saving base:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao salvar base', 'error')
  } finally {
    saving.value = false
  }
}

function confirmDelete(item) {
  itemToDelete.value = item
  deleteDialog.value = true
}

async function deleteBase() {
  deleting.value = true
  try {
    await axios.delete(`/information-bases/${itemToDelete.value.id}`)
    showSnackbar('Base excluída com sucesso!')
    deleteDialog.value = false
    await fetchBases()
  } catch (error) {
    console.error('Error deleting base:', error)
    showSnackbar('Erro ao excluir base', 'error')
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  fetchBases()
})
</script>

<style scoped>
.bases-card {
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 24px;
}
.stat-card {
  border-radius: 12px;
  height: 100%;
}
.stat-avatar {
  background: linear-gradient(135deg, var(--v-theme-primary), var(--v-theme-info));
}
</style>
