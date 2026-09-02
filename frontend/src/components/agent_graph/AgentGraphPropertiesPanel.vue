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
        <!-- Mode Toggle: System Agent vs Clean/Inline Agent -->
        <v-btn-toggle
          v-model="agentMode"
          mandatory
          density="compact"
          color="primary"
          class="mb-3 w-100"
          divided
          variant="outlined"
        >
          <v-btn value="existing" size="small" class="flex-grow-1">
            <v-icon start size="16">mdi-account-check</v-icon>
            Agente do Sistema
          </v-btn>
          <v-btn value="inline" size="small" class="flex-grow-1">
            <v-icon start size="16">mdi-pencil-plus</v-icon>
            Agente Limpo
          </v-btn>
        </v-btn-toggle>

        <!-- Mode A: Existing System Agent -->
        <template v-if="agentMode === 'existing'">
          <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
            <v-icon size="16" color="primary">mdi-robot</v-icon>Selecionar Agente Cadastrado
          </h4>

          <v-autocomplete
            v-model="nodeConfig.agent_id"
            :items="availableAgents"
            item-title="name"
            item-value="id"
            label="Agente do Sistema"
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
        </template>

        <!-- Mode B: Clean / Inline Agent -->
        <template v-else-if="agentMode === 'inline'">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
            <v-icon start size="14">mdi-information</v-icon>
            Crie um agente personalizado e limpo para este grafo, com controle total de provedor, ferramentas (MCPs) e habilidades (Skills).
          </v-alert>

          <v-text-field
            v-model="inlineAgent.name"
            label="Nome do Agente"
            placeholder="Agente Limpo Especialista"
            variant="outlined"
            density="compact"
            class="mb-3"
            hide-details
            @update:model-value="onInlineAgentChange"
          ></v-text-field>

          <v-row dense class="mb-1">
            <v-col cols="6">
              <v-select
                v-model="inlineAgent.provider_id"
                :items="providerOptions"
                item-title="title"
                item-value="value"
                label="Provedor de IA"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="onProviderChange"
              ></v-select>
            </v-col>
            <v-col cols="6">
              <v-autocomplete
                v-model="inlineAgent.model"
                :items="inlineModelOptions"
                item-title="title"
                item-value="value"
                label="Modelo de IA"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="Selecione ou busque..."
                @update:model-value="onInlineAgentChange"
              >
                <template v-slot:item="{ props, item }">
                  <v-list-item v-bind="props" :subtitle="item.raw.subtitle || item.raw.value"></v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
          </v-row>

          <v-row dense class="mb-2">
            <v-col cols="6">
              <v-text-field
                v-model.number="inlineAgent.temperature"
                label="Temperatura"
                type="number"
                min="0"
                max="2"
                step="0.1"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="onInlineAgentChange"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="inlineAgent.max_tokens"
                label="Max Tokens"
                type="number"
                min="100"
                max="128000"
                step="100"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="onInlineAgentChange"
              ></v-text-field>
            </v-col>
          </v-row>

          <!-- MCP Tools Selection -->
          <v-autocomplete
            v-model="inlineAgent.mcp_ids"
            :items="availableMcps"
            item-title="name"
            item-value="id"
            label="MCPs / Ferramentas Disponíveis"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            class="mb-3"
            hint="Selecione as ferramentas MCP que este agente poderá chamar"
            persistent-hint
            @update:model-value="onInlineAgentChange"
          >
            <template v-slot:chip="{ props, item }">
              <v-chip
                v-bind="props"
                size="small"
                color="teal-darken-1"
                variant="tonal"
                prepend-icon="mdi-connection"
              >
                {{ item.raw.name }}
              </v-chip>
            </template>
          </v-autocomplete>

          <!-- Skills Selection -->
          <v-autocomplete
            v-model="inlineAgent.skill_ids"
            :items="availableSkills"
            item-title="name"
            item-value="id"
            label="Skills / Habilidades Disponíveis"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            class="mb-3"
            hint="Selecione as skills cujas instruções serão fornecidas a este agente"
            persistent-hint
            @update:model-value="onInlineAgentChange"
          >
            <template v-slot:chip="{ props, item }">
              <v-chip
                v-bind="props"
                size="small"
                color="indigo-darken-1"
                variant="tonal"
                prepend-icon="mdi-star-shooting"
              >
                {{ item.raw.name }}
              </v-chip>
            </template>
          </v-autocomplete>

          <!-- Clean System Prompt -->
          <v-textarea
            v-model="inlineAgent.system_prompt"
            label="System Prompt (Prompt Limpo)"
            placeholder="Você é um assistente especialista que analisa e processa a solicitação do usuário..."
            variant="outlined"
            density="compact"
            rows="6"
            class="mb-3 monospace-field"
            hint="Instrução principal e direta do agente. Não contém nenhuma regra global herdada."
            persistent-hint
            @update:model-value="onInlineAgentChange"
          ></v-textarea>
        </template>

        <!-- ═══ CONTEXT & PAYLOAD SCHEMA (FOR BOTH EXISTING & INLINE AGENTS) ═══ -->
        <v-divider class="my-3"></v-divider>

        <div class="d-flex align-center justify-space-between mb-1">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="cyan">mdi-code-json</v-icon>Schema do Payload / Contexto
          </h4>
          <v-btn size="x-small" variant="tonal" color="cyan" prepend-icon="mdi-magic-staff" @click="insertDefaultPayloadSchema">
            Exemplo Igreja
          </v-btn>
        </div>

        <p class="text-caption text-medium-emphasis mb-2">
          Defina quais campos do payload devem ser extraídos e mapeados para o contexto deste agente.
        </p>

        <!-- Quick Template Variable Chips -->
        <div class="mb-2 d-flex flex-wrap ga-1">
          <v-chip
            v-for="chip in quickTemplateChips"
            :key="chip.token"
            size="x-small"
            variant="tonal"
            color="primary"
            class="cursor-pointer"
            @click="insertTemplateToken(chip.token)"
            :title="`Clique para adicionar ${chip.token}`"
          >
            + {{ chip.label }}
          </v-chip>
        </div>

        <v-textarea
          v-model="contextMappingJson"
          label="Mapeamento de Contexto (JSON)"
          placeholder='{\n  "user_name": "{{ member.name }}",\n  "user_role": "{{ member_fin.role_profile }}",\n  "permissions": "{{ member_fin.permissions }}",\n  "church_name": "{{ church.church_name }}"\n}'
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          hint="Tags dinâmicas: {{ member.name }}, {{ member_fin.permissions }}, {{ church.preferredLanguage }}, {{ $now(...) }}"
          persistent-hint
          @update:model-value="onContextMappingChange"
        ></v-textarea>

        <v-switch
          :model-value="nodeConfig.inject_full_context !== false"
          @update:model-value="val => { nodeConfig.inject_full_context = val; }"
          label="Injetar Payload Completo (<context_data>)"
          color="cyan"
          density="compact"
          hide-details
          class="mb-3"
        ></v-switch>

        <v-divider class="my-3"></v-divider>

        <!-- Structured Output Schema Section -->
        <div class="d-flex align-center justify-space-between mb-1">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="amber-darken-2">mdi-code-brackets</v-icon>Saída Estruturada (JSON Schema)
          </h4>
        </div>

        <v-switch
          v-model="nodeConfig.use_structured_output"
          label="Forçar Resposta em JSON Estruturado"
          color="amber-darken-2"
          density="compact"
          hide-details
          class="mb-2"
        ></v-switch>

        <v-textarea
          v-if="nodeConfig.use_structured_output"
          v-model="outputSchemaJson"
          label="Output Schema (JSON Schema)"
          placeholder='{\n  "type": "object",\n  "properties": {\n    "resposta": { "type": "string" },\n    "intencao": { "type": "string" }\n  },\n  "required": ["resposta"]\n}'
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          hint="Esquema JSON que o modelo deverá obedecer estritamente na resposta"
          persistent-hint
          @update:model-value="onOutputSchemaChange"
        ></v-textarea>
      </div>

      <!-- ── 2. ROUTER / SUPERVISOR NODE PROPERTIES ───────────────────── -->
      <div v-else-if="nodeType === 'router' || nodeType === 'supervisor'">
        <div class="d-flex align-center justify-space-between mb-2">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="purple">mdi-source-branch</v-icon>Supervisor & Roteador
          </h4>
          <v-btn size="x-small" variant="tonal" color="purple" prepend-icon="mdi-plus" @click="addRoute">
            Adicionar Rota
          </v-btn>
        </div>

        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          <v-icon start size="14">mdi-information</v-icon>
          O supervisor analisará a mensagem e escolherá dinamicamente a rota ideal com base nas instruções e rotas semânticas.
        </v-alert>

        <!-- LLM Model & Provider Selection -->
        <h5 class="text-caption font-weight-bold text-medium-emphasis mb-1">Modelo de IA do Roteador:</h5>
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-select
              v-model="nodeConfig.provider_id"
              :items="providerOptions"
              label="Provedor LLM"
              variant="outlined"
              density="compact"
              hide-details
            ></v-select>
          </v-col>
          <v-col cols="6">
            <v-autocomplete
              v-model="nodeConfig.model"
              :items="getNodeModelOptions(nodeConfig.provider_id)"
              label="Modelo"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              no-data-text="Nenhum modelo encontrado"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props" :subtitle="item.raw.subtitle || item.raw.value"></v-list-item>
              </template>
            </v-autocomplete>
          </v-col>
        </v-row>

        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-text-field
              v-model.number="nodeConfig.temperature"
              label="Temperatura"
              type="number"
              min="0"
              max="2"
              step="0.1"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="0.2"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model.number="nodeConfig.max_tokens"
              label="Max Tokens"
              type="number"
              min="100"
              max="128000"
              step="100"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="1500"
            ></v-text-field>
          </v-col>
        </v-row>

        <v-textarea
          v-model="nodeConfig.prompt"
          label="Instruções Principais do Supervisor (Prompt)"
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          placeholder="Você é o Supervisor e Roteador da Igreja. Analise a mensagem do usuário e escolha a rota..."
          hint="Prompt com regras e diretrizes que o roteador usará para decidir a rota"
          persistent-hint
        ></v-textarea>

        <!-- Context & Payload Schema for Router -->
        <v-divider class="my-3"></v-divider>
        <div class="d-flex align-center justify-space-between mb-1">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="cyan">mdi-code-json</v-icon>Schema do Payload / Contexto
          </h4>
          <v-btn size="x-small" variant="tonal" color="cyan" prepend-icon="mdi-magic-staff" @click="insertDefaultPayloadSchema">
            Exemplo Igreja
          </v-btn>
        </div>
        <p class="text-caption text-medium-emphasis mb-2">
          Defina quais dados do payload o supervisor deve receber para tomar a decisão correta.
        </p>
        <div class="mb-2 d-flex flex-wrap ga-1">
          <v-chip
            v-for="chip in quickTemplateChips"
            :key="chip.token"
            size="x-small"
            variant="tonal"
            color="primary"
            class="cursor-pointer"
            @click="insertTemplateToken(chip.token)"
          >
            + {{ chip.label }}
          </v-chip>
        </div>
        <v-textarea
          v-model="contextMappingJson"
          label="Mapeamento de Contexto (JSON)"
          placeholder='{\n  "user_name": "{{ member.name }}",\n  "user_role": "{{ member_fin.role_profile }}"\n}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          @update:model-value="onContextMappingChange"
        ></v-textarea>
        <v-switch
          :model-value="nodeConfig.inject_full_context !== false"
          @update:model-value="val => { nodeConfig.inject_full_context = val; }"
          label="Injetar Payload Completo (<context_data>)"
          color="cyan"
          density="compact"
          hide-details
          class="mb-3"
        ></v-switch>

        <v-divider class="my-3"></v-divider>
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="purple">mdi-call-split</v-icon>Rotas Semânticas de Saída
        </h4>

        <!-- Dynamic Routes List -->
        <div
          v-for="(route, idx) in routerRoutes"
          :key="idx"
          class="route-card mb-3 pa-3 rounded border"
          style="background: rgba(139, 92, 246, 0.05); border-color: rgba(139, 92, 246, 0.25) !important;"
        >
          <div class="d-flex justify-space-between align-center mb-2">
            <div class="d-flex align-center ga-1">
              <v-icon size="16" color="purple">mdi-call-split</v-icon>
              <span class="text-caption font-weight-bold">Rota {{ idx + 1 }}</span>
              <v-chip size="x-small" color="purple" variant="flat" density="compact" class="ml-1">
                #{{ route.id || `route_${idx}` }}
              </v-chip>
            </div>
            <div class="d-flex align-center">
              <v-btn icon variant="text" size="x-small" :disabled="idx === 0" @click="moveRoute(idx, -1)" title="Mover para cima">
                <v-icon size="14">mdi-arrow-up</v-icon>
              </v-btn>
              <v-btn icon variant="text" size="x-small" :disabled="idx === routerRoutes.length - 1" @click="moveRoute(idx, 1)" title="Mover para baixo">
                <v-icon size="14">mdi-arrow-down</v-icon>
              </v-btn>
              <v-btn icon variant="text" size="x-small" color="error" @click="removeRoute(idx)" title="Excluir rota">
                <v-icon size="14">mdi-close</v-icon>
              </v-btn>
            </div>
          </div>

          <v-text-field
            v-model="route.name"
            label="Nome da Rota"
            placeholder="Ex: Suporte Financeiro"
            variant="outlined"
            density="compact"
            class="mb-2"
            hide-details
            @update:model-value="onRoutesChange"
          ></v-text-field>

          <v-textarea
            v-model="route.description"
            label="Quando acionar esta rota?"
            placeholder="Ex: Quando o usuário perguntar sobre dízimos, ofertas, relatórios financeiros ou doações."
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-1"
            hint="Critério semântico que o LLM usará para escolher esta rota"
            persistent-hint
            @update:model-value="onRoutesChange"
          ></v-textarea>
        </div>

        <!-- Fallback Route Card -->
        <div class="route-card-fallback mb-3 pa-3 rounded border" style="background: rgba(239, 68, 68, 0.05); border-color: rgba(239, 68, 68, 0.25) !important;">
          <div class="d-flex align-center justify-space-between mb-1">
            <span class="text-caption font-weight-bold text-error d-flex align-center ga-1">
              <v-icon size="16" color="error">mdi-help-circle-outline</v-icon>Rota Padrão / Fallback (#default)
            </span>
            <v-chip size="x-small" color="error" variant="flat" density="compact">Saída Vermelha</v-chip>
          </div>
          <span class="text-caption text-medium-emphasis">
            Esta saída será acionada caso a intenção do usuário não corresponda a nenhuma das rotas acima.
          </span>
        </div>
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

        <!-- LLM Model & Provider Selection -->
        <h5 class="text-caption font-weight-bold text-medium-emphasis mb-1">Modelo de IA do Sintetizador:</h5>
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-select
              v-model="nodeConfig.provider_id"
              :items="providerOptions"
              label="Provedor LLM"
              variant="outlined"
              density="compact"
              hide-details
            ></v-select>
          </v-col>
          <v-col cols="6">
            <v-autocomplete
              v-model="nodeConfig.model"
              :items="getNodeModelOptions(nodeConfig.provider_id)"
              label="Modelo"
              variant="outlined"
              density="compact"
              hide-details
              clearable
              no-data-text="Nenhum modelo encontrado"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props" :subtitle="item.raw.subtitle || item.raw.value"></v-list-item>
              </template>
            </v-autocomplete>
          </v-col>
        </v-row>

        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-text-field
              v-model.number="nodeConfig.temperature"
              label="Temperatura"
              type="number"
              min="0"
              max="2"
              step="0.1"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="0.6"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model.number="nodeConfig.max_tokens"
              label="Max Tokens"
              type="number"
              min="100"
              max="128000"
              step="100"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="2500"
            ></v-text-field>
          </v-col>
        </v-row>

        <v-textarea
          v-model="nodeConfig.prompt"
          label="Prompt de Consolidação (Instrução)"
          variant="outlined"
          density="compact"
          rows="4"
          class="mb-3 monospace-field"
          placeholder="Você é o Sintetizador Especialista. Consolide as respostas dos especialistas em uma única mensagem clara, coesa e acolhedora..."
          hint="Unifica as saídas paralelas em uma resposta coesa"
          persistent-hint
        ></v-textarea>

        <!-- Context & Payload Schema for Synthesizer -->
        <v-divider class="my-3"></v-divider>
        <div class="d-flex align-center justify-space-between mb-1">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="cyan">mdi-code-json</v-icon>Schema do Payload / Contexto
          </h4>
          <v-btn size="x-small" variant="tonal" color="cyan" prepend-icon="mdi-magic-staff" @click="insertDefaultPayloadSchema">
            Exemplo Igreja
          </v-btn>
        </div>
        <p class="text-caption text-medium-emphasis mb-2">
          Campos de contexto fornecidos para enriquecer a síntese final.
        </p>
        <div class="mb-2 d-flex flex-wrap ga-1">
          <v-chip
            v-for="chip in quickTemplateChips"
            :key="chip.token"
            size="x-small"
            variant="tonal"
            color="primary"
            class="cursor-pointer"
            @click="insertTemplateToken(chip.token)"
          >
            + {{ chip.label }}
          </v-chip>
        </div>
        <v-textarea
          v-model="contextMappingJson"
          label="Mapeamento de Contexto (JSON)"
          placeholder='{\n  "user_name": "{{ member.name }}",\n  "church_name": "{{ church.church_name }}"\n}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          @update:model-value="onContextMappingChange"
        ></v-textarea>
        <v-switch
          :model-value="nodeConfig.inject_full_context !== false"
          @update:model-value="val => { nodeConfig.inject_full_context = val; }"
          label="Injetar Payload Completo (<context_data>)"
          color="cyan"
          density="compact"
          hide-details
          class="mb-3"
        ></v-switch>
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

        <template v-if="nodeConfig.mode === 'llm' || !nodeConfig.mode">
          <!-- LLM Model & Provider Selection -->
          <h5 class="text-caption font-weight-bold text-medium-emphasis mb-1">Modelo de IA de Decisão:</h5>
          <v-row dense class="mb-2">
            <v-col cols="6">
              <v-select
                v-model="nodeConfig.provider_id"
                :items="providerOptions"
                label="Provedor"
                variant="outlined"
                density="compact"
                hide-details
              ></v-select>
            </v-col>
            <v-col cols="6">
              <v-autocomplete
                v-model="nodeConfig.model"
                :items="getNodeModelOptions(nodeConfig.provider_id)"
                label="Modelo"
                variant="outlined"
                density="compact"
                hide-details
                clearable
                no-data-text="Nenhum modelo encontrado"
              >
                <template v-slot:item="{ props, item }">
                  <v-list-item v-bind="props" :subtitle="item.raw.subtitle || item.raw.value"></v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
          </v-row>

          <v-row dense class="mb-2">
            <v-col cols="6">
              <v-text-field
                v-model.number="nodeConfig.temperature"
                label="Temperatura"
                type="number"
                min="0"
                max="2"
                step="0.1"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="0.1"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="nodeConfig.max_tokens"
                label="Max Tokens"
                type="number"
                min="50"
                max="128000"
                step="50"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="500"
              ></v-text-field>
            </v-col>
          </v-row>

          <v-textarea
            v-model="nodeConfig.criteria"
            label="Critério de Avaliação (Pergunta Sim/Não) *"
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-2 monospace-field"
            placeholder="Ex: O usuário solicitou informações financeiras ou relatórios?"
            hint="A IA avaliará a mensagem/resposta com base nesta pergunta e responderá Verdadeiro ou Falso"
            persistent-hint
          ></v-textarea>

          <v-textarea
            v-model="nodeConfig.prompt"
            label="Instruções Adicionais de Decisão (Opcional)"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-3 monospace-field"
            placeholder="Ex: Leve em consideração também as permissões do usuário..."
          ></v-textarea>

          <!-- Context & Payload Schema for Decision -->
          <v-divider class="my-3"></v-divider>
          <div class="d-flex align-center justify-space-between mb-1">
            <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
              <v-icon size="16" color="cyan">mdi-code-json</v-icon>Schema do Payload / Contexto
            </h4>
            <v-btn size="x-small" variant="tonal" color="cyan" prepend-icon="mdi-magic-staff" @click="insertDefaultPayloadSchema">
              Exemplo Igreja
            </v-btn>
          </div>
          <div class="mb-2 d-flex flex-wrap ga-1">
            <v-chip
              v-for="chip in quickTemplateChips"
              :key="chip.token"
              size="x-small"
              variant="tonal"
              color="primary"
              class="cursor-pointer"
              @click="insertTemplateToken(chip.token)"
            >
              + {{ chip.label }}
            </v-chip>
          </div>
          <v-textarea
            v-model="contextMappingJson"
            label="Mapeamento de Contexto (JSON)"
            placeholder='{\n  "permissions": "{{ member_fin.permissions }}"\n}'
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-3 monospace-field"
            @update:model-value="onContextMappingChange"
          ></v-textarea>
          <v-switch
            :model-value="nodeConfig.inject_full_context !== false"
            @update:model-value="val => { nodeConfig.inject_full_context = val; }"
            label="Injetar Payload Completo (<context_data>)"
            color="cyan"
            density="compact"
            hide-details
            class="mb-3"
          ></v-switch>
        </template>

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

      <!-- ── 6. WORKFLOW / SUB-WORKFLOW NODE PROPERTIES ────────────────── -->
      <div v-else-if="nodeType === 'workflow' || nodeType === 'sub_workflow'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="blue">mdi-sitemap</v-icon>Executar Workflow (Zero Custo LLM)
        </h4>

        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          <v-icon start size="14">mdi-information</v-icon>
          Workflows executam automações determinísticas (APIs HTTP, queries no banco, scripts) e injetam os resultados no contexto para os agentes seguintes.
        </v-alert>

        <v-autocomplete
          v-model="nodeConfig.workflow_id"
          :items="availableWorkflows"
          item-title="name"
          item-value="id"
          label="Workflow Alvo *"
          variant="outlined"
          density="compact"
          class="mb-3"
          prepend-inner-icon="mdi-sitemap"
          @update:model-value="onWorkflowSelect"
        >
          <template v-slot:item="{ props, item }">
            <v-list-item v-bind="props" :subtitle="item.raw.description || 'Sem descrição'"></v-list-item>
          </template>
        </v-autocomplete>

        <v-text-field
          v-model="nodeConfig.output_key"
          label="Chave de Saída no Contexto ($output_key)"
          variant="outlined"
          density="compact"
          placeholder="ex: dados_membros, relatorio_financeiro"
          class="mb-3"
          hint="O resultado do workflow ficará gravado nesta chave em $context"
          persistent-hint
        ></v-text-field>

        <v-switch
          v-model="nodeConfig.inject_into_prompt"
          color="primary"
          density="compact"
          label="Injetar automaticamente no Prompt dos próximos Agentes"
          class="mb-2"
          hint="Se ativado, os dados trazidos pelo workflow aparecem diretamente para o agente responder"
          persistent-hint
        ></v-switch>
      </div>

      <!-- ── 7. JUDGE / CURATOR / VERIFIER (LOOP) NODE PROPERTIES ───────── -->
      <div v-else-if="nodeType === 'judge' || nodeType === 'curator' || nodeType === 'verifier' || nodeType === 'guardrail'">
        <h4 class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center ga-1">
          <v-icon size="16" color="amber-darken-2">mdi-scale-balance</v-icon>Juiz de Qualidade & Curadoria
        </h4>

        <v-alert type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
          <div class="d-flex flex-column ga-1">
            <span><strong>● Saída Verde (True / Aprovado):</strong> Segue para o próximo passo.</span>
            <span><strong>● Saída Amarela (False / Refazer):</strong> Conecte de volta à entrada do agente para aplicar as correções sugeridas.</span>
          </div>
        </v-alert>

        <v-select
          v-model="nodeConfig.judge_mode"
          :items="[
            { title: '⚡ LLM Customizado (Prompt Inline)', value: 'llm' },
            { title: '🤖 Agente Especialista do Sistema', value: 'agent' }
          ]"
          label="Modo de Julgamento"
          variant="outlined"
          density="compact"
          class="mb-3"
        ></v-select>

        <v-autocomplete
          v-if="nodeConfig.judge_mode === 'agent'"
          v-model="nodeConfig.agent_id"
          :items="availableAgents"
          item-title="name"
          item-value="id"
          label="Agente Juiz / Auditor"
          variant="outlined"
          density="compact"
          class="mb-3"
        ></v-autocomplete>

        <template v-else>
          <!-- LLM Model & Provider Selection -->
          <h5 class="text-caption font-weight-bold text-medium-emphasis mb-1">Modelo de IA do Juiz:</h5>
          <v-row dense class="mb-2">
            <v-col cols="6">
              <v-select
                v-model="nodeConfig.provider_id"
                :items="providerOptions"
                label="Provedor LLM"
                variant="outlined"
                density="compact"
                hide-details
              ></v-select>
            </v-col>
            <v-col cols="6">
              <v-autocomplete
                v-model="nodeConfig.model"
                :items="getNodeModelOptions(nodeConfig.provider_id)"
                label="Modelo"
                variant="outlined"
                density="compact"
                hide-details
                clearable
                no-data-text="Nenhum modelo encontrado"
              >
                <template v-slot:item="{ props, item }">
                  <v-list-item v-bind="props" :subtitle="item.raw.subtitle || item.raw.value"></v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
          </v-row>

          <v-row dense class="mb-2">
            <v-col cols="6">
              <v-text-field
                v-model.number="nodeConfig.temperature"
                label="Temperatura"
                type="number"
                min="0"
                max="2"
                step="0.1"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="0.2"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="nodeConfig.max_tokens"
                label="Max Tokens"
                type="number"
                min="100"
                max="128000"
                step="100"
                variant="outlined"
                density="compact"
                hide-details
                placeholder="2000"
              ></v-text-field>
            </v-col>
          </v-row>

          <v-textarea
            v-model="nodeConfig.prompt"
            label="Instruções Gerais do Juiz (Prompt)"
            placeholder="Você é o Juiz e Curador de Qualidade. Avalie rigorosamente a resposta gerada de acordo com os critérios definidos..."
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-3 monospace-field"
            hint="Papel e diretrizes gerais da curadoria"
            persistent-hint
          ></v-textarea>
        </template>

        <!-- Presets de Curadoria -->
        <div class="mb-2">
          <span class="text-caption font-weight-bold text-medium-emphasis mb-1 d-block">
            Modelos de Critério Rápidos:
          </span>
          <div class="d-flex flex-wrap ga-1 mb-2">
            <v-chip
              size="x-small"
              variant="outlined"
              color="primary"
              class="cursor-pointer"
              @click="applyCriteriaPreset('precisao')"
            >
              Precisão & Fidelidade
            </v-chip>
            <v-chip
              size="x-small"
              variant="outlined"
              color="teal"
              class="cursor-pointer"
              @click="applyCriteriaPreset('pastoral')"
            >
              Tom Pastoral & Acolhedor
            </v-chip>
            <v-chip
              size="x-small"
              variant="outlined"
              color="amber"
              class="cursor-pointer"
              @click="applyCriteriaPreset('conformidade')"
            >
              Conformidade & Regras
            </v-chip>
            <v-chip
              size="x-small"
              variant="outlined"
              color="indigo"
              class="cursor-pointer"
              @click="applyCriteriaPreset('completude')"
            >
              Completude Total
            </v-chip>
          </div>
        </div>

        <v-textarea
          v-model="nodeConfig.criteria"
          label="Critérios de Avaliação do Juiz *"
          variant="outlined"
          density="compact"
          rows="4"
          placeholder="Ex: Verifique se a resposta está precisa, de tom acolhedor, respondeu a todas as dúvidas e não alucinou dados."
          class="mb-3 monospace-field"
          hint="O Juiz analisará a resposta do agente com base nestes critérios"
          persistent-hint
        ></v-textarea>

        <v-slider
          v-model="nodeConfig.max_retries"
          label="Limite de Loops de Auto-Correção"
          min="1"
          max="5"
          step="1"
          thumb-label="always"
          color="amber-darken-1"
          class="mt-4"
        ></v-slider>
        <span class="text-caption text-medium-emphasis d-block mb-3">
          Após atingir o limite de tentativas, a resposta segue com aviso para evitar loops infinitos.
        </span>

        <!-- Context & Payload Schema for Judge -->
        <v-divider class="my-3"></v-divider>
        <div class="d-flex align-center justify-space-between mb-1">
          <h4 class="text-subtitle-2 font-weight-bold d-flex align-center ga-1">
            <v-icon size="16" color="cyan">mdi-code-json</v-icon>Schema do Payload / Contexto
          </h4>
          <v-btn size="x-small" variant="tonal" color="cyan" prepend-icon="mdi-magic-staff" @click="insertDefaultPayloadSchema">
            Exemplo Igreja
          </v-btn>
        </div>
        <p class="text-caption text-medium-emphasis mb-2">
          Defina quais dados do payload o Juiz deve analisar para verificar conformidade.
        </p>
        <div class="mb-2 d-flex flex-wrap ga-1">
          <v-chip
            v-for="chip in quickTemplateChips"
            :key="chip.token"
            size="x-small"
            variant="tonal"
            color="primary"
            class="cursor-pointer"
            @click="insertTemplateToken(chip.token)"
          >
            + {{ chip.label }}
          </v-chip>
        </div>
        <v-textarea
          v-model="contextMappingJson"
          label="Mapeamento de Contexto (JSON)"
          placeholder='{\n  "user_name": "{{ member.name }}",\n  "permissions": "{{ member_fin.permissions }}"\n}'
          variant="outlined"
          density="compact"
          rows="3"
          class="mb-3 monospace-field"
          @update:model-value="onContextMappingChange"
        ></v-textarea>
        <v-switch
          :model-value="nodeConfig.inject_full_context !== false"
          @update:model-value="val => { nodeConfig.inject_full_context = val; }"
          label="Injetar Payload Completo (<context_data>)"
          color="cyan"
          density="compact"
          hide-details
          class="mb-3"
        ></v-switch>
      </div>

      <!-- ── 8. TOOL / ACTION NODE PROPERTIES ─────────────────────────── -->
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
import { computed, ref, onMounted, watch } from 'vue'
import axios from '@/plugins/axios'

