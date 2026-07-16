<script setup>
import * as THREE from 'three'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchTodayPipeMaterials } from '../../api/factory'
import DataVTable from '../../components/DataVTable.vue'
import { t } from '../../services/pipecloudState'
import { createPipeComponentRenderer, normalizePipeComponentType } from '../../services/pipeComponentRenderer'
import { selectedProjectId, selectedProjectParams } from '../../services/projectState'

const sceneHost = ref(null)
const treeList = ref(null)
const loading = ref(true)
const errorMessage = ref('')
const materialLoading = ref(false)
const materialError = ref('')
const todayMaterialPayload = ref({
  date: '',
  total: 0,
  materials: [],
  weldingPlan: null,
})
const modelTree = ref([])
const selectedNodeId = ref(null)
const selectedWeldingSheet = ref('')
const expandedNodeIds = ref(new Set())
const treeSearchText = ref('')
const loadProgress = ref({
  loaded: 0,
  total: 0,
  percent: 0,
  computable: false,
})
const isolateSelection = ref(false)
const showSelectionInfoCard = ref(true)
const modelStats = ref({
  objects: 0,
  triangles: 0,
})

let renderer = null
let scene = null
let camera = null
let controls = null
let animationFrame = 0
let resizeObserver = null
let factoryModel = null
let rawMaterialGroup = null
let hiddenMaterialSurface = null
const hiddenMaterialSurfaceVisibility = new Map()
let selectionBox = null
let defaultView = null
let selectionAppearanceDirty = false
let selectionRefreshDueAt = 0
let selectionInfoSprite = null
let selectionInfoTexture = null
let selectionInfoCanvas = null
let selectionInfoCanvasContext = null
let selectionInfoLeaderLine = null
const modelObjectsById = new Map()
const parentIdsByObjectId = new Map()
const affectedMeshes = new Set()
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const selectionRefreshDelayMs = 180
const selectionInfoCardAspect = 520 / 280
const selectionInfoCardScreenRatio = 0.23
const pointerDown = {
  x: 0,
  y: 0,
  button: 0,
  active: false,
}

const visibleTreeNodes = computed(() => {
  const rows = []
  const query = treeSearchText.value.trim().toLowerCase()
  const walk = (nodes, depth = 0) => {
    nodes.forEach((node) => {
      rows.push({ ...node, depth })
      if (node.children?.length && expandedNodeIds.value.has(node.id)) {
        walk(node.children, depth + 1)
      }
    })
  }
  const walkSearch = (nodes, depth = 0) => {
    nodes.forEach((node) => {
      const startIndex = rows.length
      rows.push({ ...node, depth, isSearchPath: true })
      const nameMatches = node.name.toLowerCase().includes(query)
      let childMatches = false
      if (node.children?.length) {
        const beforeChildren = rows.length
        walkSearch(node.children, depth + 1)
        childMatches = rows.length > beforeChildren
      }
      if (!nameMatches && !childMatches) {
        rows.splice(startIndex)
      } else if (nameMatches) {
        rows[startIndex] = { ...rows[startIndex], isSearchMatch: true }
      }
    })
  }
  if (query) {
    walkSearch(modelTree.value)
    return rows
  }
  walk(modelTree.value)
  return rows
})

const treeResultCount = computed(() => (
  treeSearchText.value.trim()
    ? visibleTreeNodes.value.filter((node) => node.isSearchMatch).length
    : visibleTreeNodes.value.length
))
const isolateSelectionTooltip = computed(() => (
  isolateSelection.value ? t('showAllStructures') : t('hideNonSelectedStructures')
))

function normalizedStructureName(value) {
  return String(value || '').replace(/\s+/g, '').toLowerCase()
}

function isWorkshopOneEquipment(object) {
  if (!normalizedStructureName(modelNodeName(object, 0)).includes('设备')) return false
  let current = object?.parent || null
  while (current) {
    if (normalizedStructureName(modelNodeName(current, 0)).includes('一车间')) return true
    current = current.parent
  }
  return false
}

const selectedNodeInfo = computed(() => {
  if (!selectedNodeId.value) return null
  const object = modelObjectsById.get(selectedNodeId.value)
  if (!object) return null

  const box = new THREE.Box3().setFromObject(object)
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())

  const workshopEquipment = isWorkshopOneEquipment(object)
  const todayMaterialGroup = object.userData?.kind === 'today-pipe-material-group'
  return {
    id: object.id,
    name: modelNodeName(object, 0),
    type: object.type || 'Object3D',
    meshCount: countMeshes(object),
    childCount: object.children.length,
    sizeText: `${size.x.toFixed(2)} × ${size.y.toFixed(2)} × ${size.z.toFixed(2)}`,
    centerText: `${center.x.toFixed(2)}, ${center.y.toFixed(2)}, ${center.z.toFixed(2)}`,
    materialInfo: object.userData?.pipeMaterial || null,
    todayMaterialGroup,
    materialSummary: todayMaterialGroup ? todayMaterialSummary.value : null,
    workshopEquipment,
    weldingPlan: workshopEquipment ? todayMaterialPayload.value.weldingPlan : null,
  }
})

const selectedInfoCardTitle = computed(() => {
  if (selectedNodeInfo.value?.materialInfo) return t('materialInfo')
  if (selectedNodeInfo.value?.todayMaterialGroup) return t('todayPipeMaterialModels')
  if (selectedNodeInfo.value?.workshopEquipment) return t('todayWeldingPlan')
  return t('selectedSubstructureInfo')
})

const selectedInfoCardBadge = computed(() => {
  if (selectedNodeInfo.value?.materialInfo) return selectedNodeInfo.value.materialInfo.uniqueCode
  if (selectedNodeInfo.value?.todayMaterialGroup) {
    return todayMaterialPayload.value.date || t('noData')
  }
  if (selectedNodeInfo.value?.workshopEquipment) {
    return selectedNodeInfo.value.weldingPlan?.date || t('noTodayWeldingPlan')
  }
  return selectedNodeInfo.value?.type || t('unselected')
})

const todayMaterialTableColumns = computed(() => [
  { field: '__index', title: '#', width: 64, fixed: 'left' },
  { field: 'uniqueCode', title: t('materialUniqueCode'), width: 190, fixed: 'left', sort: true },
  { field: 'materialCode', title: t('materialCode'), width: 160, sort: true },
  { field: 'materialMark', title: t('materialMark'), width: 140, sort: true },
  { field: 'quantityText', title: t('materialQuantity'), width: 130, sort: true },
  { field: 'diameter', title: t('diameter'), width: 110, sort: true },
  { field: 'wallThickness', title: t('wallThickness'), width: 110, sort: true },
  { field: 'material', title: t('material'), width: 130, sort: true },
  { field: 'paint', title: t('materialPaint'), width: 150, sort: true },
  { field: 'description', title: t('materialDescription'), width: 280, sort: true },
])

const todayMaterialTableRows = computed(() => (
  (todayMaterialPayload.value.materials || []).map((material, index) => ({
    __index: index + 1,
    ...material,
    quantityText: `${material.quantity || '-'} ${material.unitName || ''}`.trim(),
  }))
))

const todayMaterialSummary = computed(() => {
  const materials = todayMaterialPayload.value.materials || []
  let pipeCount = 0
  let fittingCount = 0
  const materialCodes = new Set()
  materials.forEach((material) => {
    const type = normalizePipeComponentType({
      materialMark: material.materialMark,
      materialCode: material.materialCode,
      description: material.description,
    })
    if (type === 'pipe') pipeCount += 1
    else fittingCount += 1
    if (material.materialCode) materialCodes.add(material.materialCode)
  })
  return {
    date: todayMaterialPayload.value.date || '-',
    total: materials.length,
    pipeCount,
    fittingCount,
    materialCodeCount: materialCodes.size,
  }
})

const weldingPlanSheets = computed(() => todayMaterialPayload.value.weldingPlan?.sheets || [])
const selectedWeldingSheetData = computed(() => (
  weldingPlanSheets.value.find((sheet) => sheet.name === selectedWeldingSheet.value)
  || weldingPlanSheets.value[0]
  || { name: '', total: 0, columns: [], rows: [] }
))
const weldingPlanTableColumns = computed(() => [
  {
    field: '__index',
    title: '#',
    width: 64,
    fixed: 'left',
    headerStyle: { textAlign: 'center', fontWeight: 700 },
    style: { textAlign: 'center', color: '#64748b', fontWeight: 600 },
  },
  ...(selectedWeldingSheetData.value.columns || []).map((column) => ({
    field: column,
    title: column,
    width: ['描述1', '描述2'].includes(column) ? 260 : 150,
    minWidth: 120,
    sort: true,
    headerStyle: { fontWeight: 700 },
  })),
])
const weldingPlanTableRows = computed(() => (
  (selectedWeldingSheetData.value.rows || []).map((row, index) => ({
    __index: index + 1,
    ...row,
  }))
))

