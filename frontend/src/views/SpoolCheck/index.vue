<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchProjectSpools } from '../../api/projects'
import DataVTable from '../../components/DataVTable.vue'
import SpoolCheckHeader from './SpoolCheckHeader.vue'
import SpoolStructureViewer from './SpoolStructureViewer.vue'
import { t } from '../../services/pipecloudState'
import { selectedProjectId } from '../../services/projectState'

const allUnitsKey = '__all_units__'
const activeTab = ref('structure')
const loading = ref(false)
const structureLoading = ref(false)
const errorMessage = ref('')
const payload = ref(null)
const selectedSpoolNo = ref('')
const selectedUnit = ref(allUnitsKey)
const weldSource = ref('prefab')
const spoolModelCache = ref(new Map())
let spoolInfoController = null
let spoolInfoTimer = null
let spoolModelController = null
let spoolModelTimer = null
const weldSourceOptions = [
  { title: '预制焊口库', value: 'prefab' },
  { title: '初始化焊口库', value: 'initialization' },
]

const spools = computed(() => payload.value?.spools || [])
function spoolUnitValue(spool) {
  return spool.unitNo || t('unassignedUnit')
}

const unitOptions = computed(() => {
  const units = Array.from(new Set(spools.value.map((spool) => spoolUnitValue(spool))))
  return [
    { title: t('allUnits'), value: allUnitsKey },
    ...units.sort().map((unit) => ({ title: unit, value: unit })),
  ]
})
const filteredSpools = computed(() => {
  if (selectedUnit.value === allUnitsKey) return spools.value
  return spools.value.filter((spool) => spoolUnitValue(spool) === selectedUnit.value)
})
const selectedSpool = computed(() => {
  return filteredSpools.value.find((spool) => spool.spoolNo === selectedSpoolNo.value) || filteredSpools.value[0] || null
})

const spoolStats = computed(() => ({
  unitCount: selectedUnit.value === allUnitsKey
    ? new Set(spools.value.map((spool) => spoolUnitValue(spool))).size
    : 1,
  spoolCount: filteredSpools.value.length,
  welds: filteredSpools.value.reduce((total, spool) => total + Number(spool.weldCount || 0), 0),
  materials: filteredSpools.value.reduce((total, spool) => total + Number(spool.materialCount || 0), 0),
  issues: filteredSpools.value.reduce((total, spool) => total + Number(spool.issueCount || 0), 0),
}))

const materialColumns = computed(() => [
  { field: 'materialCode', title: t('materialCode'), width: 220 },
  { field: 'category', title: t('category'), width: 110 },
  { field: 'description', title: t('description'), width: 360 },
  { field: 'requiredText', title: t('required'), width: 120 },
  { field: 'stockText', title: t('stock'), width: 120 },
  { field: 'statusText', title: t('status'), width: 120 },
  { field: 'weldNosText', title: t('relatedWelds'), width: 220 },
])

const weldColumns = computed(() => [
  { field: 'finalWeldNo', title: t('weldNo'), width: 110 },
  { field: 'jointType', title: t('joint'), width: 90 },
  { field: 'weldingArea', title: t('area'), width: 90 },
  { field: 'inchDiameterText', title: t('inchDiameter'), width: 90 },
  { field: 'material', title: t('material'), width: 100 },
  { field: 'weldingMethod', title: t('method'), width: 110 },
  { field: 'completedText', title: t('completed'), width: 90 },
  { field: 'materialCode1', title: `${t('materialCode')}1`, width: 220 },
  { field: 'materialCode2', title: `${t('materialCode')}2`, width: 220 },
])

const materialRows = computed(() => {
  return (selectedSpool.value?.materials || []).map((material) => ({
    ...material,
    description: material.description || material.name || '-',
    requiredText: `${formatNumber(material.requiredQty)} ${material.unit || ''}`.trim(),
    stockText: `${formatNumber(material.stockQty)} ${material.unit || ''}`.trim(),
    statusText: material.inStock ? t('stockSatisfied') : t('shortage', { value: formatNumber(material.shortageQty) }),
    weldNosText: (material.weldNos || []).join(' / '),
  }))
})

