<script setup>
import * as THREE from 'three'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { t } from '../../services/pipecloudState'

const sceneHost = ref(null)
const treeList = ref(null)
const loading = ref(true)
const errorMessage = ref('')
const modelTree = ref([])
const selectedNodeId = ref(null)
const expandedNodeIds = ref(new Set())
const treeSearchText = ref('')
const loadProgress = ref({
  loaded: 0,
  total: 0,
  percent: 0,
  computable: false,
})
const isolateSelection = ref(false)
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

const selectedNodeInfo = computed(() => {
  if (!selectedNodeId.value) return null
  const object = modelObjectsById.get(selectedNodeId.value)
  if (!object) return null

  const box = new THREE.Box3().setFromObject(object)
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())

  return {
    id: object.id,
    name: modelNodeName(object, 0),
    type: object.type || 'Object3D',
    meshCount: countMeshes(object),
    childCount: object.children.length,
    sizeText: `${size.x.toFixed(2)} × ${size.y.toFixed(2)} × ${size.z.toFixed(2)}`,
    centerText: `${center.x.toFixed(2)}, ${center.y.toFixed(2)}, ${center.z.toFixed(2)}`,
  }
})

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

  ctx.fillStyle = '#0f172a'
  ctx.font = '700 26px Arial'
  ctx.fillText(clampText(info.name, 22), 30, 52)

  ctx.fillStyle = '#64748b'
  ctx.font = '500 15px Arial'
  ctx.fillText(info.type, 30, 78)

  ctx.fillStyle = '#f59e0b'
  ctx.fillRect(30, 95, 82, 4)

  const rows = [
    ['网格数', String(info.meshCount)],
    ['子项数', String(info.childCount)],
    ['尺寸', info.sizeText],
    ['中心', info.centerText],
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
  ctx.fillText('选中子结构信息', 30, 252)

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
  if (!object || !selectedNodeInfo.value) {
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
  if (selectedNodeId.value) {
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
    factoryModel.traverse((child) => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) {
        const materials = Array.isArray(child.material) ? child.material : [child.material]
        materials.forEach((material) => material.dispose?.())
      }
    })
  }
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
        </div>
      </v-card>

      <v-card class="factory-tree-card" rounded="lg" variant="flat">
        <v-card-item class="factory-card-item factory-tree-head">
          <template #title>模型结构</template>
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
            placeholder="搜索子结构名称"
            prepend-inner-icon="mdi-magnify"
          />
        </div>
        <div v-if="loading" class="factory-tree-empty">模型加载中</div>
        <div v-else-if="errorMessage" class="factory-tree-empty">暂无结构树</div>
        <div v-else-if="treeSearchText.trim() && !visibleTreeNodes.length" class="factory-tree-empty">无匹配结构</div>
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
      <template #title>选中子结构信息</template>
      <template #append>
        <span class="factory-info-count">{{ selectedNodeInfo ? selectedNodeInfo.type : '未选择' }}</span>
      </template>
    </v-card-item>

    <div v-if="selectedNodeInfo" class="factory-info-body">
      <div class="factory-info-summary">
        <strong :title="selectedNodeInfo.name">{{ selectedNodeInfo.name }}</strong>
        <span>网格数 {{ selectedNodeInfo.meshCount }}</span>
      </div>
      <div class="factory-info-grid">
        <div><span>类型</span><strong>{{ selectedNodeInfo.type }}</strong></div>
        <div><span>子项</span><strong>{{ selectedNodeInfo.childCount }}</strong></div>
        <div><span>尺寸</span><strong>{{ selectedNodeInfo.sizeText }}</strong></div>
        <div><span>中心</span><strong>{{ selectedNodeInfo.centerText }}</strong></div>
      </div>
    </div>
    <div v-else class="factory-info-empty">点击左侧结构树或三维模型中的子结构后，这里会展示对应信息。</div>
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

.factory-title-info {
  color: #64748b;
}

.factory-tool-button {
  color: #334155;
}

.factory-tool-button.is-active {
  background: #0f172a;
  color: #f8fafc;
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

.factory-info-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.factory-info-grid div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(241, 245, 249, .92);
}

.factory-info-grid span {
  color: #64748b;
  font-size: 12px;
}

.factory-info-grid strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  word-break: break-word;
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
html[data-theme="dark"] .factory-info-grid span {
  color: #94a3b8;
}

html[data-theme="dark"] .factory-info-summary strong,
html[data-theme="dark"] .factory-info-grid strong {
  color: #f8fafc;
}

html[data-theme="dark"] .factory-info-grid div {
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
