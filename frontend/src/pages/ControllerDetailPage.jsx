import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { STATUS_COLORS } from '@/lib/constants'
import {
  ArrowLeft, Gamepad2, Wrench, Edit
} from 'lucide-react'
import DocumentUpload from '@/components/DocumentUpload'

export default function ControllerDetailPage() {
  const { id } = useParams()
  const { isAdmin } = useAuth()
  const [controller, setController] = useState(null)
  const [maintenance, setMaintenance] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get(`/controllers/${id}`),
      api.get(`/maintenance?entity_type=controller&entity_id=${id}`).catch(() => []),
    ]).then(([c, m]) => {
      setController(c)
      setMaintenance(m)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  if (!controller) return <div className="text-center text-muted-foreground py-12">Controller not found</div>

  const displayName = controller.nickname || controller.serial_number

  return (
    <div className="space-y-6">
      <Link to="/fleet" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Back to Fleet
      </Link>

      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-2xl bg-primary/15 flex items-center justify-center text-primary shrink-0">
            <Gamepad2 className="w-8 h-8" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-foreground">{displayName}</h2>
              {isAdmin && (
                <Link to="/fleet" className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent">
                  <Edit className="w-4 h-4" />
                </Link>
              )}
            </div>
            <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
              {controller.manufacturer && <span>{controller.manufacturer}</span>}
              {controller.model && <span>{controller.model}</span>}
              <span>S/N: {controller.serial_number}</span>
            </div>
            <span className={`inline-flex mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[controller.status] || 'bg-zinc-500/15 text-zinc-400'}`}>
              {controller.status || 'unknown'}
            </span>
          </div>
        </div>
      </div>

      {/* Maintenance History */}
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
              {maintenance.map(m => (
                <tr key={m.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="px-4 py-2 text-foreground">{m.date || m.performed_date || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{m.description || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.maintenance_type || m.type || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground hidden md:table-cell">{m.performed_by || '--'}</td>
                  <td className="px-4 py-2 text-muted-foreground text-right">{m.cost != null ? `$${parseFloat(m.cost).toFixed(2)}` : '--'}</td>
                </tr>
              ))}
              {maintenance.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No maintenance records</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Notes */}
      {controller.notes && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{controller.notes}</p>
        </div>
      )}

      {/* Documents */}
      <DocumentUpload entityType="controller" entityId={id} />
    </div>
  )
}