const weldRows = computed(() => {
  return (selectedSpool.value?.welds || []).map((weld) => ({
    ...weld,
    finalWeldNo: weld.finalWeldNo || weld.initialWeldNo || '-',
    jointType: weld.jointType || '-',
    weldingArea: weld.weldingArea || '-',
    inchDiameterText: formatNumber(weld.inchDiameter),
    material: weld.material || '-',
    weldingMethod: weld.weldingMethod || '-',
    completedText: weld.completed ? t('yes') : t('no'),
  }))
})

async function loadSpoolInfo(options = {}) {
  if (spoolInfoTimer) {
    window.clearTimeout(spoolInfoTimer)
    spoolInfoTimer = null
  }
  spoolInfoController?.abort()
  spoolInfoController = null
  spoolModelController?.abort()
  spoolModelController = null
  if (spoolModelTimer) {
    window.clearTimeout(spoolModelTimer)
    spoolModelTimer = null
  }
  const controller = new AbortController()
  spoolInfoController = controller
  const projectId = selectedProjectId.value
  const source = weldSource.value
  if (!selectedProjectId.value) {
    payload.value = null
    selectedSpoolNo.value = ''
    errorMessage.value = t('selectProjectOnHome')
    spoolInfoController = null
    loading.value = false
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchProjectSpools(projectId, {
      weldSource: source,
      structureSpool: options.structureSpool,
      includeModel: false,
    }, {
      signal: controller.signal,
    })
    if (
      controller.signal.aborted
      || projectId !== selectedProjectId.value
      || source !== weldSource.value
    ) return
    payload.value = data
    spoolModelCache.value = new Map()
    if (!options.preserveSelection) {
      selectedUnit.value = allUnitsKey
      selectedSpoolNo.value = data.spools?.[0]?.spoolNo || ''
    } else if (options.structureSpool) {
      selectedSpoolNo.value = options.structureSpool
    }
    if (selectedSpoolNo.value) {
      loadSpoolModel(selectedSpoolNo.value)
    }
  } catch (error) {
    if (error?.name === 'AbortError') return
    payload.value = null
    selectedSpoolNo.value = ''
    errorMessage.value = t('spoolCheckReadFailed', { message: error.message })
  } finally {
    if (spoolInfoController === controller) {
      spoolInfoController = null
      loading.value = false
    }
  }
}

function scheduleSpoolInfoLoad(options = {}) {
  if (spoolInfoTimer) {
    window.clearTimeout(spoolInfoTimer)
  }
  spoolInfoController?.abort()
  spoolInfoController = null
  spoolModelController?.abort()
  spoolModelController = null
  if (spoolModelTimer) {
    window.clearTimeout(spoolModelTimer)
    spoolModelTimer = null
  }
  loading.value = true
  spoolInfoTimer = window.setTimeout(() => {
    spoolInfoTimer = null
    loadSpoolInfo(options)
  }, 150)
}

function spoolCacheKey(spoolNo) {
  return `${selectedProjectId.value || ''}|${weldSource.value}|${spoolNo || ''}`
}

function mergeSpoolDetail(spoolNo, detail, extraPayload = {}) {
  if (!payload.value || !detail) return
  payload.value = {
    ...payload.value,
    modelFile: extraPayload.modelFile || payload.value.modelFile,
    spools: (payload.value.spools || []).map((spool) => (
      spool.spoolNo === spoolNo
        ? { ...spool, ...detail, detailsLoaded: true, structureLoaded: true }
        : spool
    )),
  }
}