const props = defineProps({
  selectedNode: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'delete'])

const availableAgents = ref([])
const availableWorkflows = ref([])
const availableMcps = ref([])
const availableSkills = ref([])
const availableAiProviders = ref([])
const availableModels = ref([])

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

// ── AGENT STATE ─────────────────────────────────────────────────────────────
const agentMode = ref(nodeConfig.value.agent_mode || (nodeConfig.value.inline_agent ? 'inline' : 'existing'))

const inlineAgent = ref({
  name: nodeConfig.value.inline_agent?.name || '',
  system_prompt: nodeConfig.value.inline_agent?.system_prompt || '',
  provider_id: nodeConfig.value.inline_agent?.provider_id || 'openai',
  model: nodeConfig.value.inline_agent?.model || 'gpt-4o-mini',
  temperature: nodeConfig.value.inline_agent?.temperature ?? 0.7,
  max_tokens: nodeConfig.value.inline_agent?.max_tokens ?? 2000,
  mcp_ids: nodeConfig.value.inline_agent?.mcp_ids || [],
  skill_ids: nodeConfig.value.inline_agent?.skill_ids || [],
})

const providerOptions = computed(() => {
  const options = [
    { title: '🟢 OpenAI', value: 'openai' },
    { title: '🟡 Google Gemini', value: 'google' },
    { title: '🟣 DeepSeek', value: 'deepseek' },
    { title: '🔵 OpenRouter', value: 'openrouter' }
  ]
  if (Array.isArray(availableAiProviders.value)) {
    availableAiProviders.value.forEach(p => {
      options.push({
        title: `🌐 ${p.name}`,
        value: p.id,
        isCustom: true,
        default_model: p.default_model
      })
    })
  }
  return options
})

