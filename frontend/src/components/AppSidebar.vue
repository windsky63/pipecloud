<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  isNavigationRouteVisible,
  navigationVisibility,
  sidebarCollapsed,
  summary,
  t,
} from '../services/pipecloudState'
import { localizedLibraryTitle, localizedModuleTitle } from '../services/navigationLabels'
import { libraries } from '../services/weldLibraryState'

const route = useRoute()

const moduleIcons = {
  initialization: 'mdi-file-document-outline',
  arrival: 'mdi-truck-outline',
  antiCorrosion: 'mdi-package-variant-closed',
  cutting: 'mdi-saw-blade',
  welding: 'mdi-tools',
  schedule: 'mdi-calendar-sync',
}

const planMenus = computed(() => [
  { key: 'anti-corrosion', name: t('antiCorrosion'), icon: 'mdi-package-variant-closed' },
  { key: 'cutting', name: t('cutting'), icon: 'mdi-saw-blade' },
  { key: 'welding', name: t('welding'), icon: 'mdi-tools' },
  { key: 'gantt', name: t('gantt'), icon: 'mdi-calendar-week' },
])

const prefabModules = computed(() => {
  return summary.value.modules
    .filter((module) => isNavigationRouteVisible(`/prefab/${module.key}`))
    .map((module) => ({
      ...module,
      name: localizedModuleTitle(module),
    }))
})

const visiblePlanMenus = computed(() => {
  return planMenus.value.filter((plan) => isNavigationRouteVisible(`/plans/${plan.key}`))
})

const visibleLibraries = computed(() => {
  return libraries.value
    .filter((library) => isNavigationRouteVisible(`/weld-libraries/${library.key}`))
    .map((library) => ({
      ...library,
      name: localizedLibraryTitle(library),
    }))
})

const activeMenu = computed(() => {
  if (route.path.startsWith('/settings')) return '/settings'
  if (route.name === 'spool-check' || route.path.startsWith('/spool-check')) return '/spool-check'
  if (route.name === 'file-parser' || route.path.startsWith('/parser')) return '/parser'
  if (route.name === 'prefab-factory' || route.path.startsWith('/factory')) return '/factory'
  if (route.name === 'prefab-home') return '/home'
  if (route.name === 'plan-viewer') return `/plans/${route.params.planKey}`
  if (route.name === 'prefab-module') return `/prefab/${route.params.moduleKey}`
  if (route.name === 'weld-library') return `/weld-libraries/${route.params.libraryKey}`
  return '/prefab/initialization'
})

const openedMenuGroups = ref([])

const directNavigationItems = computed(() => [
  navigationVisibility.value.home && isNavigationRouteVisible('/home') && {
    title: t('prefabHome'),
    value: '/home',
    props: {
      to: '/home',
      prependIcon: 'mdi-view-dashboard-outline',
      title: t('prefabHome'),
      value: '/home',
    },
  },
  navigationVisibility.value.parser && isNavigationRouteVisible('/parser') && {
    title: t('fileParser'),
    value: '/parser',
    props: {
      to: '/parser',
      prependIcon: 'mdi-file-excel-outline',
      title: t('fileParser'),
      value: '/parser',
    },
  },
  navigationVisibility.value.spoolCheck && isNavigationRouteVisible('/spool-check') && {
    title: t('spoolCheck'),
    value: '/spool-check',
    props: {
      to: '/spool-check',
      prependIcon: 'mdi-source-branch-check',
      title: t('spoolCheck'),
      value: '/spool-check',
    },
  },
  navigationVisibility.value.factory && isNavigationRouteVisible('/factory') && {
    title: t('prefabFactory'),
    value: '/factory',
    props: {
      to: '/factory',
      prependIcon: 'mdi-factory',
      title: t('prefabFactory'),
      value: '/factory',
    },
  },
].filter(Boolean))

