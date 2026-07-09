import { API_PREFIX, postFormWithUploadProgress, postJson, requestJson } from './http'
import { uploadFilesRequest } from './uploads'

const PARSER_UPLOAD_CHUNK_SIZE = 50

export function parseUploadedFiles(params, files, onUploadProgress) {
  const fileList = (Array.isArray(files) ? files : [files]).filter(Boolean)
  return uploadParserFilesInChunks(params, fileList, onUploadProgress)
}

async function uploadParserFilesInChunks(params, files, onUploadProgress) {
  const uploadSession = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const chunkTotal = Math.ceil(files.length / PARSER_UPLOAD_CHUNK_SIZE)
  const totalFileBytes = files.reduce((sum, file) => sum + (file.size || 0), 0)
  let uploadedFileBytes = 0
  let uploadedFiles = 0
  let payload = null

  for (let index = 0; index < chunkTotal; index += 1) {
    const chunk = files.slice(index * PARSER_UPLOAD_CHUNK_SIZE, (index + 1) * PARSER_UPLOAD_CHUNK_SIZE)
    const chunkFileBytes = chunk.reduce((sum, file) => sum + (file.size || 0), 0)
    const formData = new FormData()
    chunk.forEach((file) => {
      formData.append('files', file, file.webkitRelativePath || file.name)
    })
    const nextParams = new URLSearchParams(params)
    if (chunkTotal > 1) {
      nextParams.set('upload_session', uploadSession)
      nextParams.set('chunk_index', String(index + 1))
      nextParams.set('chunk_total', String(chunkTotal))
    }
    payload = await postFormWithUploadProgress(
      `/uploads/file-parser-parse/?${nextParams}`,
      formData,
      ({ loaded, total }) => {
        const chunkRatio = total > 0 ? Math.min(loaded / total, 1) : 0
        const estimatedLoadedBytes = uploadedFileBytes + chunkFileBytes * chunkRatio
        const percent = totalFileBytes > 0
          ? Math.min(Math.round(estimatedLoadedBytes / totalFileBytes * 100), 100)
          : Math.round(((index + chunkRatio) / chunkTotal) * 100)
        onUploadProgress?.({
          phase: index === chunkTotal - 1 && chunkRatio >= 1 ? 'preparing' : 'uploading',
          percent,
          uploadedFiles: Math.min(uploadedFiles + Math.floor(chunk.length * chunkRatio), files.length),
          totalFiles: files.length,
          currentChunk: index + 1,
          totalChunks: chunkTotal,
        })
      },
    )
    uploadedFileBytes += chunkFileBytes
    uploadedFiles += chunk.length
    onUploadProgress?.({
      phase: index === chunkTotal - 1 ? 'preparing' : 'uploading',
      percent: Math.min(Math.round(uploadedFileBytes / Math.max(totalFileBytes, 1) * 100), 100),
      uploadedFiles,
      totalFiles: files.length,
      currentChunk: index + 1,
      totalChunks: chunkTotal,
    })
  }
  return payload
}

export function fetchParserJobStatus(jobId) {
  return requestJson(`/file-parser/jobs/${jobId}/`)
}

export function cancelParserJob(jobId) {
  return postJson(`/file-parser/jobs/${jobId}/cancel/`, {})
}

export function fetchLatestParserResult(params) {
  return requestJson(`/file-parser/jobs/latest-result/?${params}`)
}

export function fetchParserPreview(params) {
  const query = new URLSearchParams()
  if (params?.artifactId) query.set('artifactId', params.artifactId)
  if (params?.stagedPath) query.set('stagedPath', params.stagedPath)
  if (params?.sheet) query.set('sheet', params.sheet)
  if (params?.previewMode) query.set('previewMode', params.previewMode)
  return requestJson(`/file-parser/preview/?${query}`)
}

async function requestParserDownload(path, options) {
  const response = await fetch(`${API_PREFIX}${path}`, options)
  if (!response.ok) {
    let payload = {}
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
    const error = new Error(payload.error || `下载失败（${response.status}）`)
    error.status = response.status
    throw error
  }
  return response.blob()
}

export function downloadCurrentParserFile({ artifactId, stagedPath }) {
  const query = new URLSearchParams()
  if (artifactId) query.set('artifactId', artifactId)
  else if (stagedPath) query.set('path', stagedPath)
  return requestParserDownload(`/file-parser/download/?${query}`)
}

export function downloadAllParserFiles(results) {
  const artifactIds = results.filter((item) => item.artifactId).map((item) => item.artifactId)
  const stagedPaths = results.filter((item) => !item.artifactId && item.stagedPath).map((item) => item.stagedPath)
  return requestParserDownload('/file-parser/download-all/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ artifactIds, stagedPaths }),
  })
}

export function confirmIdfModel(params, jobId) {
  return postJson(`/file-parser/model-confirm/?${params}`, { jobId })
}

export function uploadInitializationFile(params, files, onUploadProgress) {
  return uploadFilesRequest('initialization-upload', params, files, onUploadProgress)
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
