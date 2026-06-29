import { postForm } from './http'

export function uploadFilesRequest(uploadKey, params, files) {
  const formData = new FormData()
  ;(Array.isArray(files) ? files : [files]).filter(Boolean).forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  return postForm(`/uploads/${uploadKey}/?${params}`, formData)
}
