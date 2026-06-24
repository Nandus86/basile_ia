<template>
  <div class="workflow-editor-page d-flex flex-column" style="height: calc(100vh - 64px)">
    <!-- Header Toolbar -->
    <v-toolbar color="surface" elevation="2" class="px-4" height="60">
      <v-btn icon @click="goBack" class="mr-2"><v-icon>mdi-arrow-left</v-icon></v-btn>
      <div class="d-flex align-center">
        <v-icon color="primary" class="mr-2">mdi-sitemap</v-icon>
        <v-text-field
          v-if="editingName"
          v-model="workflow.name"
          variant="outlined"
          density="compact"
          hide-details
          autofocus
          class="workflow-name-input mr-2"
          style="max-width: 320px;"
          @keydown.enter="finishEditName"
          @blur="finishEditName"
        ></v-text-field>
        <h2 v-else class="text-h6 mb-0 workflow-name-display" @click="editingName = true" title="Clique para editar">
          {{ workflow.name || 'Carregando...' }}
          <v-icon size="14" class="ml-1 opacity-50">mdi-pencil</v-icon>
        </h2>
      </div>
      <v-spacer></v-spacer>
      <v-chip class="mr-3" :color="saveStatus.color" variant="flat" size="small">
        <v-icon start size="14">{{ saveStatus.icon }}</v-icon>{{ saveStatus.text }}
      </v-chip>
      <v-btn variant="tonal" class="mr-2" @click="openSettings" prepend-icon="mdi-cog">Configurações</v-btn>
      <v-btn variant="tonal" color="info" class="mr-2" @click="showTestDialog = true" prepend-icon="mdi-play-circle">Testar</v-btn>
      <v-btn color="primary" @click="saveDefinition" :loading="saving" prepend-icon="mdi-content-save">Salvar</v-btn>
    </v-toolbar>

    <!-- Main Editor Body -->
    <div class="d-flex flex-grow-1" style="overflow: hidden">
      <!-- Toolbox Sidebar -->
      <v-navigation-drawer permanent location="left" width="260" color="surface-variant" elevation="4">
        <div class="pa-4 text-center border-b">
          <h3 class="text-subtitle-1 font-weight-bold mb-1">
            <v-icon size="20" class="mr-1">mdi-toolbox-outline</v-icon>Blocos
          </h3>
          <p class="text-caption text-medium-emphasis">Arraste para o canvas</p>
        </div>
        <v-list class="pt-0" density="compact">
          <v-list-subheader class="font-weight-bold mt-2">Gatilhos</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'trigger')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Ações</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'action')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Lógica</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'logic')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
          <v-list-subheader class="font-weight-bold mt-2">Utilitários</v-list-subheader>
          <div v-for="t in toolboxItems.filter(i => i.category === 'utility')" :key="t.type"
            class="dndnode text-center ma-2 pa-3 cursor-grab rounded border" :draggable="true"
            @dragstart="onDragStart($event, t.type)">
            <v-icon :color="t.color" class="mb-1">{{ t.icon }}</v-icon>
            <div class="text-subtitle-2">{{ t.label }}</div>
          </div>
        </v-list>
      </v-navigation-drawer>

      <!-- Vue Flow Canvas -->
      <div class="vue-flow-container flex-grow-1" style="position: relative;" @drop="onDrop" @dragover.prevent>
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :node-types="nodeTypes"
          @pane-ready="onPaneReady"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
          @edge-click="onEdgeClick"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          :delete-key-code="['Backspace', 'Delete']"
          :default-edge-options="{ type: 'smoothstep', animated: true, style: { stroke: '#6366F1', strokeWidth: 2 } }"
          :pan-on-drag="[1]"
          :selection-on-drag="true"
          :selection-key-code="true"
          :pan-activation-key-code="'Space'"
        >
          <Background pattern-color="#333" :gap="20" />
          <Controls />
          <MiniMap />
        </VueFlow>

        <!-- Floating Menu for Connection Line Style / Delete -->
        <div
          v-if="showEdgeMenu"
          class="floating-edge-menu pa-2 rounded border"
          :style="{
            position: 'fixed',
            top: `${edgeMenuPosition.y}px`,
            left: `${edgeMenuPosition.x}px`,
            zIndex: 9999,
            background: 'rgba(20, 20, 30, 0.98)',
            borderColor: 'rgba(255,255,255,0.15)',
            boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(10px)',
            minWidth: '220px'
          }"
        >
          <div class="d-flex align-center justify-space-between mb-2 px-1">
            <span class="text-caption font-weight-bold text-medium-emphasis" style="font-size: 9px !important; letter-spacing: 0.5px; color: #9CA3AF !important;">ESTILO DE CONEXÃO</span>
            <v-btn icon variant="text" size="x-small" @click="showEdgeMenu = false"><v-icon size="14">mdi-close</v-icon></v-btn>
          </div>
          <div class="d-flex flex-wrap px-1 mb-2" style="gap: 6px;">
            <div
              v-for="color in connectionColors"
              :key="color.value"
              class="color-dot cursor-pointer"
              :style="{
                backgroundColor: color.value,
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                border: selectedEdge?.style?.stroke === color.value ? '2px solid white' : '1px solid rgba(255,255,255,0.2)',
                boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
                transition: 'transform 0.1s'
              }"
              @click="setEdgeColor(color.value)"
              :title="color.name"
            ></div>
          </div>
          <v-divider class="my-2 border-opacity-25"></v-divider>
          <v-btn
            color="error"
            variant="text"
            block
            size="small"
            density="compact"
            prepend-icon="mdi-trash-can"
            @click="deleteSelectedEdge"
            class="justify-start"
          >
            Excluir Conexão
          </v-btn>
        </div>
      </div>

      <!-- Properties Panel -->
      <v-navigation-drawer :model-value="!!selectedBlock" location="right" :width="drawerWidth" color="surface" elevation="4" class="properties-drawer">
        <div class="d-flex flex-column h-100">
          <div class="pa-2 border-b d-flex align-center justify-space-between bg-surface-variant">
            <v-switch
              v-model="showAdjacentBlocks"
              label="Modo Visão Expandida (Anterior/Próximo)"
              color="primary"
              density="compact"
              hide-details
              class="ml-2"
            ></v-switch>
            <v-btn icon variant="text" size="small" @click="selectedBlock = null"><v-icon>mdi-close</v-icon></v-btn>
          </div>
          
          <div class="d-flex h-100" style="overflow-x: auto; overflow-y: hidden;">
            <!-- Prev Block -->
            <div v-if="showAdjacentBlocks && prevBlock" class="block-column" style="min-width: 450px; flex: 1; border-right: 1px solid rgba(255,255,255,0.1); opacity: 0.9;">
              <div class="pa-1 bg-surface text-center text-caption text-medium-emphasis">
                BLOCO ANTERIOR
                <v-btn size="x-small" variant="text" class="ml-2" @click="selectedBlock = prevBlock">Focar Neste</v-btn>
              </div>
              <BlockPropertiesPanel
                :block="prevBlock"
                :agents="agentsList"
                :webhook-configs="webhooksList"
                :workflows="workflowsList"
                :mcps="mcpsList"
                :information-bases="informationBasesList"
                :current-workflow-id="workflowId"
                :context-keys="availableContextKeys"
                hide-close
                @update="onBlockUpdate"
                @delete="deleteBlock(prevBlock.id)"
                @duplicate="duplicateBlockId(prevBlock.id)"
              />
            </div>

            <!-- Current Block -->
            <div class="block-column" style="min-width: 520px; flex: 1;">
              <div v-if="showAdjacentBlocks" class="pa-1 bg-primary text-center text-caption font-weight-bold">BLOCO ATUAL</div>
              <BlockPropertiesPanel
                v-if="selectedBlock"
                :block="selectedBlock"
                :agents="agentsList"
                :webhook-configs="webhooksList"
                :workflows="workflowsList"
                :mcps="mcpsList"
                :information-bases="informationBasesList"
                :current-workflow-id="workflowId"
                :context-keys="availableContextKeys"
                hide-close
                @update="onBlockUpdate"
                @delete="deleteSelectedBlock"
                @duplicate="duplicateBlock"
              />
            </div>

            <!-- Next Block -->
            <div v-if="showAdjacentBlocks && nextBlock" class="block-column" style="min-width: 450px; flex: 1; border-left: 1px solid rgba(255,255,255,0.1); opacity: 0.9;">
              <div class="pa-1 bg-surface text-center text-caption text-medium-emphasis">
                PRÓXIMO BLOCO
                <v-btn size="x-small" variant="text" class="ml-2" @click="selectedBlock = nextBlock">Focar Neste</v-btn>
              </div>
              <BlockPropertiesPanel
                :block="nextBlock"
                :agents="agentsList"
                :webhook-configs="webhooksList"
                :workflows="workflowsList"
                :mcps="mcpsList"
                :information-bases="informationBasesList"
                :current-workflow-id="workflowId"
                :context-keys="availableContextKeys"
                hide-close
                @update="onBlockUpdate"
                @delete="deleteBlock(nextBlock.id)"
                @duplicate="duplicateBlockId(nextBlock.id)"
              />
            </div>
          </div>
        </div>
      </v-navigation-drawer>
    </div>

    <!-- Test Execution Dialog -->
    <v-dialog v-model="showTestDialog" max-width="750">
      <v-card>
        <v-card-title class="bg-primary text-white d-flex align-center">
          <v-icon class="mr-2">mdi-play-circle</v-icon>Testar Workflow
          <v-spacer></v-spacer>
          <v-btn icon variant="text" color="white" @click="showTestDialog = false"><v-icon>mdi-close</v-icon></v-btn>
        </v-card-title>
        <v-card-text class="pt-4">
          <v-textarea v-model="testPayloadJson" label="Payload de Teste (JSON)" variant="outlined" rows="8"
            placeholder='{"api_base": "https://...", "leader_id": "123", "auth_token": "..."}'
            class="monospace-field"></v-textarea>

          <!-- Status Banner -->
          <v-alert v-if="testResult" :type="testResult.status === 'completed' ? 'success' : testResult.status === 'paused' ? 'warning' : 'error'" variant="tonal" class="mt-3">
            <div class="font-weight-bold mb-1">
              {{ testResult.status === 'completed' ? '✅ Sucesso' : testResult.status === 'paused' ? '⏸️ Workflow Pausado (Aguardando Resposta)' : '❌ Falha' }}
            </div>
            <div class="text-caption">
              {{ testResult.status === 'paused' 
                ? `Pausado no bloco: ${testResult.current_block_id}` 
                : `${testResult.blocks_count} blocos executados em ${testResult.duration_ms}ms` }}
            </div>
            <div v-if="testResult.error" class="text-caption mt-1" style="color: #EF4444">{{ testResult.error }}</div>
          </v-alert>

          <!-- Interactive Resume Panel when workflow is paused -->
          <v-card v-if="testResult && testResult.status === 'paused'" variant="outlined" class="mt-4 pa-4" style="border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.02)">
            <div class="text-subtitle-1 font-weight-bold mb-2">
              <v-icon color="warning" class="mr-1" size="20">mdi-account-question</v-icon>
              {{ choicePrompt }}
            </div>

            <!-- Pre-pause result display -->
            <v-alert v-if="testResult.result" variant="tonal" color="info" density="compact" class="mb-3 text-caption">
              <div class="font-weight-bold mb-1">Última Saída (Antes de Pausar):</div>
              <pre style="white-space: pre-wrap; font-family: monospace; font-size: 11px; max-height: 100px; overflow: auto; margin: 0; color: #A5F3FC;">{{ typeof testResult.result === 'object' ? JSON.stringify(testResult.result, null, 2) : testResult.result }}</pre>
            </v-alert>

            <!-- Render choices if available -->
            <div v-if="hasChoices" class="d-flex flex-wrap gap-2 mb-3 mt-2">
              <v-btn
                v-for="(choice, idx) in choicesList"
                :key="idx"
                color="primary"
                variant="flat"
                class="mr-2 mb-2"
                @click="submitSimulatedResponse(choice.value)"
                :loading="resuming"
              >
                {{ choice.label }}
              </v-btn>
            </div>

            <!-- Custom / text input response -->
            <div class="d-flex flex-column mt-2">
              <div v-if="hasChoices" class="text-caption text-medium-emphasis mb-2">Ou envie uma resposta personalizada:</div>
              <div class="d-flex align-center">
                <v-text-field
                  v-model="simulatedInputText"
                  label="Resposta Simulada"
                  variant="outlined"
                  density="compact"
                  hide-details
                  placeholder="Digite sua resposta aqui..."
                  @keydown.enter="submitSimulatedResponse(simulatedInputText)"
                  class="flex-grow-1"
                ></v-text-field>
                <v-btn
                  color="warning"
                  @click="submitSimulatedResponse(simulatedInputText)"
                  :loading="resuming"
                  prepend-icon="mdi-send"
                  height="40"
                  class="ml-3"
                >
                  Enviar
                </v-btn>
              </div>
            </div>
          </v-card>

          <!-- Tabs: Resultado Final vs Log Completo -->
          <v-tabs v-if="testResult && (testResult.status === 'completed' || testResult.status === 'paused')" v-model="testResultTab" class="mt-4" color="primary" density="compact">
            <v-tab value="final">
              <v-icon start size="16">mdi-target</v-icon>
              {{ testResult.status === 'completed' ? 'Resultado Final' : 'Resultado Atual (Pausa)' }}
            </v-tab>
            <v-tab value="log">
              <v-icon start size="16">mdi-format-list-bulleted</v-icon>
              Log da Execução
            </v-tab>
          </v-tabs>

          <v-window v-if="testResult && (testResult.status === 'completed' || testResult.status === 'paused')" v-model="testResultTab" class="mt-3">
            <!-- Tab: Resultado Final (last block output only) -->
            <v-window-item value="final">
              <v-alert type="info" variant="tonal" density="compact" class="mb-3">
                <v-icon start size="14">mdi-information</v-icon>
                {{ testResult.status === 'completed' 
                  ? 'Este é o resultado final da execução (saída do último bloco).' 
                  : 'Este é o resultado gerado até a pausa (saída do bloco anterior ao Aguardar Resposta).' }}
              </v-alert>
              <div v-if="testResult.result" class="result-box pa-3 rounded">
                <pre class="text-body-2" style="white-space: pre-wrap; overflow: auto; max-height: 400px; margin: 0;">{{ JSON.stringify(testResult.result, null, 2) }}</pre>
              </div>
              <v-alert v-else type="warning" variant="tonal" density="compact">
                Nenhum resultado de saída gerado.
              </v-alert>
            </v-window-item>

            <!-- Tab: Log Completo (all blocks + full context) -->
            <v-window-item value="log">
              <v-expansion-panels v-if="testResult.blocks && testResult.blocks.length" variant="accordion">
                <v-expansion-panel v-for="(b, i) in testResult.blocks" :key="i">
                  <v-expansion-panel-title>
                    <v-icon :color="b.status === 'success' ? 'green' : 'red'" size="16" class="mr-2">
                      {{ b.status === 'success' ? 'mdi-check-circle' : 'mdi-close-circle' }}
                    </v-icon>
                    {{ b.label || b.block_id }} ({{ b.block_type }}) — {{ b.duration_ms }}ms
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="text-caption" style="white-space: pre-wrap; max-height: 200px; overflow: auto">{{ JSON.stringify(b, null, 2) }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <!-- Full Context -->
              <v-expansion-panels class="mt-3">
                <v-expansion-panel>
                  <v-expansion-panel-title>
                    <v-icon size="16" class="mr-2">mdi-database</v-icon>
                    Contexto Completo (todos os blocos)
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="text-caption" style="white-space: pre-wrap; max-height: 400px; overflow: auto">{{ JSON.stringify(testResult.context, null, 2) }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-window-item>
          </v-window>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showTestDialog = false">Fechar</v-btn>
          <v-btn color="primary" @click="runTest" :loading="testing" prepend-icon="mdi-play">Executar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Workflow Settings Dialog -->
    <v-dialog v-model="showSettingsDialog" max-width="600px">
      <v-card>
        <v-card-title class="bg-surface-variant d-flex align-center">
          <v-icon class="mr-2">mdi-cog</v-icon>
          Configurações do Workflow
        </v-card-title>
        <v-card-text class="pt-4">
          <v-alert
            type="info"
            variant="tonal"
            class="mb-4"
            text="Estas configurações definem como este workflow se comporta quando vinculado a um Agente."
          ></v-alert>

          <v-switch
            v-model="workflow.always_run_on_startup"
            color="primary"
            label="Executar no Início do Agente (Auto-run / Pre-hook)"
            hint="Se ativado, quando o agente for acionado, este workflow será executado automaticamente ANTES do agente 'pensar', e o resultado será injetado no contexto dele."
            persistent-hint
            class="mb-4"
            @update:model-value="markUnsaved"
          ></v-switch>

          <v-divider class="mb-4"></v-divider>

          <div class="text-subtitle-2 font-weight-bold mb-2">
            <v-icon size="18" class="mr-1">mdi-key-variant</v-icon>
            Gatilho por Palavras-Chave (Bypass Agente)
          </div>
          <p class="text-caption text-medium-emphasis mb-3">
            Se alguma destas palavras for detectada na mensagem do usuário, o Agente será ignorado e este Workflow executado diretamente.
          </p>

          <v-combobox
            v-model="workflow.trigger_keywords"
            label="Palavras-Chave"
            multiple
            chips
            closable-chips
            variant="outlined"
            density="compact"
            placeholder="Digite e pressione Enter"
            hint="Ex: faturas, boleto, suporte"
            persistent-hint
            class="mb-4"
            @update:model-value="markUnsaved"
          ></v-combobox>

          <v-select
            v-model="workflow.trigger_match_mode"
            label="Modo de Comparação"
            :items="[
              { title: 'Palavra Exata', value: 'word' },
              { title: 'Contém', value: 'contains' },
              { title: 'Frase Exata', value: 'phrase' }
            ]"
            variant="outlined"
            density="compact"
            @update:model-value="markUnsaved"
          ></v-select>
          <v-divider class="my-4"></v-divider>

          <v-switch
            v-model="workflow.return_direct_payload"
            color="deep-purple"
            label="Retornar Payload Direto"
            hint="Se ativado, retorna o JSON final bruto da automação na API (bypass/keywords)"
            persistent-hint
            class="mb-2"
            @update:model-value="markUnsaved"
          ></v-switch>
        </v-card-text>
        <v-card-actions class="pa-4 bg-surface-variant">
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="showSettingsDialog = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, markRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from '@/plugins/axios'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'
import BlockPropertiesPanel from '@/components/workflow/BlockPropertiesPanel.vue'

const router = useRouter()
const route = useRoute()
const workflowId = route.params.id

const { project, getSelectedNodes } = useVueFlow()
const vueFlowInstance = ref(null)

const workflow = ref({})
const nodes = ref([])
const edges = ref([])
const agentsList = ref([])
const webhooksList = ref([])
const workflowsList = ref([])
const mcpsList = ref([])
const informationBasesList = ref([])
const saving = ref(false)
const selectedBlock = ref(null)
const saveStatus = ref({ text: 'Salvo', color: 'success', icon: 'mdi-check' })
const editingName = ref(false)
const showSettingsDialog = ref(false)
const showTestDialog = ref(false)
const testPayloadJson = ref('{\n  \n}')
const testResult = ref(null)
const testing = ref(false)
const testResultTab = ref('final')
const showAdjacentBlocks = ref(false)

// Floating edge styling menu variables
const selectedEdge = ref(null)
const edgeMenuPosition = ref({ x: 0, y: 0 })
const showEdgeMenu = ref(false)
const connectionColors = [
  { name: 'Padrão', value: '#6366F1' },   // Indigo
  { name: 'Verde', value: '#10B981' },    // Green
  { name: 'Vermelho', value: '#EF4444' },  // Red
  { name: 'Azul', value: '#3B82F6' },     // Blue
  { name: 'Amarelo', value: '#F59E0B' },  // Amber/Yellow
  { name: 'Laranja', value: '#F97316' },  // Orange
  { name: 'Rosa', value: '#EC4899' },     // Pink
  { name: 'Roxo', value: '#8B5CF6' },     // Purple
  { name: 'Cinza', value: '#9CA3AF' }      // Grey
]

// Paused workflow test resumption variables
const resuming = ref(false)
const simulatedInputText = ref('')

const hasChoices = computed(() => {
  const result = testResult.value?.result
  return result && typeof result === 'object' && Array.isArray(result.choices)
})

const choicesList = computed(() => {
  if (!hasChoices.value) return []
  return testResult.value.result.choices.map(c => {
    if (typeof c === 'string' && c.includes('|')) {
      const parts = c.split('|')
      return { label: parts[0], value: parts[1], raw: c }
    }
    return { label: String(c), value: String(c), raw: c }
  })
})

const choicePrompt = computed(() => {
  return testResult.value?.result?.response || 'O workflow está aguardando uma resposta:'
})

let idCounter = 1

const nodeTypes = { workflow: markRaw(WorkflowNode) }

const toolboxItems = [
  { type: 'trigger', label: 'Gatilho', icon: 'mdi-lightning-bolt', color: '#F59E0B', category: 'trigger' },
  { type: 'http_request', label: 'HTTP Request', icon: 'mdi-api', color: '#3B82F6', category: 'action' },
  { type: 'agent', label: 'Agente IA', icon: 'mdi-robot', color: '#10B981', category: 'action' },
  { type: 'mcp', label: 'MCP', icon: 'mdi-connection', color: '#14B8A6', category: 'action' },
  { type: 'vector_insert', label: 'Salvar na Base', icon: 'mdi-database-plus', color: '#10B981', category: 'action' },
  { type: 'python', label: 'Python', icon: 'mdi-language-python', color: '#3B82F6', category: 'action' },
  { type: 'wait_input', label: 'Aguardar Resposta', icon: 'mdi-account-question', color: '#EC4899', category: 'action' },
  { type: 'response', label: 'Saída', icon: 'mdi-logout', color: '#EC4899', category: 'action' },
  { type: 'sub_workflow', label: 'Sub-workflow', icon: 'mdi-sitemap-outline', color: '#EC4899', category: 'action' },
  { type: 'if', label: 'IF (Condição)', icon: 'mdi-call-split', color: '#8B5CF6', category: 'logic' },
  { type: 'router', label: 'Router', icon: 'mdi-source-branch', color: '#8B5CF6', category: 'logic' },
  { type: 'filter', label: 'Filter', icon: 'mdi-filter-variant', color: '#06B6D4', category: 'logic' },
  { type: 'transform', label: 'Transform', icon: 'mdi-swap-horizontal', color: '#F97316', category: 'utility' },
  { type: 'delay', label: 'Delay', icon: 'mdi-timer-sand', color: '#6B7280', category: 'utility' },
  { type: 'variables', label: 'Variáveis', icon: 'mdi-variable', color: '#10B981', category: 'utility' },
]

const availableContextKeys = computed(() => {
  const keys = ['trigger']
  for (const node of nodes.value) {
    const outputKey = node.data?.config?.output_key || node.id
    if (outputKey && !keys.includes(outputKey)) keys.push(outputKey)
  }
  return keys
})

const previousBlocks = computed(() => {
  if (!selectedBlock.value) return []
  const sources = edges.value.filter(e => e.target === selectedBlock.value.id).map(e => e.source)
  return nodes.value.filter(n => sources.includes(n.id)).map(n => ({ id: n.id, ...n.data }))
})

const nextBlocks = computed(() => {
  if (!selectedBlock.value) return []
  const targets = edges.value.filter(e => e.source === selectedBlock.value.id).map(e => e.target)
  return nodes.value.filter(n => targets.includes(n.id)).map(n => ({ id: n.id, ...n.data }))
})

const prevBlock = computed(() => previousBlocks.value[0] || null)
const nextBlock = computed(() => nextBlocks.value[0] || null)

const drawerWidth = computed(() => {
  if (!showAdjacentBlocks.value) return 520
  let w = 520
  if (prevBlock.value) w += 450
  if (nextBlock.value) w += 450
  return w
})

const clipboard = ref([])

const handleKeyDown = (event) => {
  const activeEl = document.activeElement
  if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {
    return
  }
  const isCtrl = event.ctrlKey || event.metaKey
  if (isCtrl && event.key === 'c') {
    event.preventDefault()
    copySelectedNodes()
  } else if (isCtrl && event.key === 'v') {
    event.preventDefault()
    pasteCopiedNodes()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleKeyDown)
  await Promise.all([fetchAgents(), fetchWebhooks(), fetchWorkflows(), fetchMcps(), fetchInformationBases(), loadWorkflow()])
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

function copySelectedNodes() {
  const selected = getSelectedNodes.value
  if (!selected.length) return
  const dataToCopy = selected.map(node => ({
    type: node.type,
    label: node.label,
    position: { ...node.position },
    data: JSON.parse(JSON.stringify(node.data))
  }))
  clipboard.value = dataToCopy
  try {
    localStorage.setItem('workflow_clipboard', JSON.stringify(dataToCopy))
  } catch(e) {
    console.warn("Failed to save to localStorage", e)
  }
}

function pasteCopiedNodes() {
  let pasteData = clipboard.value
  if (!pasteData || !pasteData.length) {
    try {
      const stored = localStorage.getItem('workflow_clipboard')
      if (stored) {
        pasteData = JSON.parse(stored)
      }
    } catch(e){}
  }
  if (!pasteData || !pasteData.length) return

  const newNodes = []
  nodes.value.forEach(n => {
    n.selected = false
  })
  pasteData.forEach(item => {
    const newId = `block_${idCounter++}`
    const newNode = {
      id: newId,
      type: item.type,
      position: {
        x: item.position.x + 40,
        y: item.position.y + 40
      },
      label: `${item.label || item.data?.label || 'Bloco'} (cópia)`,
      selected: true,
      data: {
        type: item.data.type,
        label: `${item.data.label || item.label || 'Bloco'} (cópia)`,
        config: JSON.parse(JSON.stringify({ ...item.data.config, output_key: newId }))
      }
    }
    newNodes.push(newNode)
  })
  nodes.value = [...nodes.value, ...newNodes]
  if (newNodes.length === 1) {
    selectedBlock.value = { id: newNodes[0].id, ...newNodes[0].data }
  } else {
    selectedBlock.value = null
  }
  markUnsaved()
}

async function fetchAgents() {
  try { agentsList.value = (await axios.get('/agents')).data.agents || [] } catch {}
}
async function fetchWebhooks() {
  try { webhooksList.value = (await axios.get('/webhooks-config')).data.webhook_configs || [] } catch {}
}
async function fetchWorkflows() {
  try { workflowsList.value = (await axios.get('/workflows')).data.workflows || [] } catch {}
}
async function fetchMcps() {
  try { mcpsList.value = (await axios.get('/mcp')).data.mcps || [] } catch {}
}
async function fetchInformationBases() {
  try { informationBasesList.value = (await axios.get('/information-bases')).data.information_bases || [] } catch {}
}

async function loadWorkflow() {
  try {
    const res = await axios.get(`/workflows/${workflowId}`)
    workflow.value = res.data.workflow || res.data
    
    // Ensure definition.settings is always initialized (fixes toggle reset on reload)
    if (!workflow.value.definition) workflow.value.definition = {}
    if (!workflow.value.definition.settings) {
      workflow.value.definition.settings = { auto_run: false }
    }
    // Ensure return_direct_payload has a boolean value (DB column, not inside definition)
    if (workflow.value.return_direct_payload === undefined || workflow.value.return_direct_payload === null) {
      workflow.value.return_direct_payload = false
    }
    // Ensure always_run_on_startup has a boolean value
    if (workflow.value.always_run_on_startup === undefined || workflow.value.always_run_on_startup === null) {
      workflow.value.always_run_on_startup = false
    }
    
    const def = workflow.value.definition || {}
    if (def.blocks && def.edges) {
      // v2 format
      nodes.value = def.blocks.map(b => ({
        id: b.id,
        type: 'workflow',
        position: b.position || { x: 0, y: 0 },
        label: b.label || b.type,
        data: { type: b.type, config: b.config || {}, label: b.label },
      }))
      edges.value = def.edges.map((e, i) => {
        const sourceHandleVal = e.sourceHandle || e.label || null;
        const defaultColor = (sourceHandleVal === 'true' || sourceHandleVal === 'match')
          ? '#10B981'
          : (sourceHandleVal === 'false' || sourceHandleVal === 'default')
            ? '#EF4444'
            : '#6366F1';
        return {
          id: e.id || `e-${i}`,
          source: e.source,
          target: e.target,
          sourceHandle: sourceHandleVal,
          label: e.label || '',
          type: 'smoothstep',
          animated: true,
          style: e.style || { stroke: defaultColor, strokeWidth: 2 },
        }
      })
      // Update counter
      for (const n of nodes.value) {
        const num = parseInt(n.id.split('_').pop())
        if (!isNaN(num) && num >= idCounter) idCounter = num + 1
      }
    } else if (def.elements) {
      // Legacy v1 format
      nodes.value = def.elements.filter(e => !e.source).map(e => ({
        id: e.id, type: 'workflow', position: e.position || { x: 0, y: 0 },
        label: e.label || '', data: e.data || {},
      }))
      edges.value = def.elements.filter(e => e.source).map(e => ({
        id: e.id, source: e.source, target: e.target, type: 'smoothstep', animated: true,
        style: { stroke: '#6366F1', strokeWidth: 2 },
      }))
    }
  } catch (e) { console.error("Failed to load workflow", e) }
}

const onPaneReady = (instance) => { vueFlowInstance.value = instance; instance.fitView() }
const onDragStart = (event, type) => {
  event.dataTransfer.setData('application/vueflow', type)
  event.dataTransfer.effectAllowed = 'move'
}

function onDrop(event) {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/vueflow')
  if (!type || !vueFlowInstance.value) return
  const position = project({ x: event.clientX - 260, y: event.clientY - 60 })
  const blockId = `block_${idCounter++}`
  const label = toolboxItems.find(t => t.type === type)?.label || type
  
  const config = { output_key: blockId }
  if (type === 'trigger') {
    config.trigger_type = 'event'
  }
  
  nodes.value = [...nodes.value, {
    id: blockId, type: 'workflow', position,
    label, data: { type, config, label },
  }]
  markUnsaved()
}

function onConnect(params) {
  const edgeId = `e-${params.source}-${params.target}-${params.sourceHandle || 'default'}`
  const label = params.sourceHandle || ''
  const defaultColor = (params.sourceHandle === 'true' || params.sourceHandle === 'match')
    ? '#10B981'
    : (params.sourceHandle === 'false' || params.sourceHandle === 'default')
      ? '#EF4444'
      : '#6366F1';
  edges.value = [...edges.value, {
    id: edgeId, source: params.source, target: params.target,
    sourceHandle: params.sourceHandle, label,
    type: 'smoothstep', animated: true,
    style: { stroke: defaultColor, strokeWidth: 2 },
  }]
  markUnsaved()
}

function onNodesChange(changes) {
  for (const c of changes) {
    if (c.type === 'position' && c.position) {
      const node = nodes.value.find(n => n.id === c.id)
      if (node) { node.position = c.position; markUnsaved() }
    }
    if (c.type === 'remove') {
      nodes.value = nodes.value.filter(n => n.id !== c.id)
      edges.value = edges.value.filter(e => e.source !== c.id && e.target !== c.id)
      if (selectedBlock.value && selectedBlock.value.id === c.id) selectedBlock.value = null
      markUnsaved()
    }
  }
}
function onEdgesChange(changes) {
  for (const c of changes) {
    if (c.type === 'remove') {
      edges.value = edges.value.filter(e => e.id !== c.id)
      markUnsaved()
    }
  }
}

function onNodeClick({ node }) {
  selectedBlock.value = { id: node.id, ...node.data }
  showEdgeMenu.value = false
}
function onPaneClick() { 
  selectedBlock.value = null
  showEdgeMenu.value = false
}

function onEdgeClick({ event, edge }) {
  event.stopPropagation()
  selectedEdge.value = edge
  edgeMenuPosition.value = { x: event.clientX, y: event.clientY }
  showEdgeMenu.value = true
}

function setEdgeColor(color) {
  if (!selectedEdge.value) return
  const edge = edges.value.find(e => e.id === selectedEdge.value.id)
  if (edge) {
    edge.style = { stroke: color, strokeWidth: 3 }
    markUnsaved()
  }
  showEdgeMenu.value = false
}

function deleteSelectedEdge() {
  if (!selectedEdge.value) return
  edges.value = edges.value.filter(e => e.id !== selectedEdge.value.id)
  selectedEdge.value = null
  showEdgeMenu.value = false
  markUnsaved()
}

function onBlockUpdate(block) {
  const node = nodes.value.find(n => n.id === block.id)
  if (node) {
    node.data = { ...block }
    node.label = block.label || node.label
  }
  markUnsaved()
}

function deleteSelectedBlock() {
  if (!selectedBlock.value) return
  deleteBlock(selectedBlock.value.id)
}

function deleteBlock(id) {
  nodes.value = nodes.value.filter(n => n.id !== id)
  edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
  if (selectedBlock.value && selectedBlock.value.id === id) selectedBlock.value = null
  markUnsaved()
}

function duplicateBlock() {
  if (!selectedBlock.value) return
  duplicateBlockId(selectedBlock.value.id)
}

function duplicateBlockId(id) {
  const sourceNode = nodes.value.find(n => n.id === id)
  if (!sourceNode) return
  const newId = `block_${idCounter++}`
  const newNode = {
    id: newId,
    type: 'workflow',
    position: { x: sourceNode.position.x + 60, y: sourceNode.position.y + 80 },
    label: `${sourceNode.label || sourceNode.data.label || 'Bloco'} (cópia)`,
    data: {
      type: sourceNode.data.type,
      config: JSON.parse(JSON.stringify({ ...sourceNode.data.config, output_key: newId })),
      label: `${sourceNode.data.label || sourceNode.label || 'Bloco'} (cópia)`,
    },
  }
  nodes.value = [...nodes.value, newNode]
  selectedBlock.value = { id: newNode.id, ...newNode.data }
  markUnsaved()
}

function markUnsaved() { saveStatus.value = { text: 'Não Salvo', color: 'warning', icon: 'mdi-alert-circle' } }

function finishEditName() {
  editingName.value = false
  markUnsaved()
}

function openSettings() {
  if (!workflow.value.definition.settings) {
    workflow.value.definition.settings = { auto_run: false }
  }
  showSettingsDialog.value = true
}

async function saveDefinition() {
  try {
    saving.value = true
    const blocks = nodes.value.map(n => ({
      id: n.id, type: n.data.type, label: n.data.label || n.label,
      position: n.position, config: n.data.config || {},
    }))
    const edgesDef = edges.value.map(e => ({
      id: e.id, source: e.source, target: e.target,
      sourceHandle: e.sourceHandle || null, label: e.label || '',
      style: e.style || null,
    }))
    const definition = { 
        version: '2.0', 
        blocks, 
        edges: edgesDef, 
        variables: workflow.value.definition?.variables || {},
        settings: workflow.value.definition?.settings || { auto_run: false }
    }
    await axios.put(`/workflows/${workflowId}`, {
      name: workflow.value.name, description: workflow.value.description,
      is_active: workflow.value.is_active,
      trigger_keywords: workflow.value.trigger_keywords || [],
      trigger_match_mode: workflow.value.trigger_match_mode || 'word',
      always_run_on_startup: workflow.value.always_run_on_startup ?? false,
      return_direct_payload: workflow.value.return_direct_payload ?? false,
      definition
    })
    saveStatus.value = { text: 'Salvo', color: 'success', icon: 'mdi-check' }
  } catch (e) {
    console.error(e)
    saveStatus.value = { text: 'Erro ao Salvar', color: 'error', icon: 'mdi-close-circle' }
  } finally { saving.value = false }
}

async function runTest() {
  testing.value = true; testResult.value = null; testResultTab.value = 'final'; simulatedInputText.value = ''
  try {
    await saveDefinition()
    let payload = {}
    try { payload = JSON.parse(testPayloadJson.value) } catch {}
    const res = await axios.post(`/workflows/${workflowId}/execute`, { trigger_data: payload })
    const exec = res.data
    testResult.value = {
      status: exec.status, duration_ms: exec.duration_ms,
      blocks_count: (exec.blocks_executed || []).length,
      blocks: exec.blocks_executed || [], error: exec.error_message,
      result: exec.result,
      context: exec.context || {},
      execution_id: exec.id,
      current_block_id: exec.current_block_id,
    }
  } catch (e) {
    testResult.value = { status: 'failed', error: e.response?.data?.detail || e.message, blocks_count: 0, duration_ms: 0 }
  } finally { testing.value = false }
}

async function submitSimulatedResponse(responseVal) {
  if (!responseVal || !testResult.value || !testResult.value.execution_id) return
  resuming.value = true
  try {
    const execId = testResult.value.execution_id
    // Mirror production resume format: include button_response in global/system.
    // To prevent payload.update() from shallow-replacing and wiping the URLs,
    // we merge with the existing global/system objects from the paused context.
    const triggerPayload = testResult.value.context['$trigger']?.payload || {}
    const existingGlobal = triggerPayload.global || {}
    const existingSystem = triggerPayload.system || {}
    
    const payload = {
      trigger_data: {
        message: responseVal,
        button_response: responseVal,
        global: { ...existingGlobal, button_response: responseVal },
        system: { ...existingSystem, button_response: responseVal },
      }
    }
    const res = await axios.post(`/workflows/executions/${execId}/resume`, payload)
    const exec = res.data
    testResult.value = {
      status: exec.status, duration_ms: exec.duration_ms,
      blocks_count: (exec.blocks_executed || []).length,
      blocks: exec.blocks_executed || [], error: exec.error_message,
      result: exec.result,
      context: exec.context || {},
      execution_id: exec.id,
      current_block_id: exec.current_block_id,
    }
    simulatedInputText.value = ''
  } catch (e) {
    testResult.value = {
      ...testResult.value,
      status: 'failed',
      error: e.response?.data?.detail || e.message
    }
  } finally {
    resuming.value = false
  }
}

function goBack() { router.push('/workflows') }
</script>

<style scoped>
.workflow-editor-page { background-color: #0F0F17; }
.dndnode { border: 1px solid rgba(255,255,255,0.15); transition: all 0.2s ease; user-select: none; color: #ffffff !important; }
.dndnode .text-subtitle-2 { color: #ffffff !important; }
.dndnode:hover { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.4); transform: translateY(-2px); }
.properties-drawer { border-left: 1px solid rgba(255,255,255,0.1); }
.monospace-field :deep(textarea) { font-family: 'JetBrains Mono', monospace !important; font-size: 12px !important; }
.workflow-name-display { cursor: pointer; transition: opacity 0.2s; }
.workflow-name-display:hover { opacity: 0.75; }
.workflow-name-input :deep(.v-field) { font-size: 1.25rem; font-weight: bold; }
.result-box {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(99, 102, 241, 0.3);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.result-box pre { color: #A5F3FC; }
</style>
