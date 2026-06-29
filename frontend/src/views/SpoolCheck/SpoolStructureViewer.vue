<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { createPipeComponentRenderer, normalizePipeComponent } from '../../services/pipeComponentRenderer'

const props = defineProps({
  spool: { type: Object, default: null },
})

const host = ref(null)
let scene = null
let camera = null
let renderer = null
let controls = null
let resizeObserver = null
let animationFrame = 0
let componentGroup = null

const components = computed(() => props.spool?.components || [])
const renderableCount = computed(() => components.value.filter((component) => componentPoints(component).length > 0).length)
const hasModel = computed(() => renderableCount.value > 0)

function initScene() {
  if (!host.value || renderer) return
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xf7f9fb)

  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100000)
  camera.position.set(18, 14, 22)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  host.value.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08

  scene.add(new THREE.HemisphereLight(0xffffff, 0xd7dee8, 2.4))
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.6)
  keyLight.position.set(16, 28, 20)
  scene.add(keyLight)
  const fillLight = new THREE.DirectionalLight(0xdbeafe, 1.1)
  fillLight.position.set(-18, 14, -12)
  scene.add(fillLight)

  const grid = new THREE.GridHelper(80, 40, 0x94a3b8, 0xd5dce6)
  grid.position.y = -0.02
  scene.add(grid)

  resizeObserver = new ResizeObserver(resizeScene)
  resizeObserver.observe(host.value)
  resizeScene()
  animate()
}

function resizeScene() {
  if (!host.value || !renderer || !camera) return
  const rect = host.value.getBoundingClientRect()
  const width = Math.max(rect.width, 1)
  const height = Math.max(rect.height, 1)
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate() {
  animationFrame = window.requestAnimationFrame(animate)
  controls?.update()
  renderer?.render(scene, camera)
}

function renderComponents() {
  if (!scene) return
  if (componentGroup) {
    scene.remove(componentGroup)
    disposeObject(componentGroup)
    componentGroup = null
  }
  const normalized = components.value.map((component) => normalizePipeComponent(component))
  const renderable = normalized.filter((component) => componentPoints(component).length > 0)
  if (!renderable.length) return

  const points = renderable.flatMap(componentPoints)
  const center = averagePoint(points)
  const bounds = pointBounds(points)
  const size = Math.max(bounds.maxRange, 1)
  const scale = Math.min(1, 34 / size)
  const connectionRefsByPoint = buildConnectionRefs(renderable)
  const pipeRenderer = createPipeComponentRenderer({
    center: new THREE.Vector3(center[0], center[1], center[2]),
    scale,
    defaultRadius: Math.max(size * scale * 0.008, 0.08),
    connectionRefsByPoint,
  })
  componentGroup = pipeRenderer.createComponentsGroup(renderable, { name: 'spool-components' })
  scene.add(componentGroup)
  frameObject(componentGroup)
}

function componentPoints(component) {
  const points = []
  if (isPoint(component.start)) points.push(component.start)
  if (isPoint(component.end)) points.push(component.end)
  if (isPoint(component.displayStart)) points.push(component.displayStart)
  for (const segment of component.segments || []) {
    if (isPoint(segment.start)) points.push(segment.start)
    if (isPoint(segment.end)) points.push(segment.end)
  }
  return points
}

function isPoint(point) {
  return Array.isArray(point)
    && point.length >= 3
    && point.slice(0, 3).every((value) => Number.isFinite(Number(value)))
}

function averagePoint(points) {
  if (!points.length) return [0, 0, 0]
  const total = points.reduce((sum, point) => [sum[0] + Number(point[0] || 0), sum[1] + Number(point[1] || 0), sum[2] + Number(point[2] || 0)], [0, 0, 0])
  return total.map((value) => value / points.length)
}

function pointBounds(points) {
  if (!points.length) return { maxRange: 1 }
  const mins = [Infinity, Infinity, Infinity]
  const maxs = [-Infinity, -Infinity, -Infinity]
  points.forEach((point) => {
    for (let index = 0; index < 3; index += 1) {
      const value = Number(point[index] || 0)
      mins[index] = Math.min(mins[index], value)
      maxs[index] = Math.max(maxs[index], value)
    }
  })
  return { maxRange: Math.max(maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2]) }
}

function buildConnectionRefs(items) {
  const refs = new Map()
  items.forEach((component) => {
    ;[component.start, component.end, component.displayStart].filter(isPoint).forEach((point) => {
      const key = point.map((value) => Number(value).toFixed(3)).join(',')
      const list = refs.get(key) || []
      list.push({ component })
      refs.set(key, list)
    })
  })
  return refs
}

function frameObject(object) {
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) return
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())
  const maxSize = Math.max(size.x, size.y, size.z, 1)
  camera.position.set(center.x + maxSize * 1.25, center.y + maxSize * 0.9, center.z + maxSize * 1.55)
  camera.near = Math.max(maxSize / 1000, 0.01)
  camera.far = maxSize * 50
  camera.updateProjectionMatrix()
  controls.target.copy(center)
  controls.update()
}

function disposeObject(object) {
  object.traverse((child) => {
    child.geometry?.dispose?.()
  })
}

onMounted(async () => {
  await nextTick()
  initScene()
  renderComponents()
})

watch(components, () => {
  nextTick(renderComponents)
})

onBeforeUnmount(() => {
  if (animationFrame) window.cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  controls?.dispose()
  if (componentGroup) disposeObject(componentGroup)
  renderer?.dispose()
  renderer?.domElement?.remove()
  scene = null
  camera = null
  renderer = null
  controls = null
})
</script>

<template>
  <div class="spool-structure-viewer">
    <div ref="host" class="spool-structure-canvas" />
    <div v-if="hasModel" class="spool-structure-status">
      <span>{{ props.spool?.lineNo || 'IDF' }}</span>
      <strong>{{ renderableCount }}/{{ components.length }}</strong>
    </div>
    <div v-if="!hasModel" class="spool-structure-empty">
      <v-icon icon="mdi-cube-off-outline" size="42" />
      <strong>暂无可渲染结构</strong>
      <span>请确认当前管段焊口包含材料唯一码、材料数量、外径或寸径等连接数据。</span>
    </div>
  </div>
</template>

<style scoped>
.spool-structure-viewer {
  position: relative;
  height: 560px;
  margin-top: 16px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f7f9fb;
}

.spool-structure-canvas {
  width: 100%;
  height: 100%;
}

.spool-structure-status {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  max-width: calc(100% - 24px);
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, #ffffff 88%, transparent);
  color: var(--muted);
  font-size: 12px;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
}

.spool-structure-status span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spool-structure-status strong {
  flex: 0 0 auto;
  color: var(--strong);
}

.spool-structure-empty {
  position: absolute;
  inset: 0;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 8px;
  background:
    linear-gradient(color-mix(in srgb, var(--line) 60%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--line) 60%, transparent) 1px, transparent 1px),
    color-mix(in srgb, var(--panel-soft) 86%, transparent);
  background-size: 48px 48px;
  color: var(--muted);
  text-align: center;
}

.spool-structure-empty strong {
  color: var(--strong);
  font-size: 15px;
}

.spool-structure-empty span {
  max-width: 420px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
