import { useCallback, useState } from 'react'
import { downloadItineraryPdf } from '../api/downloadItineraryPdf'

/** Export state for the "Download PDF" button, independent of the chat stream. */
export function usePdfExport(threadId: string) {
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const exportPdf = useCallback(async () => {
    setIsExporting(true)
    setError(null)
    try {
      await downloadItineraryPdf(threadId)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create the PDF.')
    } finally {
      setIsExporting(false)
    }
  }, [threadId])

  const clearError = useCallback(() => setError(null), [])

  return { exportPdf, isExporting, error, clearError }
}
