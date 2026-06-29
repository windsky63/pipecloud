<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <header class="page-header">
    <div>
      <div class="page-title-row">
        <h1>{{ title }}</h1>
        <InfoTooltip v-if="description" :text="description" location="bottom" />
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}

.page-header h1 {
  margin: 0;
  font-size: 26px;
  letter-spacing: 0;
}

.page-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.page-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

@media (max-width: 1400px) {
  .page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .page-header-actions {
    width: 100%;
  }
}
</style>
