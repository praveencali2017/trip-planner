const EXAMPLE_PROMPTS = [
  "I'm in Tokyo. Plan me 4 days in Kyoto.",
  'A long weekend in Lisbon, leaving from Madrid.',
]

interface EmptyStateProps {
  onPick: (prompt: string) => void
}

export function EmptyState({ onPick }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2>Plan your next trip</h2>
      <p>Tell me where you are and where you want to go, or share a YouTube travel vlog to follow its route.</p>
      <ul>
        {EXAMPLE_PROMPTS.map((prompt) => (
          <li key={prompt}>
            <button type="button" className="example" onClick={() => onPick(prompt)}>
              {prompt}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
