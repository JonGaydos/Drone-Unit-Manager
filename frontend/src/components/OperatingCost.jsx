/** A flight's operating cost: the typed value, else the estimate from the
 *  aircraft's hourly rate, marked as estimated. A dash when there is neither. */
export function OperatingCost({ flight }) {
  if (flight.operating_cost != null) return `$${Number(flight.operating_cost).toFixed(2)}`
  if (flight.operating_cost_estimate == null) return '—'
  return (
    <>
      <span>${Number(flight.operating_cost_estimate).toFixed(2)}</span>{' '}
      <span className="text-xs text-muted-foreground" title="Flight hours x the aircraft's hourly operating cost">(estimated)</span>
    </>
  )
}
