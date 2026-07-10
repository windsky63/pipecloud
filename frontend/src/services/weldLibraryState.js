import { ref } from 'vue'
import { fetchLibraries } from '../api/libraries'
import { selectedProjectId, selectedProjectParams } from './projectState'
import { t } from './pipecloudState'


export const libraryLoading = ref(false)
export const defaultLibraries = [
  { key: 'weld-library', name: '预制焊口库', exists: false, rowCount: 0 },
  { key: 'pipe-library', name: '管子材料库', exists: false, rowCount: 0 },
  { key: 'fitting-library', name: '管件法兰材料库', exists: false, rowCount: 0 },
  { key: 'anti-pipe-library', name: '防腐管子材料库', exists: false, rowCount: 0 },
  { key: 'anti-fitting-library', name: '防腐管件法兰材料库', exists: false, rowCount: 0 },
  { key: 'master-schedule-library', name: '排产计划库', exists: false, rowCount: 0 },
]
export const libraries = ref(defaultLibraries.map((library) => ({ ...library })))
export const libraryError = ref('')


export function clearLibraryError() {
  libraryError.value = ''
}


export async function loadLibraries() {
  if (!selectedProjectId.value) {
    libraries.value = defaultLibraries.map((library) => ({ ...library }))
    libraryError.value = ''
    libraryLoading.value = false
    return
  }
  libraryLoading.value = true
  libraryError.value = ''
  try {
    const payload = await fetchLibraries(selectedProjectParams())
    const received = new Map((payload.libraries || []).map((library) => [library.key, library]))
    libraries.value = defaultLibraries.map((library) => ({
      ...library,
      ...(received.get(library.key) || {}),
    }))
  } catch (error) {
    libraryError.value = t('libraryListReadFailed', { message: error.message })
  } finally {
    libraryLoading.value = false
  }
}