async function loadSpoolModel(spoolNo) {
  if (!selectedProjectId.value || !spoolNo) return
  if (spoolModelTimer) {
    window.clearTimeout(spoolModelTimer)
    spoolModelTimer = null
  }
  spoolModelController?.abort()
  const controller = new AbortController()
  spoolModelController = controller
  const projectId = selectedProjectId.value
  const source = weldSource.value
  const cacheKey = spoolCacheKey(spoolNo)
  const cached = spoolModelCache.value.get(cacheKey)
  if (cached) {
    mergeSpoolDetail(spoolNo, cached.detail, cached.payload)
    spoolModelController = null
    structureLoading.value = false
    return
  }
  structureLoading.value = true
  try {
    const data = await fetchProjectSpools(projectId, {
      weldSource: source,
      structureSpool: spoolNo,
      includeModel: true,
    }, {
      signal: controller.signal,
    })
    if (
      controller.signal.aborted
      || projectId !== selectedProjectId.value
      || source !== weldSource.value
      || spoolNo !== selectedSpoolNo.value
    ) return
    const detail = (data.spools || []).find((spool) => spool.spoolNo === spoolNo)
    if (detail) {
      spoolModelCache.value.set(cacheKey, { detail, payload: data })
      mergeSpoolDetail(spoolNo, detail, data)
    }
  } catch (error) {
    if (error?.name === 'AbortError') return
    errorMessage.value = t('spoolCheckReadFailed', { message: error.message })
  } finally {
    if (spoolModelController === controller) {
      spoolModelController = null
      structureLoading.value = false
    }
  }
}

function scheduleSpoolModelLoad(spoolNo) {
  if (spoolModelTimer) {
    window.clearTimeout(spoolModelTimer)
  }
  spoolModelController?.abort()
  spoolModelController = null
  structureLoading.value = true
  spoolModelTimer = window.setTimeout(() => {
    spoolModelTimer = null
    loadSpoolModel(spoolNo)
  }, 120)
}

function selectSpool(spool) {
  selectedSpoolNo.value = spool.spoolNo
  scheduleSpoolModelLoad(spool.spoolNo)
}

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return value || '-'
  return Number.isInteger(number) ? String(number) : number.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

onMounted(loadSpoolInfo)
watch(selectedProjectId, () => scheduleSpoolInfoLoad())
watch(weldSource, () => scheduleSpoolInfoLoad())
watch(selectedUnit, () => {
  const nextSpoolNo = filteredSpools.value[0]?.spoolNo || ''
  selectedSpoolNo.value = nextSpoolNo
  if (nextSpoolNo) {
    scheduleSpoolModelLoad(nextSpoolNo)
  }
})

onBeforeUnmount(() => {
  if (spoolInfoTimer) window.clearTimeout(spoolInfoTimer)
  if (spoolModelTimer) window.clearTimeout(spoolModelTimer)
  spoolInfoController?.abort()
  spoolModelController?.abort()
})
</script>

