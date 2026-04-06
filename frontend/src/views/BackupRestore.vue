<template>
  <div class="backup-restore-page d-flex flex-column h-100 w-100" style="padding: 0; width: 100%;">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h2 class="text-h5 font-weight-bold text-white mb-1 d-flex align-center">
          <v-icon color="primary" class="mr-3" size="32">mdi-database-export-outline</v-icon>
          Backup & Restore
        </h2>
        <p class="text-subtitle-2 text-medium-emphasis mb-0">Crie backups completos do sistema e restaure dados quando necessrio.</p>
      </div>
    </div>

    <v-card class="backup-card glass-card flex-grow-1 d-flex flex-column">
      <v-tabs v-model="tab" color="primary" class="backup-tabs border-b px-4">
        <v-tab value="backup">
          <v-icon start>mdi-database-export</v-icon>
          Backup
        </v-tab>
        <v-tab value="restore">
          <v-icon start>mdi-database-import</v-icon>
          Restore
        </v-tab>
      </v-tabs>

      <v-window v-model="tab" class="flex-grow-1 overflow-auto pa-6">
        <v-window-item value="backup" class="h-100">
          <div class="backup-section">
            <div class="d-flex justify-space-between align-center mb-6">
              <h3 class="text-h6 font-weight-medium text-white">Criar Backup do Sistema</h3>
              <v-btn
                color="primary"
                prepend-icon="mdi-database-export"
                class="glass-btn"
                :loading="backupLoading"
                :disabled="backupLoading"
                @click="createBackup"
              >
                {{ backupLoading ? 'Gerando Backup...' : 'Iniciar Backup' }}
              </v-btn>
            </div>

            <v-alert type="info" variant="tonal" class="mb-6 glass-alert">
              <template v-slot:prepend>
                <v-icon>mdi-information-outline</v-icon>
              </template>
              <div class="text-body-2">
                <strong>O que ser incluido no backup:</strong>
                <ul class="mt-2 mb-0 pl-6">
                  <li>Todas as tabelas do banco de dados PostgreSQL</li>
                  <li>Colees Weaviate (vetores de documentos, memrias)</li>
                  <li>Arquivos locais (documentos uploadados, arquivos VFS)</li>
                </ul>
                <p class="mt-2 mb-0 text-warning">
                  <v-icon size="small" class="mr-1">mdi-lock</v-icon>
                  Chaves de API e tokens so excludos por segurana.
                </p>
              </div>
            </v-alert>

            <v-card variant="outlined" class="mb-4 glass-table-card">
              <v-card-title class="text-subtitle-1 text-white d-flex align-center">
                <v-icon class="mr-2" size="20">mdi-table</v-icon>
                Tabelas do Banco de Dados
              </v-card-title>
              <v-divider></v-divider>
              <v-card-text>
                <div class="d-flex flex-wrap ga-2">
                  <v-chip
                    v-for="table in backupTables"
                    :key="table"
                    size="small"
                    variant="tonal"
                    color="primary"
                    class="text-capitalize"
                  >
                    {{ table }}
                  </v-chip>
                </div>
              </v-card-text>
            </v-card>

            <v-card variant="outlined" class="glass-table-card">
              <v-card-title class="text-subtitle-1 text-white d-flex align-center">
                <v-icon class="mr-2" size="20">mdi-vector-link</v-icon>
                Colees Weaviate
              </v-card-title>
              <v-divider></v-divider>
              <v-card-text>
                <div class="d-flex flex-wrap ga-2">
                  <v-chip
                    v-for="collection in weaviateCollections"
                    :key="collection"
                    size="small"
                    variant="tonal"
                    color="purple"
                  >
                    {{ collection }}
                  </v-chip>
                </div>
              </v-card-text>
            </v-card>

            <v-alert
              v-if="backupError"
              type="error"
              variant="tonal"
              class="mt-4"
              closable
              @click:close="backupError = ''"
            >
              {{ backupError }}
            </v-alert>
          </div>
        </v-window-item>

        <v-window-item value="restore" class="h-100">
          <div class="restore-section">
            <div class="d-flex justify-space-between align-center mb-6">
              <h3 class="text-h6 font-weight-medium text-white">Restaurar de Backup</h3>
            </div>

            <v-alert type="warning" variant="tonal" class="mb-6 glass-alert">
              <template v-slot:prepend>
                <v-icon>mdi-alert-outline</v-icon>
              </template>
              <div class="text-body-2">
                <strong>Ateno:</strong> O restore ir <u>substituir todos os dados existentes</u> no sistema.
                Certifique-se de ter um backup recente antes de prosseguir.
              </div>
            </v-alert>

            <div
              class="upload-zone glass-upload-zone mb-6"
              :class="{ 'drag-over': dragOver, 'has-file': selectedFile }"
              @dragover.prevent="dragOver = true"
              @dragleave.prevent="dragOver = false"
              @drop.prevent="handleFileDrop"
              @click="triggerFileInput"
            >
              <input
                ref="fileInput"
                type="file"
                accept=".json"
                style="display: none"
                @change="handleFileSelect"
              />
              <v-icon size="64" :color="selectedFile ? 'success' : 'primary'">
                {{ selectedFile ? 'mdi-file-check-outline' : 'mdi-database-import' }}
              </v-icon>
              <p class="text-h6 text-white mt-4 mb-2">
                {{ selectedFile ? selectedFile.name : 'Arraste o arquivo de backup aqui' }}
              </p>
              <p class="text-body-2 text-medium-emphasis">
                {{ selectedFile ? formatFileSize(selectedFile.size) : 'ou clique para selecionar' }}
              </p>
              <p class="text-caption text-medium-emphasis mt-2">
                Aceita arquivos .json
              </p>
            </div>

            <div v-if="selectedFile" class="restore-options mb-4">
              <v-card variant="outlined" class="glass-table-card">
                <v-card-title class="text-subtitle-1 text-white d-flex align-center">
                  <v-icon class="mr-2" size="20">mdi-cog</v-icon>
                  Opes de Restore
                </v-card-title>
                <v-divider></v-divider>
                <v-card-text>
                  <v-switch
                    v-model="skipFiles"
                    label="Pular restaurao de arquivos (apenas banco de dados)"
                    color="primary"
                    hide-details
                    density="comfortable"
                  ></v-switch>
                </v-card-text>
              </v-card>
            </div>

            <div v-if="selectedFile" class="d-flex ga-3 mb-4">
              <v-btn
                color="info"
                prepend-icon="mdi-eye"
                class="glass-btn"
                :loading="dryRunLoading"
                :disabled="dryRunLoading || restoreLoading"
                @click="dryRunRestore"
              >
                {{ dryRunLoading ? 'Analisando...' : 'Preview (Dry Run)' }}
              </v-btn>
              <v-btn
                color="success"
                prepend-icon="mdi-database-import"
                class="glass-btn"
                :loading="restoreLoading"
                :disabled="dryRunLoading || restoreLoading"
                @click="confirmRestore"
              >
                {{ restoreLoading ? 'Restaurando...' : 'Restaurar Backup' }}
              </v-btn>
            </div>

            <v-alert
              v-if="dryRunResult"
              type="info"
              variant="tonal"
              class="mb-4"
              closable
              @click:close="dryRunResult = null"
            >
              <div class="text-body-2">
                <strong>Preview do Restore:</strong>
                <div v-if="dryRunResult.would_restore" class="mt-2">
                  <div v-for="(count, category) in dryRunResult.would_restore.tables" :key="category">
                    Tabela {{ category }}: {{ count }} registros
                  </div>
                  <div v-for="(count, collection) in dryRunResult.would_restore.weaviate" :key="collection">
                    Coleo {{ collection }}: {{ count }} objetos
                  </div>
                  <div v-if="dryRunResult.would_restore.files">
                    Arquivos documentos: {{ dryRunResult.would_restore.files.documents || 0 }}
                    <br />
                    Arquivos VFS: {{ dryRunResult.would_restore.files.vfs || 0 }}
                  </div>
                </div>
                <div v-if="dryRunResult.warnings?.length" class="mt-2 text-warning">
                  <strong>Avisos:</strong>
                  <ul class="mb-0 pl-6">
                    <li v-for="warning in dryRunResult.warnings" :key="warning">{{ warning }}</li>
                  </ul>
                </div>
              </div>
            </v-alert>

            <v-alert
              v-if="restoreError"
              type="error"
              variant="tonal"
              class="mt-4"
              closable
              @click:close="restoreError = ''"
            >
              {{ restoreError }}
            </v-alert>

            <v-alert
              v-if="restoreSuccess"
              type="success"
              variant="tonal"
              class="mt-4"
              closable
              @click:close="restoreSuccess = ''"
            >
              {{ restoreSuccess }}
            </v-alert>
          </div>
        </v-window-item>
      </v-window>
    </v-card>

    <v-dialog v-model="confirmDialog" max-width="500" persistent>
      <v-card class="glass-dialog">
        <v-card-title class="pa-6 border-b d-flex align-center justify-space-between text-white">
          Confirmar Restore
          <v-btn icon="mdi-close" variant="text" density="compact" @click="confirmDialog = false"></v-btn>
        </v-card-title>
        <v-card-text class="pa-6">
          <p class="text-body-1 mb-4">
            Tem certeza que deseja restaurar o backup "{{ selectedFile?.name }}"?
          </p>
          <v-alert type="error" variant="tonal">
            <strong>Esta ao ir substituir TODOS os dados existentes no sistema.</strong>
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-6 border-t">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="confirmDialog = false" class="text-white">Cancelar</v-btn>
          <v-btn color="error" variant="flat" :loading="restoreLoading" @click="executeRestore">
            Confirmar Restore
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000" location="top right">
      {{ snackbar.message }}
      <template v-slot:actions>
        <v-btn icon="mdi-close" variant="text" @click="snackbar.show = false"></v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import axios from '@/plugins/axios'