const railMenus = computed(() => [
  navigationVisibility.value.prefab && {
    key: 'prefab',
    title: t('prefab'),
    icon: 'mdi-folder-open-outline',
    items: prefabModules.value.map((module) => ({
      title: module.name,
      icon: moduleIcons[module.key] || 'mdi-folder-outline',
      to: `/prefab/${module.key}`,
      value: `/prefab/${module.key}`,
    })),
  },
  navigationVisibility.value.plans && {
    key: 'plans',
    title: t('plans'),
    icon: 'mdi-calendar-month-outline',
    items: visiblePlanMenus.value.map((plan) => ({
      title: plan.name,
      icon: plan.icon,
      to: `/plans/${plan.key}`,
      value: `/plans/${plan.key}`,
    })),
  },
  navigationVisibility.value.weldLibraries && {
    key: 'weld-libraries',
    title: t('weldLibraries'),
    icon: 'mdi-table-large',
    items: visibleLibraries.value.map((library) => ({
      title: library.name,
      icon: 'mdi-file-document-outline',
      to: `/weld-libraries/${library.key}`,
      value: `/weld-libraries/${library.key}`,
    })),
  },
].filter(Boolean))

const navigationTreeItems = computed(() => [
  ...directNavigationItems.value,
  navigationVisibility.value.prefab && {
    title: t('prefab'),
    value: '/prefab',
    props: {
      prependIcon: 'mdi-folder-open-outline',
      title: t('prefab'),
      value: '/prefab',
    },
    children: prefabModules.value.map((module) => ({
      title: module.name,
      value: `/prefab/${module.key}`,
      props: {
        to: `/prefab/${module.key}`,
        prependIcon: moduleIcons[module.key] || 'mdi-folder-outline',
        title: module.name,
        value: `/prefab/${module.key}`,
      },
    })),
  },
  navigationVisibility.value.plans && {
    title: t('plans'),
    value: '/plans',
    props: {
      prependIcon: 'mdi-calendar-month-outline',
      title: t('plans'),
      value: '/plans',
    },
    children: visiblePlanMenus.value.map((plan) => ({
      title: plan.name,
      value: `/plans/${plan.key}`,
      props: {
        to: `/plans/${plan.key}`,
        prependIcon: plan.icon,
        title: plan.name,
        value: `/plans/${plan.key}`,
      },
    })),
  },
  navigationVisibility.value.weldLibraries && {
    title: t('weldLibraries'),
    value: '/weld-libraries',
    props: {
      prependIcon: 'mdi-table-large',
      title: t('weldLibraries'),
      value: '/weld-libraries',
    },
    children: visibleLibraries.value.map((library) => ({
      title: library.name,
      value: `/weld-libraries/${library.key}`,
      props: {
        to: `/weld-libraries/${library.key}`,
        prependIcon: 'mdi-file-document-outline',
        title: library.name,
        value: `/weld-libraries/${library.key}`,
      },
    })),
  },
  {
    title: t('settings'),
    value: '/settings',
    props: {
      to: '/settings',
      prependIcon: 'mdi-cog-outline',
      title: t('settings'),
      value: '/settings',
    },
  },
].filter(Boolean))

function callTreeHeaderToggle(handler, event) {
  event.stopPropagation()
  if (Array.isArray(handler)) {
    handler.forEach((fn) => fn?.(event))
    return
  }
  handler?.(event)
}

function isPrimaryTreeLeaf(value) {
  return value === '/settings' || directNavigationItems.value.some((item) => item.value === value)
}

watch(sidebarCollapsed, (collapsed) => {
  if (collapsed) {
    openedMenuGroups.value = []
  }
})
</script>

