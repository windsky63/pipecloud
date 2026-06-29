import * as THREE from 'three'

const DEFAULT_TYPE_COLORS = {
  pipe: 0x0f8ccf,
  elbow: 0xf59e0b,
  branch: 0xec4899,
  olet: 0xec4899,
  reducer: 0xa78bfa,
  flange: 0xf97316,
  valve: 0xef4444,
  'angle-valve': 0xdc2626,
  'three-way-valve': 0xb91c1c,
  'four-way-valve': 0x991b1b,
  instrument: 0x06b6d4,
  'misc-component': 0x8b5cf6,
  trap: 0x78716c,
  filter: 0x0d9488,
  'flow-arrow': 0xff7a00,
  cap: 0xb8ad72,
  weld: 0x16a34a,
  gasket: 0x64748b,
  equipment: 0x14b8a6,
  component: 0x94a3b8,
}

const reusable = {
  direction: new THREE.Vector3(),
  quaternion: new THREE.Quaternion(),
  matrix: new THREE.Matrix4(),
  yAxis: new THREE.Vector3(0, 1, 0),
  zAxis: new THREE.Vector3(0, 0, 1),
}

const materialCache = new Map()

export function createPipeComponentRenderer(options = {}) {
  const center = options.center || new THREE.Vector3()
  const scale = Number.isFinite(options.scale) ? options.scale : 1
  const defaultRadius = Number.isFinite(options.defaultRadius) ? options.defaultRadius : 1
  const typeColors = { ...DEFAULT_TYPE_COLORS, ...(options.typeColors || {}) }
  const getRadius = options.getRadius || ((spec) => {
    const dn = Number(spec)
    return Number.isFinite(dn) && dn > 0 ? Math.max(defaultRadius * 0.75, dn * scale * 0.01) : defaultRadius
  })
  const toWorld = options.toWorld || ((point) => new THREE.Vector3(
    (point[0] - center.x) * scale,
    (point[2] - center.z) * scale,
    -(point[1] - center.y) * scale,
  ))
  const toWorldDirection = options.toWorldDirection || ((direction) => new THREE.Vector3(
    direction[0],
    direction[2],
    -direction[1],
  ).normalize())
  const connectionRefsByPoint = options.connectionRefsByPoint || new Map()

  return {
    createComponentObject(component, overrides = {}) {
      return createRenderableComponentObject(component, {
        defaultRadius,
        getRadius,
        toWorld,
        toWorldDirection,
        connectionRefsByPoint: overrides.connectionRefsByPoint || connectionRefsByPoint,
        typeColors,
        symbolMode: overrides.symbolMode || 'auto',
      })
    },
    createComponentsGroup(components, overrides = {}) {
      const group = new THREE.Group()
      group.name = overrides.name || 'pipe-components'
      components.forEach((component) => {
        const object = createRenderableComponentObject(component, {
          defaultRadius,
          getRadius,
          toWorld,
          toWorldDirection,
          connectionRefsByPoint: overrides.connectionRefsByPoint || connectionRefsByPoint,
          typeColors,
          symbolMode: overrides.symbolMode || 'auto',
        })
        if (object) group.add(object)
      })
      return group
    },
  }
}

export function createPipeComponentObject(component, options = {}) {
  return createPipeComponentRenderer(options).createComponentObject(component, options)
}

export function normalizePipeComponentType(component = {}) {
  const mark = String(component.materialMark || component.material_mark || component.mark || '').trim().toUpperCase()
  const text = [
    mark,
    component.materialCode,
    component.material_code,
    component.description,
    component.materialDescription,
    component.name,
  ].filter(Boolean).join(' ').toUpperCase()

  if (component.type && DEFAULT_TYPE_COLORS[component.type]) return component.type
  if (mark === 'P' || /^P(\d|\b)/.test(text)) return 'pipe'
  if (['E', 'EL'].includes(mark) || /^((45|90)?EL|ELB)/.test(text) || /ELBOW|BEND|弯头/.test(text)) return 'elbow'
  if (['F', 'FL'].includes(mark) || /^FL/.test(text) || /FLANGE|法兰/.test(text)) return 'flange'
  if (['T', 'LT', 'RT', 'RLT'].includes(mark) || /TEE|三通/.test(text)) return 'branch'
  if (mark === 'R' || /REDUCER|大小头|异径/.test(text)) return 'reducer'
  if (mark === 'C' || /CAP|管帽/.test(text)) return 'cap'
  if (/VALVE|阀/.test(text)) return 'valve'
  if (/GASKET|垫片/.test(text)) return 'gasket'
  return component.type || 'component'
}

