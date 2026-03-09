<template>
  <div class="documents-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-book-open-page-variant-outline</v-icon>
        </div>
        <div class="header-text">
          <h1>Base de Conhecimento</h1>
          <p>Gerencie documentos para RAG (Retrieval-Augmented Generation)</p>
        </div>
      </div>
      <v-btn color="primary" size="large" prepend-icon="mdi-upload" @click="showUploadModal = true" elevation="3">
        Upload de Documento
      </v-btn>
    </div>

    <!-- Stats Cards -->
    <v-row class="mb-6">
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-file-document-multiple</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ documents.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Documentos</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-check-circle</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ readyCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Prontos</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-puzzle</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ totalChunks }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Chunks</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-earth</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ globalCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Globais</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Filters -->
    <v-card class="glass-card mb-6 pa-4">
      <div class="d-flex align-center flex-wrap ga-3">
        <v-text-field
          v-model="searchQuery"
          prepend-inner-icon="mdi-magnify"
          placeholder="Buscar documentos..."
          variant="outlined"
          density="compact"
          hide-details
          style="max-width: 320px; min-width: 200px;"
        ></v-text-field>

        <v-btn-toggle v-model="statusFilter" density="compact" variant="outlined" color="primary" divided rounded="lg">
          <v-btn :value="null" size="small">Todos</v-btn>
          <v-btn value="ready" size="small">
            <v-icon start size="14" color="success">mdi-check-circle</v-icon>
            Prontos
          </v-btn>
          <v-btn value="processing" size="small">
            <v-icon start size="14" color="info">mdi-progress-clock</v-icon>
            Processando
          </v-btn>
          <v-btn value="error" size="small">
            <v-icon start size="14" color="error">mdi-alert-circle</v-icon>
            Erro
          </v-btn>
        </v-btn-toggle>
      </div>
    </v-card>

    <!-- Documents Grid -->
    <v-row v-if="filteredDocuments.length > 0">
      <v-col cols="12" sm="6" md="4" lg="3" v-for="doc in filteredDocuments" :key="doc.id">
        <v-card class="glass-card doc-card h-100 d-flex flex-column" :class="{ 'global-border': doc.is_global }">
          <v-card-text class="pa-4 d-flex flex-column flex-grow-1">
            <!-- Top -->
            <div class="d-flex justify-space-between align-start mb-3">
              <v-avatar :color="getFileColor(doc.file_type)" size="40" rounded="lg">
                <v-icon color="white" size="22">{{ getFileIcon(doc.file_type) }}</v-icon>
              </v-avatar>
              <v-chip
                :color="getStatusColor(doc.status)"
                size="x-small"
                variant="tonal"
                :prepend-icon="getStatusIcon(doc.status)"
              >
                {{ getStatusLabel(doc.status) }}
              </v-chip>
            </div>

            <!-- Name & Meta -->
            <h3 class="text-body-1 font-weight-bold mb-2 text-truncate">{{ doc.name }}</h3>
            <div class="d-flex flex-wrap ga-2 mb-3">
              <v-chip size="x-small" variant="outlined" color="grey">{{ doc.file_type?.toUpperCase() }}</v-chip>
              <v-chip size="x-small" variant="outlined" color="grey" prepend-icon="mdi-puzzle-outline">{{ doc.chunk_count }} chunks</v-chip>
              <v-chip v-if="doc.is_global" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-earth">Global</v-chip>
            </div>

            <v-spacer />

            <!-- Actions -->
            <div class="d-flex justify-end ga-1 mt-auto">
              <v-btn icon variant="text" size="small" color="primary" @click="viewDocument(doc)">
                <v-icon size="20">mdi-eye-outline</v-icon>
                <v-tooltip activator="parent" location="top">Ver detalhes</v-tooltip>
              </v-btn>
              <v-btn icon variant="text" size="small" color="info" @click="reprocessDocument(doc)" :disabled="doc.status === 'processing'">
                <v-icon size="20">mdi-refresh</v-icon>
                <v-tooltip activator="parent" location="top">Reprocessar</v-tooltip>
              </v-btn>
              <v-btn icon variant="text" size="small" color="error" @click="confirmDelete(doc)">
                <v-icon size="20">mdi-delete-outline</v-icon>
                <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Empty State -->
    <v-card v-else class="glass-card py-16 text-center">
      <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-file-document-remove-outline</v-icon>
      <h3 class="text-h6 text-medium-emphasis mb-2">Nenhum documento encontrado</h3>
      <p class="text-body-2 text-medium-emphasis mb-4">Faça upload do primeiro documento para começar</p>
      <v-btn color="primary" prepend-icon="mdi-upload" @click="showUploadModal = true">
        Upload de Documento
      </v-btn>
    </v-card>

    <!-- Upload Dialog -->
    <v-dialog v-model="showUploadModal" max-width="600" persistent>
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-primary">
          <v-icon class="mr-2" color="white">mdi-upload</v-icon>
          <span class="text-white">Upload de Documento</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="showUploadModal = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <!-- Drop Zone -->
          <div
            class="upload-zone mb-4"
            :class="{ 'drag-active': isDragOver }"
            @drop.prevent="handleDrop"
            @dragover.prevent="isDragOver = true"
            @dragleave="isDragOver = false"
          >
            <div v-if="!selectedFile" class="text-center">
              <v-icon size="48" color="primary" class="mb-3">mdi-cloud-upload-outline</v-icon>
              <p class="text-body-1 mb-2">Arraste um arquivo aqui</p>
              <v-btn variant="outlined" color="primary" size="small" @click="$refs.fileInput.click()">
                Selecione um arquivo
              </v-btn>
              <input ref="fileInput" type="file" @change="handleFileSelect" accept=".pdf,.txt,.md,.docx,.html,.json,.csv" style="display:none" />
              <p class="text-caption text-medium-emphasis mt-2">PDF, TXT, MD, DOCX, HTML, JSON, CSV</p>
            </div>
            <div v-else class="d-flex align-center justify-space-between pa-2">
              <div class="d-flex align-center">
                <v-avatar :color="getFileColor(getFileExtension(selectedFile.name))" size="36" rounded="lg" class="mr-3">
                  <v-icon color="white" size="18">{{ getFileIcon(getFileExtension(selectedFile.name)) }}</v-icon>
                </v-avatar>
                <div>
                  <span class="font-weight-medium">{{ selectedFile.name }}</span>
                  <span class="text-caption text-medium-emphasis ml-2">({{ formatFileSize(selectedFile.size) }})</span>
                </div>
              </div>
              <v-btn icon variant="text" size="small" color="error" @click="selectedFile = null">
                <v-icon>mdi-close</v-icon>
              </v-btn>
            </div>
          </div>

          <v-text-field
            v-model="uploadForm.name"
            label="Nome do Documento (opcional)"
            variant="outlined"
            density="compact"
            class="mb-3"
          ></v-text-field>

          <v-textarea
            v-model="uploadForm.description"
            label="Descrição"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-3"
          ></v-textarea>

          <v-row>
            <v-col cols="6">
              <v-text-field
                v-model.number="uploadForm.chunk_size"
                label="Tamanho do Chunk"
                type="number"
                min="100"
                max="4000"
                variant="outlined"
                density="compact"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="uploadForm.chunk_overlap"
                label="Overlap"
                type="number"
                min="0"
                max="1000"
                variant="outlined"
                density="compact"
              ></v-text-field>
            </v-col>
          </v-row>

          <v-switch
            v-model="uploadForm.is_global"
            label="Documento Global (disponível para todos os agentes)"
            color="warning"
            hide-details
            density="compact"
          ></v-switch>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="showUploadModal = false" :disabled="uploading">Cancelar</v-btn>
          <v-btn color="primary" @click="uploadDocument" :loading="uploading" :disabled="!selectedFile">
            <v-icon start>mdi-upload</v-icon>
            Enviar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Document Details Dialog -->
    <v-dialog v-model="detailsDialog" max-width="700">
      <v-card v-if="selectedDocument">
        <v-card-title class="d-flex align-center px-6 py-4 bg-primary">
          <v-icon class="mr-2" color="white">{{ getFileIcon(selectedDocument.file_type) }}</v-icon>
          <span class="text-white text-truncate">{{ selectedDocument.name }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="detailsDialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-row>
            <v-col cols="6" sm="4">
              <div class="text-caption text-medium-emphasis mb-1">Status</div>
              <v-chip :color="getStatusColor(selectedDocument.status)" size="small" :prepend-icon="getStatusIcon(selectedDocument.status)">
                {{ getStatusLabel(selectedDocument.status) }}
              </v-chip>
            </v-col>
            <v-col cols="6" sm="4">
              <div class="text-caption text-medium-emphasis mb-1">Tipo</div>
              <span class="font-weight-medium">{{ selectedDocument.file_type?.toUpperCase() }}</span>
            </v-col>
            <v-col cols="6" sm="4">
              <div class="text-caption text-medium-emphasis mb-1">Chunks</div>
              <span class="font-weight-medium">{{ selectedDocument.chunk_count }}</span>
            </v-col>
            <v-col cols="6" sm="4">
              <div class="text-caption text-medium-emphasis mb-1">Modelo de Embedding</div>
              <span class="font-weight-medium">{{ selectedDocument.embedding_model }}</span>
            </v-col>
            <v-col cols="6" sm="4">
              <div class="text-caption text-medium-emphasis mb-1">Criado em</div>
              <span class="font-weight-medium">{{ formatDate(selectedDocument.created_at) }}</span>
            </v-col>
            <v-col cols="6" sm="4" v-if="selectedDocument.processed_at">
              <div class="text-caption text-medium-emphasis mb-1">Processado em</div>
              <span class="font-weight-medium">{{ formatDate(selectedDocument.processed_at) }}</span>
            </v-col>
          </v-row>

          <v-alert v-if="selectedDocument.error_message" type="error" variant="tonal" class="mt-4" density="compact">
            {{ selectedDocument.error_message }}
          </v-alert>

          <div v-if="selectedDocument.description" class="mt-4">
            <div class="text-caption text-medium-emphasis mb-1">Descrição</div>
            <p class="text-body-2">{{ selectedDocument.description }}</p>
          </div>
        </v-card-text>
        
        <v-card-actions class="pa-4">
          <v-btn variant="outlined" color="error" @click="confirmDelete(selectedDocument); detailsDialog = false" prepend-icon="mdi-delete">Excluir</v-btn>
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="detailsDialog = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-error">
          <v-icon class="mr-2" color="white">mdi-alert-circle</v-icon>
          <span class="text-white">Confirmar Exclusão</span>
        </v-card-title>
        <v-card-text class="pa-6 text-center">
          <v-icon size="64" color="error" class="mb-4">mdi-delete-alert</v-icon>
          <p class="text-h6">Excluir documento?</p>
          <p class="text-body-2 text-medium-emphasis">
            <strong>{{ docToDelete?.name }}</strong><br>
            Esta ação não pode ser desfeita.
          </p>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="deleteDialog = false">Cancelar</v-btn>
          <v-btn color="error" @click="deleteDocument" :loading="deleting">
            <v-icon start>mdi-delete</v-icon>
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.message }}
      <template v-slot:actions>
        <v-btn variant="text" @click="snackbar.show = false"><v-icon>mdi-close</v-icon></v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import axios from '@/plugins/axios'

