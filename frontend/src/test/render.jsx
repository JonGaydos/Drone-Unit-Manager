import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'
import { AuthSettled } from './AuthSettled'
import { withPermissions } from './permissions'

// Provider export names confirmed against source: AuthProvider, ThemeProvider,
// ToastProvider — none require props beyond children.

function Providers({ children }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider><AuthSettled>{children}</AuthSettled></AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}

// Seed the signed-in user. GET /api/auth/me returns it (test/handlers.js), with
// the role's default permissions plus any `permissions` overrides.
function seedUser({ user, role, permissions }) {
  if (!user && !role) return
  localStorage.setItem('token', 'test-token')
  const base = user || { id: 1, username: 'admin', role }
  localStorage.setItem('user', JSON.stringify(withPermissions(base, permissions)))
}

export function renderWithProviders(ui, { route = '/', user, role, permissions } = {}) {
  seedUser({ user, role, permissions })
  const result = render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    { wrapper: Providers },
  )
  return { user: userEvent.setup(), ...result }
}

// For pages that read route params, e.g. /pilots/:id
export function renderRoute(element, { path, route, user, role, permissions } = {}) {
  seedUser({ user, role, permissions })
  return {
    user: userEvent.setup(),
    ...render(
      <MemoryRouter initialEntries={[route]}>
        <Routes><Route path={path} element={element} /></Routes>
      </MemoryRouter>,
      { wrapper: Providers },
    ),
  }
}
