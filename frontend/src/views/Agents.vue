<template>
  <div class="agents-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-robot</v-icon>
        </div>
        <div class="header-text">
          <h1>Agentes IA</h1>
          <p>Gerencie seus agentes de inteligência artificial</p>
        </div>
      </div>
      <v-btn color="secondary" size="large" prepend-icon="mdi-folder-plus" @click="openGroupDialog()" elevation="3" class="mr-3">
        Nova Pasta
      </v-btn>
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="openDialog()" elevation="3">
        Novo Agente
      </v-btn>
    </div>

    <!-- Stats Cards -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-robot-outline</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ agents.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Total de Agentes</p>
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
              <p class="text-caption text-medium-emphasis mb-0">Ativos</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-star</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ premiumCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Pro/Premium</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-account-group</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ collabCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Com Colaboração</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Breadcrumb Navigation -->
    <div v-if="breadcrumb.length > 0" class="d-flex align-center mb-4 ga-1">
      <v-btn variant="text" size="small" @click="backToFolders()" class="text-capitalize">
        <v-icon start>mdi-home</v-icon> Raiz
      </v-btn>
      <template v-for="(crumb, idx) in breadcrumb" :key="crumb.id">
        <v-icon size="16">mdi-chevron-right</v-icon>
        <v-btn variant="text" size="small" @click="navigateToBreadcrumb(idx)" class="text-capitalize" :disabled="idx === breadcrumb.length - 1">
          {{ crumb.name }}
        </v-btn>
      </template>
    </div>

    <!-- Sub-folders -->
    <v-row v-if="agentGroups.length > 0" class="mb-6">
      <v-col cols="12">
        <div class="d-flex align-center justify-space-between mb-2">
          <h2 class="text-h6">{{ currentFolder ? 'Sub-pastas' : 'Pastas de Agentes' }}</h2>
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-folder-plus" @click="openGroupDialog()">
            {{ currentFolder ? 'Nova Sub-pasta' : 'Nova Pasta' }}
          </v-btn>
        </div>
      </v-col>
      <v-col cols="12" sm="6" md="4" lg="3" v-for="group in agentGroups" :key="group.id">
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
            <v-icon size="56" :color="group.children_count > 0 ? 'warning' : 'secondary'" class="mb-3">
              {{ group.children_count > 0 ? 'mdi-folder-multiple' : 'mdi-folder' }}
            </v-icon>
            <h3 class="text-subtitle-1 font-weight-bold mb-1">{{ group.name }}</h3>
            <p class="text-caption text-medium-emphasis mb-2" v-if="group.description">{{ group.description }}</p>
            <div class="d-flex ga-2">
              <v-chip size="x-small" color="primary" variant="tonal">{{ group.agent_count }} agentes</v-chip>
              <v-chip v-if="group.children_count > 0" size="x-small" color="warning" variant="tonal">{{ group.children_count }} sub-pastas</v-chip>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Agents Grid -->
    <v-card class="agents-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
        <span class="text-white">{{ currentFolder ? currentFolder.name : 'Agentes sem pasta' }}</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          density="compact"
          placeholder="Buscar agente..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          hide-details
          class="search-field"
          style="max-width: 300px"
        ></v-text-field>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="filteredAgents"
        :loading="loading"
        :items-per-page="10"
        class="agents-table"
      >
        <template v-slot:item.name="{ item }">
          <div class="d-flex align-center py-2">
            <v-avatar :color="getLevelColor(item.access_level)" size="36" class="mr-3">
              <v-icon color="white" size="20">mdi-robot</v-icon>
            </v-avatar>
            <div>
              <div class="d-flex align-center">
                <span class="font-weight-medium mr-2">{{ item.name }}</span>
                <v-chip
                  size="x-small"
                  variant="outlined"
                  color="grey-lighten-1"
                  style="cursor: pointer; opacity: 0.8;"
                  @click.stop="copyAgentId(item.id)"
                >
                  <v-icon start size="10">mdi-content-copy</v-icon>
                  {{ item.id?.split('-')[0] }}
                  <v-tooltip activator="parent" location="top">Copiar ID: {{ item.id }}</v-tooltip>
                </v-chip>
              </div>
              <p class="text-caption text-medium-emphasis mb-0" v-if="item.description">
                {{ item.description?.substring(0, 50) }}{{ item.description?.length > 50 ? '...' : '' }}
              </p>
            </div>
          </div>
        </template>
        
        <template v-slot:item.access_level="{ item }">
          <v-chip :color="getLevelColor(item.access_level)" size="small" label>
            <v-icon start size="14">{{ getLevelIcon(item.access_level) }}</v-icon>
            {{ getLevelLabel(item.access_level) }}
          </v-chip>
        </template>
        
        <template v-slot:item.model="{ item }">
          <v-chip variant="outlined" size="small" color="grey">
            {{ item.model }}
          </v-chip>
        </template>
        
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            <v-icon start size="14">{{ item.is_active ? 'mdi-check' : 'mdi-close' }}</v-icon>
            {{ item.is_active ? 'Ativo' : 'Inativo' }}
          </v-chip>
        </template>
        
        <template v-slot:item.collaboration_enabled="{ item }">
          <div class="d-flex align-center gap-2">
            <v-tooltip :text="item.collaboration_enabled ? 'Colaboração ativa' : 'Colaboração desativada'">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" :color="item.collaboration_enabled ? 'success' : 'grey-lighten-1'" size="20">
                  {{ item.collaboration_enabled ? 'mdi-account-multiple-check' : 'mdi-account-multiple-remove' }}
                </v-icon>
              </template>
            </v-tooltip>
            
            <v-tooltip :text="item.vector_memory_enabled ? 'Memória Vetorial ativa' : 'Memória Vetorial desativada'">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" :color="item.vector_memory_enabled ? 'deep-purple' : 'grey-lighten-1'" size="20">
                  {{ item.vector_memory_enabled ? 'mdi-brain' : 'mdi-brain' }}
                </v-icon>
              </template>
            </v-tooltip>
          </div>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn icon variant="text" size="small" color="info" @click="openCollaboratorsDialog(item)">
              <v-icon size="20">mdi-account-group</v-icon>
              <v-tooltip activator="parent" location="top">Colaboradores</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="secondary" @click="duplicateAgent(item)" :loading="duplicatingAgent === item.id">
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
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-robot-off-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhum agente encontrado</p>
            <p class="text-body-2 text-medium-emphasis mb-4">Crie seu primeiro agente para começar</p>
            <v-btn color="primary" @click="openDialog()">
              <v-icon start>mdi-plus</v-icon>
              Criar Agente
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create/Edit Dialog with Tabs -->
    <v-dialog v-model="dialog" max-width="900" persistent>
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-primary">
          <v-icon class="mr-2" color="white">{{ editing ? 'mdi-pencil' : 'mdi-plus-circle' }}</v-icon>
          <span class="text-white">{{ editing ? 'Editar Agente' : 'Novo Agente' }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="dialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-tabs v-model="activeTab" bg-color="surface" color="primary">
          <v-tab value="general"><v-icon start>mdi-information</v-icon>Geral</v-tab>
          <v-tab value="personality" :disabled="!editing"><v-icon start>mdi-heart</v-icon>Personalidade</v-tab>
          <v-tab value="skills" :disabled="!editing"><v-icon start>mdi-star-shooting-outline</v-icon>Skills</v-tab>
          <v-tab value="tools" :disabled="!editing"><v-icon start>mdi-tools</v-icon>Ferramentas</v-tab>
          <v-tab value="input" :disabled="!editing"><v-icon start>mdi-application-import</v-icon>Entrada</v-tab>
          <v-tab value="output" :disabled="!editing"><v-icon start>mdi-code-json</v-icon>Saída</v-tab>
          <v-tab value="resilience" :disabled="!editing"><v-icon start>mdi-shield-check</v-icon>Resiliência</v-tab>
          <v-tab value="knowledge" :disabled="!editing"><v-icon start>mdi-book-open-page-variant</v-icon>Conhecimento</v-tab>
          <v-tab value="information_bases" :disabled="!editing"><v-icon start>mdi-database-search</v-icon>Bases de Infor.</v-tab>
          <v-tab value="vfs_knowledge" :disabled="!editing"><v-icon start>mdi-file-document-multiple-outline</v-icon>VFS RAG 3.0</v-tab>
          <v-tab value="interactivity" :disabled="!editing"><v-icon start>mdi-message-flash</v-icon>Interatividade</v-tab>
          <v-tab value="planner" :disabled="!editing"><v-icon start>mdi-strategy</v-icon>Planejador</v-tab>
          <v-tab value="thinker" :disabled="!editing"><v-icon start>mdi-head-brain</v-icon>Thinker</v-tab>
          <v-tab value="guardrail" :disabled="!editing"><v-icon start>mdi-shield-alert</v-icon>Guardrail</v-tab>
          <v-tab value="prompt_preview" :disabled="!editing"><v-icon start>mdi-eye</v-icon>Prompt Geral</v-tab>
        </v-tabs>

        <v-card-text class="pa-6" style="min-height: 400px">
          <v-window v-model="activeTab">
            
            <!-- Tab: General -->
            <v-window-item value="general">
              <v-form ref="formRef" v-model="formValid">
                <v-row>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="formData.name"
                      label="Nome do Agente"
                      placeholder="Ex: Assistente de Vendas"
                      :rules="[v => !!v || 'Nome é obrigatório']"
                      prepend-inner-icon="mdi-robot"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="formData.access_level"
                      label="Nível de Acesso"
                      :items="accessLevels"
                      item-title="label"
                      item-value="value"
                      prepend-inner-icon="mdi-shield-lock"
                    ></v-select>
                  </v-col>
                </v-row>
                
                <v-textarea
                  v-model="formData.description"
                  label="Descrição"
                  placeholder="Descreva brevemente a função deste agente..."
                  rows="2"
                  prepend-inner-icon="mdi-text"
                ></v-textarea>
                
                <v-textarea
                  v-model="formData.system_prompt"
                  label="System Prompt"
                  placeholder="Instruções de comportamento do agente..."
                  rows="5"
                  :rules="[v => !!v || 'System prompt é obrigatório']"
                  prepend-inner-icon="mdi-script-text"
                ></v-textarea>
                
                <v-divider class="my-4"></v-divider>
                
                <p class="text-subtitle-2 text-medium-emphasis mb-3">
                  <v-icon size="18" class="mr-1">mdi-cog</v-icon>
                  Configurações do Modelo
                </p>
                
                <v-row>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="activeProvider"
                      label="Provedor (Grupo)"
                      :items="providerOptions"
                      prepend-inner-icon="mdi-domain"
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-combobox
                      v-model="formData.model"
                      label="Modelo LLM"
                      :items="modelOptions"
                      item-title="title"
                      item-value="value"
                      :return-object="false"
                      prepend-inner-icon="mdi-brain"
                      :loading="loadingModels"
                      placeholder="Modelo manual ou buscar..."
                      hide-no-data
                    >
                      <template v-slot:item="{ props, item }">
                        <v-list-item v-bind="props">
                          <template v-slot:subtitle v-if="item.raw.context_length">
                            <span class="text-caption">{{ formatContextLength(item.raw.context_length) }} tokens</span>
                          </template>
                        </v-list-item>
                      </template>
                    </v-combobox>
                  </v-col>
                </v-row>

                <v-row v-if="!formData.config.is_reasoning_model">
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="formData.temperature"
                      label="Temperature"
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      prepend-inner-icon="mdi-thermometer"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="formData.max_tokens"
                      label="Max Tokens"
                      type="number"
                      min="100"
                      max="128000"
                      prepend-inner-icon="mdi-counter"
                    ></v-text-field>
                  </v-col>
                </v-row>

                <v-row v-if="formData.config.is_reasoning_model">
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="formData.config.reasoning_effort"
                      label="Reasoning Effort"
                      :items="reasoningEffortOptions"
                      item-title="label"
                      item-value="value"
                      prepend-inner-icon="mdi-head-cog"
                      hint="Controle de raciocínio"
                      persistent-hint
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="formData.config.max_completion_tokens"
                      label="Max Completion Tokens"
                      type="number"
                      min="1000"
                      max="128000"
                      prepend-inner-icon="mdi-counter"
                      hint="Total tokens saída"
                      persistent-hint
                    ></v-text-field>
                  </v-col>
                </v-row>

                <v-card variant="outlined" class="mt-3 mb-3" :color="formData.config.is_reasoning_model ? 'purple' : undefined">
                  <v-card-text class="d-flex align-center py-3">
                    <v-switch
                      v-model="formData.config.is_reasoning_model"
                      label="Modelo de Raciocínio"
                      color="purple"
                      hide-details
                      density="comfortable"
                      class="mr-4"
                    ></v-switch>
                    <v-chip v-if="formData.config.is_reasoning_model" color="purple" size="small" variant="tonal">
                      <v-icon start size="14">mdi-head-lightbulb</v-icon>
                      O1 / O3 / DeepSeek R1
                    </v-chip>
                    <span v-else class="text-caption text-medium-emphasis">
                      Ative para modelos como O1, O3-mini, DeepSeek R1 (sem temperature, com reasoning_effort)
                    </span>
                  </v-card-text>
                </v-card>
                
                <v-divider class="my-4"></v-divider>
                
                <p class="text-subtitle-2 text-medium-emphasis mb-3">
                  <v-icon size="18" class="mr-1">mdi-toggle-switch</v-icon>
                  Configurações de Ativação
                </p>
                
                <v-card variant="outlined" class="mb-4">
                  <v-card-text class="pt-4 pb-4">
                    <v-row>
                      <v-col cols="12" sm="6">
                        <v-switch
                          v-model="formData.is_active"
                          label="Agente Ativo"
                          color="success"
                          hide-details
                          density="comfortable"
                        >
                          <template v-slot:prepend>
                            <v-icon :color="formData.is_active ? 'success' : 'grey'">mdi-power</v-icon>
                          </template>
                        </v-switch>
                      </v-col>
                      <v-col cols="12" sm="6">
                        <v-switch
                          v-model="formData.collaboration_enabled"
                          label="Colaboração"
                          color="info"
                          hide-details
                          density="comfortable"
                        >
                          <template v-slot:prepend>
                            <v-icon :color="formData.collaboration_enabled ? 'info' : 'grey'">mdi-account-group</v-icon>
                          </template>
                        </v-switch>
                      </v-col>
                      <v-col cols="12" sm="6">
                        <v-switch
                          v-model="formData.vector_memory_enabled"
                          label="Memória Vetorial"
                          color="deep-purple"
                          hide-details
                          density="comfortable"
                        >
                          <template v-slot:prepend>
                            <v-icon :color="formData.vector_memory_enabled ? 'deep-purple' : 'grey'">mdi-brain</v-icon>
                          </template>
                        </v-switch>
                      </v-col>
                      <v-col cols="12" sm="6">
                        <v-switch
                          v-model="formData.is_orchestrator"
                          label="Modo Orquestrador"
                          color="purple"
                          hide-details
                          density="comfortable"
                        >
                          <template v-slot:prepend>
                            <v-icon :color="formData.is_orchestrator ? 'purple' : 'grey'">mdi-account-supervisor</v-icon>
                          </template>
                        </v-switch>
                      </v-col>
                    </v-row>
                      <v-expand-transition>
                        <v-alert v-if="formData.is_orchestrator" type="info" variant="tonal" density="compact" class="mt-3 mb-0">
                          <template v-slot:prepend>
                            <v-icon>mdi-information</v-icon>
                          </template>
                          Quando ativo, este agente consulta seus colaboradores <strong>antes</strong> de responder, delegando tarefas aos especialistas mais adequados.
                        </v-alert>
                      </v-expand-transition>

                    <v-row class="mt-3">
                      <v-col cols="12">
                        <v-combobox
                          v-model="formData.trigger_keywords"
                          label="Palavras-Chave de Ativação (Opcional)"
                          hint="Se configuradas, o orquestrador acionará este agente PRIORITARIAMENTE quando alguma delas for digitada pelo usuário"
                          persistent-hint
                          multiple
                          chips
                          closable-chips
                          prepend-inner-icon="mdi-key"
                          variant="outlined"
                          density="comfortable"
                        ></v-combobox>
                      </v-col>
                      <v-col cols="12">
                        <v-text-field
                          v-model="formData.entity_memory_path"
                          label="Caminho de Memória por Entidade (Opcional)"
                          hint="Ex: $request.church._id — permite treinar regras por entidade dinâmica extraída do payload"
                          persistent-hint
                          prepend-inner-icon="mdi-domain"
                          variant="outlined"
                          density="comfortable"
                          placeholder="$request.church._id"
                        ></v-text-field>
                      </v-col>
                    </v-row>
                  </v-card-text>
                </v-card>

                <p class="text-subtitle-2 text-medium-emphasis mb-3">
                  <v-icon size="18" class="mr-1">mdi-memory</v-icon>
                  Memória de Curto Prazo
                </p>
                
                <v-card variant="outlined">
                  <v-card-text class="pt-4 pb-4">
                    <v-row>
                      <v-col cols="12" md="6">
                        <v-switch
                          v-model="formData.config.short_term_memory_enabled"
                          label="Ativar Memória STM"
                          color="teal"
                          hide-details
                          density="comfortable"
                        >
                          <template v-slot:prepend>
                            <v-icon :color="formData.config.short_term_memory_enabled ? 'teal' : 'grey'">mdi-history</v-icon>
                          </template>
                        </v-switch>
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-text-field
                          v-model="formData.config.short_term_memory_ttl_hours"
                          label="Tempo de Retenção (Horas)"
                          type="number"
                          min="1"
                          max="720"
                          prepend-inner-icon="mdi-clock-outline"
                          :disabled="!formData.config.short_term_memory_enabled"
                          hint="Tempo que o agente lembrará da conversa"
                          persistent-hint
                        ></v-text-field>
                      </v-col>
                    </v-row>
                  </v-card-text>
                </v-card>
              </v-form>
            </v-window-item>

            <!-- Tab: Personality -->
            <v-window-item value="personality">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar a personalidade.
              </v-alert>

              <div v-else>
                <!-- Orchestrator Mode -->
                <v-card variant="outlined" class="mb-6">
                  <v-card-title class="d-flex align-center py-3 px-4">
                    <v-icon class="mr-2" color="warning">mdi-sitemap</v-icon>
                    <span>Modo Orquestrador</span>
                    <v-spacer></v-spacer>
                    <v-switch
                      v-model="formData.is_orchestrator"
                      color="warning"
                      hide-details
                      density="compact"
                    ></v-switch>
                  </v-card-title>
                  <v-divider></v-divider>
                  <v-card-text>
                    <v-alert type="info" variant="tonal" density="compact" class="mb-0">
                      <template v-slot:prepend>
                        <v-icon>mdi-information</v-icon>
                      </template>
                      Quando ativado, este agente terá controle hierárquico sobre outros agentes,
                      podendo delegar tarefas e supervisionar ações. Use os "Colaboradores" para
                      definir quais agentes serão subordinados.
                    </v-alert>
                  </v-card-text>
                </v-card>

                <!-- Emotional Profile -->
                <v-card variant="outlined">
                  <v-card-title class="d-flex align-center py-3 px-4">
                    <v-icon class="mr-2" color="purple">mdi-heart-pulse</v-icon>
                    <span>Perfil Emocional</span>
                  </v-card-title>
                  <v-divider></v-divider>
                  <v-card-text>
                    <p class="text-body-2 text-medium-emphasis mb-4">
                      Selecione o estilo de comunicação deste agente. Cada perfil adiciona instruções
                      específicas ao comportamento do agente.
                    </p>

                    <!-- Category: Pastoral -->
                    <div class="mb-4" v-if="pastoralProfiles.length > 0">
                      <p class="text-subtitle-2 font-weight-bold mb-2">
                        <v-icon size="16" class="mr-1">mdi-church</v-icon>
                        Pastorais
                      </p>
                      <div class="d-flex flex-wrap gap-2">
                        <v-chip
                          v-for="profile in pastoralProfiles"
                          :key="profile.id"
                          :color="formData.emotional_profile_id === profile.id ? profile.color : 'grey-lighten-2'"
                          :variant="formData.emotional_profile_id === profile.id ? 'flat' : 'outlined'"
                          @click="selectEmotionalProfile(profile)"
                          class="profile-chip"
                          size="large"
                        >
                          <v-icon start>{{ profile.icon }}</v-icon>
                          {{ profile.name }}
                        </v-chip>
                      </div>
                    </div>

                    <!-- Category: Professional -->
                    <div class="mb-4" v-if="professionalProfiles.length > 0">
                      <p class="text-subtitle-2 font-weight-bold mb-2">
                        <v-icon size="16" class="mr-1">mdi-briefcase</v-icon>
                        Profissionais
                      </p>
                      <div class="d-flex flex-wrap gap-2">
                        <v-chip
                          v-for="profile in professionalProfiles"
                          :key="profile.id"
                          :color="formData.emotional_profile_id === profile.id ? profile.color : 'grey-lighten-2'"
                          :variant="formData.emotional_profile_id === profile.id ? 'flat' : 'outlined'"
                          @click="selectEmotionalProfile(profile)"
                          class="profile-chip"
                          size="large"
                        >
                          <v-icon start>{{ profile.icon }}</v-icon>
                          {{ profile.name }}
                        </v-chip>
                      </div>
                    </div>

                    <!-- Intensity -->
                    <div class="mb-4" v-if="formData.emotional_profile_id">
                      <p class="text-subtitle-2 font-weight-bold mb-2">
                        <v-icon size="16" class="mr-1">mdi-tune</v-icon>
                        Intensidade
                      </p>
                      <v-btn-toggle
                        v-model="formData.emotional_intensity"
                        mandatory
                        divided
                        variant="outlined"
                        color="primary"
                      >
                        <v-btn value="low" size="small">
                          <v-icon start>mdi-speedometer-slow</v-icon>
                          Sutil
                        </v-btn>
                        <v-btn value="medium" size="small">
                          <v-icon start>mdi-speedometer-medium</v-icon>
                          Moderada
                        </v-btn>
                        <v-btn value="high" size="small">
                          <v-icon start>mdi-speedometer</v-icon>
                          Intensa
                        </v-btn>
                      </v-btn-toggle>
                    </div>

                    <!-- Preview -->
                    <v-expand-transition>
                      <div v-if="selectedEmotionalProfile">
                        <v-card variant="tonal" :color="selectedEmotionalProfile.color" class="mt-4">
                          <v-card-title class="text-subtitle-2 py-2">
                            <v-icon start size="18">{{ selectedEmotionalProfile.icon }}</v-icon>
                            {{ selectedEmotionalProfile.name }}
                            <v-chip size="x-small" class="ml-2">{{ selectedEmotionalProfile.category }}</v-chip>
                          </v-card-title>
                          <v-card-text class="pt-0 text-body-2">
                            {{ selectedEmotionalProfile.description }}
                          </v-card-text>
                        </v-card>
                      </div>
                    </v-expand-transition>

                    <!-- Clear Selection -->
                    <v-btn
                      v-if="formData.emotional_profile_id"
                      variant="text"
                      color="error"
                      size="small"
                      class="mt-3"
                      @click="clearEmotionalProfile"
                    >
                      <v-icon start>mdi-close</v-icon>
                      Remover Perfil Emocional
                    </v-btn>
                  </v-card-text>
                </v-card>
              </div>
            </v-window-item>

            <!-- Tab: Skills -->
            <v-window-item value="skills">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para associar Skills de comportamento especializado.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-star-shooting-outline</v-icon>
                    Skills do Agente
                  </h3>
                  <v-btn size="small" variant="text" color="primary" to="/skills" target="_blank">
                    Criar Nova Skill <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                  <template v-slot:prepend>
                    <v-icon>mdi-information</v-icon>
                  </template>
                  Selecione os comportamentos e regras de instrução especializadas que o agente deve seguir. Skills inativas não serão enviadas para a IA.
                </v-alert>

                <div class="d-flex align-center gap-2 mb-4">
                  <v-select
                    v-model="selectedSkillToAdd"
                    :items="availableSkills"
                    item-title="name"
                    item-value="id"
                    label="Vincular Skill"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione uma Skill..."
                    :disabled="availableSkills.length === 0"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon color="info">mdi-star-circle</v-icon>
                        </template>
                        <template v-slot:subtitle>
                          <span class="text-caption">{{ item.raw.intent?.substring(0, 40) }}...</span>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                  <v-btn color="primary" @click="addSkill" :disabled="!selectedSkillToAdd" :loading="addingSkill">
                    <v-icon start>mdi-plus</v-icon>
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                  <v-list-subheader>
                    <v-icon size="18" class="mr-1">mdi-star-shooting</v-icon>
                    Skills Associadas ({{ agentSkills.length }})
                  </v-list-subheader>
                  <v-list-item v-if="agentSkills.length === 0">
                    <v-list-item-title class="text-center py-6 text-medium-emphasis">
                      <v-icon size="48" color="grey-lighten-1" class="mb-2 d-block mx-auto">mdi-star-off-outline</v-icon>
                      Nenhuma skill associada a este agente
                    </v-list-item-title>
                  </v-list-item>
                  <v-list-item v-for="skill in agentSkills" :key="skill.id">
                    <template v-slot:prepend>
                      <v-avatar color="info" size="36">
                        <v-icon color="white" size="18">mdi-star-circle</v-icon>
                      </v-avatar>
                    </template>
                    <v-list-item-title class="font-weight-medium">{{ skill.name }}</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-chip size="x-small" :color="skill.is_active ? 'success' : 'error'" variant="tonal">
                        {{ skill.is_active ? 'Ativa' : 'Inativa' }}
                      </v-chip>
                    </v-list-item-subtitle>
                    <template v-slot:append>
                      <v-btn icon variant="text" color="error" size="small" @click="removeSkill(skill)" :loading="removingSkill === skill.id">
                        <v-icon>mdi-link-variant-off</v-icon>
                        <v-tooltip activator="parent" location="top">Remover skill</v-tooltip>
                      </v-btn>
                    </template>
                  </v-list-item>
                </v-list>
              </div>
            </v-window-item>

            <!-- Tab: Tools (MCPs) -->
            <v-window-item value="tools">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar as ferramentas (MCPs).
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-connection</v-icon>
                    Ferramentas MCP
                  </h3>
                  <v-btn size="small" variant="text" color="primary" to="/mcp" target="_blank">
                    Gerenciar MCPs <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                  <template v-slot:prepend>
                    <v-icon>mdi-information</v-icon>
                  </template>
                  Selecione quais MCPs este agente poderá utilizar. MCPs não associados não estarão disponíveis.
                </v-alert>

                <div class="d-flex align-center gap-2 mb-4">
                  <v-select
                    v-model="selectedMcpToAdd"
                    :items="availableMcps"
                    item-title="name"
                    item-value="id"
                    label="Adicionar MCP"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione um MCP..."
                    :disabled="availableMcps.length === 0"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon :color="getProtocolColor(item.raw.protocol)">{{ getProtocolIcon(item.raw.protocol) }}</v-icon>
                        </template>
                        <template v-slot:subtitle>
                          <v-chip size="x-small" :color="getProtocolColor(item.raw.protocol)" class="mr-1">
                            {{ item.raw.protocol?.toUpperCase() || 'HTTP' }}
                          </v-chip>
                          <span class="text-caption">{{ item.raw.endpoint?.substring(0, 40) }}...</span>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                  <v-btn color="primary" @click="addMcp" :disabled="!selectedMcpToAdd" :loading="addingMcp">
                    <v-icon start>mdi-plus</v-icon>
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                  <v-list-subheader>
                    <v-icon size="18" class="mr-1">mdi-link-variant</v-icon>
                    MCPs Associados ({{ agentMcps.length }})
                  </v-list-subheader>
                  <v-list-item v-if="agentMcps.length === 0">
                    <v-list-item-title class="text-center py-6 text-medium-emphasis">
                      <v-icon size="48" color="grey-lighten-1" class="mb-2 d-block mx-auto">mdi-connection</v-icon>
                      Nenhum MCP associado a este agente
                    </v-list-item-title>
                  </v-list-item>
                  <v-list-item v-for="mcp in agentMcps" :key="mcp.id">
                    <template v-slot:prepend>
                      <v-avatar :color="getProtocolColor(mcp.protocol)" size="36">
                        <v-icon color="white" size="18">{{ getProtocolIcon(mcp.protocol) }}</v-icon>
                      </v-avatar>
                    </template>
                    <v-list-item-title class="font-weight-medium">{{ mcp.name }}</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-chip size="x-small" :color="getProtocolColor(mcp.protocol)" class="mr-1">
                        {{ mcp.protocol?.toUpperCase() || 'HTTP' }}
                      </v-chip>
                      <v-chip size="x-small" :color="mcp.is_active ? 'success' : 'error'" variant="tonal">
                        {{ mcp.is_active ? 'Ativo' : 'Inativo' }}
                      </v-chip>
                    </v-list-item-subtitle>
                    <template v-slot:append>
                      <v-btn icon variant="text" color="error" size="small" @click="removeMcp(mcp)" :loading="removingMcp === mcp.id">
                        <v-icon>mdi-link-variant-off</v-icon>
                        <v-tooltip activator="parent" location="top">Remover acesso</v-tooltip>
                      </v-btn>
                    </template>
                  </v-list-item>
                </v-list>

                <v-divider class="my-6"></v-divider>

                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-folder-multiple</v-icon>
                    Grupos de MCP
                  </h3>
                  <v-btn size="small" variant="text" color="primary" to="/mcp" target="_blank">
                    Gerenciar Grupos <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                  <template v-slot:prepend>
                    <v-icon>mdi-information</v-icon>
                  </template>
                  Vincular um Grupo fará com que todas as ferramentas MCP contidas nele fiquem disponíveis para o Agente.
                </v-alert>

                <div class="d-flex align-center gap-2 mb-4">
                  <v-select
                    v-model="selectedMcpGroupToAdd"
                    :items="availableMcpGroups"
                    item-title="name"
                    item-value="id"
                    label="Adicionar Grupo de MCP"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione um Grupo..."
                    :disabled="availableMcpGroups.length === 0"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon color="primary">mdi-folder</v-icon>
                        </template>
                        <template v-slot:subtitle>
                          <span class="text-caption">{{ item.raw.description?.substring(0, 40) }}...</span>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                  <v-btn color="primary" @click="addMcpGroup" :disabled="!selectedMcpGroupToAdd" :loading="addingMcpGroup">
                    <v-icon start>mdi-plus</v-icon>
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                  <v-list-subheader>
                    <v-icon size="18" class="mr-1">mdi-folder-multiple</v-icon>
                    Grupos de MCP Associados ({{ agentMcpGroups.length }})
                  </v-list-subheader>
                  <v-list-item v-if="agentMcpGroups.length === 0">
                    <v-list-item-title class="text-center py-6 text-medium-emphasis">
                      <v-icon size="48" color="grey-lighten-1" class="mb-2 d-block mx-auto">mdi-folder-off</v-icon>
                      Nenhum Grupo de MCP associado
                    </v-list-item-title>
                  </v-list-item>
                  <v-list-item v-for="group in agentMcpGroups" :key="group.id">
                    <template v-slot:prepend>
                      <v-avatar color="primary" size="36">
                        <v-icon color="white" size="18">mdi-folder</v-icon>
                      </v-avatar>
                    </template>
                    <v-list-item-title class="font-weight-medium">{{ group.name }}</v-list-item-title>
                    <v-list-item-subtitle v-if="group.description">
                      {{ group.description }}
                    </v-list-item-subtitle>
                    <template v-slot:append>
                      <v-btn icon variant="text" color="error" size="small" @click="removeMcpGroup(group)" :loading="removingMcpGroup === group.id">
                        <v-icon>mdi-link-variant-off</v-icon>
                        <v-tooltip activator="parent" location="top">Remover acesso</v-tooltip>
                      </v-btn>
                    </template>
                  </v-list-item>
                </v-list>
              </div>
            </v-window-item>

            <!-- Tab: Input Schema -->
            <v-window-item value="input">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar a entrada estruturada.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-application-import</v-icon>
                    Configuração de Entrada (Webhook)
                  </h3>
                  
                  <v-tabs v-model="inputSubTab" density="compact" color="primary" class="mb-4">
                    <v-tab value="context">1. Contexto (LLM)</v-tab>
                    <v-tab value="transition">2. Transição (Sistema)</v-tab>
                  </v-tabs>
                </div>

                <v-window v-model="inputSubTab">
                  <!-- Entrada: Contexto -->
                  <v-window-item value="context">
                    <div class="d-flex justify-space-between align-center mb-2">
                      <v-alert type="info" variant="tonal" density="compact" class="mb-0 flex-grow-1 mr-2">
                        <template v-slot:prepend>
                          <v-icon>mdi-brain</v-icon>
                        </template>
                        <strong>Contexto:</strong> Dados injetados diretamente no <strong>System Prompt</strong> para o LLM raciocinar.
                      </v-alert>
                      <v-btn-toggle
                        v-model="inputSchemaPreset"
                        divided
                        variant="outlined"
                        density="compact"
                        color="primary"
                        @update:model-value="applyInputPreset"
                      >
                        <v-btn value="church" size="small">Igreja</v-btn>
                        <v-btn value="student" size="small">Aluno</v-btn>
                        <v-btn value="custom" size="small">Person.</v-btn>
                      </v-btn-toggle>
                    </div>

                    <v-textarea
                      v-model="inputSchemaJson"
                      label="Schema de Entrada (Contexto JSON)"
                      placeholder='{"nome_usuario": {"type": "string", "description": "..."}}'
                      rows="7"
                      variant="outlined"
                      :error="inputSchemaError !== ''"
                      :error-messages="inputSchemaError"
                      @update:model-value="validateInputSchema"
                      class="output-schema-editor mt-4"
                      style="font-family: monospace"
                    ></v-textarea>

                    <v-expand-transition>
                      <v-card v-if="parsedInputSchema" variant="tonal" color="success" class="mt-2">
                        <v-card-title class="text-subtitle-2 py-2">
                          <v-icon start size="18">mdi-check-circle</v-icon>
                          Campos Injetados no LLM ({{ Object.keys(parsedInputSchema).length }})
                        </v-card-title>
                        <v-card-text class="pt-0">
                          <v-chip v-for="(field, name) in parsedInputSchema" :key="name" size="small" class="mr-1 mb-1">
                            <v-icon start size="14">{{ field.optional ? 'mdi-help-circle-outline' : 'mdi-asterisk' }}</v-icon>
                            {{ name }}
                            <v-tooltip activator="parent" location="top">{{ field.description || field.type }}{{ field.optional ? ' (opcional)' : ' (obrigatório)' }}</v-tooltip>
                          </v-chip>
                        </v-card-text>
                      </v-card>
                    </v-expand-transition>
                  </v-window-item>

                  <!-- Entrada: Transição -->
                  <v-window-item value="transition">
                    <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
                      <template v-slot:prepend>
                        <v-icon>mdi-router-wireless</v-icon>
                      </template>
                      <strong>Transição:</strong> Metadados de sessão recebidos no Webhook. <strong>NÃO</strong> são enviados ao LLM para evitar alucinações. São mantidos no estado e retornados no final.
                    </v-alert>

                    <v-textarea
                      v-model="transitionInputSchemaJson"
                      label="Schema de Entrada (Transição JSON)"
                      placeholder='{"session_id": {"type": "string", "required": true}}'
                      rows="7"
                      variant="outlined"
                      :error="transitionInputSchemaError !== ''"
                      :error-messages="transitionInputSchemaError"
                      @update:model-value="validateTransitionInputSchema"
                      class="output-schema-editor"
                      style="font-family: monospace"
                    ></v-textarea>

                    <v-expand-transition>
                      <v-card v-if="parsedTransitionInputSchema" variant="tonal" color="warning" class="mt-2">
                        <v-card-title class="text-subtitle-2 py-2">
                          <v-icon start size="18">mdi-check-circle</v-icon>
                          Variáveis de Sessão Recebidas ({{ Object.keys(parsedTransitionInputSchema).length }})
                        </v-card-title>
                        <v-card-text class="pt-0">
                          <v-chip v-for="(field, name) in parsedTransitionInputSchema" :key="name" size="small" class="mr-1 mb-1" color="warning">
                            <v-icon start size="14">{{ field.required ? 'mdi-asterisk' : 'mdi-help-circle-outline' }}</v-icon>
                            {{ name }}
                          </v-chip>
                        </v-card-text>
                      </v-card>
                    </v-expand-transition>
                  </v-window-item>
                </v-window>
              </div>
            </v-window-item>

            <!-- Tab: Output Schema -->
            <v-window-item value="output">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar a saída estruturada.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-code-json</v-icon>
                    Configuração de Saída (Webhook)
                  </h3>
                  
                  <v-tabs v-model="outputSubTab" density="compact" color="primary" class="mb-4">
                    <v-tab value="context">1. Contexto (LLM)</v-tab>
                    <v-tab value="transition">2. Transição (Sistema)</v-tab>
                  </v-tabs>
                </div>

                <v-window v-model="outputSubTab">
                  <!-- Saída: Contexto -->
                  <v-window-item value="context">
                    <div class="d-flex justify-space-between align-center mb-2">
                      <v-alert type="info" variant="tonal" density="compact" class="mb-0 flex-grow-1 mr-2">
                        <template v-slot:prepend>
                          <v-icon>mdi-brain</v-icon>
                        </template>
                        <strong>Contexto:</strong> Estrutura JSON que o LLM é <strong>OBRIGADO</strong> a gerar como resposta.
                      </v-alert>
                      <v-btn-toggle
                        v-model="outputSchemaPreset"
                        divided
                        variant="outlined"
                        density="compact"
                        color="primary"
                        @update:model-value="applyOutputPreset"
                      >
                        <v-btn value="default" size="small">Padrão</v-btn>
                        <v-btn value="whatsapp" size="small">WhatsApp</v-btn>
                        <v-btn value="custom" size="small">Person.</v-btn>
                      </v-btn-toggle>
                    </div>

                    <v-textarea
                      v-model="outputSchemaJson"
                      label="Schema de Saída (Contexto JSON)"
                      placeholder='{"output": {"type": "string", "description": "Resposta"}}'
                      rows="7"
                      variant="outlined"
                      :error="outputSchemaError !== ''"
                      :error-messages="outputSchemaError"
                      @update:model-value="validateOutputSchema"
                      class="output-schema-editor mt-4"
                      style="font-family: monospace"
                    ></v-textarea>

                    <v-expand-transition>
                      <v-card v-if="parsedOutputSchema" variant="tonal" color="success" class="mt-2">
                        <v-card-title class="text-subtitle-2 py-2">
                          <v-icon start size="18">mdi-check-circle</v-icon>
                          Campos de Saída do LLM ({{ Object.keys(parsedOutputSchema).length }})
                        </v-card-title>
                        <v-card-text class="pt-0">
                          <v-chip v-for="(field, name) in parsedOutputSchema" :key="name" size="small" class="mr-1 mb-1">
                            <v-icon start size="14">{{ field.enum ? 'mdi-format-list-bulleted' : 'mdi-text' }}</v-icon>
                            {{ name }}
                            <v-tooltip activator="parent" location="top">{{ field.description || field.type }}</v-tooltip>
                          </v-chip>
                        </v-card-text>
                      </v-card>
                    </v-expand-transition>
                  </v-window-item>

                  <!-- Saída: Transição -->
                  <v-window-item value="transition">
                    <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
                      <template v-slot:prepend>
                        <v-icon>mdi-router-wireless</v-icon>
                      </template>
                      <strong>Transição:</strong> Variáveis anexadas ao Callback final, agrupando o resultado do LLM com os dados de roteamento do seu sistema externo.
                    </v-alert>

                    <v-textarea
                      v-model="transitionOutputSchemaJson"
                      label="Schema de Saída (Transição JSON)"
                      placeholder='{"session_id": {"type": "string"}, "status_atendimento": {"type": "string", "enum": ["aberto", "fechado"]}}'
                      rows="7"
                      variant="outlined"
                      :error="transitionOutputSchemaError !== ''"
                      :error-messages="transitionOutputSchemaError"
                      @update:model-value="validateTransitionOutputSchema"
                      class="output-schema-editor"
                      style="font-family: monospace"
                    ></v-textarea>

                    <v-expand-transition>
                      <v-card v-if="parsedTransitionOutputSchema" variant="tonal" color="warning" class="mt-2">
                        <v-card-title class="text-subtitle-2 py-2">
                          <v-icon start size="18">mdi-check-circle</v-icon>
                          Variáveis de Retorno Anexadas ({{ Object.keys(parsedTransitionOutputSchema).length }})
                        </v-card-title>
                        <v-card-text class="pt-0">
                          <v-chip v-for="(field, name) in parsedTransitionOutputSchema" :key="name" size="small" class="mr-1 mb-1" color="warning">
                            <v-icon start size="14">{{ field.enum ? 'mdi-format-list-bulleted' : 'mdi-text' }}</v-icon>
                            {{ name }}
                          </v-chip>
                        </v-card-text>
                      </v-card>
                    </v-expand-transition>
                  </v-window-item>
                </v-window>
              </div>
            </v-window-item>
  
            <!-- Tab: Planner -->
            <v-window-item value="planner">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar o Planejador.
              </v-alert>
              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Planejador Dinâmico</h3>
                  <v-switch
                    v-model="formData.is_planner"
                    label="Ativar Planejador"
                    color="indigo"
                    density="compact"
                    hide-details
                    :disabled="!formData.is_orchestrator"
                  ></v-switch>
                </div>
                
                <v-alert v-if="!formData.is_orchestrator" type="warning" variant="tonal" density="compact" class="mb-4">
                  O Planejador só pode ser ativado se o agente estiver em <strong>Modo Orquestrador</strong> (Aba Geral).
                </v-alert>
                
                <p class="text-body-2 text-medium-emphasis mb-4">
                  Quando ativo, o Planejador processa a instrução de delegação do orquestrador antes de enviá-la ao colaborador. Ele utiliza um modelo menor e mais focado para gerar um checklist tático (em Markdown) tornando a instrução mais granular e direcionada.
                </p>

                <div v-if="formData.is_planner">
                  <v-textarea
                    v-model="formData.planner_prompt"
                    label="Prompt / Diretriz do Planejador"
                    placeholder="Ex: Você é o Planejador Mestre do Orquestrador. Quebre a instrução em formato Markdown list '-' e não responda mais nada."
                    rows="5"
                    variant="outlined"
                    persistent-hint
                    hint="Deixe em branco para usar o prompt padrão do sistema."
                  ></v-textarea>

                  <v-autocomplete
                    v-model="formData.planner_model"
                    label="Modelo do Planejador"
                    :items="modelOptions"
                    item-title="title"
                    item-value="value"
                    :loading="loadingModels"
                    placeholder="Selecione um modelo (ex: gpt-4o-mini)"
                    class="mt-4"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="18">
                            {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                          </v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                </div>
              </div>
            </v-window-item>

            <!-- Tab: Thinker -->
            <v-window-item value="thinker">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar o Thinker.
              </v-alert>
              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Thinker (Planejador Estratégico)</h3>
                  <v-switch
                    v-model="formData.is_thinker"
                    label="Ativar Thinker"
                    color="teal"
                    density="compact"
                    hide-details
                  ></v-switch>
                </div>
                
                <p class="text-body-2 text-medium-emphasis mb-4">
                  O Thinker é um tipo especial de agente que realiza planejamento estratégico antes do agente principal executar. Ele analisa a solicitação e gera um plano estruturado que otimiza a resposta do agente.
                </p>

                <div v-if="formData.is_thinker">
                  <v-switch
                    v-model="formData.thinker_restrictive"
                    label="Execução Restritiva"
                    color="orange"
                    density="compact"
                    hide-details
                    class="mb-4"
                  >
                    <template v-slot:prepend>
                      <v-icon color="orange">mdi-lock-outline</v-icon>
                    </template>
                  </v-switch>
                  <p class="text-caption text-medium-emphasis mb-4">
                    Quando ativado, o agente seguirá <strong>APENAS</strong> as instruções do Thinker, sem adaptar ou inventar novas etapas.
                  </p>
                  
                  <v-textarea
                    v-model="formData.thinker_prompt"
                    label="Prompt do Thinker"
                    placeholder="Ex: Você é um estrategista de IA. Analise a solicitação do usuário e crie um plano detalhado em Markdown para o agente executar."
                    rows="5"
                    variant="outlined"
                    persistent-hint
                    hint="Deixe em branco para usar o prompt padrão do sistema."
                  ></v-textarea>

                  <v-autocomplete
                    v-model="formData.thinker_model"
                    label="Modelo do Thinker"
                    :items="modelOptions"
                    item-title="title"
                    item-value="value"
                    :loading="loadingModels"
                    placeholder="Selecione um modelo (ex: gpt-4o-mini)"
                    class="mt-4"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="18">
                            {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                          </v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-autocomplete>

                  <v-autocomplete
                    v-model="formData.thinker_ids"
                    label="Thinkers Vinculados"
                    :items="availableThinkers"
                    item-title="title"
                    item-value="value"
                    multiple
                    chips
                    closable-chips
                    class="mt-4"
                    hint="Selecione outros agentes que servirão como Thinkers para este agente"
                    persistent-hint
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon color="teal" size="18">mdi-head-brain</v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                </div>
              </div>
            </v-window-item>

            <!-- Tab: Guardrail -->
            <v-window-item value="guardrail">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar o Guardrail.
              </v-alert>
              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Guardrail Interno (Validador)</h3>
                  <v-switch
                    v-model="formData.is_guardrail_active"
                    label="Ativar Guardrail"
                    color="red"
                    density="compact"
                    hide-details
                  ></v-switch>
                </div>
                
                <p class="text-body-2 text-medium-emphasis mb-4">
                  O sistema de Guardrail atua como um inspetor final da resposta gerada por este agente. Se ele identificar que a resposta violou diretrizes éticas ou regras fundamentais do System Prompt original, ele injetará uma nota de erro (invisível ao usuário) exigindo que o próprio agente corrija a resposta através de um "retry".
                </p>

                <div v-if="formData.is_guardrail_active">
                  <v-textarea
                    v-model="formData.guardrail_prompt"
                    label="Prompt Especialista do Validador"
                    placeholder="Ex: Você é um auditor de qualidade rígido. Verifique se o agente quebrou a regra principal de não repassar senhas. Responda VALID em caso afirmativo, se não explique o crime."
                    rows="6"
                    variant="outlined"
                    persistent-hint
                    hint="Deixe em branco para usar a verificação rigorosa padrão."
                  ></v-textarea>

                  <v-autocomplete
                    v-model="formData.guardrail_model"
                    label="Modelo do Guardrail"
                    :items="modelOptions"
                    item-title="title"
                    item-value="value"
                    :loading="loadingModels"
                    placeholder="Selecione um modelo (ex: gpt-4o-mini)"
                    class="mt-4"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="18">
                            {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                          </v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                </div>
              </div>
            </v-window-item>

            <!-- Tab: Resilience -->
            <v-window-item value="resilience">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar a resiliência.
              </v-alert>
              
              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Tolerância a Falhas</h3>
                  <v-switch
                    v-model="resilienceData.verbose_logging"
                    label="Logs Detalhados"
                    color="primary"
                    density="compact"
                    hide-details
                  ></v-switch>
                </div>

                <v-row>
                  <v-col cols="12" md="4">
                    <v-text-field
                      v-model.number="resilienceData.max_retries"
                      label="Max Retries"
                      type="number"
                      min="0"
                      max="10"
                      hint="Tentativas em caso de erro"
                      persistent-hint
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-text-field
                      v-model.number="resilienceData.timeout_seconds"
                      label="Timeout (segundos)"
                      type="number"
                      min="10"
                      max="600"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-switch
                      v-model="resilienceData.retry_exponential_backoff"
                      label="Exponential Backoff"
                      color="primary"
                    ></v-switch>
                  </v-col>
                </v-row>

                <h3 class="text-subtitle-1 font-weight-bold mt-4 mb-2">Fallback Model</h3>
                <v-card variant="outlined" class="pa-3 mb-4">
                  <div class="d-flex align-center mb-2">
                    <v-switch
                      v-model="resilienceData.fallback_enabled"
                      label="Habilitar Fallback"
                      color="warning"
                      hide-details
                      class="mr-4"
                    ></v-switch>
                    <span class="text-caption text-medium-emphasis">Usa modelo alternativo se o principal falhar</span>
                  </div>
                  
                  <v-expand-transition>
                    <div v-if="resilienceData.fallback_enabled">
                      <v-row>
                        <v-col cols="12" md="6">
                          <v-autocomplete
                            v-model="resilienceData.fallback_model"
                            label="Modelo de Fallback"
                            :items="modelOptions"
                            item-title="title"
                            item-value="value"
                            :loading="loadingModels"
                            placeholder="Buscar modelo..."
                          >
                            <template v-slot:item="{ props, item }">
                              <v-list-item v-bind="props">
                                <template v-slot:prepend>
                                  <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="18">
                                    {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                                  </v-icon>
                                </template>
                              </v-list-item>
                            </template>
                            <template v-slot:selection="{ item }">
                              <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="16" class="mr-1">
                                {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                              </v-icon>
                              {{ item.raw.title }}
                            </template>
                          </v-autocomplete>
                        </v-col>
                        <v-col cols="12" md="6">
                          <v-text-field
                            v-model.number="resilienceData.fallback_temperature"
                            label="Temperature"
                            type="number"
                            step="0.1"
                          ></v-text-field>
                        </v-col>
                      </v-row>
                    </div>
                  </v-expand-transition>
                </v-card>

                <h3 class="text-subtitle-1 font-weight-bold mt-4 mb-2">Conversational HITL (WhatsApp / Webhook)</h3>
                <v-card variant="outlined" class="pa-3 mb-4">
                  <p class="text-caption text-medium-emphasis mb-3">Pausa o LLM e envia pergunta direta via mensageria aguardando a resposta humana no chat.</p>
                  
                  <v-row>
                    <v-col cols="12" md="6">
                      <v-switch
                        v-model="resilienceData.hitl_user_approval_enabled"
                        label="Aprovação do Usuário Ativo"
                        color="success"
                        hide-details
                      ></v-switch>
                    </v-col>
                    <v-col cols="12" md="6">
                      <v-switch
                        v-model="resilienceData.hitl_admin_approval_enabled"
                        label="Aprovação de Administrador"
                        color="secondary"
                        hide-details
                      ></v-switch>
                    </v-col>
                  </v-row>

                  <v-expand-transition>
                    <div v-if="resilienceData.hitl_user_approval_enabled || resilienceData.hitl_admin_approval_enabled" class="mt-4">
                      <v-divider class="mb-4"></v-divider>
                      <v-row>
                        <v-col cols="12" v-if="resilienceData.hitl_admin_approval_enabled">
                          <v-text-field
                            v-model="resilienceData.hitl_admin_contact"
                            label="Contato do Admin (Telefone ou Variável)"
                            placeholder="Ex: {{ $request.admin_phone }}"
                            hint="Para quem a requisição de aprovação será enviada"
                            persistent-hint
                            variant="outlined"
                            density="compact"
                          ></v-text-field>
                        </v-col>
                        <v-col cols="12">
                          <v-textarea
                            v-model="resilienceData.hitl_message_template"
                            label="Template da Mensagem de Pausa"
                            placeholder="Ex: {{ $AIresponse }} ou 'Aguarde aprovação'"
                            hint="A mensagem de pausa manual do grafo. Use {{ $AIresponse }} para o LLM perguntar."
                            persistent-hint
                            rows="2"
                            variant="outlined"
                          ></v-textarea>
                        </v-col>
                      </v-row>
                    </div>
                  </v-expand-transition>
                </v-card>

                <h3 class="text-subtitle-1 font-weight-bold mt-4 mb-2">Painel de Aprovação (Dashboard)</h3>
                <v-card variant="outlined" class="pa-3">
                  <v-switch
                    v-model="resilienceData.human_approval_enabled"
                    label="Requer Aprovação Humana no Painel"
                    color="error"
                    hide-details
                  ></v-switch>
                  
                  <v-expand-transition>
                    <div v-if="resilienceData.human_approval_enabled" class="mt-3">
                      <v-row>
                        <v-col cols="12" md="6">
                          <v-text-field
                            v-model.number="resilienceData.human_approval_timeout_seconds"
                            label="Tempo limite de aprovação (s)"
                            type="number"
                          ></v-text-field>
                        </v-col>
                        <v-col cols="12" md="6">
                          <v-select
                            v-model="resilienceData.interrupt_before_nodes"
                            label="Interromper antes de"
                            multiple
                            chips
                            :items="['tool_execution', 'agent_response', 'mcp_execution']"
                          ></v-select>
                        </v-col>
                      </v-row>
                    </div>
                  </v-expand-transition>
                </v-card>
              </div>
            </v-window-item>

            <!-- Tab: Knowledge Base -->
            <v-window-item value="knowledge">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para associar documentos.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Base de Conhecimento (RAG)</h3>
                  <v-btn size="small" variant="text" color="primary" to="/documents" target="_blank">
                    Gerenciar Documentos <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <v-card variant="flat" border class="mb-4">
                  <v-list density="compact" lines="one">
                    <v-list-subheader>Documentos Globais (Disponíveis para todos)</v-list-subheader>
                    <v-list-item v-if="globalDocs.length === 0">
                      <v-list-item-title class="text-caption text-medium-emphasis">Nenhum documento global</v-list-item-title>
                    </v-list-item>
                    <v-list-item v-for="doc in globalDocs" :key="doc.id">
                      <template v-slot:prepend>
                        <v-icon color="warning">mdi-earth</v-icon>
                      </template>
                      <v-list-item-title>{{ doc.name }}</v-list-item-title>
                      <v-list-item-subtitle>{{ doc.file_type.toUpperCase() }} • {{ doc.chunk_count }} chunks</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-card>

                <div class="d-flex align-center gap-2 mb-2">
                  <v-select
                    v-model="selectedDocToAdd"
                    :items="availableDocs"
                    item-title="name"
                    item-value="id"
                    label="Adicionar Documento Privado"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione um documento..."
                  ></v-select>
                  <v-btn color="primary" @click="addDocument" :disabled="!selectedDocToAdd" :loading="addingDoc">
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                   <v-list-subheader>Documentos Associados</v-list-subheader>
                   <v-list-item v-if="agentDocs.length === 0">
                     <v-list-item-title class="text-center py-4 text-medium-emphasis">
                       Nenhum documento privado associado
                     </v-list-item-title>
                   </v-list-item>
                   <v-list-item v-for="doc in agentDocs" :key="doc.id">
                     <template v-slot:prepend>
                       <v-icon color="primary">mdi-file-document</v-icon>
                     </template>
                     <v-list-item-title>{{ doc.name }}</v-list-item-title>
                     <v-list-item-subtitle>
                       <v-chip size="x-small" :color="doc.status === 'ready' ? 'success' : 'warning'">{{ doc.status }}</v-chip>
                     </v-list-item-subtitle>
                     <template v-slot:append>
                       <v-btn icon variant="text" color="error" size="small" @click="removeDocument(doc)">
                         <v-icon>mdi-link-variant-off</v-icon>
                       </v-btn>
                     </template>
                   </v-list-item>
                </v-list>
              </div>
            </v-window-item>

            <!-- Tab: Information Bases -->
            <v-window-item value="information_bases">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para associar Bases de Informações.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Bases de Informações Estruturadas</h3>
                  <v-btn size="small" variant="text" color="primary" to="/information-bases" target="_blank">
                    Gerenciar Bases <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <div class="d-flex align-center gap-2 mb-2">
                  <v-select
                    v-model="selectedBaseToAdd"
                    :items="availableBases"
                    item-title="name"
                    item-value="id"
                    label="Vincular Base de Informações"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione uma Base..."
                    :disabled="availableBases.length === 0"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon color="success">mdi-database-search</v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                  <v-btn color="primary" @click="addBase" :disabled="!selectedBaseToAdd" :loading="addingBase">
                    <v-icon start>mdi-plus</v-icon>
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                   <v-list-subheader>Bases Associadas ({{ agentBases.length }})</v-list-subheader>
                   <v-list-item v-if="agentBases.length === 0">
                     <v-list-item-title class="text-center py-4 text-medium-emphasis">
                       Nenhuma Base de Informações associada
                     </v-list-item-title>
                   </v-list-item>
                   <v-list-item v-for="base in agentBases" :key="base.id">
                     <template v-slot:prepend>
                       <v-icon color="primary">mdi-database-search</v-icon>
                     </template>
                     <v-list-item-title>{{ base.name }}</v-list-item-title>
                     <v-list-item-subtitle>
                       ID: {{ base.code }}
                     </v-list-item-subtitle>
                     <template v-slot:append>
                       <v-btn icon variant="text" color="error" size="small" @click="removeBase(base)" :loading="removingBase === base.id">
                         <v-icon>mdi-link-variant-off</v-icon>
                       </v-btn>
                     </template>
                   </v-list-item>
                </v-list>
              </div>
            </v-window-item>

            <!-- Tab: VFS Knowledge Bases (RAG 3.0) -->
            <v-window-item value="vfs_knowledge">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para associar Bases VFS (RAG 3.0).
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">Bases VFS (RAG 3.0)</h3>
                  <v-btn size="small" variant="text" color="primary" to="/vfs-knowledge" target="_blank">
                    Gerenciar Bases VFS <v-icon end>mdi-open-in-new</v-icon>
                  </v-btn>
                </div>

                <div class="d-flex align-center gap-2 mb-2">
                  <v-select
                    v-model="selectedVFSToAdd"
                    :items="availableVFSBases"
                    item-title="name"
                    item-value="id"
                    label="Vincular Base VFS"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="Selecione uma Base VFS..."
                    :disabled="availableVFSBases.length === 0"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <template v-slot:prepend>
                          <v-icon color="info">mdi-file-document-multiple-outline</v-icon>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                  <v-btn color="primary" @click="addVFSBase" :disabled="!selectedVFSToAdd" :loading="addingVFS">
                    <v-icon start>mdi-plus</v-icon>
                    Adicionar
                  </v-btn>
                </div>

                <v-list border rounded>
                   <v-list-subheader>Bases VFS Associadas ({{ agentVFSBases.length }})</v-list-subheader>
                   <v-list-item v-if="agentVFSBases.length === 0">
                     <v-list-item-title class="text-center py-4 text-medium-emphasis">
                       Nenhuma Base VFS associada
                     </v-list-item-title>
                   </v-list-item>
                   <v-list-item v-for="vfsBase in agentVFSBases" :key="vfsBase.id">
                     <template v-slot:prepend>
                       <v-icon color="info">mdi-file-document-multiple-outline</v-icon>
                     </template>
                     <v-list-item-title>{{ vfsBase.name }}</v-list-item-title>
                     <v-list-item-subtitle>
                       {{ vfsBase.file_count || 0 }} arquivo(s) · {{ vfsBase.description || '' }}
                     </v-list-item-subtitle>
                     <template v-slot:append>
                       <v-btn icon variant="text" color="error" size="small" @click="removeVFSBase(vfsBase)" :loading="removingVFS === vfsBase.id">
                         <v-icon>mdi-link-variant-off</v-icon>
                       </v-btn>
                     </template>
                   </v-list-item>
                </v-list>
              </div>
            </v-window-item>

            <!-- Tab: Interactivity (Status Updates) -->
            <v-window-item value="interactivity">
              <v-alert v-if="!editing" type="info" variant="tonal" class="mb-4">
                Salve o agente primeiro para configurar interatividade.
              </v-alert>

              <div v-else>
                <div class="d-flex justify-space-between align-center mb-4">
                  <h3 class="text-subtitle-1 font-weight-bold">
                    <v-icon size="20" class="mr-1">mdi-message-flash</v-icon>
                    Mensagens de Status em Tempo Real
                  </h3>
                </div>

                <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                  <template v-slot:prepend>
                    <v-icon>mdi-information</v-icon>
                  </template>
                  Configure mensagens automáticas enviadas ao usuário enquanto o agente está processando.
                  Ideal para jobs longos que envolvem consultas a colaboradores ou ferramentas externas.
                </v-alert>

                <v-card variant="outlined" class="mb-4">
                  <v-card-text class="d-flex align-center py-2">
                    <v-switch
                      v-model="formData.status_updates_enabled"
                      label="Ativar Atualizações de Status"
                      color="teal"
                      hide-details
                      density="compact"
                    ></v-switch>
                    <v-chip v-if="formData.status_updates_enabled" color="teal" size="small" variant="tonal" class="ml-4">
                      <v-icon start size="14">mdi-check-circle</v-icon>
                      Ativo
                    </v-chip>
                  </v-card-text>
                </v-card>

                <v-expand-transition>
                  <div v-if="formData.status_updates_enabled">
                    <v-row>
                      <v-col cols="12" md="4">
                        <v-text-field
                          v-model.number="formData.status_updates_config.initial_delay_seconds"
                          label="Atraso Inicial (s)"
                          type="number"
                          min="1"
                          max="60"
                          prepend-inner-icon="mdi-timer-sand"
                          hint="Tempo antes da 1ª mensagem"
                          persistent-hint
                        ></v-text-field>
                      </v-col>
                      <v-col cols="12" md="4">
                        <v-text-field
                          v-model.number="formData.status_updates_config.follow_up_interval_seconds"
                          label="Intervalo Follow-up (s)"
                          type="number"
                          min="5"
                          max="120"
                          prepend-inner-icon="mdi-timer-outline"
                          hint="Tempo entre mensagens seguintes"
                          persistent-hint
                        ></v-text-field>
                      </v-col>
                      <v-col cols="12" md="4">
                        <v-text-field
                          v-model.number="formData.status_updates_config.max_updates"
                          label="Máx. Atualizações"
                          type="number"
                          min="1"
                          max="10"
                          prepend-inner-icon="mdi-counter"
                          hint="Limite de mensagens intermediárias"
                          persistent-hint
                        ></v-text-field>
                      </v-col>
                    </v-row>

                    <v-row class="mt-2">
                      <v-col cols="12" md="6">
                        <v-textarea
                          v-model="formData.status_updates_config.initial_message"
                          label="Mensagem Inicial"
                          rows="2"
                          prepend-inner-icon="mdi-message-text-outline"
                          hint="Enviada após o atraso inicial"
                          persistent-hint
                        ></v-textarea>
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-textarea
                          v-model="formData.status_updates_config.follow_up_message"
                          label="Mensagem de Acompanhamento"
                          rows="2"
                          prepend-inner-icon="mdi-message-processing-outline"
                          hint="Enviada nos intervalos seguintes"
                          persistent-hint
                        ></v-textarea>
                      </v-col>
                    </v-row>

                    <v-card variant="tonal" color="teal" class="mt-4">
                      <v-card-title class="text-subtitle-2 py-2">
                        <v-icon start size="18">mdi-timeline-clock</v-icon>
                        Exemplo de Fluxo
                      </v-card-title>
                      <v-card-text class="pt-0 text-body-2">
                        <div class="d-flex align-center mb-1">
                          <v-icon size="14" class="mr-2">mdi-circle-small</v-icon>
                          <strong>{{ formData.status_updates_config.initial_delay_seconds }}s:</strong>&nbsp;
                          "{{ formData.status_updates_config.initial_message?.substring(0, 50) }}..."
                        </div>
                        <div class="d-flex align-center mb-1">
                          <v-icon size="14" class="mr-2">mdi-circle-small</v-icon>
                          <strong>{{ formData.status_updates_config.initial_delay_seconds + formData.status_updates_config.follow_up_interval_seconds }}s:</strong>&nbsp;
                          "{{ formData.status_updates_config.follow_up_message?.substring(0, 50) }}..."
                        </div>
                        <div class="d-flex align-center">
                          <v-icon size="14" class="mr-2">mdi-check-circle</v-icon>
                          <strong>Fim:</strong>&nbsp;Resposta final do agente
                        </div>
                      </v-card-text>
                    </v-card>
                  </div>
                </v-expand-transition>
              </div>
            </v-window-item>

            <!-- Tab: Prompt Preview -->
            <v-window-item value="prompt_preview">
              <div v-if="loadingPrompt" class="d-flex flex-column align-center justify-center py-12">
                <v-progress-circular indeterminate color="primary" size="64" width="6"></v-progress-circular>
                <p class="mt-4 text-medium-emphasis">Gerando panorama do prompt...</p>
              </div>
              
              <div v-else-if="promptPreview" class="prompt-preview-container">
                <div class="d-flex align-center justify-space-between mb-4">
                  <div class="d-flex align-center">
                    <v-chip color="primary" variant="flat" size="small" class="mr-2">
                      {{ promptPreview.model }}
                    </v-chip>
                    <span class="text-subtitle-1 font-weight-bold">Panorama de Construção do Prompt</span>
                  </div>
                  <div class="text-right">
                    <v-chip color="info" variant="outlined" size="small">
                      Tokens Est.: ~{{ promptPreview.total_estimated_tokens }}
                    </v-chip>
                    <v-btn icon="mdi-refresh" variant="text" size="small" @click="fetchPromptPreview" class="ml-2"></v-btn>
                  </div>
                </div>

                <v-alert
                  type="info"
                  variant="tonal"
                  class="mb-4"
                  density="compact"
                  icon="mdi-lightbulb-outline"
                >
                  Este panorama mostra as peças constantes do seu agente. Conteúdos de RAG e Memória são injetados dinamicamente em tempo de execução.
                </v-alert>

                <div class="prompt-sections">
                  <v-expansion-panels variant="accordion">
                    <v-expansion-panel
                      v-for="(section, idx) in promptPreview.sections"
                      :key="idx"
                      class="prompt-section-panel mb-2"
                    >
                      <v-expansion-panel-title class="py-2">
                        <div class="d-flex align-center w-100">
                          <v-icon :color="getSourceColor(section.source)" size="20" class="mr-2">
                            {{ getSourceIcon(section.source) }}
                          </v-icon>
                          <span class="font-weight-medium">{{ section.name }}</span>
                          <v-spacer></v-spacer>
                          <v-chip size="x-small" variant="tonal" :color="getSourceColor(section.source)" class="mr-4">
                            {{ section.source.toUpperCase() }}
                          </v-chip>
                          <span class="text-caption text-medium-emphasis">{{ section.estimated_tokens }} tokens</span>
                        </div>
                      </v-expansion-panel-title>
                      <v-expansion-panel-text>
                        <div class="prompt-content-box">
                          <pre class="prompt-text">{{ section.content }}</pre>
                        </div>
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>
                </div>
              </div>
            </v-window-item>

          </v-window>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="dialog = false" :disabled="saving">
            Cancelar
          </v-btn>
          <v-btn color="primary" @click="saveData" :loading="saving">
            <v-icon start>mdi-content-save</v-icon>
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Collaborators Dialog -->
    <v-dialog v-model="collabDialog" max-width="600">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-info">
          <v-icon class="mr-2" color="white">mdi-account-group</v-icon>
          <span class="text-white">Colaboradores de {{ selectedAgent?.name }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="collabDialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-alert type="info" variant="tonal" class="mb-4" density="compact">
            <template v-slot:prepend>
              <v-icon>mdi-information</v-icon>
            </template>
            <div class="d-flex flex-wrap gap-2">
              <v-chip color="success" size="small"><v-icon start size="14">mdi-check</v-icon>Prioridade</v-chip>
              <v-chip color="grey" size="small"><v-icon start size="14">mdi-minus</v-icon>Neutro</v-chip>
              <v-chip color="error" size="small"><v-icon start size="14">mdi-close</v-icon>Bloqueado</v-chip>
            </div>
          </v-alert>

          <div class="d-flex ga-2 mb-4">
            <v-btn size="small" variant="tonal" color="success" @click="setAllCollaborators('enabled')">
              <v-icon start size="16">mdi-check-all</v-icon>
              Priorizar Todos
            </v-btn>
            <v-btn size="small" variant="tonal" @click="setAllCollaborators('neutral')">
              <v-icon start size="16">mdi-minus-box-multiple</v-icon>
              Neutralizar Todos
            </v-btn>
            <v-btn size="small" variant="tonal" color="error" @click="setAllCollaborators('blocked')">
              <v-icon start size="16">mdi-close-box-multiple</v-icon>
              Bloquear Todos
            </v-btn>
          </div>

          <div v-if="otherAgents.length === 0" class="text-center py-8">
            <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-account-off</v-icon>
            <p class="text-medium-emphasis">Nenhum outro agente disponível</p>
          </div>
          
          <v-list v-else lines="two">
            <v-list-item v-for="agent in otherAgents" :key="agent.id" class="px-0">
              <template v-slot:prepend>
                <v-avatar :color="getLevelColor(agent.access_level)" size="40">
                  <v-icon color="white" size="20">mdi-robot</v-icon>
                </v-avatar>
              </template>
              
              <v-list-item-title class="font-weight-medium">{{ agent.name }}</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip :color="getLevelColor(agent.access_level)" size="x-small" label class="mr-1">
                  {{ getLevelLabel(agent.access_level) }}
                </v-chip>
              </v-list-item-subtitle>
              
              <template v-slot:append>
                <v-btn-toggle v-model="collaboratorStatuses[agent.id]" mandatory divided variant="outlined" density="compact">
                  <v-btn value="enabled" color="success" size="small">
                    <v-icon size="16">mdi-check</v-icon>
                  </v-btn>
                  <v-btn value="neutral" size="small">
                    <v-icon size="16">mdi-minus</v-icon>
                  </v-btn>
                  <v-btn value="blocked" color="error" size="small">
                    <v-icon size="16">mdi-close</v-icon>
                  </v-btn>
                </v-btn-toggle>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="collabDialog = false" :disabled="savingCollab">
            Cancelar
          </v-btn>
          <v-btn color="info" @click="saveCollaborators" :loading="savingCollab">
            <v-icon start>mdi-content-save</v-icon>
            Salvar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Agent Group Dialog -->
    <v-dialog v-model="groupDialog" max-width="500">
      <v-card>
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" color="secondary">mdi-folder</v-icon>
          <span>{{ groupForm.id ? 'Editar Pasta' : (groupForm.parent_id ? 'Nova Sub-pasta' : 'Nova Pasta') }}</span>
        </v-card-title>
        <v-card-text class="pa-5">
          <v-text-field v-model="groupForm.name" label="Nome da Pasta" variant="outlined" class="mb-4" required></v-text-field>
          <v-textarea v-model="groupForm.description" label="Descrição" variant="outlined" rows="2" class="mb-4" hide-details></v-textarea>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="groupDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveGroup" :loading="savingGroup" :disabled="!groupForm.name.trim()">Salvar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-error">
          <v-icon class="mr-2" color="white">mdi-alert-circle</v-icon>
          <span class="text-white">Confirmar Exclusão</span>
        </v-card-title>
        
        <v-card-text class="pa-6 text-center">
          <v-icon size="64" color="error" class="mb-4">mdi-delete-alert</v-icon>
          <p class="text-h6">Deseja excluir o agente?</p>
          <p class="text-body-2 text-medium-emphasis">
            <strong>{{ agentToDelete?.name }}</strong><br>
            Esta ação não pode ser desfeita.
          </p>
        </v-card-text>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="deleteDialog = false">Cancelar</v-btn>
          <v-btn color="error" @click="deleteAgent" :loading="deleting">
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
        <v-btn variant="text" @click="snackbar.show = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import axios from '@/plugins/axios'
import { agentGroupService } from '@/services/agentGroupService'

// State
const agents = ref([])
const loading = ref(false)
const search = ref('')

// Form dialog
const dialog = ref(false)
const activeTab = ref('general')
const saving = ref(false)
const editing = ref(false)
const formRef = ref(null)
const formValid = ref(false)
const formData = reactive({
  id: null,
  name: '',
  description: '',
  system_prompt: '',
  model: 'gpt-4o-mini',
  temperature: '0.7',
  max_tokens: '2000',
  is_active: true,
  access_level: 'normal',
  collaboration_enabled: true,
  vector_memory_enabled: false,
  is_orchestrator: false,
  is_planner: false,
  is_thinker: false,
  thinker_prompt: '',
  thinker_model: 'gpt-4o-mini',
  thinker_ids: [],
  thinker_restrictive: false,
  planner_prompt: '',
  planner_model: 'gpt-4o-mini',
  is_guardrail_active: false,
  guardrail_prompt: '',
  guardrail_model: 'gpt-4o-mini',
  emotional_profile_id: null,
  emotional_intensity: 'medium',
  emotional_intensity: 'medium',
  output_schema: null,
  input_schema: null,
  transition_input_schema: null,
  transition_output_schema: null,
  trigger_keywords: [],
  entity_memory_path: null,
  provider_id: null,
  config: {
    is_reasoning_model: false,
    reasoning_effort: 'medium',
    max_completion_tokens: 16384,
    short_term_memory_enabled: true,
    short_term_memory_ttl_hours: 24
  },
  status_updates_enabled: false,
  status_updates_config: {
    initial_delay_seconds: 5,
    follow_up_interval_seconds: 10,
    initial_message: 'Aguarde um momentinho, estou processando sua solicitação...',
    follow_up_message: 'Ainda estou trabalhando nisso, já estou quase terminando...',
    max_updates: 3
  }
})

// Reasoning model options
const reasoningEffortOptions = [
  { value: 'low', label: '🟢 Low — Rápido, menos profundo' },
  { value: 'medium', label: '🟡 Medium — Balanceado' },
  { value: 'high', label: '🔴 High — Máxima profundidade' }
]

// Output Schema Data
const outputSchemaJson = ref('')
const outputSchemaError = ref('')
const outputSchemaPreset = ref('default')
const parsedOutputSchema = computed(() => {
  if (!outputSchemaJson.value) return null
  try {
    return JSON.parse(outputSchemaJson.value)
  } catch {
    return null
  }
})

const OUTPUT_PRESETS = {
  default: {
    output: { type: 'string', description: 'Resposta para o cliente' }
  },
  whatsapp: {
    output: { type: 'string', description: 'Resposta para enviar no WhatsApp' },
    tag: { type: 'string', enum: ['coletando', 'solucao', 'resolvido', 'humano'], description: 'Estado do atendimento' }
  },
  sales: {
    output: { type: 'string', description: 'Resposta para o cliente' },
    interest_level: { type: 'string', enum: ['baixo', 'medio', 'alto'], description: 'Nível de interesse' },
    next_step: { type: 'string', enum: ['agendar_demo', 'enviar_proposta', 'follow_up', 'descartar'], description: 'Próximo passo' }
  }
}

const inputSubTab = ref('context')
const outputSubTab = ref('context')

// Input Schema Data (Context)
const inputSchemaJson = ref('')
const inputSchemaError = ref('')
const inputSchemaPreset = ref('custom')
const parsedInputSchema = computed(() => {
  if (!inputSchemaJson.value) return null
  try {
    return JSON.parse(inputSchemaJson.value)
  } catch {
    return null
  }
})

// Input Schema Data (Transition)
const transitionInputSchemaJson = ref('')
const transitionInputSchemaError = ref('')
const parsedTransitionInputSchema = computed(() => {
  if (!transitionInputSchemaJson.value) return null
  try {
    return JSON.parse(transitionInputSchemaJson.value)
  } catch {
    return null
  }
})

// Output Schema Data (Transition)
const transitionOutputSchemaJson = ref('')
const transitionOutputSchemaError = ref('')
const parsedTransitionOutputSchema = computed(() => {
  if (!transitionOutputSchemaJson.value) return null
  try {
    return JSON.parse(transitionOutputSchemaJson.value)
  } catch {
    return null
  }
})

const INPUT_PRESETS = {
  church: {
    nome_igreja: { type: 'string', description: 'Nome da igreja' },
    nome_usuario: { type: 'string', description: 'Nome do membro' },
    telefone: { type: 'string', description: 'Telefone do membro', optional: true },
    cargo: { type: 'string', description: 'Cargo na igreja', optional: true }
  },
  whatsapp: {
    nome: { type: 'string', description: 'Nome do contato' },
    telefone: { type: 'string', description: 'Número do WhatsApp' },
    plano: { type: 'string', enum: ['basico', 'premium'], description: 'Plano do cliente', optional: true }
  },
  student: {
    nome_aluno: { type: 'string', description: 'Nome do aluno' },
    turma: { type: 'string', description: 'Turma do aluno' },
    instituicao: { type: 'string', description: 'Nome da instituição', optional: true }
  }
}

// Resilience Data
const resilienceData = reactive({
  max_retries: 3,
  retry_delay_seconds: 1.0,
  retry_exponential_backoff: true,
  timeout_seconds: 120,
  fallback_enabled: false,
  fallback_model: 'gpt-4o-mini',
  fallback_temperature: 0.7,
  human_approval_enabled: false,
  human_approval_timeout_seconds: 300,
  hitl_user_approval_enabled: false,
  hitl_admin_approval_enabled: false,
  hitl_admin_contact: '',
  hitl_message_template: '',
  interrupt_before_nodes: [],
  verbose_logging: false
})

// Knowledge Base Data
const allDocuments = ref([])
const agentDocuments = ref([])
const selectedDocToAdd = ref(null)

// MCP Data
const allMcps = ref([])
const agentMcps = ref([])
const selectedMcpToAdd = ref(null)
const addingMcp = ref(false)
const removingMcp = ref(null)
const addingDoc = ref(false)

// MCP Groups Data
const allMcpGroups = ref([])
const agentMcpGroups = ref([])
const selectedMcpGroupToAdd = ref(null)
const addingMcpGroup = ref(false)
const removingMcpGroup = ref(null)

// Information Bases Data
const allBases = ref([])
const agentBases = ref([])
const selectedBaseToAdd = ref(null)
const addingBase = ref(false)
const removingBase = ref(null)

// Skills Data
const allSkills = ref([])
const agentSkills = ref([])
const selectedSkillToAdd = ref(null)
const addingSkill = ref(false)
const removingSkill = ref(null)

// VFS Knowledge Bases Data (RAG 3.0)
const allVFSBases = ref([])
const agentVFSBases = ref([])
const selectedVFSToAdd = ref(null)
const addingVFS = ref(false)
const removingVFS = ref(null)

// Collaborators dialog
const collabDialog = ref(false)
const selectedAgent = ref(null)
const collaboratorStatuses = ref({})
const savingCollab = ref(false)

// Agent Groups / Folders
const agentGroups = ref([])
const customProviders = ref([])
const currentFolder = ref(null)
const breadcrumb = ref([])
const groupDialog = ref(false)
const groupForm = ref({ id: null, name: '', description: '', parent_id: null })
const savingGroup = ref(false)

// Emotional Profiles
const allEmotionalProfiles = ref([])
const pastoralProfiles = computed(() => 
  allEmotionalProfiles.value.filter(p => p.category === 'pastoral')
)
const professionalProfiles = computed(() => 
  allEmotionalProfiles.value.filter(p => p.category === 'professional' || p.category === 'neutral')
)
const selectedEmotionalProfile = computed(() => 
  allEmotionalProfiles.value.find(p => p.id === formData.emotional_profile_id)
)

// Delete dialog
const deleteDialog = ref(false)
const agentToDelete = ref(null)
const deleting = ref(false)

// Prompt Preview State
const loadingPrompt = ref(false)
const promptPreview = ref(null)

// Snackbar
const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

// Options
const accessLevels = [
  { value: 'minimum', label: '🔵 Mínimo - Acesso básico' },
  { value: 'normal', label: '🟢 Normal - Usuário padrão' },
  { value: 'pro', label: '🟡 Pro - Recursos avançados' },
  { value: 'premium', label: '🔴 Premium - Acesso total' }
]

const loadingModels = ref(false)
const allModels = ref([])

const activeProvider = ref('openai')
const providerOptions = computed(() => {
  const options = [
    { title: '🟢 OpenAI', value: 'openai' },
    { title: '🔵 OpenRouter', value: 'openrouter' }
  ]
  
  customProviders.value.forEach(p => {
    options.push({
      title: `🌐 ${p.name}`,
      value: p.id,
      isCustom: true,
      default_model: p.default_model
    })
  })
  
  return options
})

const modelOptions = computed(() => {
  return allModels.value
    .filter(m => m.provider === activeProvider.value)
    .map(m => ({
      title: m.name,
      value: m.id,
      provider: m.provider,
      context_length: m.context_length
    }))
})

function formatContextLength(length) {
  if (!length) return ''
  if (length >= 1000000) return (length / 1000000).toFixed(1) + 'M'
  if (length >= 1000) return (length / 1000).toFixed(0) + 'K'
  return length.toString()
}

const headers = [
  { title: 'Agente', key: 'name', sortable: true },
  { title: 'Nível', key: 'access_level', sortable: true },
  { title: 'Modelo', key: 'model', sortable: true },
  { title: 'Status', key: 'is_active', sortable: true },
  { title: 'Recursos', key: 'collaboration_enabled', sortable: false, align: 'center' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '180px' }
]

// Duplicate agent state
const duplicatingAgent = ref(null)

// Computed
const filteredAgents = computed(() => {
  if (!search.value) return agents.value
  const s = search.value.toLowerCase()
  return agents.value.filter(a => 
    a.name?.toLowerCase().includes(s) || 
    a.description?.toLowerCase().includes(s)
  )
})

const activeCount = computed(() => agents.value.filter(a => a.is_active).length)
const premiumCount = computed(() => agents.value.filter(a => ['pro', 'premium'].includes(a.access_level)).length)
const collabCount = computed(() => agents.value.filter(a => a.collaboration_enabled).length)

const otherAgents = computed(() => {
  if (!selectedAgent.value) return []
  return agents.value.filter(a => a.id !== selectedAgent.value.id)
})

const availableThinkers = computed(() => {
  return agents.value
    .filter(a => a.id !== formData.id)
    .map(a => ({
      title: a.name,
      value: a.id
    }))
})

const globalDocs = computed(() => agentDocuments.value.filter(d => d.is_global))
const agentDocs = computed(() => agentDocuments.value.filter(d => !d.is_global))
const availableDocs = computed(() => {
  // Docs that are not global and not already associated
  const assocIds = new Set(agentDocuments.value.map(d => d.id))
  return allDocuments.value.filter(d => !d.is_global && !assocIds.has(d.id))
})

// Available MCPs (not already associated with this agent)
const availableMcps = computed(() => {
  const assocIds = new Set(agentMcps.value.map(m => m.id))
  return allMcps.value.filter(m => !assocIds.has(m.id) && m.is_active)
})

// Available MCP Groups (not already associated with this agent)
const availableMcpGroups = computed(() => {
  const assocIds = new Set(agentMcpGroups.value.map(g => g.id))
  return allMcpGroups.value.filter(g => !assocIds.has(g.id))
})

// Available Skills (not already associated with this agent)
const availableSkills = computed(() => {
  const assocIds = new Set(agentSkills.value.map(s => s.id))
  return allSkills.value.filter(s => !assocIds.has(s.id) && s.is_active)
})

// Available Information Bases (not already associated)
const availableBases = computed(() => {
  const assocIds = new Set(agentBases.value.map(b => b.id))
  return allBases.value.filter(b => !assocIds.has(b.id) && b.is_active)
})

const availableVFSBases = computed(() => {
  const assocIds = new Set(agentVFSBases.value.map(b => b.id))
  return allVFSBases.value.filter(b => !assocIds.has(b.id) && b.is_active)
})

// Helpers
function getLevelColor(level) {
  const colors = { minimum: 'info', normal: 'success', pro: 'warning', premium: 'error' }
  return colors[level] || 'grey'
}

function getLevelLabel(level) {
  const labels = { minimum: 'Mínimo', normal: 'Normal', pro: 'Pro', premium: 'Premium' }
  return labels[level] || level
}

function getLevelIcon(level) {
  const icons = { minimum: 'mdi-circle-outline', normal: 'mdi-account', pro: 'mdi-star', premium: 'mdi-crown' }
  return icons[level] || 'mdi-circle'
}

function getProtocolColor(protocol) {
  const colors = { http: 'blue', sse: 'purple', mcp: 'teal', websocket: 'orange', stdio: 'grey' }
  return colors[(protocol || 'http').toLowerCase()] || 'grey'
}

function getProtocolIcon(protocol) {
  const icons = { http: 'mdi-web', sse: 'mdi-broadcast', mcp: 'mdi-connection', websocket: 'mdi-swap-horizontal', stdio: 'mdi-console' }
  return icons[(protocol || 'http').toLowerCase()] || 'mdi-web'
}

function showSnackbar(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function getSourceColor(source) {
  const colors = {
    config: 'blue',
    skill: 'amber',
    tools: 'teal',
    system: 'grey',
    rag: 'indigo',
    info_base: 'cyan',
    vector_memory: 'deep-purple',
    orchestrator: 'orange'
  }
  return colors[source] || 'grey'
}

function getSourceIcon(source) {
  const icons = {
    config: 'mdi-cog',
    skill: 'mdi-star',
    tools: 'mdi-tools',
    system: 'mdi-application-cog',
    rag: 'mdi-file-document',
    info_base: 'mdi-database',
    vector_memory: 'mdi-brain',
    orchestrator: 'mdi-account-group'
  }
  return icons[source] || 'mdi-text'
}

async function fetchPromptPreview() {
  if (!formData.id) return
  
  loadingPrompt.value = true
  try {
    const response = await axios.get(`/agents/${formData.id}/prompt-preview`)
    promptPreview.value = response.data
  } catch (error) {
    console.error('Error fetching prompt preview:', error)
    showSnackbar('Erro ao carregar panorama do prompt', 'error')
  } finally {
    loadingPrompt.value = false
  }
}

watch(activeTab, (newTab) => {
  if (newTab === 'prompt_preview') {
    fetchPromptPreview()
  }
})

function resetForm() {
  Object.assign(formData, {
    id: null,
    name: '',
    description: '',
    system_prompt: '',
    model: 'gpt-4o-mini',
    temperature: '0.7',
    max_tokens: '2000',
    is_active: true,
    access_level: 'normal',
    collaboration_enabled: true,
    vector_memory_enabled: false,
    is_orchestrator: false,
    is_planner: false,
    is_thinker: false,
    thinker_prompt: '',
    thinker_model: 'gpt-4o-mini',
    thinker_ids: [],
    thinker_restrictive: false,
    planner_prompt: '',
    planner_model: 'gpt-4o-mini',
    is_guardrail_active: false,
    guardrail_prompt: '',
    guardrail_model: 'gpt-4o-mini',
    emotional_profile_id: null,
    emotional_intensity: 'medium',
    output_schema: null,
    input_schema: null,
    transition_input_schema: null,
    transition_output_schema: null,
    trigger_keywords: [],
    entity_memory_path: null,
    config: {
      is_reasoning_model: false,
      reasoning_effort: 'medium',
      max_completion_tokens: 16384,
      short_term_memory_enabled: true,
      short_term_memory_ttl_hours: 24
    },
    provider_id: null
  })
  outputSchemaJson.value = ''
  outputSchemaError.value = ''
  outputSchemaPreset.value = 'default'
  transitionOutputSchemaJson.value = ''
  transitionOutputSchemaError.value = ''
  
  inputSchemaJson.value = ''
  inputSchemaError.value = ''
  inputSchemaPreset.value = 'custom'
  transitionInputSchemaJson.value = ''
  transitionInputSchemaError.value = ''
}

// Output Schema helpers
function validateOutputSchema(value) {
  if (!value) {
    outputSchemaError.value = ''
    return
  }
  try {
    JSON.parse(value)
    outputSchemaError.value = ''
  } catch (e) {
    outputSchemaError.value = 'JSON inválido: ' + e.message
  }
}

function applyOutputPreset(preset) {
  if (preset === 'custom') {
    return
  }
  const schema = OUTPUT_PRESETS[preset]
  if (schema) {
    outputSchemaJson.value = JSON.stringify(schema, null, 2)
    outputSchemaError.value = ''
  }
}

function validateInputSchema(value) {
  if (!value) {
    inputSchemaError.value = ''
    return
  }
  try {
    JSON.parse(value)
    inputSchemaError.value = ''
  } catch (e) {
    inputSchemaError.value = 'JSON inválido: ' + e.message
  }
}

function applyInputPreset(preset) {
  if (preset === 'custom') {
    return
  }
  const schema = INPUT_PRESETS[preset]
  if (schema) {
    inputSchemaJson.value = JSON.stringify(schema, null, 2)
    inputSchemaError.value = ''
  }
}

// Transition Schema validations
function validateTransitionInputSchema(value) {
  if (!value) {
    transitionInputSchemaError.value = ''
    return
  }
  try {
    JSON.parse(value)
    transitionInputSchemaError.value = ''
  } catch (e) {
    transitionInputSchemaError.value = 'JSON inválido: ' + e.message
  }
}

function validateTransitionOutputSchema(value) {
  if (!value) {
    transitionOutputSchemaError.value = ''
    return
  }
  try {
    JSON.parse(value)
    transitionOutputSchemaError.value = ''
  } catch (e) {
    transitionOutputSchemaError.value = 'JSON inválido: ' + e.message
  }
}

// API calls
async function fetchModels() {
  loadingModels.value = true
  try {
    const response = await axios.get('/models/available')
    allModels.value = response.data.models || []
  } catch (error) {
    console.error('Error fetching models:', error)
    // Fallback to hardcoded OpenAI models if API fails
    allModels.value = [
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', context_length: 128000 },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'openai', context_length: 128000 },
      { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', provider: 'openai', context_length: 128000 },
      { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', provider: 'openai', context_length: 16385 }
    ]
  } finally {
    loadingModels.value = false
  }
}

async function fetchCustomProviders() {
  try {
    const response = await axios.get('/ai-providers')
    customProviders.value = response.data.providers || []
  } catch (error) {
    console.error('Error fetching custom providers:', error)
  }
}

async function fetchAgents() {
  loading.value = true
  try {
    const response = await axios.get('/agents', { params: { group_id: currentFolder.value?.id || undefined } })
    agents.value = response.data.agents || []
  } catch (error) {
    console.error('Error fetching agents:', error)
    showSnackbar('Erro ao carregar agentes', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchDocuments() {
  try {
    const response = await axios.get('/documents')
    allDocuments.value = response.data.documents || []
  } catch (error) {
    console.error('Error fetching documents:', error)
  }
}

async function fetchAgentConfig(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/config`)
    Object.assign(resilienceData, response.data)
  } catch (error) {
    console.error('Error fetching config:', error)
  }
}

async function fetchAllMcps() {
  try {
    const response = await axios.get('/mcp')
    allMcps.value = response.data.mcps || []
  } catch (error) {
    console.error('Error fetching MCPs:', error)
  }
}

async function fetchAllMcpGroups() {
  try {
    const response = await axios.get('/mcp-groups')
    allMcpGroups.value = response.data || []
  } catch (error) {
    console.error('Error fetching MCP Groups:', error)
  }
}

async function fetchEmotionalProfiles() {
  try {
    const response = await axios.get('/emotional-profiles')
    allEmotionalProfiles.value = response.data.profiles || []
  } catch (error) {
    console.error('Error fetching emotional profiles:', error)
  }
}

async function fetchAgentMcps(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/mcps`)
    agentMcps.value = response.data.mcps || []
  } catch (error) {
    console.error('Error fetching agent MCPs:', error)
  }
}

async function fetchAgentMcpGroups(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/mcp-groups`)
    agentMcpGroups.value = response.data.mcp_groups || []
  } catch (error) {
    console.error('Error fetching agent MCP Groups:', error)
  }
}

async function fetchAllSkills() {
  try {
    const response = await axios.get('/skills/')
    allSkills.value = response.data.skills || []
  } catch (error) {
    console.error('Error fetching skills:', error)
  }
}

async function fetchAllBases() {
  try {
    const response = await axios.get('/information-bases')
    allBases.value = response.data.information_bases || []
  } catch (error) {
    console.error('Error fetching information bases:', error)
  }
}

async function fetchAgentBases(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/information-bases`)
    agentBases.value = response.data.information_bases || []
  } catch (error) {
    console.error('Error fetching agent information bases:', error)
  }
}

async function fetchAgentSkills(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/skills`)
    agentSkills.value = response.data.skills || []
  } catch (error) {
    console.error('Error fetching agent skills:', error)
  }
}

async function fetchAgentDocuments(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/documents`)
    agentDocuments.value = response.data.documents || []
  } catch (error) {
    console.error('Error fetching agent documents:', error)
  }
}

async function openDialog(agent = null) {
  activeTab.value = 'general'
  
  if (agent) {
    editing.value = true
    
    // Fetch full agent data (list doesn't include system_prompt, model, etc)
    try {
      const response = await axios.get(`/agents/${agent.id}`)
      const fullAgent = response.data
      
      Object.assign(formData, {
        id: fullAgent.id,
        name: fullAgent.name,
        description: fullAgent.description || '',
        system_prompt: fullAgent.system_prompt || '',
        model: fullAgent.model || 'gpt-4o-mini',
        temperature: fullAgent.temperature || '0.7',
        max_tokens: fullAgent.max_tokens || '2000',
        is_active: fullAgent.is_active ?? true,
        access_level: fullAgent.access_level || 'normal',
        collaboration_enabled: fullAgent.collaboration_enabled ?? true,
        vector_memory_enabled: fullAgent.vector_memory_enabled ?? false,
        is_orchestrator: fullAgent.is_orchestrator ?? false,
        is_planner: fullAgent.is_planner ?? false,
        is_thinker: fullAgent.is_thinker ?? false,
        thinker_prompt: fullAgent.thinker_prompt || '',
        thinker_model: fullAgent.thinker_model || 'gpt-4o-mini',
        thinker_ids: fullAgent.thinker_ids || [],
        thinker_restrictive: fullAgent.thinker_restrictive ?? false,
        planner_prompt: fullAgent.planner_prompt || '',
        planner_model: fullAgent.planner_model || 'gpt-4o-mini',
        is_guardrail_active: fullAgent.is_guardrail_active ?? false,
        guardrail_prompt: fullAgent.guardrail_prompt || '',
        guardrail_model: fullAgent.guardrail_model || 'gpt-4o-mini',
        emotional_profile_id: fullAgent.emotional_profile?.id || null,
        emotional_intensity: fullAgent.emotional_intensity || 'medium',
        output_schema: fullAgent.output_schema || null,
        input_schema: fullAgent.input_schema || null,
        transition_input_schema: fullAgent.transition_input_schema || null,
        transition_output_schema: fullAgent.transition_output_schema || null,
        trigger_keywords: fullAgent.trigger_keywords || [],
        entity_memory_path: fullAgent.entity_memory_path || null,
        provider_id: fullAgent.provider_id || null,
        config: {
          is_reasoning_model: fullAgent.config?.is_reasoning_model ?? false,
          reasoning_effort: fullAgent.config?.reasoning_effort || 'medium',
          max_completion_tokens: fullAgent.config?.max_completion_tokens || 16384,
          short_term_memory_enabled: fullAgent.config?.short_term_memory_enabled ?? true,
          short_term_memory_ttl_hours: fullAgent.config?.short_term_memory_ttl_hours || 24,
          ...(fullAgent.config || {})
        },
        status_updates_enabled: fullAgent.status_updates_enabled ?? false,
        status_updates_config: {
          initial_delay_seconds: fullAgent.status_updates_config?.initial_delay_seconds ?? 5,
          follow_up_interval_seconds: fullAgent.status_updates_config?.follow_up_interval_seconds ?? 10,
          initial_message: fullAgent.status_updates_config?.initial_message || 'Aguarde um momentinho, estou processando sua solicitação...',
          follow_up_message: fullAgent.status_updates_config?.follow_up_message || 'Ainda estou trabalhando nisso, já estou quase terminando...',
          max_updates: fullAgent.status_updates_config?.max_updates ?? 3
        }
      })
      
      const foundModel = allModels.value.find(m => m.id === fullAgent.model)
      
      if (fullAgent.provider_id) {
        activeProvider.value = fullAgent.provider_id
      } else if (foundModel) {
        activeProvider.value = foundModel.provider
      } else if (fullAgent.model?.includes('/')) {
        activeProvider.value = 'openrouter'
      } else if (['sambanova', 'groq'].includes(fullAgent.model)) {
        activeProvider.value = 'openrouter'
      } else {
        activeProvider.value = 'openai'
      }
      
      // Load output schema into editor (Context)
      if (fullAgent.output_schema) {
        outputSchemaJson.value = JSON.stringify(fullAgent.output_schema, null, 2)
        outputSchemaPreset.value = 'custom'
      } else {
        outputSchemaJson.value = ''
        outputSchemaPreset.value = 'default'
      }

      // Load output schema into editor (Transition)
      if (fullAgent.transition_output_schema) {
        transitionOutputSchemaJson.value = JSON.stringify(fullAgent.transition_output_schema, null, 2)
      } else {
        transitionOutputSchemaJson.value = ''
      }
      
      // Load input schema into editor (Context)
      if (fullAgent.input_schema) {
        inputSchemaJson.value = JSON.stringify(fullAgent.input_schema, null, 2)
        inputSchemaPreset.value = 'custom'
      } else {
        inputSchemaJson.value = ''
        inputSchemaPreset.value = 'custom'
      }

      // Load input schema into editor (Transition)
      if (fullAgent.transition_input_schema) {
        transitionInputSchemaJson.value = JSON.stringify(fullAgent.transition_input_schema, null, 2)
      } else {
        transitionInputSchemaJson.value = ''
      }
      
      // Fetch related data
      await Promise.all([
        fetchAgentConfig(fullAgent.id),
        fetchAgentDocuments(fullAgent.id),
        fetchAgentMcps(fullAgent.id),
        fetchAgentMcpGroups(fullAgent.id),
        fetchAgentSkills(fullAgent.id),
        fetchDocuments(),
        fetchAllMcps(),
        fetchAllMcpGroups(),
        fetchAllSkills(),
        fetchAllBases(),
        fetchAgentBases(fullAgent.id),
        fetchAllVFSBases(),
        fetchAgentVFSBases(fullAgent.id),
        fetchEmotionalProfiles(),
        fetchCustomProviders()
      ])
    } catch (error) {
      console.error('Error fetching agent details:', error)
      showSnackbar('Erro ao carregar dados do agente', 'error')
      return
    }
  } else {
    editing.value = false
    resetForm()
  }
  dialog.value = true
}

watch(activeProvider, (newValue) => {
  const custom = providerOptions.value.find(p => p.value === newValue && p.isCustom)
  if (custom) {
    formData.provider_id = custom.value
    // Auto-preencher modelo se estiver vazio e o provedor tiver um default
    if (!formData.model && custom.default_model) {
      formData.model = custom.default_model
    }
  } else {
    formData.provider_id = null
  }
})

async function saveData() {
  saving.value = true
  try {
    // Prepare payload
    const payload = { ...formData }
    delete payload.id
    
    // Include schemas from JSON editors
    if (parsedOutputSchema.value) {
      payload.output_schema = parsedOutputSchema.value
    } else if (!outputSchemaJson.value) {
      payload.output_schema = null
    }

    if (parsedTransitionOutputSchema.value) {
      payload.transition_output_schema = parsedTransitionOutputSchema.value
    } else if (!transitionOutputSchemaJson.value) {
      payload.transition_output_schema = null
    }

    if (parsedInputSchema.value) {
      payload.input_schema = parsedInputSchema.value
    } else if (!inputSchemaJson.value) {
      payload.input_schema = null
    }

    if (parsedTransitionInputSchema.value) {
      payload.transition_input_schema = parsedTransitionInputSchema.value
    } else if (!transitionInputSchemaJson.value) {
      payload.transition_input_schema = null
    }

    let agentId = formData.id
    
    // Save Agent
    if (editing.value) {
      await axios.put(`/agents/${formData.id}`, payload)
    } else {
      const response = await axios.post('/agents', payload)
      agentId = response.data.id
      editing.value = true
      formData.id = agentId
    }
    
    // Save Resilience Config (if available) - This is a separate table/endpoint
    if (activeTab.value === 'resilience' || editing.value) {
      // Only save if we have data
      if (Object.keys(resilienceData).length > 0) {
        await axios.put(`/agents/${agentId}/config`, resilienceData)
      }
    }
    
    showSnackbar('Agente salvo com sucesso!')
    await fetchAgents()
    dialog.value = false
    
  } catch (error) {
    console.error('Error saving agent:', error)
    const errorMsg = error.response?.data?.detail || error.message
    showSnackbar('Erro ao salvar agente: ' + errorMsg, 'error')
  } finally {
    saving.value = false
  }
}

async function addDocument() {
  if (!selectedDocToAdd.value) return
  
  addingDoc.value = true
  try {
    await axios.post(`/agents/${formData.id}/documents/${selectedDocToAdd.value}`)
    await fetchAgentDocuments(formData.id)
    selectedDocToAdd.value = null
    showSnackbar('Documento adicionado!')
  } catch (error) {
    console.error('Error adding document:', error)
    showSnackbar('Erro ao adicionar documento', 'error')
  } finally {
    addingDoc.value = false
  }
}

async function removeDocument(doc) {
  try {
    await axios.delete(`/agents/${formData.id}/documents/${doc.id}`)
    await fetchAgentDocuments(formData.id)
    showSnackbar('Documento removido!')
  } catch (error) {
    console.error('Error removing document:', error)
    showSnackbar('Erro ao remover documento', 'error')
  }
}

async function addMcp() {
  if (!selectedMcpToAdd.value) return
  
  addingMcp.value = true
  try {
    await axios.post(`/agents/${formData.id}/mcps/${selectedMcpToAdd.value}`)
    await fetchAgentMcps(formData.id)
    selectedMcpToAdd.value = null
    showSnackbar('MCP adicionado com sucesso!')
  } catch (error) {
    console.error('Error adding MCP:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao adicionar MCP', 'error')
  } finally {
    addingMcp.value = false
  }
}

async function removeMcp(mcp) {
  removingMcp.value = mcp.id
  try {
    await axios.delete(`/agents/${formData.id}/mcps/${mcp.id}`)
    await fetchAgentMcps(formData.id)
    showSnackbar('MCP removido!')
  } catch (error) {
    console.error('Error removing MCP:', error)
    showSnackbar('Erro ao remover MCP', 'error')
  } finally {
    removingMcp.value = null
  }
}

async function addMcpGroup() {
  if (!selectedMcpGroupToAdd.value) return
  
  addingMcpGroup.value = true
  try {
    await axios.post(`/agents/${formData.id}/mcp-groups/${selectedMcpGroupToAdd.value}`)
    await fetchAgentMcpGroups(formData.id)
    selectedMcpGroupToAdd.value = null
    showSnackbar('Grupo de MCP adicionado com sucesso!')
  } catch (error) {
    console.error('Error adding MCP Group:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao adicionar Grupo', 'error')
  } finally {
    addingMcpGroup.value = false
  }
}

async function removeMcpGroup(group) {
  removingMcpGroup.value = group.id
  try {
    await axios.delete(`/agents/${formData.id}/mcp-groups/${group.id}`)
    await fetchAgentMcpGroups(formData.id)
    showSnackbar('Grupo de MCP removido!')
  } catch (error) {
    console.error('Error removing MCP Group:', error)
    showSnackbar('Erro ao remover Grupo', 'error')
  } finally {
    removingMcpGroup.value = null
  }
}

async function addSkill() {
  if (!selectedSkillToAdd.value) return
  
  addingSkill.value = true
  try {
    await axios.post(`/agents/${formData.id}/skills/${selectedSkillToAdd.value}`)
    await fetchAgentSkills(formData.id)
    selectedSkillToAdd.value = null
    showSnackbar('Skill adicionada com sucesso!')
  } catch (error) {
    console.error('Error adding skill:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao adicionar skill', 'error')
  } finally {
    addingSkill.value = false
  }
}

async function removeSkill(skill) {
  removingSkill.value = skill.id
  try {
    await axios.delete(`/agents/${formData.id}/skills/${skill.id}`)
    await fetchAgentSkills(formData.id)
    showSnackbar('Skill removida!')
  } catch (error) {
    console.error('Error removing skill:', error)
    showSnackbar('Erro ao remover skill', 'error')
  } finally {
    removingSkill.value = null
  }
}

async function addBase() {
  if (!selectedBaseToAdd.value) return
  
  addingBase.value = true
  try {
    await axios.post(`/agents/${formData.id}/information-bases/${selectedBaseToAdd.value}`)
    await fetchAgentBases(formData.id)
    selectedBaseToAdd.value = null
    showSnackbar('Base adicionada com sucesso!')
  } catch (error) {
    console.error('Error adding base:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao adicionar base', 'error')
  } finally {
    addingBase.value = false
  }
}

async function removeBase(base) {
  removingBase.value = base.id
  try {
    await axios.delete(`/agents/${formData.id}/information-bases/${base.id}`)
    await fetchAgentBases(formData.id)
    showSnackbar('Base removida!')
  } catch (error) {
    console.error('Error removing base:', error)
    showSnackbar('Erro ao remover base', 'error')
  } finally {
    removingBase.value = null
  }
}

async function fetchAllVFSBases() {
  try {
    const response = await axios.get('/vfs-knowledge-bases')
    allVFSBases.value = response.data || []
  } catch (error) {
    console.error('Error fetching VFS knowledge bases:', error)
  }
}

async function fetchAgentVFSBases(agentId) {
  try {
    const response = await axios.get(`/agents/${agentId}/vfs-knowledge-bases`)
    agentVFSBases.value = response.data.vfs_knowledge_bases || []
  } catch (error) {
    console.error('Error fetching agent VFS bases:', error)
  }
}

async function addVFSBase() {
  if (!selectedVFSToAdd.value) return
  addingVFS.value = true
  try {
    await axios.post(`/agents/${formData.id}/vfs-knowledge-bases/${selectedVFSToAdd.value}`)
    await fetchAgentVFSBases(formData.id)
    selectedVFSToAdd.value = null
    showSnackbar('Base VFS adicionada!')
  } catch (error) {
    console.error('Error adding VFS base:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao adicionar base VFS', 'error')
  } finally {
    addingVFS.value = false
  }
}

async function removeVFSBase(vfsBase) {
  removingVFS.value = vfsBase.id
  try {
    await axios.delete(`/agents/${formData.id}/vfs-knowledge-bases/${vfsBase.id}`)
    await fetchAgentVFSBases(formData.id)
    showSnackbar('Base VFS removida!')
  } catch (error) {
    console.error('Error removing VFS base:', error)
    showSnackbar('Erro ao remover base VFS', 'error')
  } finally {
    removingVFS.value = null
  }
}

function selectEmotionalProfile(profile) {
  formData.emotional_profile_id = profile.id
}

function clearEmotionalProfile() {
  formData.emotional_profile_id = null
  formData.emotional_intensity = 'medium'
}

async function duplicateAgent(agent) {
  duplicatingAgent.value = agent.id
  try {
    // Fetch full agent data
    const response = await axios.get(`/agents/${agent.id}`)
    const fullAgent = response.data

    // Build payload without id, appending (Cópia) to name
    const payload = {
      name: fullAgent.name + ' (Cópia)',
      description: fullAgent.description || '',
      system_prompt: fullAgent.system_prompt || '',
      model: fullAgent.model || 'gpt-4o-mini',
      temperature: fullAgent.temperature || '0.7',
      max_tokens: fullAgent.max_tokens || '2000',
      is_active: false,
      access_level: fullAgent.access_level || 'normal',
      collaboration_enabled: fullAgent.collaboration_enabled ?? true,
      vector_memory_enabled: fullAgent.vector_memory_enabled ?? false,
      is_orchestrator: fullAgent.is_orchestrator ?? false,
      is_planner: fullAgent.is_planner ?? false,
      emotional_profile_id: fullAgent.emotional_profile?.id || null,
      emotional_intensity: fullAgent.emotional_intensity || 'medium',
      output_schema: fullAgent.output_schema || null,
      input_schema: fullAgent.input_schema || null,
      transition_input_schema: fullAgent.transition_input_schema || null,
      transition_output_schema: fullAgent.transition_output_schema || null,
      trigger_keywords: fullAgent.trigger_keywords || [],
      entity_memory_path: fullAgent.entity_memory_path || null,
      config: fullAgent.config || {}
    }

    // Create the duplicated agent
    const createResp = await axios.post('/agents', payload)
    const newAgentId = createResp.data.id

    // Duplicate associated skills
    try {
      const skillsResp = await axios.get(`/agents/${agent.id}/skills`)
      const skills = skillsResp.data.skills || []
      for (const skill of skills) {
        await axios.post(`/agents/${newAgentId}/skills/${skill.id}`)
      }
    } catch (e) { console.warn('Could not duplicate skills:', e) }

    // Duplicate associated MCPs
    try {
      const mcpsResp = await axios.get(`/agents/${agent.id}/mcps`)
      const mcpsList = mcpsResp.data.mcps || []
      for (const mcp of mcpsList) {
        await axios.post(`/agents/${newAgentId}/mcps/${mcp.id}`)
      }
    } catch (e) { console.warn('Could not duplicate MCPs:', e) }

    // Duplicate associated MCP Groups
    try {
      const groupsResp = await axios.get(`/agents/${agent.id}/mcp-groups`)
      const groups = groupsResp.data.mcp_groups || []
      for (const group of groups) {
        await axios.post(`/agents/${newAgentId}/mcp-groups/${group.id}`)
      }
    } catch (e) { console.warn('Could not duplicate MCP Groups:', e) }

    // Duplicate associated documents
    try {
      const docsResp = await axios.get(`/agents/${agent.id}/documents`)
      const docs = (docsResp.data.documents || []).filter(d => !d.is_global)
      for (const doc of docs) {
        await axios.post(`/agents/${newAgentId}/documents/${doc.id}`)
      }
    } catch (e) { console.warn('Could not duplicate documents:', e) }

    // Duplicate associated Information Bases
    try {
      const basesResp = await axios.get(`/agents/${agent.id}/information-bases`)
      const bases = basesResp.data.information_bases || []
      for (const base of bases) {
        await axios.post(`/agents/${newAgentId}/information-bases/${base.id}`)
      }
    } catch (e) { console.warn('Could not duplicate information bases:', e) }

    // Duplicate resilience config
    try {
      const configResp = await axios.get(`/agents/${agent.id}/config`)
      if (configResp.data && Object.keys(configResp.data).length > 0) {
        await axios.put(`/agents/${newAgentId}/config`, configResp.data)
      }
    } catch (e) { console.warn('Could not duplicate config:', e) }

    showSnackbar('Agente duplicado com sucesso!')
    await fetchAgents()
  } catch (error) {
    console.error('Error duplicating agent:', error)
    showSnackbar('Erro ao duplicar agente: ' + (error.response?.data?.detail || error.message), 'error')
  } finally {
    duplicatingAgent.value = null
  }
}

function confirmDelete(agent) {
  agentToDelete.value = agent
  deleteDialog.value = true
}

async function deleteAgent() {
  deleting.value = true
  try {
    await axios.delete(`/agents/${agentToDelete.value.id}`)
    showSnackbar('Agente excluído com sucesso!')
    deleteDialog.value = false
    await fetchAgents()
  } catch (error) {
    console.error('Error deleting agent:', error)
    showSnackbar('Erro ao excluir agente', 'error')
  } finally {
    deleting.value = false
  }
}

async function openCollaboratorsDialog(agent) {
  selectedAgent.value = agent
  collaboratorStatuses.value = {}
  
  try {
    const response = await axios.get(`/agents/${agent.id}/collaborators?include_blocked=true`)
    for (const collab of response.data) {
      collaboratorStatuses.value[collab.id] = collab.status
    }
  } catch (error) {
    console.error('Error fetching collaborators:', error)
  }
  
  // Set default for other agents
  for (const a of otherAgents.value) {
    if (!collaboratorStatuses.value[a.id]) {
      collaboratorStatuses.value[a.id] = 'neutral'
    }
  }
  
  collabDialog.value = true
}

async function saveCollaborators() {
  savingCollab.value = true
  try {
    const collaborators = Object.entries(collaboratorStatuses.value).map(([id, status]) => ({
      collaborator_id: id,
      status: status
    }))
    
    await axios.put(`/agents/${selectedAgent.value.id}/collaborators`, { collaborators })
    showSnackbar('Colaboradores atualizados!')
    collabDialog.value = false
  } catch (error) {
    console.error('Error saving collaborators:', error)
    showSnackbar('Erro ao salvar colaboradores', 'error')
  } finally {
    savingCollab.value = false
  }
}

async function fetchGroups(parentId = null) {
  try {
    const { data } = await agentGroupService.list(parentId)
    agentGroups.value = data
  } catch (e) { console.error('Failed to fetch agent groups', e) }
}

function openGroupDialog(group = null) {
  if (group) {
    groupForm.value = { id: group.id, name: group.name, description: group.description || '', parent_id: group.parent_id }
  } else {
    groupForm.value = { id: null, name: '', description: '', parent_id: currentFolder.value?.id || null }
  }
  groupDialog.value = true
}

async function saveGroup() {
  savingGroup.value = true
  try {
    const payload = { name: groupForm.value.name, description: groupForm.value.description, parent_id: groupForm.value.parent_id }
    if (groupForm.value.id) {
      await agentGroupService.update(groupForm.value.id, payload)
    } else {
      await agentGroupService.create(payload)
    }
    groupDialog.value = false
    await fetchGroups(currentFolder.value?.id || null)
    await fetchGroups()
  } catch (e) { console.error('Failed to save group', e) }
  finally { savingGroup.value = false }
}

async function deleteGroup(id) {
  if (!confirm('Excluir pasta? Sub-pastas serão removidas e agentes desagrupados.')) return
  try {
    await agentGroupService.delete(id)
    if (currentFolder.value?.id === id) backToFolders()
    else fetchGroups(currentFolder.value?.id || null)
  } catch (e) { console.error('Failed to delete group', e) }
}

function openFolder(group) {
  currentFolder.value = group
  breadcrumb.value.push({ id: group.id, name: group.name })
  fetchGroups(group.id)
  fetchAgents()
}

function navigateToBreadcrumb(idx) {
  if (idx < 0) {
    backToFolders()
  } else {
    const target = breadcrumb.value[idx]
    breadcrumb.value = breadcrumb.value.slice(0, idx + 1)
    currentFolder.value = target
    fetchGroups(target.id)
    fetchAgents()
  }
}

function backToFolders() {
  currentFolder.value = null
  breadcrumb.value = []
  fetchGroups(null)
  fetchAgents()
}

function setAllCollaborators(status) {
  for (const agent of otherAgents.value) {
    collaboratorStatuses.value[agent.id] = status
  }
}

async function copyAgentId(id) {
  try {
    await navigator.clipboard.writeText(id)
    showSnackbar('ID do Agente copiado para a área de transferência!')
  } catch (err) {
    console.error('Failed to copy: ', err)
    showSnackbar('Erro ao copiar ID', 'error')
  }
}

onMounted(() => {
  fetchAgents()
  fetchModels()
  fetchAllMcpGroups()
  fetchGroups()
  fetchCustomProviders()
})
</script>

<style scoped>
.agents-page {
  padding: 0;
  width: 100%;
}

.agents-card {
  border-radius: 16px;
}

.agents-table {
  background: transparent !important;
  font-size: 0.9rem;
  color: rgba(255,255,255,0.9) !important;
}

:deep(.v-data-table) {
  background: transparent !important;
}

.search-field :deep(.v-field) {
  border-radius: 8px;
  background: rgba(0,0,0,0.3) !important;
  border: 1px solid rgba(255,255,255,0.05);
}

.gap-1 { gap: 4px; }
.gap-2 { gap: 8px; }

.profile-chip {
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.profile-chip:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.prompt-preview-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.prompt-sections {
  max-height: 500px;
  overflow-y: auto;
  border-radius: 8px;
}

.prompt-section-panel {
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(0, 0, 0, 0.2) !important;
}

.prompt-content-box {
  background: #1e1e1e;
  padding: 12px;
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.prompt-text {
  font-family: 'Fira Code', 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  line-height: 1.4;
  white-space: pre-wrap;
  color: #dcdcdc;
}
</style>
