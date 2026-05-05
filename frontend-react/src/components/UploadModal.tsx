import { useEffect, useMemo, useState } from 'react'
import { createApiClient } from '../api/client'

export type IndexedDoc = {
  name: string
  documentId: string
  chunkCount: number
}

type Props = {
  open: boolean
  apiBaseUrl: string
  onClose: () => void
  onIndexed: (doc: IndexedDoc) => void
}

type Step =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'indexing' }
  | { kind: 'done' }
  | { kind: 'error'; message: string }

export function UploadModal({ open, apiBaseUrl, onClose, onIndexed }: Props) {
  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<Step>({ kind: 'idle' })

  useEffect(() => {
    if (!open) {
      setFile(null)
      setStep({ kind: 'idle' })
    }
  }, [open])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  async function uploadAndIndex() {
    if (!file) return
    setStep({ kind: 'uploading' })
    try {
      const up = await api.uploadDocument(file)
      setStep({ kind: 'indexing' })
      await api.indexDocument(up.document_id)
      const doc: IndexedDoc = { name: file.name, documentId: up.document_id, chunkCount: up.chunk_count }
      setStep({ kind: 'done' })
      onIndexed(doc)
      onClose()
    } catch (e) {
      setStep({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
    }
  }

  if (!open) return null

  const disabled = step.kind === 'uploading' || step.kind === 'indexing'

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div className="modalCard">
        <div className="modalHeader">
          <div>
            <div className="modalTitle">Upload document</div>
            <div className="modalSub">PDF, TXT, or an image. We’ll index it for grounded answers.</div>
          </div>
          <button type="button" className="iconBtn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="modalBody">
          <input
            className="input"
            type="file"
            accept=".pdf,.txt,image/png,image/jpeg,image/webp,image/gif"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />

          {step.kind === 'uploading' ? <div className="statusWarn">Uploading…</div> : null}
          {step.kind === 'indexing' ? <div className="statusWarn">Indexing…</div> : null}
          {step.kind === 'error' ? <div className="statusErr">{step.message}</div> : null}
        </div>

        <div className="modalFooter">
          <button type="button" className="btn" onClick={onClose} disabled={disabled}>
            Cancel
          </button>
          <button type="button" className="btn btnPrimary" onClick={() => void uploadAndIndex()} disabled={!file || disabled}>
            {step.kind === 'uploading' || step.kind === 'indexing' ? 'Working…' : 'Upload & index'}
          </button>
        </div>
      </div>
      <button className="modalBackdrop" type="button" aria-label="Close" onClick={onClose} />
    </div>
  )
}