export function normalizePipeComponent(component = {}) {
  return {
    ...component,
    type: normalizePipeComponentType(component),
  }
}

function createRenderableComponentObject(component, context) {
  if (!component || component.hideInModel) return null
  component = normalizePipeComponent(component)
  const { defaultRadius, getRadius, toWorld, toWorldDirection, connectionRefsByPoint, typeColors, symbolMode } = context
  const renderAsSymbol = symbolMode === 'symbol'
    || (symbolMode === 'auto' && shouldRenderComponentAsSymbol(component))
  if (renderAsSymbol) {
    const symbol = createComponentSymbol(component, defaultRadius, getRadius(component.spec), toWorld, typeColors)
    if (!symbol) return null
    if (component.type === 'weld' && component.direction) {
      const direction = toWorldDirection(component.direction)
      if (direction.lengthSq() > 1e-8) {
        reusable.quaternion.setFromUnitVectors(reusable.zAxis, direction)
        symbol.quaternion.copy(reusable.quaternion)
      }
    } else if (component.type === 'flow-arrow' && component.direction) {
      reusable.quaternion.setFromUnitVectors(reusable.yAxis, toWorldDirection(component.direction))
      symbol.quaternion.copy(reusable.quaternion)
    } else if (component.type === 'instrument' && component.direction && !component.end && !component.segments?.length) {
      reusable.quaternion.setFromUnitVectors(reusable.yAxis, toWorldDirection(component.direction))
      symbol.quaternion.copy(reusable.quaternion)
    }
    return symbol
  }

  if (component.type === 'elbow' && component.segments?.length >= 2) {
    return createElbowMesh(component, getRadius(component.spec), toWorld, typeColors)
  }
  if (component.type === 'reducer' && component.start && component.end) {
    return createReducerMesh(component, getRadius, toWorld, typeColors)
  }
  if (component.type === 'cap' && component.start && component.end) {
    return createCapMesh(component, getRadius(component.spec), toWorld, connectionRefsByPoint, typeColors)
  }
  if (component.type === 'flange' && component.start && component.end) {
    return createFlangeMesh(component, getRadius(component.spec), toWorld, connectionRefsByPoint, typeColors)
  }
  if (component.type === 'valve' && component.start && component.end) {
    return createValveMesh(component, getRadius(component.spec), toWorld, typeColors)
  }
  if (isCustomMultiLineType(component.type) && component.start && component.end) {
    return createPairedComponentMesh(component, getRadius(component.spec), toWorld, connectionRefsByPoint, typeColors)
  }
  if (component.start && component.end && component.type !== 'weld') {
    const group = new THREE.Group()
    group.name = `${component.type || 'component'}-${component.id || 'single'}`
    addCylinderBetweenPoints(group, toWorld(component.start), toWorld(component.end), getRadius(component.spec), getMaterial(component.type, typeColors), component, 'fitting', 24)
    return group.children.length ? group : null
  }
  return null
}

function createElbowMesh(component, radius, toWorld, typeColors) {
  const points = component.segments
    .flatMap((segment, index) => (index === 0 ? [segment.start, segment.end] : [segment.end]))
    .filter(Boolean)
    .map((point) => toWorld(point))
  if (points.length < 3) return null
  const curve = new THREE.QuadraticBezierCurve3(points[0], points[1], points.at(-1))
  const geometry = new THREE.TubeGeometry(curve, 32, radius, 18, false)
  const mesh = new THREE.Mesh(geometry, getMaterial(component.type, typeColors))
  mesh.name = `elbow-${component.id}`
  assignComponentData(mesh, component, 'fitting')
  return mesh
}

function createReducerMesh(component, getRadius, toWorld, typeColors) {
  const start = toWorld(component.start)
  const end = toWorld(component.end)
  const axis = getReducerAxis(start, end)
  if (!axis) return null
  const startRadius = getRadius(component.startSpec || component.spec)
  const endRadius = getRadius(component.endSpec || component.spec)
  const geometry = createFrustumBetweenPoints(start, end, startRadius, endRadius, axis, 32)
  const mesh = new THREE.Mesh(geometry, getMaterial(component.type, typeColors, { side: THREE.DoubleSide }))
  mesh.name = `${component.reducerKind || 'reducer'}-${component.id}`
  assignComponentData(mesh, component, 'fitting')
  return mesh
}

