import { useEffect, useMemo, useState } from 'react'
import { createApiClient } from '../api/client'
import type { IndexedDoc } from './UploadModal'
import { Tooltip } from './Tooltip'

export type ChatThreadItem = {
  id: string
  title: string
  pinned: boolean
  updated_at?: string
}

type Props = {
  apiBaseUrl: string
  onApiBaseUrlChange: (v: string) => void
  onClearConversation: () => void
  threads: ChatThreadItem[]
  activeThreadId: string
  onSelectThread: (threadId: string) => void
  onRenameThread: (threadId: string, nextTitle: string) => void
  onDeleteThread: (threadId: string) => void
  onPinThread: (threadId: string, pinned: boolean) => void
  kbDocs: IndexedDoc[]
  onKbIndexed: (doc: IndexedDoc) => void
  onRequestClose?: () => void
}

function fileSuffix(name: string): string {
  const n = (name || '').toLowerCase().trim()
  const i = n.lastIndexOf('.')
  return i >= 0 ? n.slice(i) : ''
}

export function Sidebar({
  apiBaseUrl,
  onClearConversation,
  threads,
  activeThreadId,
  onSelectThread,
  onRenameThread,
  onDeleteThread,
  onPinThread,
  kbDocs,
  onKbIndexed,
  onRequestClose,
}: Props) {
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
  const [menuForId, setMenuForId] = useState<string>('')
  const [chatSearch, setChatSearch] = useState<string>('')
  const [renameModal, setRenameModal] = useState<{ open: boolean; threadId: string; title: string }>({
    open: false,
    threadId: '',
    title: '',
  })
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; threadId: string; title: string }>({
    open: false,
    threadId: '',
    title: '',
  })

  const [prevTitles, setPrevTitles] = useState<Record<string, string>>({})
  const [titleAnim, setTitleAnim] = useState<
    Record<string, { full: string; visible: number; done: boolean }>
  >({})
  const [animatedIds, setAnimatedIds] = useState<Set<string>>(() => {
    try {
      const raw = window.localStorage.getItem('animatedThreadTitleIds') ?? '[]'
      const arr = JSON.parse(raw) as unknown
      if (Array.isArray(arr)) return new Set(arr.map((x) => String(x)))
    } catch {
      // ignore
    }
    return new Set()
  })

  useEffect(() => {
    if (!menuForId) return
    const onPointerDown = (e: PointerEvent) => {
      const el = e.target
      if (!(el instanceof Element)) return
      if (el.closest('.threadMenu') || el.closest('.chatThreadDots')) return
      setMenuForId('')
    }
    window.addEventListener('pointerdown', onPointerDown, true)
    return () => window.removeEventListener('pointerdown', onPointerDown, true)
  }, [menuForId])

  useEffect(() => {
    // Detect a "new title appears" transition and start a typewriter animation.
    // Typical flow: new thread is created with title "Chat", then after first reply backend updates title.
    const nextPrev: Record<string, string> = { ...prevTitles }
    const toStart: Array<{ id: string; title: string }> = []
    for (const t of threads) {
      const id = t.id
      const cur = (t.title || 'Chat').toString()
      const prev = (prevTitles[id] ?? '').toString()
      if (cur && cur !== 'Chat' && (prev === '' || prev === 'Chat') && prev !== cur && !animatedIds.has(id)) {
        toStart.push({ id, title: cur })
      }
      nextPrev[id] = cur
    }
    // Prune removed threads from animation maps
    const alive = new Set(threads.map((t) => t.id))
    const nextAnim: typeof titleAnim = {}
    for (const [id, v] of Object.entries(titleAnim)) {
      if (alive.has(id)) nextAnim[id] = v
    }
    if (toStart.length) {
      for (const it of toStart) {
        nextAnim[it.id] = { full: it.title, visible: 0, done: false }
      }
    }
    setPrevTitles(nextPrev)
    setTitleAnim(nextAnim)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threads])

  useEffect(() => {
    const active = Object.entries(titleAnim).filter(([, v]) => v && !v.done)
    if (!active.length) return
    const id = window.setTimeout(() => {
      setTitleAnim((prev) => {
        const next: typeof prev = { ...prev }
        const finished: string[] = []
        for (const [tid, st] of Object.entries(prev)) {
          if (!st || st.done) continue
          const nextVis = Math.min(st.full.length, st.visible + 1)
          const done = nextVis >= st.full.length
          next[tid] = { ...st, visible: nextVis, done }
          if (done) finished.push(tid)
        }
        if (finished.length) {
          setAnimatedIds((cur) => {
            const out = new Set(cur)
            for (const tid of finished) out.add(tid)
            try {
              window.localStorage.setItem('animatedThreadTitleIds', JSON.stringify(Array.from(out)))
            } catch {
              // ignore
            }
            return out
          })
        }
        return next
      })
    }, 18)
    return () => window.clearTimeout(id)
  }, [titleAnim])

  useEffect(() => {
    if (!renameModal.open && !deleteModal.open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setRenameModal({ open: false, threadId: '', title: '' })
        setDeleteModal({ open: false, threadId: '', title: '' })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [renameModal.open, deleteModal.open])

  function showToast(msg: string) {
    setToast(msg)
    if (toastTimerRef.id) window.clearTimeout(toastTimerRef.id)
    toastTimerRef.id = window.setTimeout(() => setToast(''), 6500)
  }

  const filteredThreads = useMemo(() => {
    const q = chatSearch.trim().toLowerCase()
    return threads
      .filter((t) => {
        if (!q) return true
        return (t.title || 'Chat').toLowerCase().includes(q)
      })
      .slice(0, 30)
  }, [threads, chatSearch])

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
      {renameModal.open ? (
        <div className="modalOverlay" role="dialog" aria-modal="true" aria-label="Rename chat">
          <div className="modalCard">
            <div className="modalHeader">
              <div>
                <div className="modalTitle">Rename chat</div>
                <div className="modalSub">Choose a short title for this chat.</div>
              </div>
              <button
                type="button"
                className="iconBtn"
                onClick={() => setRenameModal({ open: false, threadId: '', title: '' })}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="modalBody">
              <input
                className="input"
                value={renameModal.title}
                onChange={(e) => setRenameModal((s) => ({ ...s, title: e.target.value }))}
                placeholder="Chat title"
                autoFocus
              />
            </div>

            <div className="modalFooter">
              <button
                type="button"
                className="btn"
                onClick={() => setRenameModal({ open: false, threadId: '', title: '' })}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btnPrimary"
                onClick={() => {
                  const next = renameModal.title.trim()
                  if (!next) return
                  onRenameThread(renameModal.threadId, next)
                  setRenameModal({ open: false, threadId: '', title: '' })
                }}
                disabled={!renameModal.title.trim()}
              >
                Save
              </button>
            </div>
          </div>
          <button
            className="modalBackdrop"
            type="button"
            aria-label="Close"
            onClick={() => setRenameModal({ open: false, threadId: '', title: '' })}
          />
        </div>
      ) : null}

      {deleteModal.open ? (
        <div className="modalOverlay" role="dialog" aria-modal="true" aria-label="Delete chat">
          <div className="modalCard">
            <div className="modalHeader">
              <div>
                <div className="modalTitle">Delete chat?</div>
                <div className="modalSub">This will permanently delete the chat and its messages.</div>
              </div>
              <button
                type="button"
                className="iconBtn"
                onClick={() => setDeleteModal({ open: false, threadId: '', title: '' })}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="modalBody">
              <div className="subtitle" style={{ textAlign: 'left', margin: 0 }}>
                <b>{deleteModal.title || 'Chat'}</b>
              </div>
            </div>

            <div className="modalFooter">
              <button
                type="button"
                className="btn"
                onClick={() => setDeleteModal({ open: false, threadId: '', title: '' })}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btnPrimary"
                onClick={() => {
                  onDeleteThread(deleteModal.threadId)
                  setDeleteModal({ open: false, threadId: '', title: '' })
                }}
                style={{ background: '#ff5a5f', borderColor: 'rgba(255, 90, 95, 0.35)' }}
              >
                Delete
              </button>
            </div>
          </div>
          <button
            className="modalBackdrop"
            type="button"
            aria-label="Close"
            onClick={() => setDeleteModal({ open: false, threadId: '', title: '' })}
          />
        </div>
      ) : null}
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

      <div style={{ padding: '0 2px' }}>
        <div className="chatNav">
          <button type="button" className="chatNavButton" onClick={onClearConversation} aria-label="New chat">
            <span className="chatNavIcon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 20h9"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
                <path
                  d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <span className="chatNavLabel">New chat</span>
          </button>

          <div className="chatSearchRow" role="search">
            <span className="chatNavIcon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle
                  cx="11"
                  cy="11"
                  r="7"
                  stroke="currentColor"
                  strokeWidth="1.8"
                />
                <path
                  d="M20 20l-3.2-3.2"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <input
              className="chatSearchInput"
              value={chatSearch}
              onChange={(e) => setChatSearch(e.target.value)}
              placeholder="Search chats"
              aria-label="Search chats"
            />
          </div>
        </div>

        {threads.length ? (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {chatSearch.trim() && filteredThreads.length === 0 ? (
              <div className="subtitle" style={{ marginTop: 4, textAlign: 'center' }}>
                No chat Found
              </div>
            ) : null}
            {filteredThreads.map((t) => {
              const active = t.id === activeThreadId
              const open = menuForId === t.id
              return (
                <div
                  key={t.id}
                    className={['chatThreadRow', active ? 'chatThreadRowActive' : ''].filter(Boolean).join(' ')}
                  title={t.title}
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelectThread(t.id)
                    if (onRequestClose) onRequestClose()
                  }}
                >
                    <div className="chatThreadTitle">
                      {titleAnim[t.id] && !titleAnim[t.id]?.done ? (
                        <span className="chatThreadTitleText">
                          {titleAnim[t.id]?.full.slice(0, titleAnim[t.id]?.visible ?? 0)}
                          <span className="typewriterCursor" aria-hidden="true" />
                        </span>
                      ) : (
                        <span className="chatThreadTitleText">{t.title || 'Chat'}</span>
                      )}
                      {t.pinned ? (
                        <span className="chatThreadPinned" aria-label="Pinned chat" title="Pinned chat">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <path
                              d="M14 3l7 7-4 1-3 9-4-4-6 3 3-6-4-4 9-3 2-4Z"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </span>
                      ) : null}
                    </div>

                  <button
                    type="button"
                      className="chatThreadDots"
                    aria-label="Chat actions"
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuForId((cur) => (cur === t.id ? '' : t.id))
                    }}
                  >
                    ⋯
                  </button>

                  {open ? (
                    <div
                      className="threadMenu"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        className="threadMenuItem"
                        onClick={() => {
                          setMenuForId('')
                          setRenameModal({ open: true, threadId: t.id, title: t.title || 'Chat' })
                        }}
                      >
                        <span className="threadMenuIcon" aria-hidden="true">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path
                              d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </span>
                        Rename
                      </button>
                      <div className="threadMenuDivider" role="presentation" aria-hidden="true" />
                      <button
                        type="button"
                        className="threadMenuItem"
                        onClick={() => {
                          setMenuForId('')
                          onPinThread(t.id, !t.pinned)
                        }}
                      >
                        <span className="threadMenuIcon" aria-hidden="true">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path
                              d="M14 3l7 7-4 1-3 9-4-4-6 3 3-6-4-4 9-3 2-4Z"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </span>
                        {t.pinned ? 'Unpin chat' : 'Pin chat'}
                      </button>
                      <button
                        type="button"
                        className="threadMenuItem threadMenuItemDanger"
                        onClick={() => {
                          setMenuForId('')
                          setDeleteModal({ open: true, threadId: t.id, title: t.title || 'Chat' })
                        }}
                      >
                        <span className="threadMenuIcon" aria-hidden="true">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path
                              d="M4 7h16"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                            />
                            <path
                              d="M10 11v7M14 11v7"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                            />
                            <path
                              d="M6 7l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                            <path
                              d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"
                              stroke="currentColor"
                              strokeWidth="1.8"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </span>
                        Delete
                      </button>
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="subtitle" style={{ marginTop: 10 }}>
            No chats yet.
          </div>
        )}
      </div>

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

