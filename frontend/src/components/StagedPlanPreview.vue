<script setup>
import { computed } from 'vue'
import DataVTable from './DataVTable.vue'
import { t } from '../services/pipecloudState'

const props = defineProps({
  stage: { type: Object, default: null },
  preview: { type: Object, default: () => ({}) },
  columns: { type: Array, default: () => [] },
  title: { type: String, required: true },
  saveLabel: { type: String, required: true },
  emptyText: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  saving: { type: Boolean, default: false },
  groupByType: { type: Boolean, default: false },
})

const emit = defineEmits(['preview-file', 'change-sheet', 'save'])

function formatPlanDate(value) {
  const text = String(value || '').trim()
  const compact = text.replaceAll('-', '')
  return compact.length === 8
    ? `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6)}`
    : (text || t('unselected'))
}

const fileGroups = computed(() => {
  const groups = new Map()
  const files = [...(props.stage?.files || [])].sort((left, right) => {
    const dateOrder = String(left.planDate || '').localeCompare(String(right.planDate || ''))
    if (dateOrder) return dateOrder
    return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN')
  })
  files.forEach((file) => {
    const rawDate = String(file.planDate || '').trim()
    const key = rawDate || 'undated'
    if (!groups.has(key)) groups.set(key, { key, date: formatPlanDate(rawDate), files: [] })
    groups.get(key).files.push(file)
  })
  return Array.from(groups.values()).map((group) => {
    const types = new Map()
    group.files.forEach((file) => {
      const type = String(file.planType || file.planName || file.planKey || '').trim() || '-'
      if (!types.has(type)) types.set(type, { type, files: [] })
      types.get(type).files.push(file)
    })
    return { ...group, typeGroups: Array.from(types.values()) }
  })
})

const selectedPath = computed(() => props.preview?.file?.path || '')
const previewKey = computed(() => [
  props.preview?.file?.sourceKey || props.preview?.file?.path || 'empty',
  props.preview?.sheet || '',
  props.columns.length,
  props.preview?.rows?.length || 0,
].join(':'))
</script>

<template>
  <div v-if="stage" class="staged-plan-preview">
    <div class="preview-head">
      <div>
        <h2>{{ title }}</h2>
        <span>{{ t('pendingStagedFiles', { count: stage.files?.length || 0 }) }}</span>
      </div>
      <v-btn
        color="primary"
        prepend-icon="mdi-content-save-outline"
        :loading="saving"
        :disabled="!stage.token || saving || loading"
        @click="emit('save')"
      >
        {{ saveLabel }}
      </v-btn>
    </div>

    <v-alert v-if="error" :text="error" type="error" density="compact" class="status-alert" />

    <div class="preview-browser">
      <div class="preview-files">
        <v-expansion-panels v-if="fileGroups.length" multiple variant="accordion" class="date-panels">
          <v-expansion-panel v-for="group in fileGroups" :key="group.key" :value="group.key">
            <v-expansion-panel-title>
              <div class="date-title">
                <strong>{{ group.date }}</strong>
                <span>{{ t('pendingStagedFiles', { count: group.files.length }) }}</span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div class="date-files">
                <section
                  v-for="(typeGroup, typeIndex) in group.typeGroups"
                  :key="`${group.key}:${typeGroup.type}`"
                  :class="['type-group', { 'has-divider': typeIndex > 0 }]"
                >
                  <div v-if="groupByType" class="type-title">{{ typeGroup.type }}</div>
                  <button
                    v-for="file in typeGroup.files"
                    :key="file.sourceKey || file.path"
                    :class="['file-button', { 'is-active': selectedPath === file.path }]"
                    type="button"
                    @click="emit('preview-file', file)"
                  >
                    <v-icon icon="mdi-file-table-outline" size="18" />
                    <span>{{ file.displayName || file.name }}</span>
                    <small v-if="file.displayName && file.displayName !== file.name">{{ file.name }}</small>
                  </button>
                </section>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
        <div v-else class="preview-empty">{{ t('noPendingStagedPlans') }}</div>
      </div>

      <div class="preview-data">
        <v-progress-linear v-if="loading" indeterminate color="primary" height="2" />
        <div v-if="preview.sheets?.length" class="preview-tabs">
          <v-tabs
            :model-value="preview.sheet"
            color="primary"
            @update:model-value="emit('change-sheet', $event)"
          >
            <v-tab v-for="sheet in preview.sheets" :key="sheet" :value="sheet">{{ sheet }}</v-tab>
          </v-tabs>
        </div>
        <div v-if="preview.file" class="library-meta">
          <span>{{ preview.file.displayName || preview.file.name || t('unselected') }}</span>
          <span>{{ t('currentSheet') }}：{{ preview.sheet || t('unselected') }}</span>
          <span>{{ t('totalRows') }}：{{ preview.total || 0 }}</span>
          <span>{{ t('columnCount') }}：{{ preview.columns?.length || 0 }}</span>
        </div>
        <DataVTable
          v-if="preview.file"
          :key="previewKey"
          :records="preview.rows || []"
          :columns="columns"
          :height="420"
          :empty-text="loading ? t('loading') : (emptyText || t('currentSheetNoData'))"
          filterable
        />
        <div v-else class="preview-empty">{{ t('selectPendingPlanFile') }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staged-plan-preview {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.preview-head {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.preview-head > div {
  display: grid;
  gap: 3px;
}

.preview-head h2 {
  margin: 0;
  color: var(--strong);
  font-size: 16px;
}

.preview-head span,
.date-title span {
  color: var(--muted);
  font-size: 12px;
}

.preview-browser {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  min-width: 0;
}

.preview-files,
.preview-data {
  min-width: 0;
}

.preview-files {
  height: clamp(280px, 52vh, 480px);
  padding-right: 5px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.date-panels {
  display: grid;
  gap: 8px;
}

.date-panels :deep(.v-expansion-panel) {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.date-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 0 0 8px;
}

.date-title,
.date-files,
.type-group {
  display: grid;
  gap: 8px;
}

.date-title {
  gap: 2px;
}

.type-group.has-divider {
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.type-title {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}

.file-button {
  appearance: none;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 3px 8px;
  align-items: center;
  width: 100%;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.file-button:hover,
.file-button.is-active {
  border-color: #93b4ff;
  background: #eaf1ff;
  color: #1d4ed8;
}

.file-button :deep(.v-icon) {
  grid-row: 1 / span 2;
  color: #64748b;
}

.file-button span,
.file-button small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-button span {
  color: var(--strong);
  font-size: 13px;
  font-weight: 700;
}

.file-button small {
  grid-column: 2;
  color: var(--muted);
  font-size: 11px;
}

.preview-data {
  display: grid;
  gap: 10px;
}

.preview-tabs {
  min-width: 0;
  overflow-x: auto;
}

.preview-empty {
  display: grid;
  min-height: 220px;
  place-items: center;
  border: 1px dashed var(--line);
  border-radius: 6px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 820px) {
  .preview-browser {
    grid-template-columns: minmax(0, 1fr);
  }

  .preview-files {
    height: min(340px, 48vh);
  }
}
</style>
