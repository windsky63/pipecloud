import { postForm, postFormWithUploadProgress } from './http'

export function uploadFilesRequest(uploadKey, params, files, onUploadProgress) {
  const formData = new FormData()
  ;(Array.isArray(files) ? files : [files]).filter(Boolean).forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  const path = `/uploads/${uploadKey}/?${params}`
  return onUploadProgress
    ? postFormWithUploadProgress(path, formData, onUploadProgress)
    : postForm(path, formData)
}
