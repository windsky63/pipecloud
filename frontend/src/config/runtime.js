function trimTrailingSlash(value) {
  return value.length > 1 ? value.replace(/\/+$/, '') : value
}

/**
 * API 根地址既支持开发环境中的相对路径，也支持独立部署时的完整 URL。
 * 仅在构建时读取 Vite 环境变量，业务模块无需关心部署拓扑。
 */
export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL?.trim() || '/api/pipecloud',
)
