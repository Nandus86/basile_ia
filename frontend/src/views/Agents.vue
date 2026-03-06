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

    <!-- Agents Grid -->
    <v-card class="agents-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
        <span class="text-white">Lista de Agentes</span>
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
              <span class="font-weight-medium">{{ item.name }}</span>
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
                  <v-col cols="12" md="4">
                    <v-autocomplete
                      v-model="formData.model"
                      label="Modelo LLM"
                      :items="modelOptions"
                      item-title="title"
                      item-value="value"
                      prepend-inner-icon="mdi-brain"
                      :loading="loadingModels"
                      placeholder="Buscar modelo..."
                      no-data-text="Nenhum modelo encontrado"
                    >
                      <template v-slot:item="{ props, item }">
                        <v-list-item v-bind="props">
                          <template v-slot:prepend>
                            <v-icon :color="item.raw.provider === 'openai' ? '#10a37f' : '#6366f1'" size="18">
                              {{ item.raw.provider === 'openai' ? 'mdi-creation' : 'mdi-router-wireless' }}
                            </v-icon>
                          </template>
                          <template v-slot:subtitle v-if="item.raw.context_length">
                            <span class="text-caption">{{ formatContextLength(item.raw.context_length) }} tokens</span>
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
                  <v-col cols="12" md="4" v-if="!formData.config.is_reasoning_model">
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
                  <v-col cols="12" md="4" v-if="!formData.config.is_reasoning_model">
                    <v-text-field
                      v-model="formData.max_tokens"
                      label="Max Tokens"
                      type="number"
                      min="100"
                      max="128000"
                      prepend-inner-icon="mdi-counter"
                    ></v-text-field>
                  </v-col>
                  <v-col cols="12" md="4" v-if="formData.config.is_reasoning_model">
                    <v-select
                      v-model="formData.config.reasoning_effort"
                      label="Reasoning Effort"
                      :items="reasoningEffortOptions"
                      item-title="label"
                      item-value="value"
                      prepend-inner-icon="mdi-head-cog"
                      hint="Controla profundidade do raciocínio"
                      persistent-hint
                    ></v-select>
                  </v-col>
                  <v-col cols="12" md="4" v-if="formData.config.is_reasoning_model">
                    <v-text-field
                      v-model="formData.config.max_completion_tokens"
                      label="Max Completion Tokens"
                      type="number"
                      min="1000"
                      max="128000"
                      prepend-inner-icon="mdi-counter"
                      hint="Inclui tokens de raciocínio + resposta"
                      persistent-hint
                    ></v-text-field>
                  </v-col>
                </v-row>

                <!-- Reasoning Model Toggle -->
                <v-expand-transition>
                  <v-card variant="outlined" class="mt-2 mb-2" :color="formData.config.is_reasoning_model ? 'purple' : undefined">
                    <v-card-text class="d-flex align-center py-2">
                      <v-switch
                        v-model="formData.config.is_reasoning_model"
                        label="Modelo de Raciocínio"
                        color="purple"
                        hide-details
                        density="compact"
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
                </v-expand-transition>
                
                <v-divider class="my-4"></v-divider>
                
                <v-row>
                  <v-col cols="12" md="4">
                    <v-switch
                      v-model="formData.is_active"
                      label="Agente Ativo"
                      color="success"
                      hide-details
                    >
                      <template v-slot:prepend>
                        <v-icon :color="formData.is_active ? 'success' : 'grey'">mdi-power</v-icon>
                      </template>
                    </v-switch>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-switch
                      v-model="formData.collaboration_enabled"
                      label="Colaboração"
                      color="info"
                      hide-details
                    >
                      <template v-slot:prepend>
                        <v-icon :color="formData.collaboration_enabled ? 'info' : 'grey'">mdi-account-group</v-icon>
                      </template>
                    </v-switch>
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-switch
                      v-model="formData.vector_memory_enabled"
                      label="Memória Vetorial"
                      color="deep-purple"
                      hide-details
                    >
                      <template v-slot:prepend>
                        <v-icon :color="formData.vector_memory_enabled ? 'deep-purple' : 'grey'">mdi-brain</v-icon>
                      </template>
                    </v-switch>
                  </v-col>
                </v-row>
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

                <h3 class="text-subtitle-1 font-weight-bold mt-4 mb-2">Human-in-the-loop</h3>
                <v-card variant="outlined" class="pa-3">
                  <v-switch
                    v-model="resilienceData.human_approval_enabled"
                    label="Requer Aprovação Humana"
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
import { ref, reactive, computed, onMounted } from 'vue'
import axios from '@/plugins/axios'

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
  emotional_profile_id: null,
  emotional_intensity: 'medium',
  emotional_intensity: 'medium',
  output_schema: null,
  input_schema: null,
  transition_input_schema: null,
  transition_output_schema: null,
  config: {
    is_reasoning_model: false,
    reasoning_effort: 'medium',
    max_completion_tokens: 16384
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

// Collaborators dialog
const collabDialog = ref(false)
const selectedAgent = ref(null)
const collaboratorStatuses = ref({})
const savingCollab = ref(false)

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

const modelOptions = computed(() => {
  // Group by provider: OpenAI first, then OpenRouter
  const openai = allModels.value
    .filter(m => m.provider === 'openai')
    .map(m => ({
      title: m.name,
      value: m.id,
      provider: m.provider,
      context_length: m.context_length
    }))
  const openrouter = allModels.value
    .filter(m => m.provider === 'openrouter')
    .map(m => ({
      title: m.name,
      value: m.id,
      provider: m.provider,
      context_length: m.context_length
    }))

  const items = []
  if (openai.length > 0) {
    items.push({ type: 'subheader', title: '🟢 OpenAI' })
    items.push(...openai)
  }
  if (openrouter.length > 0) {
    items.push({ type: 'subheader', title: '🔵 OpenRouter' })
    items.push(...openrouter)
  }
  return items
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
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '140px' }
]

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
    emotional_profile_id: null,
    emotional_intensity: 'medium',
    output_schema: null,
    input_schema: null,
    transition_input_schema: null,
    transition_output_schema: null,
    config: {
      is_reasoning_model: false,
      reasoning_effort: 'medium',
      max_completion_tokens: 16384
    }
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

async function fetchAgents() {
  loading.value = true
  try {
    const response = await axios.get('/agents')
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
        emotional_profile_id: fullAgent.emotional_profile?.id || null,
        emotional_intensity: fullAgent.emotional_intensity || 'medium',
        output_schema: fullAgent.output_schema || null,
        input_schema: fullAgent.input_schema || null,
        transition_input_schema: fullAgent.transition_input_schema || null,
        transition_output_schema: fullAgent.transition_output_schema || null,
        config: {
          is_reasoning_model: fullAgent.config?.is_reasoning_model ?? false,
          reasoning_effort: fullAgent.config?.reasoning_effort || 'medium',
          max_completion_tokens: fullAgent.config?.max_completion_tokens || 16384,
          ...(fullAgent.config || {})
        }
      })
      
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
        fetchAgentSkills(fullAgent.id),
        fetchDocuments(),
        fetchAllMcps(),
        fetchAllSkills(),
        fetchAllBases(),
        fetchAgentBases(fullAgent.id),
        fetchEmotionalProfiles()
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

function selectEmotionalProfile(profile) {
  formData.emotional_profile_id = profile.id
}

function clearEmotionalProfile() {
  formData.emotional_profile_id = null
  formData.emotional_intensity = 'medium'
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
    const response = await axios.get(`/agents/${agent.id}/collaborators`)
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

onMounted(() => {
  fetchAgents()
  fetchModels()
})
</script>

<style scoped>
.agents-page {
  padding: 0;
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-icon {
  width: 50px;
  height: 50px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(157, 78, 221, 0.2), rgba(0, 242, 254, 0.1));
  border: 1px solid rgba(157, 78, 221, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-text h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  color: #FFF;
  letter-spacing: -0.02em;
}

.header-text p {
  margin: 0;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.9rem;
}

.glass-card {
  background: rgba(16, 20, 34, 0.5) !important;
  border-radius: 16px;
  box-shadow: 0 4px 30px rgba(0,0,0,0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-card {
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(157, 78, 221, 0.2);
}

.stat-avatar {
  background: linear-gradient(135deg, rgba(157, 78, 221, 0.6), rgba(0, 242, 254, 0.3)) !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
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
:deep(.v-data-table th) {
  background: transparent !important;
  border-bottom: 1px solid rgba(255,255,255,0.05) !important;
  color: rgba(255,255,255,0.6) !important;
}
:deep(.v-data-table td) {
  background: transparent !important;
  border-bottom: 1px solid rgba(255,255,255,0.03) !important;
}
:deep(.v-data-table tbody tr:hover td) {
  background: rgba(255,255,255,0.02) !important;
}

.search-field :deep(.v-field) {
  border-radius: 8px;
  background: rgba(0,0,0,0.3) !important;
  border: 1px solid rgba(255,255,255,0.05);
}

.gap-1 {
  gap: 4px;
}

.gap-2 {
  gap: 8px;
}

/* Emotional Profile Chips */
.profile-chip {
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.profile-chip:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}
</style>