function getNodeModelOptions(providerId) {
  const currentProv = providerId || 'openai'
  const filtered = (availableModels.value || [])
    .filter(m => m.provider === currentProv)
    .map(m => ({
      title: m.name || m.id,
      value: m.id,
      subtitle: m.context_length ? `${Math.round(m.context_length / 1000)}k ctx` : undefined
    }))

  if (filtered.length > 0) return filtered

  if (providerId) {
    const prov = (availableAiProviders.value || []).find(p => p.id === providerId)
    if (prov && prov.default_model) {
      return [{ title: prov.default_model, value: prov.default_model }]
    }
  }

  if (currentProv === 'google') {
    return [
      { title: 'gemini-2.5-flash', value: 'gemini-2.5-flash', subtitle: '1000k ctx' },
      { title: 'gemini-2.5-pro', value: 'gemini-2.5-pro', subtitle: '2000k ctx' },
      { title: 'gemini-2.0-flash', value: 'gemini-2.0-flash', subtitle: '1000k ctx' },
      { title: 'gemini-1.5-flash', value: 'gemini-1.5-flash', subtitle: '1000k ctx' }
    ]
  }
  if (currentProv === 'deepseek') {
    return [
      { title: 'deepseek-chat', value: 'deepseek-chat', subtitle: '64k ctx' },
      { title: 'deepseek-reasoner', value: 'deepseek-reasoner', subtitle: '64k ctx' }
    ]
  }
  if (currentProv === 'openrouter') {
    return [
      { title: 'anthropic/claude-3.5-sonnet', value: 'anthropic/claude-3.5-sonnet', subtitle: '200k ctx' },
      { title: 'meta-llama/llama-3.3-70b-instruct', value: 'meta-llama/llama-3.3-70b-instruct', subtitle: '128k ctx' },
      { title: 'google/gemini-2.5-flash', value: 'google/gemini-2.5-flash', subtitle: '1000k ctx' }
    ]
  }
  return [
    { title: 'gpt-4o-mini', value: 'gpt-4o-mini', subtitle: '128k ctx' },
    { title: 'gpt-4o', value: 'gpt-4o', subtitle: '128k ctx' },
    { title: 'o3-mini', value: 'o3-mini', subtitle: '200k ctx' }
  ]
}

