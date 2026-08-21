<template>
  <div class="json-schema-tree d-flex flex-column h-100">
    <!-- Header / Controls -->
    <div class="pa-3 border-b bg-surface-variant d-flex flex-column gap-2">
      <div class="d-flex align-center justify-space-between">
        <div class="d-flex align-center">
          <v-icon color="purple-lighten-1" size="20" class="mr-2">mdi-code-json</v-icon>
          <span class="text-subtitle-2 font-weight-bold">Explorador de Dados</span>
          <v-chip v-if="sources.length > 1" size="x-small" color="purple" variant="tonal" class="ml-2">
            {{ sources.length }} origens
          </v-chip>
        </div>
        <div class="d-flex align-center gap-1">
          <v-btn
            icon
            size="x-small"
            variant="text"
            title="Expandir Tudo"
            @click="expandAll"
          >
            <v-icon size="16">mdi-unfold-more-horizontal</v-icon>
          </v-btn>
          <v-btn
            icon
            size="x-small"
            variant="text"
            title="Recolher Tudo"
            @click="collapseAll"
          >
            <v-icon size="16">mdi-unfold-less-horizontal</v-icon>
          </v-btn>
          <v-btn
            v-if="allowEditPayload"
            icon
            size="x-small"
            variant="text"
            :color="isEditingPayload ? 'primary' : undefined"
            title="Editar JSON de Teste"
            @click="isEditingPayload = !isEditingPayload"
          >
            <v-icon size="16">mdi-pencil-outline</v-icon>
          </v-btn>
        </div>
      </div>

      <!-- Search Input -->
      <v-text-field
        v-if="!isEditingPayload"
        v-model="searchQuery"
        placeholder="Buscar campo ou valor em todos os blocos..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="search-input"
      ></v-text-field>

      <!-- Section / Source Filter Tabs (if multiple sources) -->
      <div v-if="!isEditingPayload && sources.length > 1" class="sources-tabs-wrapper d-flex align-center gap-1 overflow-x-auto py-1">
        <v-chip
          size="x-small"
          :variant="selectedSourceId === 'all' ? 'flat' : 'outlined'"
          :color="selectedSourceId === 'all' ? 'purple' : undefined"
          class="cursor-pointer"
          @click="selectedSourceId = 'all'"
        >
          Todos ({{ sources.length }})
        </v-chip>
        <v-chip
          v-for="s in sources"
          :key="s.id"
          size="x-small"
          :variant="selectedSourceId === s.id ? 'flat' : 'outlined'"
          :color="selectedSourceId === s.id ? 'primary' : undefined"
          class="cursor-pointer text-truncate"
          style="max-width: 140px;"
          @click="selectedSourceId = s.id"
        >
          <v-icon start size="11" :color="s.color">{{ s.icon || 'mdi-cube-outline' }}</v-icon>
          {{ s.label }}
        </v-chip>
      </div>

      <div v-if="!isEditingPayload" class="text-caption text-medium-emphasis d-flex align-center" style="font-size: 11px;">
        <v-icon size="13" class="mr-1 text-primary">mdi-drag</v-icon>
        <span>Arraste o campo ou clique em <v-icon size="11">mdi-content-copy</v-icon> para inserir a tag.</span>
      </div>
    </div>

    <!-- Edit Test Payload Area -->
    <div v-if="isEditingPayload" class="pa-3 flex-grow-1 d-flex flex-column bg-surface overflow-hidden">
      <div class="text-caption text-medium-emphasis mb-2">
        Cole ou edite o JSON de entrada para gerar a árvore de variáveis do gatilho:
      </div>
      <v-textarea
        v-model="rawPayloadString"
        variant="outlined"
        density="compact"
        rows="12"
        hide-details
        class="font-monospace text-caption flex-grow-1"
        style="font-family: monospace;"
        placeholder="{ ... }"
      ></v-textarea>
      <div class="d-flex justify-end gap-2 mt-3">
        <v-btn size="small" variant="text" @click="isEditingPayload = false">Cancelar</v-btn>
        <v-btn size="small" color="primary" @click="applyRawPayload">Salvar & Analisar</v-btn>
      </div>
    </div>

    <!-- Multi-Source Tree Content -->
    <div v-else class="tree-content pa-2 flex-grow-1 overflow-y-auto bg-surface">
      <div v-if="visibleSections.length === 0" class="text-center pa-6 text-medium-emphasis text-caption">
        <v-icon size="36" color="grey" class="mb-2">mdi-database-search-outline</v-icon>
        <div>Nenhum dado encontrado nos blocos ou no payload.</div>
        <v-btn size="small" variant="outlined" color="primary" class="mt-3" @click="isEditingPayload = true">
          <v-icon start size="14">mdi-plus</v-icon> Informar Payload de Teste
        </v-btn>
      </div>

      <div v-else class="sections-list d-flex flex-column gap-3">
        <div
          v-for="section in visibleSections"
          :key="section.id"
          class="source-section-card rounded border bg-surface-variant overflow-hidden"
        >
          <!-- Section Header -->
          <div
            class="section-header pa-2 d-flex align-center justify-space-between cursor-pointer"
            :style="{ borderLeft: `3px solid ${section.color || '#6366F1'}` }"
            @click="toggleSectionCollapse(section.id)"
          >
            <div class="d-flex align-center overflow-hidden mr-2">
              <v-icon
                size="14"
                class="mr-1 text-medium-emphasis"
                :style="{ transform: isSectionOpen(section.id) ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s ease' }"
              >
                mdi-chevron-right
              </v-icon>
              <v-icon size="16" :color="section.color" class="mr-1">{{ section.icon || 'mdi-cube-outline' }}</v-icon>
              <span class="font-weight-bold text-caption text-truncate mr-1">{{ section.label }}</span>
              <code class="text-caption text-disabled" style="font-size: 10px;">{{ section.sublabel || section.rootPrefix }}</code>
            </div>
            <div class="d-flex align-center gap-1">
              <v-chip v-if="section.duration_ms !== undefined" size="x-small" variant="text" class="text-caption text-medium-emphasis" style="font-size: 9px;">
                {{ section.duration_ms }}ms
              </v-chip>
              <v-icon v-if="section.status === 'success'" size="14" color="success">mdi-check-circle</v-icon>
              <v-icon v-else-if="section.status === 'failed'" size="14" color="error">mdi-alert-circle</v-icon>
            </div>
          </div>

          <!-- Section Tree Nodes -->
          <div v-if="isSectionOpen(section.id)" class="section-nodes-body pa-2 bg-surface border-t">
            <div v-if="section.nodes.length === 0" class="pa-2 text-caption text-disabled text-center">
              Nenhum dado retornado neste bloco.
            </div>
            <json-tree-node
              v-for="node in section.nodes"
              :key="node.fullPath"
              :node="node"
              :search-query="searchQuery"
              @copy="onCopyTag"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Toast Copy Feedback -->
    <v-snackbar v-model="showCopySnackbar" timeout="2000" color="success" location="bottom right">
      <v-icon start size="16">mdi-check-circle</v-icon>
      Copiado: <code>{{ copiedText }}</code>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, watch, defineComponent, h } from 'vue'

