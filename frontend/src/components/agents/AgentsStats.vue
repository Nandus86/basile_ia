<template>
  <v-row class="mb-6">
    <v-col cols="12" md="3" v-for="(stat, i) in stats" :key="i">
      <v-card class="stat-card glass-card">
        <v-card-text class="d-flex align-center">
          <v-avatar class="mr-4 stat-avatar" size="48" :style="{ background: stat.iconBg }">
            <v-icon color="white">{{ stat.icon }}</v-icon>
          </v-avatar>
          <div>
            <p class="text-h4 font-weight-bold mb-0">{{ stat.value }}</p>
            <p class="text-caption text-medium-emphasis mb-0">{{ stat.label }}</p>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>

<script>
export default {
  name: 'AgentsStats',
  props: {
    stats: {
      type: Array,
      required: true,
    },
  },
}
</script>