function createCapMesh(component, radius, toWorld, connectionRefsByPoint, typeColors) {
  const pose = getCapPose(component, connectionRefsByPoint)
  if (!pose) return null
  const start = toWorld(pose.base)
  const end = toWorld(pose.tip)
  const direction = new THREE.Vector3().subVectors(end, start)
  if (direction.length() <= 1e-6) return null
  direction.normalize()
  const group = new THREE.Group()
  group.name = `cap-${component.id}`
  addComponentMesh(group, new THREE.SphereGeometry(radius, 28, 14, 0, Math.PI * 2, 0, Math.PI / 2), getMaterial(component.type, typeColors), component, 'fitting', start, direction)
  return group
}

function createFlangeMesh(component, radius, toWorld, connectionRefsByPoint, typeColors) {
  const pose = getFlangePose(component, connectionRefsByPoint)
  const facePoint = toWorld(pose.face)
  const weldPoint = toWorld(pose.weld)
  const axis = new THREE.Vector3().subVectors(weldPoint, facePoint)
  const length = axis.length()
  if (length <= 1e-6) return null
  axis.normalize()
  const group = new THREE.Group()
  group.name = `flange-${component.id}`
  const material = getMaterial(component.type, typeColors)
  addComponentMesh(group, new THREE.CylinderGeometry(radius * 1.42, radius * 1.42, Math.max(radius * 0.55, radius * 0.6), 28), material, component, 'fitting', new THREE.Vector3().copy(facePoint).add(weldPoint).multiplyScalar(0.5), axis)
  return group
}

function createValveMesh(component, radius, toWorld, typeColors) {
  const start = toWorld(component.start)
  const end = toWorld(component.end)
  const axis = new THREE.Vector3().subVectors(end, start)
  const length = axis.length()
  if (length <= 1e-6) return null
  axis.normalize()
  const center = new THREE.Vector3().copy(start).add(end).multiplyScalar(0.5)
  const group = new THREE.Group()
  group.name = `valve-${component.id}`
  const material = getMaterial(component.type, typeColors)
  addComponentMesh(group, new THREE.SphereGeometry(radius * 1.2, 24, 14), material, component, 'fitting', center)
  addComponentMesh(group, new THREE.CylinderGeometry(radius * 1.0, radius * 1.0, length, 24), material, component, 'fitting', center, axis)
  return group
}

function createPairedComponentMesh(component, radius, toWorld, connectionRefsByPoint, typeColors) {
  const segmentPairs = getComponentSegmentPairs(component, toWorld)
  expandAngleValveSegmentPairs(component, segmentPairs, radius, toWorld, connectionRefsByPoint)
  if (!segmentPairs.length) return null
  const group = new THREE.Group()
  group.name = `${component.type}-${component.id}`
  const material = getMaterial(component.type, typeColors)
  const bodyRadius = getMultiLineBodyRadius(component.type, radius)
  const lineRadius = Math.max(radius * 0.72, bodyRadius * 0.42)

  segmentPairs.forEach((segment) => {
    addCylinderBetweenPoints(group, segment.start, segment.end, lineRadius, material, component, 'fitting', 24)
  })

  const bodyCenter = getSharedSegmentPoint(segmentPairs) || getSegmentPairsCenter(segmentPairs)
  const axis = getPairedComponentAxis(segmentPairs, bodyCenter)
  addComponentMesh(group, new THREE.CylinderGeometry(bodyRadius * 0.82, bodyRadius * 0.82, Math.max(bodyRadius * 1.55, radius * 2.1), 24), material, component, 'fitting', bodyCenter, axis)
  return group
}

function createComponentSymbol(component, defaultRadius, componentRadius, toWorld, typeColors) {
  const type = component.type || 'component'
  const position = toWorld(component.displayStart || component.start)
  const radius = type === 'weld'
    ? Math.max(componentRadius || 0, defaultRadius * 0.12)
    : Math.max(componentRadius || defaultRadius, defaultRadius * 0.7)
  let geometry
  if (type === 'weld') {
    geometry = new THREE.TorusGeometry(radius, Math.max(defaultRadius * 0.015, radius * 0.06), 10, 32)
  } else if (type === 'gasket') {
    geometry = new THREE.CylinderGeometry(radius * 1.28, radius * 1.28, Math.max(radius * 0.28, defaultRadius * 0.32), 28)
  } else if (type === 'flow-arrow') {
    return createFlowArrowSymbol(component, radius, position, typeColors)
  } else if (type === 'instrument' && !component.end && !component.segments?.length) {
    return createInstrumentBubbleSymbol(component, radius, position, typeColors)
  } else {
    geometry = new THREE.SphereGeometry(radius * 1.1, 16, 10)
  }
  const mesh = new THREE.Mesh(geometry, getMaterial(type, typeColors))
  mesh.name = `${type}-symbol-${component.lineNumber || component.id || '0'}`
  mesh.position.copy(position)
  assignComponentData(mesh, component, 'symbol')
  return mesh
}

