import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { CELL_COLORS, certCell, statusColor, statusText } from './certStatus'
import { CertStatusIcon, StatusGlyph } from './CertStatusIcon'

// Pinned inside the scroll box: the corner sits above both the header row and
// the pilot column, and every pinned cell has a solid background (matrix-pin,
// not bg-card, which is translucent or framed in some themes).
const CORNER = 'sticky top-0 left-0 z-30 matrix-pin text-left px-4 py-3 font-medium text-muted-foreground min-w-[150px] border-b border-r border-border'
const HEADER = 'sticky top-0 z-20 matrix-pin text-center px-3 py-3 font-medium text-muted-foreground min-w-[100px] border-b border-border'
const PILOT = 'sticky left-0 z-10 matrix-pin px-4 py-2 text-foreground font-medium border-b border-r border-border'
const THEAD_STYLE = { zIndex: 30 }
const MOVE = 'p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-20 disabled:cursor-not-allowed'

function TypeHeader({ ct, first, last, canManage, onReorder }) {
  return (
    <th className={HEADER}>
      <div className="flex items-center justify-center gap-0.5">
        {canManage && (
          <button onClick={() => onReorder(ct.id, 'left')} disabled={first} className={MOVE} title="Move left" aria-label={`Move ${ct.name} left`}>
            <ChevronLeft className="w-3 h-3" />
          </button>
        )}
        <span className="text-xs">{ct.name}</span>
        {canManage && (
          <button onClick={() => onReorder(ct.id, 'right')} disabled={last} className={MOVE} title="Move right" aria-label={`Move ${ct.name} right`}>
            <ChevronRight className="w-3 h-3" />
          </button>
        )}
      </div>
    </th>
  )
}

function MatrixCell({ row, ct, ctx }) {
  const cell = certCell(row, ct, ctx.labels)
  const id = cell.cert?.id
  const selectable = ctx.canManage && id && ct.has_expiration
  const onOpen = ctx.canOpen(cell.cert) ? () => ctx.onOpen(row, ct, cell.cert) : undefined
  return (
    <td className="relative px-3 py-2 text-center border-b border-border/50">
      {selectable && (
        <input
          type="checkbox"
          checked={ctx.selected.has(id)}
          onChange={() => ctx.onToggle(id)}
          className="absolute top-1 left-1 rounded border-border"
          title="Select for bulk renewal"
          aria-label="Select certification for bulk renewal"
        />
      )}
      <CertStatusIcon cell={cell} onOpen={onOpen} />
    </td>
  )
}

/** The statuses on screen, so the icons can be read without hovering. */
function Legend({ rows, certTypes, labels }) {
  const present = new Set(rows.flatMap(row => certTypes.map(ct => certCell(row, ct, labels).status)))
  const shown = Object.keys(CELL_COLORS).filter(s => present.has(s))
  if (shown.length === 0) return null
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground" aria-label="Status key">
      {shown.map(status => (
        <li key={status} className="flex items-center gap-1.5">
          <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full ${statusColor(status)}`}>
            <StatusGlyph status={status} className="h-3 w-3" />
          </span>
          {statusText(status, labels)}
        </li>
      ))}
    </ul>
  )
}

/** Pilots down, certification types across, each cell a status icon. */
export function MatrixView({ rows, certTypes, emptyMessage, ctx }) {
  return (
    <div className="space-y-2">
      <Legend rows={rows} certTypes={certTypes} labels={ctx.labels} />
      <div className="bg-card border border-border rounded-xl overflow-auto max-h-[calc(100vh-16rem)]">
        <table className="w-full text-sm border-separate border-spacing-0">
          {/* A global rule makes every thead sticky at z-index 10, a stacking
              context the pinned pilot cells would paint over; lift this one. */}
          <thead style={THEAD_STYLE}>
            <tr>
              <th className={CORNER}>Pilot</th>
              {certTypes.map((ct, idx) => (
                <TypeHeader key={ct.id} ct={ct} first={idx === 0} last={idx === certTypes.length - 1}
                  canManage={ctx.canManage} onReorder={ctx.onReorder} />
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.pilot_id} className="hover:bg-accent/30">
                <td className={PILOT}>
                  <Link to={`/pilots/${row.pilot_id}`} className="text-primary hover:underline">{row.pilot_name}</Link>
                </td>
                {certTypes.map(ct => <MatrixCell key={ct.id} row={row} ct={ct} ctx={ctx} />)}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={certTypes.length + 1} className="px-4 py-12 text-center text-muted-foreground">{emptyMessage}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
