<script setup>
import { activeUiMessages, dismissUiMessage } from '../services/uiMessages'
import { t, uiMessagePosition } from '../services/pipecloudState'
</script>

<template>
  <transition-group name="message" tag="div" :class="['ui-message-center', `is-${uiMessagePosition}`]" aria-live="polite">
    <v-alert
      v-for="message in activeUiMessages"
      :key="message.id"
      :type="message.type"
      variant="tonal"
      density="comfortable"
      closable
      class="ui-message"
      @click:close="dismissUiMessage(message.id)"
    >
      <div class="ui-message-copy">
        <strong>{{ t(message.type === 'error' ? 'messageErrorTitle' : message.type === 'warning' ? 'messageWarningTitle' : message.type === 'success' ? 'messageSuccessTitle' : 'messageInfoTitle') }}</strong>
        <span>{{ message.text }}</span>
      </div>
    </v-alert>
  </transition-group>
</template>

<style scoped>
.ui-message-center {
  position: fixed;
  z-index: 2400;
  left: 50%;
  display: grid;
  width: min(720px, calc(100vw - 32px));
  gap: 8px;
  pointer-events: none;
  transform: translateX(-50%);
}

.ui-message-center.is-top { top: 14px; }
.ui-message-center.is-bottom { bottom: 14px; }

.ui-message {
  pointer-events: auto;
  border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel) 94%, transparent) !important;
  box-shadow: 0 14px 36px rgba(15, 23, 42, .16);
  backdrop-filter: blur(12px);
}

.ui-message-copy {
  display: grid;
  gap: 2px;
}

.ui-message-copy strong {
  font-size: 13px;
}

.ui-message-copy span {
  color: var(--text);
  font-size: 13px;
  line-height: 1.45;
}

.message-enter-active,
.message-leave-active {
  transition: opacity .2s ease, transform .2s ease;
}

.ui-message-center.is-top .message-enter-from,
.ui-message-center.is-top .message-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.ui-message-center.is-bottom .message-enter-from,
.ui-message-center.is-bottom .message-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
