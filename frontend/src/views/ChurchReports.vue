<template>
  <div class="pa-2">
    <v-row class="mb-4">
      <v-col cols="12" md="3">
        <v-select
          v-model="selectedChurch"
          :items="churches"
          item-title="name"
          item-value="id"
          label="Igreja"
          variant="outlined"
          density="comfortable"
          @update:modelValue="fetchReports"
        ></v-select>
      </v-col>
      <v-col cols="12" md="3">
        <v-select
          v-model="periodType"
          :items="periodOptions"
          label="Período"
          variant="outlined"
          density="comfortable"
          @update:modelValue="fetchReports"
        ></v-select>
      </v-col>
      <v-col cols="12" md="3">
        <v-text-field
          v-model="targetDate"
          type="date"
          label="Data Base do Relatório"
          variant="outlined"
          density="comfortable"
        ></v-text-field>
      </v-col>
      <v-col cols="12" md="3" class="d-flex align-center justify-end">
        <v-btn color="secondary" prepend-icon="mdi-flash" @click="generateManual" :disabled="!selectedChurch" :loading="generating">
          Gerar Relatório Agora
        </v-btn>
      </v-col>
    </v-row>

    <v-card class="glass-card mb-6" elevation="0">
      <v-data-table-server
        v-model:items-per-page="itemsPerPage"
        :headers="headers"
        :items="reports"
        :items-length="totalItems"
        :loading="loading"
        @update:options="fetchReports"
        class="elevation-0"
        hover
      >
        <template v-slot:item.period_start="{ item }">
          {{ formatDate((item.raw || item).period_start) }}
        </template>
        
        <template v-slot:item.status="{ item }">
          <v-chip
            :color="getStatusColor((item.raw || item).status)"
            size="small"
            class="text-uppercase font-weight-bold"
          >
            {{ (item.raw || item).status }}
          </v-chip>
        </template>

        <template v-slot:item.actions="{ item }">
          <v-btn icon="mdi-eye" size="small" variant="text" color="primary" @click="viewReport(item.raw || item)"></v-btn>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- Dialog de Visualização Detalhada do Relatório -->
    <v-dialog v-model="dialog" max-width="1100" scrollable>
      <v-card class="bg-surface" rounded="lg">
        <v-card-title class="d-flex align-center justify-space-between pa-4 border-b">
          <div class="d-flex align-center ga-3">
            <v-icon color="primary" size="large">mdi-church</v-icon>
            <div>
              <div class="text-h6 font-weight-bold">
                {{ selectedReport?.entity_name || 'Igreja Local' }}
              </div>
              <div class="text-caption text-medium-emphasis">
                Período: {{ selectedReport?.period_type === 'daily' ? 'Diário' : selectedReport?.period_type === 'weekly' ? 'Semanal' : 'Mensal' }} • {{ formatDate(selectedReport?.period_start) }}
              </div>
            </div>
          </div>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false"></v-btn>
        </v-card-title>
        
        <!-- Tabs de Navegação: Quantitativo, Parecer Pastoral e JSON CRM -->
        <v-tabs v-model="activeTab" bg-color="surface-variant" color="primary" density="comfortable" grow>
          <v-tab value="quantitativo">
            <v-icon start>mdi-chart-box-outline</v-icon>
            Métricas & Quantitativo
          </v-tab>
          <v-tab value="qualitativo">
            <v-icon start>mdi-text-box-search-outline</v-icon>
            Parecer Pastoral
          </v-tab>
          <v-tab value="crm_json">
            <v-icon start>mdi-code-json</v-icon>
            JSON Técnico / CRM
          </v-tab>
        </v-tabs>

        <v-card-text class="pa-5" style="background: rgba(0,0,0,0.2); max-height: 75vh;">
          <v-window v-model="activeTab">
            <!-- TAB 1: VISÃO QUANTITATIVA E CASOS CRÍTICOS -->
            <v-window-item value="quantitativo">
              <!-- Cards de Destaque -->
              <v-row class="mb-4">
                <v-col cols="12" sm="6" md="3">
                  <v-card variant="outlined" class="pa-3 text-center bg-surface">
                    <div class="text-caption text-medium-emphasis">Atendimentos Totais</div>
                    <div class="text-h4 font-weight-bold text-primary mt-1">
                      {{ quantData.total_atendimentos || selectedReport?.stats?.total_users || 0 }}
                    </div>
                  </v-card>
                </v-col>
                <v-col cols="12" sm="6" md="3">
                  <v-card variant="outlined" class="pa-3 text-center bg-surface">
                    <div class="text-caption text-medium-emphasis">Membros Únicos</div>
                    <div class="text-h4 font-weight-bold text-info mt-1">
                      {{ selectedReport?.stats?.total_users || 0 }}
                    </div>
                  </v-card>
                </v-col>
                <v-col cols="12" sm="6" md="3">
                  <v-card variant="outlined" class="pa-3 text-center bg-surface">
                    <div class="text-caption text-medium-emphasis">Casos de Atenção Pastoral</div>
                    <div class="text-h4 font-weight-bold text-warning mt-1">
                      {{ selectedReport?.stats?.critical_cases || criticalCases.length || 0 }}
                    </div>
                  </v-card>
                </v-col>
                <v-col cols="12" sm="6" md="3">
                  <v-card variant="outlined" class="pa-3 text-center bg-surface">
                    <div class="text-caption text-medium-emphasis">Disparos Automáticos</div>
                    <div class="text-h4 font-weight-bold text-purple mt-1">
                      {{ selectedReport?.stats?.total_disparos_automaticos || 0 }}
                    </div>
                  </v-card>
                </v-col>
              </v-row>

              <!-- Tráfego de Mensagens e Funil de Disparos -->
              <v-row class="mb-4">
                <v-col cols="12" md="6">
                  <v-card variant="outlined" class="bg-surface pa-4 h-100">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="teal" size="small">mdi-message-text-fast-outline</v-icon>
                      Tráfego de Mensagens no Período
                    </div>
                    <v-row dense>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Total Diálogo</div>
                        <div class="text-h6 font-weight-bold text-teal">
                          {{ selectedReport?.stats?.trafego_mensagens?.total_mensagens_dialogo || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Membros</div>
                        <div class="text-h6 font-weight-bold">
                          {{ selectedReport?.stats?.trafego_mensagens?.mensagens_membros || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Respostas IA</div>
                        <div class="text-h6 font-weight-bold">
                          {{ selectedReport?.stats?.trafego_mensagens?.respostas_ia || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Média/Membro</div>
                        <div class="text-h6 font-weight-bold text-info">
                          {{ selectedReport?.stats?.trafego_mensagens?.media_mensagens_por_membro || 0 }}
                        </div>
                      </v-col>
                    </v-row>
                  </v-card>
                </v-col>

                <v-col cols="12" md="6">
                  <v-card variant="outlined" class="bg-surface pa-4 h-100">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="indigo" size="small">mdi-filter-variant</v-icon>
                      Funil de Disparos e Notificações
                    </div>
                    <v-row dense>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Alcançados</div>
                        <div class="text-h6 font-weight-bold text-indigo">
                          {{ selectedReport?.stats?.funil_disparos?.membros_alcancados || selectedReport?.stats?.total_disparos_automaticos || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Passivos</div>
                        <div class="text-h6 font-weight-bold text-medium-emphasis">
                          {{ selectedReport?.stats?.funil_disparos?.contatos_passivos || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Reativos</div>
                        <div class="text-h6 font-weight-bold text-success">
                          {{ selectedReport?.stats?.funil_disparos?.interacoes_reativas || 0 }}
                        </div>
                      </v-col>
                      <v-col cols="6" sm="3">
                        <div class="text-caption text-medium-emphasis">Conversão</div>
                        <div class="text-h6 font-weight-bold text-purple">
                          {{ selectedReport?.stats?.funil_disparos?.taxa_conversao_pct || 0 }}%
                        </div>
                      </v-col>
                    </v-row>
                  </v-card>
                </v-col>
              </v-row>

              <!-- Dimensões 1 e 2: Tipo de Atendimento e Criticidade Pastoral -->
              <v-row class="mb-4">
                <v-col cols="12" md="7">
                  <v-card variant="outlined" class="bg-surface pa-4 h-100">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="primary" size="small">mdi-format-list-bulleted-type</v-icon>
                      Dimensão 1: Tipos de Atendimento Classificados (Analytics)
                    </div>
                    <div v-if="hasDim1" class="d-flex flex-wrap ga-2">
                      <v-chip
                        v-for="(count, key) in quantData.dimensao_1_tipo_atendimento"
                        :key="key"
                        v-show="count > 0"
                        :color="getDim1Color(key)"
                        variant="tonal"
                        size="small"
                        class="font-weight-medium"
                      >
                        {{ getDim1Label(key) }}: <strong class="ms-1">{{ count }}</strong>
                      </v-chip>
                    </div>
                    <div v-else class="text-caption text-medium-emphasis">Nenhum atendimento categorizado neste período.</div>
                  </v-card>
                </v-col>

                <v-col cols="12" md="5">
                  <v-card variant="outlined" class="bg-surface pa-4 h-100">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="warning" size="small">mdi-shield-alert-outline</v-icon>
                      Dimensão 2: Criticidade Pastoral
                    </div>
                    <div v-if="hasDim2" class="d-flex flex-wrap ga-2">
                      <v-chip
                        v-for="(count, key) in quantData.dimensao_2_criticidade_pastoral"
                        :key="key"
                        v-show="count > 0"
                        :color="getDim2Color(key)"
                        variant="flat"
                        size="small"
                        class="font-weight-bold"
                      >
                        {{ getDim2Label(key) }}: {{ count }}
                      </v-chip>
                    </div>
                    <div v-else class="text-caption text-medium-emphasis">Nenhum registro de criticidade no período.</div>
                  </v-card>
                </v-col>
              </v-row>

              <!-- Dimensões 3 e 4: Vínculo e Sentimento -->
              <v-row class="mb-4">
                <v-col cols="12" md="6">
                  <v-card variant="outlined" class="bg-surface pa-4">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="success" size="small">mdi-account-heart-outline</v-icon>
                      Dimensão 3: Vínculo com a Igreja
                    </div>
                    <div v-if="hasDim3" class="d-flex flex-wrap ga-2">
                      <v-chip
                        v-for="(count, key) in quantData.dimensao_3_vinculo"
                        :key="key"
                        v-show="count > 0"
                        :color="getDim3Color(key)"
                        variant="tonal"
                        size="small"
                      >
                        {{ getDim3Label(key) }}: <strong class="ms-1">{{ count }}</strong>
                      </v-chip>
                    </div>
                    <div v-else class="text-caption text-medium-emphasis">Sem dados de vínculo.</div>
                  </v-card>
                </v-col>

                <v-col cols="12" md="6">
                  <v-card variant="outlined" class="bg-surface pa-4">
                    <div class="text-subtitle-2 font-weight-bold mb-3 d-flex align-center">
                      <v-icon start color="info" size="small">mdi-emoticon-outline</v-icon>
                      Dimensão 4: Sentimento do Rebanho
                    </div>
                    <div v-if="hasDim4" class="d-flex flex-wrap ga-2">
                      <v-chip
                        v-for="(count, key) in quantData.dimensao_4_sentimento"
                        :key="key"
                        v-show="count > 0"
                        :color="getDim4Color(key)"
                        variant="tonal"
                        size="small"
                      >
                        {{ getDim4Label(key) }}: <strong class="ms-1">{{ count }}</strong>
                      </v-chip>
                    </div>
                    <div v-else class="text-caption text-medium-emphasis">Sem dados de sentimento.</div>
                  </v-card>
                </v-col>
              </v-row>

              <!-- Casos Críticos de Atenção Pastoral Detalhados -->
              <v-card v-if="criticalCases.length" variant="outlined" class="mb-4 bg-surface border-warning">
                <v-card-item class="py-2 bg-warning-lighten-5">
                  <v-card-title class="text-subtitle-2 font-weight-bold text-warning d-flex align-center">
                    <v-icon start color="warning" size="small">mdi-alert-circle</v-icon>
                    Casos que Requerem Visita ou Contato Pastoral Imediato ({{ criticalCases.length }})
                  </v-card-title>
                </v-card-item>
                <v-divider></v-divider>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th class="text-left">Membro</th>
                      <th class="text-left">Contato / Sessão</th>
                      <th class="text-left">Criticidade</th>
                      <th class="text-left">Ponto de Atenção / Cuidado</th>
                      <th class="text-center">Sentimento</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(c, idx) in criticalCases" :key="idx">
                      <td class="font-weight-medium">{{ c.membro_nome || 'Não Identificado' }}</td>
                      <td><code>{{ c.phone || c.session_id }}</code></td>
                      <td>
                        <v-chip size="x-small" :color="getDim2Color(c.criticidade)" variant="flat" class="font-weight-bold">
                          {{ getDim2Label(c.criticidade) }}
                        </v-chip>
                      </td>
                      <td class="text-caption">{{ c.resumo }}</td>
                      <td class="text-center">
                        <v-chip size="x-small" :color="getDim4Color(c.sentimento)" variant="tonal">
                          {{ getDim4Label(c.sentimento) }}
                        </v-chip>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
              </v-card>

              <!-- Tabela de Detalhamento dos Disparos Automáticos -->
              <v-card v-if="selectedReport?.stats?.disparos_automaticos?.length" variant="outlined" class="bg-surface">
                <v-card-item class="py-2">
                  <v-card-title class="text-subtitle-2 font-weight-bold d-flex align-center">
                    <v-icon start color="purple" size="small">mdi-bullhorn-outline</v-icon>
                    Disparos Automáticos Realizados no Período
                  </v-card-title>
                </v-card-item>
                <v-divider></v-divider>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th class="text-left">Campanha / Ação</th>
                      <th class="text-left">Endpoint</th>
                      <th class="text-left">Type ID</th>
                      <th class="text-right">Disparos (Lotes)</th>
                      <th class="text-right">Membros Atingidos</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(disp, idx) in selectedReport.stats.disparos_automaticos" :key="idx">
                      <td class="font-weight-medium">{{ disp.label }}</td>
                      <td><code>{{ disp.path }}</code></td>
                      <td><v-chip size="x-small" color="primary" variant="outlined">{{ disp.type_id }}</v-chip></td>
                      <td class="text-right font-weight-bold">{{ disp.total_dispatches }}</td>
                      <td class="text-right font-weight-bold text-purple">{{ disp.total_contacts }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </v-card>
            </v-window-item>

            <!-- TAB 2: PARECER PASTORAL QUALITATIVO (MARKDOWN RENDER) -->
            <v-window-item value="qualitativo">
              <v-card variant="outlined" class="bg-surface pa-5">
                <div v-if="selectedReport?.report_content" class="markdown-body" v-html="renderedReportMarkdown"></div>
                <v-alert v-else type="info" variant="tonal">
                  O conteúdo qualitativo do relatório ainda não foi gerado ou não há movimentações registradas para este período.
                </v-alert>
              </v-card>
            </v-window-item>

            <!-- TAB 3: JSON TÉCNICO / CRM -->
            <v-window-item value="crm_json">
              <v-card variant="outlined" class="bg-surface pa-4">
                <div class="d-flex align-center justify-space-between mb-3">
                  <div>
                    <div class="text-subtitle-2 font-weight-bold">
                      Estrutura JSON para Integração com CRM & Dashboards Basiléia
                    </div>
                    <div class="text-caption text-medium-emphasis">
                      Este payload é enviado via Webhook para a Igreja Local e alimenta os painéis analíticos do CRM.
                    </div>
                  </div>
                  <v-btn
                    color="primary"
                    prepend-icon="mdi-content-copy"
                    variant="tonal"
                    size="small"
                    @click="copyJsonToClipboard"
                  >
                    Copiar JSON para CRM
                  </v-btn>
                </div>
                <v-sheet
                  color="grey-darken-4"
                  rounded="lg"
                  class="pa-4 overflow-auto"
                  style="max-height: 480px; font-family: monospace; font-size: 13px; line-height: 1.5;"
                >
                  <pre>{{ formattedCrmJson }}</pre>
                </v-sheet>
              </v-card>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Feedback Toast -->
    <v-snackbar v-model="snackbar" :color="snackbarColor" timeout="2500" location="bottom right">
      {{ snackbarText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from '@/plugins/axios'
import { marked } from 'marked'

const churches = ref([])
const selectedChurch = ref(null)
const targetDate = ref(new Date().toISOString().substring(0, 10))
const periodType = ref('daily')
const periodOptions = [
  { title: 'Diário', value: 'daily' },
  { title: 'Semanal', value: 'weekly' },
  { title: 'Mensal', value: 'monthly' }
]

const reports = ref([])
const totalItems = ref(0)
const itemsPerPage = ref(10)
const loading = ref(false)
const generating = ref(false)
const dialog = ref(false)
const selectedReport = ref(null)
const activeTab = ref('quantitativo')

const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')

const headers = [
  { title: 'Data do Relatório', key: 'period_start', align: 'start' },
  { title: 'Tipo', key: 'period_type' },
  { title: 'Status', key: 'status' },
  { title: 'Ações', key: 'actions', sortable: false, align: 'end' }
]

// Computed helpers para dados quantitativos e relatórios
const quantData = computed(() => {
  return selectedReport.value?.stats?.relatorio_quantitativo || {}
})

const criticalCases = computed(() => {
  return selectedReport.value?.stats?.casos_criticos_detalhe || []
})

const hasDim1 = computed(() => {
  const d = quantData.value.dimensao_1_tipo_atendimento
  return d && Object.values(d).some(v => v > 0)
})

const hasDim2 = computed(() => {
  const d = quantData.value.dimensao_2_criticidade_pastoral
  return d && Object.values(d).some(v => v > 0)
})

const hasDim3 = computed(() => {
  const d = quantData.value.dimensao_3_vinculo
  return d && Object.values(d).some(v => v > 0)
})

const hasDim4 = computed(() => {
  const d = quantData.value.dimensao_4_sentimento
  return d && Object.values(d).some(v => v > 0)
})

const renderedReportMarkdown = computed(() => {
  const content = selectedReport.value?.report_content || ''
  try {
    return marked(content)
  } catch (e) {
    return content
  }
})

const formattedCrmJson = computed(() => {
  if (!selectedReport.value) return '{}'
  const rep = selectedReport.value
  const stats = rep.stats || {}
  const relQuant = stats.relatorio_quantitativo || {}
  const casosCriticos = stats.casos_criticos_detalhe || []
  const payload = {
    report_id: rep.id,
    church_id: rep.entity_id,
    church_name: rep.entity_name || 'Igreja Local',
    level: rep.level,
    period_type: rep.period_type,
    period_start: rep.period_start,
    period_end: rep.period_end,
    relatorio_quantitativo: relQuant,
    relatorio_qualitativo: rep.report_content || '',
    trafego_mensagens: relQuant.trafego_mensagens || stats.trafego_mensagens || {},
    funil_disparos: relQuant.funil_disparos || stats.funil_disparos || {},
    classificacao_analitica: {
      tipo_atendimento: relQuant.dimensao_1_tipo_atendimento || {},
      criticidade_pastoral: relQuant.dimensao_2_criticidade_pastoral || {},
      vinculo: relQuant.dimensao_3_vinculo || {},
      sentimento: relQuant.dimensao_4_sentimento || {}
    },
    radar_atencao_pastoral: casosCriticos,
    casos_criticos_detalhe: casosCriticos,
    stats: stats,
    report_content: rep.report_content || ''
  }
  return JSON.stringify(payload, null, 2)
})

const copyJsonToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(formattedCrmJson.value)
    snackbarText.value = 'JSON copiado para o CRM com sucesso!'
    snackbarColor.value = 'success'
    snackbar.value = true
  } catch (err) {
    snackbarText.value = 'Erro ao copiar JSON para a área de transferência.'
    snackbarColor.value = 'error'
    snackbar.value = true
  }
}

// Mapas de rótulos e cores das 4 dimensões
const dim1Labels = {
  visitante_novo: 'Visitante Novo',
  cadastro_identificacao: 'Cadastro / Identificação',
  duvida_cultos: 'Cultos & Horários',
  celulas_grupos: 'Células & Grupos',
  eventos_conferencias: 'Eventos & Conferências',
  cursos_ensino_batismo: 'Cursos & Batismo',
  financeiro_pix_dizimo: 'Financeiro (PIX / Dízimo)',
  informacao_institucional: 'Info Institucional / Endereço',
  voluntariado_servir: 'Voluntariado / Servir',
  confirmacao_dialogo: 'Confirmação / Respostas',
  saudacao_gratidao: 'Saudações & Agradecimentos',
  pedido_oracao_cuidado: 'Oração & Cuidado Pastoral',
  outros_especiais: 'Demandas Especiais'
}

const getDim1Label = (k) => dim1Labels[k] || k.replace(/_/g, ' ')
const getDim1Color = (k) => {
  const map = {
    visitante_novo: 'cyan',
    cadastro_identificacao: 'blue',
    duvida_cultos: 'indigo',
    celulas_grupos: 'deep-purple',
    eventos_conferencias: 'purple',
    cursos_ensino_batismo: 'teal',
    financeiro_pix_dizimo: 'green',
    informacao_institucional: 'light-blue',
    voluntariado_servir: 'orange',
    pedido_oracao_cuidado: 'pink',
    outros_especiais: 'amber'
  }
  return map[k] || 'grey'
}

const dim2Labels = {
  estavel_rotina: 'Rotina / Estável',
  oracao_intercessao: 'Oração & Intercessão',
  saude_enfermidade: 'Saúde & Enfermidade',
  luto_perda: 'Luto & Perda',
  crise_urgente: 'Crise Urgente',
  crise_familiar: 'Crise Familiar',
  afastamento_desanimo: 'Afastamento / Desânimo',
  conflito_reclamacao: 'Conflito / Reclamação'
}

const getDim2Label = (k) => dim2Labels[k] || k.replace(/_/g, ' ')
const getDim2Color = (k) => {
  const map = {
    estavel_rotina: 'grey',
    oracao_intercessao: 'info',
    saude_enfermidade: 'deep-orange',
    luto_perda: 'purple',
    crise_urgente: 'error',
    crise_familiar: 'warning',
    afastamento_desanimo: 'brown',
    conflito_reclamacao: 'red-accent-2'
  }
  return map[k] || 'grey'
}

const dim3Labels = {
  membro_ativo: 'Membro Ativo',
  visitante_novo: 'Visitante Novo',
  em_risco_afastado: 'Em Risco / Afastado'
}
const getDim3Label = (k) => dim3Labels[k] || k.replace(/_/g, ' ')
const getDim3Color = (k) => {
  const map = {
    membro_ativo: 'success',
    visitante_novo: 'cyan',
    em_risco_afastado: 'error'
  }
  return map[k] || 'grey'
}

const dim4Labels = {
  animado: 'Animado',
  acolhido: 'Acolhido',
  neutro: 'Neutro',
  duvidoso: 'Em Dúvida',
  frustrado: 'Frustrado',
  luto_triste: 'Luto / Triste'
}
const getDim4Label = (k) => dim4Labels[k] || k.replace(/_/g, ' ')
const getDim4Color = (k) => {
  const map = {
    animado: 'success',
    acolhido: 'primary',
    neutro: 'grey',
    duvidoso: 'warning',
    frustrado: 'error',
    luto_triste: 'purple'
  }
  return map[k] || 'grey'
}

const fetchChurches = async () => {
  try {
    const res = await axios.get(`/analytics/churches`)
    churches.value = res.data
    if (churches.value.length > 0) {
      selectedChurch.value = churches.value[0].id
      fetchReports()
    }
  } catch (error) {
    console.error('Error fetching churches', error)
  }
}

const fetchReports = async (options = {}) => {
  if (!selectedChurch.value) return
  
  const { page = 1, itemsPerPage: limit = 10 } = options
  const skip = (page - 1) * limit
  loading.value = true
  
  try {
    const res = await axios.get(`/analytics/reports`, {
      params: {
        level: 'church',
        period_type: periodType.value,
        entity_id: selectedChurch.value,
        skip,
        limit
      }
    })
    reports.value = res.data.reports
    totalItems.value = res.data.total
  } catch (error) {
    console.error('Error fetching reports', error)
  } finally {
    loading.value = false
  }
}

const generateManual = async () => {
  if (!selectedChurch.value) return
  generating.value = true
  try {
    const baseDate = targetDate.value ? new Date(targetDate.value + 'T12:00:00') : new Date()
    let start, end
    if (periodType.value === 'daily') {
      start = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate())
      end = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate(), 23, 59, 59)
    } else if (periodType.value === 'weekly') {
      const day = baseDate.getDay()
      start = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate() - day)
      end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6, 23, 59, 59)
    } else {
      start = new Date(baseDate.getFullYear(), baseDate.getMonth(), 1)
      end = new Date(baseDate.getFullYear(), baseDate.getMonth() + 1, 0, 23, 59, 59)
    }

    const churchObj = churches.value.find(c => c.id === selectedChurch.value)
    const churchName = churchObj ? churchObj.name : selectedChurch.value

    await axios.post(`/analytics/reports/generate`, {
      level: 'church',
      period_type: periodType.value,
      entity_id: selectedChurch.value,
      entity_name: churchName,
      start_time: start.toISOString(),
      end_time: end.toISOString()
    })
    
    setTimeout(() => fetchReports(), 1000)
  } catch (error) {
    console.error('Error generating report', error)
  } finally {
    generating.value = false
  }
}

const viewReport = (report) => {
  selectedReport.value = report
  activeTab.value = 'quantitativo'
  dialog.value = true
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return new Intl.DateTimeFormat('pt-BR', { 
    day: '2-digit', 
    month: 'long', 
    year: 'numeric' 
  }).format(date)
}

const getStatusColor = (status) => {
  const map = {
    'pending': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'error'
  }
  return map[status] || 'grey'
}

onMounted(() => {
  fetchChurches()
})

defineExpose({
  fetchReports
})
</script>

<style scoped>
.glass-card {
  background: rgba(20, 24, 40, 0.4) !important;
  border: 1px solid rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border-radius: 16px;
}

.markdown-body {
  font-size: 15px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.9);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 1.2rem;
  margin-bottom: 0.6rem;
  font-weight: 700;
  color: #fff;
}

.markdown-body :deep(p) {
  margin-bottom: 0.8rem;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin-left: 1.5rem;
  margin-bottom: 0.8rem;
}

.markdown-body :deep(li) {
  margin-bottom: 0.3rem;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--v-primary-base, #1976d2);
  padding-left: 1rem;
  font-style: italic;
  margin: 1rem 0;
  color: rgba(255, 255, 255, 0.7);
}
</style>