<template>
  <SpoolCheckHeader :title="t('spoolCheck')" :description="t('spoolCheckDescription')">
    <template #actions>
      <v-btn prepend-icon="mdi-refresh" :loading="loading" @click="loadSpoolInfo">{{ t('refresh') }}</v-btn>
      <v-btn color="primary" prepend-icon="mdi-source-branch-check" :disabled="!selectedSpool">
        {{ t('checkCurrentSpool') }}
      </v-btn>
    </template>
  </SpoolCheckHeader>

  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <v-sheet class="spool-check-shell" color="transparent">
    <v-card class="module-panel spool-list-panel" :loading="loading" :class="{ 'is-loading': loading }" variant="flat">
      <div class="section-head">
        <div>
          <h2>{{ t('spoolList') }}</h2>
          <span>{{ payload?.projectName || t('currentProject') }}</span>
        </div>
      </div>
      <v-select
        v-model="weldSource"
        :items="weldSourceOptions"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-database-switch-outline"
        class="spool-source-filter"
      />
      <v-select
        v-model="selectedUnit"
        :items="unitOptions"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-filter-outline"
        class="spool-unit-filter"
      />

      <div class="spool-list-summary">
        <div>
          <span>{{ t('unitCount') }}</span>
          <strong>{{ spoolStats.unitCount }}</strong>
        </div>
        <div>
          <span>{{ t('spoolCount') }}</span>
          <strong>{{ spoolStats.spoolCount }}</strong>
        </div>
        <div>
          <span>{{ t('weldCount') }}</span>
          <strong>{{ spoolStats.welds }}</strong>
        </div>
      </div>

      <div v-if="!spools.length && !loading" class="spool-empty-state">
        <v-icon icon="mdi-pipe-disconnected" size="38" />
        <strong>{{ t('noSpoolData') }}</strong>
        <span>{{ t('noSpoolDataHint') }}</span>
      </div>

      <div v-else class="spool-list">
        <button
          v-for="spool in filteredSpools"
          :key="spool.spoolNo"
          type="button"
          class="spool-list-item"
          :class="{ 'is-active': selectedSpool?.spoolNo === spool.spoolNo }"
          @click="selectSpool(spool)"
        >
          <div>
            <strong>{{ spool.lineNo || t('missingLineNo') }}</strong>
            <span>{{ spoolUnitValue(spool) }} / {{ t('originalSpoolCount', { count: spool.segmentCount || 0 }) }}</span>
          </div>
          <div class="spool-list-meta">
            <span>{{ spool.weldCount }} {{ t('welds') }}</span>
            <span :class="{ 'has-issues': spool.issueCount }">{{ t('issueCount', { count: spool.issueCount }) }}</span>
          </div>
        </button>
      </div>
    </v-card>

    <v-card class="module-panel spool-detail-panel" :loading="loading || structureLoading" variant="flat">
      <div class="spool-summary">
        <div>
          <span>{{ t('currentSpool') }}</span>
          <strong>{{ selectedSpool?.lineNo || t('unselected') }}</strong>
        </div>
        <div>
          <span>{{ t('unitNo') }}</span>
          <strong>{{ selectedSpool?.unitNo || '-' }}</strong>
        </div>
        <div>
          <span>{{ t('weldCount') }}</span>
          <strong>{{ selectedSpool?.weldCount || 0 }}</strong>
        </div>
        <div>
          <span>{{ t('issues') }}</span>
          <strong>{{ selectedSpool?.issueCount || 0 }}</strong>
        </div>
      </div>

      <div class="spool-toolbar">
        <div>
          <v-chip size="small" color="primary" variant="tonal">{{ payload?.source || 'database' }}</v-chip>
          <v-chip size="small" color="info" variant="tonal">
            {{ weldSourceOptions.find((item) => item.value === payload?.weldSource)?.title || weldSourceOptions.find((item) => item.value === weldSource)?.title }}
          </v-chip>
          <v-chip size="small" :color="selectedSpool?.modelMatchCount ? 'success' : 'warning'" variant="tonal">
            {{ structureLoading ? 'IDF加载中' : `IDF ${selectedSpool?.modelMatchCount || 0}` }}
          </v-chip>
          <v-chip size="small" :color="selectedSpool?.issueCount ? 'warning' : 'success'" variant="tonal">
            {{ selectedSpool?.issueCount ? t('needsAttention') : t('checkPassed') }}
          </v-chip>
        </div>
        <div>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-file-table-outline" :disabled="!payload?.files?.weldLibrary?.exists">
            {{ payload?.files?.weldLibrary?.exists ? t('weldLibraryReady') : t('weldLibraryMissing') }}
          </v-btn>
        </div>
      </div>

      <v-tabs v-model="activeTab" density="compact" color="primary" class="spool-tabs">
        <v-tab value="structure">{{ t('structure') }}</v-tab>
        <v-tab value="materials">{{ t('materials') }}</v-tab>
        <v-tab value="welds">{{ t('welds') }}</v-tab>
        <v-tab value="documentation">{{ t('documentation') }}</v-tab>
      </v-tabs>

      <v-window v-model="activeTab">
        <v-window-item value="structure">
          <SpoolStructureViewer :spool="selectedSpool" />
        </v-window-item>

        <v-window-item value="materials">
          <DataVTable
            class="spool-vtable"
            :records="materialRows"
            :columns="materialColumns"
            :height="560"
            :empty-text="t('noSpoolMaterials')"
          />
        </v-window-item>

        <v-window-item value="welds">
          <DataVTable
            class="spool-vtable"
            :records="weldRows"
            :columns="weldColumns"
            :height="560"
            :empty-text="t('noSpoolWelds')"
          />
        </v-window-item>

        <v-window-item value="documentation">
          <div class="spool-rules">
            <v-card class="spool-rule-card" variant="flat">
              <h2>{{ t('dataSource') }}</h2>
              <div class="spool-rule-line">{{ t('weldLibrary') }}：{{ payload?.files?.weldLibrary?.exists ? t('ready') : t('notFound') }}</div>
              <div class="spool-rule-line">IDF模型：{{ payload?.modelFile?.exists ? t('ready') : t('notFound') }}</div>
              <div class="spool-rule-line">{{ t('pipeLibrary') }}：{{ payload?.files?.pipeLibrary?.exists ? t('ready') : t('notFound') }}</div>
              <div class="spool-rule-line">{{ t('fittingLibrary') }}：{{ payload?.files?.fittingLibrary?.exists ? t('ready') : t('notFound') }}</div>
            </v-card>
            <v-card class="spool-rule-card" variant="flat">
              <h2>{{ t('checkOverview') }}</h2>
              <div v-if="selectedSpool?.issues?.length" class="spool-issue-list">
                <v-alert
                  v-for="issue in selectedSpool.issues"
                  :key="issue.message"
                  :type="issue.level === 'error' ? 'error' : 'warning'"
                  density="compact"
                  variant="tonal"
                >
                  {{ issue.message }}
                </v-alert>
              </div>
              <div v-else class="spool-rule-empty">{{ t('noSpoolIssues') }}</div>
            </v-card>
          </div>
        </v-window-item>
      </v-window>
    </v-card>
  </v-sheet>
