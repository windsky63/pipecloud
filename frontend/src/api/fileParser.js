import { postForm, postJson, requestJson } from './http'
import { uploadFilesRequest } from './uploads'

const PARSER_UPLOAD_CHUNK_SIZE = 50

export function parseUploadedFiles(params, files) {
  const fileList = (Array.isArray(files) ? files : [files]).filter(Boolean)
  if (fileList.length <= PARSER_UPLOAD_CHUNK_SIZE) {
    return uploadFilesRequest('file-parser-parse', params, fileList)
  }
  return uploadParserFilesInChunks(params, fileList)
}

async function uploadParserFilesInChunks(params, files) {
  const uploadSession = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const chunkTotal = Math.ceil(files.length / PARSER_UPLOAD_CHUNK_SIZE)
  let payload = null
  for (let index = 0; index < chunkTotal; index += 1) {
    const chunk = files.slice(index * PARSER_UPLOAD_CHUNK_SIZE, (index + 1) * PARSER_UPLOAD_CHUNK_SIZE)
    const formData = new FormData()
    chunk.forEach((file) => {
      formData.append('files', file, file.webkitRelativePath || file.name)
    })
    const nextParams = new URLSearchParams(params)
    nextParams.set('upload_session', uploadSession)
    nextParams.set('chunk_index', String(index + 1))
    nextParams.set('chunk_total', String(chunkTotal))
    payload = await postForm(`/uploads/file-parser-parse/?${nextParams}`, formData)
  }
  return payload
}

export function fetchParserJobStatus(jobId) {
  return requestJson(`/file-parser/jobs/${jobId}/`)
}

export function fetchParserPreview(params) {
  const query = new URLSearchParams()
  if (params?.stagedPath) query.set('stagedPath', params.stagedPath)
  if (params?.sheet) query.set('sheet', params.sheet)
  if (params?.previewMode) query.set('previewMode', params.previewMode)
  return requestJson(`/file-parser/preview/?${query}`)
}

export function uploadInitializationFile(params, files) {
  return uploadFilesRequest('initialization-upload', params, files)
}

export function confirmInitializationFile(params, payload) {
  return postJson(`/file-parser/confirm/?${params}`, payload)
}

export function mergeParserResults(params, payload) {
  return postJson(`/file-parser/merge/?${params}`, payload)
}

export function fetchParserProjectList() {
  return requestJson('/projects/')
}
