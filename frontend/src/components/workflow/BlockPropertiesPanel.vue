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
          :items="[
            { title: 'Evento de Entrada (Padrão)', value: 'event' },
            { title: 'Webhook Externo (HTTP)', value: 'webhook' },
            { title: 'Agendamento (Cron/Horário)', value: 'schedule' },
            { title: 'Disparo Manual (Teste)', value: 'manual' }
          ]"
          item-title="title"
          item-value="value"
          label="Tipo de Gatilho"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="onTriggerTypeChange"
        ></v-select>

        <!-- Event Trigger Info -->
        <div v-if="!config.trigger_type || config.trigger_type === 'event'" class="mb-3">
          <v-alert type="info" variant="tonal" density="compact" class="text-caption">
            Este gatilho ativa o workflow a partir de eventos do sistema, como mensagens no chat. 
            Configure as palavras-chave nas configurações do Workflow (ícone de engrenagem no topo).
          </v-alert>
        </div>

        <!-- Webhook Trigger Configuration -->
        <div v-if="config.trigger_type === 'webhook'">
          <v-text-field
            v-model="config.webhook_path"
            label="Caminho do Webhook (path)"
            placeholder="meu-gatilho-vendas"
            variant="outlined"
            density="compact"
            class="mb-3"
            hint="Defina um caminho único para disparar este workflow"
            persistent-hint
            @update:model-value="emitUpdate"
          ></v-text-field>
          
          <v-alert v-if="config.webhook_path" type="success" variant="tonal" density="compact" class="mb-3 text-caption">
            <div class="font-weight-bold mb-1">URL para Disparo:</div>
            <code class="text-caption d-block my-1" style="word-break: break-all; color: #10B981; font-family: monospace;">{{ webhookUrl }}</code>
            <v-btn size="x-small" variant="outlined" color="success" class="mt-1" @click="copyWebhookUrl">
              <v-icon start size="12">mdi-content-copy</v-icon> Copiar URL
            </v-btn>
          </v-alert>

          <v-select
            v-model="config.webhook_config_id"
            :items="webhookConfigs"
            item-title="name"
            item-value="id"
            label="Webhook Config (Autenticação opcional)"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            class="mb-3"
            @update:model-value="emitUpdate"
          ></v-select>
        </div>

        <!-- Schedule Trigger Configuration -->
        <div v-if="config.trigger_type === 'schedule'">
          <v-text-field
            v-model="config.cron"
            label="Expressão Cron"
            placeholder="*/15 * * * *"
            variant="outlined"
            density="compact"
            class="mb-3"
            hint="Padrão de 5 campos. Ex: */15 * * * * (a cada 15 min), 0 9 * * * (todo dia às 9h)"
            persistent-hint
            @update:model-value="emitUpdate"
          ></v-text-field>
        </div>

        <!-- Manual Trigger Configuration -->
        <div v-if="config.trigger_type === 'manual'" class="mb-3">
          <v-alert type="info" variant="tonal" density="compact" class="text-caption">
            Este gatilho é disparado manualmente ou via testes. 
            Use o botão "Executar" (ou ícone Play) no painel superior do editor para testar e simular.
          </v-alert>
        </div>
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
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          <div v-if="config.mode === 'first_match'">
            <v-icon size="14" class="mr-1">mdi-information</v-icon>
            Conecte cada saída (Regra 1, Regra 2...) e a saída de erro (Outro) aos blocos correspondentes no canvas.
          </div>
          <div v-else>
            <v-icon size="14" class="mr-1">mdi-information</v-icon>
            Conecte as saídas Match (Verde) e Outro (Vermelho) aos blocos correspondentes no canvas.
          </div>
        </v-alert>
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
        <v-switch
          :model-value="config.inject_full_context !== false"
          @update:model-value="val => { config.inject_full_context = val; emitUpdate(); }"
          label="Injetar Contexto Completo"
          color="primary"
          density="compact"
          class="mb-3"
          hint="Se desativado, o agente não recebe o histórico de blocos do workflow por padrão (reduz o prompt)"
          persistent-hint
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

      <!-- ═══ VARIABLES ═══ -->
      <template v-if="block.type === 'variables'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Defina variáveis estáticas (fixas) ou dinâmicas que acumulam valores ao longo da execução do workflow.
        </v-alert>

        <div v-for="(v, idx) in (config.variables || [])" :key="idx" class="rule-item mb-3 pa-3 rounded border">
          <div class="d-flex justify-space-between align-center mb-2">
            <span class="text-caption font-weight-bold">Variável {{ idx + 1 }}</span>
            <v-btn icon variant="text" size="x-small" color="error" @click="removeVariable(idx)">
              <v-icon size="16">mdi-close</v-icon>
            </v-btn>
          </div>
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model="v.name"
                label="Nome"
                placeholder="celula"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-2"
                @update:model-value="emitUpdate"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-select
                v-model="v.type"
                :items="[
                  { title: 'Texto (string)', value: 'string' },
                  { title: 'Número (number)', value: 'number' },
                  { title: 'Booleano (boolean)', value: 'boolean' },
                  { title: 'Lista (array)', value: 'array' },
                  { title: 'Objeto (object)', value: 'object' }
                ]"
                label="Tipo"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-2"
                @update:model-value="emitUpdate"
              ></v-select>
            </v-col>
          </v-row>
          <v-row dense>
            <v-col cols="6">
              <v-select
                v-model="v.mode"
                :items="[
                  { title: 'Dinâmico', value: 'dynamic' },
                  { title: 'Fixo (Constante)', value: 'fixed' }
                ]"
                label="Origem"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-2"
                @update:model-value="emitUpdate"
              ></v-select>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-if="v.mode === 'fixed'"
                v-model="v.value"
                label="Valor Fixo"
                placeholder="Valor estático"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-2"
                @update:model-value="emitUpdate"
              ></v-text-field>
              <v-text-field
                v-else
                v-model="v.expression"
                label="Expressão"
                placeholder="{{ $trigger.payload.celula }}"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-2"
                @update:model-value="emitUpdate"
              ></v-text-field>
            </v-col>
          </v-row>
        </div>

        <v-btn size="small" variant="tonal" color="primary" @click="addVariable" class="mb-3 w-100">
          <v-icon start size="16">mdi-plus</v-icon> Adicionar Variável
        </v-btn>
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

      <!-- ═══ RESPONSE / SAÍDA ═══ -->
      <template v-if="block.type === 'response'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Este bloco define a resposta a ser enviada no payload de saída, retornando o resultado do bloco anterior.
        </v-alert>
        <v-switch
          :model-value="config.store_in_memory !== false"
          @update:model-value="val => { config.store_in_memory = val; emitUpdate(); }"
          label="Salvar Saída no Histórico/Memória"
          color="primary"
          density="compact"
          class="mb-3"
          hint="Se desativado, a resposta final deste workflow não será salva no histórico de conversas do banco de dados (MTM) e da memória de curto prazo (Redis)."
          persistent-hint
        ></v-switch>

        <v-switch
          v-model="config.saida_direcionada"
          @update:model-value="emitUpdate"
          label="Saída Direcionada (Webhook)"
          color="primary"
          density="compact"
          class="mb-3"
          hint="Permite enviar o payload final para uma URL/Endpoint externo."
          persistent-hint
        ></v-switch>

        <v-text-field
          v-if="config.saida_direcionada"
          v-model="config.endpoint_url"
          label="URL / Path do Endpoint HTTP"
          placeholder="https://sua-api.com/webhook"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Opcional. Se preenchido, fará um POST com o resultado final para esta URL."
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>

        <v-switch
          :model-value="config.bypass_agente !== false"
          @update:model-value="val => { config.bypass_agente = val; emitUpdate(); }"
          label="Modo Bypass (Encerrar Fluxo)"
          color="warning"
          density="compact"
          class="mb-3"
          hint="Se ativado, não chamará nenhum agente do bot ao final deste fluxo."
          persistent-hint
        ></v-switch>

        <v-select
          v-if="config.bypass_agente === false"
          v-model="config.agente_direcionado"
          :items="agents"
          item-title="name"
          item-value="id"
          label="Agente Direcionado"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
          hint="Substituirá o agente principal. Qual agente deve continuar o fluxo?"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-select>
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

      <!-- ═══ PYTHON ═══ -->
      <template v-if="block.type === 'python'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Escreva código Python. Atribua o resultado à variável <code>result</code>.
          Use <code>ctx</code> ou <code>context</code> para acessar o contexto do workflow.
        </v-alert>
        <v-textarea
          v-model="config.code"
          label="Código Python"
          placeholder="members = ctx['$members']['data']\nresult = {'count': len(members)}"
          variant="outlined"
          density="compact"
          rows="14"
          class="mb-3 monospace-field"
          hide-details
          no-resize
          @update:model-value="emitUpdate"
        ></v-textarea>
        <v-alert type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
          ⚠️ Não use import, open(), requests, subprocess ou qualquer acesso ao sistema.
          Funções disponíveis: len, range, sorted, json, re, datetime.
        </v-alert>
      </template>

      <!-- ═══ MCP ═══ -->
      <template v-if="block.type === 'mcp'">
        <v-select
          v-model="config.mcp_id"
          :items="mcps"
          item-title="name"
          item-value="id"
          label="Selecionar MCP"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
          hide-details
          @update:model-value="onMcpSelected"
        ></v-select>

        <!-- Show MCP details when selected -->
        <template v-if="selectedMcpDetails">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
            <strong>{{ selectedMcpDetails.name }}</strong><br/>
            <span v-if="selectedMcpDetails.description">{{ selectedMcpDetails.description }}<br/></span>
            <span>Protocolo: <code>{{ selectedMcpDetails.protocol }}</code> · Método: <code>{{ selectedMcpDetails.method }}</code></span>
          </v-alert>

          <!-- $fromAI params from body_template -->
          <div v-if="mcpFromAiFields.length" class="mb-3">
            <p class="text-caption text-medium-emphasis mb-2">
              <v-icon size="14" class="mr-1">mdi-robot</v-icon>
              Parâmetros do MCP (<code>$fromAI</code>)
            </p>
            <div v-for="field in mcpFromAiFields" :key="field.key" class="mb-2">
              <v-text-field
                :model-value="getMcpParam(field.key)"
                :label="field.key"
                :placeholder="field.desc || `{{ $trigger.payload.${field.key} }}`"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="val => setMcpParam(field.key, val)"
              ></v-text-field>
            </div>
          </div>

          <!-- $request variables from endpoint/body -->
          <div v-if="mcpRequestFields.length" class="mb-3">
            <p class="text-caption text-medium-emphasis mb-2">
              <v-icon size="14" class="mr-1">mdi-variable</v-icon>
              Variáveis de Contexto (<code>$request</code>)
            </p>
            <div v-for="field in mcpRequestFields" :key="field" class="mb-2">
              <v-text-field
                :model-value="getMcpVariable(field)"
                :label="field"
                :placeholder="`{{ $trigger.payload.${field.split('.').pop()} }}`"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="val => setMcpVariable(field, val)"
              ></v-text-field>
            </div>
          </div>
        </template>

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
      </template>

      <!-- ═══ VECTOR INSERT / SALVAR NA BASE ═══ -->
      <template v-if="block.type === 'vector_insert'">
        <v-select
          v-model="config.base_code"
          :items="informationBases"
          item-title="name"
          item-value="code"
          label="Base de Informações"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
          hide-details
          @update:model-value="emitUpdate"
        ></v-select>

        <v-text-field
          v-model="config.user_id"
          label="ID do Usuário (user_id)"
          placeholder="{{ $trigger.payload.user_id }}"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Suporta templates do contexto"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>

        <v-text-field
          v-model="config.external_id"
          label="ID Externo (external_id - Opcional)"
          placeholder="{{ $trigger.payload.id }}"
          variant="outlined"
          density="compact"
          class="mb-3"
          hint="Limpará blocos antigos com o mesmo ID para evitar duplicatas"
          persistent-hint
          @update:model-value="emitUpdate"
        ></v-text-field>

        <v-textarea
          v-model="vectorInsertDataJson"
          label="Dados para Salvar (JSON ou String)"
          placeholder='{"texto": "{{ $trigger.payload.text }}", "categoria": "faq"}'
          variant="outlined"
          density="compact"
          rows="6"
          class="mb-3 monospace-field"
          hint="Dados que serão processados de acordo com o esquema da base selecionada"
          persistent-hint
          @update:model-value="onVectorInsertDataChange"
        ></v-textarea>
      </template>

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
  mcps: { type: Array, default: () => [] },
  currentWorkflowId: { type: String, default: null },
  informationBases: { type: Array, default: () => [] },
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
  response:     { icon: 'mdi-logout',            color: '#EC4899', label: 'Configurar Saída' },
  python:       { icon: 'mdi-language-python',   color: '#3B82F6', label: 'Configurar Python' },
  mcp:          { icon: 'mdi-connection',        color: '#14B8A6', label: 'Configurar MCP' },
  variables:    { icon: 'mdi-variable',          color: '#10B981', label: 'Configurar Variáveis' },
  vector_insert:{ icon: 'mdi-database-plus',     color: '#10B981', label: 'Configurar Salvar na Base' },
}

