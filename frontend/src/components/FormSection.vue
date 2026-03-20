<template>
  <div class="form-section">
    <div v-if="title || icon" class="section-header mb-3">
      <h3 class="text-subtitle-2 font-weight-medium text-medium-emphasis d-flex align-center">
        <v-icon v-if="icon" :size="18" class="mr-2">{{ icon }}</v-icon>
        {{ title }}
      </h3>
      <v-divider v-if="divider" class="mt-2"></v-divider>
    </div>
    <slot></slot>
  </div>
</template>

<script>
export default {
  name: 'FormSection',
  props: {
    title: {
      type: String,
      default: '',
    },
    icon: {
      type: String,
      default: '',
    },
    divider: {
      type: Boolean,
      default: true,
    },
  },
}
</script>

<style scoped>
.form-section {
  margin-bottom: 1rem;
}

.section-header {
  padding-top: 0.5rem;
}
</style>