</template>

<style scoped>
.spool-check-shell {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  gap: 16px;
}

.spool-list-panel,
.spool-detail-panel {
  position: relative;
  min-height: calc(100vh - 132px);
}

.spool-list-summary,
.spool-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.spool-summary {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.spool-list-summary > div,
.spool-summary > div {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.spool-list-summary span,
.spool-summary span,
.spool-list-summary strong,
.spool-summary strong {
  display: block;
}

.spool-list-summary span,
.spool-summary span {
  color: var(--muted);
  font-size: 12px;
}

.spool-list-summary strong,
.spool-summary strong {
  margin-top: 5px;
  color: var(--strong);
  font-size: 16px;
  overflow-wrap: anywhere;
}

.spool-empty-state {
  display: grid;
  min-height: 420px;
  align-content: center;
  justify-items: center;
  gap: 8px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
  color: var(--muted);
  text-align: center;
}

.spool-empty-state strong {
  color: var(--strong);
  font-size: 15px;
}

.spool-empty-state span {
  max-width: 320px;
  font-size: 13px;
  line-height: 1.6;
}

.spool-source-filter,
.spool-unit-filter {
  margin-bottom: 12px;
}

.spool-list {
  display: grid;
  gap: 8px;
  max-height: calc(100vh - 310px);
  overflow: auto;
}

.spool-list-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.spool-list-item.is-active {
  border-color: color-mix(in srgb, var(--primary) 62%, var(--line));
  background: color-mix(in srgb, var(--primary) 9%, var(--panel));
}

.spool-list-item strong,
.spool-list-item span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spool-list-item strong {
  color: var(--strong);
  font-size: 14px;
}

.spool-list-item span,
.spool-list-meta {
  color: var(--muted);
  font-size: 12px;
}

.spool-list-meta {
  display: grid;
  gap: 4px;
  justify-items: end;
}

.spool-list-meta .has-issues {
  color: #d97706;
  font-weight: 800;
}

.spool-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.spool-toolbar > div {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.spool-tabs {
  border-bottom: 1px solid var(--line);
}

.spool-vtable {
  margin-top: 16px;
}

.spool-rules {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}

.spool-rule-card {
  min-height: 118px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.spool-rules h2 {
  margin: 0 0 12px;
  color: var(--strong);
  font-size: 15px;
}

.spool-rule-line,
.spool-rule-empty {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.spool-issue-list {
  display: grid;
  gap: 8px;
}

@media (max-width: 1100px) {
  .spool-check-shell,
  .spool-rules {
    grid-template-columns: 1fr;
  }

  .spool-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
