const PDF_ENDPOINT = '/api/itinerary-pdf'
const FALLBACK_FILENAME = 'itinerary.pdf'

function filenameFromDisposition(header: string | null): string {
  const match = header?.match(/filename="?([^";]+)"?/)
  return match?.[1] ?? FALLBACK_FILENAME
}

async function errorMessageFrom(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Not JSON (e.g. a proxy error page) — fall through to the generic message.
  }
  return `Could not create the PDF (HTTP ${response.status}).`
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** Ask the backend to polish this conversation's itinerary into a PDF, then download it. */
export async function downloadItineraryPdf(threadId: string): Promise<void> {
  const response = await fetch(PDF_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId }),
  })
  if (!response.ok) throw new Error(await errorMessageFrom(response))
  saveBlob(await response.blob(), filenameFromDisposition(response.headers.get('Content-Disposition')))
}