const props = defineProps({
  // Direct payload mode (legacy / single root)
  payload: {
    type: Object,
    default: () => ({})
  },
  rootPrefix: {
    type: String,
    default: '$trigger.payload'
  },
  // Multi-source array of executed blocks and trigger data
  sources: {
    type: Array,
    default: () => []
  },
  allowEditPayload: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:payload', 'copy'])

const searchQuery = ref('')
const selectedSourceId = ref('all')
const isEditingPayload = ref(false)
const rawPayloadString = ref('')
const showCopySnackbar = ref(false)
const copiedText = ref('')
const expandedMap = ref({})
const collapsedSections = ref({})

// Initialize raw payload string from trigger data
watch(() => [props.payload, props.sources], () => {
  const triggerSource = props.sources.find(s => s.id === 'trigger')
  const srcPayload = triggerSource ? triggerSource.data : props.payload
  if (srcPayload) {
    rawPayloadString.value = JSON.stringify(srcPayload, null, 2)
  }
}, { immediate: true, deep: true })

function applyRawPayload() {
  try {
    const parsed = JSON.parse(rawPayloadString.value)
    emit('update:payload', parsed)
    isEditingPayload.value = false
  } catch (err) {
    alert('JSON inválido: ' + err.message)
  }
}

// Build Tree Node Hierarchy for a given data object
function buildTree(obj, parentPath, depth = 0) {
  if (obj === null || obj === undefined) return []

  const nodes = []
  if (typeof obj === 'object') {
    const isArray = Array.isArray(obj)
    const keys = Object.keys(obj)

    for (const key of keys) {
      const val = obj[key]
      const fullPath = `${parentPath}.${key}`
      const type = getDataType(val)
      const isComplex = type === 'object' || type === 'array'

      const node = {
        key,
        fullPath,
        templatePath: `{{ ${fullPath} }}`,
        value: val,
        type,
        depth,
        isComplex,
        children: isComplex ? buildTree(val, fullPath, depth + 1) : []
      }
      nodes.push(node)
    }
  } else {
    // Primitive root
    nodes.push({
      key: 'value',
      fullPath: parentPath,
      templatePath: `{{ ${parentPath} }}`,
      value: obj,
      type: getDataType(obj),
      depth: 0,
      isComplex: false,
      children: []
    })
  }
  return nodes
}

function getDataType(val) {
  if (val === null) return 'null'
  if (Array.isArray(val)) return 'array'
  if (typeof val === 'object') return 'object'
  if (typeof val === 'number') return 'number'
  if (typeof val === 'boolean') return 'boolean'
  return 'string'
}

function filterNodes(nodes, query) {
  if (!query) return nodes
  const q = query.toLowerCase()
  const result = []

  for (const node of nodes) {
    const keyMatch = node.key.toLowerCase().includes(q)
    const valMatch = typeof node.value !== 'object' && String(node.value).toLowerCase().includes(q)
    const pathMatch = node.fullPath.toLowerCase().includes(q)

    let matchingChildren = []
    if (node.children && node.children.length > 0) {
      matchingChildren = filterNodes(node.children, query)
    }

    if (keyMatch || valMatch || pathMatch || matchingChildren.length > 0) {
      result.push({
        ...node,
        children: matchingChildren.length > 0 ? matchingChildren : node.children
      })
    }
  }
  return result
}

// Compute normalized active sections
const allSections = computed(() => {
  if (props.sources && props.sources.length > 0) {
    return props.sources.map(src => {
      const rawNodes = buildTree(src.data, src.rootPrefix || `$${src.id}`, 0)
      return {
        id: src.id,
        label: src.label,
        sublabel: src.sublabel || src.rootPrefix,
        icon: src.icon,
        color: src.color,
        rootPrefix: src.rootPrefix,
        status: src.status,
        duration_ms: src.duration_ms,
        nodes: filterNodes(rawNodes, searchQuery.value)
      }
    })
  }

  // Fallback to single payload prop
  const rawNodes = buildTree(props.payload, props.rootPrefix, 0)
  return [{
    id: 'trigger',
    label: 'Gatilho de Entrada',
    sublabel: props.rootPrefix,
    icon: 'mdi-lightning-bolt',
    color: '#F59E0B',
    rootPrefix: props.rootPrefix,
    nodes: filterNodes(rawNodes, searchQuery.value)
  }]
})

const visibleSections = computed(() => {
  let list = allSections.value
  if (selectedSourceId.value !== 'all') {
    list = list.filter(s => s.id === selectedSourceId.value)
  }
  if (searchQuery.value) {
    list = list.filter(s => s.nodes.length > 0)
  }
  return list
})

function isSectionOpen(sectionId) {
  if (searchQuery.value) return true
  return collapsedSections.value[sectionId] !== true
}

function toggleSectionCollapse(sectionId) {
  collapsedSections.value[sectionId] = !collapsedSections.value[sectionId]
}

function expandAll() {
  collapsedSections.value = {}
  function setExpand(nodes, val) {
    for (const n of nodes) {
      expandedMap.value[n.fullPath] = val
      if (n.children && n.children.length > 0) {
        setExpand(n.children, val)
      }
    }
  }
  for (const s of allSections.value) {
    setExpand(s.nodes, true)
  }
}

function collapseAll() {
  expandedMap.value = {}
}

function onCopyTag(tag) {
  navigator.clipboard.writeText(tag)
  copiedText.value = tag
  showCopySnackbar.value = true
  emit('copy', tag)
}

// ── Recursive Node Sub-Component ──
const JsonTreeNode = defineComponent({
  name: 'JsonTreeNode',
  props: {
    node: { type: Object, required: true },
    searchQuery: { type: String, default: '' }
  },
  emits: ['copy'],
  setup(nodeProps, { emit: subEmit }) {
    const isExpanded = computed({
      get: () => {
        if (nodeProps.searchQuery) return true
        return expandedMap.value[nodeProps.node.fullPath] ?? false
      },
      set: (v) => {
        expandedMap.value[nodeProps.node.fullPath] = v
      }
    })

    function toggleExpand() {
      if (nodeProps.node.isComplex) {
        isExpanded.value = !isExpanded.value
      }
    }

    function onDragStart(event) {
      event.dataTransfer.setData('text/plain', nodeProps.node.templatePath)
      event.dataTransfer.setData('application/json', JSON.stringify({
        path: nodeProps.node.fullPath,
        template: nodeProps.node.templatePath,
        type: nodeProps.node.type,
        value: nodeProps.node.value
      }))
      event.dataTransfer.effectAllowed = 'copy'
    }

    function getTypeColor(type) {
      switch (type) {
        case 'string': return '#10B981'
        case 'number': return '#3B82F6'
        case 'boolean': return '#EC4899'
        case 'array': return '#8B5CF6'
        case 'object': return '#F59E0B'
        default: return '#6B7280'
      }
    }

    function formatValuePreview(val, type) {
      if (type === 'null') return 'null'
      if (type === 'array') return `[${val.length} itens]`
      if (type === 'object') return `{${Object.keys(val).length} chaves}`
      if (type === 'string') return `"${val.length > 30 ? val.substring(0, 27) + '...' : val}"`
      return String(val)
    }

    return () => {
      const { node } = nodeProps
      const typeColor = getTypeColor(node.type)
      const paddingLeft = `${node.depth * 14 + 6}px`

      return h('div', { class: 'tree-node-wrapper' }, [
        h('div', {
          class: ['tree-node-row d-flex align-center justify-space-between py-1 px-1 rounded', { 'is-complex': node.isComplex }],
          style: { paddingLeft },
          draggable: true,
          onDragstart: onDragStart,
          title: `Arrastar ${node.templatePath}`
        }, [
          // Left: Arrow + Drag Icon + Key + Value
          h('div', {
            class: 'd-flex align-center overflow-hidden flex-grow-1 mr-1 cursor-pointer',
            onClick: toggleExpand
          }, [
            // Expand/Collapse icon
            node.isComplex
              ? h('v-icon', {
                  size: 14,
                  class: 'mr-1 text-medium-emphasis',
                  style: { transform: isExpanded.value ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s ease' }
                }, () => 'mdi-chevron-right')
              : h('span', { style: { width: '18px', display: 'inline-block' } }),

            // Drag handle
            h('v-icon', {
              size: 13,
              class: 'drag-handle mr-1 text-disabled',
              title: 'Arrastar campo'
            }, () => 'mdi-drag'),

            // Type Badge
            h('span', {
              class: 'type-badge text-caption px-1 mr-1 font-weight-bold',
              style: {
                color: typeColor,
                backgroundColor: `${typeColor}18`,
                borderRadius: '3px',
                fontSize: '10px',
                lineHeight: '14px',
                display: 'inline-block'
              }
            }, node.type.substring(0, 3).toUpperCase()),

            // Key Name
            h('span', {
              class: 'node-key font-weight-medium text-caption mr-1',
              style: { color: '#E2E8F0', whiteSpace: 'nowrap' }
            }, `${node.key}:`),

            // Value Preview
            h('span', {
              class: 'node-val text-caption text-truncate',
              style: { color: '#94A3B8', fontSize: '11px' }
            }, formatValuePreview(node.value, node.type))
          ]),

          // Right: Copy Tag Button
          h('v-btn', {
            icon: true,
            size: 'x-small',
            variant: 'text',
            class: 'copy-btn ml-1',
            title: `Copiar ${node.templatePath}`,
            onClick: (e) => {
              e.stopPropagation()
              subEmit('copy', node.templatePath)
            }
          }, () => h('v-icon', { size: 13, color: 'primary' }, () => 'mdi-content-copy'))
        ]),

        // Children (if expanded)
        node.isComplex && isExpanded.value && node.children && node.children.length > 0
          ? h('div', { class: 'tree-children' },
              node.children.map(child =>
                h(JsonTreeNode, {
                  key: child.fullPath,
                  node: child,
                  searchQuery: nodeProps.searchQuery,
                  onCopy: (t) => subEmit('copy', t)
                })
              )
            )
          : null
      ])
    }
  }
})
</script>

<style scoped>
.json-schema-tree {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  user-select: none;
}

.sources-tabs-wrapper::-webkit-scrollbar {
  height: 3px;
}

.sources-tabs-wrapper::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

.tree-node-row {
  transition: background-color 0.15s ease;
  border: 1px solid transparent;
}

.tree-node-row:hover {
  background-color: rgba(139, 92, 246, 0.1) !important;
  border-color: rgba(139, 92, 246, 0.2);
}

.tree-node-row:hover .drag-handle {
  color: #A78BFA !important;
}

.tree-node-row:active {
  cursor: grabbing;
  opacity: 0.7;
}

.cursor-pointer {
  cursor: pointer;
}

.drag-handle {
  cursor: grab;
}

.copy-btn {
  opacity: 0.4;
  transition: opacity 0.15s ease;
}

.tree-node-row:hover .copy-btn {
  opacity: 1;
}

.search-input :deep(.v-field__input) {
  font-size: 12px;
  min-height: 32px;
  padding-top: 4px;
  padding-bottom: 4px;
}
</style>
