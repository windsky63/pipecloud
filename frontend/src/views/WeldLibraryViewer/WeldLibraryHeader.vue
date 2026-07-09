<script setup>
import PageHeader from '../../components/PageHeader.vue'

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
  <PageHeader :title="title" :description="description">
    <slot />
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>
  </PageHeader>
</template>
