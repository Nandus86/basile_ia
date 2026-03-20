<template>
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
      <v-col cols="12" md="3">
        <v-select
          v-model="activeProvider"
          label="Provedor (Grupo)"
          :items="providerOptions"
          prepend-inner-icon="mdi-domain"
        ></v-select>
      </v-col>
      <v-col cols="12" md="3">
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
      <v-col cols="12" md="3" v-if="!formData.config.is_reasoning_model">
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
      <v-col cols="12" md="3" v-if="!formData.config.is_reasoning_model">
        <v-text-field
          v-model="formData.max_tokens"
          label="Max Tokens"
          type="number"
          min="100"
          max="128000"
          prepend-inner-icon="mdi-counter"
        ></v-text-field>
      </v-col>
      <v-col cols="12" md="3" v-if="formData.config.is_reasoning_model">
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
      <v-col cols="12" md="3" v-if="formData.config.is_reasoning_model">
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

    <v-row class="mt-0">
      <v-col cols="12" md="4">
        <v-switch
          v-model="formData.is_orchestrator"
          label="Modo Orquestrador"
          color="purple"
          hide-details
        >
          <template v-slot:prepend>
            <v-icon :color="formData.is_orchestrator ? 'purple' : 'grey'">mdi-account-supervisor</v-icon>
          </template>
        </v-switch>
      </v-col>
      <v-col cols="12" md="8" v-if="formData.is_orchestrator">
        <v-alert type="info" variant="tonal" density="compact">
          <template v-slot:prepend>
            <v-icon>mdi-information</v-icon>
          </template>
          Quando ativo, este agente consulta seus colaboradores <strong>antes</strong> de responder, delegando tarefas aos especialistas mais adequados.
        </v-alert>
      </v-col>
    </v-row>
    
    <v-row class="mt-2">
      <v-col cols="12" md="6">
        <v-switch
          v-model="formData.config.short_term_memory_enabled"
          label="Memória de Curto Prazo (STM)"
          color="teal"
          hide-details
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
    }
  },
  methods: {
    formatContextLength(tokens) {
      return tokens?.toLocaleString() || 'N/A'
    },
  },
}
</script>