const meta = computed(() => BLOCK_META[props.block.type] || { icon: 'mdi-help-circle', color: '#9CA3AF', label: 'Configurar Bloco' })

const config = computed(() => {
  if (!props.block.config) props.block.config = {}
  return props.block.config
})

// ── MCP block helpers ─────────────────────────────────────────────────────
const selectedMcpDetails = computed(() => {
  if (props.block.type !== 'mcp' || !config.value.mcp_id) return null
  return props.mcps.find(m => m.id === config.value.mcp_id) || null
})

/** Extract {{ $fromAI('key', 'desc') }} occurrences from body_template + query_template */
const mcpFromAiFields = computed(() => {
  if (!selectedMcpDetails.value) return []
  const mcp = selectedMcpDetails.value
  const src = JSON.stringify({ ...mcp.body_template, ...mcp.query_template })
  const re = /\$fromAI\(\s*'([^']+)'\s*(?:,\s*'([^']*)')?/g
  const fields = []
  const seen = new Set()
  let m
  while ((m = re.exec(src)) !== null) {
    if (!seen.has(m[1])) {
      seen.add(m[1])
      fields.push({ key: m[1], desc: m[2] || '' })
    }
  }
  return fields
})

/** Extract {{ $request.xxx }} dot-path keys from endpoint + body + headers + query */
const mcpRequestFields = computed(() => {
  if (!selectedMcpDetails.value) return []
  const mcp = selectedMcpDetails.value
  const src = JSON.stringify([
    mcp.endpoint, mcp.body_template, mcp.headers, mcp.query_template
  ])
  const re = /\$request\.([\w.]+)/g
  const fields = []
  const seen = new Set()
  let m
  while ((m = re.exec(src)) !== null) {
    if (!seen.has(m[1])) {
      seen.add(m[1])
      fields.push(m[1])
    }
  }
  return fields
})

