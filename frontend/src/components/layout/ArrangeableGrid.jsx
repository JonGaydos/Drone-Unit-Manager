/**
 * A tile grid the signed-in user can arrange: drag tiles into a new order and
 * switch tiles off, then save the arrangement to their account. Admins can
 * also save it as the unit default that users without their own layout get.
 *
 * Tiles: [{ id, label, span, render, visible }]. `span` holds the tile's grid
 * width classes; `visible: false` (no permission) keeps a tile off the page
 * whatever the layout says.
 */
import { useState } from 'react'
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, LayoutGrid } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { resolveLayout } from './resolveLayout'

const SWITCH_TONES = {
  on: { track: 'bg-primary', thumb: 'translate-x-4 bg-primary-foreground' },
  off: { track: 'bg-secondary border border-border', thumb: 'translate-x-0.5 bg-muted-foreground' },
}

function TileSwitch({ label, on, onToggle }) {
  const tone = SWITCH_TONES[on ? 'on' : 'off']
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={`Show ${label}`} onClick={onToggle}
      className="inline-flex h-8 w-11 shrink-0 items-center justify-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {/* The button is the touch target; the track inside keeps the switch shape. */}
      <span aria-hidden="true" className={`inline-flex h-5 w-9 items-center rounded-full transition-colors ${tone.track}`}>
        <span className={`h-4 w-4 rounded-full shadow-sm transition-transform ${tone.thumb}`} />
      </span>
    </button>
  )
}

function editCellClass(isDragging) {
  return isDragging ? 'relative z-10 shadow-lg shadow-black/30 rounded-xl' : ''
}

function SortableTile({ tile, editing, hidden, onToggle }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: tile.id, disabled: !editing })
  const style = { transform: CSS.Translate.toString(transform), transition }
  return (
    <div ref={setNodeRef} style={style} data-tile-id={tile.id}
      className={`${tile.span} flex flex-col min-w-0 ${editCellClass(isDragging)}`}>
      {editing && (
        <div className="flex items-center gap-2 mb-2 rounded-lg border border-dashed border-border bg-muted/30 px-1.5 py-1">
          <button type="button" ref={setActivatorNodeRef} aria-label={`Move ${tile.label}`} {...attributes} {...listeners}
            className="touch-none inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground cursor-grab active:cursor-grabbing focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <GripVertical className="w-4 h-4" aria-hidden="true" />
          </button>
          <span className="flex-1 min-w-0 truncate text-xs font-medium text-foreground">{tile.label}</span>
          <TileSwitch label={tile.label} on={!hidden} onToggle={() => onToggle(tile.id)} />
        </div>
      )}
      <div inert={editing} className={`flex-1 flex flex-col min-w-0 *:flex-1 transition-opacity ${hidden ? 'opacity-35' : ''}`}>
        {tile.render()}
      </div>
    </div>
  )
}

function EditBar({ saving, canSetDefault, onSave, onSaveDefault, onReset, onCancel }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-card px-4 py-3">
      <p className="flex-1 min-w-[16rem] text-xs text-muted-foreground">
        Drag a tile by its handle, or focus the handle, press Space and use the arrow keys. Switch a tile off to hide it.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onReset} disabled={saving}>Reset to default</Button>
        {canSetDefault && (
          <Button variant="outline" size="sm" onClick={onSaveDefault} disabled={saving}>Save as unit default</Button>
        )}
        <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button size="sm" onClick={onSave} disabled={saving}>Save</Button>
      </div>
    </div>
  )
}

/** Screen reader messages that name the tile and its new place. */
function announcementsFor(order, labelOf) {
  const place = (id) => `position ${order.indexOf(id) + 1} of ${order.length}`
  return {
    onDragStart: ({ active }) => `Picked up ${labelOf(active.id)}.`,
    onDragOver: ({ active, over }) => (over ? `${labelOf(active.id)} moved to ${place(over.id)}.` : `${labelOf(active.id)} is not over a position.`),
    onDragEnd: ({ active, over }) => (over ? `${labelOf(active.id)} dropped at ${place(over.id)}.` : `${labelOf(active.id)} dropped.`),
    onDragCancel: ({ active }) => `Move of ${labelOf(active.id)} cancelled.`,
  }
}

const INSTRUCTIONS = {
  draggable: 'Press Space to pick up the tile, use the arrow keys to move it, then Space to drop it or Escape to cancel.',
}

function layoutOf(draft) {
  return { order: draft.order, hidden: draft.hidden }
}

export default function ArrangeableGrid({
  tiles, layout, defaultLayout, onSave, onSaveDefault, canSetDefault = false, className = '',
}) {
  const available = tiles.filter(t => t.visible !== false)
  const byId = new Map(available.map(t => [t.id, t]))
  // While editing: the working arrangement; `reset` means save "use the default".
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const editing = draft !== null
  const current = draft ?? resolveLayout(available, layout ?? defaultLayout)
  const hidden = new Set(current.hidden)
  const shownIds = editing ? current.order : current.order.filter(id => !hidden.has(id))
  const labelOf = (id) => byId.get(id)?.label ?? 'Tile'

  const change = (update) => setDraft(d => ({ ...d, ...update(d), reset: false }))
  const toggle = (id) => change(d => ({
    hidden: d.hidden.includes(id) ? d.hidden.filter(x => x !== id) : [...d.hidden, id],
  }))
  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return
    change(d => ({ order: arrayMove(d.order, d.order.indexOf(active.id), d.order.indexOf(over.id)) }))
  }
  // The page reports a failed save; edit mode stays open so nothing is lost.
  const finish = async (action) => {
    setSaving(true)
    try {
      await action()
      setDraft(null)
    } catch { /* reported by the page */ } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      {editing ? (
        <EditBar saving={saving} canSetDefault={canSetDefault}
          onSave={() => finish(() => onSave(draft.reset ? null : layoutOf(draft)))}
          onSaveDefault={() => finish(() => onSaveDefault(layoutOf(draft)))}
          onReset={() => setDraft({ ...resolveLayout(available, defaultLayout), reset: true })}
          onCancel={() => setDraft(null)} />
      ) : (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => setDraft({ ...current, reset: false })}>
            <LayoutGrid className="w-3.5 h-3.5" aria-hidden="true" /> Edit layout
          </Button>
        </div>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}
        accessibility={{ announcements: announcementsFor(current.order, labelOf), screenReaderInstructions: INSTRUCTIONS }}>
        <SortableContext items={shownIds} strategy={rectSortingStrategy}>
          <div className={`grid gap-4 auto-rows-min ${className}`}>
            {shownIds.map(id => (
              <SortableTile key={id} tile={byId.get(id)} editing={editing} hidden={hidden.has(id)} onToggle={toggle} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  )
}