const inlineModelOptions = computed(() => getNodeModelOptions(inlineAgent.value.provider_id))

function onProviderChange(provId) {
  if (!provId) {
    inlineAgent.value.provider_id = 'openai'
    provId = 'openai'
  }
  const available = (availableModels.value || []).filter(m => m.provider === provId)
  if (available.length > 0) {
    inlineAgent.value.model = available[0].id
  } else {
    const prov = (availableAiProviders.value || []).find(p => p.id === provId)
    if (prov && prov.default_model) {
      inlineAgent.value.model = prov.default_model
    } else if (provId === 'google') {
      inlineAgent.value.model = 'gemini-2.5-flash'
    } else if (provId === 'deepseek') {
      inlineAgent.value.model = 'deepseek-chat'
    } else if (provId === 'openrouter') {
      inlineAgent.value.model = 'anthropic/claude-3.5-sonnet'
    } else {
      inlineAgent.value.model = 'gpt-4o-mini'
    }
  }
  onInlineAgentChange()
}

function onInlineAgentChange() {
  nodeConfig.value.inline_agent = { ...inlineAgent.value }
  nodeConfig.value.agent_mode = 'inline'
}

watch(agentMode, (newMode) => {
  nodeConfig.value.agent_mode = newMode
  if (newMode === 'inline') {
    nodeConfig.value.agent_id = null
    if (!nodeConfig.value.inline_agent) {
      nodeConfig.value.inline_agent = { ...inlineAgent.value }
    }
  } else {
    nodeConfig.value.inline_agent = null
  }
})

