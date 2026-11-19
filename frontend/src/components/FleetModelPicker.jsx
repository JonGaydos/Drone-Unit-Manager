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

function unknownLabel(name, loaded) {
  return loaded ? `${name} (Not in fleet)` : name
}

/**
 * Choose which fleet models a rule applies to. `value` is a list of model
 * names; an empty list means All aircraft. `models` is null until the fleet
 * list has loaded (or when it failed); then the saved names show as plain
 * chips, because nothing can be compared with the fleet yet. `labelledBy` is
 * the id of the element that names the group.
 */
export default function FleetModelPicker({ models, value, onChange, loadError = false, labelledBy }) {
  const loaded = Array.isArray(models)
  const list = loaded ? models : []
  const selected = new Set(value.map(normalizeModel))
  const fleet = new Set(list.map(m => normalizeModel(m.name)))
  const shown = list.filter(m => m.aircraft > 0 || selected.has(normalizeModel(m.name)))
  const unknown = value.filter(v => !fleet.has(normalizeModel(v)))

  const toggle = (name) => {
    const key = normalizeModel(name)
    if (selected.has(key)) onChange(value.filter(v => normalizeModel(v) !== key))
    else onChange([...value, name])
  }

  return (
    <div className="space-y-2">
      <div role="group" aria-labelledby={labelledBy} className="flex flex-wrap gap-2">
        <Toggle pressed={value.length === 0} onClick={() => onChange([])}>All aircraft</Toggle>
        {shown.map(m => (
          <Toggle key={m.name} pressed={selected.has(normalizeModel(m.name))} onClick={() => toggle(m.name)}>
            {modelLabel(m)}
          </Toggle>
        ))}
        {unknown.map(name => (
          <Toggle key={name} pressed dashed onClick={() => toggle(name)}>
            {unknownLabel(name, loaded)}
          </Toggle>
        ))}
      </div>
      {loadError && <p className="text-xs text-muted-foreground">Fleet models could not be loaded</p>}
    </div>
  )
}
