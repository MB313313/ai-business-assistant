export type ChatImagePart = {
  media_type: string
  base64_data: string
}

export type ChatRequest = {
  message?: string
  images?: ChatImagePart[]
  thread_id?: string
}

export type ChatResponse = {
  reply: string
}

export type HealthResponse = {
  status: string
}

export type UploadDocumentResponse = {
  chunk_count: number
  document_id: string
}

export type IndexRequest = {
  document_id: string
}

export type IndexResponse = {
  indexed_chunks: number
  total_vectors: number
}

export type ApiClientOptions = {
  /**
   * Base URL for the API.
   * - For dev proxy: use '/api' (default)
   * - For direct calls: use 'http://127.0.0.1:8000'
   */
  baseUrl?: string
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 120_000

/** Shown when the browser cannot reach the API (backend down, wrong URL, offline, timeout). */
export const SERVER_UNREACHABLE_MESSAGE =
  "We're having trouble connecting to the server. Please check that the backend is running and try again."

export function isLikelyConnectionError(e: unknown): boolean {
  if (e == null || typeof e !== 'object') return false
  const err = e as Error
  const name = (err.name || '').toString()
  const msg = (err.message || '').toString().toLowerCase()

  if (name === 'AbortError') return true

  if (e instanceof TypeError) {
    if (msg.includes('failed to fetch') || msg.includes('networkerror') || msg.includes('load failed')) {
      return true
    }
  }

  if (msg.includes('network request failed')) return true

  // Dev proxy / gateway when the upstream (e.g. uvicorn) is down
  const head = (err.message || '').trim()
  if (/^(502|503|504)(\s|$)/.test(head)) return true

  return false
}

function joinUrl(baseUrl: string, path: string): string {
  const b = baseUrl.replace(/\/+$/, '')
  const p = path.startsWith('/') ? path : `/${path}`
  return `${b}${p}`
}

async function fetchJson<T>(url: string, init: RequestInit, timeoutMs: number): Promise<T> {
  const controller = new AbortController()
  const id = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, { ...init, signal: controller.signal })
    if (!res.ok) {
      // Read body once — calling .json() then .text() throws "body stream already read".
      const raw = (await res.text()).trim()
      if ([502, 503, 504].includes(res.status)) {
        throw new Error(`${res.status} ${res.statusText}`.trim())
      }
      // Vite's `/api` proxy often returns 500 with HTML or a short error when the target is down.
      if (res.status === 500) {
        const looksProxyUnreachable =
          !raw ||
          /^\s*</i.test(raw) ||
          /ECONNREFUSED|ECONNRESET|socket hang up|ENOTFOUND|connect error/i.test(raw)
        if (looksProxyUnreachable) {
          throw new Error('503 Service Unavailable')
        }
      }
      let detail = ''
      if (raw) {
        try {
          const body = JSON.parse(raw) as unknown
          if (body && typeof body === 'object' && 'detail' in body) {
            detail = String((body as { detail?: unknown }).detail ?? '')
          } else if (body && typeof body === 'object') {
            detail = JSON.stringify(body)
          } else {
            detail = raw
          }
        } catch {
          // Proxy often returns HTML when the backend is unreachable; don't surface huge pages.
          detail = raw.length > 400 ? `${res.status} ${res.statusText}`.trim() : raw
        }
      }
      const msg = detail || `${res.status} ${res.statusText}`
      throw new Error(msg)
    }
    return (await res.json()) as T
  } finally {
    window.clearTimeout(id)
  }
}

function headersWithUserId(userId?: string): Record<string, string> {
  const uid = (userId ?? '').trim()
  return uid ? { 'X-User-Id': uid } : {}
}

export async function fileToBase64Data(file: File): Promise<string> {
  const buf = await file.arrayBuffer()
  const bytes = new Uint8Array(buf)
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }
  return btoa(binary)
}

export type CreateAnonymousUserResponse = {
  user_id: string
}

export type CreateThreadResponse = {
  thread_id: string
}

export type EnsureDefaultThreadResponse = {
  thread_id: string
}

export type ChatMessageOut = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export type ThreadMessagesResponse = {
  thread_id: string
  messages: ChatMessageOut[]
}

export type ThreadOut = {
  id: string
  title: string
  pinned: boolean
  created_at: string
  updated_at: string
}

export type ListThreadsResponse = {
  threads: ThreadOut[]
}

export type RenameThreadResponse = {
  ok: boolean
}

export type PinThreadResponse = {
  ok: boolean
  pinned: boolean
}

