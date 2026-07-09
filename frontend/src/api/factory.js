import { requestJson } from './http'

export function fetchTodayPipeMaterials(params) {
  return requestJson(`/factory/today-pipe-materials/?${params}`)
}
