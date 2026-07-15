import { apiPost } from './index'
import { API_BASE } from '../utils/constants'

interface CodeResult {
  success: boolean
  stdout: string
  stderr: string
  execution_time: number
  timed_out: boolean
  network_time: number
  total_time: number
}

export async function executeCode(
  code: string,
  timeout = 10,
  knowledgePoint?: string,
): Promise<CodeResult> {
  const startTime = Date.now()

  try {
    const payload: Record<string, unknown> = { code, timeout }
    if (knowledgePoint) payload.knowledge_point = knowledgePoint
    const resp = await apiPost<CodeResult>(`${API_BASE}/code/execute`, payload, 30000)
    const networkTime = Date.now() - startTime

    if (resp.code === 200 && resp.data) {
      return {
        ...resp.data,
        network_time: networkTime,
        total_time: networkTime,
      }
    }

    return {
      success: false,
      stdout: '',
      stderr: resp.message || '执行失败',
      execution_time: 0,
      timed_out: false,
      network_time: networkTime,
      total_time: networkTime,
    }
  } catch (error: unknown) {
    const totalTime = Date.now() - startTime
    return {
      success: false,
      stdout: '',
      stderr: error instanceof Error ? error.message : '网络连接失败',
      execution_time: 0,
      timed_out: false,
      network_time: totalTime,
      total_time: totalTime,
    }
  }
}
