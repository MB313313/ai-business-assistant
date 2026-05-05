import { useEffect, useMemo, useState } from 'react'
import { AttachmentPicker } from './components/AttachmentPicker'
import { MessageList, type ChatMessage } from './components/MessageList'
import { Sidebar } from './components/Sidebar'
import { createApiClient, fileToBase64Data, type ChatImagePart } from './api/client'

function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState<string>(() => {
    return window.localStorage.getItem('apiBaseUrl') ?? '/api'
  })
  useEffect(() => {
    window.localStorage.setItem('apiBaseUrl', apiBaseUrl)
  }, [apiBaseUrl])

  const api = useMemo(() => createApiClient({ baseUrl: apiBaseUrl || '/api' }), [apiBaseUrl])

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>('')

  async function sendMessage(text: string, attachments: File[]) {
    const trimmed = text.trim()
    if (!trimmed && attachments.length === 0) return

    setError('')
    setBusy(true)
    const userDisplay =
      trimmed || (attachments.length ? '*Question with attachment*' : '')

    setMessages((prev) => [...prev, { role: 'user', content: userDisplay }])
    setDraft('')
    setFiles([])

    try {
      const images: ChatImagePart[] = []
      for (const f of attachments) {
        const mt = (f.type || '').toLowerCase()
        if (!mt.startsWith('image/')) continue
        images.push({ media_type: mt, base64_data: await fileToBase64Data(f) })
      }
      const resp = await api.chat({ message: trimmed, images })
      const reply = (resp.reply ?? '').toString().trim()
      setMessages((prev) => [...prev, { role: 'assistant', content: reply || '(no reply)' }])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'I could not complete that request right now. Please try again in a moment.',
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="appShell">
      <Sidebar
        apiBaseUrl={apiBaseUrl}
        onApiBaseUrlChange={setApiBaseUrl}
        onClearConversation={() => setMessages([])}
      />

      <main className="main">
        <div>
          <h1 className="title">AI Business Assistant</h1>
          <p className="subtitle">Upload documents, index them, then chat with grounded answers.</p>
        </div>

        {error ? (
          <div className="card">
            <div className="statusErr">{error}</div>
          </div>
        ) : null}

        <MessageList messages={messages} />

        <div className="composerBar">
          <AttachmentPicker files={files} onChange={setFiles} />
          <div className="composer">
            <textarea
              value={draft}
              placeholder="Ask anything"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void sendMessage(draft, files)
                }
              }}
            />
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy || (!draft.trim() && files.length === 0)}
              onClick={() => void sendMessage(draft, files)}
              style={{ borderRadius: 999 }}
            >
              {busy ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
