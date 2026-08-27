<template>
  <div class="properties-panel d-flex flex-column h-100 bg-surface">
    <!-- Header -->
    <div class="panel-header d-flex align-center justify-space-between pa-4 border-b">
      <div class="d-flex align-center ga-2">
        <v-icon :color="nodeColor" size="20">{{ nodeIcon }}</v-icon>
        <div>
          <h3 class="text-subtitle-1 font-weight-bold mb-0">{{ nodeTitle }}</h3>
          <span class="text-caption text-medium-emphasis">{{ nodeTypeLabel }}</span>
        </div>
      </div>
      <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')"></v-btn>
    </div>

    <!-- Scrollable Content -->
    <div class="panel-body flex-grow-1 overflow-y-auto pa-4">
      <!-- General Label -->
      <v-text-field
        v-model="nodeData.label"
        label="Rótulo do Nó"
        variant="outlined"
        density="compact"
        class="mb-3"
        hint="Nome de exibição no diagrama"
        persistent-hint
      ></v-text-field>

      <v-textarea
        v-model="nodeData.description"
        label="Descrição / Anotações"
        variant="outlined"
        density="compact"
        rows="2"
        class="mb-4"
        hide-details
      ></v-textarea>

      <v-divider class="my-3"></v-divider>

      <!-- ── 1. AGENT NODE PROPERTIES ─────────────────────────────────── -->
      <div v-if="nodeType === 'agent'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="primary">mdi-robot</v-icon>Configuração do Especialista
        </h4>

        <v-autocomplete
          v-model="nodeConfig.agent_id"
          :items="availableAgents"
          item-title="name"
          item-value="id"
          label="Selecionar Agente do Sistema"
          variant="outlined"
          density="compact"
          class="mb-3"
          prepend-inner-icon="mdi-account-tie"
          @update:model-value="onAgentSelect"
        >
          <template v-slot:item="{ props, item }">
            <v-list-item v-bind="props" :subtitle="item.raw.model || 'gpt-4o-mini'"></v-list-item>
          </template>
        </v-autocomplete>

        <v-text-field
          v-model="nodeConfig.agent_name"
          label="Nome do Agente"
          variant="outlined"
          density="compact"
          readonly
          class="mb-3"
          disabled
        ></v-text-field>

        <v-textarea
          v-model="nodeConfig.prompt_override"
          label="Instrução Adicional (Opcional)"
          variant="outlined"
          density="compact"
          rows="3"
          placeholder="Instruções específicas para o comportamento deste agente neste grafo..."
          hint="Será anexado ao prompt original do agente"
          persistent-hint
        ></v-textarea>
      </div>

      <!-- ── 2. ROUTER / SUPERVISOR NODE PROPERTIES ───────────────────── -->
      <div v-else-if="nodeType === 'router' || nodeType === 'supervisor'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="purple">mdi-source-branch</v-icon>Instruções de Roteamento
        </h4>
        <v-textarea
          v-model="nodeConfig.prompt"
          label="Prompt do Supervisor"
          variant="outlined"
          density="compact"
          rows="5"
          placeholder="Ex: Analise a intenção da mensagem e direcione para o especialista correto com base nas regras..."
          hint="O supervisor analisará a mensagem e escolherá o próximo nó"
          persistent-hint
        ></v-textarea>
      </div>

      <!-- ── 3. PARALLEL FAN-OUT NODE PROPERTIES ──────────────────────── -->
      <div v-else-if="nodeType === 'parallel'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="cyan">mdi-call-split</v-icon>Execução Paralela (Fan-Out)
        </h4>
        <v-alert type="info" variant="tonal" density="compact" class="text-caption mb-3">
          Todos os nós conectados à saída deste bloco serão disparados <strong>simultaneamente</strong> via <code>asyncio.gather</code>.
        </v-alert>
      </div>

      <!-- ── 4. SYNTHESIZER FAN-IN NODE PROPERTIES ────────────────────── -->
      <div v-else-if="nodeType === 'synthesizer'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="pink">mdi-call-merge</v-icon>Sintetizador de Respostas
        </h4>
        <v-textarea
          v-model="nodeConfig.prompt"
          label="Prompt de Consolidação"
          variant="outlined"
          density="compact"
          rows="4"
          placeholder="Você é o Sintetizador. Consolide as respostas dos especialistas em uma única mensagem clara..."
          hint="Unifica as saídas paralelas em uma resposta coesa"
          persistent-hint
        ></v-textarea>
      </div>

      <!-- ── 5. CONDITION / DECISION NODE PROPERTIES ──────────────────── -->
      <div v-else-if="nodeType === 'condition' || nodeType === 'decision'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="amber">mdi-help-rhombus</v-icon>Regra de Ramificação
        </h4>

        <v-select
          v-model="nodeConfig.mode"
          :items="[
            { title: 'Avaliação via LLM (IA)', value: 'llm' },
            { title: 'Contém Palavras-chave', value: 'keyword' },
            { title: 'Expressão Regular (Regex)', value: 'regex' }
          ]"
          label="Tipo de Condição"
          variant="outlined"
          density="compact"
          class="mb-3"
        ></v-select>

        <v-textarea
          v-if="nodeConfig.mode === 'llm' || !nodeConfig.mode"
          v-model="nodeConfig.criteria"
          label="Critério de Avaliação (Pergunta Sim/Não)"
          variant="outlined"
          density="compact"
          rows="3"
          placeholder="Ex: O usuário solicitou informações financeiras ou relatórios?"
        ></v-textarea>

        <v-combobox
          v-else-if="nodeConfig.mode === 'keyword'"
          v-model="nodeConfig.keywords"
          label="Palavras-chave (Pressione Enter)"
          multiple
          chips
          closable-chips
          variant="outlined"
          density="compact"
        ></v-combobox>

        <v-text-field
          v-else-if="nodeConfig.mode === 'regex'"
          v-model="nodeConfig.regex"
          label="Padrão Regex"
          variant="outlined"
          density="compact"
          placeholder="Ex: \b(relatorio|financeiro)\b"
        ></v-text-field>
      </div>

      <!-- ── 6. VERIFIER / GUARDRAIL (LOOP) NODE PROPERTIES ───────────── -->
      <div v-else-if="nodeType === 'verifier' || nodeType === 'guardrail'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="amber-darken-2">mdi-shield-check</v-icon>Verificador de Qualidade & Loop
        </h4>

        <v-textarea
          v-model="nodeConfig.criteria"
          label="Critério de Validação"
          variant="outlined"
          density="compact"
          rows="3"
          placeholder="Ex: Verifique se a resposta respondeu de forma acolhedora, precisa e sem alucinações."
          class="mb-3"
        ></v-textarea>

        <v-slider
          v-model="nodeConfig.max_retries"
          label="Máximo de Tentativas (Loops)"
          min="1"
          max="5"
          step="1"
          thumb-label="always"
          color="amber-darken-1"
          class="mt-4"
        ></v-slider>
        <span class="text-caption text-medium-emphasis">
          Se a resposta for rejeitada, ela retorna pela saída <strong>Loop Refazer</strong> com as instruções de correção até atingir o limite.
        </span>
      </div>

      <!-- ── 7. TOOL / ACTION NODE PROPERTIES ─────────────────────────── -->
      <div v-else-if="nodeType === 'tool' || nodeType === 'action'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="teal">mdi-tools</v-icon>Ação / Ferramenta
        </h4>
        <v-select
          v-model="nodeConfig.action_type"
          :items="['mcp_tool', 'http_webhook', 'custom_python']"
          label="Tipo de Ação"
          variant="outlined"
          density="compact"
          class="mb-3"
        ></v-select>
      </div>
    </div>

    <!-- Footer Actions -->
    <div class="panel-footer pa-4 border-t d-flex align-center justify-space-between">
      <v-btn
        color="error"
        variant="tonal"
        size="small"
        prepend-icon="mdi-trash-can-outline"
        @click="$emit('delete', selectedNode.id)"
      >
        Excluir Nó
      </v-btn>

      <v-btn
        color="primary"
        variant="flat"
        size="small"
        prepend-icon="mdi-check"
        @click="$emit('close')"
      >
        Concluído
      </v-btn>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import axios from '@/plugins/axios'