<template>
  <v-navigation-drawer
    permanent
    :rail="sidebarCollapsed"
    :width="220"
    :rail-width="72"
    :class="['sidebar', { 'is-collapsed': sidebarCollapsed }]"
  >
    <div class="brand">
      <span class="pipe-mark" aria-hidden="true"></span>
      <div v-if="!sidebarCollapsed">
        <strong>PipeCloud</strong>
        <small>{{ t('appSubtitle') }}</small>
      </div>
    </div>    

    <v-treeview
      v-if="!sidebarCollapsed"
      v-model:opened="openedMenuGroups"
      :activated="[activeMenu]"
      :items="navigationTreeItems"
      activatable
      active-color="primary"
      density="compact"
      item-children="children"
      item-props="props"
      item-title="title"
      item-value="value"
      hide-actions
      open-on-click
      slim
      class="side-menu"
    >
      <template #header="{ props }">
        <v-list-item
          v-bind="props"
          class="tree-root-item"
          :prepend-icon="props.prependIcon"
          :title="props.title"
        >
          <template #append>
            <v-icon
              class="tree-root-toggle-icon"
              :icon="props.ariaExpanded ? 'mdi-chevron-down' : 'mdi-chevron-right'"
              size="18"
              @click.stop="callTreeHeaderToggle(props.onToggleExpand, $event)"
            />
          </template>
        </v-list-item>
      </template>

      <template #item="{ props, item }">
        <v-list-item
          v-bind="props"
          :class="isPrimaryTreeLeaf(item.value) ? 'tree-root-item' : 'tree-child-item'"
          :prepend-icon="props.prependIcon"
          :title="props.title"
        />
      </template>
    </v-treeview>

    <v-list v-else :selected="[activeMenu]" bg-color="transparent" class="rail-menu" density="compact" nav>
      <v-tooltip
        v-for="item in directNavigationItems"
        :key="item.value"
        location="end"
        open-delay="120"
      >
        <template #activator="{ props }">
          <v-list-item
            v-bind="props"
            :value="item.value"
            :to="item.props.to"
            :active="activeMenu === item.value"
            :aria-label="item.title"
            :prepend-icon="item.props.prependIcon"
          />
        </template>
        <span>{{ item.title }}</span>
      </v-tooltip>

      <v-menu
        v-for="menu in railMenus"
        :key="menu.key"
        location="end"
        open-on-hover
        close-delay="80"
      >
        <template #activator="{ props }">
          <v-list-item
            v-bind="props"
            :active="menu.key === 'prefab' ? activeMenu.startsWith('/prefab') : menu.items.some((item) => item.value === activeMenu)"
            :aria-label="menu.title"
            :prepend-icon="menu.icon"
          />
        </template>
        <v-card class="rail-flyout" elevation="10">
          <v-list :selected="[activeMenu]" density="compact" nav>
            <v-list-subheader>{{ menu.title }}</v-list-subheader>
            <v-list-item
              v-for="item in menu.items"
              :key="item.value"
              :value="item.value"
              :to="item.to"
              :prepend-icon="item.icon"
              :title="item.title"
            />
          </v-list>
        </v-card>
      </v-menu>

      <v-tooltip location="end" open-delay="120">
        <template #activator="{ props }">
          <v-list-item
            v-bind="props"
            value="/settings"
            to="/settings"
            :active="activeMenu === '/settings'"
            :aria-label="t('settings')"
            prepend-icon="mdi-cog-outline"
          />
        </template>
        <span>{{ t('settings') }}</span>
      </v-tooltip>
    </v-list>
  </v-navigation-drawer>
</template>

<style scoped>
.sidebar {
  border-right: 1px solid var(--sidebar-border);
  background: var(--sidebar-bg);
  box-shadow: var(--sidebar-shadow);
  color: var(--sidebar-text);
  position: fixed !important;
  transition: none;
  overflow: visible !important;
}

.sidebar :deep(.v-navigation-drawer__content) {
  --scrollbar-width: 6px;
  overflow-y: auto;
}

.sidebar :deep(.v-navigation-drawer__content::-webkit-scrollbar) {
  width: 6px;
}

.sidebar.is-collapsed :deep(.v-navigation-drawer__content) {
  overflow: visible;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 66px;
  padding: 0 14px;
  border-bottom: 1px solid var(--sidebar-border);
  background: var(--sidebar-surface);
}

.sidebar.is-collapsed .brand {
  justify-content: center;
  padding: 0;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  color: var(--sidebar-text);
  font-size: 18px;
  line-height: 1.15;
}

.brand small {
  margin-top: 4px;
  color: var(--sidebar-muted);
  font-size: 12px;
}

.pipe-mark {
  display: inline-block;
  width: 30px;
  height: 18px;
  padding: 0;
  border: 3px solid var(--sidebar-brand-mark);
  border-radius: 10px;
  background: transparent;
  box-shadow: inset 0 0 0 3px var(--sidebar-surface);
  flex-shrink: 0;
}

.side-menu {
  border-right: 0;
  padding: 10px 8px;
  color: var(--sidebar-muted);
}

.side-menu :deep(.v-list-item) {
  min-height: 42px;
  margin-bottom: 3px;
  padding-inline: 12px 10px;
  border-radius: 8px;
  color: var(--sidebar-text);
  font-weight: 600;
}

.side-menu :deep(.tree-root-item .v-list-item__prepend),
.side-menu :deep(.tree-child-item .v-list-item__prepend) {
  flex: 0 0 24px;
  align-items: center;
  justify-content: center;
  width: 24px;
  min-width: 24px;
  margin-inline-end: 0;
}

