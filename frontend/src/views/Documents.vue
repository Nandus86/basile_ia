<template>
  <div class="documents-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <h1>📚 Base de Conhecimento</h1>
          <p class="subtitle">Gerencie documentos para RAG (Retrieval-Augmented Generation)</p>
        </div>
        <div class="actions">
          <button class="btn btn-primary" @click="showUploadModal = true">
            <span class="icon">📤</span>
            Upload de Documento
          </button>
        </div>
      </div>
      
      <!-- Stats -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-value">{{ documents.length }}</span>
          <span class="stat-label">Documentos</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ readyCount }}</span>
          <span class="stat-label">Prontos</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ totalChunks }}</span>
          <span class="stat-label">Chunks</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ globalCount }}</span>
          <span class="stat-label">Globais</span>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="filters-section">
      <div class="search-box">
        <input 
          v-model="searchQuery" 
          type="text" 
          placeholder="Buscar documentos..."
          class="search-input"
        />
      </div>
      <div class="filter-pills">
        <button 
          :class="['filter-pill', { active: statusFilter === null }]"
          @click="statusFilter = null"
        >
          Todos
        </button>
        <button 
          :class="['filter-pill', { active: statusFilter === 'ready' }]"
          @click="statusFilter = 'ready'"
        >
          ✅ Prontos
        </button>
        <button 
          :class="['filter-pill', { active: statusFilter === 'processing' }]"
          @click="statusFilter = 'processing'"
        >
          ⏳ Processando
        </button>
        <button 
          :class="['filter-pill', { active: statusFilter === 'error' }]"
          @click="statusFilter = 'error'"
        >
          ❌ Erro
        </button>
      </div>
    </div>

    <!-- Documents Grid -->
    <div class="documents-grid" v-if="filteredDocuments.length > 0">
      <div 
        v-for="doc in filteredDocuments" 
        :key="doc.id" 
        class="document-card"
        :class="{ 'is-global': doc.is_global }"
      >
        <div class="card-header">
          <div class="doc-icon">{{ getFileIcon(doc.file_type) }}</div>
          <div class="doc-status" :class="doc.status">
            {{ getStatusLabel(doc.status) }}
          </div>
        </div>
        
        <div class="card-body">
          <h3 class="doc-name">{{ doc.name }}</h3>
          <div class="doc-meta">
            <span class="meta-item">
              <span class="meta-icon">📄</span>
              {{ doc.file_type.toUpperCase() }}
            </span>
            <span class="meta-item">
              <span class="meta-icon">🧩</span>
              {{ doc.chunk_count }} chunks
            </span>
            <span class="meta-item" v-if="doc.is_global">
              <span class="meta-icon">🌍</span>
              Global
            </span>
          </div>
        </div>
        
        <div class="card-footer">
          <button class="btn-icon" @click="viewDocument(doc)" title="Ver detalhes">
            👁️
          </button>
          <button 
            class="btn-icon" 
            @click="reprocessDocument(doc)" 
            title="Reprocessar"
            :disabled="doc.status === 'processing'"
          >
            🔄
          </button>
          <button class="btn-icon danger" @click="confirmDelete(doc)" title="Excluir">
            🗑️
          </button>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div class="empty-state" v-else>
      <div class="empty-icon">📭</div>
      <h3>Nenhum documento encontrado</h3>
      <p>Faça upload do primeiro documento para começar</p>
      <button class="btn btn-primary" @click="showUploadModal = true">
        Upload de Documento
      </button>
    </div>

    <!-- Upload Modal -->
    <div class="modal-overlay" v-if="showUploadModal" @click.self="showUploadModal = false">
      <div class="modal">
        <div class="modal-header">
          <h2>📤 Upload de Documento</h2>
          <button class="btn-close" @click="showUploadModal = false">✕</button>
        </div>
        
        <div class="modal-body">
          <div 
            class="upload-zone"
            :class="{ 'drag-over': isDragOver }"
            @drop.prevent="handleDrop"
            @dragover.prevent="isDragOver = true"
            @dragleave="isDragOver = false"
          >
            <div v-if="!selectedFile">
              <div class="upload-icon">📁</div>
              <p>Arraste um arquivo aqui ou</p>
              <label class="file-input-label">
                <input type="file" @change="handleFileSelect" accept=".pdf,.txt,.md,.docx,.html,.json,.csv" />
                Selecione um arquivo
              </label>
              <p class="file-types">Tipos aceitos: PDF, TXT, MD, DOCX, HTML, JSON, CSV</p>
            </div>
            <div v-else class="file-selected">
              <div class="file-info">
                <span class="file-icon">{{ getFileIcon(getFileExtension(selectedFile.name)) }}</span>
                <span class="file-name">{{ selectedFile.name }}</span>
                <span class="file-size">({{ formatFileSize(selectedFile.size) }})</span>
              </div>
              <button class="btn-icon" @click="selectedFile = null">✕</button>
            </div>
          </div>

          <div class="form-group">
            <label>Nome do Documento</label>
            <input v-model="uploadForm.name" type="text" placeholder="Nome personalizado (opcional)" />
          </div>

          <div class="form-group">
            <label>Descrição</label>
            <textarea v-model="uploadForm.description" placeholder="Descrição do documento..."></textarea>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Tamanho do Chunk</label>
              <input v-model.number="uploadForm.chunk_size" type="number" min="100" max="4000" />
            </div>
            <div class="form-group">
              <label>Overlap</label>
              <input v-model.number="uploadForm.chunk_overlap" type="number" min="0" max="1000" />
            </div>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input type="checkbox" v-model="uploadForm.is_global" />
              <span>Documento Global</span>
              <small>Disponível para todos os agentes</small>
            </label>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showUploadModal = false">Cancelar</button>
          <button 
            class="btn btn-primary" 
            @click="uploadDocument" 
            :disabled="!selectedFile || uploading"
          >
            {{ uploading ? 'Enviando...' : 'Enviar' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Document Details Modal -->
    <div class="modal-overlay" v-if="selectedDocument" @click.self="selectedDocument = null">
      <div class="modal modal-large">
        <div class="modal-header">
          <h2>{{ getFileIcon(selectedDocument.file_type) }} {{ selectedDocument.name }}</h2>
          <button class="btn-close" @click="selectedDocument = null">✕</button>
        </div>
        
        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item">
              <label>Status</label>
              <span :class="['status-badge', selectedDocument.status]">
                {{ getStatusLabel(selectedDocument.status) }}
              </span>
            </div>
            <div class="detail-item">
              <label>Tipo</label>
              <span>{{ selectedDocument.file_type.toUpperCase() }}</span>
            </div>
            <div class="detail-item">
              <label>Chunks</label>
              <span>{{ selectedDocument.chunk_count }}</span>
            </div>
            <div class="detail-item">
              <label>Modelo de Embedding</label>
              <span>{{ selectedDocument.embedding_model }}</span>
            </div>
            <div class="detail-item">
              <label>Criado em</label>
              <span>{{ formatDate(selectedDocument.created_at) }}</span>
            </div>
            <div class="detail-item" v-if="selectedDocument.processed_at">
              <label>Processado em</label>
              <span>{{ formatDate(selectedDocument.processed_at) }}</span>
            </div>
          </div>

          <div v-if="selectedDocument.error_message" class="error-box">
            <strong>Erro:</strong> {{ selectedDocument.error_message }}
          </div>

          <div v-if="selectedDocument.description" class="description-box">
            <label>Descrição</label>
            <p>{{ selectedDocument.description }}</p>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-danger" @click="confirmDelete(selectedDocument); selectedDocument = null">
            🗑️ Excluir
          </button>
          <button class="btn btn-secondary" @click="selectedDocument = null">
            Fechar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_URL = '/api'

// State
const documents = ref([])
const loading = ref(false)
const searchQuery = ref('')
const statusFilter = ref(null)
const showUploadModal = ref(false)
const selectedDocument = ref(null)
const selectedFile = ref(null)
const isDragOver = ref(false)
const uploading = ref(false)

const uploadForm = ref({
  name: '',
  description: '',
  chunk_size: 1000,
  chunk_overlap: 200,
  is_global: false
})

// Computed
const filteredDocuments = computed(() => {
  let filtered = documents.value
  
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(d => d.name.toLowerCase().includes(query))
  }
  
  if (statusFilter.value) {
    filtered = filtered.filter(d => d.status === statusFilter.value)
  }
  
  return filtered
})

const readyCount = computed(() => documents.value.filter(d => d.status === 'ready').length)
const globalCount = computed(() => documents.value.filter(d => d.is_global).length)
const totalChunks = computed(() => documents.value.reduce((sum, d) => sum + d.chunk_count, 0))

// Methods
const fetchDocuments = async () => {
  loading.value = true
  try {
    const response = await fetch(`${API_URL}/documents`)
    const data = await response.json()
    documents.value = data.documents || []
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
  if (files.length > 0) {
    selectedFile.value = files[0]
  }
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
    
    const response = await fetch(`${API_URL}/documents/upload`, {
      method: 'POST',
      body: formData
    })
    
    if (response.ok) {
      showUploadModal.value = false
      selectedFile.value = null
      uploadForm.value = { name: '', description: '', chunk_size: 1000, chunk_overlap: 200, is_global: false }
      await fetchDocuments()
    }
  } catch (error) {
    console.error('Upload failed:', error)
  } finally {
    uploading.value = false
  }
}

const viewDocument = async (doc) => {
  try {
    const response = await fetch(`${API_URL}/documents/${doc.id}`)
    selectedDocument.value = await response.json()
  } catch (error) {
    console.error('Failed to fetch document:', error)
  }
}

const reprocessDocument = async (doc) => {
  try {
    await fetch(`${API_URL}/documents/${doc.id}/reprocess`, { method: 'POST' })
    await fetchDocuments()
  } catch (error) {
    console.error('Failed to reprocess:', error)
  }
}

const confirmDelete = async (doc) => {
  if (confirm(`Excluir documento "${doc.name}"?`)) {
    try {
      await fetch(`${API_URL}/documents/${doc.id}`, { method: 'DELETE' })
      await fetchDocuments()
    } catch (error) {
      console.error('Failed to delete:', error)
    }
  }
}

const getFileIcon = (type) => {
  const icons = {
    pdf: '📕',
    txt: '📄',
    md: '📝',
    markdown: '📝',
    docx: '📘',
    html: '🌐',
    json: '🔧',
    csv: '📊'
  }
  return icons[type] || '📄'
}

const getStatusLabel = (status) => {
  const labels = {
    pending: '⏳ Pendente',
    processing: '🔄 Processando',
    ready: '✅ Pronto',
    error: '❌ Erro',
    reprocessing: '🔄 Reprocessando'
  }
  return labels[status] || status
}

const getFileExtension = (filename) => {
  return filename.split('.').pop().toLowerCase()
}

const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleString('pt-BR')
}

