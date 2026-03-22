import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'
import { Layout } from '@/components/layout/Layout'
import { lazy, Suspense } from 'react'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-bg flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-xl p-8 max-w-md text-center">
            <h2 className="text-xl font-semibold text-foreground mb-2">Something went wrong</h2>
            <p className="text-muted-foreground mb-4">{this.state.error?.message || 'An unexpected error occurred.'}</p>
            <button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg">
              Reload Page
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const FlightsPage = lazy(() => import('@/pages/FlightsPage'))
const FlightDetailPage = lazy(() => import('@/pages/FlightDetailPage'))
const PilotsPage = lazy(() => import('@/pages/PilotsPage'))
const PilotDetailPage = lazy(() => import('@/pages/PilotDetailPage'))
const FleetPage = lazy(() => import('@/pages/FleetPage'))
const VehicleDetailPage = lazy(() => import('@/pages/VehicleDetailPage'))
const BatteryDetailPage = lazy(() => import('@/pages/BatteryDetailPage'))
const ControllerDetailPage = lazy(() => import('@/pages/ControllerDetailPage'))
const CertificationsPage = lazy(() => import('@/pages/CertificationsPage'))
const MaintenancePage = lazy(() => import('@/pages/MaintenancePage'))
const MediaPage = lazy(() => import('@/pages/MediaPage'))
const ReportsPage = lazy(() => import('@/pages/ReportsPage'))
const AlertsPage = lazy(() => import('@/pages/AlertsPage'))
const MissionLogPage = lazy(() => import('@/pages/MissionLogPage'))
const TrainingLogPage = lazy(() => import('@/pages/TrainingLogPage'))
const DocumentStoragePage = lazy(() => import('@/pages/DocumentStoragePage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))

function Spinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-background flex items-center justify-center"><Spinner /></div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-background flex items-center justify-center"><Spinner /></div>

  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/flights" element={<FlightsPage />} />
          <Route path="/flights/:id" element={<FlightDetailPage />} />
          <Route path="/missions" element={<MissionLogPage />} />
          <Route path="/training" element={<TrainingLogPage />} />
          <Route path="/pilots" element={<PilotsPage />} />
          <Route path="/pilots/:id" element={<PilotDetailPage />} />
          <Route path="/fleet" element={<FleetPage />} />
          <Route path="/fleet/vehicles/:id" element={<VehicleDetailPage />} />
          <Route path="/fleet/batteries/:id" element={<BatteryDetailPage />} />
          <Route path="/fleet/controllers/:id" element={<ControllerDetailPage />} />
          <Route path="/certifications" element={<CertificationsPage />} />
          <Route path="/maintenance" element={<MaintenancePage />} />
          <Route path="/media" element={<MediaPage />} />
          <Route path="/documents" element={<DocumentStoragePage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>
            <ErrorBoundary>
              <AppRoutes />
            </ErrorBoundary>
          </ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
