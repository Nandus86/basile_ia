<template>
  <v-form ref="formRef" v-model="formValid">
    <v-row>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="formData.name"
          label="Nome do Agente"
          placeholder="Ex: Assistente de Vendas"
          :rules="[v => !!v || 'Nome é obrigatório', v => (v && v.length >= 3) || 'Nome deve ter pelo menos 3 caracteres', v => /^[\w\sá-úÁ-ÚüÜ]+$/.test(v) || 'Nome inválido']"
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
      :rules="[v => (!v || v.length <= 500) || 'Descrição muito longa (máximo 500 caracteres)', v => (!v || v.length >= 5) || 'Descrição deve ter pelo menos 5 caracteres']"
      prepend-inner-icon="mdi-text"
    ></v-textarea>
    
    <v-textarea
      v-model="formData.system_prompt"
      label="System Prompt"
      placeholder="Instruções de comportamento do agente..."
      rows="5"
      :rules="[v => !!v || 'System prompt é obrigatório', v => (v && v.length >= 10) || 'System prompt deve ter pelo menos 10 caracteres', v => (v && v.length <= 10000) || 'System prompt muito longo (máximo 10.000 caracteres)']"
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
          :rules="[v => (v === '' || v === null || !isNaN(v)) || 'Valor numérico inválido', v => (v === '' || v === null || (v >= 0 && v <= 2)) || 'Temperature deve ser entre 0 e 2']"
          prepend-inner-icon="mdi-thermometer"
        ></v-text-field>
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="formData.max_tokens"
          label="Max Tokens"
          type="number"
          :rules="[v => (v === '' || v === null || !isNaN(v)) || 'Valor numérico inválido', v => (v === '' || v === null || (v >= 100 && v <= 128000)) || 'Max tokens deve ser entre 100 e 128.000']"
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
            :rules="[v => (!v || !isNaN(v)) || 'Valor numérico inválido', v => (!v || (v >= 1000 && v <= 128000)) || 'Max completion tokens deve ser entre 1.000 e 128.000']"
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
           label="Modelo de Raciocínio (Reasoning)"
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

     <!-- Parâmetros de Geração (Qwen3 / Sampling) -->
     <v-card variant="outlined" class="mt-3">
       <v-card-title class="text-subtitle-2">
         <v-icon size="18" class="mr-1">mdi-tune</v-icon>
         Parâmetros de Geração (Sampling)
       </v-card-title>
       <v-card-text>
         <v-row>
           <!-- Top-P (Nucleus Sampling) -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.top_p"
               label="Top P (Nucleus)"
               type="number"
               step="0.05"
               min="0.01"
               max="1"
               hint="Filtro probabilidade acumulada. Padrão Qwen3 Instruct: 0.80 | Thinking: 0.95"
               persistent-hint
               prepend-inner-icon="mdi-filter-variant"
             ></v-text-field>
           </v-col>

           <!-- Top-K -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.top_k"
               label="Top K"
               type="number"
               min="1"
               max="100"
               step="1"
               hint="Limite de tokens mais prováveis. Padrão Qwen3: 20"
               persistent-hint
               prepend-inner-icon="mdi-format-list-numbered"
             ></v-text-field>
           </v-col>

           <!-- Min-P -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.min_p"
               label="Min P (Probabilidade Mínima)"
               type="number"
               step="0.01"
               min="0"
               max="1"
               hint="Filtro absoluto de probabilidade. Padrão: 0.00"
               persistent-hint
               prepend-inner-icon="mdi-arrow-collapse-down"
             ></v-text-field>
           </v-col>

           <!-- Repetition Penalty -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.repetition_penalty"
               label="Repetition Penalty"
               type="number"
               step="0.1"
               min="1"
               max="2"
               hint="Penaliza repetições (1.0 = desativado, >1.0 = mais penalidade)"
               persistent-hint
               prepend-inner-icon="mdi-repeat-off"
             ></v-text-field>
           </v-col>

           <!-- Presence Penalty -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.presence_penalty"
               label="Presence Penalty"
               type="number"
               step="0.1"
               min="-2"
               max="2"
               hint="Penaliza tokens já aparecidos (-2 a +2)"
               persistent-hint
               prepend-inner-icon="mdi-text-box-check"
             ></v-text-field>
           </v-col>

           <!-- Frequency Penalty -->
           <v-col cols="12" md="6">
             <v-text-field
               v-model.number="formData.config.frequency_penalty"
               label="Frequency Penalty"
               type="number"
               step="0.1"
               min="-2"
               max="2"
               hint="Reduz frequência de palavras repetidas"
               persistent-hint
               prepend-inner-icon="mdi-chart-line"
             ></v-text-field>
           </v-col>
         </v-row>

         <v-alert type="info" variant="tonal" density="compact" class="mt-2">
           <template v-slot:prepend>
             <v-icon>mdi-information</v-icon>
           </template>
           <div>
             <strong>Configurações recomendadas Qwen3:</strong><br>
             • <strong>Instruct (padrão):</strong> temp=0.7, top_p=0.80, top_k=20, min_p=0.0<br>
             • <strong>Thinking (raciocínio):</strong> temp=0.6, top_p=0.95, top_k=20<br>
             • <strong>JSON estruturado:</strong> habilite "Estilo de Resposta" abaixo e inclua "JSON" no system prompt
           </div>
         </v-alert>
       </v-card-text>
     </v-card>

     <!-- Estilo de Resposta (Colaboradores) -->
     <v-card variant="outlined" class="mt-3">
       <v-card-title class="text-subtitle-2">
         <v-icon size="18" class="mr-1">mdi-format-text</v-icon>
         Formato de Resposta (Colaboradores)
       </v-card-title>
       <v-card-text>
         <v-row>
           <v-col cols="12">
             <v-select
               v-model="formData.response_style"
               label="Estilo de Resposta"
               :items="responseStyleOptions"
               item-title="title"
               item-value="value"
               prepend-inner-icon="mdi-format-text"
               persistent-hint
             ></v-select>
           </v-col>
         </v-row>
         <v-alert v-if="formData.response_style === 'structured'" type="success" variant="tonal" density="compact">
           <template v-slot:prepend>
             <v-icon>mdi-check-circle</v-icon>
           </template>
           <div>
             <strong>Modo ESTRUTURADO (JSON) ativado</strong><br>
             Colaboradores retornarão JSON com campos: <code>achados</code>, <code>dados</code>, <code>recomendacao</code>.
           </div>
         </v-alert>
         <v-alert v-else type="warning" variant="tonal" density="compact">
           <template v-slot:prepend>
             <v-icon>mdi-alert</v-icon>
           </template>
           <div>
             <strong>Modo NATURAL (texto livre) ativado</strong><br>
             Colaboradores responderão em texto direto (menos estruturado, mais flexível).
           </div>
         </v-alert>
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
          <v-col cols="12" sm="6">
            <v-select
              v-model="formData.execution_mode"
              :items="executionModeOptions"
              item-title="label"
              item-value="value"
              label="Modo de Execução"
              prepend-inner-icon="mdi-tune-variant"
              density="comfortable"
              hide-details
            ></v-select>
          </v-col>
          <v-col cols="12" sm="6">
            <v-switch
              v-model="formData.is_planner"
              label="Planejador Mestre"
              color="indigo"
              hide-details
              density="comfortable"
              :disabled="!formData.is_orchestrator"
            >
              <template v-slot:prepend>
                <v-icon :color="formData.is_planner ? 'indigo' : 'grey'">mdi-clipboard-list-outline</v-icon>
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
        <v-expand-transition>
          <v-alert v-if="formData.is_planner" type="indigo" variant="tonal" density="compact" class="mt-3 mb-0">
            <template v-slot:prepend>
              <v-icon>mdi-clipboard-list-outline</v-icon>
            </template>
            O Planejador enviará primeiro a solicitação a um LLM rápido para estruturar um checklist de tarefas granulares que o colaborador deverá cumprir.
          </v-alert>
        </v-expand-transition>
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
            :rules="[v => (!v || !isNaN(v)) || 'Valor numérico inválido', v => (!v || (v >= 1 && v <= 720)) || 'Tempo deve ser entre 1 e 720 horas']"
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
</template>

