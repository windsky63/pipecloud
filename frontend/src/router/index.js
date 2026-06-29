import { createRouter, createWebHistory } from 'vue-router'
import PrefabHome from '../views/PrefabHome/index.vue'
import PrefabWorkspace from '../views/PrefabWorkspace/index.vue'
import PlanViewer from '../views/PlanViewer/index.vue'
import SystemSettings from '../views/SystemSettings/index.vue'
import WeldLibraryViewer from '../views/WeldLibraryViewer/index.vue'
import FileParser from '../views/FileParser/index.vue'
import SpoolCheck from '../views/SpoolCheck/index.vue'
import { hasSelectedProject, notifyProjectRequired, setSelectedProjectId } from '../services/projectState'


const routes = [
  { path: '/', redirect: '/prefab/initialization' },
  { path: '/prefab', redirect: '/prefab/initialization' },
  { path: '/home', name: 'prefab-home', component: PrefabHome },
  { path: '/prefab/:moduleKey', name: 'prefab-module', component: PrefabWorkspace },
  { path: '/plans', redirect: '/plans/anti-corrosion' },
  { path: '/plans/:planKey', name: 'plan-viewer', component: PlanViewer },
  { path: '/weld-libraries', redirect: '/weld-libraries/weld-library' },
  { path: '/weld-libraries/:libraryKey', name: 'weld-library', component: WeldLibraryViewer },
  { path: '/settings', name: 'settings', component: SystemSettings },
  { path: '/parser', name: 'parser', component: FileParser },
  { path: '/spool-check', name: 'spool-check', component: SpoolCheck },
  { path: '/factory', name: 'prefab-factory', component: () => import('../views/PrefabFactory/index.vue') },
  // 添加404通配路由
  { path: '/:pathMatch(.*)*', name: 'not-found', redirect: '/home' }
]


const router = createRouter({
  history: createWebHistory(),
  routes,
})

const projectFreeRoutes = new Set(['prefab-home', 'prefab-factory', 'settings'])

router.beforeEach(async (to) => {
  // 处理不存在的路由（通过匹配到 not-found 路由名称）
  if (to.name === 'not-found') {
    return { name: 'prefab-home' }
  }
  
  if (projectFreeRoutes.has(to.name)) return true
  if (await hasSelectedProject()) return true

  setSelectedProjectId(null)
  notifyProjectRequired()
  return { name: 'prefab-home' }
})

export default router