const tab = ref('backup')
const backupLoading = ref(false)
const backupError = ref('')
const restoreLoading = ref(false)
const dryRunLoading = ref(false)
const restoreError = ref('')
const restoreSuccess = ref('')
const dragOver = ref(false)
const selectedFile = ref(null)
const skipFiles = ref(false)
const dryRunResult = ref(null)
const confirmDialog = ref(false)
const fileInput = ref(null)

const snackbar = reactive({ show: false, message: '', color: 'success' })

const backupTables = [
  'ai_providers', 'emotional_profiles', 'agent_groups', 'mcp_groups',
  'skill_groups', 'vfs_knowledge_bases', 'information_bases', 'agents',
  'mcps', 'skills', 'documents', 'vfs_files', 'agent_configs',
  'agent_collaborators', 'pending_approvals', 'webhook_configs',
  'job_logs', 'conversation_messages', 'api_keys'
]

const weaviateCollections = [
  'AgentDocuments', 'ContactMemory', 'AgentSelfMemory', 'InformationBaseNode'
]

const showMessage = (msg, color = 'success') => {
  snackbar.message = msg
  snackbar.color = color
  snackbar.show = true
}

const createBackup = async () => {
  backupLoading.value = true
  backupError.value = ''
  
  try {
    // Use fetch API directly - bypasses Vue Router and axios interceptors
    const response = await fetch('/api/backup/create')
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `HTTP ${response.status}`)
    }
    
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    
    // Extract filename from Content-Disposition or use fallback
    const cd = response.headers.get('content-disposition')
    let filename = `basile_backup_${new Date().toISOString().slice(0, 19).replace(/:/g, '')}.json`
    if (cd && cd.includes('filename=')) {
      const match = cd.match(/filename="?([^";\s]+)"?/)
      if (match) filename = match[1]
    }
    
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    
    showMessage('Backup gerado e download iniciado com sucesso!')
  } catch (error) {
    console.error('Error creating backup:', error)
    backupError.value = error.message || 'Erro ao criar backup. Tente novamente.'
    showMessage(backupError.value, 'error')
  } finally {
    backupLoading.value = false
  }
}

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event) => {
  const file = event.target.files?.[0]
  if (file) {
    selectedFile.value = file
    dryRunResult.value = null
    restoreError.value = ''
    restoreSuccess.value = ''
  }
}