// State
const documents = ref([])
const loading = ref(false)
const searchQuery = ref('')
const statusFilter = ref(null)
const showUploadModal = ref(false)
const selectedDocument = ref(null)
const detailsDialog = ref(false)
const selectedFile = ref(null)
const isDragOver = ref(false)
const uploading = ref(false)

// Delete
const deleteDialog = ref(false)
const docToDelete = ref(null)
const deleting = ref(false)

const uploadForm = ref({
  name: '',
  description: '',
  chunk_size: 1000,
  chunk_overlap: 200,
  is_global: false
})

// Snackbar
const snackbar = reactive({ show: false, message: '', color: 'success' })
function showSnackbar(msg, color = 'success') {
  snackbar.message = msg
  snackbar.color = color
  snackbar.show = true
}

// Computed
const filteredDocuments = computed(() => {
  let filtered = documents.value
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(d => d.name?.toLowerCase().includes(query))
  }
  if (statusFilter.value) {
    filtered = filtered.filter(d => d.status === statusFilter.value)
  }
  return filtered
})

const readyCount = computed(() => documents.value.filter(d => d.status === 'ready').length)
const globalCount = computed(() => documents.value.filter(d => d.is_global).length)
const totalChunks = computed(() => documents.value.reduce((sum, d) => sum + (d.chunk_count || 0), 0))

