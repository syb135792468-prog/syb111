import { API_BASE } from '../utils/constants'

export interface ImageUploadResult {
  url: string
  ocr_text: string
  filename: string
}

let _getToken: () => string = () => ''

export function setImageTokenGetter(getToken: () => string) {
  _getToken = getToken
}

const UPLOAD_TIMEOUT = 120_000 // 120秒（首次OCR需下载模型）

export async function uploadImage(file: File): Promise<ImageUploadResult> {
  const formData = new FormData()
  formData.append('file', file)

  const token = _getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT)

  try {
    const response = await fetch(`${API_BASE}/images/upload`, {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)
    const json = await response.json().catch(() => null)

    if (!response.ok) {
      const msg = json?.message || json?.detail || `上传失败: ${response.status}`
      throw new Error(msg)
    }

    if (!json || json.code !== 200 || !json.data) {
      throw new Error(json?.message || '图片上传返回数据异常')
    }

    return json.data as ImageUploadResult
  } catch (e: unknown) {
    clearTimeout(timeoutId)
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error('上传超时，服务器可能正在初始化OCR模型，请稍后重试')
    }
    throw e
  }
}
