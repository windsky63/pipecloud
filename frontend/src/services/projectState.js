import { ref } from 'vue'
import { fetchProjects } from '../api/projects'
import { i18n } from '../i18n'

const selectedProjectStorageKey = 'pipecloud.selectedProjectId'

function readSelectedProjectId() {
  if (typeof window === 'undefined') return null
  const value = Number(window.localStorage.getItem(selectedProjectStorageKey))
  return Number.isFinite(value) && value > 0 ? value : null
}

export const selectedProjectId = ref(readSelectedProjectId())
export const projectGateMessage = ref('')

export function setSelectedProjectId(value) {
  const normalizedValue = Number(value)
  selectedProjectId.value = Number.isFinite(normalizedValue) && normalizedValue > 0 ? normalizedValue : null
  if (typeof window !== 'undefined') {
    if (selectedProjectId.value) {
      window.localStorage.setItem(selectedProjectStorageKey, String(selectedProjectId.value))
    } else {
      window.localStorage.removeItem(selectedProjectStorageKey)
    }
  }
}

export function notifyProjectRequired() {
  projectGateMessage.value = ''
  setTimeout(() => {
    projectGateMessage.value = i18n.global.t('projectRequired')
  }, 0)
}

export function selectedProjectParams(initialValues) {
  const params = new URLSearchParams(initialValues)
  if (selectedProjectId.value) {
    params.set('project_id', String(selectedProjectId.value))
  }
  return params
}

export async function hasSelectedProject() {
  if (!selectedProjectId.value) return false
  try {
    const payload = await fetchProjects()
    return (payload.rows || []).some((project) => project.id === selectedProjectId.value)
  } catch {
    return false
  }
}

export async function ensureSelectedProject() {
  if (selectedProjectId.value) return selectedProjectId.value
  const payload = await fetchProjects()
  const rows = payload.rows || []
  if (rows.length === 1) {
    setSelectedProjectId(rows[0].id)
    return selectedProjectId.value
  }
  return null
}
