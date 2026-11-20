import { normalizeModel } from '@/lib/utils'

const BASE = 'px-3 py-1.5 rounded-full border text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring'
const ON = 'bg-accent text-primary border-primary'
const OFF = 'bg-secondary text-muted-foreground border-border hover:bg-accent'

export function Toggle({ pressed, onClick, dashed = false, children }) {
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

// How two or more selected models count toward a requirement's target.
function ModeChoice({ mode, onSelect }) {
  const each = mode === 'each' || mode === 'each_all_active'
  return (
    <div className="space-y-2">
      <fieldset className="flex flex-wrap items-center gap-2 min-w-0 border-0 p-0 m-0">
        <legend className="float-left mr-1 text-xs text-muted-foreground">Count time</legend>
        <Toggle pressed={mode === 'combined'} onClick={() => onSelect('combined')}>Combined</Toggle>
        <Toggle pressed={each} onClick={() => onSelect('each')}>Each separately</Toggle>
      </fieldset>
      {each && (
        <fieldset className="flex flex-wrap items-center gap-2 min-w-0 border-0 p-0 m-0">
          <legend className="float-left mr-1 text-xs text-muted-foreground">On</legend>
          <Toggle pressed={mode === 'each'} onClick={() => onSelect('each')}>Selected models</Toggle>
          <Toggle pressed={mode === 'each_all_active'} onClick={() => onSelect('each_all_active')}>All active models</Toggle>
        </fieldset>
      )}
    </div>
  )
}

/**
 * Choose which fleet models a rule applies to. `value` is a list of model
 * names; an empty list means All aircraft. `models` is null until the fleet
 * list has loaded (or when it failed); then the saved names show as plain
 * chips, because nothing can be compared with the fleet yet. `labelledBy` is
 * the id of the element that names the group.
 *
 * Requirements also pass `mode` ('all', 'combined', 'each' or
 * 'each_all_active') and `onModeChange`. With two or more models selected the
 * picker then offers Combined or Each separately, and under Each separately,
 * All active models, which follows the fleet: every active model shows
 * pressed, and changing the selection turns it back into a list.
 */
export default function FleetModelPicker({ models, value, onChange, loadError = false, labelledBy, mode, onModeChange }) {
  const loaded = Array.isArray(models)
  const list = loaded ? models : []
  const allActive = mode === 'each_all_active'
  const active = list.filter(m => m.aircraft > 0).map(m => m.name)
  const current = allActive ? active : value
  const selected = new Set(current.map(normalizeModel))
  const fleet = new Set(list.map(m => normalizeModel(m.name)))
  const shown = list.filter(m => m.aircraft > 0 || selected.has(normalizeModel(m.name)))
  const unknown = current.filter(v => !fleet.has(normalizeModel(v)))
  const showModes = Boolean(onModeChange) && (current.length >= 2 || allActive)

  // Leaving All active models keeps its models as an ordinary list.
  const leaveAllActive = () => {
    if (allActive) onModeChange('each')
  }
  const change = (next) => {
    leaveAllActive()
    onChange(next)
  }
  const toggle = (name) => {
    const key = normalizeModel(name)
    if (selected.has(key)) change(current.filter(v => normalizeModel(v) !== key))
    else change([...current, name])
  }
  const selectMode = (next) => {
    onModeChange(next)
    if (allActive && next !== mode) onChange(current)
  }

  return (
    <div className="space-y-2">
      <fieldset aria-labelledby={labelledBy} className="flex flex-wrap gap-2 min-w-0 border-0 p-0 m-0">
        <Toggle pressed={!allActive && value.length === 0} onClick={() => change([])}>All aircraft</Toggle>
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
      </fieldset>
      {showModes && <ModeChoice mode={mode} onSelect={selectMode} />}
      {loadError && <p className="text-xs text-muted-foreground">Fleet models could not be loaded</p>}
    </div>
  )
}
