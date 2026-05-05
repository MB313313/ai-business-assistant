import { useEffect, useMemo, useRef, useState } from 'react'

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  role: ChatRole
  content: string
  /** When true, assistant text reveals letter-by-letter once (then stays full). */
  typewriter?: boolean
}

type Props = {
  messages: ChatMessage[]
  /** Show animated “typing” dots while waiting for the assistant reply */
  assistantTyping?: boolean
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function AvatarAssistant() {
  return (
    <div className="msgAvatar msgAvatarAi" role="img" aria-label="Assistant">
      <svg
        className="msgAvatarSvg msgAvatarSvgRobot"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <g
          stroke="currentColor"
          strokeWidth="1.65"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="12" y1="4" x2="12" y2="6.15" />
          <circle cx="12" cy="2.35" r="1.2" fill="currentColor" stroke="none" />
          <path d="M 3.75 8.4 A 1.85 1.85 0 0 1 3.75 12.85" fill="none" />
          <path d="M 20.25 8.4 A 1.85 1.85 0 0 0 20.25 12.85" fill="none" />
          <rect
            x="4.15"
            y="6.05"
            width="15.7"
            height="10"
            rx="3.6"
            ry="3.6"
            fill="rgba(255, 255, 255, 0.06)"
          />
          <line x1="12" y1="16.05" x2="12" y2="17.55" />
          <rect
            x="5.65"
            y="17.55"
            width="12.7"
            height="6.15"
            rx="2.5"
            ry="2.5"
            fill="rgba(255, 255, 255, 0.05)"
          />
        </g>
        <circle cx="8.85" cy="11.05" r="1.25" fill="currentColor" stroke="none" />
        <circle cx="15.15" cy="11.05" r="1.25" fill="currentColor" stroke="none" />
        <circle cx="9.25" cy="20.55" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="12" cy="20.55" r="0.8" fill="currentColor" stroke="none" />
        <circle cx="14.75" cy="20.55" r="0.8" fill="currentColor" stroke="none" />
      </svg>
    </div>
  )
}

function AvatarUser() {
  return (
    <div className="msgAvatar msgAvatarUser" role="img" aria-label="You">
      <svg className="msgAvatarSvg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="9" r="3.5" stroke="currentColor" strokeWidth="1.45" />
        <path
          d="M5.75 20.25c.85-3.1 3.55-5.25 6.25-5.25s5.4 2.15 6.25 5.25"
          stroke="currentColor"
          strokeWidth="1.45"
          strokeLinecap="round"
        />
      </svg>
    </div>
  )
}

function TypewriterBubble({ text }: { text: string }) {
  const chars = useMemo(() => Array.from(text), [text])
  const reduced = useMemo(() => prefersReducedMotion(), [])
  const [visible, setVisible] = useState(() => (reduced ? chars.length : 0))
  const [done, setDone] = useState(reduced)
  const wrapRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (done) return
    const list = wrapRef.current?.closest('.chatList') as HTMLElement | null
    if (list) list.scrollTop = list.scrollHeight
  }, [visible, done])

  useEffect(() => {
    if (done) return
    if (visible >= chars.length) {
      setDone(true)
      return
    }
    const ch = chars[visible] ?? ''
    const ms = ch === '\n' ? 48 : /\s/.test(ch) ? 12 : 16
    const id = window.setTimeout(() => setVisible((v) => v + 1), ms)
    return () => window.clearTimeout(id)
  }, [visible, chars, done])

  if (done) return <>{text}</>

  const shown = chars.slice(0, visible).join('')
  return (
    <span ref={wrapRef} className="typewriterWrap">
      {shown}
      <span className="typewriterCursor" aria-hidden="true" />
    </span>
  )
}

export function MessageList({ messages, assistantTyping }: Props) {
  const typingRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!assistantTyping) return
    typingRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [assistantTyping, messages.length])

  return (
    <div className="chatList">
      {messages.map((m, idx) => {
        const isUser = m.role === 'user'
        return (
          <div
            key={idx}
            className={['bubbleRow', isUser ? 'bubbleRowUser' : 'bubbleRowAssistant'].join(' ')}
          >
            {isUser ? null : <AvatarAssistant />}
            <div className={['bubble', isUser ? 'bubbleUser' : 'bubbleAssistant'].join(' ')}>
              {isUser ? (
                m.content
              ) : m.typewriter ? (
                <TypewriterBubble text={m.content} />
              ) : (
                m.content
              )}
            </div>
            {isUser ? <AvatarUser /> : null}
          </div>
        )
      })}
      {assistantTyping ? (
        <div
          ref={typingRef}
          className="bubbleRow bubbleRowAssistant"
          aria-live="polite"
          aria-busy="true"
        >
          <AvatarAssistant />
          <div className="bubble bubbleAssistant bubbleTyping">
            <span className="srOnly">Assistant is replying</span>
            <span className="typingWave" aria-hidden="true">
              <span className="typingDot" />
              <span className="typingDot" />
              <span className="typingDot" />
            </span>
          </div>
        </div>
      ) : null}
    </div>
  )
}