// ── ROUTER STATE ────────────────────────────────────────────────────────────
const routerRoutes = ref(nodeConfig.value.routes || [])

function addRoute() {
  const newIndex = routerRoutes.value.length
  const newRoute = {
    id: `route_${newIndex}`,
    name: `Rota ${newIndex + 1}`,
    description: ''
  }
  routerRoutes.value.push(newRoute)
  onRoutesChange()
}

function removeRoute(idx) {
  routerRoutes.value.splice(idx, 1)
  routerRoutes.value.forEach((r, i) => {
    if (r.id.startsWith('route_')) {
      r.id = `route_${i}`
    }
  })
  onRoutesChange()
}

function moveRoute(idx, delta) {
  const targetIdx = idx + delta
  if (targetIdx < 0 || targetIdx >= routerRoutes.value.length) return
  const item = routerRoutes.value.splice(idx, 1)[0]
  routerRoutes.value.splice(targetIdx, 0, item)
  onRoutesChange()
}

function onRoutesChange() {
  nodeConfig.value.routes = [...routerRoutes.value]
}

// ── CRITERIA PRESETS ────────────────────────────────────────────────────────
function applyCriteriaPreset(presetKey) {
  if (presetKey === 'precisao') {
    nodeConfig.value.criteria = 'Verifique se a resposta está precisa, lógica, fiel aos dados reais e sem qualquer tipo de alucinação ou suposição infundada.'
  } else if (presetKey === 'pastoral') {
    nodeConfig.value.criteria = 'Verifique se a resposta utiliza um tom acolhedor, empático, amoroso e encorajador, adequado ao ambiente eclesiástico/pastoral.'
  } else if (presetKey === 'conformidade') {
    nodeConfig.value.criteria = 'Verifique se a resposta respeita estritamente as regras de conformidade, sigilo de dados (LGPD) e validação correta de registros e valores.'
  } else if (presetKey === 'completude') {
    nodeConfig.value.criteria = 'Verifique se todas as dúvidas, instruções ou perguntas feitas pelo usuário foram integralmente e diretamente respondidas sem deixar pontas soltas.'
  }
}