function createFlowArrowSymbol(component, radius, position, typeColors) {
  const group = new THREE.Group()
  group.position.copy(position)
  group.userData.kind = 'symbol'
  const material = getMaterial('flow-arrow', typeColors, { depthTest: false, depthWrite: false })
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.12, radius * 0.12, radius * 2.35, 12), material)
  shaft.position.set(0, radius * 0.82, 0)
  assignComponentData(shaft, component, 'symbol')
  group.add(shaft)
  const head = new THREE.Mesh(new THREE.ConeGeometry(radius * 0.38, radius, 18), material)
  head.position.set(0, radius * 1.9, 0)
  assignComponentData(head, component, 'symbol')
  group.add(head)
  return group
}

function createInstrumentBubbleSymbol(component, radius, position, typeColors) {
  const group = new THREE.Group()
  group.position.copy(position)
  group.userData.kind = 'symbol'
  const material = getMaterial('instrument', typeColors)
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.16, radius * 0.16, radius * 1.45, 14), material)
  stem.position.set(0, radius * 0.72, 0)
  assignComponentData(stem, component, 'symbol')
  group.add(stem)
  const disk = new THREE.Mesh(new THREE.CylinderGeometry(radius * 1.12, radius * 1.12, radius * 0.16, 36), material)
  disk.rotation.x = Math.PI / 2
  disk.position.set(0, radius * 2.2, 0)
  assignComponentData(disk, component, 'symbol')
  group.add(disk)
  return group
}

function getMaterial(type, typeColors, options = {}) {
  const key = type || 'component'
  const cacheKey = [
    key,
    options.side || THREE.FrontSide,
    options.depthTest === false ? 'no-depth-test' : 'depth-test',
    options.depthWrite === false ? 'no-depth-write' : 'depth-write',
  ].join('|')
  if (!materialCache.has(cacheKey)) {
    materialCache.set(cacheKey, new THREE.MeshStandardMaterial({
      color: typeColors[key] || typeColors.component,
      roughness: 0.36,
      metalness: 0.12,
      side: options.side || THREE.FrontSide,
      depthTest: options.depthTest !== false,
      depthWrite: options.depthWrite !== false,
    }))
  }
  return materialCache.get(cacheKey)
}

function addComponentMesh(group, geometry, material, component, kind, position, direction = reusable.yAxis) {
  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.copy(position)
  if (direction) {
    reusable.quaternion.setFromUnitVectors(reusable.yAxis, direction.clone().normalize())
    mesh.quaternion.copy(reusable.quaternion)
  }
  assignComponentData(mesh, component, kind)
  group.add(mesh)
  return mesh
}

function assignComponentData(mesh, component, kind) {
  mesh.userData.kind = kind
  mesh.userData.componentId = component.id
  mesh.userData.component = component
}

function addCylinderBetweenPoints(group, start, end, radius, material, component, kind, radialSegments = 18) {
  const length = start.distanceTo(end)
  if (length <= 1e-6) return null
  const center = new THREE.Vector3().copy(start).add(end).multiplyScalar(0.5)
  const direction = new THREE.Vector3().subVectors(end, start).normalize()
  return addComponentMesh(group, new THREE.CylinderGeometry(radius, radius, length, radialSegments), material, component, kind, center, direction)
}