watch(
  () => todayMaterialPayload.value.weldingPlan,
  (plan) => {
    const names = (plan?.sheets || []).map((sheet) => sheet.name)
    if (!names.includes(selectedWeldingSheet.value)) {
      selectedWeldingSheet.value = plan?.selectedSheet || names[0] || ''
    }
  },
  { immediate: true },
)

function setupScene() {
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xf6f7f9)

  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000)
  camera.position.set(18, 14, 18)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  sceneHost.value.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.screenSpacePanning = true
  controls.minDistance = 0.3
  controls.maxDistance = Infinity

  const hemiLight = new THREE.HemisphereLight(0xffffff, 0xcbd5e1, 2.2)
  scene.add(hemiLight)

  const keyLight = new THREE.DirectionalLight(0xffffff, 2.8)
  keyLight.position.set(12, 20, 10)
  keyLight.castShadow = true
  keyLight.shadow.mapSize.set(2048, 2048)
  scene.add(keyLight)

  const fillLight = new THREE.DirectionalLight(0xdbeafe, 1.2)
  fillLight.position.set(-18, 10, -8)
  scene.add(fillLight)

  const grid = new THREE.GridHelper(80, 40, 0x94a3b8, 0xd0d7e2)
  grid.position.y = -0.02
  scene.add(grid)
}

function countModelStats(root) {
  let objects = 0
  let triangles = 0
  root.traverse((child) => {
    objects += 1
    if (child.isMesh && child.geometry) {
      const position = child.geometry.attributes?.position
      const index = child.geometry.index
      triangles += index ? index.count / 3 : (position?.count || 0) / 3
    }
  })
  modelStats.value = {
    objects,
    triangles: Math.round(triangles),
  }
}

function modelNodeName(object, fallbackIndex) {
  const name = String(object.name || '').trim()
  if (name) return name
  return `${object.type || 'Object'} ${fallbackIndex + 1}`
}

function buildModelTree(root) {
  modelObjectsById.clear()
  parentIdsByObjectId.clear()
  const walk = (object, fallbackIndex = 0, parentId = null) => {
    modelObjectsById.set(object.id, object)
    if (parentId !== null) parentIdsByObjectId.set(object.id, parentId)
    const meshCount = countMeshes(object)
    return {
      id: object.id,
      name: modelNodeName(object, fallbackIndex),
      type: object.type || 'Object3D',
      meshCount,
      children: object.children.map((child, index) => walk(child, index, object.id)),
    }
  }
  const rootNode = walk(root)
  modelTree.value = [rootNode]
  expandedNodeIds.value = new Set([rootNode.id, ...rootNode.children.slice(0, 12).map((child) => child.id)])
}

function countMeshes(object) {
  let count = 0
  object.traverse((child) => {
    if (child.isMesh) count += 1
  })
  return count
}