const handleFileDrop = (event) => {
  dragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file && file.name.endsWith('.json')) {
    selectedFile.value = file
    dryRunResult.value = null
    restoreError.value = ''
    restoreSuccess.value = ''
  } else {
    showMessage('Por favor, selecione um arquivo .json vlido.', 'error')
  }
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const dryRunRestore = async () => {
  if (!selectedFile.value) {
    showMessage('Selecione um arquivo de backup primeiro.', 'warning')
    return
  }
  
  dryRunLoading.value = true
  dryRunResult.value = null
  restoreError.value = ''
  
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    
    const response = await axios.post('/backup/dry-run', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    dryRunResult.value = response.data
    showMessage('Anlise do backup concluda!', 'success')
  } catch (error) {
    console.error('Error during dry run:', error)
    restoreError.value = error.response?.data?.detail || 'Erro ao analisar backup.'
    showMessage(restoreError.value, 'error')
  } finally {
    dryRunLoading.value = false
  }
}

const confirmRestore = () => {
  confirmDialog.value = true
}

const executeRestore = async () => {
  if (!selectedFile.value) {
    showMessage('Selecione um arquivo de backup primeiro.', 'warning')
    return
  }
  
  confirmDialog.value = false
  restoreLoading.value = true
  restoreError.value = ''
  restoreSuccess.value = ''
  dryRunResult.value = null
  
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('skip_files', skipFiles.value.toString())
    formData.append('dry_run', 'false')
    
    const response = await axios.post('/backup/restore', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    restoreSuccess.value = 'Backup restaurado com sucesso! O sistema pode precisar ser recarregado.'
    showMessage(restoreSuccess.value, 'success')
    
    selectedFile.value = null
    skipFiles.value = false
  } catch (error) {
    console.error('Error restoring backup:', error)
    restoreError.value = error.response?.data?.detail || 'Erro ao restaurar backup.'
    showMessage(restoreError.value, 'error')
  } finally {
    restoreLoading.value = false
  }
}
</script>

