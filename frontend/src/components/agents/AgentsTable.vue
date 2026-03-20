<template>
  <v-card class="agents-card glass-card">
    <v-card-title class="d-flex align-center px-6 py-4">
      <v-icon class="mr-2" color="primary">mdi-view-list</v-icon>
      <span class="text-white">{{ title }}</span>
      <v-spacer></v-spacer>
      <v-text-field
        v-model="searchQuery"
        density="compact"
        :placeholder="searchPlaceholder"
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        hide-details
        class="search-field"
        style="max-width: 300px"
        @update:model-value="$emit('update:search', $event)"
      ></v-text-field>
    </v-card-title>
    
    <v-divider></v-divider>
    
    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      :items-per-page="itemsPerPage"
      class="agents-table"
    >
      <template v-slot:item.name="{ item }">
        <slot name="item-name" :item="item">
          <div class="d-flex align-center py-2">
            <v-avatar :color="getLevelColor(item.access_level)" size="36" class="mr-3">
              <v-icon color="white" size="20">mdi-robot</v-icon>
            </v-avatar>
            <div>
              <span class="font-weight-medium">{{ item.name }}</span>
              <p class="text-caption text-medium-emphasis mb-0" v-if="item.description">
                {{ item.description?.substring(0, 50) }}{{ item.description?.length > 50 ? '...' : '' }}
              </p>
            </div>
          </div>
        </slot>
      </template>
      
      <template v-slot:item.access_level="{ item }">
        <slot name="item-level" :item="item">
          <v-chip :color="getLevelColor(item.access_level)" size="small" label>
            <v-icon start size="14">{{ getLevelIcon(item.access_level) }}</v-icon>
            {{ getLevelLabel(item.access_level) }}
          </v-chip>
        </slot>
      </template>
      
      <template v-slot:item.model="{ item }">
        <v-chip variant="outlined" size="small" color="grey">
          {{ item.model }}
        </v-chip>
      </template>
      
      <template v-slot:item.is_active="{ item }">
        <slot name="item-status" :item="item">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            <v-icon start size="14">{{ item.is_active ? 'mdi-check' : 'mdi-close' }}</v-icon>
            {{ item.is_active ? 'Ativo' : 'Inativo' }}
          </v-chip>
        </slot>
      </template>
      
      <template v-slot:item.collaboration_enabled="{ item }">
        <slot name="item-badges" :item="item">
          <div class="d-flex align-center gap-2">
            <v-tooltip :text="item.collaboration_enabled ? 'Colaboração ativa' : 'Colaboração desativada'">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" :color="item.collaboration_enabled ? 'success' : 'grey-lighten-1'" size="20">
                  {{ item.collaboration_enabled ? 'mdi-account-multiple-check' : 'mdi-account-multiple-remove' }}
                </v-icon>
              </template>
            </v-tooltip>
            
            <v-tooltip :text="item.vector_memory_enabled ? 'Memória Vetorial ativa' : 'Memória Vetorial desativada'">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" :color="item.vector_memory_enabled ? 'deep-purple' : 'grey-lighten-1'" size="20">
                  mdi-brain
                </v-icon>
              </template>
            </v-tooltip>
          </div>
        </slot>
      </template>
      
      <template v-slot:item.actions="{ item }">
        <slot name="item-actions" :item="item">
          <div class="d-flex gap-1">
            <v-btn icon variant="text" size="small" color="info" @click="$emit('collaborators', item)">
              <v-icon size="20">mdi-account-group</v-icon>
              <v-tooltip activator="parent" location="top">Colaboradores</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="secondary" @click="$emit('duplicate', item)">
              <v-icon size="20">mdi-content-copy</v-icon>
              <v-tooltip activator="parent" location="top">Duplicar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="primary" @click="$emit('edit', item)">
              <v-icon size="20">mdi-pencil</v-icon>
              <v-tooltip activator="parent" location="top">Editar</v-tooltip>
            </v-btn>
            <v-btn icon variant="text" size="small" color="error" @click="$emit('delete', item)">
              <v-icon size="20">mdi-delete</v-icon>
              <v-tooltip activator="parent" location="top">Excluir</v-tooltip>
            </v-btn>
          </div>
        </slot>
      </template>
      
      <template v-slot:no-data>
        <slot name="no-data">
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-robot-off-outline</v-icon>
            <p class="text-h6 text-medium-emphasis">Nenhum agente encontrado</p>
            <p class="text-body-2 text-medium-emphasis mb-4">Crie seu primeiro agente para começar</p>
            <v-btn color="primary" @click="$emit('create')">
              <v-icon start>mdi-plus</v-icon>
              Criar Agente
            </v-btn>
          </div>
        </slot>
      </template>
    </v-data-table>
  </v-card>
</template>

<script>
export default {
  name: 'AgentsTable',
  props: {
    title: {
      type: String,
      default: 'Lista de Agentes',
    },
    headers: {
      type: Array,
      required: true,
    },
    items: {
      type: Array,
      required: true,
    },
    loading: {
      type: Boolean,
      default: false,
    },
    itemsPerPage: {
      type: Number,
      default: 10,
    },
    searchPlaceholder: {
      type: String,
      default: 'Buscar agente...',
    },
  },
  emits: ['edit', 'delete', 'duplicate', 'collaborators', 'create', 'update:search'],
  setup(props, { emit }) {
    const getLevelColor = (level) => {
      const colors = {
        public: 'success',
        private: 'warning',
        premium: 'purple',
      }
      return colors[level] || 'grey'
    }

    const getLevelIcon = (level) => {
      const icons = {
        public: 'mdi-earth',
        private: 'mdi-lock',
        premium: 'mdi-crown',
      }
      return icons[level] || 'mdi-help-circle'
    }

    const getLevelLabel = (level) => {
      const labels = {
        public: 'Público',
        private: 'Privado',
        premium: 'Premium',
      }
      return labels[level] || level
    }

    return {
      getLevelColor,
      getLevelIcon,
      getLevelLabel,
    }
  },
}
</script>