const props = defineProps({
  selectedNode: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'delete'])

const availableAgents = ref([])

const nodeData = computed(() => {
  if (!props.selectedNode.data) props.selectedNode.data = {}
  return props.selectedNode.data
})

const nodeConfig = computed(() => {
  if (!nodeData.value.config) nodeData.value.config = {}
  return nodeData.value.config
})

const nodeType = computed(() => nodeData.value.type || 'agent')
const nodeTitle = computed(() => nodeData.value.label || 'Configurar Nó')

const NODE_META = {
  start:        { icon: 'mdi-play-circle',       color: '#10B981', label: 'Início / Trigger' },
  agent:        { icon: 'mdi-robot',             color: '#3B82F6', label: 'Agente Especialista' },
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Supervisor / Router' },
  supervisor:   { icon: 'mdi-account-supervisor', color: '#8B5CF6', label: 'Supervisor / Router' },
  parallel:     { icon: 'mdi-call-split',        color: '#06B6D4', label: 'Fan-Out Paralelo' },
  synthesizer:  { icon: 'mdi-call-merge',        color: '#EC4899', label: 'Sintetizador Fan-In' },
  condition:    { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  decision:     { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  verifier:     { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  guardrail:    { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Verificador (Loop)' },
  tool:         { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  action:       { icon: 'mdi-tools',             color: '#14B8A6', label: 'Ferramenta / Ação' },
  end:          { icon: 'mdi-stop-circle',       color: '#64748B', label: 'Fim / Resposta' },
}

const meta = computed(() => NODE_META[nodeType.value] || { icon: 'mdi-cube-outline', color: '#94A3B8', label: 'Bloco' })
const nodeIcon = computed(() => meta.value.icon)
const nodeColor = computed(() => meta.value.color)
const nodeTypeLabel = computed(() => meta.value.label)

const fetchAgents = async () => {
  try {
    const res = await axios.get('/agents?limit=200')
    availableAgents.value = res.data.agents || []
  } catch (e) {
    console.error('Erro ao buscar agentes:', e)
  }
}

const onAgentSelect = (agentId) => {
  const ag = availableAgents.value.find(a => a.id === agentId)
  if (ag) {
    nodeConfig.value.agent_name = ag.name
    if (!nodeData.value.label || nodeData.value.label === 'Agente Especialista') {
      nodeData.value.label = ag.name
    }
  }
}

onMounted(() => {
  fetchAgents()
})
</script>

<style scoped>
.properties-panel {
  width: 320px;
  border-left: 1px solid rgba(255, 255, 255, 0.12);
  background: #111625 !important;
}
</style>
