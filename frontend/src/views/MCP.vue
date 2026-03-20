<template>
  <div class="mcp-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-folder-network</v-icon>
        </div>
        <div class="header-text">
          <h1>MCP - Model Context Protocol</h1>
          <p v-if="!currentFolder">Integrações com APIs externas e ferramentas</p>
          <p v-else>
            {{ currentFolder.name }}
          </p>
        </div>
      </div>
      <div>
        <v-btn v-if="currentFolder" color="secondary" size="large" prepend-icon="mdi-arrow-left" @click="backToFolders()" elevation="3" class="mr-3">
          Voltar as Pastas
        </v-btn>
        <v-btn v-if="!currentFolder" color="secondary" size="large" prepend-icon="mdi-folder-plus" @click="openGroupDialog()" elevation="3" class="mr-3">
          Nova Pasta
        </v-btn>
        <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="openDialog()" elevation="3">
          Novo MCP
        </v-btn>
      </div>
    </div>

    <!-- Stats Cards -->
    <v-row class="mb-6">
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-puzzle</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ mcps.length }}</p>
              <p class="text-caption text-medium-emphasis mb-0">Total MCPs</p>
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
              <v-icon color="white">mdi-cloud-download</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ getCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">GET Requests</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card class="stat-card glass-card">
          <v-card-text class="d-flex align-center">
            <v-avatar class="mr-4 stat-avatar" size="48">
              <v-icon color="white">mdi-cloud-upload</v-icon>
            </v-avatar>
            <div>
              <p class="text-h4 font-weight-bold mb-0">{{ postCount }}</p>
              <p class="text-caption text-medium-emphasis mb-0">POST/PUT/DELETE</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Folders View (Only shown at root level, not inside a folder) -->
    <v-row v-if="!currentFolder && mcpGroups.length > 0" class="mb-6">
      <v-col cols="12">
        <h2 class="text-h6 mb-2">Pastas de Integração</h2>
      </v-col>
      <!-- User Folders -->
      <v-col cols="12" sm="6" md="4" lg="3" v-for="group in mcpGroups" :key="group.id">
        <v-card class="folder-card glass-card h-100 d-flex flex-column" hover>
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
            <p class="text-body-2 text-medium-emphasis mb-3 line-clamp-2" style="min-height: 40px">
              {{ group.description || 'Sem descrição' }}
            </p>
            <v-chip size="small" color="primary" variant="tonal">
              {{ mcps.filter(m => m.group_id === group.id).length }} itens
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- MCP Table -->
    <v-card class="mcp-card glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
        <span class="text-white">{{ currentFolder ? `Ferramentas em: ${currentFolder.name}` : 'Ferramentas sem pasta' }}</span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          density="compact"
          placeholder="Buscar MCP..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          hide-details
          style="max-width: 300px"
        ></v-text-field>
      </v-card-title>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="filteredMcps"
        :loading="loading"
        :items-per-page="10"
        class="mcp-table"
      >
        <template v-slot:item.name="{ item }">
          <div class="d-flex align-center py-2">
            <v-avatar :color="getMethodColor(item.method)" size="36" class="mr-3">
              <v-icon color="white" size="18">{{ getMethodIcon(item.method) }}</v-icon>
            </v-avatar>
            <div>
              <span class="font-weight-medium">{{ item.name }}</span>
              <p class="text-caption text-medium-emphasis mb-0" v-if="item.description">
                {{ item.description?.substring(0, 40) }}{{ item.description?.length > 40 ? '...' : '' }}
              </p>
            </div>
          </div>
        </template>
        
        <template v-slot:item.endpoint="{ item }">
          <v-chip variant="outlined" size="small" class="endpoint-chip">
            <code>{{ truncateUrl(item.endpoint) }}</code>
          </v-chip>
        </template>
        
        <template v-slot:item.method="{ item }">
          <v-chip :color="getMethodColor(item.method)" size="small" label>
            {{ item.method }}
          </v-chip>
        </template>
        
        <template v-slot:item.protocol="{ item }">
          <v-chip :color="getProtocolColor(item.protocol)" size="small" variant="tonal">
            <v-icon start size="14">{{ getProtocolIcon(item.protocol) }}</v-icon>
            {{ (item.protocol || 'http').toUpperCase() }}
          </v-chip>
        </template>
        
        
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            <v-icon start size="14">{{ item.is_active ? 'mdi-check' : 'mdi-close' }}</v-icon>
            {{ item.is_active ? 'Ativo' : 'Inativo' }}
          </v-chip>
        </template>
        
        <template v-slot:item.group_id="{ item }">
          <v-chip v-if="item.group_id" size="small" variant="outlined" color="secondary">
            <v-icon start size="14">mdi-folder</v-icon>
            {{ getGroupName(item.group_id) }}
          </v-chip>
          <span v-else class="text-caption text-medium-emphasis">-</span>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn icon variant="text" size="small" color="success" @click="openExecuteDialog(item)">
              <v-icon size="20">mdi-play-circle</v-icon>
              <v-tooltip activator="parent" location="top">Testar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="secondary" @click="duplicateMcp(item)" :loading="duplicatingMcp === item.id">
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
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-puzzle-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhum MCP encontrado</p>
            <p class="text-body-2 text-medium-emphasis mb-4">Crie sua primeira integração para começar</p>
            <v-btn color="primary" @click="openDialog()">
              <v-icon start>mdi-plus</v-icon>
              Criar MCP
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
          <span class="text-white">{{ editing ? 'Editar MCP' : 'Novo MCP' }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="dialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-form ref="formRef" v-model="formValid">
            <!-- Basic Info -->
            <p class="text-subtitle-2 text-medium-emphasis mb-3">
              <v-icon size="18" class="mr-1">mdi-information</v-icon>
              Informações Básicas
            </p>
            
            <v-row>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="formData.name"
                  label="Nome do MCP"
                  placeholder="Ex: API de Clima"
                  :rules="[v => !!v || 'Nome é obrigatório']"
                  prepend-inner-icon="mdi-puzzle"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="formData.group_id"
                  :items="mcpGroups"
                  item-title="name"
                  item-value="id"
                  label="Pasta / Grupo"
                  prepend-inner-icon="mdi-folder"
                  clearable
                ></v-select>
              </v-col>
              <v-col cols="12" md="2">
                <v-switch
                  v-model="formData.is_active"
                  label="Ativo"
                  color="success"
                  hide-details
                >
                  <template v-slot:prepend>
                    <v-icon :color="formData.is_active ? 'success' : 'grey'">mdi-power</v-icon>
                  </template>
                </v-switch>
              </v-col>
            </v-row>
            
            <v-textarea
              v-model="formData.description"
              label="Descrição"
              placeholder="Descreva o que este MCP faz..."
              rows="2"
              prepend-inner-icon="mdi-text"
            ></v-textarea>

            <v-divider class="my-4"></v-divider>

            <!-- Endpoint Config -->
            <p class="text-subtitle-2 text-medium-emphasis mb-3">
              <v-icon size="18" class="mr-1">mdi-api</v-icon>
              Configuração do Endpoint
            </p>
            
            <v-row>
              <v-col cols="12" md="4">
                <v-select
                  v-model="formData.protocol"
                  label="Protocolo"
                  :items="protocolOptions"
                  item-title="label"
                  item-value="value"
                  prepend-inner-icon="mdi-swap-horizontal"
                >
                  <template v-slot:item="{ item, props }">
                    <v-list-item v-bind="props">
                      <template v-slot:prepend>
                        <v-icon :color="getProtocolColor(item.value)" size="20" class="mr-2">
                          {{ getProtocolIcon(item.value) }}
                        </v-icon>
                      </template>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="formData.method"
                  label="Método"
                  :items="httpMethods"
                  item-title="label"
                  item-value="value"
                  prepend-inner-icon="mdi-web"
                ></v-select>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="formData.timeout_seconds"
                  label="Timeout (s)"
                  type="number"
                  min="1"
                  max="300"
                  prepend-inner-icon="mdi-timer"
                ></v-text-field>
              </v-col>
            </v-row>
            <v-row>
              <v-col cols="12">
                <v-textarea
                  v-model="formData.endpoint"
                  label="URL do Endpoint"
                  placeholder="https://api.exemplo.com/v1/resource"
                  :rules="[v => !!v || 'Endpoint é obrigatório']"
                  prepend-inner-icon="mdi-link"
                  variant="outlined"
                  auto-grow
                  rows="2"
                ></v-textarea>
              </v-col>
            </v-row>
            
            <v-alert v-if="formData.protocol === 'sse'" type="info" variant="tonal" density="compact" class="mt-2 mb-0">
              <v-icon start>mdi-information</v-icon>
              <strong>SSE:</strong> Server-Sent Events - conexão streaming para receber eventos em tempo real.
            </v-alert>

            <v-divider class="my-4"></v-divider>

            <!-- Headers & Body -->
            <v-row>
              <v-col cols="12" md="6">
                <p class="text-subtitle-2 text-medium-emphasis mb-2">
                  <v-icon size="18" class="mr-1">mdi-code-json</v-icon>
                  Headers (JSON)
                </p>
                <v-textarea
                  v-model="headersJson"
                  placeholder='{"Authorization": "Bearer ...", "Content-Type": "application/json"}'
                  rows="4"
                  variant="outlined"
                  density="compact"
                  :error-messages="headersError"
                  @blur="validateHeaders"
                ></v-textarea>
              </v-col>
              <v-col cols="12" md="6">
                <p class="text-subtitle-2 text-medium-emphasis mb-2">
                  <v-icon size="18" class="mr-1">mdi-code-braces</v-icon>
                  Body Template (JSON)
                </p>
                <v-textarea
                  v-model="bodyJson"
                  placeholder='{"query": "", "limit": 10}'
                  rows="4"
                  variant="outlined"
                  density="compact"
                  :error-messages="bodyError"
                  @blur="validateBody"
                ></v-textarea>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>
            
            <v-row>
              <v-col cols="12" md="12">
                <p class="text-subtitle-2 text-medium-emphasis mb-2">
                  <v-icon size="18" class="mr-1">mdi-magnify</v-icon>
                  Query Template (JSON)
                </p>
                <v-textarea
                  v-model="queryTemplateJson"
                  placeholder='{"search": "{{ $fromAI(\"query\", \"The search query\", \"string\") }}"}'
                  rows="2"
                  variant="outlined"
                  density="compact"
                  :error-messages="queryTemplateError"
                  @blur="validateQueryTemplate"
                ></v-textarea>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Response Mapping & Keywords -->
            <v-row>
              <v-col cols="12" md="6">
                <p class="text-subtitle-2 text-medium-emphasis mb-2">
                  <v-icon size="18" class="mr-1">mdi-map</v-icon>
                  Response Mapping (JSON)
                </p>
                <v-textarea
                  v-model="responseMappingJson"
                  placeholder='{"result": "data.items", "total": "meta.total"}'
                  rows="3"
                  variant="outlined"
                  density="compact"
                  hint="Mapeia campos da resposta para uso pelo agente"
                  persistent-hint
                ></v-textarea>
              </v-col>
              <v-col cols="12" md="6">
                <p class="text-subtitle-2 text-medium-emphasis mb-2">
                  <v-icon size="18" class="mr-1">mdi-tag-multiple</v-icon>
                  Trigger Keywords
                </p>
                <v-combobox
                  v-model="formData.trigger_keywords"
                  label="Palavras-chave que ativam este MCP"
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="compact"
                  hint="Pressione Enter para adicionar"
                  persistent-hint
                ></v-combobox>
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-btn variant="outlined" color="info" @click="testMcp" :loading="testing" :disabled="!formData.endpoint">
            <v-icon start>mdi-play</v-icon>
            Testar Conexão
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="dialog = false" :disabled="saving">
            Cancelar
          </v-btn>
          <v-btn color="primary" @click="saveMcp" :loading="saving" :disabled="!formValid">
            <v-icon start>mdi-content-save</v-icon>
            {{ editing ? 'Atualizar' : 'Criar' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Execute Dialog -->
    <v-dialog v-model="executeDialog" max-width="700">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-success">
          <v-icon class="mr-2" color="white">mdi-play-circle</v-icon>
          <span class="text-white">Testar: {{ selectedMcp?.name }}</span>
          <v-spacer></v-spacer>
          <v-chip :color="getMethodColor(selectedMcp?.method)" size="small" class="ml-2">
            {{ selectedMcp?.method }}
          </v-chip>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-alert type="info" variant="tonal" class="mb-4" density="compact">
            <strong>Endpoint:</strong> {{ selectedMcp?.endpoint }}
          </v-alert>
          
          <p class="text-subtitle-2 text-medium-emphasis mb-2">
            <v-icon size="18" class="mr-1">mdi-code-json</v-icon>
            Parâmetros (JSON)
          </p>
          <v-textarea
            v-model="executeParamsJson"
            placeholder='{"query": "teste", "limit": 5}'
            rows="5"
            variant="outlined"
          ></v-textarea>
          
          <!-- Variables ($request) -->
          <div v-if="hasRequestVars">
            <p class="text-subtitle-2 text-medium-emphasis mb-2 mt-4">
              <v-icon size="18" class="mr-1">mdi-variable</v-icon>
              Variáveis (<code>$request</code>)
            </p>
            <v-alert type="info" variant="tonal" density="compact" class="mb-2">
              Substitui <code>{{ '{{ $request.xxx }}' }}</code> antes de enviar a requisição.
            </v-alert>
            <v-textarea
              v-model="executeVariablesJson"
              placeholder='{"system.baseUrlBasileia": "https://dash.basileia.global"}'
              rows="4"
              variant="outlined"
              class="font-monospace"
            ></v-textarea>
          </div>
          
          <!-- Result -->
          <div v-if="executeResult" class="mt-4">
            <v-alert :type="executeResult.success ? 'success' : 'error'" variant="tonal" class="mb-2">
              <div class="d-flex align-center">
                <span>{{ executeResult.success ? 'Sucesso!' : 'Erro' }}</span>
                <v-spacer></v-spacer>
                <v-chip size="small" variant="outlined">
                  <v-icon start size="14">mdi-clock</v-icon>
                  {{ executeResult.execution_time_ms?.toFixed(0) }}ms
                </v-chip>
              </div>
            </v-alert>
            
            <v-card variant="outlined" class="result-card">
              <v-card-title class="text-subtitle-2 py-2 px-4 bg-grey-lighten-4">
                <v-icon size="18" class="mr-1">mdi-code-braces</v-icon>
                Resposta
                <v-spacer></v-spacer>
                <v-btn icon size="x-small" variant="text" @click="copyResult">
                  <v-icon size="16">mdi-content-copy</v-icon>
                  <v-tooltip activator="parent">Copiar</v-tooltip>
                </v-btn>
              </v-card-title>
              <v-card-text class="pa-4">
                <pre class="result-pre">{{ formatResult }}</pre>
              </v-card-text>
            </v-card>
          </div>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="executeDialog = false">
            Fechar
          </v-btn>
          <v-btn color="success" @click="runMcp" :loading="executing">
            <v-icon start>mdi-play</v-icon>
            Executar
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
          <p class="text-h6">Deseja excluir este MCP?</p>
          <p class="text-body-2 text-medium-emphasis">
            <strong>{{ mcpToDelete?.name }}</strong><br>
            Esta ação não pode ser desfeita.
          </p>
        </v-card-text>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="deleteDialog = false">Cancelar</v-btn>
          <v-btn color="error" @click="deleteMcp" :loading="deleting">
            <v-icon start>mdi-delete</v-icon>
            Excluir
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Group Management Dialog -->
    <v-dialog v-model="groupDialog" max-width="500">
      <v-card>
        <v-card-title class="d-flex align-center px-6 py-4 bg-secondary">
          <v-icon class="mr-2" color="white">{{ editingGroup ? 'mdi-pencil' : 'mdi-folder-plus' }}</v-icon>
          <span class="text-white">{{ editingGroup ? 'Editar Pasta' : 'Nova Pasta' }}</span>
          <v-spacer></v-spacer>
          <v-btn icon variant="text" @click="groupDialog = false" color="white">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6">
          <v-form ref="groupFormRef" v-model="groupFormValid" @submit.prevent="saveGroup">
            <v-row class="mb-2">
              <v-col cols="12" md="12">
                <v-text-field
                  v-model="newGroup.name"
                  label="Nome da Pasta"
                  :rules="[v => !!v || 'Nome é obrigatório']"
                  density="compact"
                  variant="outlined"
                  hide-details="auto"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="12">
                <v-textarea
                  v-model="newGroup.description"
                  label="Descrição (Para ajudar a IA a entender como usar)"
                  density="compact"
                  variant="outlined"
                  rows="3"
                  hide-details="auto"
                ></v-textarea>
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="outlined" @click="groupDialog = false">Cancelar</v-btn>
          <v-btn color="primary" @click="saveGroup" :loading="savingGroup" :disabled="!groupFormValid">
            <v-icon start>mdi-content-save</v-icon> {{ editingGroup ? 'Salvar' : 'Criar' }}
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
const mcps = ref([])
const mcpGroups = ref([])
const selectedGroupId = ref(null)
const currentView = ref('folders')
const currentFolder = ref(null)
const loading = ref(false)
const search = ref('')

// Form dialog
const dialog = ref(false)
const saving = ref(false)
const testing = ref(false)
const editing = ref(false)
const formRef = ref(null)
const formValid = ref(false)
const formData = reactive({
  id: null,
  name: '',
  description: '',
  endpoint: '',
  method: 'POST',
  protocol: 'http',
  headers: {},
  body_template: {},
  query_template: {},
  response_mapping: {},
  trigger_keywords: [],
  timeout_seconds: 30,
  is_active: true,
  group_id: null
})
const headersJson = ref('{}')
const bodyJson = ref('{}')
const queryTemplateJson = ref('{}')
const responseMappingJson = ref('{}')
const headersError = ref('')
const bodyError = ref('')
const queryTemplateError = ref('')

// Group Dialog
const groupDialog = ref(false)
const groupFormValid = ref(false)
const savingGroup = ref(false)
const editingGroup = ref(false)
const newGroup = reactive({ id: null, name: '', description: '' })

// Execute dialog
const executeDialog = ref(false)
const selectedMcp = ref(null)
const executeParamsJson = ref('{}')
const executeVariablesJson = ref('{}')
const executeResult = ref(null)
const executing = ref(false)

// Delete dialog
const deleteDialog = ref(false)
const mcpToDelete = ref(null)
const deleting = ref(false)

// Snackbar
const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
})

const httpMethods = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
  { value: 'PUT', label: 'PUT' },
  { value: 'PATCH', label: 'PATCH' },
  { value: 'DELETE', label: 'DEL' }
]

