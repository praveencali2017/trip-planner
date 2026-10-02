/** Test helpers that build fetch Responses shaped like the backend's real ones. */

const encoder = new TextEncoder()

export function sseFrame(name: string, data: object = {}): string {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`
}

/** A complete SSE response whose body arrives in the given raw byte chunks. */
export function sseResponse(chunks: (string | Uint8Array)[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk)
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

/**
 * An SSE response the test pushes events into one at a time, so intermediate UI states can be
 * asserted. Like real fetch, aborting the request's signal errors the body with an AbortError.
 */
export function controllableSse(signal?: AbortSignal | null) {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) })
  signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')))
  return {
    response: new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    send: (name: string, data: object = {}) => controller.enqueue(encoder.encode(sseFrame(name, data))),
    close: () => controller.close(),
  }
}

export function jsonResponse(status: number, body: object): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
