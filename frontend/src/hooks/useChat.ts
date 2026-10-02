import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '../api/streamChat'
import type { ChatMessage } from '../types'

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/** Conversation state for one trip thread, with a streaming assistant reply. */
export function useChat() {
  const [threadId, setThreadId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortControllerRef.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      const message = text.trim()
      if (!message || isStreaming) return

      const replyId = crypto.randomUUID()
      const appendToReply = (chunk: string) =>
        setMessages((current) =>
          current.map((m) => (m.id === replyId ? { ...m, content: m.content + chunk } : m)),
        )

      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'user', content: message },
        { id: replyId, role: 'assistant', content: '' },
      ])
      setError(null)
      setIsStreaming(true)
      const controller = new AbortController()
      abortControllerRef.current = controller

      try {
        for await (const event of streamChat(threadId, message, controller.signal)) {
          if (event.name === 'token') {
            setStatus(null)
            appendToReply(event.data.text)
          } else if (event.name === 'status') {
            setStatus(event.data.message)
          } else if (event.name === 'error') {
            setError(event.data.message)
          }
        }
      } catch (caught) {
        if (!isAbortError(caught)) {
          setError(caught instanceof Error ? caught.message : 'Could not reach the server.')
        }
      } finally {
        abortControllerRef.current = null
        setIsStreaming(false)
        setStatus(null)
        // Drop the reply bubble if nothing arrived (stopped early or failed before any text).
        setMessages((current) => current.filter((m) => m.id !== replyId || m.content))
      }
    },
    [isStreaming, threadId],
  )

  const stop = useCallback(() => abortControllerRef.current?.abort(), [])

  const startNewTrip = useCallback(() => {
    abortControllerRef.current?.abort()
    setThreadId(crypto.randomUUID())
    setMessages([])
    setError(null)
  }, [])

  return { threadId, messages, status, error, isStreaming, send, stop, startNewTrip }
}
