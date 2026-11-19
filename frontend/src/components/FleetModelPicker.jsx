import { normalizeModel } from '@/lib/utils'

const BASE = 'px-3 py-1.5 rounded-full border text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring'
const ON = 'bg-accent text-primary border-primary'
const OFF = 'bg-secondary text-muted-foreground border-border hover:bg-accent'

function Toggle({ pressed, onClick, dashed = false, children }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`${BASE} ${pressed ? ON : OFF} ${dashed ? 'border-dashed' : ''}`}
    >
      {children}
    </button>
  )
}

function modelLabel(model) {
  return model.aircraft > 0 ? `${model.name} (${model.aircraft})` : `${model.name} (no active aircraft)`
}

/**
 * Choose which fleet models a rule applies to. `value` is a list of model
 * names; an empty list means All aircraft.
 */
export default function FleetModelPicker({ models, value, onChange }) {
  const selected = new Set(value.map(normalizeModel))
  const fleet = new Set(models.map(m => normalizeModel(m.name)))
  const shown = models.filter(m => m.aircraft > 0 || selected.has(normalizeModel(m.name)))
  const unknown = value.filter(v => !fleet.has(normalizeModel(v)))

  const toggle = (name) => {
    const key = normalizeModel(name)
    if (selected.has(key)) onChange(value.filter(v => normalizeModel(v) !== key))
    else onChange([...value, name])
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Toggle pressed={value.length === 0} onClick={() => onChange([])}>All aircraft</Toggle>
      {shown.map(m => (
        <Toggle key={m.name} pressed={selected.has(normalizeModel(m.name))} onClick={() => toggle(m.name)}>
          {modelLabel(m)}
        </Toggle>
      ))}
      {unknown.map(name => (
        <Toggle key={name} pressed dashed onClick={() => toggle(name)}>
          {name} (Not in fleet)
        </Toggle>
      ))}
    </div>
  )
}
