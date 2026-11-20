/**
 * Field groups of the requirement builder. Each takes the form state and
 * `update`, which merges a patch (or the result of a function of the current
 * form) into it.
 */
import FleetModelPicker, { Toggle } from '@/components/FleetModelPicker'
import { sortPilotsActiveFirst } from '@/lib/formatters'
import { withModels } from './formState'

const INPUT = 'w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50'
const LABEL = 'block text-sm font-medium text-foreground mb-1'
const LEGEND = 'text-sm font-medium text-foreground mb-2'
const HINT = 'text-xs text-muted-foreground mt-1'
const FIELDSET = 'min-w-0 border-0 p-0 m-0'
const RADIO = 'w-4 h-4 border-border text-primary focus:ring-ring'

const PERIOD_OPTIONS = [
  ['calendar_month', 'Calendar month'],
  ['calendar_quarter', 'Calendar quarter'],
  ['calendar_year', 'Calendar year'],
  ['fiscal_quarter', 'Fiscal quarter'],
  ['fiscal_year', 'Fiscal year'],
  ['monthly_window', 'Monthly window (day X to day Y)'],
  ['span', 'Span from a start date'],
  ['custom', 'Custom date range'],
  ['every_n_months', 'Every N months from a start date'],
]
const NAMED_PERIODS = new Set(['calendar_month', 'calendar_quarter', 'calendar_year', 'fiscal_quarter', 'fiscal_year'])
const NIGHT_REASON = 'Set the unit default location in Settings, General, to use night.'

function NumberField({ id, label, value, onChange, min, max }) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>{label}</label>
      <input id={id} type="number" inputMode="numeric" min={min} max={max} value={value}
        onChange={e => onChange(e.target.value)} className={INPUT} />
    </div>
  )
}