.side-menu :deep(.v-list-item__spacer) {
  width: 10px !important;
}

.side-menu :deep(.tree-root-item .v-list-item__append) {
  margin-inline-start: auto;
  padding-inline-start: 8px;
  color: var(--sidebar-icon);
}

.tree-root-toggle-icon {
  border-radius: 50%;
  cursor: pointer;
}

.tree-root-toggle-icon:hover {
  color: var(--sidebar-active-text);
}

.side-menu :deep(.v-list-item__content) {
  min-width: 0;
}

.side-menu :deep(.v-list-item-title) {
  overflow: hidden;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.side-menu :deep(.tree-child-item) {
  padding-inline-start: 38px !important;
  padding-inline-end: 10px !important;
}

.side-menu :deep(.tree-child-item .v-list-item__prepend) {
  flex-basis: 22px;
  width: 22px;
  min-width: 22px;
}

.side-menu :deep(.tree-child-item .v-list-item-title) {
  font-size: 12px;
}

.side-menu :deep(.v-list-item:hover) {
  background: var(--sidebar-hover);
  color: var(--sidebar-text);
}

.side-menu :deep(.v-list-item--active) {
  background: var(--sidebar-active);
  color: var(--sidebar-active-text) !important;
}

.side-menu :deep(.v-list-item--active .v-list-item-title),
.side-menu :deep(.v-list-item--active .v-list-item__content) {
  color: var(--sidebar-active-text) !important;
}

.side-menu :deep(.v-list-item__prepend > .v-icon),
.side-menu :deep(.v-list-item__append > .v-icon) {
  color: var(--sidebar-icon);
  opacity: 1;
}

.side-menu :deep(.v-list-item--active .v-list-item__prepend > .v-icon),
.side-menu :deep(.v-list-item--active .v-list-item__append > .v-icon) {
  color: var(--sidebar-active-text) !important;
}

.side-menu :deep(.v-list-item__overlay),
.side-menu :deep(.v-list-item__underlay) {
  display: none;
}

.rail-menu {
  padding: 10px 12px;
  background: transparent;
}

.rail-menu :deep(.v-list-item) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  min-width: 48px;
  height: 48px;
  min-height: 48px;
  padding: 0;
  margin-bottom: 6px;
  border-radius: 8px;
  color: var(--sidebar-icon);
}

.rail-menu :deep(.v-list-item:hover),
.rail-menu :deep(.v-list-item--active) {
  background: var(--sidebar-active);
  color: var(--sidebar-active-text) !important;
}

.rail-menu :deep(.v-list-item__prepend) {
  flex: 0 0 24px;
  align-items: center;
  justify-content: center;
  width: 24px;
  min-width: 24px;
  height: 24px;
  margin: 0;
}

.rail-menu :deep(.v-list-item__prepend > .v-icon) {
  color: currentColor;
  opacity: 1;
  margin: 0;
}

.rail-menu :deep(.v-list-item__content),
.rail-menu :deep(.v-list-item__append),
.rail-menu :deep(.v-list-item__spacer) {
  display: none;
}

.rail-flyout {
  width: 220px;
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--sidebar-border);
  border-radius: 8px;
  background: var(--sidebar-bg);
  box-shadow: 0 18px 42px rgba(15, 23, 42, .16);
}

.rail-flyout :deep(.v-list) {
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  padding: 8px;
}

.rail-flyout :deep(.v-list-subheader) {
  min-height: 30px;
  padding-inline: 10px;
  color: var(--sidebar-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.rail-flyout :deep(.v-list-item) {
  min-height: 36px;
  border-radius: 7px;
  color: var(--sidebar-text);
  font-size: 13px;
}

.rail-flyout :deep(.v-list-item:hover) {
  background: var(--sidebar-hover);
}

.rail-flyout :deep(.v-list-item--active) {
  background: var(--sidebar-active);
  color: var(--sidebar-active-text);
}

.rail-flyout :deep(.v-list-item__prepend > .v-icon) {
  color: var(--sidebar-icon);
}

.rail-flyout :deep(.v-list-item--active .v-list-item__prepend > .v-icon) {
  color: var(--sidebar-active-text);
}

.sidebar.is-collapsed :deep(.v-list-item__prepend) {
  justify-content: center;
  width: 100%;
}
</style>
