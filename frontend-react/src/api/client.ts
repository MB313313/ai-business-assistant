export type ChatImagePart = {
  media_type: string
  base64_data: string
}

export type ChatRequest = {
  message?: string
  images?: ChatImagePart[]
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
      let detail = ''
      try {
        const body = (await res.json()) as unknown
        if (body && typeof body === 'object' && 'detail' in body) {
          detail = String((body as any).detail ?? '')
        } else {
          detail = JSON.stringify(body)
        }
      } catch {
        detail = (await res.text()).trim()
      }
      // Prefer the API's user-facing detail message when present.
      const msg = detail || `${res.status} ${res.statusText}`
      throw new Error(msg)
    }
    return (await res.json()) as T
  } finally {
    window.clearTimeout(id)
  }
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

export function createApiClient(opts: ApiClientOptions = {}) {
  const baseUrl = (opts.baseUrl ?? '/api').trim().replace(/\/+$/, '')
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS

  return {
    baseUrl,

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

    chatWithFiles: async (message: string, files: File[]): Promise<ChatResponse> => {
      const url = joinUrl(baseUrl, '/chat-with-files')
      const form = new FormData()
      form.append('message', (message ?? '').toString())
      for (const f of files) {
        form.append('files', f, f.name)
      }
      return await fetchJson<ChatResponse>(
        url,
        {
          method: 'POST',
          body: form,
        },
        timeoutMs,
      )
    },
  }
}

