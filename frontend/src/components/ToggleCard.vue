<template>
  <v-card variant="outlined" :class="['toggle-card', { 'has-color': color }]">
    <v-card-text class="pt-4 pb-4">
      <slot></slot>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  name: 'ToggleCard',
  props: {
    color: {
      type: String,
      default: '',
    },
  },
}
</script>

<style scoped>
.toggle-card {
  transition: all 0.2s ease;
}

.toggle-card:hover {
  border-color: rgba(157, 78, 221, 0.3);
}

.toggle-card.has-color {
  border-color: rgba(157, 78, 221, 0.4);
}
</style>