// ── CONTEXT MAPPING & SCHEMAS STATE ───────────────────────────────────────
const contextMappingJson = ref(
  nodeConfig.value.context_mapping ? JSON.stringify(nodeConfig.value.context_mapping, null, 2) : ''
)
const outputSchemaJson = ref(
  nodeConfig.value.output_schema ? JSON.stringify(nodeConfig.value.output_schema, null, 2) : ''
)

const quickTemplateChips = [
  { label: 'Nome Usuário', token: '{{ member.name }}' },
  { label: 'Perfil/Role', token: '{{ member_fin.role_profile }}' },
  { label: 'Permissões', token: '{{ member_fin.permissions }}' },
  { label: 'Nome Igreja', token: '{{ church.church_name }}' },
  { label: 'Rótulo Célula', token: '{{ ai_params.label_cell }}' },
  { label: 'Data/Hora Atual', token: '{{ $now(%A, %d/%m/%Y %H:%M) }}' },
  { label: 'Idioma', token: '{{ church.preferredLanguage }}' },
  { label: 'Telefone', token: '{{ member.phone }}' }
]

function onContextMappingChange(val) {
  try {
    if (!val || !val.trim()) {
      delete nodeConfig.value.context_mapping
    } else {
      nodeConfig.value.context_mapping = JSON.parse(val)
    }
  } catch (e) {
    // typing JSON
  }
}

