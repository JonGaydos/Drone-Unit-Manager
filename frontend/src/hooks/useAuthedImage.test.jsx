import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { useAuthedImage } from '@/hooks/useAuthedImage'

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

afterEach(() => { vi.restoreAllMocks() })

describe('useAuthedImage', () => {
  it('fetches an /api/ image with the session token and returns a blob URL', async () => {
    localStorage.setItem('token', 'test-token')
    let auth = null
    server.use(http.get('/api/pilots/7/photo/view', ({ request }) => {
      auth = request.headers.get('Authorization')
      return new HttpResponse(PNG, { headers: { 'Content-Type': 'image/png' } })
    }))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:pilot-7')
    const { result } = renderHook(() => useAuthedImage('/api/pilots/7/photo/view?t=1'))
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current).toBe('blob:pilot-7'))
    expect(auth).toBe('Bearer test-token')
  })

  it('revokes the blob URL on unmount', async () => {
    server.use(http.get('/api/vehicles/3/photo/view', () =>
      new HttpResponse(PNG, { headers: { 'Content-Type': 'image/png' } })))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:vehicle-3')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const { result, unmount } = renderHook(() => useAuthedImage('/api/vehicles/3/photo/view'))
    await waitFor(() => expect(result.current).toBe('blob:vehicle-3'))
    unmount()
    expect(revoke).toHaveBeenCalledWith('blob:vehicle-3')
  })

  it('returns null when the file cannot be fetched', async () => {
    server.use(http.get('/api/pilots/8/photo/view', () => new HttpResponse(null, { status: 404 })))
    const { result } = renderHook(() => useAuthedImage('/api/pilots/8/photo/view'))
    await new Promise(r => setTimeout(r, 20))
    expect(result.current).toBeNull()
  })

  it('passes through a URL outside the API and an empty one', () => {
    expect(renderHook(() => useAuthedImage('https://example.test/a.png')).result.current)
      .toBe('https://example.test/a.png')
    expect(renderHook(() => useAuthedImage(null)).result.current).toBeNull()
  })
})
