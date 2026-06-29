import { API_PREFIX, postForm, postJson, requestJson } from './http'

export function fetchProjects() {
  return requestJson('/projects/')
}

export function createProject(project) {
  return postJson('/projects/', project)
}

export function updateProject(projectId, project) {
  return postJson(`/projects/${projectId}/`, project, { method: 'PUT' })
}

export function deleteProjectById(projectId) {
  return requestJson(`/projects/${projectId}/`, { method: 'DELETE' })
}

export function importProjectsFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  return postForm('/projects/import/', formData)
}

export function projectExportUrl() {
  return `${API_PREFIX}/projects/export/`
}

export function fetchProjectWelds(projectId, params) {
  return requestJson(`/projects/${projectId}/welds/?${params}`)
}

export function fetchProjectSpools(projectId, options = {}) {
  const params = new URLSearchParams()
  if (options.weldSource) params.set('weldSource', options.weldSource)
  if (options.structureSpool) params.set('structureSpool', options.structureSpool)
  if (options.includeModel) params.set('includeModel', 'true')
  const query = params.toString()
  return requestJson(`/projects/${projectId}/spools/${query ? `?${query}` : ''}`)
}
