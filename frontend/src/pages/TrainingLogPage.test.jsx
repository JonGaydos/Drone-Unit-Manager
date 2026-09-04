import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import TrainingLogPage from './TrainingLogPage'

// Mount endpoints (Promise.all in load()):
//   GET /training-logs?...   (array)
//   GET /pilots /vehicles
const TRAININGS = [
  { id: 1, date: '2026-05-01', title: 'Night Ops Recurrent', training_type: 'Recurrent', instructor: 'Sgt Lee', location: 'Field A', man_hours: 3, outcome: 'completed', pilots: [{ id: 11, pilot_id: 5, pilot_name: 'Jane Doe', role: 'Student', hours: 3 }] },
  { id: 2, date: '2026-05-02', title: 'Initial Cert', training_type: 'Initial', instructor: 'Capt Ray', location: 'Field B', man_hours: 6, outcome: 'incomplete', pilots: [] },
]

function mockMount(overrides = {}) {
  const base = {
    trainings: () => HttpResponse.json(TRAININGS),
    ...overrides,
  }
  server.use(
    http.get('/api/training-logs', base.trainings),
    http.get('/api/pilots', () => HttpResponse.json([{ id: 5, full_name: 'Jane Doe', is_active: true }])),
    http.get('/api/vehicles', () => HttpResponse.json([{ id: 2, nickname: 'Falcon', model: 'Mavic 3' }])),
  )
}

describe('TrainingLogPage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<TrainingLogPage />, { role: 'admin' })
    expect(await screen.findByText('Night Ops Recurrent')).toBeInTheDocument()
  })

  it('loads and renders training rows from a populated payload', async () => {
    mockMount()
    renderWithProviders(<TrainingLogPage />, { role: 'admin' })
    expect(await screen.findByText('Night Ops Recurrent')).toBeInTheDocument()
    expect(screen.getByText('Initial Cert')).toBeInTheDocument()
    expect(screen.getByText('Sgt Lee')).toBeInTheDocument()
  })

  it('shows the empty state when there are no training logs', async () => {
    mockMount({ trainings: () => HttpResponse.json([]) })
    renderWithProviders(<TrainingLogPage />, { role: 'admin' })
    expect(await screen.findByText('No training logs found')).toBeInTheDocument()
  })

  it('shows the error banner when the primary endpoint 500s', async () => {
    mockMount({ trainings: () => HttpResponse.json({ detail: 'training boom' }, { status: 500 }) })
    renderWithProviders(<TrainingLogPage />, { role: 'admin' })
    expect(await screen.findByText('training boom')).toBeInTheDocument()
  })

  it('fires the filtered request with the right training_type query', async () => {
    let lastUrl = null
    mockMount({
      trainings: ({ request }) => { lastUrl = new URL(request.url); return HttpResponse.json(TRAININGS) },
    })
    const { user } = renderWithProviders(<TrainingLogPage />, { role: 'admin' })

    await screen.findByText('Night Ops Recurrent')
    // The last select is the training-type filter ("All Types").
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[selects.length - 1], 'Initial')

    await screen.findByText('Night Ops Recurrent')
    expect(lastUrl.searchParams.get('training_type')).toBe('Initial')
  })
})