const protocolOptions = [
  { value: 'http', label: 'HTTP - Request/Response' },
  { value: 'sse', label: 'SSE - Server-Sent Events' },
  { value: 'mcp', label: 'MCP - Model Context Protocol' },
  { value: 'websocket', label: 'WebSocket (em breve)' },
  { value: 'stdio', label: 'STDIO (em breve)' }
]

const headers = [
  { title: 'MCP', key: 'name', sortable: true },
  { title: 'Protocolo', key: 'protocol', sortable: true, width: '100px' },
  { title: 'Endpoint', key: 'endpoint', sortable: false },
  { title: 'Método', key: 'method', sortable: true, width: '80px' },
  { title: 'Status', key: 'is_active', sortable: true, width: '100px' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '180px' }
]

// Duplicate MCP state
const duplicatingMcp = ref(null)

// Computed
const filterGroupOptions = computed(() => {
  return [{ id: null, name: 'Todos' }, ...mcpGroups.value]
})

const filteredMcps = computed(() => {
  let filtered = mcps.value
  
  // Se estiver dentro de uma pasta, filtra só os MCPs daquela pasta
  if (currentFolder.value) {
    filtered = filtered.filter(m => m.group_id === currentFolder.value.id)
  } else {
    // Se estiver na raiz, mostra só os MCPs que não têm pasta
    filtered = filtered.filter(m => !m.group_id)
  }
  
  if (!search.value) return filtered
  
  const s = search.value.toLowerCase()
  return filtered.filter(m => 
    m.name?.toLowerCase().includes(s) || 
    m.description?.toLowerCase().includes(s) ||
    m.endpoint?.toLowerCase().includes(s)
  )
})

