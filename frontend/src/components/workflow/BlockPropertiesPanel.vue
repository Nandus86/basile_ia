<template>
  <div class="block-panel pa-4 h-100 d-flex flex-column">
    <!-- Header -->
    <div class="d-flex justify-space-between align-center mb-3">
      <h3 class="text-subtitle-1 d-flex align-center font-weight-bold">
        <v-icon :color="meta.color" class="mr-2" size="22">{{ meta.icon }}</v-icon>
        {{ meta.label }}
      </h3>
      <v-btn v-if="!hideClose" icon variant="text" size="small" @click="$emit('close')">
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </div>
    <v-divider class="mb-4"></v-divider>

    <div class="flex-grow-1 overflow-y-auto pr-1">
      <!-- Common: Label -->
      <v-text-field
        v-model="block.label"
        label="Rótulo do Bloco"
        variant="outlined"
        density="compact"
        class="mb-3"
        hide-details
        @update:model-value="emitUpdate"
      ></v-text-field>

      <!-- Common: Output Key -->
      <v-text-field
        v-if="block.type !== 'trigger' && block.type !== 'if'"
        v-model="config.output_key"
        label="Chave de Saída (output_key)"
        variant="outlined"
        density="compact"
        class="mb-3"
        hint="Nome usado para referenciar o resultado: {{ $output_key.data }}"
        persistent-hint
        @update:model-value="emitUpdate"
      ></v-text-field>

      <!-- ═══ TRIGGER ═══ -->
      <template v-if="block.type === 'trigger'">
        <v-select
          v-model="config.trigger_type"
          :items="['webhook', 'manual', 'schedule', 'event']"
          label="Tipo de Gatilho"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-select
          v-if="config.trigger_type === 'webhook'"
          v-model="config.webhook_config_id"
          :items="webhookConfigs"
          item-title="name"
          item-value="id"
          label="Webhook Config (opcional)"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          class="mb-3"
          @update:model-value="emitUpdate"
        ></v-select>
      </template>

      <!-- ═══ HTTP REQUEST ═══ -->
      <template v-if="block.type === 'http_request'">
        <v-select
          v-model="config.method"
          :items="['GET', 'POST', 'PUT', 'PATCH', 'DELETE']"
          label="Método HTTP"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-text-field
          v-model="config.url"
          label="URL"
          placeholder="{{ $trigger.payload.api_base }}/endpoint"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Suporta templates: {{ $chave.path }}"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>

        <!-- Query Params (JSON editor) -->
        <v-textarea
          v-model="queryJson"
          label="Query Params (JSON)"
          placeholder='{"search": "{{ $trigger.payload.query }}"}'
          variant="outlined"
          density="compact"
          rows="2"
          class="mb-3 monospace-field"
          hide-details
          @update:model-value="onQueryChange"
        ></v-textarea>

        <!-- Auth -->
        <v-select
          v-model="config.auth_type"
          :items="[{title:'Nenhuma', value:'none'}, {title:'Bearer Token', value:'bearer'}, {title:'API Key', value:'api_key'}]"
          label="Autenticação"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-text-field
          v-if="config.auth_type && config.auth_type !== 'none'"
          v-model="config.auth_value"
          :label="config.auth_type === 'bearer' ? 'Token' : 'API Key'"
          placeholder="{{ $trigger.payload.auth_token }}"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-text-field>

        <!-- Headers (JSON editor) -->
        <v-textarea
          v-model="headersJson"
          label="Headers (JSON)"
          placeholder='{"Content-Type": "application/json"}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          hide-details
          @update:model-value="onHeadersChange"
        ></v-textarea>

        <!-- Body -->
        <v-textarea
          v-if="['POST','PUT','PATCH'].includes(config.method)"
          v-model="bodyJson"
          label="Body (JSON)"
          placeholder='{"key": "{{ $trigger.payload.value }}"}'
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          hide-details
          @update:model-value="onBodyChange"
        ></v-textarea>

        <!-- Error handling -->
        <v-select
          v-model="config.error_handling"
          :items="[{title:'Parar execução', value:'stop'}, {title:'Continuar mesmo com erro', value:'continue'}]"
          label="Em caso de erro"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-text-field
          v-model.number="config.retry_count"
          label="Tentativas (retries)"
          type="number"
          variant="outlined"
          density="compact"
          min="0"
          max="5"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-text-field>

        <!-- Response Mapping -->
        <v-textarea
          v-model="responseMappingJson"
          label="Response Mapping (JSON)"
          placeholder='{"membros": "data.body[*].{id: _id, nome: name}"}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          hint="Mapeia campos do response. Suporta paths, [*], agrupamento {alias: campo}"
          persistent-hint
          @update:model-value="onResponseMappingChange"
        ></v-textarea>
      </template>

      <!-- ═══ IF ═══ -->
      <template v-if="block.type === 'if'">
        <v-text-field
          v-model="config.value_a"
          label="Valor A"
          placeholder="{{ $http_members.data.length }}"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Template do contexto"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>
        <v-select
          v-model="config.operator"
          :items="operators"
          label="Operador"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-text-field
          v-if="!['exists','is_empty'].includes(config.operator)"
          v-model="config.value_b"
          label="Valor B"
          placeholder="0"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-text-field>
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          <div class="d-flex align-center gap-2">
            <v-icon color="green" size="14">mdi-circle</v-icon> Verdadeiro →
            <v-icon color="red" size="14">mdi-circle</v-icon> Falso
          </div>
          Conecte as saídas coloridas aos blocos desejados.
        </v-alert>
      </template>

      <!-- ═══ ROUTER ═══ -->
      <template v-if="block.type === 'router'">
        <v-select
          v-model="config.mode"
          :items="[{title:'Primeiro match', value:'first_match'}, {title:'Todos os matches', value:'all_matches'}]"
          label="Modo"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <div v-for="(rule, idx) in (config.rules || [])" :key="idx" class="rule-item mb-3 pa-3 rounded border">
          <div class="d-flex justify-space-between align-center mb-2">
            <span class="text-caption font-weight-bold">Regra {{ idx + 1 }}</span>
            <v-btn icon variant="text" size="x-small" color="error" @click="removeRule(idx)">
              <v-icon size="16">mdi-close</v-icon>
            </v-btn>
          </div>
          <v-text-field v-model="rule.value_a" label="Valor A" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-text-field>
          <v-select v-model="rule.operator" :items="operators" label="Operador" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-select>
          <v-text-field v-model="rule.value_b" label="Valor B" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-text-field>
          <v-text-field v-model="rule.target_block_id" label="ID do bloco destino" variant="outlined" density="compact" hide-details @update:model-value="emitUpdate"></v-text-field>
        </div>
        <v-btn size="small" variant="tonal" color="primary" @click="addRule" class="mb-3">
          <v-icon start size="16">mdi-plus</v-icon> Adicionar Regra
        </v-btn>
      </template>

      <!-- ═══ FILTER ═══ -->
      <template v-if="block.type === 'filter'">
        <v-text-field v-model="config.source" label="Array de origem" placeholder="{{ $http_members.data.members }}" variant="outlined" density="compact" class="mb-3" hint="Template do array" persistent-hint @update:model-value="emitUpdate"></v-text-field>
        <v-text-field v-model="config.filter_field" label="Campo para filtrar" variant="outlined" density="compact" class="mb-3" hide-details @update:model-value="emitUpdate"></v-text-field>
        <v-select v-model="config.filter_operator" :items="operators" label="Operador" variant="outlined" density="compact" class="mb-3" hide-details @update:model-value="emitUpdate"></v-select>
        <v-text-field v-model="config.filter_value" label="Valor do filtro" variant="outlined" density="compact" class="mb-3" hide-details @update:model-value="emitUpdate"></v-text-field>
      </template>

      <!-- ═══ AGENT ═══ -->
      <template v-if="block.type === 'agent'">
        <v-select
          v-model="config.agent_id"
          :items="agents"
          item-title="name"
          item-value="id"
          label="Agente"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>
        <v-alert v-if="!config.agent_id" type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
          Selecione um agente para executar neste bloco.
        </v-alert>
        <v-textarea
          v-model="config.message_template"
          label="Mensagem para o Agente"
          placeholder="Registrar presença do líder {{ $leader_data.data.name }}..."
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3"
          hint="Suporta templates do contexto"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-textarea>
        <v-textarea
          v-model="contextMappingJson"
          label="Mapeamento de Contexto (JSON)"
          placeholder='{"leader": "{{ $leader_data.data }}"}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          hide-details
          @update:model-value="onContextMappingChange"
        ></v-textarea>
        <v-text-field
          v-model="config.session_id_source"
          label="Session ID (template)"
          placeholder="{{ $trigger.payload.session_id }}"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-text-field>
        <v-switch
          v-model="config.use_structured_output"
          label="Output Estruturado"
          color="primary"
          density="compact"
          hide-details
          class="mb-3"
          @update:model-value="emitUpdate"
        ></v-switch>
      </template>

      <!-- ═══ TRANSFORM ═══ -->
      <template v-if="block.type === 'transform'">
        <div v-for="(op, idx) in (config.operations || [])" :key="idx" class="rule-item mb-3 pa-3 rounded border">
          <div class="d-flex justify-space-between align-center mb-2">
            <span class="text-caption font-weight-bold">Operação {{ idx + 1 }}</span>
            <v-btn icon variant="text" size="x-small" color="error" @click="removeOperation(idx)">
              <v-icon size="16">mdi-close</v-icon>
            </v-btn>
          </div>
          <v-select v-model="op.op" :items="['set','merge','extract','map','flatten','join','stringify','parse_json']" label="Tipo" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-select>
          <v-text-field v-model="op.key" label="Chave destino" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-text-field>
          <v-textarea v-model="op.value" label="Valor / Template" variant="outlined" density="compact" class="mb-2" hide-details auto-grow rows="2" @update:model-value="emitUpdate"></v-textarea>
          <v-text-field v-if="['extract','map','flatten'].includes(op.op)" v-model="op.source" label="Source" variant="outlined" density="compact" class="mb-2" hide-details @update:model-value="emitUpdate"></v-text-field>
          <v-text-field v-if="op.op === 'extract'" v-model="op.path" label="Path" variant="outlined" density="compact" hide-details @update:model-value="emitUpdate"></v-text-field>
          <v-text-field v-if="op.op === 'map'" v-model="op.field" label="Campo" variant="outlined" density="compact" hide-details @update:model-value="emitUpdate"></v-text-field>
        </div>
        <v-btn size="small" variant="tonal" color="primary" @click="addOperation" class="mb-3">
          <v-icon start size="16">mdi-plus</v-icon> Adicionar Operação
        </v-btn>

        <v-divider class="my-3"></v-divider>

        <v-select
          v-model="config.output_type"
          :items="[
            { title: 'Dicionário (JSON)', value: 'json' },
            { title: 'Texto Plano (Template)', value: 'text' },
            { title: 'Extrair Chave Direta', value: 'raw_key' }
          ]"
          label="Formato do Resultado de Saída"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>

        <v-textarea
          v-if="config.output_type === 'text'"
          v-model="config.text_template"
          label="Template de Texto de Saída"
          placeholder="O resultado final é: {{ $step_1.message }}"
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3"
          hint="Suporta variáveis como {{ $contact.name }}"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-textarea>

        <v-text-field
          v-if="config.output_type === 'raw_key'"
          v-model="config.raw_key"
          label="Chave a ser Extraída"
          placeholder="texto"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Retornará o valor puro desta chave ao invés do JSON completo"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>
      </template>

      <!-- ═══ DELAY ═══ -->
      <template v-if="block.type === 'delay'">
        <v-text-field
          v-model.number="config.delay_ms"
          label="Atraso (ms)"
          type="number"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Máximo: 300000 (5 min)"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>
      </template>

      <!-- ═══ WAIT INPUT ═══ -->
      <template v-if="block.type === 'wait_input'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Este bloco pausa a execução do workflow e aguarda uma resposta do usuário.
          O resultado da resposta será armazenado na chave de saída configurada.
        </v-alert>
        <v-text-field
          v-model.number="config.timeout_seconds"
          label="Tempo Limite de Espera (segundos)"
          type="number"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Padrão: 7200 (2 horas)"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>
      </template>

      <!-- ═══ SUB-WORKFLOW ═══ -->
      <template v-if="block.type === 'sub_workflow'">
        <v-select
          v-model="config.workflow_id"
          :items="workflows.filter(w => w.id !== currentWorkflowId)"
          item-title="name"
          item-value="id"
          label="Selecionar Workflow"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>

        <v-select
          v-model="config.payload_mode"
          :items="[
            { title: 'Enviar Contexto Completo', value: 'full' },
            { title: 'Personalizar Payload (JSON)', value: 'custom' }
          ]"
          label="Dados de Entrada (Payload)"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>

        <v-textarea
          v-if="config.payload_mode === 'custom'"
          v-model="payloadTemplateJson"
          label="Payload Customizado (JSON)"
          placeholder='{"key": "{{ $trigger.payload.val }}"}'
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          hide-details
          @update:model-value="onPayloadTemplateChange"
        ></v-textarea>

        <v-select
          v-model="config.error_handling"
          :items="[{title:'Parar execução', value:'stop'}, {title:'Continuar mesmo com erro', value:'continue'}]"
          label="Em caso de erro"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>

        <v-text-field
          v-model.number="config.retry_count"
          label="Tentativas (retries)"
          type="number"
          variant="outlined"
          density="compact"
          min="0"
          max="5"
          class="mb-3"
          hide-details
          @update:model-value="emitUpdate"
        ></v-text-field>
      </template>

      <!-- Context variables available -->
      <v-expansion-panels v-if="contextKeys.length" class="mt-2" variant="accordion">
        <v-expansion-panel>
          <v-expansion-panel-title class="text-caption">
            <v-icon size="16" class="mr-1">mdi-variable</v-icon>
            Variáveis disponíveis ({{ contextKeys.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div v-for="key in contextKeys" :key="key" class="d-flex align-center py-1">
              <code class="text-caption mr-2" style="color: #8B5CF6">${{ key }}</code>
              <v-btn icon variant="text" size="x-small" @click="copyVar(key)">
                <v-icon size="14">mdi-content-copy</v-icon>
              </v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </div>

    <!-- Footer -->
    <div class="mt-3 pt-3 border-t d-flex justify-space-between">
      <v-btn color="error" variant="text" size="small" @click="$emit('delete')">
        <v-icon start>mdi-trash-can</v-icon>
        Excluir Bloco
      </v-btn>
      <v-btn color="info" variant="tonal" size="small" @click="$emit('duplicate')">
        <v-icon start>mdi-content-duplicate</v-icon>
        Duplicar Bloco
      </v-btn>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  block: { type: Object, required: true },
  agents: { type: Array, default: () => [] },
  webhookConfigs: { type: Array, default: () => [] },
  contextKeys: { type: Array, default: () => [] },
  hideClose: { type: Boolean, default: false },
  workflows: { type: Array, default: () => [] },
  currentWorkflowId: { type: String, default: null },
})
const emit = defineEmits(['update', 'close', 'delete', 'duplicate'])

const BLOCK_META = {
  trigger:      { icon: 'mdi-lightning-bolt',    color: '#F59E0B', label: 'Configurar Gatilho' },
  http_request: { icon: 'mdi-api',              color: '#3B82F6', label: 'Configurar HTTP Request' },
  if:           { icon: 'mdi-call-split',        color: '#8B5CF6', label: 'Configurar Condição IF' },
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Configurar Router' },
  filter:       { icon: 'mdi-filter-variant',    color: '#06B6D4', label: 'Configurar Filter' },
  agent:        { icon: 'mdi-robot',             color: '#10B981', label: 'Configurar Agente' },
  transform:    { icon: 'mdi-swap-horizontal',   color: '#F97316', label: 'Configurar Transform' },
  delay:        { icon: 'mdi-timer-sand',        color: '#6B7280', label: 'Configurar Delay' },
  sub_workflow: { icon: 'mdi-sitemap-outline',    color: '#EC4899', label: 'Configurar Sub-workflow' },
  wait_input:   { icon: 'mdi-account-question',  color: '#EC4899', label: 'Configurar Aguardar Resposta' },
}

const meta = computed(() => BLOCK_META[props.block.type] || { icon: 'mdi-help-circle', color: '#9CA3AF', label: 'Configurar Bloco' })

const config = computed(() => {
  if (!props.block.config) props.block.config = {}
  return props.block.config
})

const operators = [
  { title: 'Igual a', value: 'equals' },
  { title: 'Diferente de', value: 'not_equals' },
  { title: 'Maior que', value: 'greater_than' },
  { title: 'Maior ou igual', value: 'greater_than_or_equal' },
  { title: 'Menor que', value: 'less_than' },
  { title: 'Menor ou igual', value: 'less_than_or_equal' },
  { title: 'Contém', value: 'contains' },
  { title: 'Não contém', value: 'not_contains' },
  { title: 'Começa com', value: 'starts_with' },
  { title: 'Termina com', value: 'ends_with' },
  { title: 'Existe', value: 'exists' },
  { title: 'Está vazio', value: 'is_empty' },
]

// JSON field helpers
const headersJson = ref(JSON.stringify(config.value.headers || {}, null, 2))
const queryJson = ref(JSON.stringify(config.value.query_params || {}, null, 2))
const bodyJson = ref(typeof config.value.body === 'object' ? JSON.stringify(config.value.body, null, 2) : (config.value.body || ''))
const contextMappingJson = ref(JSON.stringify(config.value.context_mapping || {}, null, 2))
const responseMappingJson = ref(JSON.stringify(config.value.response_mapping || {}, null, 2))
const payloadTemplateJson = ref(typeof config.value.payload_template === 'object' ? JSON.stringify(config.value.payload_template, null, 2) : (config.value.payload_template || ''))

watch(() => props.block.id, () => {
  headersJson.value = JSON.stringify(config.value.headers || {}, null, 2)
  queryJson.value = JSON.stringify(config.value.query_params || {}, null, 2)
  bodyJson.value = typeof config.value.body === 'object' ? JSON.stringify(config.value.body, null, 2) : (config.value.body || '')
  contextMappingJson.value = JSON.stringify(config.value.context_mapping || {}, null, 2)
  responseMappingJson.value = JSON.stringify(config.value.response_mapping || {}, null, 2)
  payloadTemplateJson.value = typeof config.value.payload_template === 'object' ? JSON.stringify(config.value.payload_template, null, 2) : (config.value.payload_template || '')
})

function onHeadersChange(val) {
  try { config.value.headers = JSON.parse(val) } catch {}
  emitUpdate()
}
function onQueryChange(val) {
  try { config.value.query_params = JSON.parse(val) } catch {}
  emitUpdate()
}
function onBodyChange(val) {
  try { config.value.body = JSON.parse(val) } catch { config.value.body = val }
  emitUpdate()
}
function onContextMappingChange(val) {
  try { config.value.context_mapping = JSON.parse(val) } catch {}
  emitUpdate()
}
function onResponseMappingChange(val) {
  try { config.value.response_mapping = JSON.parse(val) } catch {}
  emitUpdate()
}
function onPayloadTemplateChange(val) {
  try { config.value.payload_template = JSON.parse(val) } catch { config.value.payload_template = val }
  emitUpdate()
}

function addRule() {
  if (!config.value.rules) config.value.rules = []
  config.value.rules.push({ value_a: '', operator: 'equals', value_b: '', target_block_id: '' })
  emitUpdate()
}
function removeRule(idx) {
  config.value.rules.splice(idx, 1)
  emitUpdate()
}

function addOperation() {
  if (!config.value.operations) config.value.operations = []
  config.value.operations.push({ op: 'set', key: '', value: '' })
  emitUpdate()
}
function removeOperation(idx) {
  config.value.operations.splice(idx, 1)
  emitUpdate()
}

function copyVar(key) {
  navigator.clipboard.writeText(`{{ $${key} }}`)
}

function emitUpdate() {
  emit('update', props.block)
}
</script>

<style scoped>
.block-panel {
  background: rgba(20, 20, 30, 0.98);
}
.rule-item {
  border-color: rgba(255,255,255,0.1) !important;
  background: rgba(255,255,255,0.02);
}
.monospace-field :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
  font-size: 12px !important;
}
</style>