function clampText(text, maxLength = 24) {
  const value = String(text || '')
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength - 1)}...`
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2)
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + width, y, x + width, y + height, r)
  ctx.arcTo(x + width, y + height, x, y + height, r)
  ctx.arcTo(x, y + height, x, y, r)
  ctx.arcTo(x, y, x + width, y, r)
  ctx.closePath()
}

function getSelectionInfoCanvasContext() {
  if (selectionInfoCanvas && selectionInfoCanvasContext) return selectionInfoCanvasContext
  selectionInfoCanvas = document.createElement('canvas')
  selectionInfoCanvasContext = selectionInfoCanvas.getContext('2d')
  return selectionInfoCanvasContext
}

function ensureSelectionInfoSprite() {
  if (selectionInfoSprite) return selectionInfoSprite

  selectionInfoSprite = new THREE.Sprite(new THREE.SpriteMaterial({
    transparent: true,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  }))
  selectionInfoSprite.name = 'FactorySelectionInfoCard'
  selectionInfoSprite.renderOrder = 1000
  selectionInfoSprite.visible = false
  scene.add(selectionInfoSprite)
  return selectionInfoSprite
}

function ensureSelectionInfoLeaderLine() {
  if (selectionInfoLeaderLine) return selectionInfoLeaderLine

  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(),
    new THREE.Vector3(),
  ])
  const material = new THREE.LineBasicMaterial({
    color: 0xf59e0b,
    transparent: true,
    opacity: 0.92,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  })
  selectionInfoLeaderLine = new THREE.Line(geometry, material)
  selectionInfoLeaderLine.name = 'FactorySelectionInfoLeaderLine'
  selectionInfoLeaderLine.renderOrder = 999
  selectionInfoLeaderLine.visible = false
  scene.add(selectionInfoLeaderLine)
  return selectionInfoLeaderLine
}

function drawSelectionInfoTexture(info) {
  const ctx = getSelectionInfoCanvasContext()
  if (!ctx) return

  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
  const width = 520
  const height = 280
  selectionInfoCanvas.width = width * pixelRatio
  selectionInfoCanvas.height = height * pixelRatio
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  ctx.clearRect(0, 0, width, height)

  ctx.fillStyle = 'rgba(255, 255, 255, 0.96)'
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.74)'
  ctx.lineWidth = 2
  roundRect(ctx, 8, 8, width - 16, height - 16, 18)
  ctx.fill()
  ctx.stroke()

  const pipeMaterial = info.materialInfo
  const todayMaterialGroup = info.todayMaterialGroup
  const weldingPlan = info.workshopEquipment ? info.weldingPlan : null
  const title = pipeMaterial?.uniqueCode || (todayMaterialGroup ? t('todayPipeMaterialModels') : info.name)
  ctx.fillStyle = '#0f172a'
  ctx.font = '700 26px Arial'
  ctx.fillText(clampText(title, 22), 30, 52)

  ctx.fillStyle = '#64748b'
  ctx.font = '500 15px Arial'
  ctx.fillText(
    pipeMaterial
      ? t('todayPipeMaterialModels')
      : (todayMaterialGroup
          ? (info.materialSummary?.date || '-')
          : (info.workshopEquipment ? (weldingPlan?.date || t('noTodayWeldingPlan')) : info.type)),
    30,
    78,
  )

  ctx.fillStyle = '#f59e0b'
  ctx.fillRect(30, 95, 82, 4)

  const rows = pipeMaterial
    ? [
        [t('materialCode'), pipeMaterial.materialCode || '-'],
        [t('materialQuantity'), `${pipeMaterial.quantity || '-'} ${pipeMaterial.unitName || ''}`.trim()],
        [t('diameter'), pipeMaterial.diameter || '-'],
        [t('materialDescription'), pipeMaterial.description || '-'],
      ]
    : todayMaterialGroup
      ? [
          [t('materialItemCount'), String(info.materialSummary?.total || 0)],
          [t('materialCodeCount'), String(info.materialSummary?.materialCodeCount || 0)],
          [t('pipeItemCount'), String(info.materialSummary?.pipeCount || 0)],
          [t('fittingItemCount'), String(info.materialSummary?.fittingCount || 0)],
        ]
    : info.workshopEquipment
      ? [
          [t('weldingOrderCount'), String(weldingPlan?.orderCount || 0)],
          [t('weldCount'), String(weldingPlan?.weldCount || 0)],
          [t('planDiameterTotal'), String(weldingPlan?.diameterTotal || 0)],
          [t('segmentCount'), String(weldingPlan?.segmentCount || 0)],
        ]
    : [
        [t('meshCount'), String(info.meshCount)],
        [t('childCount'), String(info.childCount)],
        [t('dimensions'), info.sizeText],
        [t('center'), info.centerText],
      ]
  ctx.font = '500 17px Arial'
  rows.forEach(([label, value], index) => {
    const y = 132 + index * 34
    ctx.fillStyle = '#64748b'
    ctx.fillText(label, 30, y)
    ctx.fillStyle = '#334155'
    ctx.fillText(clampText(value, 32), 116, y)
  })

  ctx.fillStyle = '#64748b'
  ctx.font = '500 13px Arial'
  ctx.fillText(
    pipeMaterial
      ? t('materialUniqueCode')
      : (todayMaterialGroup
          ? t('todayPlanMaterialSummary')
          : (info.workshopEquipment ? t('workshopOneEquipment') : t('selectedSubstructureInfo'))),
    30,
    252,
  )

  if (!selectionInfoTexture) {
    selectionInfoTexture = new THREE.CanvasTexture(selectionInfoCanvas)
    selectionInfoTexture.colorSpace = THREE.SRGBColorSpace
  }
  selectionInfoTexture.needsUpdate = true

  const sprite = ensureSelectionInfoSprite()
  sprite.material.map = selectionInfoTexture
  sprite.material.needsUpdate = true
}

function updateSelectionInfoCardPosition(object) {
  if (!selectionInfoSprite || !object || !camera || !renderer) return
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) {
    selectionInfoSprite.visible = false
    if (selectionInfoLeaderLine) selectionInfoLeaderLine.visible = false
    return
  }

  const center = box.getCenter(new THREE.Vector3())
  const projectedCenter = center.clone().project(camera)
  if (
    !Number.isFinite(projectedCenter.x)
    || !Number.isFinite(projectedCenter.y)
    || !Number.isFinite(projectedCenter.z)
    || projectedCenter.z < -1
    || projectedCenter.z > 1
  ) {
    selectionInfoSprite.visible = false
    if (selectionInfoLeaderLine) selectionInfoLeaderLine.visible = false
    return
  }

  const width = renderer.domElement.clientWidth || renderer.domElement.width || 1
  const height = renderer.domElement.clientHeight || renderer.domElement.height || 1
  const centerScreen = {
    x: (projectedCenter.x * 0.5 + 0.5) * width,
    y: (-projectedCenter.y * 0.5 + 0.5) * height,
  }
  const minCardHeightPx = Math.min(118, Math.max(86, height * 0.18))
  const maxCardHeightPx = Math.min(190, Math.max(118, height * 0.34))
  const targetCardHeightPx = THREE.MathUtils.clamp(height * selectionInfoCardScreenRatio, minCardHeightPx, maxCardHeightPx)
  const cardHeightPx = Math.min(targetCardHeightPx, height - 32)
  const cardWidthPx = Math.min(cardHeightPx * selectionInfoCardAspect, width - 32)
  const margin = 16
  const leaderGap = 24
  const preferredSide = centerScreen.x <= width * 0.58 ? 1 : -1
  const preferredX = centerScreen.x + preferredSide * (cardWidthPx / 2 + leaderGap)
  const fallbackX = centerScreen.x - preferredSide * (cardWidthPx / 2 + leaderGap)
  const centerAvoidanceGap = Math.min(132, Math.max(84, width * 0.12))
  const centerAvoidanceX = (width / 2) + preferredSide * (cardWidthPx / 2 + centerAvoidanceGap)
  const sideBiasedPreferredX = preferredSide > 0
    ? Math.max(preferredX, centerAvoidanceX)
    : Math.min(preferredX, centerAvoidanceX)
  const minX = margin + cardWidthPx / 2
  const maxX = width - margin - cardWidthPx / 2
  const hasPreferredSpace = sideBiasedPreferredX >= minX && sideBiasedPreferredX <= maxX
  const cardScreenX = THREE.MathUtils.clamp(hasPreferredSpace ? sideBiasedPreferredX : fallbackX, minX, maxX)
  const minY = margin + cardHeightPx / 2
  const maxY = height - margin - cardHeightPx / 2
  const cardScreenY = THREE.MathUtils.clamp(centerScreen.y - cardHeightPx * 0.35, minY, maxY)

  const distance = camera.position.distanceTo(center)
  const visibleHeight = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * Math.max(distance, 0.01)
  const cardHeight = visibleHeight * (cardHeightPx / height)
  const cardWidth = cardHeight * selectionInfoCardAspect

  const cardNdc = new THREE.Vector3(
    (cardScreenX / width) * 2 - 1,
    -(cardScreenY / height) * 2 + 1,
    projectedCenter.z,
  )
  selectionInfoSprite.position.copy(cardNdc.unproject(camera))
  selectionInfoSprite.scale.set(cardWidth, cardHeight, 1)
  selectionInfoSprite.visible = true

  const leaderLine = ensureSelectionInfoLeaderLine()
  const edgeScreenX = cardScreenX + (centerScreen.x < cardScreenX ? -cardWidthPx / 2 : cardWidthPx / 2)
  const edgeScreenY = THREE.MathUtils.clamp(centerScreen.y, cardScreenY - cardHeightPx / 2 + 16, cardScreenY + cardHeightPx / 2 - 16)
  const edgeNdc = new THREE.Vector3(
    (edgeScreenX / width) * 2 - 1,
    -(edgeScreenY / height) * 2 + 1,
    projectedCenter.z,
  )
  const edgeWorld = edgeNdc.unproject(camera)
  leaderLine.geometry.setFromPoints([center, edgeWorld])
  leaderLine.geometry.computeBoundingSphere()
  leaderLine.visible = true
}

function syncSelectionInfoCard(object) {
  if (!showSelectionInfoCard.value || !object || !selectedNodeInfo.value) {
    if (selectionInfoSprite) selectionInfoSprite.visible = false
    if (selectionInfoLeaderLine) selectionInfoLeaderLine.visible = false
    return
  }
  drawSelectionInfoTexture(selectedNodeInfo.value)
  updateSelectionInfoCardPosition(object)
}

function normalizeModel(root) {
  root.position.set(0, 0, 0)
  root.scale.setScalar(1)
  root.updateMatrixWorld(true)

  const box = new THREE.Box3().setFromObject(root)
  const size = box.getSize(new THREE.Vector3())
  const maxAxis = Math.max(size.x, size.y, size.z) || 1
  const scale = 28 / maxAxis

  root.scale.setScalar(scale)
  root.updateMatrixWorld(true)

  const centeredBox = new THREE.Box3().setFromObject(root)
  const centeredCenter = centeredBox.getCenter(new THREE.Vector3())
  root.position.sub(centeredCenter)
  root.updateMatrixWorld(true)

  const groundedBox = new THREE.Box3().setFromObject(root)
  root.position.y -= groundedBox.min.y
  root.updateMatrixWorld(true)

  const normalizedBox = new THREE.Box3().setFromObject(root)
  const normalizedSize = normalizedBox.getSize(new THREE.Vector3())

  const distance = Math.max(normalizedSize.x, normalizedSize.z) * 1.15 + normalizedSize.y * 0.8
  camera.position.set(distance, Math.max(10, normalizedSize.y * 0.9), distance)
  controls.target.set(0, Math.max(1, normalizedSize.y * 0.35), 0)
  controls.update()
  saveDefaultView()
}

function prepareModel(root) {
  root.traverse((child) => {
    if (!child.isMesh) return
    child.castShadow = true
    child.receiveShadow = true
    if (child.material) {
      child.material = Array.isArray(child.material)
        ? child.material.map((material) => material.clone())
        : child.material.clone()
      const materials = Array.isArray(child.material) ? child.material : [child.material]
      materials.forEach((material) => {
        material.side = THREE.DoubleSide
        material.needsUpdate = true
      })
    }
  })
  normalizeModel(root)
  countModelStats(root)
  buildModelTree(root)
}

function findFactoryObjectByName(name) {
  let matched = null
  factoryModel?.traverse((object) => {
    if (!matched && String(object.name || '').trim() === name) matched = object
  })
  return matched
}

function findObjectByNameFrom(root, name) {
  const normalizedName = String(name || '').trim().toLowerCase()
  let matched = null
  root?.traverse((object) => {
    if (!matched && String(object.name || '').trim().toLowerCase() === normalizedName) matched = object
  })
  return matched
}

function parsePositiveNumber(value) {
  const match = String(value || '').replace(',', '.').match(/\d+(?:\.\d+)?/)
  const number = match ? Number(match[0]) : 0
  return Number.isFinite(number) && number > 0 ? number : 0
}

function disposeObject(root) {
  root?.traverse((child) => {
    child.geometry?.dispose?.()
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material]
      materials.forEach((material) => material.dispose?.())
    }
  })
}

function clearRawMaterialModels() {
  if (hiddenMaterialSurface) {
    hiddenMaterialSurface.traverse((object) => {
      if (hiddenMaterialSurfaceVisibility.has(object.id)) {
        object.visible = hiddenMaterialSurfaceVisibility.get(object.id)
      }
      delete object.userData.hiddenForTodayPipeMaterials
    })
    hiddenMaterialSurfaceVisibility.clear()
    hiddenMaterialSurface = null
  }
  if (!rawMaterialGroup) return
  rawMaterialGroup.removeFromParent()
  disposeObject(rawMaterialGroup)
  rawMaterialGroup = null
}

function materialLengthMillimeters(material) {
  const quantity = parsePositiveNumber(material.quantity)
  if (!quantity) return 0
  const unit = String(material.unitName || '').trim().toLowerCase()
  if (['mm', '毫米'].includes(unit)) return quantity
  if (['cm', '厘米'].includes(unit)) return quantity * 10
  return quantity * 1000
}

function pipeOutsideDiameterMillimeters(value) {
  const inches = parsePositiveNumber(value)
  if (!inches) return 60.3
  const standardOutsideDiameters = new Map([
    [0.5, 21.3],
    [0.75, 26.7],
    [1, 33.4],
    [1.25, 42.2],
    [1.5, 48.3],
    [2, 60.3],
    [2.5, 73],
    [3, 88.9],
    [4, 114.3],
    [5, 141.3],
    [6, 168.3],
    [8, 219.1],
    [10, 273],
    [12, 323.9],
    [14, 355.6],
    [16, 406.4],
    [18, 457],
    [20, 508],
    [24, 610],
  ])
  return standardOutsideDiameters.get(inches) || inches * 25.4
}

function yardMaterialType(material) {
  const type = normalizePipeComponentType({
    materialMark: material.materialMark,
    materialCode: material.materialCode,
    description: material.description,
  })
  return type === 'component' ? 'fallback-elbow' : type
}

function compareYardMaterials(left, right) {
  const typeOrder = {
    pipe: 0,
    elbow: 1,
    branch: 2,
    reducer: 3,
    flange: 4,
    valve: 5,
    cap: 6,
    gasket: 7,
    'fallback-elbow': 99,
  }
  const leftType = yardMaterialType(left)
  const rightType = yardMaterialType(right)
  const typeDifference = (typeOrder[leftType] ?? 50) - (typeOrder[rightType] ?? 50)
  if (typeDifference) return typeDifference

  if (leftType === 'pipe') {
    const lengthDifference = materialLengthMillimeters(left) - materialLengthMillimeters(right)
    if (lengthDifference) return lengthDifference
  }

  const diameterDifference = parsePositiveNumber(left.diameter) - parsePositiveNumber(right.diameter)
  if (diameterDifference) return diameterDifference
  const codeDifference = String(left.materialCode || '').localeCompare(String(right.materialCode || ''), 'zh-CN')
  if (codeDifference) return codeDifference
  return String(left.uniqueCode || '').localeCompare(String(right.uniqueCode || ''), 'zh-CN')
}

function createYardMaterialObject(material, start, end, radius, crossSpan) {
  const normalizedType = normalizePipeComponentType({
    materialMark: material.materialMark,
    materialCode: material.materialCode,
    description: material.description,
  })
  const usesFallbackElbow = normalizedType === 'component'
  const renderType = usesFallbackElbow ? 'elbow' : normalizedType
  const pipeRenderer = createPipeComponentRenderer({
    defaultRadius: radius,
    getRadius: () => radius,
    toWorld: (point) => new THREE.Vector3(point[0], point[1], point[2]),
    typeColors: usesFallbackElbow ? { elbow: 0xef4444 } : undefined,
  })
  const component = {
    id: material.uniqueCode,
    type: renderType,
    materialMark: material.materialMark,
    materialCode: material.materialCode,
    description: material.description,
    spec: material.diameter,
    start,
    end,
  }
  if (renderType === 'elbow') {
    const alongX = Math.abs(end[0] - start[0]) >= Math.abs(end[2] - start[2])
    const halfCross = crossSpan / 2
    const elbowStart = alongX
      ? [start[0], start[1], start[2] - halfCross]
      : [start[0] - halfCross, start[1], start[2]]
    const corner = alongX
      ? [end[0], end[1], end[2] - halfCross]
      : [end[0] - halfCross, end[1], end[2]]
    const elbowEnd = alongX
      ? [end[0], end[1], end[2] + halfCross]
      : [end[0] + halfCross, end[1], end[2]]
    component.start = elbowStart
    component.end = elbowEnd
    component.segments = [
      { start: elbowStart, end: corner },
      { start: corner, end: elbowEnd },
    ]
  }
  if (renderType === 'reducer') {
    component.startSpec = material.diameter
    component.endSpec = parsePositiveNumber(material.diameter) * 0.65
  }
  const renderedObject = pipeRenderer.createComponentObject(component)
  if (!renderedObject) return null
  let object = renderedObject
  if (renderedObject.children.length === 1 && renderedObject.children[0].isMesh) {
    renderedObject.updateMatrix()
    object = renderedObject.children[0]
    renderedObject.remove(object)
    object.applyMatrix4(renderedObject.matrix)
  }
  object.name = material.uniqueCode
  object.userData.kind = 'today-yard-material'
  object.userData.pipeMaterial = material
  object.userData.renderType = renderType
  object.userData.usesFallbackElbow = usesFallbackElbow
  object.traverse((child) => {
    if (!child.isMesh) return
    const sourceMaterials = Array.isArray(child.material) ? child.material : [child.material]
    const clonedMaterials = sourceMaterials.map((sourceMaterial) => {
      const cloned = sourceMaterial.clone()
      if (usesFallbackElbow) cloned.color?.setHex(0xef4444)
      cloned.roughness = 0.48
      cloned.metalness = 0.72
      return cloned
    })
    child.material = Array.isArray(child.material) ? clonedMaterials : clonedMaterials[0]
    child.castShadow = true
    child.receiveShadow = true
    child.userData.pipeMaterial = material
    child.userData.renderType = renderType
    child.userData.usesFallbackElbow = usesFallbackElbow
  })
  return object
}

function renderTodayPipeMaterials() {
  clearRawMaterialModels()
  const materials = [...(todayMaterialPayload.value.materials || [])].sort(compareYardMaterials)
  if (!factoryModel || !materials.length) {
    if (factoryModel) {
      countModelStats(factoryModel)
      buildModelTree(factoryModel)
    }
    return
  }

  const yard = findFactoryObjectByName('碳钢管道原材料堆场')
  if (!yard) {
    materialError.value = t('carbonSteelYardMissing')
    return
  }

  factoryModel.updateMatrixWorld(true)
  const yardBox = new THREE.Box3().setFromObject(yard)
  if (yardBox.isEmpty()) {
    materialError.value = t('carbonSteelYardMissing')
    return
  }
  const surfaceObject = findObjectByNameFrom(yard, 'text010') || findObjectByNameFrom(factoryModel, 'text010')
  const surfaceBox = surfaceObject ? new THREE.Box3().setFromObject(surfaceObject) : null
  const contactY = surfaceBox && !surfaceBox.isEmpty() ? surfaceBox.min.y : yardBox.max.y
  if (surfaceObject) {
    hiddenMaterialSurface = surfaceObject
    surfaceObject.traverse((object) => {
      hiddenMaterialSurfaceVisibility.set(object.id, object.visible)
      object.userData.hiddenForTodayPipeMaterials = true
      object.visible = false
    })
  }

  const placementBox = yardBox.clone()
  const placementSize = placementBox.getSize(new THREE.Vector3())
  const pipeAlongX = placementSize.x >= placementSize.z
  const factoryWorldScale = factoryModel.getWorldScale(new THREE.Vector3())
  const millimeterScale = Math.max(factoryWorldScale.x, factoryWorldScale.y, factoryWorldScale.z)
  const materialSizes = materials.map((material) => {
    const type = normalizePipeComponentType({
      materialMark: material.materialMark,
      materialCode: material.materialCode,
      description: material.description,
    })
    const radius = pipeOutsideDiameterMillimeters(material.diameter) * millimeterScale / 2
    const fittingSpan = Math.max(radius * 6, 200 * millimeterScale)
    return {
      type,
      radius,
      length: type === 'pipe'
        ? materialLengthMillimeters(material) * millimeterScale
        : fittingSpan,
      crossSpan: type === 'pipe' ? radius * 2 : fittingSpan,
    }
  })
  const maxRadius = Math.max(...materialSizes.map((item) => item.radius), 0.001)
  const maxHeight = Math.max(...materialSizes.map((item) => item.crossSpan), maxRadius * 2)
  const gap = maxRadius * 2
  const edgeMargin = Math.max(maxRadius * 2, Math.min(placementSize.x, placementSize.z) * 0.06)
  const longMin = (pipeAlongX ? placementBox.min.x : placementBox.min.z) + edgeMargin
  const longMax = (pipeAlongX ? placementBox.max.x : placementBox.max.z) - edgeMargin
  const crossMin = (pipeAlongX ? placementBox.min.z : placementBox.min.x) + edgeMargin
  const crossMax = (pipeAlongX ? placementBox.max.z : placementBox.max.x) - edgeMargin
  let longCursor = longMin
  let crossCursor = crossMin
  let laneThickness = 0
  let layer = 0

  rawMaterialGroup = new THREE.Group()
  rawMaterialGroup.name = t('todayPipeMaterialModels')
  rawMaterialGroup.userData.kind = 'today-pipe-material-group'
  scene.add(rawMaterialGroup)

  materials.forEach((material, index) => {
    const materialSize = materialSizes[index]
    const radius = materialSize.radius
    const availableLength = Math.max(longMax - longMin, maxRadius * 2)
    const length = materialSize.length || availableLength * 0.7
    const crossSpan = materialSize.crossSpan

    if (longCursor > longMin && longCursor + length > longMax) {
      longCursor = longMin
      crossCursor += laneThickness + gap
      laneThickness = 0
    }
    if (crossCursor + crossSpan > crossMax) {
      layer += 1
      longCursor = longMin
      crossCursor = crossMin
      laneThickness = 0
    }

    const longCenter = longCursor + length / 2
    const crossCenter = crossCursor + crossSpan / 2
    const y = contactY + radius + layer * maxHeight * 1.2
    const start = pipeAlongX
      ? [longCenter - length / 2, y, crossCenter]
      : [crossCenter, y, longCenter - length / 2]
    const end = pipeAlongX
      ? [longCenter + length / 2, y, crossCenter]
      : [crossCenter, y, longCenter + length / 2]
    const object = createYardMaterialObject(
      material,
      start,
      end,
      radius,
      crossSpan,
    )
    if (object) rawMaterialGroup.add(object)
    longCursor += length + gap
    laneThickness = Math.max(laneThickness, crossSpan)
  })

  rawMaterialGroup.updateMatrixWorld(true)
  factoryModel.attach(rawMaterialGroup)
  factoryModel.updateMatrixWorld(true)
  materialError.value = ''
  countModelStats(factoryModel)
  buildModelTree(factoryModel)
}

async function loadTodayPipeMaterials() {
  todayMaterialPayload.value = { date: '', total: 0, materials: [], weldingPlan: null }
  materialError.value = ''
  if (!selectedProjectId.value) {
    materialError.value = t('selectProjectForFactoryMaterials')
    renderTodayPipeMaterials()
    return
  }
  materialLoading.value = true
  try {
    todayMaterialPayload.value = await fetchTodayPipeMaterials(selectedProjectParams())
    renderTodayPipeMaterials()
    if (selectedNodeId.value) refreshSelectionAppearanceNow()
  } catch (error) {
    materialError.value = t('factoryMaterialsLoadFailed', { message: error.message })
    renderTodayPipeMaterials()
  } finally {
    materialLoading.value = false
  }
}

function saveDefaultView() {
  defaultView = {
    position: camera.position.clone(),
    target: controls.target.clone(),
    near: camera.near,
    far: camera.far,
    minDistance: controls.minDistance,
    maxDistance: controls.maxDistance,
  }
}

function materialsForMesh(mesh) {
  if (!mesh.material) return []
  return Array.isArray(mesh.material) ? mesh.material : [mesh.material]
}

function selectedMeshIdSetForObject(object) {
  const selectedMeshIds = new Set()
  object?.traverse((child) => {
    if (child.isMesh) selectedMeshIds.add(child.id)
  })
  return selectedMeshIds
}

function updateMeshVisibility() {
  if (!factoryModel) return
  const selectedObject = selectedNodeId.value ? modelObjectsById.get(selectedNodeId.value) : null
  const selectedMeshIds = selectedMeshIdSetForObject(selectedObject)

  factoryModel.traverse((child) => {
    if (!child.isMesh) return
    if (child.userData?.hiddenForTodayPipeMaterials) {
      child.visible = false
      return
    }
    child.visible = !isolateSelection.value || !selectedMeshIds.size || selectedMeshIds.has(child.id)
  })
}

function restoreAffectedMeshes() {
  affectedMeshes.forEach((mesh) => {
    materialsForMesh(mesh).forEach((material) => {
      const original = material.userData?.factoryOriginalHighlight
      if (!original) return
      if (material.color && original.color) material.color.copy(original.color)
      if (material.emissive && original.emissive) material.emissive.copy(original.emissive)
      material.depthWrite = original.depthWrite
      material.opacity = original.opacity
      material.transparent = original.transparent
      material.needsUpdate = true
      delete material.userData.factoryOriginalHighlight
    })
  })
  affectedMeshes.clear()
}

function rememberMaterial(material) {
  if (material.userData?.factoryOriginalHighlight) return
  material.userData.factoryOriginalHighlight = {
    color: material.color?.clone(),
    emissive: material.emissive?.clone(),
    opacity: material.opacity,
    transparent: material.transparent,
    depthWrite: material.depthWrite,
  }
}

function applySelectedMaterial(mesh) {
  affectedMeshes.add(mesh)
  materialsForMesh(mesh).forEach((material) => {
    rememberMaterial(material)
    if (material.emissive) material.emissive.setHex(0xffc107)
    if (material.color) material.color.lerp(new THREE.Color(0xffd54f), 0.45)
    material.opacity = 1
    material.transparent = false
    material.depthWrite = true
    material.needsUpdate = true
  })
}

function applyContextMaterial(mesh) {
  affectedMeshes.add(mesh)
  materialsForMesh(mesh).forEach((material) => {
    rememberMaterial(material)
    material.opacity = 0.18
    material.transparent = true
    material.depthWrite = false
    material.needsUpdate = true
  })
}

function collectSelectedMeshes(object) {
  const selectedMeshes = []
  const selectedMeshIds = new Set()
  object.traverse((child) => {
    if (!child.isMesh) return
    selectedMeshes.push(child)
    selectedMeshIds.add(child.id)
  })
  return { selectedMeshes, selectedMeshIds }
}

function collectOcclusionSamplePoints(object, selectedMeshes) {
  const samplePoints = []
  const box = new THREE.Box3().setFromObject(object)
  if (!box.isEmpty()) {
    const center = box.getCenter(new THREE.Vector3())
    samplePoints.push(center)
    const min = box.min
    const max = box.max
    ;[
      new THREE.Vector3(min.x, min.y, min.z),
      new THREE.Vector3(min.x, min.y, max.z),
      new THREE.Vector3(min.x, max.y, min.z),
      new THREE.Vector3(min.x, max.y, max.z),
      new THREE.Vector3(max.x, min.y, min.z),
      new THREE.Vector3(max.x, min.y, max.z),
      new THREE.Vector3(max.x, max.y, min.z),
      new THREE.Vector3(max.x, max.y, max.z),
      new THREE.Vector3(center.x, center.y, min.z),
      new THREE.Vector3(center.x, center.y, max.z),
      new THREE.Vector3(min.x, center.y, center.z),
      new THREE.Vector3(max.x, center.y, center.z),
      new THREE.Vector3(center.x, min.y, center.z),
      new THREE.Vector3(center.x, max.y, center.z),
    ].forEach((point) => samplePoints.push(point))
  }

  const meshStep = Math.max(1, Math.ceil(selectedMeshes.length / 12))
  for (let index = 0; index < selectedMeshes.length; index += meshStep) {
    const mesh = selectedMeshes[index]
    const meshBox = new THREE.Box3().setFromObject(mesh)
    if (!meshBox.isEmpty()) {
      samplePoints.push(meshBox.getCenter(new THREE.Vector3()))
    } else {
      samplePoints.push(mesh.getWorldPosition(new THREE.Vector3()))
    }
  }

  return samplePoints
}

function collectOccludingMeshes(object, selectedMeshes, selectedMeshIds) {
  if (!factoryModel || !camera) return new Set()

  const occludingMeshes = new Set()
  const samplePoints = collectOcclusionSamplePoints(object, selectedMeshes)
  const samplePointer = new THREE.Vector2()

  samplePoints.forEach((point) => {
    const projected = point.clone().project(camera)
    if (
      !Number.isFinite(projected.x)
      || !Number.isFinite(projected.y)
      || !Number.isFinite(projected.z)
      || projected.z < -1
      || projected.z > 1
    ) {
      return
    }

    samplePointer.set(projected.x, projected.y)
    raycaster.near = 0
    raycaster.far = Infinity
    raycaster.setFromCamera(samplePointer, camera)

    const selectedHits = raycaster.intersectObject(object, true)
      .filter((intersection) => intersection.object?.isMesh && intersection.object.visible && selectedMeshIds.has(intersection.object.id))
    if (!selectedHits.length) return

    const targetDistance = selectedHits[0].distance
    const blockers = []
    const sceneHits = raycaster.intersectObject(factoryModel, true)

    for (const intersection of sceneHits) {
      const mesh = intersection.object
      if (!mesh?.isMesh || !mesh.visible) continue
      if (intersection.distance >= targetDistance - 0.01) break
      if (selectedMeshIds.has(mesh.id)) break
      blockers.push(mesh)
    }

    blockers.forEach((mesh) => occludingMeshes.add(mesh))
  })

  return occludingMeshes
}

function updateSelectionAppearance(object) {
  restoreAffectedMeshes()
  const { selectedMeshes, selectedMeshIds } = collectSelectedMeshes(object)
  selectedMeshes.forEach((mesh) => applySelectedMaterial(mesh))
  const occludingMeshes = collectOccludingMeshes(object, selectedMeshes, selectedMeshIds)
  occludingMeshes.forEach((mesh) => applyContextMaterial(mesh))
  if (!selectionBox) {
    selectionBox = new THREE.BoxHelper(object, 0xf59e0b)
    selectionBox.name = 'FactorySelectionBox'
    scene.add(selectionBox)
  } else {
    selectionBox.setFromObject(object)
  }
  selectionBox.visible = true
}

function refreshSelectionAppearanceNow(nodeId = selectedNodeId.value) {
  if (!nodeId) return
  const object = modelObjectsById.get(nodeId)
  if (!object) return
  updateMeshVisibility()
  updateSelectionAppearance(object)
  syncSelectionInfoCard(object)
  selectionAppearanceDirty = false
  selectionRefreshDueAt = 0
}

function requestSelectionAppearanceRefresh() {
  if (!selectedNodeId.value) return
  selectionAppearanceDirty = true
  selectionRefreshDueAt = performance.now() + selectionRefreshDelayMs
}

function focusObject(object) {
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) return

  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const maxSize = Math.max(size.x, size.y, size.z, 1)
  const fov = THREE.MathUtils.degToRad(camera.fov)
  const fitDistance = Math.max(maxSize * 1.8, maxSize / (2 * Math.tan(fov / 2)))
  const direction = camera.position.clone().sub(controls.target)
  if (direction.lengthSq() === 0) direction.set(1, 0.75, 1)
  direction.normalize()

  camera.position.copy(center).add(direction.multiplyScalar(fitDistance * 1.25))
  controls.target.copy(center)
  camera.near = Math.max(0.01, fitDistance / 1000)
  camera.far = Math.max(10000, fitDistance * 1000)
  camera.updateProjectionMatrix()
  controls.minDistance = 0.3
  controls.maxDistance = Infinity
  controls.update()
}

function expandTreeAncestors(nodeId) {
  const next = new Set(expandedNodeIds.value)
  let parentId = parentIdsByObjectId.get(nodeId)
  while (parentId !== undefined) {
    next.add(parentId)
    parentId = parentIdsByObjectId.get(parentId)
  }
  expandedNodeIds.value = next
}

function scrollTreeNodeIntoView(nodeId) {
  nextTick(() => {
    const row = treeList.value?.querySelector(`[data-node-id="${nodeId}"]`)
    row?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  })
}

function selectModelNode(nodeId, { revealInTree = false } = {}) {
  const object = modelObjectsById.get(nodeId)
  if (!object) return
  if (selectedNodeId.value === nodeId) {
    clearSelection()
    return
  }
  if (revealInTree) expandTreeAncestors(nodeId)
  selectedNodeId.value = nodeId
  focusObject(object)
  refreshSelectionAppearanceNow(nodeId)
  if (revealInTree) scrollTreeNodeIntoView(nodeId)
}

function selectTreeNode(nodeId) {
  selectModelNode(nodeId)
}

function toggleTreeNode(node, event) {
  event?.stopPropagation()
  if (treeSearchText.value.trim()) return
  const next = new Set(expandedNodeIds.value)
  if (next.has(node.id)) {
    next.delete(node.id)
  } else {
    next.add(node.id)
  }
  expandedNodeIds.value = next
}

function loadFactoryModel() {
  loading.value = true
  errorMessage.value = ''
  loadProgress.value = {
    loaded: 0,
    total: 0,
    percent: 0,
    computable: false,
  }
  const loader = new FBXLoader()
  loader.load(
    '/models/prefab-factory.fbx',
    (model) => {
      clearSelection()
      factoryModel = model
      prepareModel(factoryModel)
      scene.add(factoryModel)
      renderTodayPipeMaterials()
      loading.value = false
    },
    (event) => {
      const total = Number(event.total || 0)
      const loaded = Number(event.loaded || 0)
      const computable = total > 0
      loadProgress.value = {
        loaded,
        total,
        percent: computable ? Math.min(100, Math.round((loaded / total) * 100)) : 0,
        computable,
      }
    },
    (error) => {
      errorMessage.value = t('factoryModelLoadFailed', { message: error?.message || error })
      loading.value = false
    },
  )
}

function clearSelection() {
  selectedNodeId.value = null
  isolateSelection.value = false
  selectionAppearanceDirty = false
  selectionRefreshDueAt = 0
  updateMeshVisibility()
  restoreAffectedMeshes()
  if (selectionBox) selectionBox.visible = false
  if (selectionInfoSprite) selectionInfoSprite.visible = false
  if (selectionInfoLeaderLine) selectionInfoLeaderLine.visible = false
}

function hitTestModel(event) {
  if (!factoryModel || !renderer || !camera) return null
  const rect = renderer.domElement.getBoundingClientRect()
  if (!rect.width || !rect.height) return null

  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
  raycaster.setFromCamera(pointer, camera)

  const intersections = raycaster.intersectObject(factoryModel, true)
  return intersections.find((intersection) => intersection.object?.isMesh && intersection.object.visible)?.object || null
}

function onScenePointerDown(event) {
  pointerDown.x = event.clientX
  pointerDown.y = event.clientY
  pointerDown.button = event.button
  pointerDown.active = true
}

function onScenePointerUp(event) {
  if (!pointerDown.active) return
  pointerDown.active = false
  if (pointerDown.button !== 0 || event.button !== 0) return

  const moveDistance = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y)
  if (moveDistance > 5) return

  const pickedObject = hitTestModel(event)
  if (!pickedObject) return
  selectModelNode(pickedObject.id, { revealInTree: true })
}

function resizeRenderer() {
  if (!sceneHost.value || !renderer || !camera) return
  const width = sceneHost.value.clientWidth
  const height = sceneHost.value.clientHeight
  renderer.setSize(width, height, false)
  camera.aspect = width / Math.max(height, 1)
  camera.updateProjectionMatrix()
}

function animate() {
  controls?.update()
  if (
    selectionAppearanceDirty
    && selectedNodeId.value
    && performance.now() >= selectionRefreshDueAt
  ) {
    refreshSelectionAppearanceNow()
  }
  if (showSelectionInfoCard.value && selectedNodeId.value) {
    const object = modelObjectsById.get(selectedNodeId.value)
    if (object) updateSelectionInfoCardPosition(object)
  }
  renderer?.render(scene, camera)
  animationFrame = requestAnimationFrame(animate)
}

function resetCamera() {
  if (defaultView) {
    clearSelection()
    camera.position.copy(defaultView.position)
    controls.target.copy(defaultView.target)
    camera.near = defaultView.near
    camera.far = defaultView.far
    camera.updateProjectionMatrix()
    controls.minDistance = defaultView.minDistance
    controls.maxDistance = defaultView.maxDistance
    controls.update()
    return
  }
  camera.position.set(18, 14, 18)
  controls.target.set(0, 2, 0)
  controls.update()
}

function toggleIsolateSelection() {
  if (!selectedNodeId.value) return
  isolateSelection.value = !isolateSelection.value
  refreshSelectionAppearanceNow()
}

function toggleSelectionInfoCard() {
  showSelectionInfoCard.value = !showSelectionInfoCard.value
  if (!showSelectionInfoCard.value) {
    if (selectionInfoSprite) selectionInfoSprite.visible = false
    if (selectionInfoLeaderLine) selectionInfoLeaderLine.visible = false
    return
  }
  if (selectedNodeId.value) refreshSelectionAppearanceNow()
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`
}

