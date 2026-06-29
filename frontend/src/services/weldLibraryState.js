import { ref } from 'vue'
import { fetchLibraries } from '../api/libraries'
import { selectedProjectParams } from './projectState'
import { t } from './pipecloudState'


export const libraryLoading = ref(false)
export const libraries = ref([])
export const libraryError = ref('')


export async function loadLibraries() {
  libraryLoading.value = true
  libraryError.value = ''
  try {
    const payload = await fetchLibraries(selectedProjectParams())
    libraries.value = payload.libraries || []
  } catch (error) {
    libraryError.value = t('libraryListReadFailed', { message: error.message })
  } finally {
    libraryLoading.value = false
  }
}
