import { createRouter, createWebHistory } from 'vue-router'
import { hasSelectedProject, notifyProjectRequired, setSelectedProjectId } from '../services/projectState'
import { developerMode } from '../services/pipecloudState'

// 页面统一按路由懒加载。大型表格、Excel 和 3D 依赖只在进入相应页面时下载。
const PrefabHome = () => import('../views/PrefabHome/index.vue')
const PrefabWorkspace = () => import('../views/PrefabWorkspace/index.vue')
const PlanViewer = () => import('../views/PlanViewer/index.vue')
const SystemSettings = () => import('../views/SystemSettings/index.vue')
const DeveloperControls = () => import('../views/DeveloperControls/index.vue')
const WeldLibraryViewer = () => import('../views/WeldLibraryViewer/index.vue')
const FileParser = () => import('../views/FileParser/index.vue')
const SpoolCheck = () => import('../views/SpoolCheck/index.vue')
const FileExport = () => import('../views/FileExport/index.vue')
const PrefabFactory = () => import('../views/PrefabFactory/index.vue')

const routes = [
  { path: '/', redirect: '/prefab/initialization' },
  { path: '/prefab', redirect: '/prefab/initialization' },
  { path: '/home', name: 'prefab-home', component: PrefabHome },
  { path: '/prefab/:moduleKey', name: 'prefab-module', component: PrefabWorkspace },
  { path: '/plans', redirect: '/plans/anti-corrosion' },
  { path: '/plans/:planKey', name: 'plan-viewer', component: PlanViewer },
  { path: '/libraries', redirect: '/libraries/weld-library' },
  { path: '/libraries/:libraryKey', name: 'weld-library', component: WeldLibraryViewer },
  { path: '/settings', name: 'settings', component: SystemSettings },
  { path: '/settings/developer', name: 'developer-controls', component: DeveloperControls },
  {
    path: '/files',
    name: 'files',
    redirect: '/files/parser',
    children: [
      { path: 'parser', name: 'file-parser', component: FileParser },
      { path: 'export', name: 'file-export', component: FileExport },
    ],
  },
  { path: '/parser', redirect: '/files/parser' },
  { path: '/spool-check', name: 'spool-check', component: SpoolCheck },
  { path: '/factory', name: 'prefab-factory', component: PrefabFactory },
  { path: '/:pathMatch(.*)*', name: 'not-found', redirect: '/home' },
]


const router = createRouter({
  history: createWebHistory(),
  routes,
})

const projectFreeRoutes = new Set(['prefab-home', 'prefab-factory', 'settings', 'developer-controls'])

router.beforeEach(async (to) => {
  // 守卫顺序很重要：先处理特殊路由，再执行项目上下文校验。
  if (to.name === 'not-found') {
    return { name: 'prefab-home' }
  }

  if (to.name === 'developer-controls' && !developerMode.value) {
    return { name: 'settings' }
  }

  if (projectFreeRoutes.has(to.name)) return true
  if (await hasSelectedProject()) return true

  setSelectedProjectId(null)
  notifyProjectRequired()
  return { name: 'prefab-home' }
})

export default router
