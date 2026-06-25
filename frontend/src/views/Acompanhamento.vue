<template>
  <div class="tracking-page" style="overflow-y:auto; max-height:90vh; padding-bottom:40px;">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-icon">
          <v-icon size="32" color="primary">mdi-chart-timeline-variant</v-icon>
        </div>
        <div class="header-text">
          <h1>Acompanhamento e Rastreio</h1>
          <p>Monitore requisições, status dos jobs e webhooks processados</p>
        </div>
      </div>
      <div class="d-flex align-center ga-3">
        <div class="d-flex align-center ga-1" v-if="sseConnected">
          <span class="sse-dot"></span>
          <span class="text-caption text-success">Tempo real ativo</span>
        </div>
        <div class="d-flex align-center ga-1" v-else>
          <span class="sse-dot sse-offline"></span>
          <span class="text-caption text-medium-emphasis">Desconectado</span>
        </div>
        <v-btn color="primary" @click="fetchData" :loading="loading" prepend-icon="mdi-refresh" elevation="3">
          Atualizar
        </v-btn>
      </div>
    </div>

    <!-- Tabs Header -->
    <v-tabs v-model="activeTab" color="primary" class="mb-6">
      <v-tab value="webhooks">Webhooks</v-tab>
      <v-tab value="entradas">Entradas (Ingress)</v-tab>
      <v-tab value="notificacoes">Notificações</v-tab>
      <v-tab value="disparador">Disparador</v-tab>
      <v-tab value="gatilhos-disparador">Gatilhos Disparador</v-tab>
      <v-tab value="automacao">Automação</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <template v-for="tabItem in ['webhooks', 'notificacoes']" :key="tabItem">
      <v-window-item :value="tabItem">
    <!-- Stats Summary Row -->
    <v-card class="glass-card mb-6 overflow-x-auto" style="white-space: nowrap; overflow-y: hidden;">
      <v-card-text class="d-flex align-center py-4" style="gap: 16px;">
        <!-- Total Card -->
        <v-card class="d-inline-flex flex-column align-center justify-center pa-3 rounded-lg border" min-width="120" elevation="0" style="background-color: rgba(123, 31, 162, 0.3); border-color: rgba(255,255,255,0.1) !important;">
          <div class="text-overline text-white opacity-80 mb-1" style="line-height: 1.2;">TOTAL</div>
          <div class="text-h5 font-weight-bold text-white" style="line-height: 1.2;">{{ trackingStats.total_calls || 0 }}</div>
        </v-card>

        <!-- Divider -->
        <v-divider vertical class="mx-2 bg-white opacity-20" style="height: 40px; align-self: center;"></v-divider>
        
        <!-- Path Cards -->
        <v-card 
          v-for="(item, i) in trackingStats.by_path" 
          :key="i"
          class="d-inline-flex flex-column align-center justify-center pa-3 rounded-lg border" 
          min-width="120"
          elevation="0"
          style="background-color: rgba(156, 39, 176, 0.3); border-color: rgba(255,255,255,0.1) !important;"
        >
          <div class="text-overline text-white opacity-80 mb-1 text-truncate" style="max-width: 180px; line-height: 1.2;" :title="item.path">
            {{ item.path.split('/').pop().toUpperCase() }}
          </div>
          <div class="text-h5 font-weight-bold text-white" style="line-height: 1.2;">{{ item.count }}</div>
        </v-card>
        
        <div v-if="trackingStats.by_path?.length === 0" class="text-medium-emphasis text-body-2 font-italic ml-2">
          Nenhum dado encontrado
        </div>
      </v-card-text>
    </v-card>

    <!-- Data Table -->
    <v-card class="glass-card">
      <v-card-title class="d-flex align-center px-6 py-4">
        <v-icon class="mr-2" color="primary">mdi-history</v-icon>
        <span class="text-white font-weight-medium">Histórico de Webhooks</span>
      </v-card-title>
      
      <v-divider></v-divider>

      <v-card-text class="px-6 py-4" style="max-height: 65vh; overflow-y:auto; padding-bottom: 20px;">
        <v-row dense>
          <v-col cols="12" sm="6" md="3">
            <v-combobox v-model="searchPaths" :items="availablePaths" multiple chips closable-chips prepend-inner-icon="mdi-magnify" placeholder="Buscar Paths..." variant="outlined" density="compact" hide-details @update:model-value="onSearchPathsChange"></v-combobox>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field v-model="searchSessionId" prepend-inner-icon="mdi-identifier" placeholder="Buscar Session ID..." variant="outlined" density="compact" hide-details @keyup.enter="fetchLogs"></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field v-model="searchChurchName" prepend-inner-icon="mdi-church" placeholder="Buscar Igreja..." variant="outlined" density="compact" hide-details @keyup.enter="fetchLogs"></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field v-model="searchMemberName" prepend-inner-icon="mdi-account" placeholder="Buscar Nome..." variant="outlined" density="compact" hide-details @keyup.enter="fetchLogs"></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field v-model="searchMessage" prepend-inner-icon="mdi-message-text" placeholder="Buscar na Mensagem..." variant="outlined" density="compact" hide-details @keyup.enter="fetchLogs"></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field v-model="searchResponse" prepend-inner-icon="mdi-robot" placeholder="Buscar na Resposta..." variant="outlined" density="compact" hide-details @keyup.enter="fetchLogs"></v-text-field>
          </v-col>
          <v-col cols="12" sm="12" md="4">
            <v-select v-model="statusFilter" :items="statusOptions" label="Status" variant="outlined" density="compact" hide-details clearable @update:model-value="fetchLogs"></v-select>
          </v-col>
        </v-row>
      </v-card-text>
      
      <v-divider></v-divider>
      
      <v-data-table
        :headers="headers"
        :items="logs"
        :loading="loading"
        :items-per-page="itemsPerPage"
        :items-per-page-options="itemsPerPageOptions"
        :items-length="totalItems"
        v-model:page="page"
        show-current-page
        @update:options="handleOptionsUpdate"
        hover
        class="bg-transparent"
      >
        <template v-slot:item.created_at="{ item }">
          <span class="text-body-2">{{ formatDate(item.created_at) }}</span>
        </template>
        
        <template v-slot:item.session_id="{ item }">
          <div v-if="item.session_id" class="text-body-2 font-weight-medium text-info text-truncate" style="max-width: 100px" :title="item.session_id">
            {{ item.session_id }}
          </div>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template v-slot:item.church_name="{ item }">
          <span v-if="item.church_name" class="text-body-2">{{ item.church_name }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template v-slot:item.member_fullname="{ item }">
          <span v-if="item.member_fullname" class="text-body-2">{{ item.member_fullname }}</span>
          <span v-else-if="item.request_data?.member?.fullname" class="text-body-2">{{ item.request_data.member.fullname }}</span>
          <span v-else-if="item.request_data?.context_data?.name" class="text-body-2">{{ item.request_data.context_data.name }}</span>
          <span v-else-if="item.request_data?.name" class="text-body-2">{{ item.request_data.name }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template v-slot:item.user_message="{ item }">
          <div v-if="item.user_message" class="text-body-2 text-truncate" style="max-width: 140px" :title="item.user_message">
            {{ item.user_message }}
          </div>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template v-slot:item.agent_response="{ item }">
          <div v-if="item.agent_response" class="text-body-2 text-truncate" style="max-width: 140px" :title="item.agent_response">
            {{ item.agent_response }}
          </div>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        
        <template v-slot:item.status="{ item }">
          <v-chip :color="getStatusColor(item.status)" size="small" variant="tonal">
            <v-icon start size="12">{{ getStatusIcon(item.status) }}</v-icon>
            {{ item.status.toUpperCase() }}
          </v-chip>
        </template>
        
        <template v-slot:item.duration_ms="{ item }">
          <span v-if="item.duration_ms" class="text-body-2">
            <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
            {{ item.duration_ms }} ms
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        
        <template v-slot:item.actions="{ item }">
          <div class="d-flex ga-1 justify-center">
            <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-eye" @click="openJobDetails(item)">
              Ver
            </v-btn>
            <v-btn
              v-if="getSessionId(item)"
              icon
              variant="text"
              size="small"
              color="info"
              @click="viewStmFromJob(item)"
            >
              <v-icon size="18">mdi-message-text-clock-outline</v-icon>
              <v-tooltip activator="parent" location="top">Ver STM (Conversa)</v-tooltip>
            </v-btn>
            <v-btn
              v-if="getSessionId(item)"
              icon
              variant="text"
              size="small"
              color="warning"
              @click="viewMtmFromJob(item)"
            >
              <v-icon size="18">mdi-database-clock-outline</v-icon>
              <v-tooltip activator="parent" location="top">Ver MTM (Histórico)</v-tooltip>
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Job Details Dialog -->
    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card v-if="selectedJob">
        <v-card-title class="bg-primary text-white d-flex align-center px-6 py-4">
          <v-icon class="mr-2" color="white">mdi-identifier</v-icon>
          <span class="text-body-1 font-weight-bold">Job: {{ selectedJob.job_id }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" color="white"></v-btn>
        </v-card-title>
        
        <v-card-text class="pa-6" style="max-height: 60vh; overflow-y:auto;">
          <v-row class="mb-4">
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Path do Webhook</div>
              <v-chip variant="outlined" color="info" size="small">{{ selectedJob.webhook_path }}</v-chip>
            </v-col>
            <v-col cols="12" sm="3">
              <div class="text-caption text-medium-emphasis mb-1">Status</div>
              <v-chip :color="getStatusColor(selectedJob.status)" size="small" variant="tonal">
                {{ selectedJob.status.toUpperCase() }}
              </v-chip>
            </v-col>
            <v-col cols="12" sm="3">
              <div class="text-caption text-medium-emphasis mb-1">Duração</div>
              <span class="font-weight-medium">{{ selectedJob.duration_ms ? selectedJob.duration_ms + ' ms' : '—' }}</span>
            </v-col>
          </v-row>

          <v-divider class="mb-4"></v-divider>

          <!-- Request -->
          <div class="d-flex align-center justify-space-between mb-2">
            <h3 class="text-subtitle-2 font-weight-bold text-primary">Payload de Entrada (Request)</h3>
            <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.request_data)"></v-btn>
          </div>
          <v-sheet class="pa-4 rounded-lg overflow-auto code-sheet mb-4" max-height="250">
            <pre class="text-caption">{{ formatJSON(selectedJob.request_data) }}</pre>
          </v-sheet>

          <!-- Response -->
          <div class="d-flex align-center justify-space-between mb-2">
            <h3 class="text-subtitle-2 font-weight-bold" :class="selectedJob.status === 'failed' ? 'text-error' : 'text-success'">Payload de Saída (Response)</h3>
            <v-btn v-if="selectedJob.response_data || selectedJob.error_message" size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(selectedJob.response_data || selectedJob.error_message)"></v-btn>
          </div>
          <v-sheet v-if="selectedJob.response_data" class="pa-4 rounded-lg overflow-auto code-sheet" max-height="250">
            <pre class="text-caption">{{ formatJSON(selectedJob.response_data) }}</pre>
          </v-sheet>
          <v-alert v-else-if="selectedJob.error_message" type="error" variant="tonal" class="rounded-lg">
            <pre style="white-space: pre-wrap; font-family: monospace;" class="text-caption">{{ selectedJob.error_message }}</pre>
          </v-alert>
          <div v-else class="text-medium-emphasis font-italic text-body-2">Sem resposta gerada.</div>

          <!-- Test Result (Internal Mode) -->
          <div v-if="testResult" class="mt-6">
            <v-divider class="mb-4"></v-divider>
            <div class="d-flex align-center justify-space-between mb-2">
              <h3 class="text-subtitle-2 font-weight-bold text-info">
                <v-icon size="small" class="mr-1">mdi-flask</v-icon>
                Resultado do Teste (Interno)
              </h3>
              <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(testResult)"></v-btn>
            </div>
            <v-sheet class="pa-4 rounded-lg overflow-auto code-sheet" max-height="300" style="border: 1px solid rgba(0, 209, 255, 0.3);">
              <pre class="text-caption" style="color: #00D1FF;">{{ formatJSON(testResult) }}</pre>
            </v-sheet>
          </div>

          <!-- Redo Result -->
          <div v-if="redoResult" class="mt-6">
            <v-divider class="mb-4"></v-divider>
            <div class="d-flex align-center justify-space-between mb-2">
              <h3 class="text-subtitle-2 font-weight-bold" style="color: #FF9800;">
                <v-icon size="small" class="mr-1" color="orange">mdi-refresh-circle</v-icon>
                Resultado do Refazer (Novo Job: {{ redoNewJobId }})
              </h3>
              <div class="d-flex ga-1">
                <v-btn size="x-small" variant="text" icon="mdi-content-copy" @click="copyToClipboard(redoResult)"></v-btn>
                <v-btn
                  v-if="redoCallbackUrl"
                  size="small"
                  color="success"
                  variant="tonal"
                  prepend-icon="mdi-send-variant"
                  :loading="resendingRedo"
                  @click="resendRedoResult"
                >
                  Enviar Resultado
                </v-btn>
              </div>
            </div>
            <v-sheet class="pa-4 rounded-lg overflow-auto code-sheet" max-height="300" style="border: 1px solid rgba(255, 152, 0, 0.3);">
              <pre class="text-caption" style="color: #FF9800;">{{ formatJSON(redoResult) }}</pre>
            </v-sheet>
          </div>
          <!-- Human Response Input -->
          <div v-if="showHumanInput" class="mt-4">
            <v-divider class="mb-4"></v-divider>
            <h3 class="text-subtitle-2 font-weight-bold text-warning mb-2">
              <v-icon size="small" class="mr-1">mdi-account-voice</v-icon>
              Human Response
            </h3>
            <v-textarea
              v-model="humanText"
              variant="outlined"
              placeholder="Digite a mensagem que será enviada como resposta..."
              rows="3"
              auto-grow
              hide-details
            ></v-textarea>
            <div class="d-flex justify-end mt-2 gap-2">
              <v-btn size="small" variant="text" @click="showHumanInput = false; humanText = ''">Cancelar</v-btn>
              <v-btn
                size="small"
                color="warning"
                variant="flat"
                prepend-icon="mdi-send"
                :loading="sendingHuman"
                :disabled="!humanText.trim()"
                @click="sendHumanResponse"
              >
                Enviar Resposta
              </v-btn>
            </div>
          </div>
        </v-card-text>
        
        <v-card-actions class="pa-4 border-t d-flex flex-wrap gap-2">
          <v-btn
            color="orange"
            variant="tonal"
            prepend-icon="mdi-refresh-circle"
            :loading="redoingJob"
            @click="redoCurrentJob"
          >
            Refazer
          </v-btn>
          <v-btn
            color="info"
            variant="tonal"
            prepend-icon="mdi-flask"
            :loading="testingJob"
            @click="testCurrentJob"
          >
            Testar Job
          </v-btn>
          <v-btn
            v-if="selectedJob.callback_url && selectedJob.response_data"
            color="success"
            variant="tonal"
            prepend-icon="mdi-send-variant"
            :loading="resendingJob"
            @click="resendCurrentJob"
          >
            Reenviar
          </v-btn>
          <v-btn
            v-if="selectedJob.callback_url"
            color="warning"
            variant="tonal"
            prepend-icon="mdi-account-voice"
            @click="showHumanInput = !showHumanInput"
          >
            Human Response
          </v-btn>
          <!-- Agent Control Buttons -->
          <v-btn
            color="error"
            variant="tonal"
            prepend-icon="mdi-robot-off"
            :loading="pausingAgent"
            @click="pauseAgent(null)"
            size="small"
          >
            Desativar Agente
          </v-btn>
          <div class="d-flex align-center ga-1">
            <v-btn
              color="error"
              variant="tonal"
              prepend-icon="mdi-timer-off"
              :loading="pausingAgent"
              :disabled="!pauseMinutes"
              @click="pauseAgent(pauseMinutes)"
              size="small"
            >
              Desativar por
            </v-btn>
            <v-text-field
              v-model.number="pauseMinutes"
              type="number"
              density="compact"
              variant="outlined"
              hide-details
              style="max-width: 75px"
              placeholder="min"
            />
          </div>
          <v-btn
            color="success"
            variant="tonal"
            prepend-icon="mdi-robot"
            :loading="activatingAgent"
            @click="activateAgent"
            size="small"
          >
            Ativar Agente
          </v-btn>
          <v-btn
            v-if="getSessionId(selectedJob)"
            color="teal"
            variant="tonal"
            prepend-icon="mdi-account-check"
            :loading="unblockingBot"
            @click="unblockBot(getSessionId(selectedJob))"
            size="small"
          >
            Não é BOT
          </v-btn>
          <v-btn
            v-if="getSessionId(selectedJob)"
            color="error"
            variant="tonal"
            prepend-icon="mdi-robot-dead"
            :loading="blockingBot"
            @click="blockBot(getSessionId(selectedJob))"
            size="small"
          >
            É BOT
          </v-btn>
          <v-btn
            v-if="getSessionId(selectedJob)"
            color="deep-orange"
            variant="tonal"
            prepend-icon="mdi-lock-open-variant"
            :loading="unlockingSession"
            @click="unlockSession(getSessionId(selectedJob))"
            size="small"
          >
            Liberar Trava (Locks)
          </v-btn>
          <v-btn
            v-if="selectedJob.status === 'in_progress' || selectedJob.status === 'queued'"
            color="error"
            variant="flat"
            prepend-icon="mdi-stop-circle-outline"
            :loading="abortingJob"
            @click="abortCurrentJob"
          >
            Abortar Job
          </v-btn>
          <v-btn color="primary" variant="text" @click="dialog = false" :disabled="testingJob || abortingJob || resendingJob || sendingHuman || pausingAgent || activatingAgent">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- STM/MTM Messages Dialog -->
    <v-dialog v-model="memoryDialog" max-width="750" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important">
        <v-card-title class="d-flex align-center pa-5">
          <v-icon class="mr-2" size="20" :color="memoryDialogType === 'stm' ? '#00D1FF' : '#FBBF24'">
            {{ memoryDialogType === 'stm' ? 'mdi-message-text-clock-outline' : 'mdi-database-clock-outline' }}
          </v-icon>
          <span class="text-subtitle-1 font-weight-bold text-white">{{ memoryDialogTitle }}</span>
          <v-spacer />
          <v-btn icon variant="text" size="small" @click="memoryDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider style="border-color: rgba(255,255,255,0.05)"></v-divider>
        <v-card-text class="pa-5" style="max-height: 550px; overflow-y: auto;">
          <div v-if="memoryDialogLoading" class="d-flex justify-center py-12">
            <v-progress-circular indeterminate color="primary" size="32"></v-progress-circular>
          </div>
          <div v-else-if="memoryMessages.length > 0" class="d-flex flex-column ga-3">
            <div
              v-for="(msg, idx) in memoryMessages"
              :key="idx"
              class="memory-bubble pa-3 rounded-lg"
              :class="getMemoryBubbleClass(msg.role)"
            >
              <div class="d-flex align-center mb-1">
                <v-icon size="14" class="mr-1" :color="getMemoryIconColor(msg.role)">
                  {{ getMemoryIcon(msg.role) }}
                </v-icon>
                <span class="text-caption font-weight-bold text-uppercase" style="opacity: 0.7">{{ msg.role }}</span>
                <span v-if="msg.created_at || msg.timestamp" class="text-caption ml-2" style="opacity: 0.4">
                  {{ formatDate(msg.created_at || msg.timestamp) }}
                </span>
              </div>
              <div class="text-body-2 text-white" style="white-space: pre-wrap; word-break: break-word;">{{ msg.content }}</div>
            </div>
          </div>
          <div v-else class="text-center pa-8 text-medium-emphasis">
            Nenhuma mensagem encontrada para esta sessão.
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
      </v-window-item>
      </template>

      <v-window-item value="entradas">
        <!-- Ingress Data Table -->
        <v-card class="glass-card">
          <v-card-title class="d-flex align-center px-6 py-4">
            <v-icon class="mr-2" color="teal">mdi-login-variant</v-icon>
            <span class="text-white font-weight-medium">Logs de Entrada (Ingress)</span>
            <v-spacer></v-spacer>
            <v-btn color="teal" variant="tonal" prepend-icon="mdi-refresh" size="small" @click="fetchIngressLogs" :loading="ingressLoading">
              Atualizar
            </v-btn>
          </v-card-title>
          
          <v-divider></v-divider>

          <v-card-text class="px-6 py-4">
            <v-row dense>
              <v-col cols="12" sm="6" md="4">
                <v-text-field
                  v-model="ingressSearchPath"
                  prepend-inner-icon="mdi-magnify"
                  placeholder="Buscar Path (ex: meu-webhook)..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="4">
                <v-select
                  v-model="ingressStatusFilter"
                  :items="['forwarded', 'queued', 'stopped', 'validation_error', 'unauthorized', 'not_found', 'error']"
                  label="Status"
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                ></v-select>
              </v-col>
            </v-row>
          </v-card-text>

          <v-divider></v-divider>

          <v-data-table
            :headers="[
              { title: 'Data/Hora', key: 'created_at', width: '180px' },
              { title: 'Webhook Path', key: 'pipeline_path' },
              { title: 'URL Destino', key: 'destination_url' },
              { title: 'Código HTTP', key: 'response_code', align: 'center', width: '110px' },
              { title: 'Duração', key: 'duration_ms', align: 'center', width: '110px' },
              { title: 'Status', key: 'status', align: 'center', width: '140px' },
              { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '120px' }
            ]"
            :items="ingressLogs"
            :loading="ingressLoading"
            hover
            hide-default-footer
            class="bg-transparent"
          >
            <template v-slot:item.created_at="{ item }">
              <span class="text-body-2">{{ formatDate(item.created_at) }}</span>
            </template>

            <template v-slot:item.pipeline_path="{ item }">
              <v-chip variant="outlined" color="teal" size="small">
                /webhook/{{ item.pipeline_path }}
              </v-chip>
            </template>

            <template v-slot:item.destination_url="{ item }">
              <span class="text-caption text-truncate d-inline-block" style="max-width: 300px;" :title="item.destination_url">
                {{ item.destination_url || '—' }}
              </span>
            </template>

            <template v-slot:item.response_code="{ item }">
              <v-chip v-if="item.response_code" :color="item.response_code < 400 ? 'success' : 'error'" size="x-small" variant="tonal">
                {{ item.response_code }}
              </v-chip>
              <span v-else class="text-medium-emphasis">—</span>
            </template>

            <template v-slot:item.duration_ms="{ item }">
              <span v-if="item.duration_ms" class="text-body-2">
                <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
                {{ item.duration_ms }} ms
              </span>
              <span v-else class="text-medium-emphasis">—</span>
            </template>

            <template v-slot:item.status="{ item }">
              <v-chip :color="getIngressStatusColor(item.status)" size="small" variant="tonal">
                <v-icon start size="12">{{ getIngressStatusIcon(item.status) }}</v-icon>
                {{ item.status.toUpperCase() }}
              </v-chip>
            </template>

            <template v-slot:item.actions="{ item }">
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-eye" @click="openIngressLogDetails(item)">
                Ver
              </v-btn>
            </template>

            <template v-slot:bottom>
              <div class="d-flex align-center justify-end pa-4 border-t" style="gap: 16px;">
                <v-pagination
                  v-model="ingressPage"
                  :length="Math.ceil(ingressTotal / ingressItemsPerPage) || 1"
                  density="compact"
                  total-visible="5"
                  active-color="primary"
                ></v-pagination>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <v-window-item value="disparador">
        <v-row class="mb-6 mt-2">
          <v-col cols="12" sm="6" md="2">
            <v-card class="glass-card"><v-card-text><div class="text-overline">ATIVAS / PAUSADAS</div><div class="text-h4 text-primary">{{ dispStats.active_campaigns }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">AGUARDANDO NO MQ</div><div class="text-h4 text-warning">{{ dispStats.mq_pending || 0 }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-card class="glass-card"><v-card-text><div class="text-overline">ENVIADAS HOJE</div><div class="text-h4 text-success">{{ dispStats.total_sent }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" sm="6" md="2">
            <v-card class="glass-card"><v-card-text><div class="text-overline">COMPLETAS</div><div class="text-h4 text-info">{{ dispStats.completed_campaigns }}</div></v-card-text></v-card>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card"><v-card-text><div class="text-overline">FALHAS (DLQ)</div><div class="text-h4 text-error">{{ dispStats.total_failed }}</div></v-card-text></v-card>
          </v-col>
        </v-row>
        
        <div class="mb-6">
            <h3 class="text-subtitle-1 font-weight-bold mb-4 d-flex align-center">
               <v-icon color="warning" class="mr-2">mdi-clock-fast</v-icon>
               Fila de Espera (Smart Routing)
            </h3>
            <v-expansion-panels v-if="dispStaged && dispStaged.length > 0" variant="accordion" class="glass-panels">
              <v-expansion-panel
                v-for="staged in dispStaged"
                :key="staged.queue_id"
                class="glass-card mb-2"
                style="border: 1px solid rgba(255, 152, 0, 0.2);"
              >
                <v-expansion-panel-title>
                  <div class="d-flex align-center w-100 pr-4">
                    <v-icon class="mr-2" color="warning">mdi-church</v-icon>
                    <span class="font-weight-bold mr-4">Queue: {{ staged.queue_id }}</span>
                    <v-chip size="small" color="info" variant="flat" class="mr-4">{{ staged.total_contacts }} contatos</v-chip>
                    <v-spacer></v-spacer>
                    <div class="text-caption d-flex align-center">
                       <v-icon size="14" class="mr-1">mdi-timer-outline</v-icon>
                       Próximo disparo em: 
                       <span class="font-weight-bold ml-1 text-warning mr-4">
                          {{ staged.time_remaining_minutes }}m {{ staged.time_remaining_seconds }}s
                       </span>
                       <v-tooltip text="Disparar Agora" location="top">
                          <template v-slot:activator="{ props }">
                             <v-btn v-bind="props" icon="mdi-play-circle" color="success" variant="text" size="small" class="ml-2" @click.stop="dispatchStagedQueue(staged.queue_id)"></v-btn>
                          </template>
                       </v-tooltip>
                       <v-tooltip text="Excluir Fila" location="top">
                          <template v-slot:activator="{ props }">
                             <v-btn v-bind="props" icon="mdi-delete" color="error" variant="text" size="small" @click.stop="deleteStagedQueue(staged.queue_id)"></v-btn>
                          </template>
                       </v-tooltip>
                    </div>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text class="pa-0">
                  <v-list bg-color="transparent" density="compact" class="pa-0">
                    <div v-for="typeInfo in staged.type_ids" :key="typeInfo.type_id" class="border-b border-opacity-10 last:border-0 pa-2">
                       <div class="d-flex align-center mb-2 px-2">
                          <v-icon size="18" color="primary" class="mr-2">mdi-tag-outline</v-icon>
                          <span class="text-subtitle-2 font-weight-medium">Tipo: {{ typeInfo.type_id }}</span>
                          <v-chip size="x-small" variant="outlined" class="ml-2">{{ typeInfo.contact_count }} contatos</v-chip>
                       </div>
                       
                       <v-row dense class="px-2">
                         <v-col v-for="(contact, cIdx) in typeInfo.contacts" :key="cIdx" cols="12" sm="6" md="4" lg="3">
                           <v-sheet class="pa-2 rounded border border-opacity-10 d-flex align-center ga-2" color="rgba(255,255,255,0.03)">
                              <v-avatar size="24" color="primary" variant="tonal">
                                <span class="text-caption">{{ contact.name?.charAt(0) || '?' }}</span>
                              </v-avatar>
                              <div class="text-truncate">
                                <div class="text-caption font-weight-bold text-truncate">{{ contact.name }}</div>
                                <div class="text-tiny text-medium-emphasis">{{ contact.number }}</div>
                                <!-- Extra Fields -->
                                <div class="d-flex flex-wrap ga-1 mt-1">
                                   <template v-for="(val, key) in contact" :key="key">
                                      <v-chip v-if="!['name','number','phone'].includes(key)" size="x-small" variant="tonal" density="compact" style="font-size: 8px; height: 14px;">
                                         {{ key }}: {{ val }}
                                      </v-chip>
                                   </template>
                                </div>
                              </div>
                           </v-sheet>
                         </v-col>
                       </v-row>
                    </div>
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <div v-else class="text-medium-emphasis text-body-2 px-2 d-flex align-center ga-2 py-4 border rounded border-dashed border-opacity-20">
               <v-icon size="18">mdi-information-outline</v-icon>
               Nenhuma fila de contato aguardando no momento.
            </div>
        </div>

        <div class="d-flex align-center mb-4">
            <h3 class="text-subtitle-1 font-weight-bold">Campanhas em Execução</h3>
            <v-spacer></v-spacer>
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" size="small" @click="fetchDisparadorData" :loading="dispLoading">Atualizar</v-btn>
        </div>

        <v-card class="glass-card">
          <v-data-table :headers="dispHeaders" :items="dispCampaigns" :loading="dispLoading" hover>
            <template #item.queue_id="{ item }"><v-chip size="x-small" color="info" variant="tonal" class="font-weight-bold">{{ item.queue_id || '—' }}</v-chip></template>
            <template #item.type_id="{ item }"><v-chip size="x-small" color="primary" variant="outlined">{{ item.type_id || '—' }}</v-chip></template>
            <template #item.service_id="{ item }"><v-chip size="small" variant="flat" color="rgba(255,255,255,0.05)">{{ item.service_id }}</v-chip></template>
            <template #item.status="{ item }">
              <v-chip :color="item.status === 'running' ? 'success' : item.status === 'paused' ? 'warning' : 'info'" size="small">
                {{ item.status.toUpperCase() }}
              </v-chip>
            </template>
            <template #item.started_at="{ item }">
               <span class="text-caption text-medium-emphasis">{{ formatDate(item.started_at) }}</span>
            </template>
            <template #item.percent="{ item }">
              <div class="d-flex align-center w-100">
                <v-progress-linear :model-value="item.percent" color="primary" height="8" rounded></v-progress-linear>
                <span class="text-caption ml-2 min-w-[40px]">{{ item.percent }}%</span>
              </div>
            </template>
            <template #item.actions="{ item }">
               <v-btn size="small" variant="text" icon="mdi-magnify" color="primary" @click="openDispDetails(item)"></v-btn>
            </template>
      </v-data-table>
        </v-card>
        
        <v-dialog v-model="dispDialog" max-width="700">
          <v-card v-if="dispSelected" class="glass-card">
             <v-card-title class="pa-6 border-b">
                Campanha: {{ dispSelected.service_id }}
                <v-chip size="small" class="ml-2" :color="dispSelected.status === 'running' ? 'success' : dispSelected.status === 'paused' ? 'warning' : 'info'">{{ dispSelected.status.toUpperCase() }}</v-chip>
             </v-card-title>
             <v-card-text class="pa-6" style="max-height: 60vh; overflow-y:auto;">
                <v-row>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Total</div><div class="text-h6">{{ dispSelected.total }}</div></v-col>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Enviados</div><div class="text-h6 text-success">{{ dispSelected.sent }}</div></v-col>
                  <v-col cols="4"><div class="text-caption text-medium-emphasis">Falhas</div><div class="text-h6 text-error">{{ dispSelected.failed }}</div></v-col>
                </v-row>
                <div class="my-6">
                    <div class="text-caption mb-1">Progresso ({{ dispSelected.percent }}%)</div>
                    <v-progress-linear :model-value="dispSelected.percent" color="primary" height="12" rounded></v-progress-linear>
                </div>
                <div v-if="dispReport">
                    <v-divider class="mb-4"></v-divider>
                    <div class="d-flex flex-wrap ga-2 mb-4">
                      <v-chip variant="outlined" color="success" size="small">Taxa Sucesso: {{ dispReport.success_rate }}%</v-chip>
                      <v-chip variant="outlined" color="error" size="small">DLQ: {{ dispReport.dlq_count }} contatos</v-chip>
                    </div>

                    <h4 class="text-subtitle-2 mb-2 d-flex align-center">
                       <v-icon size="18" class="mr-2">mdi-account-details</v-icon>
                       Status por Contato
                    </h4>
                    <v-table density="compact" class="glass-card border rounded mb-6" style="max-height: 350px; overflow-y: auto;">
                       <thead>
                          <tr>
                             <th class="text-left py-2">Nome / Info</th>
                             <th class="text-left py-2">Status</th>
                             <th class="text-left py-2">Horário</th>
                             <th class="text-left py-2">Erro</th>
                             <th class="text-center py-2">Ações</th>
                          </tr>
                       </thead>
                       <tbody>
                          <tr v-for="c in dispReport.contacts" :key="c.number || c.user_id" class="hover:bg-white/5">
                             <td class="text-caption py-2">
                                <div class="font-weight-bold">{{ c.name }}</div>
                                <div class="text-tiny text-medium-emphasis">{{ c.number }}</div>
                                <!-- Extra Data -->
                                <div class="d-flex flex-wrap ga-1 mt-1">
                                   <template v-for="(val, key) in c" :key="key">
                                      <v-chip v-if="!['name','number','status','updated_at','error','phone'].includes(key)" size="x-small" variant="tonal" density="compact" style="font-size: 8px; height: 14px;">
                                         {{ key }}: {{ val }}
                                      </v-chip>
                                   </template>
                                </div>
                             </td>
                             <td>
                                <v-chip size="x-small" :color="c.status === 'sent' ? 'success' : c.status === 'failed' ? 'error' : 'warning'" variant="flat">
                                   {{ c.status.toUpperCase() }}
                                </v-chip>
                             </td>
                             <td class="text-tiny text-medium-emphasis">{{ formatDate(c.updated_at) }}</td>
                             <td class="text-tiny text-error text-truncate" style="max-width: 120px;">{{ c.error || '—' }}</td>
                             <td class="text-center">
                                <v-btn
                                   size="x-small"
                                   variant="tonal"
                                   color="orange"
                                   prepend-icon="mdi-send-clock"
                                   :loading="redispatchingContact === (c.number || c.user_id)"
                                   @click="redispatchContact(c)"
                                >
                                   Redisparar
                                </v-btn>
                             </td>
                          </tr>
                       </tbody>
                    </v-table>

                    <!-- Seção de Debug de Payloads -->
                    <div v-if="dispReport.debug" class="mt-6">
                       <h4 class="text-subtitle-2 mb-3 d-flex align-center">
                          <v-icon size="18" class="mr-2" color="primary">mdi-code-json</v-icon>
                          Dados Técnicos (Payload Debugger)
                       </h4>
                       <v-expansion-panels variant="accordion" class="glass-card border rounded">
                          <v-expansion-panel v-if="dispReport.debug.input" bg-color="transparent">
                             <v-expansion-panel-title class="text-caption font-weight-bold">
                                Payload de Entrada (Input Sample)
                             </v-expansion-panel-title>
                             <v-expansion-panel-text>
                                <v-sheet class="pa-2 rounded code-sheet" style="font-size: 10px;">
                                   <pre>{{ formatJSON(dispReport.debug.input) }}</pre>
                                </v-sheet>
                             </v-expansion-panel-text>
                          </v-expansion-panel>

                          <v-expansion-panel v-if="dispReport.debug.output" bg-color="transparent">
                             <v-expansion-panel-title class="text-caption font-weight-bold">
                                Payload de Saída (Output Sample - Agente)
                             </v-expansion-panel-title>
                             <v-expansion-panel-text>
                                <v-sheet class="pa-2 rounded code-sheet" style="font-size: 10px;">
                                   <pre>{{ formatJSON(dispReport.debug.output) }}</pre>
                                </v-sheet>
                             </v-expansion-panel-text>
                          </v-expansion-panel>
                       </v-expansion-panels>
                    </div>
                </div>
             </v-card-text>
             <v-card-actions class="pa-4 border-t">
                <v-btn v-if="dispSelected.status === 'running'" color="warning" prepend-icon="mdi-pause" variant="flat" @click="dispAction('pause')" :loading="dispActionLoading">Pausar</v-btn>
                <v-btn color="success" prepend-icon="mdi-play" variant="flat" @click="dispAction('resume')" :loading="dispActionLoading">Ativar / Retomar</v-btn>
                <v-btn v-if="dispReport && dispReport.dlq_count > 0" color="error" prepend-icon="mdi-refresh" variant="flat" @click="dispAction('retry-dlq')" :loading="dispActionLoading">Reprocessar DLQ</v-btn>
                <v-btn color="info" prepend-icon="mdi-cached" variant="flat" @click="dispAction('recreate')" :loading="dispActionLoading">Recriar</v-btn>
                <v-btn color="error" prepend-icon="mdi-delete" variant="flat" @click="dispAction('delete')" :loading="dispActionLoading">Excluir</v-btn>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="dispDialog = false">Fechar</v-btn>
             </v-card-actions>
          </v-card>
         </v-dialog>
      </v-window-item>

      <v-window-item value="gatilhos-disparador">
        <v-card class="glass-card">
          <v-card-title class="d-flex align-center px-6 py-4">
            <v-icon class="mr-2" color="primary">mdi-webhook</v-icon>
            <span class="text-white font-weight-medium">Gatilhos do Disparador (Webhooks Recebidos)</span>
            <v-spacer></v-spacer>
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" size="small" @click="fetchGatilhos" :loading="gatilhosLoading">
              Atualizar
            </v-btn>
          </v-card-title>
          
          <v-divider></v-divider>

          <v-card-text class="px-6 py-4">
            <v-row dense>
              <v-col cols="12" sm="6" md="4">
                <v-text-field
                  v-model="gatilhosSearchPath"
                  prepend-inner-icon="mdi-magnify"
                  placeholder="Buscar Path (ex: minha-campanha)..."
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                  @keyup.enter="fetchGatilhos"
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="4">
                <v-select
                  v-model="gatilhosStatusFilter"
                  :items="[
                    { title: 'Todos', value: null },
                    { title: 'Sucesso', value: 'success' },
                    { title: 'Pendente', value: 'pending' },
                    { title: 'Erro', value: 'failed' },
                    { title: 'Erro de Validação', value: 'validation_error' },
                    { title: 'Não Autorizado', value: 'unauthorized' }
                  ]"
                  item-title="title"
                  item-value="value"
                  label="Status"
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                  @update:model-value="fetchGatilhos"
                ></v-select>
              </v-col>
            </v-row>
          </v-card-text>

          <v-divider></v-divider>

          <v-data-table
            :headers="[
              { title: 'Data/Hora', key: 'created_at', width: '180px' },
              { title: 'Webhook Path', key: 'webhook_path' },
              { title: 'Contatos', key: 'contact_count', align: 'center', width: '110px' },
              { title: 'Código HTTP', key: 'status_code', align: 'center', width: '120px' },
              { title: 'Duração', key: 'duration_ms', align: 'center', width: '110px' },
              { title: 'Status', key: 'status', align: 'center', width: '150px' },
              { title: 'Ações', key: 'actions', sortable: false, align: 'center', width: '120px' }
            ]"
            :items="gatilhosLogs"
            :loading="gatilhosLoading"
            hover
            hide-default-footer
            class="bg-transparent"
          >
            <template v-slot:item.created_at="{ item }">
              <span class="text-body-2">{{ formatDate(item.created_at) }}</span>
            </template>

            <template v-slot:item.webhook_path="{ item }">
              <v-chip variant="outlined" color="primary" size="small">
                /webhook/{{ item.webhook_path }}
              </v-chip>
            </template>

            <template v-slot:item.contact_count="{ item }">
              <v-chip size="x-small" color="info" variant="flat">
                {{ item.contact_count }}
              </v-chip>
            </template>

            <template v-slot:item.status_code="{ item }">
              <v-chip v-if="item.status_code" :color="item.status_code < 400 ? 'success' : 'error'" size="x-small" variant="tonal">
                {{ item.status_code }}
              </v-chip>
              <span v-else class="text-medium-emphasis">—</span>
            </template>

            <template v-slot:item.duration_ms="{ item }">
              <span v-if="item.duration_ms" class="text-body-2">
                <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
                {{ item.duration_ms }} ms
              </span>
              <span v-else class="text-medium-emphasis">—</span>
            </template>

            <template v-slot:item.status="{ item }">
              <v-chip :color="getGatilhoStatusColor(item.status)" size="small" variant="tonal">
                <v-icon start size="12">{{ getGatilhoStatusIcon(item.status) }}</v-icon>
                {{ getGatilhoStatusLabel(item.status) }}
              </v-chip>
            </template>

            <template v-slot:item.actions="{ item }">
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-eye" @click="openGatilhoDetails(item)">
                Ver
              </v-btn>
            </template>

            <template v-slot:bottom>
              <div class="d-flex align-center justify-end pa-4 border-t" style="gap: 16px;">
                <v-pagination
                  v-model="gatilhosPage"
                  :length="Math.ceil(gatilhosTotal / gatilhosItemsPerPage) || 1"
                  density="compact"
                  total-visible="5"
                  active-color="primary"
                ></v-pagination>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <v-window-item value="automacao">
        <!-- Selector and Action Bar -->
        <v-card class="glass-card mb-6">
          <v-card-text class="d-flex align-center py-4" style="gap: 16px;">
            <v-icon color="primary" class="mr-2" size="28">mdi-robot-industrial</v-icon>
            <div style="flex-grow: 1; max-width: 400px;">
              <v-select
                v-model="selectedWorkflowId"
                :items="workflowsList"
                item-title="name"
                item-value="id"
                label="Selecione o Workflow / Automação"
                variant="outlined"
                density="compact"
                hide-details
              ></v-select>
            </div>
            <v-spacer></v-spacer>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-refresh"
              @click="fetchWorkflowExecutions"
              :loading="wfLoading"
            >
              Atualizar Logs
            </v-btn>
          </v-card-text>
        </v-card>

        <!-- Stats row -->
        <v-row class="mb-6" v-if="selectedWorkflowId">
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card">
              <v-card-text>
                <div class="text-overline">TOTAL DE RUNS</div>
                <div class="text-h4 text-primary">{{ workflowExecutionsTotal }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card">
              <v-card-text>
                <div class="text-overline text-success">SUCESSOS</div>
                <div class="text-h4 text-success">{{ wfStats.completed }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card">
              <v-card-text>
                <div class="text-overline text-error">FALHAS</div>
                <div class="text-h4 text-error">{{ wfStats.failed }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-card class="glass-card">
              <v-card-text>
                <div class="text-overline text-info">LATÊNCIA MÉDIA</div>
                <div class="text-h4 text-info">{{ wfStats.avgDuration }} ms</div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <!-- Executions Table -->
        <v-card class="glass-card" v-if="selectedWorkflowId">
          <v-card-title class="px-6 py-4">
            <v-icon class="mr-2" color="primary">mdi-history</v-icon>
            Histórico de Execuções
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text class="pa-0">
            <v-data-table
              :headers="[
                { title: 'ID do Run', key: 'id', align: 'start' },
                { title: 'Status', key: 'status', align: 'center' },
                { title: 'Gatilho', key: 'trigger_type', align: 'center' },
                { title: 'Duração', key: 'duration_ms', align: 'center' },
                { title: 'Data/Hora', key: 'created_at', align: 'center' },
                { title: 'Ações', key: 'actions', sortable: false, align: 'center' }
              ]"
              :items="workflowExecutions"
              :loading="wfLoading"
              hover
              hide-default-footer
              class="bg-transparent"
            >
              <template v-slot:item.id="{ item }">
                <div class="d-flex align-center" style="gap: 8px;">
                  <code class="text-caption" style="color: #00D1FF">{{ item.id.substring(0, 8) }}...</code>
                  <v-btn icon variant="text" size="x-small" @click="copyToClipboard(item.id)">
                    <v-icon size="14">mdi-content-copy</v-icon>
                  </v-btn>
                </div>
              </template>

              <template v-slot:item.status="{ item }">
                <v-chip :color="getWfStatusColor(item.status)" size="small" variant="tonal">
                  <v-icon start size="12">{{ getWfStatusIcon(item.status) }}</v-icon>
                  {{ item.status.toUpperCase() }}
                </v-chip>
              </template>

              <template v-slot:item.trigger_type="{ item }">
                <v-chip size="small" variant="outlined" color="primary">
                  {{ item.trigger_type || 'manual' }}
                </v-chip>
              </template>

              <template v-slot:item.duration_ms="{ item }">
                <span v-if="item.duration_ms" class="text-body-2 font-weight-medium">
                  <v-icon size="14" class="mr-1">mdi-timer-outline</v-icon>
                  {{ item.duration_ms }} ms
                </span>
                <span v-else class="text-medium-emphasis">—</span>
              </template>

              <template v-slot:item.created_at="{ item }">
                <span class="text-body-2">{{ formatDate(item.created_at) }}</span>
              </template>

              <template v-slot:item.actions="{ item }">
                <div class="d-flex ga-1 justify-center align-center">
                  <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-magnify" @click="openWfExecutionDetails(item)">
                    Investigar
                  </v-btn>
                  <v-btn
                    v-if="item.status === 'running' || item.status === 'pending' || item.status === 'paused'"
                    color="error"
                    variant="tonal"
                    size="small"
                    prepend-icon="mdi-stop-circle-outline"
                    :loading="cancellingWfId === item.id"
                    @click="cancelWfExecution(item.id)"
                  >
                    Parar
                  </v-btn>
                </div>
              </template>

              <template v-slot:bottom>
                <div class="d-flex align-center justify-end pa-4 border-t" style="gap: 16px;">
                  <v-pagination
                    v-model="workflowPage"
                    :length="Math.ceil(workflowExecutionsTotal / workflowItemsPerPage) || 1"
                    density="compact"
                    total-visible="5"
                    active-color="primary"
                  ></v-pagination>
                </div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>

        <div v-else class="text-center py-12 text-medium-emphasis border rounded border-dashed border-opacity-20 mt-6">
          <v-icon size="48" class="mb-4">mdi-robot-vacuum</v-icon>
          <div class="text-body-1">Selecione uma automação acima para acompanhar seus logs de execução.</div>
        </div>
      </v-window-item>
    </v-window>

    <!-- Dialog de Detalhes da Execução da Automação -->
    <v-dialog v-model="wfDrawer" max-width="950" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important" v-if="selectedWfExecution">
        <v-card-title class="d-flex align-center pa-5 border-b">
          <v-icon class="mr-2" size="24" :color="getWfStatusColor(selectedWfExecution.status)">
            {{ getWfStatusIcon(selectedWfExecution.status) }}
          </v-icon>
          <div>
            <span class="text-subtitle-1 font-weight-bold text-white">Execução: {{ selectedWfExecution.id.substring(0, 8) }}</span>
            <div class="text-caption text-medium-emphasis mt-n1">
              Iniciado em {{ formatDate(selectedWfExecution.created_at) }} • Duração: {{ selectedWfExecution.duration_ms || 0 }} ms
            </div>
          </div>
          <v-spacer />
          <v-chip :color="getWfStatusColor(selectedWfExecution.status)" size="small" class="mr-3" variant="flat">
            {{ selectedWfExecution.status.toUpperCase() }}
          </v-chip>
          <v-btn icon variant="text" size="small" @click="wfDrawer = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-tabs v-model="wfDetailTab" color="primary" class="border-b">
          <v-tab value="timeline">Linha do Tempo</v-tab>
          <v-tab value="payloads">Entrada e Saída</v-tab>
          <v-tab value="context">Contexto Completo</v-tab>
        </v-tabs>

        <v-card-text class="pa-5" style="max-height: 650px; overflow-y: auto;">
          <!-- ── TAB: TIMELINE ── -->
          <div v-if="wfDetailTab === 'timeline'">
            <!-- Alerta se falhar -->
            <v-alert
              v-if="selectedWfExecution.status === 'failed' && selectedWfExecution.error_message"
              type="error"
              variant="tonal"
              title="Execução Falhou com Erro Crítico"
              class="mb-6 text-caption"
            >
              <pre class="mt-2 text-tiny" style="white-space: pre-wrap; font-family: monospace;">{{ selectedWfExecution.error_message }}</pre>
            </v-alert>

            <!-- Timeline Steps -->
            <v-timeline density="compact" align="start" class="w-100 px-2">
              <v-timeline-item
                v-for="step in selectedWfExecution.blocks_executed"
                :key="step.block_id"
                :dot-color="step.status === 'success' ? 'success' : 'error'"
                :icon="step.status === 'success' ? 'mdi-check' : 'mdi-alert'"
                size="small"
                class="mb-4"
              >
                <div class="d-flex flex-column ga-1 w-100">
                  <div class="d-flex align-center justify-space-between w-100">
                    <div class="d-flex align-center" style="gap: 8px;">
                      <span class="text-subtitle-2 font-weight-bold text-white">{{ step.label || step.block_id }}</span>
                      <v-chip size="x-small" variant="tonal" color="primary">{{ step.block_type }}</v-chip>
                    </div>
                    <span class="text-caption text-medium-emphasis">
                      <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
                      {{ step.duration_ms || 0 }} ms
                    </span>
                  </div>

                  <div class="text-caption text-medium-emphasis" v-if="step.output_key">
                    Output Key: <code style="color: #00D1FF">{{ step.output_key }}</code>
                  </div>

                  <!-- Step Error message -->
                  <v-alert
                    v-if="step.error"
                    type="error"
                    variant="tonal"
                    density="compact"
                    class="mt-2 text-tiny"
                  >
                    {{ step.error }}
                  </v-alert>
                </div>
              </v-timeline-item>
            </v-timeline>
          </div>

          <!-- ── TAB: PAYLOADS ── -->
          <div v-else-if="wfDetailTab === 'payloads'">
            <h4 class="text-subtitle-2 font-weight-bold text-white mb-2">Gatilho de Entrada (trigger_data)</h4>
            <v-sheet rounded class="code-sheet pa-4 mb-6">
              <div class="d-flex justify-space-between mb-2">
                <span class="text-caption text-medium-emphasis">JSON Cru</span>
                <v-btn size="x-small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedWfExecution.trigger_data)">Copiar</v-btn>
              </div>
              <pre>{{ formatJSON(selectedWfExecution.trigger_data) }}</pre>
            </v-sheet>

            <h4 class="text-subtitle-2 font-weight-bold text-white mb-2">Resultado Final (result)</h4>
            <v-sheet rounded class="code-sheet pa-4">
              <div class="d-flex justify-space-between mb-2">
                <span class="text-caption text-medium-emphasis">Retorno Final da Automação</span>
                <v-btn size="x-small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedWfExecution.result)">Copiar</v-btn>
              </div>
              <pre v-if="typeof selectedWfExecution.result === 'object'">{{ formatJSON(selectedWfExecution.result) }}</pre>
              <pre v-else>{{ selectedWfExecution.result || 'Sem resultado retornado' }}</pre>
            </v-sheet>
          </div>

          <!-- ── TAB: CONTEXT ── -->
          <div v-else-if="wfDetailTab === 'context'">
            <div class="d-flex justify-space-between align-center mb-4">
              <h4 class="text-subtitle-2 font-weight-bold text-white">Estado das Variáveis Acumuladas (context)</h4>
              <v-btn size="x-small" color="primary" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedWfExecution.context)">Copiar Tudo</v-btn>
            </div>
            <v-sheet rounded class="code-sheet pa-4">
              <pre>{{ formatJSON(selectedWfExecution.context) }}</pre>
            </v-sheet>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 border-t">
          <v-btn
            v-if="selectedWfExecution.status === 'running' || selectedWfExecution.status === 'pending' || selectedWfExecution.status === 'paused'"
            color="error"
            variant="flat"
            prepend-icon="mdi-stop-circle-outline"
            :loading="cancellingWf"
            @click="cancelWfExecution(selectedWfExecution.id)"
          >
            Parar Execução
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="wfDrawer = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Dialog de Detalhes do Log do Ingress -->
    <v-dialog v-model="ingressDialog" max-width="950" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important" v-if="selectedIngressLog">
        <v-card-title class="d-flex align-center pa-5 border-b">
          <v-icon class="mr-2" size="24" :color="getIngressStatusColor(selectedIngressLog.status)">
            {{ getIngressStatusIcon(selectedIngressLog.status) }}
          </v-icon>
          <div>
            <span class="text-subtitle-1 font-weight-bold text-white">Log do Ingress: {{ selectedIngressLog.id.substring(0, 8) }}</span>
            <div class="text-caption text-medium-emphasis mt-n1">
              Recebido em {{ formatDate(selectedIngressLog.created_at) }} • Duração: {{ selectedIngressLog.duration_ms || 0 }} ms
            </div>
          </div>
          <v-spacer />
          <v-chip :color="getIngressStatusColor(selectedIngressLog.status)" size="small" class="mr-3" variant="flat">
            {{ selectedIngressLog.status.toUpperCase() }}
          </v-chip>
          <v-btn icon variant="text" size="small" @click="ingressDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-tabs v-model="ingressDetailTab" color="primary" class="border-b">
          <v-tab value="general">Geral / Resposta</v-tab>
          <v-tab value="raw">Payload Recebido (Bruto)</v-tab>
          <v-tab value="output">Payload Enviado (Tratado)</v-tab>
        </v-tabs>

        <v-card-text class="pa-5" style="max-height: 650px; overflow-y: auto;">
          <!-- TAB: GERAL -->
          <div v-if="ingressDetailTab === 'general'">
            <v-row>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis mb-1">Path do Pipeline</div>
                <div class="text-body-2 font-weight-bold text-white">/webhook/{{ selectedIngressLog.pipeline_path }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis mb-1">URL de Destino</div>
                <div class="text-body-2 font-weight-bold text-white">{{ selectedIngressLog.destination_url || '—' }}</div>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <v-row>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis mb-1">Código de Resposta HTTP</div>
                <v-chip v-if="selectedIngressLog.response_code" :color="selectedIngressLog.response_code < 400 ? 'success' : 'error'" size="small">
                  {{ selectedIngressLog.response_code }}
                </v-chip>
                <div v-else class="text-body-2 text-medium-emphasis">—</div>
              </v-col>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis mb-1">Status Final</div>
                <v-chip :color="getIngressStatusColor(selectedIngressLog.status)" size="small" variant="flat">
                  {{ selectedIngressLog.status.toUpperCase() }}
                </v-chip>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Error message if any -->
            <div v-if="selectedIngressLog.error_message" class="mb-4">
              <h4 class="text-subtitle-2 font-weight-bold text-error mb-2">Mensagem de Erro</h4>
              <v-alert type="error" variant="tonal" class="text-caption">
                <pre style="white-space: pre-wrap; font-family: monospace;">{{ selectedIngressLog.error_message }}</pre>
              </v-alert>
            </div>

            <!-- Destination Response Body if any -->
            <div>
              <h4 class="text-subtitle-2 font-weight-bold text-white mb-2">Corpo da Resposta do Destino</h4>
              <v-sheet rounded class="code-sheet pa-4" v-if="selectedIngressLog.response_body">
                <pre>{{ selectedIngressLog.response_body }}</pre>
              </v-sheet>
              <div v-else class="text-medium-emphasis font-italic text-body-2">Nenhuma resposta do destino gravada.</div>
            </div>
          </div>

          <!-- TAB: RAW PAYLOAD -->
          <div v-else-if="ingressDetailTab === 'raw'">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-caption text-medium-emphasis">Exibindo payload recebido cru da origem externa</span>
              <v-btn size="x-small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedIngressLog.raw_payload)">
                Copiar Payload
              </v-btn>
            </div>
            <v-sheet rounded class="code-sheet pa-4">
              <pre>{{ formatJSON(selectedIngressLog.raw_payload) }}</pre>
            </v-sheet>
          </div>

          <!-- TAB: OUTPUT PAYLOAD -->
          <div v-else-if="ingressDetailTab === 'output'">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-caption text-medium-emphasis">Exibindo payload pós-tratamento/automação enviado ao destino</span>
              <v-btn size="x-small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedIngressLog.output_payload)">
                Copiar Payload
              </v-btn>
            </div>
            <v-sheet rounded class="code-sheet pa-4" v-if="selectedIngressLog.output_payload">
              <pre>{{ formatJSON(selectedIngressLog.output_payload) }}</pre>
            </v-sheet>
            <div v-else class="text-medium-emphasis font-italic text-body-2">Nenhum payload de saída gerado (ex: falha na validação inicial).</div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 border-t">
          <v-spacer />
          <v-btn variant="text" @click="ingressDialog = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Dialog de Detalhes do Gatilho do Disparador -->
    <v-dialog v-model="gatilhosDialog" max-width="950" scrollable>
      <v-card class="glass-card" style="background: #0D1117 !important" v-if="selectedGatilhoLog">
        <v-card-title class="d-flex align-center pa-5 border-b">
          <v-icon class="mr-2" size="24" :color="getGatilhoStatusColor(selectedGatilhoLog.status)">
            {{ getGatilhoStatusIcon(selectedGatilhoLog.status) }}
          </v-icon>
          <div>
            <span class="text-subtitle-1 font-weight-bold text-white">Log do Gatilho: {{ selectedGatilhoLog.id.substring(0, 8) }}</span>
            <div class="text-caption text-medium-emphasis mt-n1">
              Recebido em {{ formatDate(selectedGatilhoLog.created_at) }} • Duração: {{ selectedGatilhoLog.duration_ms || 0 }} ms
            </div>
          </div>
          <v-spacer />
          <v-chip :color="getGatilhoStatusColor(selectedGatilhoLog.status)" size="small" class="mr-3" variant="flat">
            {{ getGatilhoStatusLabel(selectedGatilhoLog.status) }}
          </v-chip>
          <v-btn icon variant="text" size="small" @click="gatilhosDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-tabs v-model="gatilhoDetailTab" color="primary" class="border-b">
          <v-tab value="general">Geral / Resposta</v-tab>
          <v-tab value="raw">Payload Recebido (Request)</v-tab>
        </v-tabs>

        <v-card-text class="pa-5" style="max-height: 650px; overflow-y: auto;">
          <!-- TAB: GERAL -->
          <div v-if="gatilhoDetailTab === 'general'">
            <v-row>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis mb-1">Path do Webhook</div>
                <div class="text-body-2 font-weight-bold text-white">/webhook/{{ selectedGatilhoLog.webhook_path }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis mb-1">Quantidade de Contatos</div>
                <div class="text-body-2 font-weight-bold text-white">{{ selectedGatilhoLog.contact_count }} contatos</div>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <v-row>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis mb-1">Código de Resposta HTTP</div>
                <v-chip v-if="selectedGatilhoLog.status_code" :color="selectedGatilhoLog.status_code < 400 ? 'success' : 'error'" size="small">
                  {{ selectedGatilhoLog.status_code }}
                </v-chip>
                <div v-else class="text-body-2 text-medium-emphasis">—</div>
              </v-col>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis mb-1">Status Final</div>
                <v-chip :color="getGatilhoStatusColor(selectedGatilhoLog.status)" size="small" variant="flat">
                  {{ getGatilhoStatusLabel(selectedGatilhoLog.status) }}
                </v-chip>
              </v-col>
            </v-row>

            <v-divider class="my-4"></v-divider>

            <!-- Error message if any -->
            <div v-if="selectedGatilhoLog.error_message" class="mb-4">
              <h4 class="text-subtitle-2 font-weight-bold text-error mb-2">Mensagem de Erro</h4>
              <v-alert type="error" variant="tonal" class="text-caption">
                <pre style="white-space: pre-wrap; font-family: monospace;">{{ selectedGatilhoLog.error_message }}</pre>
              </v-alert>
            </div>

            <!-- Disparador Response Body if any -->
            <div>
              <h4 class="text-subtitle-2 font-weight-bold text-white mb-2">Resposta do Disparador</h4>
              <v-sheet rounded class="code-sheet pa-4" v-if="selectedGatilhoLog.response_payload">
                <pre>{{ formatJSON(selectedGatilhoLog.response_payload) }}</pre>
              </v-sheet>
              <div v-else class="text-medium-emphasis font-italic text-body-2">Nenhuma resposta gravada.</div>
            </div>
          </div>

          <!-- TAB: RAW REQUEST -->
          <div v-else-if="gatilhoDetailTab === 'raw'">
            <div class="d-flex justify-space-between align-center mb-2">
              <span class="text-caption text-medium-emphasis">Exibindo payload recebido cru da requisição</span>
              <v-btn size="x-small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyToClipboard(selectedGatilhoLog.request_payload)">
                Copiar Payload
              </v-btn>
            </div>
            <v-sheet rounded class="code-sheet pa-4">
              <pre>{{ formatJSON(selectedGatilhoLog.request_payload) }}</pre>
            </v-sheet>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 border-t">
          <v-btn
            color="success"
            variant="flat"
            prepend-icon="mdi-send-clock"
            :loading="retriggeringGatilho"
            @click="retriggerGatilho(selectedGatilhoLog.id)"
          >
            Re-disparar (Nova Chamada)
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="gatilhosDialog = false" :disabled="retriggeringGatilho">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import axiosInstance from '@/plugins/axios'
import axios from 'axios'
import VueApexCharts from 'vue3-apexcharts'
import ApexCharts from 'apexcharts'

const apexchart = VueApexCharts

const activeTab = ref('webhooks')

// Ingress (Entradas) client and state
const ingressAxios = axios.create({
  baseURL: '/ingress-api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

const ingressLogs = ref([])
const ingressTotal = ref(0)
const ingressPage = ref(1)
const ingressItemsPerPage = ref(20)
const ingressLoading = ref(false)
const ingressSearchPath = ref('')
const ingressStatusFilter = ref(null)
const ingressDialog = ref(false)
const selectedIngressLog = ref(null)
const ingressDetailTab = ref('general')

// Gatilhos Disparador State
const gatilhosLogs = ref([])
const gatilhosTotal = ref(0)
const gatilhosPage = ref(1)
const gatilhosItemsPerPage = ref(20)
const gatilhosLoading = ref(false)
const gatilhosSearchPath = ref('')
const gatilhosStatusFilter = ref(null)
const gatilhosDialog = ref(false)
const selectedGatilhoLog = ref(null)
const gatilhoDetailTab = ref('general')
const retriggeringGatilho = ref(false)


// Debounce utility for search inputs
let _debounceTimer = null
function debouncedFetchLogs(delay = 400) {
  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => {
    page.value = 1
    fetchLogs()
  }, delay)
}

// Workflows / Automações state
const workflowsList = ref([])
const selectedWorkflowId = ref(null)
const workflowExecutions = ref([])
const workflowExecutionsTotal = ref(0)
const workflowPage = ref(1)
const workflowItemsPerPage = ref(20)
const wfLoading = ref(false)
const wfStats = computed(() => {
  const list = workflowExecutions.value || []
  const total = list.length
  const completed = list.filter(e => e.status === 'completed').length
  const failed = list.filter(e => e.status === 'failed').length
  const totalDuration = list.reduce((acc, curr) => acc + (curr.duration_ms || 0), 0)
  const avgDuration = total > 0 ? Math.round(totalDuration / total) : 0
  return { total, completed, failed, avgDuration }
})

// Details
const wfDrawer = ref(false)
const selectedWfExecution = ref(null)
const wfDetailTab = ref('timeline')

const dispStats = ref({ total_campaigns: 0, active_campaigns: 0, completed_campaigns: 0, total_sent: 0, total_failed: 0 })
const dispCampaigns = ref([])
const dispStaged = ref([])
const dispLoading = ref(false)
const dispDialog = ref(false)
const dispSelected = ref(null)
const dispReport = ref(null)
const dispActionLoading = ref(false)
const redispatchingContact = ref(null)

const dispHeaders = [
  { title: 'QUEUE ID', key: 'queue_id' },
  { title: 'TIPO', key: 'type_id' },
  { title: 'SERVICE ID', key: 'service_id' },
  { title: 'STATUS', key: 'status' },
  { title: 'INÍCIO', key: 'started_at' },
  { title: 'TOTAL', key: 'total' },
  { title: 'ENVIADAS', key: 'sent' },
  { title: 'FALHAS', key: 'failed' },
  { title: 'PROGRESSO', key: 'percent' },
  { title: 'AÇÕES', key: 'actions', sortable: false, align: 'end' }
]

const fetchDisparadorData = async () => {
    dispLoading.value = true
    try {
       const [resStats, resCamp] = await Promise.all([
           axiosInstance.get('/disparador/dashboard/stats'),
           axiosInstance.get('/disparador/dashboard/campaigns')
       ])
       dispStats.value = resStats.data
       dispCampaigns.value = resCamp.data
    } catch (e) {
       console.error('Failed to fetch disparador core data:', e)
    } 
    
    try {
       const resStaged = await axiosInstance.get('/disparador/dashboard/staged')
       dispStaged.value = resStaged.data
    } catch (e) {
       console.error('Failed to fetch staged queue:', e)
    } finally {
       dispLoading.value = false
    }
}

const dispatchStagedQueue = async (queue_id) => {
    try {
        await axiosInstance.post(`/disparador/dashboard/staged/${queue_id}/dispatch`)
        snackbar.value = { show: true, text: 'Fila disparada com sucesso!', color: 'success' }
        await fetchDisparadorData()
    } catch (e) {
        snackbar.value = { show: true, text: `Erro ao disparar fila: ${e.response?.data?.detail || e.message}`, color: 'error' }
    }
}

const deleteStagedQueue = async (queue_id) => {
    try {
        await axiosInstance.delete(`/disparador/dashboard/staged/${queue_id}/delete`)
        snackbar.value = { show: true, text: 'Fila excluída com sucesso!', color: 'success' }
        await fetchDisparadorData()
    } catch (e) {
        snackbar.value = { show: true, text: `Erro ao excluir fila: ${e.response?.data?.detail || e.message}`, color: 'error' }
    }
}

const openDispDetails = async (item) => {
    dispSelected.value = item
    dispReport.value = null
    dispDialog.value = true
    try {
        const res = await axiosInstance.get(`/disparador/dashboard/campaigns/${item.service_id}/report`)
        dispReport.value = res.data
    } catch (e) {
        console.error('Failed to fetch campaign report:', e)
    }
}

const dispAction = async (action) => {
    if (!dispSelected.value) return
    dispActionLoading.value = true
    try {
        const endpoint = `/disparador/dashboard/campaigns/${dispSelected.value.service_id}/${action}`
        await axiosInstance.post(endpoint)
        if (action === 'retry-dlq') {
            dispReport.value.dlq_count = 0
            snackbar.value = { show: true, text: 'Contatos falhados reenfileirados.', color: 'success' }
        } else if (action === 'recreate') {
            snackbar.value = { show: true, text: 'Campanha recriada e disparada com sucesso!', color: 'success' }
            dispDialog.value = false
        } else if (action === 'delete') {
            snackbar.value = { show: true, text: 'Campanha excluída e filas limpas!', color: 'success' }
            dispDialog.value = false
        } else if (action === 'pause') {
            snackbar.value = { show: true, text: 'Campanha pausada com sucesso.', color: 'success' }
        } else if (action === 'resume') {
            snackbar.value = { show: true, text: 'Campanha retomada com sucesso.', color: 'success' }
        }
        await fetchDisparadorData()
        if (action !== 'retry-dlq' && action !== 'recreate' && action !== 'delete') {
           const updated = dispCampaigns.value.find(c => c.service_id === dispSelected.value.service_id)
           if (updated) dispSelected.value = updated
        }
    } catch (e) {
        snackbar.value = { show: true, text: 'Erro ao executar ação.', color: 'error' }
    } finally {
        dispActionLoading.value = false
    }
}

const redispatchContact = async (contact) => {
    if (!dispSelected.value) return
    const contactKey = contact.number || contact.user_id
    redispatchingContact.value = contactKey
    try {
        const endpoint = `/disparador/dashboard/campaigns/${dispSelected.value.service_id}/redispatch-contact`
        await axiosInstance.post(endpoint, { contact })
        snackbar.value = { show: true, text: `Contato ${contact.name || ''} reenfileirado com sucesso!`, color: 'success' }
        // Update local contact status to pending
        if (dispReport.value && dispReport.value.contacts) {
            const c = dispReport.value.contacts.find(x => (x.number || x.user_id) === contactKey)
            if (c) {
                c.status = 'pending'
                c.error = null
            }
        }
    } catch (e) {
        snackbar.value = { show: true, text: `Erro ao redisparar contato: ${e.response?.data?.detail || e.message}`, color: 'error' }
    } finally {
        redispatchingContact.value = null
    }
}

// Loading
const loading = ref(false)
const statsLoading = ref(false)

// SSE
const sseConnected = ref(false)

// Charts — Dark themed
const statusChartSeries = ref([])
const statusChartOptions = ref({
  chart: {
    type: 'donut',
    fontFamily: 'Inter, sans-serif',
    background: 'transparent',
    events: {
      legendClick: (chartContext, seriesIndex, config) => {
        chartContext.hideSeries(config.globals.colors[seriesIndex])
      }
    }
  },
  labels: [],
  colors: ['#00FC8B', '#FF0055', '#FFB800', '#00D1FF'],
  plotOptions: { pie: { donut: { size: '68%', labels: { show: true, total: { show: true, label: 'Total', color: 'rgba(255,255,255,0.6)', formatter: (w) => w.globals.seriesTotals.reduce((a, b) => a + b, 0) } } } } },
  dataLabels: { enabled: false },
  legend: { position: 'bottom', labels: { colors: 'rgba(255,255,255,0.6)' } },
  stroke: { width: 2, colors: ['#070a13'] },
      tooltip: { theme: 'dark', y: { formatter: (val, opts) => `${val} (${((val / opts.config.series.reduce((a, b) => a + b, 0)) * 100).toFixed(1)}%)` } },
  responsive: [{
    breakpoint: 480,
    options: {
      chart: { height: 220 },
      legend: { position: 'right' }
    }
  }]
})

const pathChartSeries = ref([{ name: 'Requisições', data: [] }])
const pathChartOptions = ref({
  chart: {
    type: 'bar',
    toolbar: { show: true, tools: { download: true } },
    fontFamily: 'Inter, sans-serif',
    background: 'transparent'
  },
  plotOptions: { bar: { horizontal: true, borderRadius: 6, barHeight: '60%', dataLabels: { position: 'top' } } },
  dataLabels: { enabled: true, style: { colors: ['#fff'] }, formatter: (val) => `${val}` },
  xaxis: { categories: [], labels: { style: { colors: 'rgba(255,255,255,0.5)' } } },
  yaxis: { labels: { style: { colors: 'rgba(255,255,255,0.7)' } } },
  grid: { borderColor: 'rgba(255,255,255,0.04)' },
  colors: ['#9D4EDD'],
  tooltip: { theme: 'dark' },
  responsive: [{
    breakpoint: 768,
    options: {
      chart: { height: 240 },
      yaxis: { labels: { rotate: -90 } }
    }
  }]
})

// Data Table
const logs = ref([])
const totalItems = ref(0)
const page = ref(1)
const itemsPerPage = ref(20)
const itemsPerPageOptions = [
  { value: 20, title: '20' },
  { value: 50, title: '50' },
  { value: 100, title: '100' },
  { value: 250, title: '250' },
  { value: 500, title: '500' },
  { value: 1000, title: '1000' },
]
const searchPaths = ref([])
const webhooksList = ref([])
const fetchWebhooksList = async () => {
  try {
    const { data } = await axiosInstance.get('/webhooks-config')
    if (data && data.webhooks) {
      webhooksList.value = data.webhooks.map(w => w.path)
    }
  } catch(e) {}
}

const internalPaths = ref([
  '/process',
  '/disparo/campaign',
  '/webhook/n8n',
  '/webhook/trigger/personalizado'
])

const availablePaths = computed(() => {
  const chartPaths = trackingStats.value.by_path?.map(i => i.path) || []
  const all = new Set([
     ...chartPaths,
     ...webhooksList.value,
     ...internalPaths.value
  ])
  return Array.from(all).sort()
})
const onSearchPathsChange = () => {
  const key = activeTab.value === 'notificacoes' ? 'notificacoes_search_paths' : 'acompanhamento_search_paths'
  localStorage.setItem(key, JSON.stringify(searchPaths.value));
  fetchLogs();
}

watch(activeTab, (newVal) => {
  if (['webhooks', 'notificacoes'].includes(newVal)) {
    const key = newVal === 'notificacoes' ? 'notificacoes_search_paths' : 'acompanhamento_search_paths'
    try {
      const saved = localStorage.getItem(key);
      searchPaths.value = saved ? JSON.parse(saved) : [];
    } catch (e) {
      searchPaths.value = [];
    }
    page.value = 1;
    fetchLogs();
  }
})
const searchSessionId = ref('')
const searchChurchName = ref('')
const searchMemberName = ref('')
const searchMessage = ref('')
const searchResponse = ref('')
const statusFilter = ref(null)
const statusOptions = ['completed', 'failed', 'queued', 'in_progress', 'buffered', 'paused']

// Auto-search on typing with debounce (no need to press Enter)
watch(searchSessionId, () => debouncedFetchLogs())
watch(searchChurchName, () => debouncedFetchLogs())
watch(searchMemberName, () => debouncedFetchLogs())
watch(searchMessage, () => debouncedFetchLogs())
watch(searchResponse, () => debouncedFetchLogs())

const headers = [
  { title: 'Data/Hora', key: 'created_at', sortable: false, width: '110px' },
  { title: 'Session ID', key: 'session_id', sortable: false, width: '90px' },
  { title: 'Igreja', key: 'church_name', sortable: false, width: '100px' },
  { title: 'Nome', key: 'member_fullname', sortable: false, width: '100px' },
  { title: 'Mensagem (Input)', key: 'user_message', sortable: false, width: '140px' },
  { title: 'Resposta (Output)', key: 'agent_response', sortable: false, width: '140px' },
  { title: 'Webhook Path', key: 'webhook_path', sortable: false, width: '100px' },
  { title: 'Status', key: 'status', sortable: false, width: '90px' },
  { title: 'Tempo', key: 'duration_ms', sortable: false, width: '80px' },
  { title: 'Ação', key: 'actions', sortable: false, align: 'center', width: '140px' }
]

const dialog = ref(false)
const selectedJob = ref(null)
const snackbar = ref({ show: false, text: '', color: 'success' })

// Test mode references
const testingJob = ref(false)
const testResult = ref(null)

// Redo state
const redoingJob = ref(false)
const redoResult = ref(null)
const redoNewJobId = ref(null)
const redoCallbackUrl = ref(null)
const resendingRedo = ref(false)

// Abort state
const abortingJob = ref(false)

// Resend state
const resendingJob = ref(false)

// Human Response state
const showHumanInput = ref(false)
const humanText = ref('')
const sendingHuman = ref(false)

// Agent Control state
const pauseMinutes = ref(null)
const pausingAgent = ref(false)
const activatingAgent = ref(false)
const unblockingBot = ref(false)
const blockingBot = ref(false)
const unlockingSession = ref(false)

// STM/MTM Memory Dialog
const memoryDialog = ref(false)
const memoryDialogType = ref('stm')
const memoryDialogTitle = ref('')
const memoryDialogLoading = ref(false)
const memoryMessages = ref([])

// ── SSE Connection (fetch-based for auth header support) ──
let sseAbortController = null

function connectSSE() {
  disconnectSSE()
  sseAbortController = new AbortController()

  const baseUrl = axiosInstance.defaults?.baseURL || '/api'
  const token = localStorage.getItem('accessToken')
  const headers = { 'Accept': 'text/event-stream' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const doConnect = async () => {
    try {
      const res = await fetch(`${baseUrl}/tracking/stream`, {
        headers,
        signal: sseAbortController.signal,
      })

      if (!res.ok) {
        sseConnected.value = false
        scheduleReconnect()
        return
      }

      sseConnected.value = true
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          try {
            const payload = JSON.parse(raw)
            handleSSEEvent(payload)
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        sseConnected.value = false
        scheduleReconnect()
      }
    }
  }

  doConnect()
}

function scheduleReconnect() {
  setTimeout(() => {
    if (!sseAbortController?.signal.aborted) {
      connectSSE()
    }
  }, 5000)
}

function handleSSEEvent(payload) {
  const { event, data: jobData } = payload
  if (!jobData) return

  if (event === 'new_job') {
    const idx = logs.value.findIndex(j => j.job_id === jobData.job_id)
    if (idx !== -1) {
      logs.value[idx] = { ...logs.value[idx], ...jobData }
    } else {
      logs.value.unshift(jobData)
      totalItems.value += 1
    }
  } else if (event === 'job_updated') {
    const idx = logs.value.findIndex(j => j.job_id === jobData.job_id)
    if (idx !== -1) {
      logs.value[idx] = { ...logs.value[idx], ...jobData }
    } else {
      logs.value.unshift(jobData)
      totalItems.value += 1
    }
  }

  // Refresh stats occasionally
  if (Math.random() < 0.2) {
    fetchStats()
  }
}

function disconnectSSE() {
  if (sseAbortController) {
    sseAbortController.abort()
    sseAbortController = null
  }
  sseConnected.value = false
}

// ── Helpers ──
function getSessionId(item) {
  return item.request_data?.session_id || item.session_id || null
}

const trackingStats = ref({ total_calls: 0, by_path: [] })

const fetchStats = async () => {
  statsLoading.value = true
  try {
    const { data } = await axiosInstance.get('/tracking/stats')
    trackingStats.value = data
  } catch (error) {
    showSnackbar('Erro ao carregar estatísticas', 'error')
  } finally { statsLoading.value = false }
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const skip = (page.value - 1) * itemsPerPage.value
    let url = `/tracking/logs?skip=${skip}&limit=${itemsPerPage.value}`
    if (statusFilter.value) url += `&status=${encodeURIComponent(statusFilter.value)}`
    if (searchPaths.value && searchPaths.value.length > 0) url += `&path=${encodeURIComponent(searchPaths.value.join(','))}`
    if (searchSessionId.value) url += `&session_id=${encodeURIComponent(searchSessionId.value)}`
    if (searchChurchName.value) url += `&church_name=${encodeURIComponent(searchChurchName.value)}`
    if (searchMemberName.value) url += `&member_name=${encodeURIComponent(searchMemberName.value)}`
    if (searchMessage.value) url += `&user_message=${encodeURIComponent(searchMessage.value)}`
    if (searchResponse.value) url += `&agent_response=${encodeURIComponent(searchResponse.value)}`

    const { data } = await axiosInstance.get(url)

    logs.value = data.items || []
    totalItems.value = data.total || 0
  } catch (error) {
    showSnackbar('Erro ao carregar logs', 'error')
  } finally { loading.value = false }
}

const fetchData = () => { fetchStats(); fetchLogs() }
const handleOptionsUpdate = ({ page: np, itemsPerPage: nip }) => {
  const nextPage = np || 1
  const nextItemsPerPage = nip || itemsPerPage.value
  const shouldFetch = page.value !== nextPage || itemsPerPage.value !== nextItemsPerPage
  page.value = nextPage
  itemsPerPage.value = nextItemsPerPage
  if (shouldFetch) fetchLogs()
}
const openJobDetails = async (job) => {
  testResult.value = null;
  redoResult.value = null;
  redoNewJobId.value = null;
  redoCallbackUrl.value = null;
  showHumanInput.value = false;
  humanText.value = '';

  try {
    const { data } = await axiosInstance.get(`/tracking/jobs/${job.job_id}`)
    selectedJob.value = data
  } catch (error) {
    console.error('Erro ao carregar detalhes do job:', error)
    selectedJob.value = job
    showSnackbar('Falha ao carregar detalhes completos do job', 'error')
  }

  dialog.value = true
}

// ── STM/MTM from Job ──
async function viewStmFromJob(item) {
  const sessionId = getSessionId(item)
  if (!sessionId) return
  
  memoryDialogType.value = 'stm'
  memoryDialogTitle.value = `STM - Conversa: ${sessionId}`
  memoryMessages.value = []
  memoryDialogLoading.value = true
  memoryDialog.value = true

  try {
    const key = `conversation:${sessionId}`
    const { data } = await axiosInstance.get(`/memory/stm/keys/${encodeURIComponent(key)}`)
    memoryMessages.value = data.messages || []
  } catch (e) {
    memoryMessages.value = []
    showSnackbar('Erro ao carregar conversa STM', 'error')
  } finally {
    memoryDialogLoading.value = false
  }
}

async function viewMtmFromJob(item) {
  const sessionId = getSessionId(item)
  if (!sessionId) return

  memoryDialogType.value = 'mtm'
  memoryDialogTitle.value = `MTM - Histórico: ${sessionId}`
  memoryMessages.value = []
  memoryDialogLoading.value = true
  memoryDialog.value = true

  try {
    const { data } = await axiosInstance.get(`/memory/mtm/sessions/${encodeURIComponent(sessionId)}`)
    memoryMessages.value = data.messages || []
  } catch (e) {
    memoryMessages.value = []
    showSnackbar('Erro ao carregar histórico MTM', 'error')
  } finally {
    memoryDialogLoading.value = false
  }
}

const testCurrentJob = async () => {
  if (!selectedJob.value) return;
  testingJob.value = true;
  testResult.value = null;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/test`);
    showSnackbar(`Job testado em ${data.processing_time_ms}ms`, 'success');
    testResult.value = data.test_response;
  } catch (error) {
    console.error("Erro no teste:", error);
    showSnackbar('Falha ao testar job internamente', 'error');
    if (error.response?.data?.detail) {
      testResult.value = { error: error.response.data.detail };
    }
  } finally {
    testingJob.value = false;
  }
}

const redoCurrentJob = async () => {
  if (!selectedJob.value) return;
  redoingJob.value = true;
  redoResult.value = null;
  redoNewJobId.value = null;
  redoCallbackUrl.value = null;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/redo`);
    showSnackbar(`Job refeito em ${data.processing_time_ms}ms — Novo Job: ${data.new_job_id}`, 'success');
    redoResult.value = data.response_data;
    redoNewJobId.value = data.new_job_id;
    redoCallbackUrl.value = data.callback_url;
  } catch (error) {
    console.error("Erro ao refazer:", error);
    showSnackbar('Falha ao refazer job', 'error');
    if (error.response?.data?.detail) {
      redoResult.value = { error: error.response.data.detail };
    }
  } finally {
    redoingJob.value = false;
  }
}

const resendRedoResult = async () => {
  if (!redoNewJobId.value) return;
  resendingRedo.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${redoNewJobId.value}/resend`);
    showSnackbar(data.message || 'Novo resultado enviado com sucesso!', 'success');
  } catch (error) {
    console.error("Erro ao enviar resultado do redo:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao enviar resultado', 'error');
  } finally {
    resendingRedo.value = false;
  }
}

const abortCurrentJob = async () => {
  if (!selectedJob.value) return;
  abortingJob.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/abort`);
    showSnackbar(data.message || 'Sinal de cancelamento enviado!', 'warning');
    selectedJob.value.status = 'failed';
    selectedJob.value.error_message = 'Aguardando cancelamento / Aborted by user';
  } catch (error) {
    console.error("Erro ao cancelar:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao abortar job', 'error');
  } finally {
    abortingJob.value = false;
  }
}

const resendCurrentJob = async () => {
  if (!selectedJob.value) return;
  resendingJob.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/resend`);
    showSnackbar(data.message || 'Response reenviado com sucesso!', 'success');
  } catch (error) {
    console.error("Erro ao reenviar:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao reenviar response', 'error');
  } finally {
    resendingJob.value = false;
  }
}

const sendHumanResponse = async () => {
  if (!selectedJob.value || !humanText.value.trim()) return;
  sendingHuman.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/human-response`, { human_text: humanText.value });
    showSnackbar(data.message || 'Human response enviada com sucesso!', 'success');
    showHumanInput.value = false;
    if (selectedJob.value.response_data && 'result' in selectedJob.value.response_data) {
      selectedJob.value.response_data.result = humanText.value;
    }
    humanText.value = '';
  } catch (error) {
    console.error("Erro ao enviar human response:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao enviar human response', 'error');
  } finally {
    sendingHuman.value = false;
  }
}

