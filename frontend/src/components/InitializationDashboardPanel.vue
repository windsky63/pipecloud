<script setup>
import { computed, ref } from 'vue'
import DataVTable from './DataVTable.vue'
import { t } from '../services/pipecloudState'

const props = defineProps({
  dashboard: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
  showRefresh: {
    type: Boolean,
    default: false,
  },
  collapsible: {
    type: Boolean,
    default: false,
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
  panel: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['refresh', 'toggle'])
const activeView = ref('data')

const viewItems = computed(() => [
  { value: 'data', label: t('dashboardDataView'), icon: 'mdi-view-dashboard-outline' },
  { value: 'table', label: t('dashboardTableView'), icon: 'mdi-table' },
  { value: 'source', label: t('dashboardSourceView'), icon: 'mdi-file-table-outline' },
])

const unitTableColumns = computed(() => [
  { field: 'unit', title: t('unitNo'), width: 140 },
  { field: 'totalWeldCount', title: t('fieldWeldCount'), width: 120 },
  { field: 'prefabWeldCount', title: t('prefabWeldCount'), width: 130 },
  { field: 'prefabRateText', title: t('prefabRate'), width: 130 },
  { field: 'autoWeldCount', title: t('autoWeldCount'), width: 120 },
  { field: 'autoRateText', title: t('autoWeldRate'), width: 130 },
])

const sourceTableColumns = computed(() => [
  { field: 'label', title: t('dataItem'), width: 120 },
  { field: 'path', title: t('filePath'), width: 520 },
])

const unitRows = computed(() => {
  return (props.dashboard.units || []).map((row) => ({
    ...row,
    prefabRateText: formatPercent(row.prefabRate),
    autoRateText: formatPercent(row.autoRate),
  }))
})

const sourceRows = computed(() => [
  { label: t('fieldWelds'), path: props.dashboard.sources?.total?.path || '-' },
  { label: t('prefabWelds'), path: props.dashboard.sources?.prefab?.path || '-' },
  { label: t('autoWelds'), path: props.dashboard.sources?.auto?.path || '-' },
])

function formatPercent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0%'
  return `${number.toFixed(number % 1 === 0 ? 0 : 2)}%`
}
</script>

<template>
  <component
    :is="panel ? 'v-card' : 'div'"
    class="initialization-dashboard-panel"
    :class="{ 'module-panel': panel }"
    v-bind="panel ? { loading, variant: 'flat' } : {}"
  >
    <div v-if="title || showRefresh || collapsible || !collapsed" class="section-head initialization-dashboard-head">
      <div>
        <div class="section-title-with-tip">
          <h2>{{ title }}</h2>
          <InfoTooltip v-if="description" :text="description" />
        </div>
      </div>
      <div class="initialization-dashboard-actions">
        <v-btn-toggle
          v-if="!collapsed"
          v-model="activeView"
          class="dashboard-icon-toggle"
          mandatory
          density="compact"
          color="primary"
          variant="text"
        >
          <v-btn
            v-for="item in viewItems"
            :key="item.value"
            :value="item.value"
            :icon="item.icon"
            variant="text"
            :aria-label="item.label"
            :title="item.label"
          />
        </v-btn-toggle>
        <span
          v-if="!collapsed && (showRefresh || collapsible)"
          class="dashboard-action-divider"
          aria-hidden="true"
        />
        <slot name="header-extra" />
        <v-btn
          v-if="showRefresh"
          :loading="loading"
          icon="mdi-refresh"
          variant="text"
          :aria-label="t('refreshStats')"
          :title="t('refreshStats')"
          @click="emit('refresh')"
        />
        <v-btn
          v-if="collapsible"
          :icon="collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
          variant="text"
          :aria-label="collapsed ? t('expandDashboard') : t('collapseDashboard')"
          @click="emit('toggle')"
        />
      </div>
    </div>

    <slot name="actions" />

    <template v-if="!collapsed">
      <v-alert v-if="error" :text="error" type="error" density="compact" class="status-alert" />

      <template v-if="activeView === 'data'">
        <v-sheet class="initialization-stats" color="transparent">
          <div class="initialization-stat-card is-prefab">
            <span>{{ t('prefabVsFieldWelds') }}</span>
            <strong>{{ formatPercent(props.dashboard.prefabRate) }}</strong>
            <small>{{ props.dashboard.prefabWeldCount || 0 }} / {{ props.dashboard.totalWeldCount || 0 }}</small>
          </div>
          <div class="initialization-stat-card is-auto">
            <span>{{ t('autoVsPrefabWelds') }}</span>
            <strong>{{ formatPercent(props.dashboard.autoRate) }}</strong>
            <small>{{ props.dashboard.autoWeldCount || 0 }} / {{ props.dashboard.prefabWeldCount || 0 }}</small>
          </div>
          <div class="initialization-stat-card">
            <span>{{ t('statisticalUnits') }}</span>
            <strong>{{ props.dashboard.unitCount || 0 }}</strong>
            <small>{{ t('groupedByUnitNo') }}</small>
          </div>
        </v-sheet>
      </template>

      <template v-else-if="activeView === 'table'">
        <div class="initialization-table-head">
          <div class="section-title-with-tip">
            <h3>{{ t('unitWeldRatio') }}</h3>
            <InfoTooltip :text="t('unitWeldRatioTip')" />
          </div>
        </div>
        <DataVTable
          :records="unitRows"
          :columns="unitTableColumns"
          :height="360"
          :empty-text="t('noInitializationStats')"
        />
      </template>

      <template v-else>
        <div class="initialization-table-head">
          <div class="section-title-with-tip">
            <h3>{{ t('initializationDataSource') }}</h3>
            <InfoTooltip :text="t('initializationDataSourceTip')" />
          </div>
        </div>
        <DataVTable
          :records="sourceRows"
          :columns="sourceTableColumns"
          :height="220"
          :empty-text="t('noInitializationDataSource')"
        />
      </template>
    </template>
  </component>
</template>

<style scoped>
.initialization-dashboard-panel {
  min-width: 0;
}

.initialization-dashboard-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 36px;
  margin-bottom: 14px;
}

.initialization-dashboard-head > div:first-child,
.initialization-dashboard-head .section-title-with-tip {
  min-height: 36px;
  align-items: center;
}

.initialization-dashboard-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  min-height: 36px;
  align-self: center;
}

.dashboard-icon-toggle {
  flex-shrink: 0;
}

.dashboard-icon-toggle :deep(.v-btn),
.initialization-dashboard-actions > .v-btn {
  min-width: 36px;
  width: 36px;
  height: 36px;
}

.dashboard-action-divider {
  width: 1px;
  height: 24px;
  flex: 0 0 1px;
  background: var(--line);
}

.initialization-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.initialization-stat-card {
  display: grid;
  gap: 6px;
  min-height: 108px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-soft);
}

.initialization-stat-card.is-prefab {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--line));
}

.initialization-stat-card.is-auto {
  border-color: color-mix(in srgb, #0f9f6e 35%, var(--line));
}

.initialization-stat-card span,
.initialization-stat-card small {
  color: var(--muted);
  font-size: 12px;
}

.initialization-stat-card strong {
  color: var(--strong);
  font-size: 30px;
  line-height: 1;
}

.initialization-table-head {
  margin-bottom: 10px;
}

.initialization-table-head h3 {
  margin: 0;
  color: var(--strong);
  font-size: 16px;
}

@media (max-width: 1100px) {
  .initialization-stats {
    grid-template-columns: 1fr;
  }
}
</style>
