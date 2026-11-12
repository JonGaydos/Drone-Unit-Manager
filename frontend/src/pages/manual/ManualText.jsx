// Inline **bold** inside a line. The lazy group has no trailing anchor, so a
// line whose ** never closes stays linear instead of backtracking.
function renderInline(text) {
  const parts = text.split(/\*\*(.+?)\*\*/)
  return parts.map((part, i) =>
    i % 2 === 1
      ? <strong key={i} className="text-foreground">{part}</strong>
      : part
  )
}

export default function ManualText({ text }) {
  return text.split('\n').map((line, i) => {
    const lineKey = `line-${i}-${line.slice(0, 20)}`
    if (line.startsWith('• ')) {
      return (
        <div key={lineKey} className="flex gap-2 ml-2 mt-1">
          <span className="text-muted-foreground">•</span>
          <span>{renderInline(line.slice(2))}</span>
        </div>
      )
    }
    if (line.match(/^\d+\./)) {
      return <div key={lineKey} className="ml-2 mt-1">{renderInline(line)}</div>
    }
    if (line.trim() === '') return <div key={lineKey} className="h-2" />
    return <span key={lineKey}>{renderInline(line)} </span>
  })
}
