import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'

// Provider export names confirmed against source: AuthProvider, ThemeProvider,
// ToastProvider — none require props beyond children.

function Providers({ children }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}

export function renderWithProviders(ui, { route = '/', user, role } = {}) {
  if (user || role) {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify(user || { id: 1, username: 'admin', role: role || 'admin' }))
  }
  const result = render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    { wrapper: Providers },
  )
  return { user: userEvent.setup(), ...result }
}

// For pages that read route params, e.g. /pilots/:id
export function renderRoute(element, { path, route, user, role } = {}) {
  if (user || role) {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify(user || { id: 1, username: 'admin', role: role || 'admin' }))
  }
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