// API
const fetchDocuments = async () => {
  loading.value = true
  try {
    const response = await axios.get('/documents')
    documents.value = response.data.documents || []
  } catch (error) {
    console.error('Failed to fetch documents:', error)
  } finally {
    loading.value = false
  }
}

const handleFileSelect = (event) => {
  selectedFile.value = event.target.files[0]
}

const handleDrop = (event) => {
  isDragOver.value = false
  const files = event.dataTransfer.files
  if (files.length > 0) selectedFile.value = files[0]
}

const uploadDocument = async () => {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('name', uploadForm.value.name || '')
    formData.append('description', uploadForm.value.description || '')
    formData.append('chunk_size', uploadForm.value.chunk_size)
    formData.append('chunk_overlap', uploadForm.value.chunk_overlap)
    formData.append('is_global', uploadForm.value.is_global)
    
    await axios.post('/documents/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    showUploadModal.value = false
    selectedFile.value = null
    uploadForm.value = { name: '', description: '', chunk_size: 1000, chunk_overlap: 200, is_global: false }
    showSnackbar('Documento enviado com sucesso!')
    await fetchDocuments()
  } catch (error) {
    console.error('Upload failed:', error)
    showSnackbar('Erro ao enviar documento', 'error')
  } finally {
    uploading.value = false
  }
}

