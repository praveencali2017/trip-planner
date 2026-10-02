import { Composer } from './components/Composer'
import { EmptyState } from './components/EmptyState'
import { MessageList } from './components/MessageList'
import { useChat } from './hooks/useChat'
import { usePdfExport } from './hooks/usePdfExport'

export default function App() {
  const { threadId, messages, status, error, isStreaming, send, stop, startNewTrip } = useChat()
  const pdfExport = usePdfExport(threadId)
  const hasAssistantReply = messages.some((message) => message.role === 'assistant')
  const canExportPdf = hasAssistantReply && !isStreaming && !pdfExport.isExporting
  const visibleError = error ?? pdfExport.error

  const handleNewTrip = () => {
    pdfExport.clearError()
    startNewTrip()
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Trip Planner</h1>
        <div className="header-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={pdfExport.exportPdf}
            disabled={!canExportPdf}
            aria-busy={pdfExport.isExporting}
          >
            {pdfExport.isExporting ? 'Preparing PDF…' : 'Download PDF'}
          </button>
          <button type="button" className="button button--ghost" onClick={handleNewTrip}>
            New trip
          </button>
        </div>
      </header>
      <main className="chat">
        {messages.length === 0 ? (
          <EmptyState onPick={send} />
        ) : (
          <MessageList messages={messages} status={status} isStreaming={isStreaming} />
        )}
        {visibleError && (
          <p className="error" role="alert">
            {visibleError}
          </p>
        )}
      </main>
      <Composer isStreaming={isStreaming} onSend={send} onStop={stop} />
    </div>
  )
}
