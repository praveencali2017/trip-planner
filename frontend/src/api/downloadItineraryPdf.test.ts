import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse } from '../test/sse'
import { downloadItineraryPdf } from './downloadItineraryPdf'

function pdfResponse(headers: Record<string, string> = {}): Response {
  return new Response(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
    status: 200,
    headers: { 'Content-Type': 'application/pdf', ...headers },
  })
}

describe('downloadItineraryPdf', () => {
  let clickedLinks: { href: string; download: string; inDocument: boolean }[]

  beforeEach(() => {
    clickedLinks = []
    // jsdom has no object URLs and can't navigate; record what would be downloaded instead.
    URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clickedLinks.push({ href: this.href, download: this.download, inDocument: document.body.contains(this) })
    })
  })

  it('requests the thread PDF and saves it under the server-provided filename', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      pdfResponse({ 'Content-Disposition': 'attachment; filename="4-day-kyoto-trip.pdf"' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await downloadItineraryPdf('thread-9')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/itinerary-pdf')
    expect(JSON.parse(init.body)).toEqual({ thread_id: 'thread-9' })
    expect(clickedLinks).toEqual([{ href: 'blob:mock-url', download: '4-day-kyoto-trip.pdf', inDocument: true }])
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
    expect(document.querySelector('a')).toBeNull() // temporary link cleaned up
  })

  it('falls back to itinerary.pdf when the filename header is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(pdfResponse()))

    await downloadItineraryPdf('t')

    expect(clickedLinks[0].download).toBe('itinerary.pdf')
  })

  it("surfaces the server's detail message on an error response", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'No itinerary yet.' })))

    await expect(downloadItineraryPdf('t')).rejects.toThrow('No itinerary yet.')
    expect(clickedLinks).toEqual([])
  })

  it('uses a generic message when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad Gateway</html>', { status: 502 })))

    await expect(downloadItineraryPdf('t')).rejects.toThrow('Could not create the PDF (HTTP 502).')
  })
})