onMounted(() => {
  setupScene()
  resizeRenderer()
  loadFactoryModel()
  loadTodayPipeMaterials()
  resizeObserver = new ResizeObserver(resizeRenderer)
  resizeObserver.observe(sceneHost.value)
  window.addEventListener('resize', resizeRenderer)
  renderer.domElement.addEventListener('pointerdown', onScenePointerDown)
  renderer.domElement.addEventListener('pointerup', onScenePointerUp)
  controls.addEventListener('change', requestSelectionAppearanceRefresh)
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  selectionAppearanceDirty = false
  selectionRefreshDueAt = 0
  window.removeEventListener('resize', resizeRenderer)
  renderer?.domElement?.removeEventListener('pointerdown', onScenePointerDown)
  renderer?.domElement?.removeEventListener('pointerup', onScenePointerUp)
  resizeObserver?.disconnect()
  controls?.removeEventListener('change', requestSelectionAppearanceRefresh)
  controls?.dispose()
  if (factoryModel) {
    disposeObject(factoryModel)
  }
  rawMaterialGroup = null
  selectionBox?.geometry?.dispose()
  selectionBox?.material?.dispose()
  selectionInfoLeaderLine?.geometry?.dispose()
  selectionInfoLeaderLine?.material?.dispose()
  selectionInfoSprite?.material?.map?.dispose?.()
  selectionInfoSprite?.material?.dispose?.()
  modelObjectsById.clear()
  parentIdsByObjectId.clear()
  renderer?.dispose()
  renderer?.domElement?.remove()
})
</script>