<style scoped>
.backup-restore-page {
  animation: fadeIn 0.4s ease-out;
}

.backup-card {
  border-radius: 16px;
  background: rgba(20, 24, 40, 0.6) !important;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}

.backup-tabs {
  background: transparent !important;
  border-bottom-color: rgba(255, 255, 255, 0.05) !important;
}

.backup-tabs :deep(.v-tab) {
  text-transform: none;
  font-weight: 500;
  letter-spacing: 0;
  color: rgba(255, 255, 255, 0.6);
}

.backup-tabs :deep(.v-tab--selected) {
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

.glass-alert {
  background: rgba(20, 24, 40, 0.5) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(8px);
}

.glass-table-card {
  background: rgba(15, 18, 30, 0.4) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.glass-upload-zone {
  background: rgba(20, 24, 40, 0.5) !important;
  border: 2px dashed rgba(157, 78, 221, 0.4);
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
}

.glass-upload-zone:hover {
  border-color: rgba(157, 78, 221, 0.7);
  background: rgba(25, 30, 50, 0.6) !important;
}

.glass-upload-zone.drag-over {
  border-color: #9D4EDD;
  background: rgba(157, 78, 221, 0.1) !important;
}

.glass-upload-zone.has-file {
  border-color: rgba(34, 197, 94, 0.5);
  background: rgba(34, 197, 94, 0.05) !important;
}

.glass-dialog {
  background: rgba(20, 24, 40, 0.95) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6) !important;
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
