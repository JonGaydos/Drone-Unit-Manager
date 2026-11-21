import { Filter, Search } from 'lucide-react'
import { CELL_COLORS, CERT_CATEGORIES, statusText } from './certStatus'

const SELECT = 'px-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm'

/** Status, category, pilot search and hide-empty filters, shared by every view. */
export function CertFilters({ filters, onChange, shownPilots, totalPilots, columns }) {
  const set = (key) => (value) => onChange({ ...filters, [key]: value })
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex flex-col sm:flex-row flex-wrap items-start sm:items-center gap-2 sm:gap-3">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-muted-foreground">Filters:</span>
        </div>

        <div className="relative">
          <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search pilots..."
            aria-label="Search pilots"
            value={filters.search}
            onChange={e => set('search')(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-secondary border border-border rounded-lg text-foreground text-sm w-44 focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <select aria-label="Status" value={filters.status} onChange={e => set('status')(e.target.value)} className={SELECT}>
          <option value="all">All Statuses</option>
          {Object.keys(CELL_COLORS).map(s => <option key={s} value={s}>{statusText(s)}</option>)}
        </select>

        <select aria-label="Category" value={filters.category} onChange={e => set('category')(e.target.value)} className={SELECT}>
          <option value="all">All Categories</option>
          {CERT_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>

        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={filters.hideEmpty}
            onChange={e => set('hideEmpty')(e.target.checked)}
            className="rounded border-border"
          />{' '}
          Hide empty
        </label>

        <span className="text-xs text-muted-foreground ml-auto">
          {shownPilots} of {totalPilots} pilots | {columns} cert columns
        </span>
      </div>
    </div>
  )
}