function onOutputSchemaChange(val) {
  try {
    if (!val || !val.trim()) {
      delete nodeConfig.value.output_schema
    } else {
      nodeConfig.value.output_schema = JSON.parse(val)
    }
  } catch (e) {
    // typing JSON
  }
}

function insertDefaultPayloadSchema() {
  const defaultSchema = {
    "user_name": "{{ member.name }}",
    "user_role": "{{ member_fin.role_profile }}",
    "permissions": "{{ member_fin.permissions }}",
    "church_name": "{{ church.church_name }}",
    "label_cell": "{{ ai_params.label_cell }}"
  }
  nodeConfig.value.context_mapping = defaultSchema
  contextMappingJson.value = JSON.stringify(defaultSchema, null, 2)
}

function insertTemplateToken(token) {
  let current = {}
  try {
    if (contextMappingJson.value && contextMappingJson.value.trim()) {
      current = JSON.parse(contextMappingJson.value)
    }
  } catch {}
  const cleanKey = token.replace(/[{}$\s%]/g, '').split('.').pop().replace(/[^a-zA-Z0-9_]/g, '_') || 'campo'
  current[cleanKey] = token
  nodeConfig.value.context_mapping = current
  contextMappingJson.value = JSON.stringify(current, null, 2)
}

// ── SYNC ON NODE CHANGE ─────────────────────────────────────────────────────
watch(() => props.selectedNode.id, () => {
  agentMode.value = nodeConfig.value.agent_mode || (nodeConfig.value.inline_agent ? 'inline' : 'existing')
  inlineAgent.value = {
    name: nodeConfig.value.inline_agent?.name || '',
    system_prompt: nodeConfig.value.inline_agent?.system_prompt || '',
    provider_id: nodeConfig.value.inline_agent?.provider_id || 'openai',
    model: nodeConfig.value.inline_agent?.model || 'gpt-4o-mini',
    temperature: nodeConfig.value.inline_agent?.temperature ?? 0.7,
    max_tokens: nodeConfig.value.inline_agent?.max_tokens ?? 2000,
    mcp_ids: nodeConfig.value.inline_agent?.mcp_ids || [],
    skill_ids: nodeConfig.value.inline_agent?.skill_ids || [],
  }
  routerRoutes.value = nodeConfig.value.routes || []
  contextMappingJson.value = nodeConfig.value.context_mapping ? JSON.stringify(nodeConfig.value.context_mapping, null, 2) : ''
  outputSchemaJson.value = nodeConfig.value.output_schema ? JSON.stringify(nodeConfig.value.output_schema, null, 2) : ''
})

