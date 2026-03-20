<template>
  <v-snackbar
    v-for="toast in toasts"
    :key="toast.id"
    :model-value="true"
    :color="toast.type"
    :timeout="5000"
    location="top right"
    class="toast-notification"
    @update:model-value="remove(toast.id)"
  >
    {{ toast.message }}
    <template #actions>
      <v-btn
        variant="text"
        @click="remove(toast.id)"
      >
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </template>
  </v-snackbar>
</template>

<script>
import { useToast } from '@/composables/useToast'

export default {
  setup() {
    const { toasts, remove } = useToast()
    
    return {
      toasts,
      remove,
    }
  },
}
</script>

<style scoped>
.toast-notification {
  margin-top: 60px;
}
</style>
