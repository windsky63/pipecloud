import { requestJson } from './http'
import { uploadFilesRequest } from './uploads'

export function fetchSummary(params) {
  return requestJson(`/summary/?${params}`)
}

export function runWorkflowAction(actionKey, params, options = {}) {
  const requestOptions = { method: 'POST' }
  if (options && Object.keys(options).length) {
    requestOptions.headers = {
      'Content-Type': 'application/json',
    }
    requestOptions.body = JSON.stringify(options)
  }
  return requestJson(`/run/${actionKey}/?${params}`, requestOptions)
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

export function fetchStagedPlanFileRows(params, stageToken, filePath, sourceKey, sheet) {
  const nextParams = new URLSearchParams(params)
  if (stageToken) nextParams.set('stageToken', stageToken)
  if (filePath) nextParams.set('path', filePath)
  if (sourceKey) nextParams.set('sourceKey', sourceKey)
  if (sheet) nextParams.set('sheet', sheet)
  return requestJson(`/schedule/stage/file/?${nextParams}`)
}

export function fetchArrivalFiles(params) {
  return requestJson(`/arrival/files/?${params}`)
}

export function fetchTodayArrival(params) {
  return requestJson(`/arrival/today/?${params}`)
}

export function fetchArrivalFileRows(params, fileName, sheet) {
  const nextParams = new URLSearchParams(params)
  if (fileName) nextParams.set('file', fileName)
  if (sheet) nextParams.set('sheet', sheet)
  return requestJson(`/arrival/file/?${nextParams}`)
}

export function fetchInitializationStats(params) {
  return requestJson(`/initialization/stats/?${params}`)
}

export function syncInitializationData(params) {
  return requestJson(`/initialization/sync/?${params}`, {
    method: 'POST',
  })
}

export function updateInitializationProjectMetrics(params) {
  return requestJson(`/initialization/project-metrics/?${params}`, {
    method: 'POST',
  })
}

export function fetchWeldingDashboard(params) {
  return requestJson(`/welding/dashboard/?${params}`)
}

export function uploadArrivalFileRequest(params, files) {
  return uploadFilesRequest('arrival-order', params, files)
}

export function fetchCuttingPreSchedule(params) {
  return requestJson(`/cutting/pre-schedule/?${params}`)
}

export function fetchCuttingVisualization(params) {
  return requestJson(`/cutting/visualization/?${params}`)
}
