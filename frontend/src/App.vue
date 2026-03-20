<template>
  <v-app>
    <router-view />
    <ToastNotifications />
  </v-app>
</template>

<script setup>
import ToastNotifications from '@/components/ToastNotifications.vue'
</script>

<style>
html {
  overflow-y: auto !important;
}
</style>