// Lifecycle
onMounted(() => {
  fetchDocuments()
  // Poll for updates
  setInterval(fetchDocuments, 10000)
})
</script>

<style scoped>
.documents-page {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

/* Header */
.page-header {
  margin-bottom: 2rem;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.title-section h1 {
  font-size: 2rem;
  color: var(--text-primary);
  margin: 0;
}

.subtitle {
  color: var(--text-secondary);
  margin-top: 0.5rem;
}

/* Stats */
.stats-bar {
  display: flex;
  gap: 2rem;
  background: var(--bg-secondary);
  padding: 1rem 1.5rem;
  border-radius: 12px;
  border: 1px solid var(--border-color);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

/* Filters */
.filters-section {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.search-box {
  flex: 1;
  min-width: 200px;
}

.search-input {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.filter-pills {
  display: flex;
  gap: 0.5rem;
}

.filter-pill {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 20px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.filter-pill.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

/* Documents Grid */
.documents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}

.document-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s;
}

.document-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
}

.document-card.is-global {
  border-color: #ffd700;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--bg-tertiary);
}

.doc-icon {
  font-size: 2rem;
}

.doc-status {
  font-size: 0.75rem;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-weight: 500;
}

.doc-status.ready { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
.doc-status.pending { background: rgba(234, 179, 8, 0.2); color: #eab308; }
.doc-status.processing { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
.doc-status.error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
.doc-status.reprocessing { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }

.card-body {
  padding: 1rem;
}

.doc-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.75rem 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border-color);
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.25rem;
  padding: 0.5rem;
  border-radius: 8px;
  transition: background 0.2s;
}

.btn-icon:hover {
  background: var(--bg-tertiary);
}

.btn-icon.danger:hover {
  background: rgba(239, 68, 68, 0.2);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal {
  background: var(--bg-primary);
  border-radius: 16px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-large {
  max-width: 700px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h2 {
  margin: 0;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--text-secondary);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-color);
}

/* Upload Zone */
.upload-zone {
  border: 2px dashed var(--border-color);
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  margin-bottom: 1.5rem;
  transition: all 0.2s;
}

.upload-zone.drag-over {
  border-color: var(--primary);
  background: rgba(99, 102, 241, 0.1);
}

.upload-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.file-input-label {
  display: inline-block;
  padding: 0.5rem 1rem;
  background: var(--primary);
  color: white;
  border-radius: 8px;
  cursor: pointer;
  margin: 0.5rem 0;
}

.file-input-label input {
  display: none;
}

.file-types {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: 0.5rem;
}

.file-selected {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.file-icon {
  font-size: 1.5rem;
}

.file-name {
  font-weight: 500;
  color: var(--text-primary);
}

.file-size {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

/* Form */
.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.form-group textarea {
  min-height: 80px;
  resize: vertical;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.checkbox-group small {
  color: var(--text-tertiary);
  font-size: 0.75rem;
}

/* Buttons */
.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Detail Grid */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.detail-item {
  background: var(--bg-secondary);
  padding: 1rem;
  border-radius: 8px;
}

.detail-item label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

.status-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.875rem;
}

.status-badge.ready { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
.status-badge.pending { background: rgba(234, 179, 8, 0.2); color: #eab308; }
.status-badge.processing { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
.status-badge.error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

.error-box {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 1rem;
  border-radius: 8px;
  color: #ef4444;
  margin-bottom: 1rem;
}

.description-box {
  background: var(--bg-secondary);
  padding: 1rem;
  border-radius: 8px;
}

.description-box label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.description-box p {
  margin: 0;
  color: var(--text-primary);
}
</style>