<template>
  <v-card class="factory-page" :loading="loading" rounded="lg" variant="flat" tag="main">
      <template #loader>
        <v-progress-linear
          :model-value="loadProgress.computable ? loadProgress.percent : undefined"
          :indeterminate="!loadProgress.computable"
          color="primary"
          height="4"
        />
      </template>

    <div class="factory-toolbar">
      <div class="factory-title">
        <h1>{{ t('prefabFactory') }}</h1>
        <v-tooltip location="bottom" open-delay="120" max-width="320">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              class="factory-title-info"
              icon="mdi-information-outline"
              size="small"
              variant="text"
            />
          </template>
          <span>{{ t('prefabFactoryDescription') }}</span>
        </v-tooltip>
      </div>
      <div class="factory-toolbar-actions">
        <v-tooltip location="bottom" open-delay="120">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              class="factory-tool-button"
              icon="mdi-crosshairs-gps"
              variant="tonal"
              @click="resetCamera"
            />
          </template>
          <span>{{ t('resetView') }}</span>
        </v-tooltip>

        <v-tooltip location="bottom" open-delay="120">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              :class="['factory-tool-button', { 'is-active': showSelectionInfoCard }]"
              :icon="showSelectionInfoCard ? 'mdi-card-text-outline' : 'mdi-card-off-outline'"
              :variant="showSelectionInfoCard ? 'flat' : 'tonal'"
              @click="toggleSelectionInfoCard"
            />
          </template>
          <span>{{ showSelectionInfoCard ? t('hideModelInfoCard') : t('showModelInfoCard') }}</span>
        </v-tooltip>

        <v-tooltip location="bottom" open-delay="120">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              :class="['factory-tool-button', { 'is-active': isolateSelection, 'is-disabled': !selectedNodeId }]"
              :aria-disabled="!selectedNodeId"
              :icon="isolateSelection ? 'mdi-eye-off' : 'mdi-eye-off-outline'"
              :variant="isolateSelection ? 'flat' : 'tonal'"
              @click="toggleIsolateSelection"
            />
          </template>
          <span>{{ isolateSelectionTooltip }}</span>
        </v-tooltip>
      </div>
    </div>

    <div class="factory-workspace">
      <v-card class="factory-viewer-card" rounded="lg" variant="flat">
        <div class="factory-viewer-body">
          <div ref="sceneHost" class="factory-scene" />
          <div v-if="errorMessage" class="factory-scene-overlay is-error">
            {{ errorMessage }}
          </div>
          <div v-else-if="materialError" class="factory-material-notice">
            {{ materialError }}
          </div>
        </div>
      </v-card>

      <v-card class="factory-tree-card" rounded="lg" variant="flat">
        <v-card-item class="factory-card-item factory-tree-head">
          <template #title>{{ t('modelStructure') }}</template>
          <template #append>
            <span class="factory-tree-count">
              {{ treeSearchText.trim() ? `${treeResultCount} / ${modelStats.objects}` : `${visibleTreeNodes.length} / ${modelStats.objects}` }}
            </span>
          </template>
        </v-card-item>

        <div class="factory-tree-search">
          <v-text-field
            v-model="treeSearchText"
            density="compact"
            hide-details
            clearable
            variant="outlined"
            :placeholder="t('searchSubstructure')"
            prepend-inner-icon="mdi-magnify"
          />
        </div>
        <div v-if="loading" class="factory-tree-empty">{{ t('modelLoading') }}</div>
        <div v-else-if="errorMessage" class="factory-tree-empty">{{ t('noStructureTree') }}</div>
        <div v-else-if="treeSearchText.trim() && !visibleTreeNodes.length" class="factory-tree-empty">{{ t('noMatchingStructure') }}</div>
        <div v-else ref="treeList" class="factory-tree-list">
          <button
            v-for="node in visibleTreeNodes"
            :key="node.id"
            type="button"
            :data-node-id="node.id"
            :class="[
              'factory-tree-row',
              {
                'is-active': selectedNodeId === node.id,
                'is-search-path': node.isSearchPath && !node.isSearchMatch,
                'is-search-match': node.isSearchMatch,
              },
            ]"
            :style="{ paddingLeft: `${10 + node.depth * 16}px` }"
            @click="selectTreeNode(node.id)"
          >
            <span
              :class="['factory-tree-toggle', { 'is-hidden': !node.children.length || treeSearchText.trim() }]"
              @click="toggleTreeNode(node, $event)"
            >
              <v-icon
                :icon="expandedNodeIds.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                size="16"
              />
            </span>
            <v-icon :icon="node.meshCount ? 'mdi-cube-outline' : 'mdi-folder-outline'" size="16" />
            <span class="factory-tree-name" :title="node.name">{{ node.name }}</span>
            <small v-if="node.meshCount">{{ node.meshCount }}</small>
          </button>
        </div>
      </v-card>
    </div>
  </v-card>

  <v-card class="factory-info-card" rounded="lg" variant="flat">
    <v-card-item class="factory-card-item factory-info-head">
      <template #title>{{ selectedInfoCardTitle }}</template>
      <template #append>
        <span class="factory-info-count">
          {{ selectedInfoCardBadge }}
        </span>
      </template>
    </v-card-item>

    <div v-if="selectedNodeInfo" class="factory-info-body">
      <div v-if="selectedNodeInfo.materialInfo" class="factory-material-details">
        <div><span>{{ t('materialUniqueCode') }}</span><strong>{{ selectedNodeInfo.materialInfo.uniqueCode }}</strong></div>
        <div><span>{{ t('materialCode') }}</span><strong>{{ selectedNodeInfo.materialInfo.materialCode || '-' }}</strong></div>
        <div><span>{{ t('materialQuantity') }}</span><strong>{{ selectedNodeInfo.materialInfo.quantity || '-' }} {{ selectedNodeInfo.materialInfo.unitName }}</strong></div>
        <div><span>{{ t('diameter') }}</span><strong>{{ selectedNodeInfo.materialInfo.diameter || '-' }}</strong></div>
        <div><span>{{ t('wallThickness') }}</span><strong>{{ selectedNodeInfo.materialInfo.wallThickness || '-' }}</strong></div>
        <div><span>{{ t('material') }}</span><strong>{{ selectedNodeInfo.materialInfo.material || '-' }}</strong></div>
        <div><span>{{ t('materialPaint') }}</span><strong>{{ selectedNodeInfo.materialInfo.paint || '-' }}</strong></div>
        <div><span>{{ t('materialDescription') }}</span><strong>{{ selectedNodeInfo.materialInfo.description || '-' }}</strong></div>
      </div>
      <template v-else-if="selectedNodeInfo.todayMaterialGroup">
        <div class="factory-info-summary">
          <strong>{{ t('todayPipeMaterialModels') }}</strong>
          <span>{{ todayMaterialSummary.date }}</span>
        </div>
        <div class="factory-info-grid factory-material-summary-grid">
          <div><span>{{ t('materialItemCount') }}</span><strong>{{ todayMaterialSummary.total }}</strong></div>
          <div><span>{{ t('materialCodeCount') }}</span><strong>{{ todayMaterialSummary.materialCodeCount }}</strong></div>
          <div><span>{{ t('pipeItemCount') }}</span><strong>{{ todayMaterialSummary.pipeCount }}</strong></div>
          <div><span>{{ t('fittingItemCount') }}</span><strong>{{ todayMaterialSummary.fittingCount }}</strong></div>
        </div>
        <div class="factory-material-table">
          <DataVTable
            :records="todayMaterialTableRows"
            :columns="todayMaterialTableColumns"
            :height="460"
            :empty-text="t('noData')"
          />
        </div>
      </template>
      <template v-else-if="selectedNodeInfo.workshopEquipment">
        <div class="factory-info-summary">
          <strong>{{ t('workshopOneEquipment') }}</strong>
          <span>{{ selectedNodeInfo.weldingPlan?.available ? selectedNodeInfo.weldingPlan.date : t('noTodayWeldingPlan') }}</span>
        </div>
        <div class="factory-info-grid">
          <div><span>{{ t('weldingOrderCount') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.orderCount || 0 }}</strong></div>
          <div><span>{{ t('weldCount') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.weldCount || 0 }}</strong></div>
          <div><span>{{ t('planDiameterTotal') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.diameterTotal || 0 }}</strong></div>
          <div><span>{{ t('completedCount') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.completedCount || 0 }}</strong></div>
          <div><span>{{ t('segmentCount') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.segmentCount || 0 }}</strong></div>
          <div><span>{{ t('pipelineCount') }}</span><strong>{{ selectedNodeInfo.weldingPlan?.pipelineCount || 0 }}</strong></div>
          <div class="factory-plan-orders">
            <span>{{ t('weldingOrderNumbers') }}</span>
            <strong>{{ selectedNodeInfo.weldingPlan?.orderNumbers?.join('、') || '-' }}</strong>
          </div>
        </div>
        <div v-if="weldingPlanSheets.length" class="factory-welding-plan">
          <v-tabs
            v-model="selectedWeldingSheet"
            class="factory-welding-tabs"
            color="primary"
            density="compact"
            show-arrows
          >
            <v-tab
              v-for="sheet in weldingPlanSheets"
              :key="sheet.name"
              :value="sheet.name"
            >
              {{ sheet.name }}（{{ sheet.total }}）
            </v-tab>
          </v-tabs>
          <DataVTable
            :key="selectedWeldingSheet"
            :records="weldingPlanTableRows"
            :columns="weldingPlanTableColumns"
            :height="420"
            :empty-text="t('noData')"
          />
        </div>
        <div v-else class="factory-info-empty">{{ t('noTodayWeldingPlan') }}</div>
      </template>
      <template v-else>
        <div class="factory-info-summary">
          <strong :title="selectedNodeInfo.name">{{ selectedNodeInfo.name }}</strong>
          <span>{{ t('meshCount') }} {{ selectedNodeInfo.meshCount }}</span>
        </div>
        <div class="factory-info-grid">
          <div><span>{{ t('type') }}</span><strong>{{ selectedNodeInfo.type }}</strong></div>
          <div><span>{{ t('children') }}</span><strong>{{ selectedNodeInfo.childCount }}</strong></div>
          <div><span>{{ t('dimensions') }}</span><strong>{{ selectedNodeInfo.sizeText }}</strong></div>
          <div><span>{{ t('center') }}</span><strong>{{ selectedNodeInfo.centerText }}</strong></div>
        </div>
      </template>
    </div>
    <div v-else class="factory-info-empty">{{ t('selectSubstructureHint') }}</div>
  </v-card>
