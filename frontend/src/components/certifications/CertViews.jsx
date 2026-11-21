import { useMemo } from 'react'
import { filterCertTypes, filterMatrix } from './certStatus'
import { CertFilters } from './CertFilters'
import { ViewSwitch } from './ViewSwitch'
import { BulkRenewBar } from './BulkRenew'
import { MatrixView } from './MatrixView'
import { PilotCardsView } from './PilotCardsView'
import { UrgencyView } from './UrgencyView'

/** The view switch, the shared filters, and the chosen view of pilot certifications. */
export function CertViews({ matrix, certTypes, filters, onFiltersChange, view, onViewChange, bulk, ctx }) {
  const columns = useMemo(() => filterCertTypes(certTypes, filters.category), [certTypes, filters.category])
  const rows = useMemo(() => filterMatrix(matrix, filters), [matrix, filters])
  const emptyMessage = matrix.length === 0 ? 'No pilots or certifications configured yet' : 'No pilots match the current filters'
  const viewProps = { rows, certTypes: columns, emptyMessage, ctx }
  return (
    <>
      <ViewSwitch view={view} onChange={onViewChange} />
      <CertFilters filters={filters} onChange={onFiltersChange}
        shownPilots={rows.length} totalPilots={matrix.length} columns={columns.length} />
      {view === 'matrix' && ctx.canManage && <BulkRenewBar bulk={bulk} />}
      {view === 'matrix' && <MatrixView {...viewProps} />}
      {view === 'pilot' && <PilotCardsView {...viewProps} />}
      {view === 'urgency' && <UrgencyView {...viewProps} status={filters.status} />}
    </>
  )
}
