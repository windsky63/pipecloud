import { i18n } from '../i18n'

export const API_PREFIX = '/api/pipecloud'

export async function requestJson(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_PREFIX}${path}`, options)
  } catch (networkError) {
    const error = new Error(i18n.global.t('apiNetworkError'))
    error.cause = networkError
    throw error
  }
  let payload = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }
  if (!response.ok) {
    const error = new Error(payload.error || i18n.global.t('apiStatusError', { status: response.status }))
    error.payload = payload
    error.status = response.status
    throw error
  }
  return payload
}

export function postJson(path, body, options = {}) {
  return requestJson(path, {
    ...options,
    method: options.method || 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    body: JSON.stringify(body),
  })
}

export function postForm(path, formData, options = {}) {
  return requestJson(path, {
    ...options,
    method: options.method || 'POST',
    body: formData,
  })
}
