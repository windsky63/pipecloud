<script setup>
import { t } from '../services/pipecloudState'

defineProps({
  text: {
    type: String,
    required: true,
  },
  location: {
    type: String,
    default: 'top',
  },
})
</script>

<template>
  <v-tooltip :location="location" max-width="360">
    <template #activator="{ props }">
      <v-btn
        v-bind="props"
        class="info-tooltip-button"
        icon="mdi-information-outline"
        size="x-small"
        variant="text"
        density="comfortable"
        :aria-label="t('viewDescription')"
      />
    </template>
    <span>{{ text }}</span>
  </v-tooltip>
</template>

<style scoped>
.info-tooltip-button {
  color: var(--muted);
  vertical-align: middle;
  background: transparent !important;
  box-shadow: none !important;
}

.info-tooltip-button :deep(.v-btn__overlay),
.info-tooltip-button :deep(.v-btn__underlay) {
  background: transparent !important;
  opacity: 0 !important;
}
</style>
