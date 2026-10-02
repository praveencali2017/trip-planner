interface StatusIndicatorProps {
  message: string
}

export function StatusIndicator({ message }: StatusIndicatorProps) {
  return (
    <div className="status" role="status">
      <span className="dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {message}
    </div>
  )
}