const NODE_META = {
  start:        { icon: 'mdi-play-circle',       color: '#10B981', label: 'Início / Trigger' },
  agent:        { icon: 'mdi-robot',             color: '#3B82F6', label: 'Agente Especialista' },
  workflow:     { icon: 'mdi-sitemap',           color: '#2563EB', label: 'Workflow (Dados)' },
  sub_workflow: { icon: 'mdi-sitemap',           color: '#2563EB', label: 'Workflow (Dados)' },
  router:       { icon: 'mdi-source-branch',     color: '#8B5CF6', label: 'Supervisor / Router' },
  supervisor:   { icon: 'mdi-account-supervisor', color: '#8B5CF6', label: 'Supervisor / Router' },
  parallel:     { icon: 'mdi-call-split',        color: '#06B6D4', label: 'Fan-Out Paralelo' },
  synthesizer:  { icon: 'mdi-call-merge',        color: '#EC4899', label: 'Sintetizador Fan-In' },
  condition:    { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  decision:     { icon: 'mdi-help-rhombus',      color: '#F59E0B', label: 'Decisão / Condição' },
  judge:        { icon: 'mdi-scale-balance',     color: '#EAB308', label: 'Juiz / Curador' },
  curator:      { icon: 'mdi-shield-check',      color: '#EAB308', label: 'Juiz / Curador' },
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

const fetchWorkflows = async () => {
  try {
    const res = await axios.get('/workflows?limit=200')
    availableWorkflows.value = res.data.workflows || res.data || []
  } catch (e) {
    console.error('Erro ao buscar workflows:', e)
  }
}

const fetchMcps = async () => {
  try {
    const res = await axios.get('/mcp')
    availableMcps.value = res.data.mcps || []
  } catch (e) {
    console.error('Erro ao buscar MCPs:', e)
  }
}

const fetchSkills = async () => {
  try {
    const res = await axios.get('/skills/', { params: { all: true, limit: 200 } })
    availableSkills.value = res.data.skills || []
  } catch (e) {
    console.error('Erro ao buscar Skills:', e)
  }
}

const fetchAiProviders = async () => {
  try {
    const res = await axios.get('/ai-providers', { params: { limit: 100 } })
    availableAiProviders.value = res.data.providers || []
  } catch (e) {
    console.error('Erro ao buscar Provedores de IA:', e)
  }
}

const fetchModels = async () => {
  try {
    const res = await axios.get('/models/available')
    availableModels.value = res.data.models || []
  } catch (e) {
    try {
      const res2 = await axios.get('/models')
      availableModels.value = res2.data.models || []
    } catch (e2) {
      console.error('Erro ao buscar Modelos:', e)
    }
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

const onWorkflowSelect = (wfId) => {
  const wf = availableWorkflows.value.find(w => w.id === wfId)
  if (wf) {
    nodeConfig.value.workflow_name = wf.name
    if (!nodeConfig.value.output_key) {
      nodeConfig.value.output_key = (wf.name || 'wf_data').toLowerCase().replace(/[^a-z0-9_]/g, '_').slice(0, 25)
    }
    if (!nodeData.value.label || nodeData.value.label === 'Workflow (Dados)') {
      nodeData.value.label = wf.name
    }
  }
}

onMounted(() => {
  fetchAgents()
  fetchWorkflows()
  fetchMcps()
  fetchSkills()
  fetchAiProviders()
  fetchModels()
})
</script>

<style scoped>
.properties-panel {
  width: 340px;
  border-left: 1px solid rgba(255, 255, 255, 0.12);
  background: #111625 !important;
}

.route-card {
  transition: all 0.2s ease;
}

.route-card:hover {
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15);
}

.monospace-field :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
  font-size: 12px !important;
}
</style>
