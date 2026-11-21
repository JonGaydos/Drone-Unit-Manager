import { ListOrdered, Table2, Users } from 'lucide-react'

const OPTIONS = [
  { value: 'matrix', label: 'Matrix', Icon: Table2 },
  { value: 'pilot', label: 'By pilot', Icon: Users },
  { value: 'urgency', label: 'By urgency', Icon: ListOrdered },
]

const ON = 'bg-card text-foreground shadow-sm'
const OFF = 'text-muted-foreground hover:text-foreground'

/** Segmented control for the Certifications views. */
export function ViewSwitch({ view, onChange }) {
  return (
    <fieldset className="inline-flex rounded-lg border border-border bg-secondary p-0.5">
      <legend className="sr-only">View</legend>
      {OPTIONS.map(({ value, label, Icon }) => (
        <button key={value} type="button" aria-pressed={view === value} onClick={() => onChange(value)}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${view === value ? ON : OFF}`}>
          <Icon className="h-4 w-4" aria-hidden="true" />
          {label}
        </button>
      ))}
    </fieldset>
  )
}
