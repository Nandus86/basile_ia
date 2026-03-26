<template>
  <div class="skills-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-star-shooting-outline</v-icon>
        </div>
        <div class="header-text">
          <h1>Criador de Skills</h1>
          <p>Crie e gerencie habilidades especializadas para os seus agentes</p>
        </div>
      </div>
      <v-btn color="secondary" size="large" prepend-icon="mdi-folder-plus" @click="openGroupDialog()" elevation="3" class="mr-3">
        Nova Pasta
      </v-btn>
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="openDialog()" elevation="3">
        Nova Skill
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
              <p class="text-h4 font-weight-bold mb-0">{{ skills.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Total de Skills</p>
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
              <p class="text-caption text-medium-emphasis mb-0">Skills Ativas</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Folder Cards (shown at root level) -->
    <v-row v-if="!currentFolder && skillGroups.length > 0" class="mb-6">
      <v-col cols="12">
        <div class="d-flex align-center justify-space-between mb-2">
          <h2 class="text-h6">Pastas de Skills</h2>
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-folder-plus" @click="openGroupDialog()">
            Nova Pasta
          </v-btn>
        </div>
      </v-col>
      <v-col cols="12" sm="6" md="4" lg="3" v-for="group in skillGroups" :key="group.id">
        <v-card class="glass-card h-100 d-flex flex-column" hover>
          <div class="d-flex justify-end pa-2 pb-0">
            <v-menu position="bottom end">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-dots-vertical" variant="text" size="small" v-bind="props"></v-btn>
              </template>
              <v-list density="compact">
                <v-list-item @click="openGroupDialog(group)">
                  <template v-slot:prepend><v-icon size="small">mdi-pencil</v-icon></template>
                  <v-list-item-title>Editar</v-list-item-title>
                </v-list-item>
                <v-list-item @click="deleteGroup(group.id)" class="text-error">
                  <template v-slot:prepend><v-icon color="error" size="small">mdi-delete</v-icon></template>
                  <v-list-item-title>Excluir</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </div>
          <v-card-text class="flex-grow-1 d-flex flex-column align-center justify-center pt-0 pb-6 px-6 text-center cursor-pointer" @click="openFolder(group)">
            <v-icon size="64" color="secondary" class="mb-4">mdi-folder</v-icon>
            <h3 class="text-h6 mb-2">{{ group.name }}</h3>
            <p class="text-body-2 text-medium-emphasis mb-3" style="min-height: 20px">
              {{ group.description || '' }}
            </p>
            <v-chip size="small" color="primary" variant="tonal">
              {{ group.skill_count }} skills
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Skills Table -->
    <v-card class="skills-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-btn v-if="currentFolder" icon="mdi-arrow-left" variant="text" size="small" class="mr-2" @click="backToFolders()"></v-btn>
        <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
        <span class="text-white">{{ currentFolder ? `Skills em: ${currentFolder.name}` : 'Skills sem pasta' }}</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          density="compact"
          placeholder="Buscar Skill..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          hide-details
          style="max-width: 300px"
        ></v-text-field>
        <v-btn v-if="!currentFolder" size="small" variant="tonal" color="secondary" icon="mdi-folder-plus" class="ml-2" @click="openGroupDialog()"></v-btn>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="filteredSkills"
        :loading="loading"
        :items-per-page="10"
        class="skills-table"
      >
        <template v-slot:item.name="{ item }">
          <div class="d-flex align-center py-2">
            <v-avatar color="info" size="36" class="mr-3">
              <v-icon color="white" size="18">mdi-star-circle</v-icon>
            </v-avatar>
            <div>
              <span class="font-weight-medium">{{ item.name }}</span>
              <p class="text-caption text-medium-emphasis mb-0" v-if="item.intent">
                {{ item.intent?.substring(0, 50) }}{{ item.intent?.length > 50 ? '...' : '' }}
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
            <v-btn icon variant="text" size="small" color="secondary" @click="duplicateSkill(item)" :loading="duplicatingSkill === item.id">
              <v-icon size="20">mdi-content-copy</v-icon>
              <v-tooltip activator="parent" location="top">Duplicar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="primary" @click="openDialog(item)">
              <v-icon size="20">mdi-pencil</v-icon>
              <v-tooltip activator="parent" location="top">Editar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="error" @click="confirmDelete(item)">
              <v-icon size="20">mdi-delete</v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
          </div>
        </template>
        
        <template v-slot:no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-star-off-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhuma Skill encontrada</p>
            <p class="text-body-2 text-medium-emphasis mb-4">Crie sua primeira skill para começar</p>
            <v-btn color="primary" @click="openDialog()">
              <v-icon start>mdi-plus</v-icon>
              Criar Skill
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog" max-width="900" persistent>
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-primary">
          <v-icon class="mr-2" color="white">{{ editing ? 'mdi-pencil' : 'mdi-plus-circle' }}</v-icon>
          <span class="text-white">{{ editing ? 'Editar Skill' : 'Criar Nova Skill' }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="dialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <!-- Tabs for Editor vs Generator -->
        <v-tabs v-model="activeTab" bg-color="surface" color="primary">
          <v-tab value="generator"><v-icon start>mdi-auto-fix</v-icon>Gerador de IA</v-tab>
          <v-tab value="editor"><v-icon start>mdi-language-markdown-outline</v-icon>Código Markdown</v-tab>
        </v-tabs>

        <v-card-text class="pa-6" style="min-height: 450px;">
          <v-window v-model="activeTab">
            <!-- Gerador -->
            <v-window-item value="generator">
              <v-form ref="formGeneratorRef" v-model="formValid">
                <p class="text-subtitle-2 text-medium-emphasis mb-3">
                  <v-icon size="18" class="mr-1">mdi-head-idea-outline</v-icon>
                  Descreva o que seu agente deve aprender a fazer
                </p>
                <v-row>
                  <v-col cols="12" md="8">
                    <v-text-field
                      v-model="formData.name"
                      label="Nome da Skill"
                      placeholder="Ex: Analista de Sentimentos em Texto"
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

                <v-select
                  v-model="formData.group_id"
                  :items="skillGroups"
                  item-title="name"
                  item-value="id"
                  label="Pasta / Grupo"
                  prepend-inner-icon="mdi-folder"
                  clearable
                  variant="outlined"
                  class="mb-4"
                ></v-select>
                
                <v-textarea
                  v-model="formData.intent"
                  label="Intenção da Skill (Prompt)"
                  placeholder="Explique detalhadamente o que o agente deve saber fazer. Ex: Como extrair o humor de um texto usando emojis e classificações como positivo/negativo..."
                  rows="4"
                  prepend-inner-icon="mdi-comment-text-outline"
                  hint="Seja o mais específico possível. A IA irá converter isso em um arquivo Markdown SKILL.md estruturado."
                  persistent-hint
                ></v-textarea>

                <div class="mt-6 text-center">
                  <v-btn 
                    color="primary" 
                    variant="tonal" 
                    prepend-icon="mdi-creation" 
                    @click="generateMarkdown" 
                    :loading="generating" 
                    :disabled="!formData.name || !formData.intent"
                  >
                    Gerar Skill via IA
                  </v-btn>
                </div>

                <v-alert v-if="generateSuccess" type="success" variant="tonal" class="mt-4" density="compact" closable>
                  Skill gerada com sucesso! Acesse a aba <strong>Código Markdown</strong> para revisar, ou salve agora.
                </v-alert>
                <v-alert v-if="generateError" type="error" variant="tonal" class="mt-4" density="compact" closable>
                  {{ generateError }}
                </v-alert>

              </v-form>
            </v-window-item>

            <!-- Editor -->
            <v-window-item value="editor">
              <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                Revise ou edite manualmente o código da Skill. O formato deve seguir o padrão SKILL.md usando cabeçalhos frontmatter.
              </v-alert>
              
              <v-row>
                <v-col cols="12" md="8" v-if="!formData.name">
                  <!-- Se o usuário pular o gerador e for direto pro editor sem nome -->
                  <v-text-field
                      v-model="formData.name"
                      label="Nome da Skill"
                      :rules="[v => !!v || 'Insira um nome']"
                  ></v-text-field>
                </v-col>
              </v-row>

              <p class="text-subtitle-2 text-medium-emphasis mb-2">
                <v-icon size="18" class="mr-1">mdi-code-json</v-icon>
                Conteúdo Markdown (SKILL.md)
              </p>
              <v-textarea
                v-model="formData.content_md"
                placeholder="---
name: Minha Skill
description: Descrição...
---
# Instruções..."
                rows="12"
                variant="outlined"
                density="compact"
                style="font-family: monospace; font-size: 13px;"
                :rules="[v => !!v || 'O conteúdo não pode estar vazio']"
              ></v-textarea>
            </v-window-item>
          </v-window>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="dialog = false" :disabled="saving || generating">
            Cancelar
          </v-btn>
          <v-btn color="primary" @click="saveSkill" :loading="saving" :disabled="saving || generating || !formData.name || !formData.content_md">
            <v-icon start>mdi-content-save</v-icon>
            {{ editing ? 'Atualizar' : 'Salvar Skill' }}
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
          <p class="text-h6">Deseja excluir esta Skill?</p>
          <p class="text-body-2 text-medium-emphasis">
            <strong>{{ itemToDelete?.name }}</strong><br>
            Os agentes perderão esta habilidade de imediato. Esta ação não pode ser desfeita.
          </p>
        </v-card-text>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="deleteDialog = false">Cancelar</v-btn>
          <v-btn color="error" @click="deleteSkill" :loading="deleting">
            <v-icon start>mdi-delete</v-icon>
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Group Dialog -->
    <v-dialog v-model="groupDialog" max-width="500">
      <v-card>
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" color="secondary">mdi-folder</v-icon>
          <span>{{ groupForm.id ? 'Editar Pasta' : 'Nova Pasta' }}</span>
        </v-card-title>
        <v-card-text class="pa-5">
          <v-text-field v-model="groupForm.name" label="Nome da Pasta" variant="outlined" class="mb-4" required></v-text-field>
          <v-textarea v-model="groupForm.description" label="Descrição" variant="outlined" rows="2" hide-details></v-textarea>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="groupDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveGroup" :loading="savingGroup" :disabled="!groupForm.name.trim()">Salvar</v-btn>
        </v-card-actions>
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
import { skillGroupService } from '@/services/skillGroupService'

// State
const skills = ref([])
const loading = ref(false)
const search = ref('')
const skillGroups = ref([])
const currentFolder = ref(null)
const groupDialog = ref(false)
const groupForm = ref({ id: null, name: '', description: '' })
const savingGroup = ref(false)

// Dialog
const dialog = ref(false)
const editing = ref(false)
const saving = ref(false)
const formValid = ref(false)
const activeTab = ref('generator')
const generating = ref(false)
const generateSuccess = ref(false)
const generateError = ref('')

const formData = reactive({
  id: null,
  name: '',
  intent: '',
  content_md: '',
  is_active: true,
  group_id: null
})

// Delete Dialog
const deleteDialog = ref(false)
const deleting = ref(false)
const itemToDelete = ref(null)

// Snackbar
const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

const headers = [
  { title: 'Skill', key: 'name', sortable: true },
  { title: 'Status', key: 'is_active', sortable: true, width: '100px' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '160px' }
]

// Duplicate skill state
const duplicatingSkill = ref(null)

// Computed
const filteredSkills = computed(() => {
  if (!search.value) return skills.value
  const s = search.value.toLowerCase()
  return skills.value.filter(item => 
    item.name?.toLowerCase().includes(s) || 
    item.intent?.toLowerCase().includes(s)
  )
})

const activeCount = computed(() => skills.value.filter(s => s.is_active).length)

function showSnackbar(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function resetForm() {
  Object.assign(formData, {
    id: null,
    name: '',
    intent: '',
    content_md: '',
    is_active: true,
    group_id: currentFolder.value?.id || null
  })
  activeTab.value = 'generator'
  generateSuccess.value = false
  generateError.value = ''
}

// API Methods
async function fetchSkills() {
  loading.value = true
  try {
    const params = { search: search.value || undefined, group_id: currentFolder.value?.id || undefined }
    const response = await axios.get('/skills/', { params })
    skills.value = response.data.skills || []
  } catch (error) {
    console.error('Error fetching skills:', error)
    showSnackbar('Erro ao carregar renderizações de skills.', 'error')
  } finally {
    loading.value = false
  }
}

function openDialog(skill = null) {
  resetForm()
  if (skill) {
    editing.value = true
    Object.assign(formData, {
      id: skill.id,
      name: skill.name,
      intent: skill.intent || '',
      content_md: skill.content_md || '',
      is_active: skill.is_active ?? true,
      group_id: skill.group_id || null
    })
    activeTab.value = 'editor' // Se for edição, assume que quer ver o MD pronto
  } else {
    editing.value = false
  }
  dialog.value = true
}

async function generateMarkdown() {
  generating.value = true
  generateSuccess.value = false
  generateError.value = ''
  
  try {
    const response = await axios.post('/skills/generate', {
      name: formData.name,
      intent: formData.intent
    })
    
    formData.content_md = response.data.content_md
    generateSuccess.value = true
    // optionally switch to editor
    // activeTab.value = 'editor'
  } catch (error) {
    console.error('Error generating skill:', error)
    generateError.value = error.response?.data?.detail || 'Ocorreu um erro ao gerar a Skill. Verifique se a API Key da OpenAI está configurada.'
  } finally {
    generating.value = false
  }
}

async function saveSkill() {
  saving.value = true
  try {
    const payload = {
      name: formData.name,
      intent: formData.intent,
      content_md: formData.content_md,
      is_active: formData.is_active,
      group_id: formData.group_id || null
    }
    
    if (editing.value) {
      await axios.put(`/skills/${formData.id}`, payload)
      showSnackbar('Skill atualizada com sucesso!')
    } else {
      await axios.post('/skills/', payload)
      showSnackbar('Skill criada com sucesso!')
    }
    dialog.value = false
    await fetchSkills()
  } catch (error) {
    console.error('Error saving skill:', error)
    showSnackbar('Erro ao salvar skill', 'error')
  } finally {
    saving.value = false
  }
}

async function duplicateSkill(skill) {
  duplicatingSkill.value = skill.id
  try {
    const payload = {
      name: skill.name + ' (Cópia)',
      intent: skill.intent || '',
      content_md: skill.content_md || '',
      is_active: false
    }
    await axios.post('/skills/', payload)
    showSnackbar('Skill duplicada com sucesso!')
    await fetchSkills()
  } catch (error) {
    console.error('Error duplicating skill:', error)
    showSnackbar('Erro ao duplicar skill', 'error')
  } finally {
    duplicatingSkill.value = null
  }
}

function confirmDelete(item) {
  itemToDelete.value = item
  deleteDialog.value = true
}

async function deleteSkill() {
  deleting.value = true
  try {
    await axios.delete(`/skills/${itemToDelete.value.id}`)
    showSnackbar('Skill excluída com sucesso!')
    deleteDialog.value = false
    await fetchSkills()
  } catch (error) {
    console.error('Error deleting skill:', error)
    showSnackbar('Erro ao excluir skill', 'error')
  } finally {
    deleting.value = false
  }
}

async function fetchGroups() {
  try {
    const { data } = await skillGroupService.list()
    skillGroups.value = data
  } catch (e) { console.error('Failed to fetch groups', e) }
}

function openGroupDialog(group = null) {
  if (group) {
    groupForm.value = { id: group.id, name: group.name, description: group.description || '' }
  } else {
    groupForm.value = { id: null, name: '', description: '' }
  }
  groupDialog.value = true
}

async function saveGroup() {
  savingGroup.value = true
  try {
    if (groupForm.value.id) {
      await skillGroupService.update(groupForm.value.id, { name: groupForm.value.name, description: groupForm.value.description })
    } else {
      await skillGroupService.create({ name: groupForm.value.name, description: groupForm.value.description })
    }
    groupDialog.value = false
    await fetchGroups()
  } catch (e) { console.error('Failed to save group', e) }
  finally { savingGroup.value = false }
}

async function deleteGroup(id) {
  if (!confirm('Excluir pasta? Skills dentro serão desagrupadas.')) return
  try {
    await skillGroupService.delete(id)
    await fetchGroups()
    if (currentFolder.value?.id === id) backToFolders()
  } catch (e) { console.error('Failed to delete group', e) }
}

function openFolder(group) {
  currentFolder.value = group
  fetchSkills()
}

function backToFolders() {
  currentFolder.value = null
  fetchSkills()
}

onMounted(() => {
  fetchSkills()
  fetchGroups()
})
</script>

<style scoped>
.skills-page {
  padding: 0;
  width: 100%;
}

.skills-card {
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 24px;
}

:deep(.v-data-table) {
  background: transparent !important;
}
</style>
