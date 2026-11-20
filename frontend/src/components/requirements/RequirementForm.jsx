import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { describeRequirement } from './RequirementSummary'
import { formProblem, startsInPast, toBody } from './formState'
import {
  ActiveField, AircraftField, BasicsFields, PeriodFields, PilotField, PurposeField, ReminderFields, TargetFields, TimeFields,
} from './RequirementFields'

function Section({ children }) {
  return <div data-form-section className="pt-5 first:pt-0 border-t border-border first:border-t-0">{children}</div>
}

/**
 * The requirement builder. `initial` is form state (see formState.js);
 * `onSubmit(body)` saves it and rejects with an Error whose message the form
 * shows. `models` is null until the fleet list loads; `locationSet` says
 * whether the unit default location is set, which Night needs. `isNew` is
 * false when editing a saved requirement, whose closed periods never reopen,
 * so the past-start warning shows only for a new one.
 */
export default function RequirementForm({
  title, initial, isNew = true, models, modelsError = false, purposes, pilots, locationSet, fiscalStartMonth, onSubmit,
  onCancel,
}) {
  const [form, setForm] = useState(initial)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const formRef = useRef(null)

  // The form opens above the list, so bring it into view from a row far down.
  useEffect(() => {
    formRef.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [])

  const update = (patch) => setForm(f => ({ ...f, ...(typeof patch === 'function' ? patch(f) : patch) }))

  const submit = async (e) => {
    e.preventDefault()
    const problem = formProblem(form)
    setError(problem)
    if (problem) return
    setSaving(true)
    try {
      await onSubmit(toBody(form))
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <form ref={formRef} onSubmit={submit} noValidate aria-labelledby="req-form-title"
      className="bg-card border border-border rounded-xl p-6 space-y-5">
      <h2 id="req-form-title" className="text-lg font-semibold text-foreground">{title}</h2>
      <Section>
        <div className="space-y-4">
          <BasicsFields form={form} update={update} />
          <ActiveField form={form} update={update} />
        </div>
      </Section>
      <Section>
        <PeriodFields form={form} update={update} />
        {isNew && startsInPast(form, fiscalStartMonth) && (
          <p className="mt-3 rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning">
            This requirement starts in the past. Periods that already ended will be counted, flagged and emailed.
          </p>
        )}
      </Section>
      <Section><TargetFields form={form} update={update} /></Section>
      <Section>
        <div className="space-y-5">
          <AircraftField form={form} update={update} models={models} modelsError={modelsError} />
          <TimeFields form={form} update={update} locationSet={locationSet} />
          <PurposeField form={form} update={update} purposes={purposes} />
        </div>
      </Section>
      <Section><PilotField form={form} update={update} pilots={pilots} /></Section>
      <Section><ReminderFields form={form} update={update} /></Section>
      <div className="rounded-lg bg-muted/30 border border-border px-4 py-3">
        <p className="text-xs font-medium text-muted-foreground mb-1">Summary</p>
        <p aria-live="polite" className="text-sm text-foreground">
          {describeRequirement(form, { pilots, fiscalStartMonth })}
        </p>
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving}
          className="flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
          {saving && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
          Save requirement
        </button>
        <button type="button" onClick={onCancel}
          className="px-4 py-2 bg-secondary text-secondary-foreground rounded-lg text-sm hover:opacity-90">
          Cancel
        </button>
      </div>
    </form>
  )
}
