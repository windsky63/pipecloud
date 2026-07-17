import { i18n } from '../i18n'
import { API_BASE_URL } from '../config/runtime'

export const API_PREFIX = API_BASE_URL

export async function requestJson(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_PREFIX}${path}`, options)
  } catch (networkError) {
    if (networkError?.name === 'AbortError') {
      throw networkError
    }
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

export function postFormWithUploadProgress(path, formData, onUploadProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', `${API_PREFIX}${path}`)

    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        onUploadProgress?.({
          loaded: event.loaded,
          total: event.total,
        })
      }
    })

    request.addEventListener('load', () => {
      let payload = {}
      try {
        payload = request.responseText ? JSON.parse(request.responseText) : {}
      } catch {
        payload = {}
      }

      if (request.status >= 200 && request.status < 300) {
        resolve(payload)
        return
      }

      const error = new Error(payload.error || i18n.global.t('apiStatusError', { status: request.status }))
      error.payload = payload
      error.status = request.status
      reject(error)
    })

    request.addEventListener('error', () => {
      reject(new Error(i18n.global.t('apiNetworkError')))
    })

    request.addEventListener('abort', () => {
      reject(new Error(i18n.global.t('apiNetworkError')))
    })

    request.send(formData)
  })
}
