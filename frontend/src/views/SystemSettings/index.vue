<script setup>
import { computed, onMounted, ref } from 'vue'
import InfoTooltip from '../../components/InfoTooltip.vue'
import SystemSettingsHeader from './SystemSettingsHeader.vue'
import {
  isNavigationRouteVisible,
  developerMode,
  dashboardVisibility,
  dashboardVisibilityKeys,
  errorMessage,
  homeComponentVisibility,
  homeComponentVisibilityKeys,
  loadSummary,
  loading,
  language,
  languageOptions,
  navigationVisibility,
  navigationVisibilityKeys,
  setShowRunLog,
  setDeveloperMode,
  setDashboardVisibility,
  setLanguage,
  setHomeComponentVisibility,
  setNavigationRouteVisibility,
  setNavigationVisibility,
  setSidebarCollapsed,
  setUiTheme,
  showRunLog,
  sidebarCollapsed,
  summary,
  t,
  uiTheme,
  uiThemeOptions,
} from '../../services/pipecloudState'
import { localizedLibraryTitle, localizedModuleTitle } from '../../services/navigationLabels'
import { libraries, loadLibraries } from '../../services/weldLibraryState'

const expandedNavigationNodes = ref(new Set())

const localizedThemeOptions = computed(() => {
  return uiThemeOptions.map((option) => ({
    ...option,
    title: t(option.titleKey),
  }))
})

const localizedLanguageOptions = computed(() => {
  return languageOptions.map((option) => ({
    ...option,
    title: option.title,
  }))
})

const navigationItems = computed(() => [
  { key: 'home', routeKey: '/home', title: t('prefabHome'), icon: 'mdi-view-dashboard-outline' },
  { key: 'parser', routeKey: '/files', title: t('files'), icon: 'mdi-folder-multiple-outline' },
  { key: 'spoolCheck', routeKey: '/spool-check', title: t('spoolCheck'), icon: 'mdi-source-branch-check' },
  { key: 'factory', routeKey: '/factory', title: t('prefabFactory'), icon: 'mdi-factory' },
  {
    key: 'prefab',
    routeKey: '/prefab',
    title: t('prefab'),
    icon: 'mdi-folder-open-outline',
    children: summary.value.modules.map((module) => ({
      routeKey: `/prefab/${module.key}`,
      title: localizedModuleTitle(module),
      icon: 'mdi-file-document-outline',
    })),
  },
  {
    key: 'plans',
    routeKey: '/plans',
    title: t('plans'),
    icon: 'mdi-calendar-month-outline',
    children: [
      { routeKey: '/plans/anti-corrosion', title: t('antiCorrosion'), icon: 'mdi-package-variant-closed' },
      { routeKey: '/plans/cutting', title: t('cutting'), icon: 'mdi-saw-blade' },
      { routeKey: '/plans/welding', title: t('welding'), icon: 'mdi-tools' },
      { routeKey: '/plans/gantt', title: t('gantt'), icon: 'mdi-calendar-week' },
    ],
  },
  {
    key: 'weldLibraries',
    routeKey: '/libraries',
    title: t('weldLibraries'),
    icon: 'mdi-table-large',
    children: libraries.value.map((library) => ({
      routeKey: `/libraries/${library.key}`,
      title: localizedLibraryTitle(library),
      icon: 'mdi-file-document-outline',
    })),
  },
].filter((item) => navigationVisibilityKeys.includes(item.key)))

const lockedNavigationItems = computed(() => [
  { routeKey: '/settings', title: t('settings'), icon: 'mdi-cog-outline' },
])

const homeComponentItems = computed(() => [
  { key: 'initializationDashboard', title: t('initializationDashboardTitle'), icon: 'mdi-chart-donut' },
  { key: 'antiCorrosionDashboard', title: t('antiCorrosionDashboardTitle'), icon: 'mdi-shield-check-outline' },
  { key: 'cuttingDashboard', title: t('cuttingDashboardTitle'), icon: 'mdi-saw-blade' },
  { key: 'weldingDashboard', title: t('weldingDashboardTitle'), icon: 'mdi-chart-line' },
  { key: 'arrivalDashboard', title: t('arrivalDashboardTitle'), icon: 'mdi-truck-check-outline' },
  { key: 'workflow', title: t('workflow'), icon: 'mdi-source-branch-sync' },
  { key: 'projectData', title: t('projectData'), icon: 'mdi-table-cog' },
  { key: 'projectWeldInfo', title: t('projectWeldInfo'), icon: 'mdi-table-search' },
].filter((item) => homeComponentVisibilityKeys.includes(item.key)))