</template>

<style scoped>
.factory-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100vh - 104px);
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f6f7f9;
  padding: 14px;
}

.factory-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.factory-viewer-card,
.factory-tree-card {
  display: flex;
  flex-direction: column;
  background: #ffffff;
  width: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, .34);
  box-shadow: 0 10px 24px rgba(15, 23, 42, .08);
}

.factory-viewer-card,
.factory-tree-card {
  height: 100%;
}

.factory-viewer-body {
  position: relative;
  flex: 1;
  display: flex;
  min-height: 0;
  padding: 0;
}

.factory-scene {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.factory-scene :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.factory-toolbar {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 2px 2px 4px;
}

.factory-title {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.factory-toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex: 0 0 auto;
}

.factory-material-notice {
  position: absolute;
  top: 12px;
  left: 50%;
  z-index: 2;
  max-width: min(560px, calc(100% - 32px));
  transform: translateX(-50%);
  border: 1px solid rgba(217, 119, 6, .32);
  border-radius: 6px;
  background: rgba(255, 251, 235, .94);
  padding: 8px 12px;
  color: #92400e;
  font-size: 12px;
  box-shadow: 0 6px 18px rgba(15, 23, 42, .1);
}

.factory-title-info {
  color: #64748b;
}

.factory-tool-button {
  color: #334155;
}

.factory-tool-button.is-active {
  background: #0f172a !important;
  color: #ffffff !important;
}

.factory-tool-button.is-disabled {
  opacity: 0.48;
}

.factory-toolbar h1 {
  margin: 0;
  color: #0f172a;
  font-size: 22px;
  font-weight: 850;
  letter-spacing: 0;
}

.factory-toolbar span {
  display: block;
  margin-top: 4px;
  color: #475569;
  font-size: 13px;
}

.factory-tree-head {
  border-bottom: 1px solid rgba(148, 163, 184, .28);
}

.factory-tree-count {
  color: #64748b;
  font-size: 12px;
}

.factory-tree-search {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, .2);
}

