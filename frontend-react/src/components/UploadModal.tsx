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
  userId?: string
  onClose: () => void
  onIndexed: (doc: IndexedDoc) => void
}

type Step =
  | { kind: 'idle' }
  | { kind: 'uploading'; index: number; total: number }
  | { kind: 'indexing'; index: number; total: number }
  | { kind: 'done' }
  | { kind: 'error'; message: string }

function fileSuffix(name: string): string {
  const n = (name || '').toLowerCase().trim()
  const i = n.lastIndexOf('.')
  return i >= 0 ? n.slice(i) : ''
}

export function UploadModal({ open, apiBaseUrl, userId, onClose, onIndexed }: Props) {
  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])
  const [files, setFiles] = useState<File[]>([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [step, setStep] = useState<Step>({ kind: 'idle' })

  useEffect(() => {
    if (!open) {
      setFiles([])
      setStep({ kind: 'idle' })
    } else {
      setFileInputKey((k) => k + 1)
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
    const list = files
    if (!list.length) return

    for (const file of list) {
      const suf = fileSuffix(file.name)
      if (['.mp4', '.webm', '.mov'].includes(suf) || (file.type || '').toLowerCase().startsWith('video/')) {
        setStep({
          kind: 'error',
          message:
            'Videos can’t be added to the knowledge base. Use PDF, TXT, or an image. (You can attach videos in chat.)',
        })
        return
      }
    }

    try {
      const uid = (userId ?? '').trim()
      const n = list.length
      for (let i = 0; i < n; i++) {
        const file = list[i]
        setStep({ kind: 'uploading', index: i + 1, total: n })
        const up = await api.uploadDocument(file, uid || undefined)
        setStep({ kind: 'indexing', index: i + 1, total: n })
        await api.indexDocument(up.document_id, uid || undefined)
        onIndexed({
          name: file.name,
          documentId: up.document_id,
          chunkCount: up.chunk_count,
        })
      }
      setStep({ kind: 'done' })
      onClose()
    } catch (e) {
      setStep({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
    }
  }

  if (!open) return null

  const disabled = step.kind === 'uploading' || step.kind === 'indexing'
  const fileLabel =
    files.length === 0
      ? 'No files chosen'
      : files.length === 1
        ? files[0].name
        : `${files.length} files selected`

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div className="modalCard">
        <div className="modalHeader">
          <div>
            <div className="modalTitle">Upload document</div>
            <div className="modalSub">PDF, TXT, or images. Select one or more files—we’ll index each for grounded answers.</div>
          </div>
          <button type="button" className="iconBtn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="modalBody">
          <input
            key={fileInputKey}
            className="input"
            type="file"
            multiple
            accept=".pdf,.txt,image/png,image/jpeg,image/webp,image/gif"
            onChange={(e) => setFiles(e.target.files?.length ? Array.from(e.target.files) : [])}
          />
          <div className="modalSub" style={{ marginTop: 6, fontSize: 13, opacity: 0.85 }}>
            {fileLabel}
          </div>

          {step.kind === 'uploading' ? (
            <div className="statusWarn">
              Uploading file {step.index} of {step.total}…
            </div>
          ) : null}
          {step.kind === 'indexing' ? (
            <div className="statusWarn">
              Indexing file {step.index} of {step.total}…
            </div>
          ) : null}
          {step.kind === 'error' ? <div className="statusErr">{step.message}</div> : null}
        </div>

        <div className="modalFooter">
          <button type="button" className="btn" onClick={onClose} disabled={disabled}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btnPrimary"
            onClick={() => void uploadAndIndex()}
            disabled={!files.length || disabled}
          >
            {step.kind === 'uploading' || step.kind === 'indexing' ? 'Working…' : 'Upload & index'}
          </button>
        </div>
      </div>
      <button className="modalBackdrop" type="button" aria-label="Close" onClick={onClose} />
    </div>
  )
}

