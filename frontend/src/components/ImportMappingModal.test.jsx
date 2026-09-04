import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import { ImportMappingModal } from './ImportMappingModal'

// The mapping UI is built from the preview the backend returns for the
// uploaded file: target_schema (app fields) + headers (the file's columns).
const PREVIEW = {
  row_count: 3,
  headers: ['When', 'Who', 'Notes'],
  sample_rows: [{ When: '2026-01-01', Who: 'Jane', Notes: 'ok' }],
  suggested_mapping: { date: 'When' },
  target_schema: [
    { key: 'date', label: 'Date', required: true, type: 'date' },
    { key: 'pilot', label: 'Pilot', required: false, type: 'string' },
  ],
}

function pickFile(user) {
  const input = document.querySelector('input[type="file"]')
  const file = new File(['When,Who,Notes\n2026-01-01,Jane,ok'], 'log.csv', { type: 'text/csv' })
  return user.upload(input, file)
}

describe('ImportMappingModal', () => {
  beforeEach(() => {
    server.use(http.post('/api/import/preview', () => HttpResponse.json(PREVIEW)))
  })

  it('renders the column-mapping table from the preview after a file is chosen', async () => {
    const { user } = renderWithProviders(
      <ImportMappingModal entity="missions" onClose={() => {}} onComplete={() => {}} />)

    expect(screen.getByText('Import Mission Logs')).toBeInTheDocument()
    await pickFile(user)

    // App fields from target_schema.
    expect(await screen.findByText('Date')).toBeInTheDocument()
    expect(screen.getByText('Pilot')).toBeInTheDocument()
    // The suggested mapping is preselected (Date -> "When").
    const selects = screen.getAllByRole('combobox')
    expect(selects[0]).toHaveValue('When')
  })

  it('changing a mapping and committing calls /api/import/commit with the mapping', async () => {
    let committedMapping = null
    server.use(http.post('/api/import/commit', ({ request }) => {
      committedMapping = new URL(request.url).searchParams.get('mapping')
      return HttpResponse.json({ created: 3, skipped: 0 })
    }))
    const onComplete = vi.fn()

    const { user } = renderWithProviders(
      <ImportMappingModal entity="missions" onClose={() => {}} onComplete={onComplete} />)

    await pickFile(user)
    await screen.findByText('Date')

    // Map the optional Pilot field to the "Who" column.
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[1], 'Who')

    await user.click(screen.getByRole('button', { name: /Import 3 rows/ }))

    await waitFor(() => expect(committedMapping).toContain('"pilot":"Who"'))
    // Result summary appears after commit.
    expect(await screen.findByText(/record.* created/)).toBeInTheDocument()
  })

  it('disables commit while a required field is unmapped', async () => {
    server.use(http.post('/api/import/preview', () =>
      HttpResponse.json({ ...PREVIEW, suggested_mapping: {} })))

    const { user } = renderWithProviders(
      <ImportMappingModal entity="missions" onClose={() => {}} onComplete={() => {}} />)

    await pickFile(user)
    await screen.findByText('Date')

    // Required Date is unmapped -> the import button is disabled.
    expect(screen.getByRole('button', { name: /Import 3 rows/ })).toBeDisabled()
    expect(screen.getByText('Pick a column')).toBeInTheDocument()
  })
})
