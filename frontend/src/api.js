const BASE = ''

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

async function request(path, { method = 'GET', body, headers = {}, raw = false } = {}) {
  const opts = { method, credentials: 'same-origin', headers: { ...headers } }
  if (body !== undefined) {
    if (body instanceof FormData) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const res = await fetch(BASE + path, opts)
  const ct = res.headers.get('content-type') || ''
  let data
  if (raw) data = await res.blob()
  else if (ct.includes('application/json')) data = await res.json()
  else data = await res.text()

  if (res.status === 401 && !path.startsWith('/api/auth/login')) {
    onUnauthorized && onUnauthorized()
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.error)) || `请求失败 (${res.status})`
    throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), res.status, data)
  }
  return data
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: 'POST', body }),
  patch: (p, body) => request(p, { method: 'PATCH', body }),
  del: (p) => request(p, { method: 'DELETE' }),
  me: () => request('/api/auth/me'),
  login: (username, password) => request('/api/auth/login', { method: 'POST', body: { username, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  /** 任意 multipart 提交（上传项目、导入书签、恢复备份都用它） */
  postForm(path, formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', path)
      xhr.withCredentials = true
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }
      xhr.onload = () => {
        let data = {}
        try {
          data = JSON.parse(xhr.responseText || '{}')
        } catch {
          data = { detail: xhr.responseText }
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data)
        else if (xhr.status === 401) {
          onUnauthorized && onUnauthorized()
          reject(new ApiError('未登录', 401, data))
        } else {
          reject(new ApiError(data.detail || `上传失败 (${xhr.status})`, xhr.status, data))
        }
      }
      xhr.onerror = () => reject(new ApiError('网络错误，上传中断', 0))
      xhr.send(formData)
    })
  },

  upload(formData, onProgress) {
    return api.postForm('/api/projects', formData, onProgress)
  },
}

export function qs(params) {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return
    if (Array.isArray(v)) v.forEach((item) => sp.append(k, item))
    else sp.append(k, v)
  })
  return sp.toString()
}
