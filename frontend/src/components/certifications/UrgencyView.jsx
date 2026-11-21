import { useId } from 'react'
import { Link } from 'react-router-dom'
import { URGENCY_GROUPS, groupByUrgency, statusColor } from './certStatus'
import { StatusGlyph } from './CertStatusIcon'

const ITEM_TEXT = 'min-w-0 truncate text-left text-foreground'

function UrgencyItem({ item, ctx }) {
  const open = ctx.canOpen(item.cert)
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 border-t border-border/50 first:border-t-0">
      <span className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${statusColor(item.status)}`}>
        <StatusGlyph status={item.status} className="h-3.5 w-3.5" />
      </span>
      <Link to={`/pilots/${item.row.pilot_id}`} className="font-medium text-primary hover:underline">{item.row.pilot_name}</Link>
      {open && (
        <button type="button" aria-label={item.label} title={item.title} onClick={() => ctx.onOpen(item.row, item.ct, item.cert)}
          className={`${ITEM_TEXT} rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}>
          {item.ct.name}
        </button>
      )}
      {!open && <span className={ITEM_TEXT} title={item.title}>{item.ct.name}</span>}
      <span className="ml-auto text-sm text-muted-foreground tabular-nums whitespace-nowrap">{item.shortDate || 'No expiration'}</span>
    </li>
  )
}

function UrgencyGroup({ group, items, ctx }) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="bg-card border border-border rounded-xl">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <StatusGlyph status={group.status} className={`h-4 w-4 ${group.tone}`} />
        <h2 id={headingId} className="text-sm font-semibold text-foreground">{group.title}</h2>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">{items.length}</span>
      </div>
      {items.length === 0 && <p className="px-4 py-3 text-sm text-muted-foreground">None</p>}
      {items.length > 0 && (
        <ul>{items.map(item => <UrgencyItem key={item.cert.id} item={item} ctx={ctx} />)}</ul>
      )}
    </section>
  )
}

/** Certifications by how soon they need attention. */
export function UrgencyView({ rows, certTypes, status, emptyMessage, ctx }) {
  if (rows.length === 0) {
    return <div className="bg-card border border-border rounded-xl px-4 py-12 text-center text-muted-foreground">{emptyMessage}</div>
  }
  const groups = groupByUrgency(rows, certTypes, status, ctx.labels)
  return (
    <div className="space-y-3">
      {URGENCY_GROUPS.map(group => <UrgencyGroup key={group.key} group={group} items={groups[group.key]} ctx={ctx} />)}
    </div>
  )
}
