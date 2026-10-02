import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../types'
import { MessageBubble } from './MessageBubble'
import { StatusIndicator } from './StatusIndicator'

interface MessageListProps {
  messages: ChatMessage[]
  status: string | null
  isStreaming: boolean
}

export function MessageList({ messages, status, isStreaming }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null)
  const lastMessage = messages.at(-1)
  const streamingReplyId = isStreaming && lastMessage?.role === 'assistant' ? lastMessage.id : null
  const isAwaitingFirstToken = streamingReplyId !== null && !lastMessage?.content

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, status])

  return (
    <div className="message-list" role="log" aria-live="polite" aria-label="Conversation">
      {messages.map((message) =>
        message.content ? (
          <MessageBubble
            key={message.id}
            message={message}
            isStreaming={message.id === streamingReplyId}
          />
        ) : null,
      )}
      {(status || isAwaitingFirstToken) && <StatusIndicator message={status ?? 'Thinking…'} />}
      <div ref={endRef} />
    </div>
  )
}
