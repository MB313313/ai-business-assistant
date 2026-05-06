import { useEffect, useMemo, useRef, useState } from 'react'
import { MessageList, type ChatMessage } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import { createApiClient } from './api/client'
import type { IndexedDoc } from './components/UploadModal'
import { Tooltip } from './components/Tooltip'
import type { ChatThreadItem } from './components/Sidebar'

type AttachmentStatus = 'processing' | 'ready' | 'error'
type ChatAttachment = {
  id: string
  file: File
  name: string
  mediaType: string
  status: AttachmentStatus
  error?: string
}

const CHAT_FILE_MAX_BYTES = 25 * 1024 * 1024
const CHAT_TOTAL_MAX_BYTES = 100 * 1024 * 1024

function fileSuffix(name: string): string {
  const n = (name || '').toLowerCase().trim()
  const i = n.lastIndexOf('.')
  return i >= 0 ? n.slice(i) : ''
}

function isChatAttachmentSupported(f: File): boolean {
  const mt = (f.type || '').toLowerCase()
  if (mt.startsWith('image/')) return true
  if (mt.startsWith('video/')) return true
  const suf = fileSuffix(f.name)
  return suf === '.pdf' || suf === '.txt' || suf === '.docx'
}

function App() {
  const [isMobile, setIsMobile] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 980px)')
    const apply = () => {
      const mobile = mq.matches
      setIsMobile(mobile)
      setSidebarOpen(!mobile)
    }
    apply()
    const onChange = () => apply()
    if ('addEventListener' in mq) mq.addEventListener('change', onChange)
    else (mq as any).addListener(onChange)
    return () => {
      if ('removeEventListener' in mq) mq.removeEventListener('change', onChange)
      else (mq as any).removeListener(onChange)
    }
  }, [])

  const [apiBaseUrl, setApiBaseUrl] = useState<string>(() => {
    return window.localStorage.getItem('apiBaseUrl') ?? '/api'
  })
  useEffect(() => {
    window.localStorage.setItem('apiBaseUrl', apiBaseUrl)
  }, [apiBaseUrl])

  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [userId, setUserId] = useState<string>(() => window.localStorage.getItem('chatUserId') ?? '')
  const [threadId, setThreadId] = useState<string>(() => window.localStorage.getItem('chatThreadId') ?? '')
  const [threads, setThreads] = useState<ChatThreadItem[]>([])
  const [draft, setDraft] = useState('')
  const [chatAttachments, setChatAttachments] = useState<ChatAttachment[]>([])
  const [indexedDocs, setIndexedDocs] = useState<IndexedDoc[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>('')
  const [toast, setToast] = useState<string>('')
  const toastTimerRef = useRef<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const chipScrollerRef = useRef<HTMLDivElement | null>(null)
  const dragRef = useRef<{ active: boolean; startX: number; startLeft: number }>({
    active: false,
    startX: 0,
    startLeft: 0,
  })
  const anyProcessing = chatAttachments.some((a) => a.status === 'processing')
  const anyReady = chatAttachments.some((a) => a.status === 'ready')
  const anyFailed = chatAttachments.some((a) => a.status === 'error')
  const canSend = !busy && !anyProcessing && !anyFailed && (draft.trim().length > 0 || anyReady)

  useEffect(() => {
    window.localStorage.setItem('chatUserId', userId)
  }, [userId])

  useEffect(() => {
    window.localStorage.setItem('chatThreadId', threadId)
  }, [threadId])

  useEffect(() => {
    let cancelled = false
    async function initChat() {
      try {
        setError('')
        let uid = (userId ?? '').trim()
        if (!uid) {
          const u = await api.createAnonymousUser()
          uid = (u.user_id ?? '').toString()
          if (!uid) return
          if (cancelled) return
          setUserId(uid)
        }

        // Load threads list
        const tlist = await api.listThreads(uid)
        if (cancelled) return
        const normalized: ChatThreadItem[] = (tlist.threads ?? []).map((t) => ({
          id: t.id,
          title: t.title,
          pinned: !!t.pinned,
          updated_at: t.updated_at,
        }))
        setThreads(normalized)

        // If we have no active thread selected yet, pick the newest existing one (if any).
        let tid = (threadId ?? '').trim()
        if (!tid && normalized.length) {
          tid = normalized[0]?.id ?? ''
          if (tid && !cancelled) setThreadId(tid)
        }
        if (!tid) {
          // No threads yet — don't auto-create one. ChatGPT-style: create on first message.
          setMessages([])
          return
        }

        const hist = await api.listMessages(uid, tid)
        if (cancelled) return
        setMessages(
          (hist.messages ?? []).map((m) => ({
            role: m.role,
            content: (m.content ?? '').toString(),
          })),
        )
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : String(e))
      }
    }
    void initChat()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl])

  async function refreshThreads(uid: string, preferActiveId?: string) {
    const tlist = await api.listThreads(uid)
    const normalized: ChatThreadItem[] = (tlist.threads ?? []).map((t) => ({
      id: t.id,
      title: t.title,
      pinned: !!t.pinned,
      updated_at: t.updated_at,
    }))
    setThreads(normalized)
    if (preferActiveId && normalized.some((t) => t.id === preferActiveId)) {
      setThreadId(preferActiveId)
    }
  }

  async function selectThread(nextThreadId: string) {
    const uid = (userId ?? '').trim()
    const tid = (nextThreadId ?? '').trim()
    if (!uid || !tid) return
    setThreadId(tid)
    setMessages([])
    try {
      const hist = await api.listMessages(uid, tid)
      setMessages(
        (hist.messages ?? []).map((m) => ({
          role: m.role,
          content: (m.content ?? '').toString(),
        })),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function newChat() {
    setMessages([])
    setIndexedDocs([])
    setChatAttachments([])
    // ChatGPT-style: "New chat" doesn't create a server thread until first message.
    setThreadId('')
  }

  function showToast(msg: string) {
    setToast(msg)
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current)
    toastTimerRef.current = window.setTimeout(() => setToast(''), 2600)
  }

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  function autosizeTextarea() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    const max = 160
    const next = Math.min(max, el.scrollHeight)
    el.style.height = `${next}px`
  }

  useEffect(() => {
    // Keep height in sync (including after clears/sends).
    queueMicrotask(autosizeTextarea)
  }, [draft])

  async function addChatFiles(files: File[]) {
    const supported = files.filter((f) => !!f)
    const now = Date.now()
    const items: ChatAttachment[] = supported.map((f, idx) => ({
      id: `${now}-${idx}-${f.name}-${f.size}-${f.lastModified}`,
      file: f,
      name: f.name,
      mediaType: (f.type || '').toLowerCase(),
      status: 'processing',
    }))

    if (!items.length) return

    // Client-side size limits (match backend defaults)
    const existingBytes = chatAttachments.reduce((acc, a) => acc + (a.file?.size || 0), 0)
    let runningTotal = existingBytes

    setChatAttachments((prev) => {
      const next: ChatAttachment[] = []
      for (const it of items) {
        const sz = it.file.size || 0
        if (!isChatAttachmentSupported(it.file)) {
          next.push({
            ...it,
            status: 'error',
            error: 'Unsupported type. Use images, video, PDF, TXT, or DOCX.',
          })
          continue
        }
        if (sz > CHAT_FILE_MAX_BYTES) {
          next.push({
            ...it,
            status: 'error',
            error: `Too large (max ${Math.floor(CHAT_FILE_MAX_BYTES / (1024 * 1024))} MB).`,
          })
          continue
        }
        runningTotal += sz
        if (runningTotal > CHAT_TOTAL_MAX_BYTES) {
          next.push({
            ...it,
            status: 'error',
            error: `Total too large (max ${Math.floor(CHAT_TOTAL_MAX_BYTES / (1024 * 1024))} MB).`,
          })
          continue
        }
        next.push(it)
      }
      return [...next, ...prev]
    })

    // Process in background: ensure we can read the file (and it isn't blocked).
    await Promise.all(
      items.map(async (it) => {
        const f = it.file
        const id = it.id
        if (!isChatAttachmentSupported(f)) return
        if (f.size > CHAT_FILE_MAX_BYTES) return
        try {
          // Read a small prefix to trigger browser file access and show "loading" UX.
          await f.slice(0, 64 * 1024).arrayBuffer()
          setChatAttachments((prev) =>
            prev.map((a) => (a.id === id ? { ...a, status: 'ready' } : a)),
          )
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e)
          setChatAttachments((prev) =>
            prev.map((a) => (a.id === id ? { ...a, status: 'error', error: msg } : a)),
          )
        }
      }),
    )
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim()
    if (anyFailed) {
      showToast('Remove failed attachments before sending.')
      return
    }
    if (anyProcessing) {
      showToast('Please wait until attachments finish loading.')
      return
    }
    if (!trimmed && !anyReady) {
      showToast('Type a message or add an attachment.')
      return
    }

    setError('')
    setBusy(true)
    const userDisplay = trimmed || (anyReady ? '*Question with attachment*' : '')

    setMessages((prev) => [...prev, { role: 'user', content: userDisplay }])
    setDraft('')
    const attachmentsToSend = chatAttachments.filter((a) => a.status === 'ready').map((a) => a.file)
    setChatAttachments([])

    try {
      let uid = (userId ?? '').trim()
      if (!uid) {
        const u = await api.createAnonymousUser()
        uid = (u.user_id ?? '').toString()
        if (uid) setUserId(uid)
      }

      let tid = (threadId ?? '').trim()
      if (!tid) {
        const r = await api.createThread(uid)
        tid = (r.thread_id ?? '').toString()
        if (tid) setThreadId(tid)
        await refreshThreads(uid, tid)
      }

      const resp = await api.chatWithFiles(uid, tid, trimmed, attachmentsToSend)
      const reply = (resp.reply ?? '').toString().trim()
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: reply || '(no reply)', typewriter: true },
      ])

      // Title/pin/order may have changed after message persistence.
      await refreshThreads(uid, tid)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'I could not complete that request right now. Please try again in a moment.',
          typewriter: true,
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`appShell ${sidebarOpen ? 'appShellSidebarOpen' : 'appShellSidebarClosed'}`}>
      {isMobile ? (
        <button
          type="button"
          className={[
            'sidebarToggle',
            'sidebarToggleDocked',
            sidebarOpen ? 'sidebarToggleDocked--open' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <span className="burgerBar burgerBarTop" aria-hidden="true" />
          <span className="burgerBar burgerBarMid" aria-hidden="true" />
          <span className="burgerBar burgerBarBot" aria-hidden="true" />
        </button>
      ) : null}
      {isMobile ? (
        <>
          <div className={`sidebarDrawer ${sidebarOpen ? 'sidebarDrawerOpen' : ''}`}>
            <Sidebar
              apiBaseUrl={apiBaseUrl}
              onApiBaseUrlChange={setApiBaseUrl}
              onClearConversation={() => void newChat()}
              threads={threads}
              activeThreadId={threadId}
              onSelectThread={(id) => void selectThread(id)}
              onRenameThread={(id, title) => {
                const uid = (userId ?? '').trim()
                if (!uid) return
                void api
                  .renameThread(uid, id, title)
                  .then(() => refreshThreads(uid, threadId))
                  .catch(() => {
                    // ignore
                  })
              }}
              onDeleteThread={(id) => {
                const uid = (userId ?? '').trim()
                if (!uid) return
                void api
                  .deleteThread(uid, id)
                  .then(() => {
                    const nextActive = id === threadId ? '' : threadId
                    return refreshThreads(uid, nextActive)
                  })
                  .then(() => {
                    if (id === threadId) void newChat()
                  })
                  .catch(() => {
                    // ignore
                  })
              }}
              onPinThread={(id, pinned) => {
                const uid = (userId ?? '').trim()
                if (!uid) return
                void api
                  .pinThread(uid, id, pinned)
                  .then(() => refreshThreads(uid, threadId))
                  .catch(() => {
                    // ignore
                  })
              }}
              kbDocs={indexedDocs}
              onKbIndexed={(doc) => setIndexedDocs((prev) => [doc, ...prev])}
              onRequestClose={() => setSidebarOpen(false)}
            />
          </div>
          {sidebarOpen ? (
            <button
              type="button"
              className="sidebarBackdrop"
              aria-label="Close sidebar"
              onClick={() => setSidebarOpen(false)}
            />
          ) : null}
        </>
      ) : (
        <Sidebar
          apiBaseUrl={apiBaseUrl}
          onApiBaseUrlChange={setApiBaseUrl}
          onClearConversation={() => void newChat()}
          threads={threads}
          activeThreadId={threadId}
          onSelectThread={(id) => void selectThread(id)}
          onRenameThread={(id, title) => {
            const uid = (userId ?? '').trim()
            if (!uid) return
            void api
              .renameThread(uid, id, title)
              .then(() => refreshThreads(uid, threadId))
              .catch(() => {
                // ignore
              })
          }}
          onDeleteThread={(id) => {
            const uid = (userId ?? '').trim()
            if (!uid) return
            void api
              .deleteThread(uid, id)
              .then(() => {
                const nextActive = id === threadId ? '' : threadId
                return refreshThreads(uid, nextActive)
              })
              .then(() => {
                if (id === threadId) void newChat()
              })
              .catch(() => {
                // ignore
              })
          }}
          onPinThread={(id, pinned) => {
            const uid = (userId ?? '').trim()
            if (!uid) return
            void api
              .pinThread(uid, id, pinned)
              .then(() => refreshThreads(uid, threadId))
              .catch(() => {
                // ignore
              })
          }}
          kbDocs={indexedDocs}
          onKbIndexed={(doc) => setIndexedDocs((prev) => [doc, ...prev])}
        />
      )}

      <main className="main">
        <div>
          <header className={['pageHeader', isMobile ? 'pageHeader--withNav' : ''].filter(Boolean).join(' ')}>
            <div className="pageHeaderTitleLine">
              <h1 className="title titleBig pageHeaderTitle">AI Business Assistant</h1>
            </div>
            <p className="subtitle subtitleBig pageHeaderSubtitle">
              Welcome. This workspace is here to help you get clear, reliable answers to business
              questions—using your indexed documents and company knowledge so responses stay aligned
              with the information your organization trusts.
            </p>
          </header>

          <details className="howTo card" open={false}>
            <summary className="howToSummary">
              <span>How to use</span>
              <span className="howToChevron" aria-hidden="true">▾</span>
            </summary>
            <div className="howToBody">
              <ol className="howToList">
                <li>
                  In the sidebar, set the <b>Service link</b> (keep <code>/api</code> for local dev).
                </li>
                <li>
                  Click <b>Test connection</b> to confirm the assistant service is reachable.
                </li>
                <li>
                  Under <b>Document knowledge base</b>, upload a PDF/TXT/image and click <b>Upload &amp; index</b>.
                </li>
                <li>
                  Ask questions in the chat. Use the <b>+</b> to attach images to your next message.
                </li>
              </ol>
              <div className="howToTip">
                Tip: If you don’t index anything yet, answers will be limited. Index at least one document first.
              </div>
            </div>
          </details>
        </div>

        {error ? (
          <div className="card">
            <Tooltip label={error}>
              <div className="statusErr">{error}</div>
            </Tooltip>
          </div>
        ) : null}

        <MessageList messages={messages} assistantTyping={busy} />

        <div className="composerBar">
          <div className={`composerPill ${chatAttachments.length ? 'composerPillHasChips' : ''}`}>
            {chatAttachments.length ? (
              <div
                ref={chipScrollerRef}
                className="composerTopRow composerTopRowDraggable"
                onPointerDown={(e) => {
                  // Don't hijack clicks on the remove button (or anything inside it).
                  const target = e.target as HTMLElement | null
                  if (target?.closest?.('button')) return
                  if (e.button !== 0) return
                  const el = chipScrollerRef.current
                  if (!el) return
                  dragRef.current.active = true
                  dragRef.current.startX = e.clientX
                  dragRef.current.startLeft = el.scrollLeft
                  el.setPointerCapture(e.pointerId)
                }}
                onPointerMove={(e) => {
                  const el = chipScrollerRef.current
                  if (!el || !dragRef.current.active) return
                  const dx = e.clientX - dragRef.current.startX
                  el.scrollLeft = dragRef.current.startLeft - dx
                }}
                onPointerUp={(e) => {
                  const el = chipScrollerRef.current
                  dragRef.current.active = false
                  try {
                    el?.releasePointerCapture(e.pointerId)
                  } catch {
                    // ignore
                  }
                }}
                onPointerCancel={() => {
                  dragRef.current.active = false
                }}
              >
                {chatAttachments.map((a) => (
                  <div
                    key={a.id}
                    className="miniChip"
                    title={
                      a.status === 'processing'
                        ? 'Preparing attachment…'
                        : a.status === 'error'
                          ? a.error || 'Failed to prepare attachment'
                          : 'Attachment ready'
                    }
                  >
                    <div className="miniChipIcon">▣</div>
                    <div className="miniChipText">
                      <div className="miniChipName">{a.name}</div>
                      <div className="miniChipSub">
                        <span
                          className={[
                            'miniChipDot',
                            a.status === 'ready'
                              ? 'miniChipDotReady'
                              : a.status === 'error'
                                ? 'miniChipDotErr'
                                : '',
                          ].join(' ')}
                          aria-hidden="true"
                        />
                        {a.status === 'processing'
                          ? 'Loading…'
                          : a.status === 'error'
                            ? 'Failed'
                            : 'Ready'}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="chipX"
                      aria-label={`Remove ${a.name}`}
                      onPointerDown={(e) => {
                        // Prevent the scroller from capturing this pointer.
                        e.stopPropagation()
                      }}
                      onClick={() => setChatAttachments((prev) => prev.filter((x) => x.id !== a.id))}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="composerBottomRow">
              <div className="composerInputRow">
                <Tooltip label="Add attachments (images, video, PDF, TXT, DOCX)">
                  <button type="button" className="plusBtn" onClick={openFilePicker} aria-label="Add attachments">
                    +
                  </button>
                </Tooltip>
                <Tooltip label="Limits: images/video/PDF/TXT/DOCX. Max 25 MB per file, 100 MB total per message. Images must be ≤ 4 MB each.">
                  <button type="button" className="limitsPill" aria-label="Chat attachment limits">
                    Limits
                  </button>
                </Tooltip>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm,video/quicktime,.pdf,.txt,.docx"
                  multiple
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? [])
                    void addChatFiles(files)
                    e.currentTarget.value = ''
                  }}
                />

                <textarea
                  className="composerTextarea"
                  ref={textareaRef}
                  value={draft}
                  placeholder="Ask anything"
                  onChange={(e) => {
                    setDraft(e.target.value)
                    // next tick after state updates
                    queueMicrotask(autosizeTextarea)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      void sendMessage(draft)
                    }
                  }}
                />
              </div>

              <div className="composerActions">
                <Tooltip label="Voice input is not implemented yet.">
                  <button type="button" className="circleBtn" aria-label="Voice (not implemented)" disabled>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="M19 11a7 7 0 0 1-14 0"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                    <path
                      d="M12 18v3"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                  </button>
                </Tooltip>

                <Tooltip
                  label={
                    busy
                      ? 'Sending…'
                      : anyProcessing
                        ? 'Please wait until attachments finish loading.'
                        : anyFailed
                          ? 'Remove failed attachments first.'
                        : 'Send message'
                  }
                >
                  <button
                    type="button"
                    className="circleBtn circleBtnPrimary"
                    disabled={!canSend}
                    onClick={() => void sendMessage(draft)}
                    aria-label="Send"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M12 5v14M12 5l6 6M12 5 6 11"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </Tooltip>
              </div>
            </div>
          </div>
        </div>
      </main>

      {toast ? (
        <div className="toast" role="status" aria-live="polite">
          {toast}
        </div>
      ) : null}
    </div>
  )
}

export default App