// ── Agent Control Functions ──
const pauseAgent = async (minutes) => {
  if (!selectedJob.value) return;
  pausingAgent.value = true;
  try {
    const body = minutes ? { timeout_minutes: Number(minutes) } : {};
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/pause-agent`, body);
    const modeText = data.mode === 'temporary' ? `por ${data.timeout_minutes} min` : 'permanentemente';
    showSnackbar(`Agente desativado ${modeText} para sessão ${data.session_id}`, 'warning');
  } catch (error) {
    console.error("Erro ao pausar agente:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao desativar agente', 'error');
  } finally {
    pausingAgent.value = false;
  }
}

const activateAgent = async () => {
  if (!selectedJob.value) return;
  activatingAgent.value = true;
  try {
    const { data } = await axiosInstance.post(`/tracking/jobs/${selectedJob.value.job_id}/activate-agent`);
    showSnackbar(`Agente reativado para sessão ${data.session_id}`, 'success');
  } catch (error) {
    console.error("Erro ao ativar agente:", error);
    showSnackbar(error.response?.data?.detail || 'Falha ao ativar agente', 'error');
  } finally {
    activatingAgent.value = false;
  }
}

const unblockBot = async (sessionId) => {
  if (!sessionId) return
  unblockingBot.value = true
  try {
    await axiosInstance.delete(`/tracking/antibot/${sessionId}`)
    showSnackbar('Bloqueio Anti-Bot removido!', 'success')
  } catch (error) {
    console.error('Error unblocking bot:', error)
    showSnackbar('Erro ao remover bloqueio', 'error')
  } finally {
    unblockingBot.value = false
  }
}

const blockBot = async (sessionId) => {
  if (!sessionId) return
  blockingBot.value = true
  try {
    await axiosInstance.post(`/tracking/antibot/${sessionId}`)
    showSnackbar('Sessão marcada e bloqueada como BOT!', 'error')
  } catch (error) {
    console.error('Error blocking bot:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao bloquear sessão como bot', 'error')
  } finally {
    blockingBot.value = false
  }
}

const unlockSession = async (sessionId) => {
  if (!sessionId) return
  unlockingSession.value = true
  try {
    await axiosInstance.post(`/tracking/sessions/${sessionId}/unlock`)
    showSnackbar('Trava de concorrência e buffer da sessão liberados!', 'success')
  } catch (error) {
    console.error('Error unlocking session:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao liberar trava da sessão', 'error')
  } finally {
    unlockingSession.value = false
  }
}

// ── Memory Bubble Helpers ──
const getMemoryBubbleClass = (role) => ({
  'user': 'mem-user-msg',
  'assistant': 'mem-assistant-msg',
  'fromMe': 'mem-fromme-msg',
  'supportResponse': 'mem-support-msg',
}[role] || 'mem-user-msg')

const getMemoryIcon = (role) => ({
  'user': 'mdi-account',
  'assistant': 'mdi-robot',
  'fromMe': 'mdi-whatsapp',
  'supportResponse': 'mdi-headset',
}[role] || 'mdi-account')

const getMemoryIconColor = (role) => ({
  'user': '#00D1FF',
  'assistant': '#9D4EDD',
  'fromMe': '#25D366',
  'supportResponse': '#FBBF24',
}[role] || '#00D1FF')

const getStatusColor = (status) => ({ 'completed': 'success', 'failed': 'error', 'queued': 'warning', 'in_progress': 'info', 'buffered': 'purple', 'paused': 'orange' }[status] || 'grey')
const getStatusIcon = (status) => ({ 'completed': 'mdi-check', 'failed': 'mdi-close', 'queued': 'mdi-clock', 'in_progress': 'mdi-play', 'buffered': 'mdi-tray-full', 'paused': 'mdi-pause-circle' }[status] || 'mdi-help')
const formatDate = (d) => d ? new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
const formatJSON = (obj) => { try { return JSON.stringify(obj, null, 2) } catch { return obj } }

const fetchWorkflows = async () => {
  try {
    const { data } = await axiosInstance.get('/workflows')
    workflowsList.value = data.workflows || []
    if (workflowsList.value.length > 0 && !selectedWorkflowId.value) {
      selectedWorkflowId.value = workflowsList.value[0].id
    }
  } catch (error) {
    console.error('Error fetching workflows:', error)
    showSnackbar('Erro ao buscar lista de automações', 'error')
  }
}

const fetchWorkflowExecutions = async () => {
  if (!selectedWorkflowId.value) return
  wfLoading.value = true
  try {
    const skip = (workflowPage.value - 1) * workflowItemsPerPage.value
    const { data } = await axiosInstance.get(`/workflows/${selectedWorkflowId.value}/executions`, {
      params: { skip, limit: workflowItemsPerPage.value }
    })
    workflowExecutions.value = data.executions || []
    workflowExecutionsTotal.value = data.total || 0
  } catch (error) {
    console.error('Error fetching executions:', error)
    showSnackbar('Erro ao buscar logs de execução', 'error')
  } finally {
    wfLoading.value = false
  }
}

const openWfExecutionDetails = async (execution) => {
  try {
    const { data } = await axiosInstance.get(`/workflows/executions/${execution.id}`)
    selectedWfExecution.value = data
    wfDrawer.value = true
    wfDetailTab.value = 'timeline'
  } catch (error) {
    console.error('Error fetching execution details:', error)
    showSnackbar('Erro ao carregar detalhes da execução', 'error')
  }
}

const cancellingWfId = ref(null)
const cancellingWf = ref(false)

const cancelWfExecution = async (executionId) => {
  cancellingWfId.value = executionId
  cancellingWf.value = true
  try {
    await axiosInstance.post(`/workflows/executions/${executionId}/cancel`)
    showSnackbar('Sinal de parada enviado para a automação!', 'warning')
    
    // Update local state in table
    const idx = workflowExecutions.value.findIndex(e => e.id === executionId)
    if (idx !== -1) {
      workflowExecutions.value[idx].status = 'cancelled'
    }
    
    // Update local state in drawer
    if (selectedWfExecution.value && selectedWfExecution.value.id === executionId) {
      selectedWfExecution.value.status = 'cancelled'
      selectedWfExecution.value.error_message = 'Execução cancelada manualmente pelo usuário'
    }
  } catch (error) {
    console.error('Error cancelling execution:', error)
    showSnackbar(error.response?.data?.detail || 'Erro ao parar automação', 'error')
  } finally {
    cancellingWfId.value = null
    cancellingWf.value = false
  }
}

const getWfStatusColor = (status) => {
  return {
    'completed': 'success',
    'failed': 'error',
    'pending': 'warning',
    'running': 'info',
    'cancelled': 'grey'
  }[status] || 'grey'
}

const getWfStatusIcon = (status) => {
  return {
    'completed': 'mdi-check-circle',
    'failed': 'mdi-alert-circle',
    'pending': 'mdi-clock-outline',
    'running': 'mdi-sync',
    'cancelled': 'mdi-stop-circle-outline'
  }[status] || 'mdi-help-circle'
}

watch(selectedWorkflowId, () => {
  workflowPage.value = 1
  fetchWorkflowExecutions()
})

watch(workflowPage, () => {
  fetchWorkflowExecutions()
})

const fetchIngressLogs = async () => {
  ingressLoading.value = true
  try {
    const skip = (ingressPage.value - 1) * ingressItemsPerPage.value
    let url = `/pipelines/logs?skip=${skip}&limit=${ingressItemsPerPage.value}`
    
    const statusVal = ingressStatusFilter.value
    if (statusVal && statusVal !== 'null' && statusVal !== 'undefined' && String(statusVal).trim() !== '') {
      url += `&status=${encodeURIComponent(statusVal)}`
    }
    
    const pathVal = ingressSearchPath.value
    if (pathVal && pathVal !== 'null' && pathVal !== 'undefined' && String(pathVal).trim() !== '') {
      url += `&pipeline_path=${encodeURIComponent(pathVal)}`
    }
    
    const { data } = await ingressAxios.get(url)
    ingressLogs.value = data.items || []
    ingressTotal.value = data.total || 0
  } catch (e) {
    showSnackbar('Erro ao carregar logs do Ingress', 'error')
  } finally {
    ingressLoading.value = false
  }
}

const openIngressLogDetails = async (log) => {
  try {
    const { data } = await ingressAxios.get(`/pipelines/logs/${log.id}`)
    selectedIngressLog.value = data
    ingressDetailTab.value = 'general'
    ingressDialog.value = true
  } catch (e) {
    showSnackbar('Erro ao carregar detalhes do log do Ingress', 'error')
  }
}

const getIngressStatusColor = (status) => {
  return {
    'forwarded': 'success',
    'queued': 'warning',
    'stopped': 'info',
    'validation_error': 'error',
    'unauthorized': 'error',
    'not_found': 'error',
    'error': 'error'
  }[status] || 'grey'
}

const getIngressStatusIcon = (status) => {
  return {
    'forwarded': 'mdi-check-circle',
    'queued': 'mdi-clock-outline',
    'stopped': 'mdi-octagon-outline',
    'validation_error': 'mdi-alert-circle-outline',
    'unauthorized': 'mdi-lock-alert',
    'not_found': 'mdi-alert-octagon-outline',
    'error': 'mdi-alert'
  }[status] || 'mdi-help-circle'
}

// ── Gatilhos Disparador Functions ──
const fetchGatilhos = async () => {
  gatilhosLoading.value = true
  try {
    const skip = (gatilhosPage.value - 1) * gatilhosItemsPerPage.value
    let url = `/tracking/dispatcher-webhooks?skip=${skip}&limit=${gatilhosItemsPerPage.value}`

    const statusVal = gatilhosStatusFilter.value
    if (statusVal && statusVal !== 'null' && String(statusVal).trim() !== '') {
      url += `&status=${encodeURIComponent(statusVal)}`
    }

    const pathVal = gatilhosSearchPath.value
    if (pathVal && pathVal !== 'null' && String(pathVal).trim() !== '') {
      url += `&path=${encodeURIComponent(pathVal)}`
    }

    const { data } = await axiosInstance.get(url)
    gatilhosLogs.value = data.items || []
    gatilhosTotal.value = data.total || 0
  } catch (e) {
    showSnackbar('Erro ao carregar logs de gatilhos do disparador', 'error')
  } finally {
    gatilhosLoading.value = false
  }
}

const openGatilhoDetails = async (log) => {
  try {
    const { data } = await axiosInstance.get(`/tracking/dispatcher-webhooks/${log.id}`)
    selectedGatilhoLog.value = data
    gatilhoDetailTab.value = 'general'
    gatilhosDialog.value = true
  } catch (e) {
    showSnackbar('Erro ao carregar detalhes do gatilho', 'error')
  }
}

const retriggerGatilho = async (logId) => {
  retriggeringGatilho.value = true
  try {
    const { data } = await axiosInstance.post(`/tracking/dispatcher-webhooks/${logId}/retrigger`)
    if (data.success) {
      showSnackbar(`Re-disparo realizado com sucesso! Status: ${data.status_code}`, 'success')
    } else {
      showSnackbar(`Re-disparo retornou status ${data.status_code}`, 'warning')
    }
    // Refresh logs list to show the new re-triggered log entry
    await fetchGatilhos()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Erro ao re-disparar gatilho', 'error')
  } finally {
    retriggeringGatilho.value = false
  }
}

const getGatilhoStatusColor = (status) => {
  return {
    'success': 'success',
    'pending': 'warning',
    'failed': 'error',
    'validation_error': 'deep-orange',
    'unauthorized': 'error'
  }[status] || 'grey'
}

const getGatilhoStatusIcon = (status) => {
  return {
    'success': 'mdi-check-circle',
    'pending': 'mdi-clock-outline',
    'failed': 'mdi-alert-circle',
    'validation_error': 'mdi-alert-circle-outline',
    'unauthorized': 'mdi-lock-alert'
  }[status] || 'mdi-help-circle'
}

const getGatilhoStatusLabel = (status) => {
  return {
    'success': 'SUCESSO',
    'pending': 'PENDENTE',
    'failed': 'FALHOU',
    'validation_error': 'VALIDAÇÃO',
    'unauthorized': 'NÃO AUTORIZADO'
  }[status] || (status ? status.toUpperCase() : '—')
}

watch(gatilhosPage, () => {
  fetchGatilhos()
})

watch(ingressSearchPath, () => {
  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => {
    ingressPage.value = 1
    fetchIngressLogs()
  }, 400)
})

watch(ingressStatusFilter, () => {
  ingressPage.value = 1
  fetchIngressLogs()
})

watch(ingressPage, () => {
  fetchIngressLogs()
})

watch(activeTab, (newTab) => {
  if (newTab === 'automacao') {
    fetchWorkflows()
  } else if (newTab === 'entradas') {
    fetchIngressLogs()
  } else if (newTab === 'gatilhos-disparador') {
    fetchGatilhos()
  }
})

const copyToClipboard = (data) => {
  const text = typeof data === 'object' ? JSON.stringify(data, null, 2) : data
  navigator.clipboard.writeText(text).then(() => showSnackbar('Copiado!', 'success')).catch(() => showSnackbar('Erro ao copiar', 'error'))
}

const showSnackbar = (text, color = 'success') => { snackbar.value = { show: true, text, color } }

onMounted(() => { 
  try {
    const key = activeTab.value === 'notificacoes' ? 'notificacoes_search_paths' : 'acompanhamento_search_paths'
    const saved = localStorage.getItem(key);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) searchPaths.value = parsed;
    }
  } catch (e) {}
  fetchWebhooksList()
  fetchData()
  fetchDisparadorData()
  fetchWorkflows()
  fetchIngressLogs()
  fetchGatilhos()
  connectSSE()
})

onUnmounted(() => {
  disconnectSSE()
})
</script>

<style scoped>
.tracking-page {
  animation: pageEnter 0.45s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.code-sheet {
  background: rgba(5, 8, 16, 0.8) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.8);
}

.code-sheet pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

/* SSE indicator */
.sse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00FC8B;
  box-shadow: 0 0 6px rgba(0, 252, 139, 0.6);
  animation: sse-pulse 2s ease-in-out infinite;
}

.sse-offline {
  background: #FF0055;
  box-shadow: 0 0 6px rgba(255, 0, 85, 0.4);
  animation: none;
}

@keyframes sse-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Memory message bubbles */
.memory-bubble {
  border: 1px solid rgba(255,255,255,0.05);
}

.mem-user-msg {
  background: rgba(0, 163, 255, 0.06);
  border-left: 3px solid rgba(0, 209, 255, 0.5);
}

.mem-assistant-msg {
  background: rgba(157, 78, 221, 0.06);
  border-left: 3px solid rgba(157, 78, 221, 0.5);
}

.mem-fromme-msg {
  background: rgba(37, 211, 102, 0.08);
  border-left: 3px solid rgba(37, 211, 102, 0.5);
}

.mem-support-msg {
  background: rgba(251, 191, 36, 0.08);
  border-left: 3px solid rgba(251, 191, 36, 0.5);
}

/* Data table pagination footer */
:deep(.v-data-table-footer) {
  background: rgba(255, 255, 255, 0.02) !important;
  border-top: 1px solid rgba(255, 255, 255, 0.05) !important;
  padding: 8px 16px !important;
}

:deep(.v-data-table-footer__info) {
  color: rgba(255, 255, 255, 0.6) !important;
  font-size: 13px;
}

:deep(.v-data-table-footer__items-per-page .v-field) {
  background: rgba(255, 255, 255, 0.05) !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  color: rgba(255, 255, 255, 0.7) !important;
}

:deep(.v-data-table-footer__pagination .v-btn) {
  color: rgba(255, 255, 255, 0.6) !important;
}

:deep(.v-data-table-footer__pagination .v-btn:hover) {
  background: rgba(157, 78, 221, 0.15) !important;
  color: white !important;
}

:deep(.v-data-table-footer__pagination .v-btn--disabled) {
  color: rgba(255, 255, 255, 0.15) !important;
}
</style>