function getMcpParam(key) {
  return (config.value.params || {})[key] || ''
}
function setMcpParam(key, val) {
  if (!config.value.params) config.value.params = {}
  config.value.params[key] = val
  emitUpdate()
}
function getMcpVariable(key) {
  return (config.value.variables || {})[key] || ''
}
function setMcpVariable(key, val) {
  if (!config.value.variables) config.value.variables = {}
  config.value.variables[key] = val
  emitUpdate()
}
function onMcpSelected(id) {
  const mcp = props.mcps.find(m => m.id === id)
  if (mcp) {
    config.value.mcp_name = mcp.name
    // Reset params/variables when MCP changes
    config.value.params = {}
    config.value.variables = {}
  }
  emitUpdate()
}

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
const vectorInsertDataJson = ref(typeof config.value.data === 'object' ? JSON.stringify(config.value.data, null, 2) : (config.value.data || ''))

watch(() => props.block.id, () => {
  headersJson.value = JSON.stringify(config.value.headers || {}, null, 2)
  queryJson.value = JSON.stringify(config.value.query_params || {}, null, 2)
  bodyJson.value = typeof config.value.body === 'object' ? JSON.stringify(config.value.body, null, 2) : (config.value.body || '')
  contextMappingJson.value = JSON.stringify(config.value.context_mapping || {}, null, 2)
  responseMappingJson.value = JSON.stringify(config.value.response_mapping || {}, null, 2)
  payloadTemplateJson.value = typeof config.value.payload_template === 'object' ? JSON.stringify(config.value.payload_template, null, 2) : (config.value.payload_template || '')
  vectorInsertDataJson.value = typeof config.value.data === 'object' ? JSON.stringify(config.value.data, null, 2) : (config.value.data || '')
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
function onVectorInsertDataChange(val) {
  try { config.value.data = JSON.parse(val) } catch { config.value.data = val }
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

function addVariable() {
  if (!config.value.variables) config.value.variables = []
  config.value.variables.push({ name: '', type: 'string', mode: 'dynamic', value: '', expression: '' })
  emitUpdate()
}
function removeVariable(idx) {
  config.value.variables.splice(idx, 1)
  emitUpdate()
}

function copyVar(key) {
  navigator.clipboard.writeText(`{{ $${key} }}`)
}

const webhookUrl = computed(() => {
  if (!config.value.webhook_path) return ''
  const base = window.location.origin
  return `${base}/api/workflows/trigger/${config.value.webhook_path}`
})

function copyWebhookUrl() {
  if (webhookUrl.value) {
    navigator.clipboard.writeText(webhookUrl.value)
  }
}

function onTriggerTypeChange(val) {
  if (val === 'webhook') {
    if (!config.value.webhook_path) config.value.webhook_path = ''
  } else if (val === 'schedule') {
    if (!config.value.cron) config.value.cron = '*/15 * * * *'
  }
  emitUpdate()
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
