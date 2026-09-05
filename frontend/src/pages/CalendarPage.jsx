import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'

const COLORS = {
  training_day: '#0ea5e9', mission: '#8b5cf6', maintenance_due: '#f59e0b',
  cert_expiration: '#ef4444', event: '#10b981', leave: '#6b7280', flights: '#3b82f6',
}
const LABELS = {
  training_day: 'Training', mission: 'Missions', maintenance_due: 'Maintenance due',
  cert_expiration: 'Cert expirations', event: 'Events', leave: 'Leave', flights: 'Flights',
}
const ALL_CATS = Object.keys(LABELS)
const blankForm = () => ({ title: '', category: 'event', start_date: '', end_date: '', notes: '' })

export default function CalendarPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const calRef = useRef(null)
  const rangeRef = useRef({ start: null, end: null })
  const [events, setEvents] = useState([])
  const [flightCounts, setFlightCounts] = useState({})
  const [enabled, setEnabled] = useState(() => Object.fromEntries(ALL_CATS.map(c => [c, true])))
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(blankForm())
  const [editId, setEditId] = useState(null)

  const fetchRange = useCallback(async (start, end) => {
    rangeRef.current = { start, end }
    try {
      const res = await api.get(`/calendar?start=${start}&end=${end}`)
      setEvents(res.events || [])
      setFlightCounts(res.flight_counts || {})
    } catch (err) { toast.error(err.message) }
  }, [toast])

  const handleDatesSet = (arg) => {
    fetchRange(arg.startStr.slice(0, 10), arg.endStr.slice(0, 10))
  }

  const fcEvents = []
  for (const e of events) {
    if (!enabled[e.category]) continue
    fcEvents.push({
      id: e.id, title: e.title, start: e.start, end: e.end || undefined, allDay: e.all_day,
      color: COLORS[e.category] || '#64748b',
      extendedProps: { category: e.category, link: e.link, editable: e.editable, raw: e },
    })
  }
  if (enabled.flights) {
    for (const [d, n] of Object.entries(flightCounts)) {
      fcEvents.push({ id: `flights-${d}`, title: `${n} flight${n === 1 ? '' : 's'}`, start: d, allDay: true,
        color: COLORS.flights, extendedProps: { category: 'flights', link: '/flights' } })
    }
  }

  const handleEventClick = (info) => {
    const xp = info.event.extendedProps
    if (xp.category === 'event' || xp.category === 'leave') {
      const raw = xp.raw
      setEditId(raw.event_id)
      setForm({
        title: raw.title, category: raw.category, start_date: raw.start || '',
        end_date: raw.end || '', notes: raw.notes || '',
      })
      setModalOpen(true)
    } else if (xp.link) {
      navigate(xp.link)
    }
  }

  const openCreate = () => { setEditId(null); setForm(blankForm()); setModalOpen(true) }

  const canEditCurrent = editId == null || (() => {
    const e = events.find(x => x.event_id === editId)
    return e ? e.editable : true
  })()

  const handleSave = async (e) => {
    e.preventDefault()
    const body = { title: form.title, category: form.category, start_date: form.start_date,
                   end_date: form.end_date || null, notes: form.notes || null }
    try {
      if (editId) await api.patch(`/calendar/events/${editId}`, body)
      else await api.post('/calendar/events', body)
      setModalOpen(false)
      const { start, end } = rangeRef.current
      if (start) fetchRange(start, end)
    } catch (err) { toast.error(err.message) }
  }

  const handleDelete = () => {
    if (!editId) return
    requestConfirm({
      title: 'Delete entry', message: 'Delete this calendar entry?',
      onConfirm: async () => {
        try {
          await api.delete(`/calendar/events/${editId}`)
          setModalOpen(false)
          const { start, end } = rangeRef.current
          if (start) fetchRange(start, end)
        } catch (err) { toast.error(err.message) }
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-foreground">Calendar</h1>
        <Button onClick={openCreate}>Add event / leave</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        {ALL_CATS.map(c => (
          <label key={c} className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
            <input type="checkbox" checked={enabled[c]} onChange={() => setEnabled(s => ({ ...s, [c]: !s[c] }))} />
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: COLORS[c] }} />
            {LABELS[c]}
          </label>
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl p-3">
        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          headerToolbar={{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listMonth' }}
          height="auto"
          events={fcEvents}
          datesSet={handleDatesSet}
          eventClick={handleEventClick}
        />
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editId ? 'Edit entry' : 'Add event / leave'}>
        <form onSubmit={handleSave} className="space-y-3">
          <Input label="Title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required />
          <div>
            <label htmlFor="event-category" className="text-sm font-medium text-foreground">Category</label>
            <select id="event-category" className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
              <option value="event">Event</option>
              <option value="leave">Leave</option>
            </select>
          </div>
          <Input label="Start date" type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} required />
          <Input label="End date (optional)" type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
          <Input label="Notes (optional)" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          <div className="flex justify-between gap-2 pt-2">
            {editId && canEditCurrent
              ? <Button type="button" variant="destructive" onClick={handleDelete}>Delete</Button>
              : <span />}
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={editId && !canEditCurrent}>Save</Button>
            </div>
          </div>
        </form>
      </Modal>
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