const dashboardItems = computed(() => [
  { key: 'initialization', title: t('initializationDashboardTitle'), page: t('initialization') },
  { key: 'arrival', title: t('arrivalDashboardTitle'), page: t('arrival') },
  { key: 'antiCorrosion', title: t('antiCorrosionDashboardTitle'), page: t('antiCorrosion') },
  { key: 'cutting', title: t('cuttingDashboardTitle'), page: t('cutting') },
  { key: 'welding', title: t('weldingDashboardTitle'), page: t('welding') },
  { key: 'futureAntiCorrosion', title: t('antiCorrosionDashboardTitle'), page: t('totalSchedulingPlan') },
  { key: 'futureCutting', title: t('cuttingDashboardTitle'), page: t('totalSchedulingPlan') },
  { key: 'futureWelding', title: t('weldingDashboardTitle'), page: t('totalSchedulingPlan') },
].filter((item) => dashboardVisibilityKeys.includes(item.key)))

function isNavigationItemVisible(item) {
  return Boolean(navigationVisibility.value[item.key]) && isNavigationRouteVisible(item.routeKey)
}

function setNavigationItemVisibility(item, value) {
  setNavigationVisibility(item.key, value)
  setNavigationRouteVisibility(item.routeKey, value)
}

function isNavigationNodeExpanded(item) {
  return expandedNavigationNodes.value.has(item.key)
}

function toggleNavigationNode(item) {
  if (!item.children?.length) return
  const nextExpanded = new Set(expandedNavigationNodes.value)
  if (nextExpanded.has(item.key)) {
    nextExpanded.delete(item.key)
  } else {
    nextExpanded.add(item.key)
  }
  expandedNavigationNodes.value = nextExpanded
}

onMounted(() => {
  if (!summary.value.modules.length) {
    loadSummary()
  }
  if (!libraries.value.length) {
    loadLibraries()
  }
})
</script>

