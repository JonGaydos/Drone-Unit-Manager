import { Wrench } from 'lucide-react'

/**
 * Maintenance history card shared by the fleet detail pages.
 * @param {object[]} records - Maintenance records for the entity.
 */
export default function MaintenanceHistoryCard({ records }) {
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <Wrench className="w-4 h-4 text-primary" />
        <h3 className="font-semibold text-foreground">Maintenance History</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Date</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium">Description</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Type</th>
              <th className="text-left px-4 py-2 text-muted-foreground font-medium hidden md:table-cell">Performed By</th>
              <th className="text-right px-4 py-2 text-muted-foreground font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            {records.map(m => (
              <tr key={m.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="px-4 py-2 text-foreground">{m.date || m.performed_date || '--'}</td>
                <td className="px-4 py-2 text-foreground">{m.description || '--'}</td>
                <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                <td className="px-4 py-2 text-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                <td className="px-4 py-2 text-foreground text-right">{m.cost == null ? '--' : `$${Number.parseFloat(m.cost).toFixed(2)}`}</td>
              </tr>
            ))}
            {records.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
