import { useMemo, useState } from 'react'
import { createApiClient } from '../api/client'
import type { IndexedDoc } from './UploadModal'
import { Tooltip } from './Tooltip'

type Props = {
  apiBaseUrl: string
  onApiBaseUrlChange: (v: string) => void
  onClearConversation: () => void
  kbDocs: IndexedDoc[]
  onKbIndexed: (doc: IndexedDoc) => void
  onRequestClose?: () => void
}

function fileSuffix(name: string): string {
  const n = (name || '').toLowerCase().trim()
  const i = n.lastIndexOf('.')
  return i >= 0 ? n.slice(i) : ''
}

export function Sidebar({ apiBaseUrl, kbDocs, onKbIndexed, onRequestClose }: Props) {
  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])
  const [kbFile, setKbFile] = useState<File | null>(null)
  const [kbDragOver, setKbDragOver] = useState(false)
  const [kbState, setKbState] = useState<
    | { kind: 'idle' }
    | { kind: 'uploading' }
    | { kind: 'indexing' }
    | { kind: 'ok'; message: string }
    | { kind: 'err'; message: string }
  >({ kind: 'idle' })
  const [toast, setToast] = useState('')
  const toastTimerRef = useMemo(() => ({ id: null as number | null }), [])

  function showToast(msg: string) {
    setToast(msg)
    if (toastTimerRef.id) window.clearTimeout(toastTimerRef.id)
    toastTimerRef.id = window.setTimeout(() => setToast(''), 6500)
  }

  async function uploadToKnowledgeBase() {
    if (!kbFile) return

    const suf = fileSuffix(kbFile.name)
    if (['.mp4', '.webm', '.mov'].includes(suf) || (kbFile.type || '').toLowerCase().startsWith('video/')) {
      setKbState({ kind: 'idle' })
      showToast(
        'Videos can’t be added to the knowledge base. Upload PDF, TXT, or an image instead. (You can attach videos in chat.)',
      )
      return
    }

    setKbState({ kind: 'uploading' })
    try {
      const up = await api.uploadDocument(kbFile)
      setKbState({ kind: 'indexing' })
      await api.indexDocument(up.document_id)
      const doc: IndexedDoc = { name: kbFile.name, documentId: up.document_id, chunkCount: up.chunk_count }
      setKbState({ kind: 'ok', message: `Indexed (${up.chunk_count} chunks).` })
      // bubble up so App can keep list
      onKbIndexed(doc)
      setKbFile(null)
    } catch (e) {
      setKbState({ kind: 'err', message: e instanceof Error ? e.message : String(e) })
    }
  }

  return (
    <aside className="sidebar">
      <div>
        <div className="sidebarHeaderRow">
          <div />
          {onRequestClose ? (
            <button type="button" className="iconBtn" aria-label="Close sidebar" onClick={onRequestClose}>
              ×
            </button>
          ) : null}
        </div>

        <div className="kbIntro">
          <div className="kbHeroIcon kbHeroIconCenter kbHeroIconBig" aria-hidden="true">
            <svg width="65" height="65" viewBox="0 0 24 24" fill="none">
              <path
                d="M7 3h7l3 3v15a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
              <path
                d="M14 3v3a1 1 0 0 0 1 1h3"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
              <path
                d="M8 11h8M8 15h8M8 19h6"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="kbIntroTitle">Document knowledge base</div>
          <div className="kbIntroSub">
            Upload and index your company documents so the assistant can retrieve relevant excerpts and answer
            consistently.
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div className="label">Upload & index</div>
          <Tooltip label="Limits: PDF/TXT/images. Max ~15 MB per file. Upload then Index to make it searchable.">
            <button type="button" className="limitsPill" aria-label="Knowledge base limits">
              Limits
            </button>
          </Tooltip>
        </div>
        <Tooltip label="Upload a PDF, TXT, or image to add it to the searchable knowledge base.">
          <label
            className={`uploadZone ${kbDragOver ? 'uploadZoneActive' : ''}`}
            onDragEnter={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setKbDragOver(true)
            }}
            onDragOver={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setKbDragOver(true)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setKbDragOver(false)
            }}
            onDrop={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setKbDragOver(false)
              const f = e.dataTransfer.files?.[0]
              if (f) setKbFile(f)
            }}
          >
            <div className="uploadZoneInner">
              <div className="uploadZoneIcon" aria-hidden="true">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M7 18a4 4 0 0 1 .4-8A5 5 0 0 1 18 11.2 3.5 3.5 0 0 1 17.5 18"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                  />
                  <path
                    d="M12 12v7"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                  />
                  <path
                    d="M9.5 14.5 12 12l2.5 2.5"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div className="uploadZoneText">
                <div className="uploadZoneTitle">
                  {kbFile ? kbFile.name : 'Browse or drop a file'}
                </div>
                <div className="uploadZoneSub">PDF, TXT, PNG/JPG/WebP/GIF</div>
              </div>
            </div>
            <input
              className="uploadZoneInput"
              type="file"
              accept=".pdf,.txt,image/png,image/jpeg,image/webp,image/gif"
              onChange={(e) => setKbFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </Tooltip>
        <div className="kbActionRow">
          <a
            className="kbDownloadLink"
            href={`${import.meta.env.BASE_URL}sample.zip`}
            download="sample.zip"
            aria-label="Download all sample files as a zip (extract to get a sample folder)"
          >
            <span className="kbDownloadIconBtn" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 5v11m0 0-4-4m4 4 4-4"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M5 19h14"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="kbDownloadLabel">Download samples</span>
          </a>
          <button
            className="btn btnPrimary"
            type="button"
            onClick={() => void uploadToKnowledgeBase()}
            disabled={!kbFile || kbState.kind === 'uploading' || kbState.kind === 'indexing'}
          >
            {kbState.kind === 'uploading'
              ? 'Uploading…'
              : kbState.kind === 'indexing'
                ? 'Indexing…'
                : 'Upload & index'}
          </button>
        </div>
        {kbState.kind === 'ok' ? (
          <div className="statusOk" style={{ marginTop: 8 }}>
            {kbState.message}
          </div>
        ) : null}
        {kbState.kind === 'err' ? (
          <div className="statusErr" style={{ marginTop: 8 }}>
            {kbState.message}
          </div>
        ) : null}

        {kbDocs.length ? (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {kbDocs.slice(0, 6).map((d) => (
              <div key={d.documentId} className="miniChip" title={`Indexed: ${d.chunkCount} chunks`}>
                <div className="miniChipIcon">▦</div>
                <div className="miniChipText">
                  <div className="miniChipName">{d.name}</div>
                  <div className="miniChipSub">Indexed</div>
                </div>
              </div>
            ))}
            {kbDocs.length > 6 ? (
              <div className="subtitle" style={{ fontSize: 12 }}>
                +{kbDocs.length - 6} more
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="kbSectionDivider" role="presentation" aria-hidden="true" />

      {toast ? (
        <div className="toast toastRight" role="status" aria-live="polite">
          <div className="toastText">{toast}</div>
          <button type="button" className="toastClose" aria-label="Close" onClick={() => setToast('')}>
            ×
          </button>
        </div>
      ) : null}
    </aside>
  )
}

