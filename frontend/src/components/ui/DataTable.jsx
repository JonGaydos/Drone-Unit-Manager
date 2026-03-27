/**
 * Sortable, paginated data table component with customizable column rendering.
 */
import { cn } from '@/lib/utils'
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * Renders the appropriate sort direction indicator for a table column header.
 * @param {Object} props
 * @param {string} props.columnKey - The column this icon belongs to.
 * @param {string} props.sortKey - The currently sorted column key.
 * @param {'asc'|'desc'} props.sortDir - Current sort direction.
 */
function SortIcon({ columnKey, sortKey, sortDir }) {
  if (sortKey !== columnKey) {
    return <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground/50" />
  }
  return sortDir === 'asc' ? (
    <ChevronUp className="h-3.5 w-3.5 text-foreground" />
  ) : (
    <ChevronDown className="h-3.5 w-3.5 text-foreground" />
  )
}

/**
 * Generic data table with sortable column headers and pagination controls.
 * @param {Object} props
 * @param {Array<{key: string, label: string, sortable?: boolean, render?: Function}>} props.columns - Column definitions.
 * @param {Array<Object>} props.data - Row data to display.
 * @param {Function} [props.onSort] - Callback when a sortable column header is clicked.
 * @param {string} [props.sortKey] - Currently sorted column key.
 * @param {'asc'|'desc'} [props.sortDir] - Current sort direction.
 * @param {number} [props.page] - Current page number (1-based).
 * @param {number} [props.totalPages] - Total number of pages.
 * @param {Function} [props.onPageChange] - Callback when page navigation buttons are clicked.
 * @param {string} [props.className] - Additional CSS classes for the table container.
 */
function DataTable({
  columns = [],
  data = [],
  onSort,
  sortKey,
  sortDir,
  page,
  totalPages,
  onPageChange,
  className,
}) {
  return (
    <div className={cn('rounded-xl border border-border bg-card overflow-hidden', className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/50">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    'px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground',
                    col.sortable && 'cursor-pointer select-none hover:text-foreground transition-colors'
                  )}
                  onClick={() => col.sortable && onSort?.(col.key)}
                >
                  <span className="inline-flex items-center gap-1.5">
                    {col.label}
                    {col.sortable && (
                      <SortIcon columnKey={col.key} sortKey={sortKey} sortDir={sortDir} />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-muted-foreground"
                >
                  No data available
                </td>
              </tr>
            ) : (
              data.map((row, idx) => (
                <tr
                  key={row.id ?? idx}
                  className="hover:bg-muted/50 transition-colors"
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3 text-foreground">
                      {col.render ? col.render(row[col.key], row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange?.(page - 1)}
              disabled={page <= 1}
              aria-label="Previous page"
              className={cn(
                'inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'disabled:pointer-events-none disabled:opacity-50',
                'cursor-pointer'
              )}
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => onPageChange?.(page + 1)}
              disabled={page >= totalPages}
              aria-label="Next page"
              className={cn(
                'inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'disabled:pointer-events-none disabled:opacity-50',
                'cursor-pointer'
              )}
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export { DataTable }
