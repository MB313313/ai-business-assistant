import { useMemo, useState } from 'react'
import { createApiClient } from '../api/client'

type Props = {
  apiBaseUrl: string
  onApiBaseUrlChange: (v: string) => void
  onClearConversation: () => void
}

type ConnState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'ok' }
  | { kind: 'warn'; message: string }
  | { kind: 'err'; message: string }

type UploadState =
  | { kind: 'idle' }
  | { kind: 'working'; step: string }
  | { kind: 'ok'; message: string }
  | { kind: 'err'; message: string }

export function Sidebar({ apiBaseUrl, onApiBaseUrlChange, onClearConversation }: Props) {
  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])
  const [conn, setConn] = useState<ConnState>({ kind: 'idle' })

  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [upload, setUpload] = useState<UploadState>({ kind: 'idle' })

  async function testConnection() {
    setConn({ kind: 'checking' })
    try {
      const h = await api.health()
      if (h.status === 'ok') setConn({ kind: 'ok' })
      else setConn({ kind: 'warn', message: 'Service responded, but status is unusual.' })
    } catch (e) {
      setConn({ kind: 'err', message: e instanceof Error ? e.message : String(e) })
    }
  }

  async function uploadAndIndex() {
    if (!uploadFile) return
    setUpload({ kind: 'working', step: 'Uploading…' })
    try {
      const up = await api.uploadDocument(uploadFile)
      setUpload({ kind: 'working', step: 'Indexing…' })
      await api.indexDocument(up.document_id)
      setUpload({ kind: 'ok', message: `Ready (${up.chunk_count} chunks).` })
    } catch (e) {
      setUpload({ kind: 'err', message: e instanceof Error ? e.message : String(e) })
    }
  }

  return (
    <aside className="sidebar">
      <div>
        <div className="title">Workspace</div>
        <div className="subtitle">Company documents + optional images. Answers stay grounded in what you indexed.</div>
      </div>

      <div className="card">
        <div className="label">Connection</div>
        <input
          className="input"
          value={apiBaseUrl}
          onChange={(e) => onApiBaseUrlChange(e.target.value)}
          placeholder="/api (recommended) or http://127.0.0.1:8000"
        />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn btnPrimary" type="button" onClick={testConnection} disabled={conn.kind === 'checking'}>
            {conn.kind === 'checking' ? 'Checking…' : 'Test connection'}
          </button>
          {conn.kind === 'ok' ? <span className="statusOk">Connected</span> : null}
          {conn.kind === 'warn' ? <span className="statusWarn">{conn.message}</span> : null}
          {conn.kind === 'err' ? <span className="statusErr">{conn.message}</span> : null}
        </div>
      </div>

      <div className="card">
        <div className="label">Your documents</div>
        <input
          className="input"
          type="file"
          accept=".pdf,.txt,image/png,image/jpeg,image/webp,image/gif"
          onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
        />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn btnPrimary" type="button" onClick={uploadAndIndex} disabled={!uploadFile || upload.kind === 'working'}>
            {upload.kind === 'working' ? upload.step : 'Upload & add to knowledge base'}
          </button>
        </div>
        {upload.kind === 'ok' ? <div className="statusOk" style={{ marginTop: 8 }}>{upload.message}</div> : null}
        {upload.kind === 'err' ? <div className="statusErr" style={{ marginTop: 8 }}>{upload.message}</div> : null}
      </div>

      <div className="card">
        <div className="row">
          <button className="btn" type="button" onClick={onClearConversation}>
            Clear conversation
          </button>
        </div>
      </div>
    </aside>
  )
}