function createFrustumBetweenPoints(start, end, startRadius, endRadius, axis, radialSegments = 24) {
  const helper = Math.abs(axis.dot(reusable.yAxis)) > 0.92 ? reusable.zAxis : reusable.yAxis
  const right = new THREE.Vector3().crossVectors(helper, axis).normalize()
  const up = new THREE.Vector3().crossVectors(axis, right).normalize()
  const positions = []
  const indices = []
  for (let ring = 0; ring < 2; ring += 1) {
    const center = ring === 0 ? start : end
    const radius = ring === 0 ? startRadius : endRadius
    for (let index = 0; index < radialSegments; index += 1) {
      const angle = (Math.PI * 2 * index) / radialSegments
      const radial = new THREE.Vector3().copy(right).multiplyScalar(Math.cos(angle)).addScaledVector(up, Math.sin(angle)).normalize()
      const point = new THREE.Vector3().copy(center).addScaledVector(radial, radius)
      positions.push(point.x, point.y, point.z)
    }
  }
  const startCenterIndex = positions.length / 3
  positions.push(start.x, start.y, start.z)
  const endCenterIndex = positions.length / 3
  positions.push(end.x, end.y, end.z)
  for (let index = 0; index < radialSegments; index += 1) {
    const next = (index + 1) % radialSegments
    indices.push(index, radialSegments + index, radialSegments + next)
    indices.push(index, radialSegments + next, next)
    indices.push(startCenterIndex, next, index)
    indices.push(endCenterIndex, radialSegments + index, radialSegments + next)
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  return geometry
}

function getCapPose(component, connectionRefsByPoint) {
  const startRefs = connectionRefsByPoint.get(pointKey(component.start)) || []
  const endRefs = connectionRefsByPoint.get(pointKey(component.end)) || []
  const startConnected = startRefs.some((ref) => ref.component.id !== component.id)
  const endConnected = endRefs.some((ref) => ref.component.id !== component.id)
  if (startConnected && !endConnected) return { base: component.start, tip: component.end }
  if (endConnected && !startConnected) return { base: component.end, tip: component.start }
  return { base: component.start, tip: component.end }
}

function getFlangePose(component, connectionRefsByPoint) {
  const startRefs = connectionRefsByPoint.get(pointKey(component.start)) || []
  const endRefs = connectionRefsByPoint.get(pointKey(component.end)) || []
  const startHasGasket = startRefs.some((ref) => isGasketLike(ref.component, component.id))
  const endHasGasket = endRefs.some((ref) => isGasketLike(ref.component, component.id))
  if (startHasGasket && !endHasGasket) return { face: component.start, weld: component.end }
  if (endHasGasket && !startHasGasket) return { face: component.end, weld: component.start }
  return { face: component.start, weld: component.end }
}

function isGasketLike(component, selfId) {
  return component
    && component.id !== selfId
    && (component.type === 'gasket' || component.identifier === 110 || /垫片|gasket/i.test(component.materialDescription || ''))
}

function getComponentSegmentPairs(component, toWorld) {
  const segments = component.segments?.length ? component.segments : [{ start: component.start, end: component.end }]
  return segments
    .filter((segment) => segment.start && segment.end)
    .map((segment) => ({ start: toWorld(segment.start), end: toWorld(segment.end) }))
    .filter((segment) => segment.start.distanceTo(segment.end) > 1e-6)
}

function expandAngleValveSegmentPairs(component, segmentPairs, radius, toWorld, connectionRefsByPoint) {
  if (component.type !== 'angle-valve' || segmentPairs.length !== 1 || !component.segments?.length) return
  if (!component.start || !component.end || pointKey(component.start) === pointKey(component.end)) return
  const startPoint = toWorld(component.start)
  const endPoint = toWorld(component.end)
  const startDirection = getAngleValvePortDirection(component, component.start, toWorld, connectionRefsByPoint, true)
  const endDirection = getAngleValvePortDirection(component, component.end, toWorld, connectionRefsByPoint, false)
  if (!startDirection || !endDirection || Math.abs(startDirection.dot(endDirection)) > 0.94) return
  const corner = getClosestPointBetweenLines(startPoint, startDirection, endPoint, endDirection)
  if (!corner || corner.distanceTo(startPoint) <= 1e-6 || corner.distanceTo(endPoint) <= 1e-6) return
  segmentPairs.splice(0, segmentPairs.length, { start: startPoint, end: corner.clone() }, { start: corner.clone(), end: endPoint })
}

function getAngleValvePortDirection(component, point, toWorld, connectionRefsByPoint, awayFromConnection) {
  const worldPoint = toWorld(point)
  const refs = connectionRefsByPoint.get(pointKey(point)) || []
  for (const ref of refs) {
    const otherComponent = ref.component
    if (!otherComponent || otherComponent.id === component.id || !otherComponent.start || !otherComponent.end) continue
    const otherPoint = pointKey(otherComponent.start) === pointKey(point)
      ? otherComponent.end
      : pointKey(otherComponent.end) === pointKey(point)
        ? otherComponent.start
        : null
    if (!otherPoint) continue
    const otherWorld = toWorld(otherPoint)
    const direction = awayFromConnection
      ? new THREE.Vector3().subVectors(worldPoint, otherWorld)
      : new THREE.Vector3().subVectors(otherWorld, worldPoint)
    if (direction.length() > 1e-6) return direction.normalize()
  }
  return null
}

function getClosestPointBetweenLines(pointA, directionA, pointB, directionB) {
  const between = new THREE.Vector3().subVectors(pointA, pointB)
  const a = directionA.dot(directionA)
  const b = directionA.dot(directionB)
  const c = directionB.dot(directionB)
  const d = directionA.dot(between)
  const e = directionB.dot(between)
  const denominator = a * c - b * b
  if (Math.abs(denominator) <= 1e-9) return null
  const t = (b * e - c * d) / denominator
  const u = (a * e - b * d) / denominator
  const closestA = pointA.clone().addScaledVector(directionA, t)
  const closestB = pointB.clone().addScaledVector(directionB, u)
  return closestA.add(closestB).multiplyScalar(0.5)
}

function getSharedSegmentPoint(segmentPairs) {
  const points = []
  segmentPairs.forEach((segment) => points.push(segment.start, segment.end))
  for (const point of points) {
    const count = points.filter((candidate) => candidate.distanceTo(point) <= 1e-6).length
    if (count > 1) return point.clone()
  }
  return null
}

function getSegmentPairsCenter(segmentPairs) {
  const center = new THREE.Vector3()
  let count = 0
  segmentPairs.forEach((segment) => {
    center.add(segment.start).add(segment.end)
    count += 2
  })
  return count ? center.multiplyScalar(1 / count) : new THREE.Vector3()
}

function getPairedComponentAxis(segmentPairs, bodyCenter) {
  const longest = segmentPairs.reduce((best, segment) => {
    const length = segment.start.distanceTo(segment.end)
    return length > best.length ? { segment, length } : best
  }, { segment: segmentPairs[0], length: 0 }).segment
  const connected = segmentPairs
    .map((segment) => {
      if (segment.start.distanceTo(bodyCenter) <= 1e-6) return segment.end
      if (segment.end.distanceTo(bodyCenter) <= 1e-6) return segment.start
      return null
    })
    .filter(Boolean)
  if (connected.length >= 2) {
    const axis = new THREE.Vector3().subVectors(connected[0], connected[1])
    if (axis.length() > 1e-6) return axis.normalize()
  }
  return new THREE.Vector3().subVectors(longest.end, longest.start).normalize()
}

function getReducerAxis(start, end) {
  const delta = new THREE.Vector3().subVectors(end, start)
  if (delta.length() <= 1e-6) return null
  const abs = [Math.abs(delta.x), Math.abs(delta.y), Math.abs(delta.z)]
  const axis = new THREE.Vector3()
  if (abs[0] >= abs[1] && abs[0] >= abs[2]) axis.set(Math.sign(delta.x) || 1, 0, 0)
  else if (abs[1] >= abs[0] && abs[1] >= abs[2]) axis.set(0, Math.sign(delta.y) || 1, 0)
  else axis.set(0, 0, Math.sign(delta.z) || 1)
  return axis
}

function getMultiLineBodyRadius(type, radius) {
  if (type === 'filter') return radius * 1.7
  if (type === 'trap') return radius * 1.55
  if (type === 'instrument') return radius * 1.3
  if (type === 'teed-reducer' || type === 'teed-elbow') return radius * 1.45
  if (type === 'three-way-valve' || type === 'four-way-valve') return radius * 1.55
  return radius * 1.35
}

function isCustomMultiLineType(type) {
  return ['teed-reducer', 'teed-elbow', 'angle-valve', 'three-way-valve', 'four-way-valve', 'instrument', 'misc-component', 'trap', 'filter'].includes(type)
}

function shouldRenderComponentAsSymbol(component) {
  return component.type === 'weld'
    || component.type === 'gasket'
    || component.type === 'flow-arrow'
    || (component.type === 'instrument' && (!component.end || !component.start) && !component.segments?.length)
    || !component.start
}

function pointKey(point) {
  return point.map((value) => Number(value).toFixed(3)).join(',')
}
