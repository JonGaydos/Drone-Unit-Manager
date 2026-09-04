import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'

describe('harness', () => {
  it('renders a component through the providers', () => {
    renderWithProviders(<div>hello harness</div>)
    expect(screen.getByText('hello harness')).toBeInTheDocument()
  })

  it('MSW intercepts an api call', async () => {
    server.use(http.get('/api/ping', () => HttpResponse.json({ ok: true })))
    const { api } = await import('@/api/client')
    await expect(api.get('/ping')).resolves.toEqual({ ok: true })
  })
})
