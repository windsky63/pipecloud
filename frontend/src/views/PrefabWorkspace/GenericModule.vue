<script setup>
import InfoTooltip from '../../components/InfoTooltip.vue'
import { localizedActionName, localizedModuleDescription } from '../../services/navigationLabels'
import { t } from '../../services/pipecloudState'

defineProps({
  activeModule: { type: Object, required: true },
  activeModuleTitle: { type: String, required: true },
  runningKey: { type: String, default: '' },
})

defineEmits(['execute-action'])
</script>

<template>
  <v-card class="module-panel">
    <div class="section-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ activeModuleTitle }}</h2>
          <InfoTooltip :text="localizedModuleDescription(activeModule)" />
        </div>
      </div>
    </div>

    <div class="module-actions">
      <v-btn
        v-for="action in activeModule.actions"
        :key="action.key"
        color="primary"
        variant="tonal"
        :loading="runningKey === action.key"
        @click="$emit('execute-action', action.key)"
      >
        {{ localizedActionName(action) }}
      </v-btn>
    </div>
  </v-card>
</template>
