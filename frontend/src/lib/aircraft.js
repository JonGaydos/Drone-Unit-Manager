/** A heading in degrees, or null when the feed value is not a finite number. */
export function numericTrack(track) {
  const n = typeof track === 'number' ? track : Number.NaN
  return Number.isFinite(n) ? n : null
}

/** SVG markup for an aircraft marker. Only numbers reach the style attribute. */
export function aircraftIconHtml(track, color) {
  const rotation = numericTrack(track) ?? 0
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style="transform:rotate(${rotation}deg)">
      <path d="M12 2L8 9h-5l1 2 5 1 1 8 2 2 2-2 1-8 5-1 1-2h-5z" fill="${color}" stroke="#000" stroke-width="0.5"/>
    </svg>`
}
