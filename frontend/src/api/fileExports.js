import { API_PREFIX, requestJson } from './http'

export function fetchProjectFileTree(params) {
  return requestJson(`/files/export-tree/?${params}`)
}

export async function exportProjectFiles(params, fileIds) {
  const response = await fetch(`${API_PREFIX}/files/batch-export/?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fileIds }),
  })
  if (!response.ok) {
    let payload = {}
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
    throw new Error(payload.error || `HTTP ${response.status}`)
  }
  return response.blob()
}

export function startProjectFileExport(params, fileIds) {
  return requestJson(`/files/batch-export/start/?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fileIds }),
  })
}

export function fetchProjectFileExportStatus(params, jobId) {
  const nextParams = new URLSearchParams(params)
  nextParams.set('jobId', jobId)
  return requestJson(`/files/batch-export/status/?${nextParams}`)
}

export async function downloadProjectFileExport(params, jobId) {
  const nextParams = new URLSearchParams(params)
  nextParams.set('jobId', jobId)
  const response = await fetch(`${API_PREFIX}/files/batch-export/download/?${nextParams}`)
  if (!response.ok) {
    let payload = {}
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
    throw new Error(payload.error || `HTTP ${response.status}`)
  }
  return response.blob()
}
