function uniqueIds(list) {
  return Array.isArray(list) ? [...new Set(list)] : []
}

/** The tile ids in display order and those switched off, for the given tiles.
 *  Unknown ids are dropped; tiles the layout does not name go last, switched on. */
export function resolveLayout(tiles, layout) {
  const ids = tiles.map(t => t.id)
  const known = new Set(ids)
  const saved = uniqueIds(layout?.order).filter(id => known.has(id))
  const placed = new Set(saved)
  return {
    order: [...saved, ...ids.filter(id => !placed.has(id))],
    hidden: uniqueIds(layout?.hidden).filter(id => known.has(id)),
  }
}