export function createApiClient(opts: ApiClientOptions = {}) {
  const baseUrl = (opts.baseUrl ?? '/api').trim().replace(/\/+$/, '')
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS

  return {
    baseUrl,

    createAnonymousUser: async (): Promise<CreateAnonymousUserResponse> => {
      const url = joinUrl(baseUrl, '/users/anonymous')
      return await fetchJson<CreateAnonymousUserResponse>(url, { method: 'POST' }, 15_000)
    },

    ensureDefaultThread: async (userId: string): Promise<EnsureDefaultThreadResponse> => {
      const url = joinUrl(baseUrl, '/chats/default')
      return await fetchJson<EnsureDefaultThreadResponse>(
        url,
        { method: 'POST', headers: headersWithUserId(userId) },
        15_000,
      )
    },

    createThread: async (userId: string): Promise<CreateThreadResponse> => {
      const url = joinUrl(baseUrl, '/chats')
      return await fetchJson<CreateThreadResponse>(
        url,
        { method: 'POST', headers: headersWithUserId(userId) },
        15_000,
      )
    },

    listThreads: async (userId: string): Promise<ListThreadsResponse> => {
      const url = joinUrl(baseUrl, '/chats')
      return await fetchJson<ListThreadsResponse>(url, { method: 'GET', headers: headersWithUserId(userId) }, 15_000)
    },

    renameThread: async (userId: string, threadId: string, title: string): Promise<RenameThreadResponse> => {
      const url = joinUrl(baseUrl, `/chats/${encodeURIComponent(threadId)}`)
      return await fetchJson<RenameThreadResponse>(
        url,
        {
          method: 'PATCH',
          headers: { ...headersWithUserId(userId), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title }),
        },
        15_000,
      )
    },

    pinThread: async (userId: string, threadId: string, pinned: boolean): Promise<PinThreadResponse> => {
      const url = joinUrl(baseUrl, `/chats/${encodeURIComponent(threadId)}/pin`)
      return await fetchJson<PinThreadResponse>(
        url,
        {
          method: 'POST',
          headers: { ...headersWithUserId(userId), 'Content-Type': 'application/json' },
          body: JSON.stringify({ pinned }),
        },
        15_000,
      )
    },

    deleteThread: async (userId: string, threadId: string): Promise<{ ok: boolean }> => {
      const url = joinUrl(baseUrl, `/chats/${encodeURIComponent(threadId)}`)
      return await fetchJson<{ ok: boolean }>(
        url,
        { method: 'DELETE', headers: headersWithUserId(userId) },
        15_000,
      )
    },

    listMessages: async (userId: string, threadId: string): Promise<ThreadMessagesResponse> => {
      const url = joinUrl(baseUrl, `/chats/${encodeURIComponent(threadId)}/messages`)
      return await fetchJson<ThreadMessagesResponse>(
        url,
        { method: 'GET', headers: headersWithUserId(userId) },
        15_000,
      )
    },

    health: async (): Promise<HealthResponse> => {
      const url = joinUrl(baseUrl, '/health')
      return await fetchJson<HealthResponse>(url, { method: 'GET' }, 15_000)
    },

    uploadDocument: async (file: File): Promise<UploadDocumentResponse> => {
      const url = joinUrl(baseUrl, '/upload-document')
      const form = new FormData()
      form.append('file', file, file.name)
      return await fetchJson<UploadDocumentResponse>(
        url,
        {
          method: 'POST',
          body: form,
        },
        timeoutMs,
      )
    },

    indexDocument: async (documentId: string): Promise<IndexResponse> => {
      const url = joinUrl(baseUrl, '/vector/index')
      const body: IndexRequest = { document_id: documentId }
      return await fetchJson<IndexResponse>(
        url,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
        timeoutMs,
      )
    },

    chat: async (req: ChatRequest): Promise<ChatResponse> => {
      const url = joinUrl(baseUrl, '/chat')
      const body: ChatRequest = {
        message: (req.message ?? '').toString(),
        images: req.images ?? [],
        thread_id: req.thread_id,
      }
      return await fetchJson<ChatResponse>(
        url,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
        timeoutMs,
      )
    },

    chatWithFiles: async (
      userId: string | undefined,
      threadId: string | undefined,
      message: string,
      files: File[],
    ): Promise<ChatResponse> => {
      const url = joinUrl(baseUrl, '/chat-with-files')
      const form = new FormData()
      form.append('message', (message ?? '').toString())
      if ((threadId ?? '').trim()) form.append('thread_id', (threadId ?? '').trim())
      for (const f of files) {
        form.append('files', f, f.name)
      }
      return await fetchJson<ChatResponse>(
        url,
        {
          method: 'POST',
          headers: headersWithUserId(userId),
          body: form,
        },
        timeoutMs,
      )
    },
  }
}

