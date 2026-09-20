/** Axios 实例与统一错误处理。 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiError } from '@/types'

const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
})

/** 登录态失效时的回调，由 auth store 注入，避免此处直接 import 造成循环依赖。 */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('uams_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error.response?.status
    const data = error.response?.data as ApiError | undefined

    if (status === 401) {
      // 不在登录页时才提示，避免登录失败被重复提示
      if (!location.pathname.startsWith('/login')) {
        ElMessage.error('登录已过期，请重新登录')
        onUnauthorized?.()
      }
    } else if (status === 422 && data?.errors?.length) {
      ElMessage.error(
        data.errors.map((e) => `${e.field}: ${e.msg}`).join('；'),
      )
    } else if (data?.message) {
      ElMessage.error(data.message)
    } else if (!error.response) {
      ElMessage.error('网络异常，请检查后端服务是否已启动')
    } else {
      ElMessage.error('请求失败')
    }
    return Promise.reject(error)
  },
)

export async function get<T>(url: string, params?: unknown, config?: AxiosRequestConfig) {
  const { data } = await http.get<T>(url, { params: clampPageSize(params), ...config })
  return data
}

/** 后端 page_size 上限为 200，超过会直接返回 422。
 *  下拉框常想「一次拉全量」，这里统一夹住，避免各处重复写死上限。 */
const MAX_PAGE_SIZE = 200

function clampPageSize(params: unknown): unknown {
  if (!params || typeof params !== 'object') return params
  const p = params as Record<string, unknown>
  if (typeof p.page_size === 'number' && p.page_size > MAX_PAGE_SIZE) {
    return { ...p, page_size: MAX_PAGE_SIZE }
  }
  return params
}

export async function post<T>(url: string, body?: unknown, config?: AxiosRequestConfig) {
  const { data } = await http.post<T>(url, body, config)
  return data
}

export async function put<T>(url: string, body?: unknown) {
  const { data } = await http.put<T>(url, body)
  return data
}

export async function del<T = void>(url: string) {
  const { data } = await http.delete<T>(url)
  return data
}

/** 下载二进制文件（Excel 模板等）：401/业务错误的响应体是 Blob，需先解析再提示。 */
export async function download(
  url: string,
  params?: unknown,
  filename = 'download.xlsx',
): Promise<void> {
  try {
    const res = await http.get(url, { params, responseType: 'blob' })
    saveBlob(res.data as Blob, filename)
  } catch (error) {
    const blob = (error as { response?: { data?: unknown } }).response?.data
    if (blob instanceof Blob) {
      try {
        const body = JSON.parse(await blob.text()) as ApiError
        ElMessage.error(body.message || '下载失败')
      } catch {
        ElMessage.error('下载失败')
      }
    }
    throw error
  }
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 上传文件（multipart/form-data）。 */
export async function upload<T>(url: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<T>(url, form)
  return data
}

export default http