.factory-tree-search :deep(.v-field) {
  border-radius: 6px;
  font-size: 12px;
}

.factory-tree-empty {
  display: grid;
  flex: 1;
  place-items: center;
  padding: 20px;
  color: #64748b;
  font-size: 13px;
}

.factory-tree-list {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 6px;
}

.factory-tree-row {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  min-height: 30px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #334155;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.factory-tree-row:hover {
  background: rgba(37, 99, 235, .08);
}

.factory-tree-row.is-active {
  background: rgba(245, 158, 11, .16);
  color: #92400e;
}

.factory-tree-row.is-search-path {
  color: #64748b;
}

.factory-tree-row.is-search-match:not(.is-active) {
  background: rgba(37, 99, 235, .08);
  color: #1d4ed8;
}

.factory-tree-toggle {
  display: inline-grid;
  flex: 0 0 16px;
  place-items: center;
  color: #64748b;
}

.factory-tree-toggle.is-hidden {
  visibility: hidden;
}

.factory-tree-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.factory-tree-row small {
  flex: 0 0 auto;
  min-width: 20px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(100, 116, 139, .12);
  color: #64748b;
  font-size: 10px;
  text-align: center;
}

.factory-scene-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(246, 247, 249, .74);
  color: #475569;
  font-size: 13px;
  text-align: center;
  pointer-events: none;
}

