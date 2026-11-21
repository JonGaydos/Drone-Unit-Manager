import { Edit, Eye, EyeOff, ShieldCheck, Trash2 } from 'lucide-react'

function TypeActions({ ct, onToggleHidden, onEdit, onDelete }) {
  return (
    <div className="flex gap-1">
      <button onClick={() => onToggleHidden(ct)} className="p-1 text-muted-foreground hover:text-foreground"
        aria-label={ct.is_active ? 'Hide' : 'Unhide'} title={ct.is_active ? 'Hide from the matrix (keeps records)' : 'Show on the matrix again'}>
        {ct.is_active ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
      </button>
      <button onClick={() => onEdit(ct)} className="p-1 text-muted-foreground hover:text-foreground" aria-label="Edit"><Edit className="w-3.5 h-3.5" /></button>
      <button onClick={() => onDelete(ct.id)} className="p-1 text-muted-foreground hover:text-destructive" aria-label="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
    </div>
  )
}

function expiresText(ct) {
  return ct.has_expiration ? `Yes (${ct.renewal_period_months || '?'}mo)` : 'No'
}

/** The Cert Types tab: one card per certification type. */
export function CertTypesGrid({ certTypes, canManage, onToggleHidden, onEdit, onDelete }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {certTypes.map(ct => (
        <div key={ct.id} className={`bg-card border border-border rounded-xl p-4 ${ct.is_active ? '' : 'opacity-60'}`}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">{ct.name}</h3>
              {!ct.is_active && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-500/15 text-zinc-400">Hidden</span>
              )}
            </div>
            {canManage && <TypeActions ct={ct} onToggleHidden={onToggleHidden} onEdit={onEdit} onDelete={onDelete} />}
          </div>
          <div className="mt-2 space-y-1 text-xs text-muted-foreground">
            <p>Category: <span className="text-foreground">{ct.category}</span></p>
            <p>Expires: <span className="text-foreground">{expiresText(ct)}</span></p>
            {ct.description && <p className="mt-1">{ct.description}</p>}
          </div>
        </div>
      ))}
      {certTypes.length === 0 && (
        <div className="col-span-full text-center py-12 text-muted-foreground">No certification types configured yet</div>
      )}
    </div>
  )
}