function Radio({ name, checked, onChange, disabled = false, describedBy, children }) {
  return (
    <label className={`flex items-center gap-2 text-sm text-foreground select-none ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <input type="radio" name={name} checked={checked} onChange={onChange} disabled={disabled}
        aria-describedby={describedBy} className={RADIO} />
      {children}
    </label>
  )
}

export function BasicsFields({ form, update }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div>
        <label htmlFor="req-name" className={LABEL}>Name</label>
        <input id="req-name" type="text" required maxLength={200} value={form.name}
          onChange={e => update({ name: e.target.value })} placeholder="e.g. Quarterly model time" className={INPUT} />
      </div>
      <div>
        <label htmlFor="req-description" className={LABEL}>Description (optional)</label>
        <input id="req-description" type="text" maxLength={1000} value={form.description}
          onChange={e => update({ description: e.target.value })} className={INPUT} />
      </div>
    </div>
  )
}

function PeriodDetailFields({ form, update }) {
  if (form.period_type === 'monthly_window') {
    return (
      <>
        <NumberField id="req-window-start" label="Start day" min={1} max={31} value={form.window_start_day}
          onChange={v => update({ window_start_day: v })} />
        <NumberField id="req-window-end" label="End day" min={1} max={31} value={form.window_end_day}
          onChange={v => update({ window_end_day: v })} />
      </>
    )
  }
  if (form.period_type === 'span') {
    return (
      <>
        <NumberField id="req-span-length" label="Length" min={1} max={365} value={form.span_length}
          onChange={v => update({ span_length: v })} />
        <div>
          <label htmlFor="req-span-unit" className={LABEL}>Unit</label>
          <select id="req-span-unit" value={form.span_unit} onChange={e => update({ span_unit: e.target.value })} className={INPUT}>
            <option value="days">Days</option>
            <option value="weeks">Weeks</option>
            <option value="months">Months</option>
          </select>
        </div>
      </>
    )
  }
  if (form.period_type === 'every_n_months') {
    return (
      <NumberField id="req-every" label="Every (months)" min={1} max={24} value={form.every_months}
        onChange={v => update({ every_months: v })} />
    )
  }
  return null
}

function DateFields({ form, update }) {
  const custom = form.period_type === 'custom'
  const showEnd = custom || form.recurring
  const startHint = NAMED_PERIODS.has(form.period_type)
    ? 'Any day in the first period.'
    : 'The first day of the first period.'
  return (
    <>
      <div>
        <label htmlFor="req-start" className={LABEL}>Starts</label>
        <input id="req-start" type="date" value={form.start_date} aria-describedby="req-start-hint"
          onChange={e => update({ start_date: e.target.value })} className={INPUT} />
        <p id="req-start-hint" className={HINT}>{startHint}</p>
      </div>
      {showEnd && (
        <div>
          <label htmlFor="req-end" className={LABEL}>{custom ? 'Ends' : 'Ends (optional)'}</label>
          <input id="req-end" type="date" value={form.end_date} min={form.start_date || undefined}
            onChange={e => update({ end_date: e.target.value })} className={INPUT} />
        </div>
      )}
    </>
  )
}

export function PeriodFields({ form, update }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="req-period" className={LABEL}>Period</label>
          <select id="req-period" value={form.period_type} onChange={e => update({ period_type: e.target.value })} className={INPUT}>
            {PERIOD_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        {form.period_type !== 'custom' && (
          <fieldset className={FIELDSET}>
            <legend className={LEGEND}>Repeats</legend>
            <div className="flex gap-4 py-2">
              <Radio name="req-repeats" checked={!form.recurring} onChange={() => update({ recurring: false })}>One time</Radio>
              <Radio name="req-repeats" checked={form.recurring} onChange={() => update({ recurring: true })}>Recurring</Radio>
            </div>
          </fieldset>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <PeriodDetailFields form={form} update={update} />
        <DateFields form={form} update={update} />
      </div>
    </div>
  )
}

export function TargetFields({ form, update }) {
  return (
    <fieldset className={FIELDSET} aria-describedby="req-target-hint">
      <legend className={LEGEND}>Target</legend>
      <div className="grid grid-cols-3 gap-3">
        <NumberField id="req-hours" label="Hours" min={0} value={form.target_hours} onChange={v => update({ target_hours: v })} />
        <NumberField id="req-minutes" label="Minutes" min={0} max={59} value={form.target_mins} onChange={v => update({ target_mins: v })} />
        <NumberField id="req-flights" label="Flights" min={0} value={form.target_flights} onChange={v => update({ target_flights: v })} />
      </div>
      <p id="req-target-hint" className={HINT}>Set a time, a number of flights, or both.</p>
    </fieldset>
  )
}

export function AircraftField({ form, update, models, modelsError }) {
  return (
    <div>
      <span id="req-models-label" className={`block ${LEGEND}`}>Aircraft</span>
      <FleetModelPicker
        models={models}
        loadError={modelsError}
        labelledBy="req-models-label"
        value={form.models}
        onChange={next => update(f => withModels(f, next))}
        mode={form.model_mode}
        onModeChange={model_mode => update({ model_mode })}
      />
    </div>
  )
}

export function TimeFields({ form, update, locationSet }) {
  return (
    <fieldset className={FIELDSET}>
      <legend className={LEGEND}>Time of day</legend>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <Radio name="req-time" checked={form.time_mode === 'any'} onChange={() => update({ time_mode: 'any' })}>Any time</Radio>
        <Radio name="req-time" checked={form.time_mode === 'clock'} onChange={() => update({ time_mode: 'clock' })}>Clock window</Radio>
        <Radio name="req-time" checked={form.time_mode === 'night'} onChange={() => update({ time_mode: 'night' })}
          disabled={!locationSet} describedBy={locationSet ? 'req-night-hint' : 'req-night-reason'}>
          Night (civil twilight)
        </Radio>
      </div>
      {locationSet
        ? <p id="req-night-hint" className={HINT}>Night runs from the end of evening civil twilight to the start of morning civil twilight at the unit location.</p>
        : <p id="req-night-reason" className={HINT}>{NIGHT_REASON}</p>}
      {form.time_mode === 'clock' && (
        <div className="grid grid-cols-2 gap-3 mt-3">
          <div>
            <label htmlFor="req-time-start" className={LABEL}>From</label>
            <input id="req-time-start" type="time" value={form.window_start_time}
              onChange={e => update({ window_start_time: e.target.value })} className={INPUT} />
          </div>
          <div>
            <label htmlFor="req-time-end" className={LABEL}>To</label>
            <input id="req-time-end" type="time" value={form.window_end_time}
              onChange={e => update({ window_end_time: e.target.value })} className={INPUT} />
          </div>
          <p className={`${HINT} col-span-2 mt-0`}>In the unit time zone. An end earlier than the start crosses midnight.</p>
        </div>
      )}
    </fieldset>
  )
}

// Purposes match without regard to case or surrounding spaces, as the API compares them.
function purposeKey(name) {
  return name.trim().toLowerCase()
}

function togglePurpose(list, name) {
  const key = purposeKey(name)
  const kept = list.filter(p => purposeKey(p) !== key)
  return kept.length === list.length ? [...list, name] : kept
}

export function PurposeField({ form, update, purposes }) {
  const selected = new Set(form.purposes.map(purposeKey))
  const listed = purposes.filter(p => p.is_active !== false || selected.has(purposeKey(p.name))).map(p => p.name)
  const listedKeys = new Set(listed.map(purposeKey))
  const extra = form.purposes.filter(name => !listedKeys.has(purposeKey(name)))
  return (
    <div>
      <span id="req-purposes-label" className={`block ${LEGEND}`}>Flight purposes</span>
      <fieldset aria-labelledby="req-purposes-label" aria-describedby="req-purposes-hint" className={`flex flex-wrap gap-2 ${FIELDSET}`}>
        <Toggle pressed={form.purposes.length === 0} onClick={() => update({ purposes: [] })}>All purposes</Toggle>
        {[...listed, ...extra].map(name => (
          <Toggle key={name} pressed={selected.has(purposeKey(name))}
            onClick={() => update(f => ({ purposes: togglePurpose(f.purposes, name) }))}>
            {name}
          </Toggle>
        ))}
      </fieldset>
      <p id="req-purposes-hint" className={HINT}>Flights with no purpose count only under All purposes.</p>
    </div>
  )
}

function PilotChoices({ form, update, pilots }) {
  const toggle = (id) => update(f => ({
    pilot_ids: f.pilot_ids.includes(id) ? f.pilot_ids.filter(p => p !== id) : [...f.pilot_ids, id],
  }))
  return (
    <fieldset className={`${FIELDSET} mt-3`}>
      <legend className="sr-only">Pilots</legend>
      <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-secondary p-2 grid gap-1 sm:grid-cols-2">
        {pilots.length === 0 && <p className="text-sm text-muted-foreground px-2 py-1">No pilots found.</p>}
        {sortPilotsActiveFirst(pilots).map(p => (
          <label key={p.id} className="flex items-center gap-2 px-2 py-1 rounded text-sm text-foreground cursor-pointer hover:bg-accent">
            <input type="checkbox" checked={form.pilot_ids.includes(p.id)} onChange={() => toggle(p.id)}
              className="w-4 h-4 rounded border-border text-primary focus:ring-ring" />
            {p.status === 'active' ? p.full_name : `${p.full_name} (inactive)`}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function PilotField({ form, update, pilots }) {
  return (
    <fieldset className={FIELDSET}>
      <legend className={LEGEND}>Applies to</legend>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <Radio name="req-pilots" checked={form.all_pilots} onChange={() => update({ all_pilots: true })}>All active pilots</Radio>
        <Radio name="req-pilots" checked={!form.all_pilots} onChange={() => update({ all_pilots: false })}>Selected pilots</Radio>
      </div>
      {!form.all_pilots && <PilotChoices form={form} update={update} pilots={pilots} />}
    </fieldset>
  )
}

export function ReminderFields({ form, update }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 sm:items-end">
      <div>
        <label htmlFor="req-reminder" className={LABEL}>Reminder (days before the period ends)</label>
        <input id="req-reminder" type="number" inputMode="numeric" min={0} max={60} value={form.reminder_days}
          onChange={e => update({ reminder_days: e.target.value })} className={INPUT} />
      </div>
      <label className="flex items-center gap-2 py-2 text-sm text-foreground cursor-pointer select-none">
        <input type="checkbox" checked={form.is_active} onChange={() => update(f => ({ is_active: !f.is_active }))}
          className="w-4 h-4 rounded border-border text-primary focus:ring-ring" />
        <span>Active</span>
      </label>
    </div>
  )
}
