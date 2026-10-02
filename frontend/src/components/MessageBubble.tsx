import Markdown from 'react-markdown'
import type { ChatMessage } from '../types'

interface MessageBubbleProps {
  message: ChatMessage
  isStreaming: boolean
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  return (
    <article className={`bubble bubble--${message.role}`} aria-busy={isStreaming}>
      {message.role === 'assistant' ? (
        <Markdown
          components={{
            a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
          }}
        >
          {message.content}
        </Markdown>
      ) : (
        <p>{message.content}</p>
      )}
      {isStreaming && <span className="cursor" aria-hidden="true" />}
    </article>
  )
}
