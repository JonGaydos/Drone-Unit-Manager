import { Link } from 'react-router-dom'
import { certCell } from './certStatus'
import { CertChip } from './CertStatusIcon'

function PilotCard({ row, certTypes, ctx }) {
  return (
    <li aria-label={row.pilot_name} className="bg-card border border-border rounded-xl p-4">
      <Link to={`/pilots/${row.pilot_id}`} className="font-semibold text-primary hover:underline">{row.pilot_name}</Link>
      <ul className="mt-3 flex flex-wrap gap-2">
        {certTypes.map(ct => {
          const cell = certCell(row, ct, ctx.labels)
          const onOpen = ctx.canOpen(cell.cert) ? () => ctx.onOpen(row, ct, cell.cert) : undefined
          return <li key={ct.id}><CertChip name={ct.name} cell={cell} onOpen={onOpen} /></li>
        })}
      </ul>
    </li>
  )
}

/** One card per pilot, their certifications as status chips. */
export function PilotCardsView({ rows, certTypes, emptyMessage, ctx }) {
  if (rows.length === 0) {
    return <div className="bg-card border border-border rounded-xl px-4 py-12 text-center text-muted-foreground">{emptyMessage}</div>
  }
  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
      {rows.map(row => <PilotCard key={row.pilot_id} row={row} certTypes={certTypes} ctx={ctx} />)}
    </ul>
  )
}