const viewDocument = async (doc) => {
  try {
    const response = await axios.get(`/documents/${doc.id}`)
    selectedDocument.value = response.data
    detailsDialog.value = true
  } catch (error) {
    console.error('Failed to fetch document:', error)
  }
}

const reprocessDocument = async (doc) => {
  try {
    await axios.post(`/documents/${doc.id}/reprocess`)
    showSnackbar('Reprocessamento iniciado!')
    await fetchDocuments()
  } catch (error) {
    console.error('Failed to reprocess:', error)
    showSnackbar('Erro ao reprocessar', 'error')
  }
}

const confirmDelete = (doc) => {
  docToDelete.value = doc
  deleteDialog.value = true
}

const deleteDocument = async () => {
  deleting.value = true
  try {
    await axios.delete(`/documents/${docToDelete.value.id}`)
    showSnackbar('Documento excluído!')
    deleteDialog.value = false
    await fetchDocuments()
  } catch (error) {
    console.error('Failed to delete:', error)
    showSnackbar('Erro ao excluir', 'error')
  } finally {
    deleting.value = false
  }
}

// Helpers
const getFileIcon = (type) => {
  const icons = { pdf: 'mdi-file-pdf-box', txt: 'mdi-file-document', md: 'mdi-language-markdown', markdown: 'mdi-language-markdown', docx: 'mdi-file-word', html: 'mdi-language-html5', json: 'mdi-code-json', csv: 'mdi-file-delimited' }
  return icons[type] || 'mdi-file-document'
}

const getFileColor = (type) => {
  const colors = { pdf: '#EF4444', txt: '#6366F1', md: '#3B82F6', markdown: '#3B82F6', docx: '#2563EB', html: '#F97316', json: '#10B981', csv: '#8B5CF6' }
  return colors[type] || '#64748B'
}

const getStatusColor = (status) => {
  const map = { pending: 'warning', processing: 'info', ready: 'success', error: 'error', reprocessing: 'info' }
  return map[status] || 'grey'
}

const getStatusIcon = (status) => {
  const map = { pending: 'mdi-clock-outline', processing: 'mdi-progress-clock', ready: 'mdi-check-circle', error: 'mdi-alert-circle', reprocessing: 'mdi-refresh' }
  return map[status] || 'mdi-help-circle'
}

const getStatusLabel = (status) => {
  const labels = { pending: 'Pendente', processing: 'Processando', ready: 'Pronto', error: 'Erro', reprocessing: 'Reprocessando' }
  return labels[status] || status
}

const getFileExtension = (filename) => filename.split('.').pop().toLowerCase()

const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const formatDate = (dateStr) => new Date(dateStr).toLocaleString('pt-BR')

// Lifecycle
let pollInterval
onMounted(() => {
  fetchDocuments()
  pollInterval = setInterval(fetchDocuments, 15000)
})
onBeforeUnmount(() => {
  clearInterval(pollInterval)
})
</script>

<style scoped>
.doc-card {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.doc-card:hover {
  transform: translateY(-3px);
  border-color: rgba(157, 78, 221, 0.2) !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25) !important;
}

.global-border {
  border-color: rgba(245, 158, 11, 0.3) !important;
}

.upload-zone {
  border: 2px dashed rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 32px;
  text-align: center;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.02);
}

.upload-zone.drag-active {
  border-color: rgba(157, 78, 221, 0.5);
  background: rgba(157, 78, 221, 0.08);
}

.upload-zone:hover {
  border-color: rgba(157, 78, 221, 0.3);
  background: rgba(255, 255, 255, 0.03);
}
</style>
