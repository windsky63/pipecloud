import { API_PREFIX, postForm, postJson, requestJson } from './http'

export function fetchPlanRows(planKey, params) {
  return requestJson(`/plans/${planKey}/?${params}`)
}

export function fetchPlanFileRows(planKey, params) {
  return requestJson(`/plans/${planKey}/file/?${params}`)
}

export function savePlanFileRows(planKey, params, payload) {
  return postJson(`/plans/${planKey}/file/save/?${params}`, payload)
}

export function movePlanDate(planKey, params, payload) {
  return postJson(`/plans/${planKey}/move/?${params}`, payload)
}

export function importPlanPatchRows(planKey, formData, params) {
  return postForm(`/plans/${planKey}/file/import/?${params}`, formData)
}

export async function exportPlanPatchRows(planKey, params, payload) {
  const response = await fetch(`${API_PREFIX}/plans/${planKey}/file/export/?${params}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}))
    throw new Error(errorPayload.error || `Export failed: ${response.status}`)
  }
  return response.blob()
}