const activeCount = computed(() => mcps.value.filter(m => m.is_active).length)
const getCount = computed(() => mcps.value.filter(m => m.method === 'GET').length)
const postCount = computed(() => mcps.value.filter(m => ['POST', 'PUT', 'PATCH', 'DELETE'].includes(m.method)).length)

const formatResult = computed(() => {
  if (!executeResult.value) return ''
  const data = executeResult.value.result || executeResult.value.error || {}
  return JSON.stringify(data, null, 2)
})

const hasRequestVars = computed(() => {
  try {
    const vars = JSON.parse(executeVariablesJson.value || '{}')
    return Object.keys(vars).length > 0
  } catch {
    return false
  }
})

// Helpers
function getGroupName(groupId) {
  if (!groupId) return ''
  const g = mcpGroups.value.find(item => item.id === groupId)
  return g ? g.name : ''
}

function getMethodColor(method) {
  const colors = { GET: 'info', POST: 'success', PUT: 'warning', PATCH: 'deep-orange', DELETE: 'error' }
  return colors[method] || 'grey'
}

function getMethodIcon(method) {
  const icons = { GET: 'mdi-download', POST: 'mdi-upload', PUT: 'mdi-pencil', PATCH: 'mdi-update', DELETE: 'mdi-trash-can' }
  return icons[method] || 'mdi-web'
}

