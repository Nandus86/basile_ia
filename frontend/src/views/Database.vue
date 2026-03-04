<template>
  <div>
    <h1 class="text-h4 font-weight-bold mb-6">Gerenciamento de Database</h1>

    <v-tabs v-model="tab" color="primary">
      <v-tab value="postgres">PostgreSQL</v-tab>
      <v-tab value="weaviate">Weaviate</v-tab>
    </v-tabs>

    <v-window v-model="tab" class="mt-4">
      <!-- PostgreSQL Tab -->
      <v-window-item value="postgres">
        <v-row>
          <v-col cols="12" md="4">
            <v-card>
              <v-card-title>Estatísticas</v-card-title>
              <v-card-text>
                <v-list density="compact">
                  <v-list-item>
                    <v-list-item-title>Database</v-list-item-title>
                    <template v-slot:append>{{ pgStats.database_name }}</template>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Tamanho</v-list-item-title>
                    <template v-slot:append>{{ pgStats.database_size }}</template>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Tabelas</v-list-item-title>
                    <template v-slot:append>{{ pgStats.table_count }}</template>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Conexões</v-list-item-title>
                    <template v-slot:append>{{ pgStats.connection_count }}</template>
                  </v-list-item>
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="8">
            <v-card>
              <v-card-title>Tabelas</v-card-title>
              <v-card-text>
                <v-list>
                  <v-list-item v-for="table in pgTables" :key="table.name">
                    <template v-slot:prepend>
                      <v-icon>mdi-table</v-icon>
                    </template>
                    <v-list-item-title>{{ table.name }}</v-list-item-title>
                    <template v-slot:append>{{ table.schema }}</template>
                  </v-list-item>
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <v-card class="mt-4">
          <v-card-title>Query Console (SELECT only)</v-card-title>
          <v-card-text>
            <v-textarea v-model="sqlQuery" label="SQL Query" rows="3" placeholder="SELECT * FROM agents LIMIT 10"></v-textarea>
            <v-btn color="primary" @click="executeQuery" :loading="queryLoading" class="mt-2">
              Executar
            </v-btn>
            <v-alert v-if="queryError" type="error" class="mt-4">{{ queryError }}</v-alert>
            <v-data-table v-if="queryResult.length" :headers="queryHeaders" :items="queryResult" class="mt-4"></v-data-table>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- Weaviate Tab -->
      <v-window-item value="weaviate">
        <v-row>
          <v-col cols="12" md="4">
            <v-card>
              <v-card-title>Estatísticas</v-card-title>
              <v-card-text>
                <v-list density="compact">
                  <v-list-item>
                    <v-list-item-title>Status</v-list-item-title>
                    <template v-slot:append>
                      <v-chip :color="wvStats.is_ready ? 'success' : 'error'" size="small">
                        {{ wvStats.is_ready ? 'Online' : 'Offline' }}
                      </v-chip>
                    </template>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Classes</v-list-item-title>
                    <template v-slot:append>{{ wvStats.class_count }}</template>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Objetos</v-list-item-title>
                    <template v-slot:append>{{ wvStats.total_objects }}</template>
                  </v-list-item>
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="8">
            <v-card>
              <v-card-title>Classes</v-card-title>
              <v-card-text>
                <v-list>
                  <v-list-item v-for="cls in wvClasses" :key="cls.name">
                    <template v-slot:prepend>
                      <v-icon>mdi-cube-outline</v-icon>
                    </template>
                    <v-list-item-title>{{ cls.name }}</v-list-item-title>
                    <template v-slot:append>
                      <v-chip size="small">{{ cls.object_count }} objetos</v-chip>
                      <v-btn icon variant="text" size="small" color="error" @click="purgeClass(cls.name)">
                        <v-icon>mdi-delete</v-icon>
                      </v-btn>
                    </template>
                  </v-list-item>
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <v-card class="mt-4">
          <v-card-title>Busca Vetorial</v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="4">
                <v-select v-model="searchClass" label="Classe" :items="wvClasses.map(c => c.name)"></v-select>
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="searchQuery" label="Query"></v-text-field>
              </v-col>
              <v-col cols="2">
                <v-btn color="primary" block @click="searchWeaviate" :loading="searchLoading">Buscar</v-btn>
              </v-col>
            </v-row>
            <v-list v-if="searchResults.length">
              <v-list-item v-for="(result, i) in searchResults" :key="i">
                <pre class="text-caption">{{ JSON.stringify(result, null, 2) }}</pre>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const tab = ref('postgres')

// PostgreSQL
const pgStats = ref({})
const pgTables = ref([])
const sqlQuery = ref('')
const queryResult = ref([])
const queryHeaders = ref([])
const queryLoading = ref(false)
const queryError = ref('')

// Weaviate
const wvStats = ref({})
const wvClasses = ref([])
const searchClass = ref('')
const searchQuery = ref('')
const searchResults = ref([])
const searchLoading = ref(false)

const fetchPgData = async () => {
  try {
    const [statsRes, tablesRes] = await Promise.all([
      axios.get('/api/database/postgres/stats'),
      axios.get('/api/database/postgres/tables')
    ])
    pgStats.value = statsRes.data
    pgTables.value = tablesRes.data.tables || []
  } catch (error) {
    console.error('Error:', error)
  }
}

const executeQuery = async () => {
  queryLoading.value = true
  queryError.value = ''
  queryResult.value = []
  try {
    const response = await axios.post('/api/database/postgres/query', { query: sqlQuery.value })
    if (response.data.success) {
      queryResult.value = response.data.rows
      queryHeaders.value = response.data.columns.map(c => ({ title: c, key: c }))
    } else {
      queryError.value = response.data.error
    }
  } catch (error) {
    queryError.value = error.message
  }
  queryLoading.value = false
}

const fetchWvData = async () => {
  try {
    const [statsRes, classesRes] = await Promise.all([
      axios.get('/api/database/weaviate/stats'),
      axios.get('/api/database/weaviate/classes')
    ])
    wvStats.value = statsRes.data
    wvClasses.value = classesRes.data.classes || []
  } catch (error) {
    console.error('Error:', error)
  }
}

const searchWeaviate = async () => {
  searchLoading.value = true
  try {
    const response = await axios.post('/api/database/weaviate/search', {
      class_name: searchClass.value,
      query: searchQuery.value,
      limit: 5
    })
    searchResults.value = response.data.results || []
  } catch (error) {
    console.error('Error:', error)
  }
  searchLoading.value = false
}

const purgeClass = async (className) => {
  if (confirm(`Tem certeza que deseja limpar a classe ${className}?`)) {
    try {
      await axios.delete(`/api/database/weaviate/purge/${className}`)
      fetchWvData()
    } catch (error) {
      console.error('Error:', error)
    }
  }
}

onMounted(() => {
  fetchPgData()
  fetchWvData()
})
</script>
