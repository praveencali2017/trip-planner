import { describe, expect, it, vi } from 'vitest'
import { jsonResponse, sseFrame, sseResponse } from '../test/sse'
import type { ChatEvent } from '../types'
import { streamChat } from './streamChat'

async function collect(response: Response): Promise<{ events: ChatEvent[]; fetchMock: ReturnType<typeof vi.fn> }> {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  const events: ChatEvent[] = []
  for await (const event of streamChat('thread-1', 'Plan Kyoto', new AbortController().signal)) events.push(event)
  return { events, fetchMock }
}

describe('streamChat', () => {
  it('posts the thread id and message as JSON with the abort signal', async () => {
    const { fetchMock } = await collect(sseResponse([sseFrame('done')]))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/chat')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ thread_id: 'thread-1', message: 'Plan Kyoto' })
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('yields every event in order when several arrive in one chunk', async () => {
    const { events } = await collect(
      sseResponse([sseFrame('status', { message: 'Researching…' }) + sseFrame('token', { text: 'Day' }) + sseFrame('done')]),
    )

    expect(events).toEqual([
      { name: 'status', data: { message: 'Researching…' } },
      { name: 'token', data: { text: 'Day' } },
      { name: 'done', data: {} },
    ])
  })

  it('reassembles a frame split across network chunks, including mid-character', async () => {
    const frame = new TextEncoder().encode(sseFrame('token', { text: 'café 京都' }))
    const splitInsideMultibyteChar = frame.indexOf(0xc3) + 1 // between the two bytes of "é"
    const { events } = await collect(
      sseResponse([frame.slice(0, 5), frame.slice(5, splitInsideMultibyteChar), frame.slice(splitInsideMultibyteChar), sseFrame('done')]),
    )

    expect(events).toEqual([
      { name: 'token', data: { text: 'café 京都' } },
      { name: 'done', data: {} },
    ])
  })

  it('skips frames without an event name, such as keep-alive comments', async () => {
    const { events } = await collect(sseResponse([': keep-alive\n\n', sseFrame('done')]))

    expect(events).toEqual([{ name: 'done', data: {} }])
  })

  it('throws with the status code when the server rejects the request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { detail: [] })))

    const stream = streamChat('t', '', new AbortController().signal)

    await expect(stream.next()).rejects.toThrow('The server rejected the request (HTTP 422).')
  })
})
