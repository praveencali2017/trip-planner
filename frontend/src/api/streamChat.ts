import type { ChatEvent } from '../types'

const CHAT_ENDPOINT = '/api/chat'

/** Parse one SSE frame ("event: x\ndata: {...}") into a ChatEvent. */
function parseFrame(frame: string): ChatEvent | null {
  let name = ''
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) name = line.slice('event:'.length).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart())
  }
  if (!name) return null
  return { name, data: JSON.parse(dataLines.join('\n') || '{}') } as ChatEvent
}

/**
 * Send a message and yield the reply's events as they arrive.
 * Uses fetch + a body reader because EventSource can only make GET requests.
 */
export async function* streamChat(
  threadId: string,
  message: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch(CHAT_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, message }),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`The server rejected the request (HTTP ${response.status}).`)
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const event = parseFrame(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (event) yield event
      }
    }
  } finally {
    reader.releaseLock()
  }
}