<template>
  <SystemSettingsHeader :title="t('settings')" :description="t('settingsDescription')">
    <template #actions>
      <v-btn color="secondary" variant="tonal" :loading="loading" prepend-icon="mdi-refresh" @click="loadSummary">
        {{ t('refreshConfig') }}
      </v-btn>
    </template>
  </SystemSettingsHeader>

  <v-alert v-if="errorMessage" :text="errorMessage" type="error" density="compact" class="status-alert" />

  <div class="settings-page-layout">
    <v-card class="module-panel settings-section">
      <div class="section-head">
        <div class="section-title-with-tip">
          <h2>{{ t('interfaceOptions') }}</h2>
          <InfoTooltip :text="t('savedInBrowser')" />
        </div>
      </div>
      <v-table density="compact" class="settings-table">
        <tbody>
          <tr>
            <th>{{ t('theme') }}</th>
            <td>
              <v-select
                :model-value="uiTheme"
                :items="localizedThemeOptions"
                density="compact"
                hide-details
                class="settings-select"
                @update:model-value="setUiTheme"
              />
            </td>
          </tr>
          <tr>
            <th>{{ t('language') }}</th>
            <td>
              <v-select
                :model-value="language"
                :items="localizedLanguageOptions"
                density="compact"
                hide-details
                class="settings-select"
                @update:model-value="setLanguage"
              />
            </td>
          </tr>
          <tr>
            <th>{{ t('runLog') }}</th>
            <td>
              <v-switch
                :model-value="showRunLog"
                color="primary"
                density="compact"
                hide-details
                :label="showRunLog ? t('show') : t('hide')"
                @update:model-value="setShowRunLog"
              />
            </td>
          </tr>
          <tr>
            <th>{{ t('developerMode') }}</th>
            <td>
              <v-switch
                :model-value="developerMode"
                color="primary"
                density="compact"
                hide-details
                :label="developerMode ? t('enabled') : t('disabled')"
                @update:model-value="setDeveloperMode"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card class="module-panel settings-section">
      <div class="section-head">
        <div class="section-title-with-tip">
          <h2>{{ t('dashboardOptions') }}</h2>
          <InfoTooltip :text="t('dashboardOptionsDescription')" />
        </div>
      </div>
      <v-table density="compact" class="settings-table">
        <tbody>
          <tr class="settings-row-spaced">
            <th>{{ t('dashboardVisibility') }}</th>
            <td>
              <div class="home-component-settings">
                <div v-for="item in dashboardItems" :key="item.key" class="navigation-tree-row">
                  <div class="navigation-tree-main">
                    <v-icon icon="mdi-view-dashboard-outline" size="18" />
                    <span>{{ item.page }} / {{ item.title }}</span>
                  </div>
                  <v-switch
                    :model-value="dashboardVisibility[item.key]"
                    class="navigation-compact-switch"
                    color="primary"
                    density="compact"
                    hide-details
                    inset
                    @update:model-value="(value) => setDashboardVisibility(item.key, value)"
                  />
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card class="module-panel settings-section">
      <div class="section-head">
        <div class="section-title-with-tip">
          <h2>{{ t('prefabHomeOptions') }}</h2>
          <InfoTooltip :text="t('prefabHomeOptionsDescription')" />
        </div>
      </div>
      <v-table density="compact" class="settings-table">
        <tbody>
          <tr class="settings-row-spaced">
            <th>{{ t('prefabHomeComponents') }}</th>
            <td>
              <div class="home-component-settings">
                <div
                  v-for="item in homeComponentItems"
                  :key="item.key"
                  class="navigation-tree-row"
                >
                  <div class="navigation-tree-main">
                    <v-icon :icon="item.icon" size="18" />
                    <span>{{ item.title }}</span>
                  </div>
                  <v-switch
                    :model-value="homeComponentVisibility[item.key]"
                    class="navigation-compact-switch"
                    color="primary"
                    density="compact"
                    hide-details
                    inset
                    @update:model-value="(value) => setHomeComponentVisibility(item.key, value)"
                  />
                </div>
                <div class="navigation-tree-row is-locked">
                  <div>
                    <v-icon icon="mdi-swap-horizontal-bold" size="18" />
                    <span>{{ t('projectSwitcher') }}</span>
                  </div>
                  <span>{{ t('projectSwitcherAlwaysVisible') }}</span>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card class="module-panel settings-section">
      <div class="section-head">
        <div class="section-title-with-tip">
          <h2>{{ t('navigationOptions') }}</h2>
          <InfoTooltip :text="t('navigationOptionsDescription')" />
        </div>
      </div>
      <v-table density="compact" class="settings-table">
        <tbody>
          <tr>
            <th>{{ t('sidebar') }}</th>
            <td>
              <v-switch
                :model-value="sidebarCollapsed"
                color="primary"
                density="compact"
                hide-details
                :label="sidebarCollapsed ? t('collapsed') : t('expanded')"
                @update:model-value="setSidebarCollapsed"
              />
            </td>
          </tr>
          <tr class="settings-row-spaced">
            <th>{{ t('navigationItems') }}</th>
            <td>
              <div class="navigation-tree-settings">
              <div
                v-for="item in navigationItems"
                :key="item.key"
                class="navigation-tree-node"
              >
                <div class="navigation-tree-row">
                  <div class="navigation-tree-main">
                    <v-btn
                      v-if="item.children?.length"
                      :icon="isNavigationNodeExpanded(item) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      :aria-label="t('toggleCollapse')"
                      class="navigation-tree-toggle"
                      density="compact"
                      size="x-small"
                      variant="text"
                      @click="toggleNavigationNode(item)"
                    />
                    <span v-else class="navigation-tree-toggle-spacer"></span>
                    <v-icon :icon="item.icon" size="18" />
                    <span>{{ item.title }}</span>
                  </div>
                  <v-switch
                    :model-value="isNavigationItemVisible(item)"
                    class="navigation-compact-switch"
                    color="primary"
                    density="compact"
                    hide-details
                    inset
                    @update:model-value="(value) => setNavigationItemVisibility(item, value)"
                  />
                </div>
                <div
                  v-if="item.children?.length && isNavigationNodeExpanded(item)"
                  class="navigation-tree-children"
                >
                  <div
                    v-for="child in item.children"
                    :key="child.routeKey"
                    class="navigation-tree-row is-child"
                  >
                    <div class="navigation-tree-main">
                      <span class="navigation-tree-toggle-spacer"></span>
                      <v-icon :icon="child.icon" size="17" />
                      <span>{{ child.title }}</span>
                    </div>
                    <v-switch
                      :model-value="child.key ? isNavigationItemVisible(child) : isNavigationRouteVisible(child.routeKey)"
                      class="navigation-compact-switch"
                      color="primary"
                      density="compact"
                      hide-details
                      inset
                      @update:model-value="(value) => child.key ? setNavigationItemVisibility(child, value) : setNavigationRouteVisibility(child.routeKey, value)"
                    />
                  </div>
                </div>
              </div>
              <div
                v-for="item in lockedNavigationItems"
                :key="item.routeKey"
                class="navigation-tree-row is-locked"
              >
                <div>
                  <v-icon :icon="item.icon" size="18" />
                  <span>{{ item.title }}</span>
                </div>
                <span>{{ t('cannotHideSettings') }}</span>
              </div>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

  </div>
</template>

<style scoped>
</style>
