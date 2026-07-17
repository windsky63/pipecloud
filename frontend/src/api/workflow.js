import { API_PREFIX, postJson, requestJson } from './http'
import { uploadFilesRequest } from './uploads'

export function fetchSummary(params, options = {}) {
  return requestJson(`/summary/?${params}`, options)
}

export function runWorkflowAction(actionKey, params, options = {}, fetchOptions = {}) {
  const requestOptions = { ...fetchOptions, method: 'POST' }
  if (options && Object.keys(options).length) {
    requestOptions.headers = {
      'Content-Type': 'application/json',
    }
    requestOptions.body = JSON.stringify(options)
  }
  return requestJson(`/run/${actionKey}/?${params}`, requestOptions)
}

export function cancelInitializationTask(taskId, options = {}) {
  return requestJson('/initialization/cancel/', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify({ taskId }),
  })
}

export function generateFutureSchedule(params, options = {}) {
  return requestJson(`/schedule/future/?${params}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(options),
  })
}

export function commitStagedPlan(params, stageToken) {
  return requestJson(`/schedule/stage/commit/?${params}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ stageToken }),
  })
}

export function discardStagedPlans(params, stageTokens, options = {}) {
  return requestJson(`/schedule/stage/discard/?${params}`, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify({ stageTokens }),
  })
}

export function beaconDiscardStagedPlans(params, stageTokens) {
  if (typeof navigator === 'undefined' || !stageTokens?.length) return false
  return navigator.sendBeacon(
    `${API_PREFIX}/schedule/stage/discard/?${params}`,
    new Blob([JSON.stringify({ stageTokens })], { type: 'application/json' }),
  )
}

export function fetchStagedPlanFileRows(params, stageToken, filePath, sourceKey, sheet, options = {}) {
  const nextParams = new URLSearchParams(params)
  if (stageToken) nextParams.set('stageToken', stageToken)
  if (filePath) nextParams.set('path', filePath)
  if (sourceKey) nextParams.set('sourceKey', sourceKey)
  if (sheet) nextParams.set('sheet', sheet)
  return requestJson(`/schedule/stage/file/?${nextParams}`, options)
}

export function fetchArrivalFiles(params, options = {}) {
  return requestJson(`/arrival/files/?${params}`, options)
}

export function fetchTodayArrival(params, options = {}) {
  return requestJson(`/arrival/today/?${params}`, options)
}

export function fetchArrivalFileRows(params, fileName, sheet, options = {}) {
  const nextParams = new URLSearchParams(params)
  if (fileName) nextParams.set('file', fileName)
  if (sheet) nextParams.set('sheet', sheet)
  return requestJson(`/arrival/file/?${nextParams}`, options)
}

export function fetchInitializationStats(params, options = {}) {
  return requestJson(`/initialization/stats/?${params}`, options)
}

export function fetchWeldingDashboard(params, options = {}) {
  return requestJson(`/welding/dashboard/?${params}`, options)
}

export function fetchArrivalDashboard(params, options = {}) {
  return requestJson(`/arrival/dashboard/?${params}`, options)
}

export function fetchAntiCorrosionDashboard(params, options = {}) {
  return requestJson(`/anti-corrosion/dashboard/?${params}`, options)
}

export function fetchCuttingDashboard(params, options = {}) {
  return requestJson(`/cutting/dashboard/?${params}`, options)
}

export function uploadArrivalFileRequest(params, files) {
  return uploadFilesRequest('arrival-order', params, files)
}

export function fetchCuttingPreSchedule(params, options = {}) {
  return requestJson(`/cutting/pre-schedule/?${params}`, options)
}

export function fetchMaterialLockingRows(params, options = {}) {
  return requestJson(`/material-locking/pre-schedule/?${params}`, options)
}

export function releaseMaterialLockingRows(params, selectedLibrarySeqs) {
  return postJson(`/material-locking/release/?${params}`, { selectedLibrarySeqs })
}

export function fetchAntiCorrosionPreSchedule(params, options = {}) {
  return requestJson(`/anti-corrosion/pre-schedule/?${params}`, options)
}

export function fetchAntiCorrosionCuttingVisualization(params, options = {}) {
  return requestJson(`/anti-corrosion/cutting-visualization/?${params}`, options)
}

export function fetchWeldingPreSchedule(params, options = {}) {
  return requestJson(`/welding/pre-schedule/?${params}`, options)
}

export function fetchCuttingVisualization(params, options = {}) {
  return requestJson(`/cutting/visualization/?${params}`, options)
}
