<template>
  <div class="vfs-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-file-document-multiple-outline</v-icon>
        </div>
        <div class="header-text">
          <h1>Base VFS (RAG 3.0)</h1>
          <p>Gerencie bases de conhecimento com arquivos .md para recuperação inteligente por subagente</p>
        </div>
      </div>
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="openKBDialog()" elevation="3">
        Nova Base VFS
      </v-btn>
    </div>

    <!-- Stats Cards -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-folder-multiple</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ knowledgeBases.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Bases VFS</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-file-document</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ totalFiles }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Arquivos .md</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
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
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-scale-balance</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ formattedSize }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Tamanho Total</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Knowledge Bases Table -->
    <v-card class="vfs-card glass-card">
      <v-card-title class="d-flex align-center pa-4">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="Buscar base..."
          density="compact"
          variant="outlined"
          hide-details
          class="mr-4"
          style="max-width: 350px"
        />
        <v-spacer />
      </v-card-title>

      <v-data-table
        :headers="kbHeaders"
        :items="filteredKBs"
        :loading="loading"
        :search="search"
        items-per-page="10"
        class="glass-table"
        hover
      >
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'grey'" size="small" variant="tonal">
            {{ item.is_active ? 'Ativa' : 'Inativa' }}
          </v-chip>
        </template>

        <template v-slot:item.file_count="{ item }">
          <v-chip color="info" size="small" variant="tonal" prepend-icon="mdi-file-document">
            {{ item.file_count || 0 }}
          </v-chip>
        </template>

        <template v-slot:item.total_size_bytes="{ item }">
          {{ formatBytes(item.total_size_bytes) }}
        </template>

        <template v-slot:item.actions="{ item }">
          <v-btn icon variant="text" size="small" color="info" @click="openFilesView(item)" title="Ver Arquivos">
            <v-icon size="20">mdi-folder-open</v-icon>
          </v-btn>
          <v-btn icon variant="text" size="small" color="primary" @click="openKBDialog(item)" title="Editar">
            <v-icon size="20">mdi-pencil</v-icon>
          </v-btn>
          <v-btn icon variant="text" size="small" color="error" @click="confirmDeleteKB(item)" title="Excluir">
            <v-icon size="20">mdi-delete</v-icon>
          </v-btn>
        </template>
      </v-data-table>
    </v-card>

    <!-- KB Create/Edit Dialog -->
    <v-dialog v-model="kbDialog" max-width="600">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="primary">mdi-folder-plus</v-icon>
          {{ editingKB ? 'Editar Base VFS' : 'Nova Base VFS' }}
        </v-card-title>
        <v-card-text>
          <v-form v-model="kbFormValid">
            <v-text-field
              v-model="kbForm.name"
              label="Nome da Base"
              :rules="[v => !!v || 'Nome é obrigatório']"
              variant="outlined"
              density="comfortable"
              class="mb-3"
            />
            <v-textarea
              v-model="kbForm.description"
              label="Descrição"
              variant="outlined"
              density="comfortable"
              rows="3"
              class="mb-3"
            />
            <v-switch
              v-if="editingKB"
              v-model="kbForm.is_active"
              label="Base Ativa"
              color="success"
              density="compact"
            />
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="kbDialog = false">Cancelar</v-btn>
          <v-btn color="primary" :loading="savingKB" :disabled="!kbFormValid" @click="saveKB">
            {{ editingKB ? 'Salvar' : 'Criar' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Files View Dialog -->
    <v-dialog v-model="filesDialog" max-width="1000" scrollable>
      <v-card class="glass-card" min-height="600">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="info">mdi-folder-open</v-icon>
          <span>{{ selectedKB?.name }} — Arquivos</span>
          <v-spacer />
          <v-btn color="primary" size="small" prepend-icon="mdi-plus" variant="tonal" class="mr-2" @click="openFileCreateDialog">
            Criar Arquivo
          </v-btn>
          <v-btn color="info" size="small" prepend-icon="mdi-upload" variant="tonal" @click="openFileUpload">
            Upload .md
          </v-btn>
        </v-card-title>

        <v-divider />

        <v-card-text v-if="loadingFiles" class="d-flex justify-center align-center" style="min-height: 300px">
          <v-progress-circular indeterminate color="primary" />
        </v-card-text>

        <v-card-text v-else-if="files.length === 0" class="d-flex flex-column align-center justify-center text-center" style="min-height: 300px">
          <v-icon size="64" color="grey" class="mb-4">mdi-file-document-outline</v-icon>
          <p class="text-h6 text-medium-emphasis mb-2">Nenhum arquivo</p>
          <p class="text-body-2 text-medium-emphasis">Clique em "Criar Arquivo" ou "Upload .md" para adicionar</p>
        </v-card-text>

        <v-card-text v-else class="pa-0">
          <v-list lines="two">
            <v-list-item
              v-for="file in files" :key="file.id"
              class="file-item"
            >
              <template v-slot:prepend>
                <v-icon color="info" size="24" class="mr-3">mdi-language-markdown</v-icon>
              </template>

              <v-list-item-title class="font-weight-medium">{{ file.title || file.filename }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ file.filename }} · {{ formatBytes(file.size_bytes) }}
                <span v-if="file.summary" class="ml-2 text-medium-emphasis">— {{ file.summary.substring(0, 100) }}{{ file.summary.length > 100 ? '...' : '' }}</span>
              </v-list-item-subtitle>

              <template v-slot:append>
                <v-btn icon variant="text" size="small" color="info" @click="viewFile(file)" title="Visualizar">
                  <v-icon size="18">mdi-eye</v-icon>
                </v-btn>
                <v-btn icon variant="text" size="small" color="primary" @click="editFile(file)" title="Editar">
                  <v-icon size="18">mdi-pencil</v-icon>
                </v-btn>
                <v-btn icon variant="text" size="small" color="error" @click="confirmDeleteFile(file)" title="Excluir">
                  <v-icon size="18">mdi-delete</v-icon>
                </v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- File Create/Edit Dialog -->
    <v-dialog v-model="fileDialog" max-width="900" scrollable persistent>
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="primary">{{ editingFile ? 'mdi-file-edit' : 'mdi-file-plus' }}</v-icon>
          {{ editingFile ? 'Editar Arquivo' : 'Novo Arquivo .md' }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="fileForm.filename"
            label="Nome do Arquivo"
            hint="Ex: guia-de-uso.md"
            variant="outlined"
            density="comfortable"
            class="mb-3"
            :disabled="editingFile"
          />
          <v-text-field
            v-model="fileForm.title"
            label="Título (opcional)"
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />

          <!-- Tabs for editor/preview -->
          <v-tabs v-model="editorTab" color="primary" density="compact" class="mb-3">
            <v-tab value="editor">
              <v-icon class="mr-1" size="18">mdi-code-tags</v-icon>
              Editor
            </v-tab>
            <v-tab value="preview">
              <v-icon class="mr-1" size="18">mdi-eye</v-icon>
              Preview
            </v-tab>
          </v-tabs>

          <v-window v-model="editorTab">
            <v-window-item value="editor">
              <v-textarea
                v-model="fileForm.content"
                label="Conteúdo Markdown"
                variant="outlined"
                rows="18"
                auto-grow
                class="markdown-editor"
                placeholder="# Título&#10;&#10;Conteúdo do documento..."
              />
            </v-window-item>
            <v-window-item value="preview">
              <v-card variant="outlined" class="pa-4" min-height="300">
                <div class="markdown-preview" v-html="renderedMarkdown"></div>
              </v-card>
            </v-window-item>
          </v-window>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="fileDialog = false">Cancelar</v-btn>
          <v-btn color="primary" :loading="savingFile" :disabled="!fileForm.filename || !fileForm.content" @click="saveFile">
            {{ editingFile ? 'Salvar' : 'Criar' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- File View Dialog -->
    <v-dialog v-model="viewDialog" max-width="800" scrollable>
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="info">mdi-file-document</v-icon>
          {{ viewingFile?.title || viewingFile?.filename }}
        </v-card-title>
        <v-card-text>
          <v-card variant="outlined" class="pa-4">
            <div class="markdown-preview" v-html="viewContent"></div>
          </v-card>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="viewDialog = false">Fechar</v-btn>
          <v-btn color="primary" variant="tonal" @click="viewDialog = false; editFile(viewingFile)">Editar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Hidden File Upload Input -->
    <input
      ref="fileInput"
      type="file"
      accept=".md"
      multiple
      style="display: none"
      @change="handleFileUpload"
    />

    <!-- Delete KB Dialog -->
    <v-dialog v-model="deleteKBDialog" max-width="440">
      <v-card class="glass-card">
        <v-card-title class="text-h6 pa-4">Confirmar Exclusão</v-card-title>
        <v-card-text>
          Tem certeza que deseja excluir a base <strong>{{ itemToDeleteKB?.name }}</strong> e todos os seus arquivos?
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteKBDialog = false">Cancelar</v-btn>
          <v-btn color="error" :loading="deletingKB" @click="deleteKB">Excluir</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete File Dialog -->
    <v-dialog v-model="deleteFileDialog" max-width="440">
      <v-card class="glass-card">
        <v-card-title class="text-h6 pa-4">Confirmar Exclusão</v-card-title>
        <v-card-text>
          Tem certeza que deseja excluir o arquivo <strong>{{ itemToDeleteFile?.filename }}</strong>?
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteFileDialog = false">Cancelar</v-btn>
          <v-btn color="error" :loading="deletingFile" @click="deleteFile">Excluir</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="4000" location="bottom right">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import axios from '@/plugins/axios'
import { marked } from 'marked'

// State
const knowledgeBases = ref([])
const files = ref([])
const loading = ref(false)
const loadingFiles = ref(false)
const search = ref('')
const selectedKB = ref(null)

// KB Dialog
const kbDialog = ref(false)
const editingKB = ref(false)
const savingKB = ref(false)
const kbFormValid = ref(false)
const kbForm = reactive({ name: '', description: '', is_active: true })

// Files Dialog
const filesDialog = ref(false)
const fileDialog = ref(false)
const editingFile = ref(false)
const savingFile = ref(false)
const editorTab = ref('editor')
const fileForm = reactive({ id: null, filename: '', title: '', content: '' })

// View Dialog
const viewDialog = ref(false)
const viewingFile = ref(null)
const viewContent = ref('')

// Delete Dialogs
const deleteKBDialog = ref(false)
const deletingKB = ref(false)
const itemToDeleteKB = ref(null)
const deleteFileDialog = ref(false)
const deletingFile = ref(false)
const itemToDeleteFile = ref(null)

// File Upload
const fileInput = ref(null)

// Snackbar
const snackbar = reactive({ show: false, message: '', color: 'success' })

// Headers
const kbHeaders = [
  { title: 'Nome', key: 'name', sortable: true },
  { title: 'Descrição', key: 'description', sortable: false },
  { title: 'Arquivos', key: 'file_count', sortable: true, width: '100px', align: 'center' },
  { title: 'Tamanho', key: 'total_size_bytes', sortable: true, width: '100px' },
  { title: 'Status', key: 'is_active', sortable: true, width: '100px' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '160px' }
]

// Computed
const filteredKBs = computed(() => {
  if (!search.value) return knowledgeBases.value
  const s = search.value.toLowerCase()
  return knowledgeBases.value.filter(kb =>
    kb.name?.toLowerCase().includes(s) ||
    kb.description?.toLowerCase().includes(s)
  )
})

const totalFiles = computed(() => knowledgeBases.value.reduce((sum, kb) => sum + (kb.file_count || 0), 0))
const activeCount = computed(() => knowledgeBases.value.filter(kb => kb.is_active).length)
const totalSize = computed(() => knowledgeBases.value.reduce((sum, kb) => sum + (kb.total_size_bytes || 0), 0))
const formattedSize = computed(() => formatBytes(totalSize.value))

const renderedMarkdown = computed(() => {
  try {
    return marked(fileForm.content || '')
  } catch { return '' }
})

// Helpers
function showSnackbar(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// ── API: Knowledge Bases ──────────────────────────────

async function fetchKBs() {
  loading.value = true
  try {
    const response = await axios.get('/vfs-knowledge-bases')
    knowledgeBases.value = response.data || []
  } catch (error) {
    console.error('Error fetching VFS knowledge bases:', error)
    showSnackbar('Erro ao carregar bases VFS', 'error')
  } finally {
    loading.value = false
  }
}

function openKBDialog(kb = null) {
  Object.assign(kbForm, { name: '', description: '', is_active: true })
  if (kb) {
    editingKB.value = true
    Object.assign(kbForm, { name: kb.name, description: kb.description || '', is_active: kb.is_active })
    kbForm._id = kb.id
  } else {
    editingKB.value = false
  }
  kbDialog.value = true
}

async function saveKB() {
  savingKB.value = true
  try {
    if (editingKB.value) {
      await axios.put(`/vfs-knowledge-bases/${kbForm._id}`, {
        name: kbForm.name,
        description: kbForm.description,
        is_active: kbForm.is_active
      })
      showSnackbar('Base VFS atualizada!')
    } else {
      await axios.post('/vfs-knowledge-bases', {
        name: kbForm.name,
        description: kbForm.description
      })
      showSnackbar('Base VFS criada!')
    }
    kbDialog.value = false
    await fetchKBs()
  } catch (error) {
    console.error('Error saving VFS KB:', error)
    showSnackbar('Erro ao salvar base', 'error')
  } finally {
    savingKB.value = false
  }
}

function confirmDeleteKB(item) {
  itemToDeleteKB.value = item
  deleteKBDialog.value = true
}

async function deleteKB() {
  deletingKB.value = true
  try {
    await axios.delete(`/vfs-knowledge-bases/${itemToDeleteKB.value.id}`)
    showSnackbar('Base VFS excluída!')
    deleteKBDialog.value = false
    await fetchKBs()
  } catch (error) {
    showSnackbar('Erro ao excluir', 'error')
  } finally {
    deletingKB.value = false
  }
}

// ── API: Files ──────────────────────────────────────

async function openFilesView(kb) {
  selectedKB.value = kb
  filesDialog.value = true
  await fetchFiles(kb.id)
}

async function fetchFiles(kbId) {
  loadingFiles.value = true
  try {
    const response = await axios.get(`/vfs-knowledge-bases/${kbId}/files`)
    files.value = response.data || []
  } catch (error) {
    console.error('Error fetching files:', error)
    showSnackbar('Erro ao carregar arquivos', 'error')
  } finally {
    loadingFiles.value = false
  }
}

function openFileCreateDialog() {
  editingFile.value = false
  Object.assign(fileForm, { id: null, filename: '', title: '', content: '' })
  editorTab.value = 'editor'
  fileDialog.value = true
}

async function editFile(file) {
  editingFile.value = true
  editorTab.value = 'editor'
  try {
    const response = await axios.get(`/vfs-knowledge-bases/${selectedKB.value.id}/files/${file.id}`)
    Object.assign(fileForm, {
      id: file.id,
      filename: response.data.filename,
      title: response.data.title || '',
      content: response.data.content || ''
    })
    fileDialog.value = true
  } catch (error) {
    showSnackbar('Erro ao carregar arquivo', 'error')
  }
}

async function viewFile(file) {
  viewingFile.value = file
  try {
    const response = await axios.get(`/vfs-knowledge-bases/${selectedKB.value.id}/files/${file.id}`)
    viewContent.value = marked(response.data.content || '')
    viewDialog.value = true
  } catch (error) {
    showSnackbar('Erro ao carregar arquivo', 'error')
  }
}

async function saveFile() {
  savingFile.value = true
  try {
    if (editingFile.value) {
      await axios.put(`/vfs-knowledge-bases/${selectedKB.value.id}/files/${fileForm.id}`, {
        title: fileForm.title,
        content: fileForm.content
      })
      showSnackbar('Arquivo atualizado!')
    } else {
      const formDataObj = new FormData()
      formDataObj.append('filename', fileForm.filename)
      formDataObj.append('title', fileForm.title)
      formDataObj.append('content', fileForm.content)
      await axios.post(`/vfs-knowledge-bases/${selectedKB.value.id}/files/create`, formDataObj)
      showSnackbar('Arquivo criado!')
    }
    fileDialog.value = false
    await fetchFiles(selectedKB.value.id)
    await fetchKBs()  // refresh stats
  } catch (error) {
    console.error('Error saving file:', error)
    showSnackbar('Erro ao salvar arquivo', 'error')
  } finally {
    savingFile.value = false
  }
}

function openFileUpload() {
  fileInput.value?.click()
}

async function handleFileUpload(event) {
  const uploadFiles = event.target.files
  if (!uploadFiles || !selectedKB.value) return

  for (const file of uploadFiles) {
    try {
      const formDataObj = new FormData()
      formDataObj.append('file', file)
      await axios.post(`/vfs-knowledge-bases/${selectedKB.value.id}/files`, formDataObj, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    } catch (error) {
      showSnackbar(`Erro ao enviar ${file.name}`, 'error')
    }
  }

  showSnackbar(`${uploadFiles.length} arquivo(s) enviado(s)!`)
  event.target.value = ''
  await fetchFiles(selectedKB.value.id)
  await fetchKBs()
}

function confirmDeleteFile(file) {
  itemToDeleteFile.value = file
  deleteFileDialog.value = true
}

async function deleteFile() {
  deletingFile.value = true
  try {
    await axios.delete(`/vfs-knowledge-bases/${selectedKB.value.id}/files/${itemToDeleteFile.value.id}`)
    showSnackbar('Arquivo excluído!')
    deleteFileDialog.value = false
    await fetchFiles(selectedKB.value.id)
    await fetchKBs()
  } catch (error) {
    showSnackbar('Erro ao excluir arquivo', 'error')
  } finally {
    deletingFile.value = false
  }
}

onMounted(() => {
  fetchKBs()
})
</script>

<style scoped>
.vfs-page {
  padding: 0;
  width: 100%;
}

.vfs-card {
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 24px;
}

:deep(.v-data-table) {
  background: transparent !important;
}

.file-item {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.file-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.markdown-editor :deep(.v-field__input) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
}

.markdown-preview {
  font-size: 14px;
  line-height: 1.7;
}

.markdown-preview :deep(h1) { font-size: 1.6em; font-weight: 700; margin: 1em 0 0.5em; }
.markdown-preview :deep(h2) { font-size: 1.3em; font-weight: 600; margin: 0.8em 0 0.4em; }
.markdown-preview :deep(h3) { font-size: 1.1em; font-weight: 600; margin: 0.6em 0 0.3em; }
.markdown-preview :deep(p) { margin: 0.5em 0; }
.markdown-preview :deep(ul), .markdown-preview :deep(ol) { padding-left: 1.5em; margin: 0.5em 0; }
.markdown-preview :deep(code) {
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
.markdown-preview :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.markdown-preview :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-preview :deep(blockquote) {
  border-left: 3px solid rgba(124, 58, 237, 0.5);
  padding-left: 12px;
  margin: 0.5em 0;
  opacity: 0.85;
}
</style>