<script>
export default {
  name: 'AgentFormGeneral',
  props: {
    formData: {
      type: Object,
      required: true,
    },
    accessLevels: {
      type: Array,
      default: () => [
        { title: 'Público', value: 'public' },
        { title: 'Privado', value: 'private' },
        { title: 'Premium', value: 'premium' },
      ],
    },
    providerOptions: {
      type: Array,
      default: () => [],
    },
    modelOptions: {
      type: Array,
      default: () => [],
    },
    loadingModels: {
      type: Boolean,
      default: false,
    },
    reasoningEffortOptions: {
      type: Array,
      default: () => [
        { title: 'Baixo', value: 'low' },
        { title: 'Médio', value: 'medium' },
        { title: 'Alto', value: 'high' },
      ],
    },
  },
  emits: ['update:activeProvider'],
   data() {
     return {
       formValid: false,
       activeProvider: null,
       executionModeOptions: [
         { label: 'Balanceado', value: 'balanced' },
         { label: 'Priorizar Ferramentas', value: 'tools_first' },
         { label: 'Priorizar Orquestração', value: 'orchestrator_first' },
       ],
       responseStyleOptions: [
         { title: 'Estruturado (JSON — recomendado para Qwen3)', value: 'structured' },
         { title: 'Natural (texto livre)', value: 'natural' },
       ],
     }
  },
  methods: {
    formatContextLength(tokens) {
      return tokens?.toLocaleString() || 'N/A'
    },
  },
}
</script>
