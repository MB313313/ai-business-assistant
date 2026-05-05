export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  role: ChatRole
  content: string
}

type Props = {
  messages: ChatMessage[]
}

export function MessageList({ messages }: Props) {
  return (
    <div className="chatList">
      {messages.map((m, idx) => {
        const isUser = m.role === 'user'
        return (
          <div
            key={idx}
            className={`bubbleRow ${isUser ? 'bubbleRowUser' : ''}`}
          >
            <div className="bubble">{m.content}</div>
          </div>
        )
      })}
    </div>
  )
}

