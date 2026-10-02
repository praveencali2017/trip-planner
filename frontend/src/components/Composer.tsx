import { useState, type FormEvent, type KeyboardEvent } from 'react'

interface ComposerProps {
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export function Composer({ isStreaming, onSend, onStop }: ComposerProps) {
  const [draft, setDraft] = useState('')
  const canSend = !isStreaming && draft.trim().length > 0

  const submit = () => {
    if (!canSend) return
    onSend(draft)
    setDraft('')
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    submit()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label htmlFor="composer-input" className="visually-hidden">
        Message
      </label>
      <textarea
        id="composer-input"
        rows={1}
        value={draft}
        placeholder="Where are you, and where do you want to go? Or paste a YouTube travel video."
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        autoFocus
      />
      {isStreaming ? (
        <button type="button" className="button button--stop" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="button" disabled={!canSend}>
          Send
        </button>
      )}
    </form>
  )
}
