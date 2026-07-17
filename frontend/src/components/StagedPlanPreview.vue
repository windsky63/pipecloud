<script setup>
import { computed, ref, watch } from 'vue'
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
const expandedDates = ref([])

watch(fileGroups, (groups) => {
  const keys = groups.map((group) => group.key)
  expandedDates.value = expandedDates.value.filter((key) => keys.includes(key))
  if (!expandedDates.value.length && keys.length) {
    expandedDates.value = [keys.at(-1)]
  }
}, { immediate: true })

function typeIcon(type) {
  const text = String(type || '')
  if (text.includes('防腐') || text.includes('corrosion')) return 'mdi-shield-check-outline'
  if (text.includes('下料') || text.includes('cutting')) return 'mdi-content-cut'
  if (text.includes('焊接') || text.includes('welding')) return 'mdi-flash-outline'
  return 'mdi-folder-outline'
}
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

    <div class="preview-browser">
      <div class="preview-files">
        <v-expansion-panels v-if="fileGroups.length" v-model="expandedDates" multiple variant="accordion" class="date-panels">
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
                  <div v-if="groupByType" class="type-title">
                    <v-icon :icon="typeIcon(typeGroup.type)" size="15" />
                    <span>{{ typeGroup.type }}</span>
                    <small>{{ typeGroup.files.length }}</small>
                  </div>
                  <button
                    v-for="file in typeGroup.files"
                    :key="file.sourceKey || file.path"
                    :class="['file-button', { 'is-active': selectedPath === file.path }]"
                    type="button"
                    @click="emit('preview-file', file)"
                  >
                    <span class="file-icon"><v-icon icon="mdi-file-excel-outline" size="19" /></span>
                    <span class="file-copy">
                      <strong>{{ file.displayName || file.name }}</strong>
                      <small v-if="file.displayName && file.displayName !== file.name">{{ file.name }}</small>
                    </span>
                    <v-icon class="file-arrow" icon="mdi-chevron-right" size="17" />
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
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  gap: 18px;
  align-items: stretch;
  height: clamp(280px, 52vh, 480px);
  min-width: 0;
}

.preview-files,
.preview-data {
  min-width: 0;
}

.preview-files {
  height: 100%;
  padding: 10px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: color-mix(in srgb, var(--soft) 82%, var(--panel));
}

.date-panels {
  display: grid;
  gap: 8px;
  width: 100%;
}

.date-panels :deep(.v-expansion-panel) {
  width: 100%;
  margin-inline: 0;
  border: 1px solid var(--line);
  border-radius: 9px !important;
  background: var(--panel);
  color: var(--text);
  box-shadow: 0 2px 8px rgba(15, 23, 42, .04);
  overflow: hidden;
}

.date-panels :deep(.v-expansion-panel-title) {
  min-height: 58px;
  padding: 10px 13px;
}

.date-panels :deep(.v-expansion-panel-title--active) {
  color: #1d4ed8;
  background: color-mix(in srgb, #2563eb 7%, var(--panel));
}

.date-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 10px;
  border-top: 1px solid var(--line);
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

.date-title strong {
  color: var(--strong);
  font-size: 14px;
  letter-spacing: .01em;
}

.type-group.has-divider {
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.type-title {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.type-title small {
  display: grid;
  min-width: 22px;
  height: 20px;
  place-items: center;
  border-radius: 999px;
  background: color-mix(in srgb, #2563eb 10%, var(--panel));
  color: #2563eb;
  font-size: 10px;
}

.file-button {
  appearance: none;
  display: grid;
  position: relative;
  grid-template-columns: 34px minmax(0, 1fr) 18px;
  gap: 9px;
  align-items: center;
  width: 100%;
  min-height: 56px;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease, box-shadow .16s ease, transform .16s ease;
}

.file-button:hover,
.file-button.is-active {
  border-color: #7da4ff;
  background: color-mix(in srgb, #2563eb 9%, var(--panel));
  color: #1d4ed8;
  box-shadow: 0 5px 15px rgba(37, 99, 235, .12);
  transform: translateX(2px);
}

.file-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 7px;
  background: color-mix(in srgb, #16a34a 10%, var(--panel));
  color: #15803d;
}

.file-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.file-copy strong,
.file-copy small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-copy strong {
  color: var(--strong);
  font-size: 13px;
  font-weight: 700;
}

.file-copy small {
  color: var(--muted);
  font-size: 11px;
}

.file-arrow {
  color: #94a3b8;
  transition: transform .16s ease;
}

.file-button:hover .file-arrow,
.file-button.is-active .file-arrow {
  color: #2563eb;
  transform: translateX(2px);
}

.preview-data {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 4px 16px rgba(15, 23, 42, .04);
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
    height: auto;
  }

  .preview-files {
    height: min(340px, 48vh);
  }
}
</style>