.factory-scene-overlay.is-error {
  color: #b91c1c;
}

.factory-info-card {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, .34);
  box-shadow: 0 10px 24px rgba(15, 23, 42, .08);
}

.factory-info-head {
  border-bottom: 1px solid rgba(148, 163, 184, .28);
}

.factory-info-count {
  color: #64748b;
  font-size: 12px;
}

.factory-info-body {
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
}

.factory-info-summary {
  display: flex;
  gap: 10px;
  align-items: baseline;
  min-width: 0;
}

.factory-info-summary strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #0f172a;
  font-size: 16px;
}

.factory-info-summary span {
  color: #64748b;
  font-size: 12px;
}

.factory-info-grid,
.factory-material-details {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.factory-material-table {
  margin-top: 14px;
  min-width: 0;
}

.factory-info-grid div,
.factory-material-details div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(241, 245, 249, .92);
}

.factory-info-grid span,
.factory-material-details span {
  color: #64748b;
  font-size: 12px;
}

.factory-info-grid strong,
.factory-material-details strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  word-break: break-word;
}

.factory-info-grid .factory-plan-orders {
  grid-column: span 2;
}

.factory-welding-plan {
  display: grid;
  gap: 10px;
  min-width: 0;
  margin-top: 4px;
}

.factory-welding-tabs {
  min-width: 0;
  border-bottom: 1px solid rgba(148, 163, 184, .28);
}

.factory-info-empty {
  padding: 18px 16px 20px;
  color: #64748b;
  font-size: 13px;
}

html[data-theme="dark"] .factory-page {
  border-color: #374151;
  background: #111827;
}

html[data-theme="dark"] .factory-viewer-card,
html[data-theme="dark"] .factory-tree-card {
  border-color: #374151;
  background: #111827;
  box-shadow: 0 10px 24px rgba(0, 0, 0, .24);
}

html[data-theme="dark"] .factory-info-card {
  border-color: #374151;
  background: #111827;
  box-shadow: 0 10px 24px rgba(0, 0, 0, .24);
}

html[data-theme="dark"] .factory-toolbar h1 {
  color: #f8fafc;
}

html[data-theme="dark"] .factory-toolbar span {
  color: #cbd5e1;
}

html[data-theme="dark"] .factory-title-info {
  color: #94a3b8;
}

html[data-theme="dark"] .factory-tool-button {
  color: #e2e8f0;
}

html[data-theme="dark"] .factory-tool-button.is-active {
  background: #e2e8f0;
  color: #111827;
}

html[data-theme="dark"] .factory-tree-head {
  border-bottom-color: rgba(71, 85, 105, .72);
}

html[data-theme="dark"] .factory-tree-search {
  border-bottom-color: rgba(71, 85, 105, .62);
}

html[data-theme="dark"] .factory-tree-count,
html[data-theme="dark"] .factory-tree-empty,
html[data-theme="dark"] .factory-tree-toggle,
html[data-theme="dark"] .factory-tree-row small {
  color: #94a3b8;
}

html[data-theme="dark"] .factory-tree-row {
  color: #e2e8f0;
}

html[data-theme="dark"] .factory-tree-row:hover {
  background: rgba(96, 165, 250, .14);
}

html[data-theme="dark"] .factory-tree-row.is-active {
  background: rgba(245, 158, 11, .22);
  color: #fcd34d;
}

html[data-theme="dark"] .factory-tree-row.is-search-match:not(.is-active) {
  background: rgba(96, 165, 250, .14);
  color: #93c5fd;
}

html[data-theme="dark"] .factory-info-head {
  border-bottom-color: rgba(71, 85, 105, .72);
}

html[data-theme="dark"] .factory-info-count,
html[data-theme="dark"] .factory-info-empty,
html[data-theme="dark"] .factory-info-summary span,
html[data-theme="dark"] .factory-info-grid span,
html[data-theme="dark"] .factory-material-details span {
  color: #94a3b8;
}

html[data-theme="dark"] .factory-info-summary strong,
html[data-theme="dark"] .factory-info-grid strong,
html[data-theme="dark"] .factory-material-details strong {
  color: #f8fafc;
}

html[data-theme="dark"] .factory-info-grid div,
html[data-theme="dark"] .factory-material-details div {
  background: rgba(30, 41, 59, .92);
}

html[data-theme="dark"] .factory-scene-overlay {
  background: rgba(17, 24, 39, .72);
  color: #cbd5e1;
}

html[data-theme="dark"] .factory-scene-overlay.is-error {
  color: #fca5a5;
}

@media (max-width: 900px) {
  .factory-workspace {
    grid-template-columns: 1fr;
  }

  .factory-viewer-card {
    min-height: 0;
  }

  .factory-scene {
    min-height: 360px;
  }

  .factory-toolbar {
    flex-direction: column;
  }

  .factory-title {
    width: 100%;
  }

  .factory-toolbar-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .factory-toolbar h1 {
    font-size: 18px;
  }

  .factory-tree-card {
    height: min(42vh, 360px);
  }

  .factory-info-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
