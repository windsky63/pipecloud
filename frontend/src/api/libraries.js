import { postJson, requestJson } from './http'

export function fetchLibraries(params) {
  return requestJson(`/libraries/?${params}`)
}

export function fetchLibraryRows(libraryKey, params, options = {}) {
  return requestJson(`/libraries/${libraryKey}/?${params}`, options)
}

export function saveLibraryRows(libraryKey, params, payload) {
  return postJson(`/libraries/${libraryKey}/save/?${params}`, payload)
}
