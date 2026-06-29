<script setup>
import { ref } from 'vue'
import { t } from '../services/pipecloudState'

const dialog = ref(false)
const options = ref({
  title: t('unsyncedEditTitle'),
  text: t('unsavedLeaveConfirm'),
  confirmText: t('continueDiscard'),
  color: 'warning',
})
let resolver = null

function open(customOptions = {}) {
  options.value = {
    title: t('unsyncedEditTitle'),
    text: t('unsavedLeaveConfirm'),
    confirmText: t('continueDiscard'),
    color: 'warning',
    ...customOptions,
  }
  dialog.value = true
  return new Promise((resolve) => {
    resolver = resolve
  })
}

function close(result) {
  const resolve = resolver
  dialog.value = false
  resolver = null
  resolve?.(result)
}

defineExpose({
  open,
  close,
})
</script>

<template>
  <v-dialog v-model="dialog" max-width="420" persistent>
    <v-card>
      <v-card-title>{{ options.title }}</v-card-title>
      <v-card-text>{{ options.text }}</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close(false)">{{ t('cancel') }}</v-btn>
        <v-btn :color="options.color" variant="flat" @click="close(true)">
          {{ options.confirmText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
