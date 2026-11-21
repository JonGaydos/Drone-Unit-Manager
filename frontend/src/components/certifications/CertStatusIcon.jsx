import { createElement } from 'react'
import { statusColor, statusIcon } from './certStatus'

const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

/** The icon for a status, decorative: the label sits on its container. */
export function StatusGlyph({ status, className }) {
  return createElement(statusIcon(status), { className, 'aria-hidden': 'true' })
}

/** A status as a colored icon; a button when it opens the certification. */
export function CertStatusIcon({ cell, onOpen }) {
  const className = `inline-flex h-7 w-7 items-center justify-center rounded-full ${statusColor(cell.status)}`
  const icon = <StatusGlyph status={cell.status} className="h-4 w-4" />
  if (!onOpen) {
    return <span role="img" aria-label={cell.label} title={cell.title} className={className}>{icon}</span>
  }
  return (
    <button type="button" aria-label={cell.label} title={cell.title} onClick={onOpen}
      className={`${className} transition-shadow hover:ring-2 hover:ring-ring/40 ${FOCUS}`}>
      {icon}
    </button>
  )
}

/** A status chip naming the certification, with its expiration date. */
export function CertChip({ name, cell, onOpen }) {
  const className = `inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${statusColor(cell.status)}`
  const content = (
    <>
      <StatusGlyph status={cell.status} className="h-3.5 w-3.5 shrink-0" />
      <span>{name}</span>
      {cell.shortDate && <span className="tabular-nums opacity-80">{cell.shortDate}</span>}
    </>
  )
  if (!onOpen) {
    return (
      <span className={className} title={cell.title}>
        {content}<span className="sr-only">: {cell.text}</span>
      </span>
    )
  }
  return (
    <button type="button" aria-label={cell.label} title={cell.title} onClick={onOpen}
      className={`${className} transition-shadow hover:ring-2 hover:ring-ring/40 ${FOCUS}`}>
      {content}
    </button>
  )
}