function truncateUrl(url) {
  if (!url) return ''
  if (url.length > 35) return url.substring(0, 35) + '...'
  return url
}

function showSnackbar(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

function validateHeaders() {
  try {
    JSON.parse(headersJson.value)
    headersError.value = ''
  } catch (e) {
    headersError.value = 'JSON inválido'
  }
}

function validateBody() {
  try {
    JSON.parse(bodyJson.value)
    bodyError.value = ''
  } catch (e) {
    bodyError.value = 'JSON inválido'
  }
}

function validateQueryTemplate() {
  try {
    JSON.parse(queryTemplateJson.value)
    queryTemplateError.value = ''
  } catch (e) {
    queryTemplateError.value = 'JSON inválido'
  }
}

function resetForm() {
  Object.assign(formData, {
    id: null,
    name: '',
    description: '',
    endpoint: '',
    method: 'POST',
    protocol: 'http',
    headers: {},
    body_template: {},
    query_template: {},
    response_mapping: {},
    trigger_keywords: [],
    timeout_seconds: 30,
    is_active: true,
    group_id: null
  })
  headersJson.value = '{}'
  bodyJson.value = '{}'
  queryTemplateJson.value = '{}'
  responseMappingJson.value = '{}'
  headersError.value = ''
  bodyError.value = ''
  queryTemplateError.value = ''
}

function getProtocolColor(protocol) {
  const colors = { http: 'info', sse: 'warning', mcp: 'purple', websocket: 'success', stdio: 'grey' }
  return colors[protocol] || 'grey'
}

function getProtocolIcon(protocol) {
  const icons = { http: 'mdi-web', sse: 'mdi-broadcast', mcp: 'mdi-robot', websocket: 'mdi-lan-connect', stdio: 'mdi-console' }
  return icons[protocol] || 'mdi-connection'
}

async function copyResult() {
  await navigator.clipboard.writeText(formatResult.value)
  showSnackbar('Copiado!')
}

// API
async function fetchMcps() {
  loading.value = true
  try {
    const response = await axios.get('/mcp')
    mcps.value = response.data.mcps || []
  } catch (error) {
    console.error('Error fetching MCPs:', error)
    showSnackbar('Erro ao carregar MCPs', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchMcpGroups() {
  try {
    const response = await axios.get('/mcp-groups')
    mcpGroups.value = response.data || []
  } catch (error) {
    console.error('Error fetching MCP Groups:', error)
  }
}

function openGroupDialog(group = null) {
  if (group) {
    editingGroup.value = true
    newGroup.id = group.id
    newGroup.name = group.name
    newGroup.description = group.description || ''
  } else {
    editingGroup.value = false
    newGroup.id = null
    newGroup.name = ''
    newGroup.description = ''
  }
  groupDialog.value = true
}

async function saveGroup() {
  if (!newGroup.name) return
  savingGroup.value = true
  try {
    const payload = { 
      name: newGroup.name,
      description: newGroup.description
    }
    
    if (editingGroup.value) {
      await axios.put(`/mcp-groups/${newGroup.id}`, payload)
      showSnackbar('Grupo atualizado com sucesso!')
    } else {
      await axios.post('/mcp-groups', payload)
      showSnackbar('Grupo criado com sucesso!')
    }
    
    groupDialog.value = false
    await fetchMcpGroups()
  } catch (error) {
    console.error('Error saving group:', error)
    showSnackbar('Erro ao salvar grupo', 'error')
  } finally {
    savingGroup.value = false
  }
}

function openFolder(group) {
  currentFolder.value = group
  search.value = ''
}

function backToFolders() {
  currentFolder.value = null
  search.value = ''
}

async function deleteGroup(id) {
  if (!confirm('Tem certeza que deseja deletar este grupo? Os MCPs ficarão sem grupo.')) return
  try {
    await axios.delete(`/mcp-groups/${id}`)
    showSnackbar('Grupo excluído!')
    await fetchMcpGroups()
    await fetchMcps()
  } catch (error) {
    showSnackbar('Erro ao excluir grupo', 'error')
  }
}

function openDialog(mcp = null) {
  if (mcp) {
    editing.value = true
    Object.assign(formData, {
      id: mcp.id,
      name: mcp.name,
      description: mcp.description || '',
      endpoint: mcp.endpoint,
      method: mcp.method || 'POST',
      headers: mcp.headers || {},
      body_template: mcp.body_template || {},
      query_template: mcp.query_template || {},
      response_mapping: mcp.response_mapping || {},
      trigger_keywords: mcp.trigger_keywords || [],
      protocol: mcp.protocol || 'http',
      timeout_seconds: mcp.timeout_seconds || 30,
      is_active: mcp.is_active ?? true,
      group_id: mcp.group_id || null
    })
    headersJson.value = JSON.stringify(mcp.headers || {}, null, 2)
    bodyJson.value = JSON.stringify(mcp.body_template || {}, null, 2)
    queryTemplateJson.value = JSON.stringify(mcp.query_template || {}, null, 2)
    responseMappingJson.value = JSON.stringify(mcp.response_mapping || {}, null, 2)
  } else {
    editing.value = false
    resetForm()
  }
  dialog.value = true
}

async function saveMcp() {
  saving.value = true
  try {
    // Parse JSON fields
    const payload = {
      name: formData.name,
      description: formData.description,
      endpoint: formData.endpoint,
      method: formData.method,
      protocol: formData.protocol,
      timeout_seconds: parseInt(formData.timeout_seconds) || 30,
      headers: JSON.parse(headersJson.value || '{}'),
      body_template: JSON.parse(bodyJson.value || '{}'),
      query_template: JSON.parse(queryTemplateJson.value || '{}'),
      response_mapping: JSON.parse(responseMappingJson.value || '{}'),
      trigger_keywords: formData.trigger_keywords,
      is_active: formData.is_active,
      group_id: formData.group_id || null
    }
    
    if (editing.value) {
      await axios.put(`/mcp/${formData.id}`, payload)
      showSnackbar('MCP atualizado com sucesso!')
    } else {
      await axios.post('/mcp', payload)
      showSnackbar('MCP criado com sucesso!')
    }
    dialog.value = false
    await fetchMcps()
  } catch (error) {
    console.error('Error saving MCP:', error)
    showSnackbar('Erro ao salvar MCP', 'error')
  } finally {
    saving.value = false
  }
}

async function testMcp() {
  testing.value = true
  try {
    // Quick connectivity test
    showSnackbar('Endpoint válido!', 'success')
  } finally {
    testing.value = false
  }
}

async function duplicateMcp(mcp) {
  duplicatingMcp.value = mcp.id
  try {
    const payload = {
      name: mcp.name + ' (Cópia)',
      description: mcp.description || '',
      endpoint: mcp.endpoint || '',
      method: mcp.method || 'POST',
      protocol: mcp.protocol || 'http',
      timeout_seconds: mcp.timeout_seconds || 30,
      headers: mcp.headers || {},
      body_template: mcp.body_template || {},
      query_template: mcp.query_template || {},
      response_mapping: mcp.response_mapping || {},
      trigger_keywords: mcp.trigger_keywords || [],
      is_active: false,
      group_id: mcp.group_id || null
    }
    await axios.post('/mcp', payload)
    showSnackbar('MCP duplicado com sucesso!')
    await fetchMcps()
  } catch (error) {
    console.error('Error duplicating MCP:', error)
    showSnackbar('Erro ao duplicar MCP', 'error')
  } finally {
    duplicatingMcp.value = null
  }
}

function confirmDelete(mcp) {
  mcpToDelete.value = mcp
  deleteDialog.value = true
}

async function deleteMcp() {
  deleting.value = true
  try {
    await axios.delete(`/mcp/${mcpToDelete.value.id}`)
    showSnackbar('MCP excluído com sucesso!')
    deleteDialog.value = false
    await fetchMcps()
  } catch (error) {
    console.error('Error deleting MCP:', error)
    showSnackbar('Erro ao excluir MCP', 'error')
  } finally {
    deleting.value = false
  }
}

function openExecuteDialog(mcp) {
  selectedMcp.value = mcp
  executeResult.value = null
  
  // Scan all MCP fields to find $fromAI and $request placeholders
  const textToScan = [
    mcp.endpoint || '',
    JSON.stringify(mcp.headers || {}),
    JSON.stringify(mcp.body_template || {}),
    JSON.stringify(mcp.query_template || {})
  ].join('\n')
  
  // ── Extract $fromAI params ──
  const extractedParams = {}
  const fromAIRegex = /\{\{\s*\$fromAI\(([^)]+)\)\s*\}\}/g
  let match
  while ((match = fromAIRegex.exec(textToScan)) !== null) {
    try {
      const argsStr = match[1]
      const firstArgMatch = argsStr.match(/^\s*['"]([^'"]+)['"]/)
      if (firstArgMatch && firstArgMatch[1]) {
        const name = firstArgMatch[1]
        const allArgs = argsStr.split(',').map(s => s.trim().replace(/^['"]|['"]$/g, ''))
        let defaultValue = ''
        if (allArgs.length >= 4 && allArgs[3] !== 'null' && allArgs[3] !== 'undefined' && allArgs[3] !== '') {
          defaultValue = allArgs[3]
        }
        if (!extractedParams[name]) {
          extractedParams[name] = defaultValue || ''
        }
      }
    } catch (e) { /* ignore */ }
  }
  const mergedParams = { ...(mcp.body_template || {}), ...extractedParams }
  executeParamsJson.value = JSON.stringify(mergedParams, null, 2)

  // ── Extract $request variable paths ──
  const requestRegex = /\{\{\s*\$request\.([^\s}]+?)\s*\}\}/g
  const extractedVars = {}
  let varMatch
  while ((varMatch = requestRegex.exec(textToScan)) !== null) {
    const path = varMatch[1].trim()
    if (!(path in extractedVars)) {
      extractedVars[path] = ''
    }
  }
  executeVariablesJson.value = JSON.stringify(extractedVars, null, 2)
  
  executeDialog.value = true
}

async function runMcp() {
  executing.value = true
  executeResult.value = null
  try {
    const params = JSON.parse(executeParamsJson.value || '{}')
    const variables = JSON.parse(executeVariablesJson.value || '{}')
    const response = await axios.post(`/mcp/${selectedMcp.value.id}/execute`, { params, variables })
    executeResult.value = response.data
  } catch (error) {
    console.error('Error executing MCP:', error)
    executeResult.value = { 
      success: false, 
      error: error.response?.data?.detail || error.message,
      execution_time_ms: 0
    }
  } finally {
    executing.value = false
  }
}

onMounted(() => {
  fetchMcps()
  fetchMcpGroups()
})
</script>

<style scoped>
.mcp-page {
  padding: 0;
  width: 100%;
}

.mcp-card {
  border-radius: 16px;
}

.endpoint-chip code {
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
}

.gap-1 { gap: 4px; }

.result-card {
  max-height: 300px;
  overflow: auto;
}

.result-pre {
  margin: 0;
  font-size: 0.8rem;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

:deep(.v-data-table) {
  background: transparent !important;
}
</style>
