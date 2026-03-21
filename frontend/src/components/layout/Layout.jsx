import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'

const pageTitles = {
  '/': 'Dashboard',
  '/analytics': 'Analytics',
  '/flights': 'Flights',
  '/flights/review': 'Flight Review Queue',
  '/pilots': 'Pilots',
  '/fleet': 'Fleet Management',
  '/certifications': 'Certifications',
  '/maintenance': 'Maintenance',
  '/media': 'Media',
  '/reports': 'Reports',
  '/alerts': 'Alerts',
  '/settings': 'Settings',
}

export function Layout() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || 'Drone Unit Manager'
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('sidebar-collapsed') === 'true')
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const handler = (e) => setSidebarCollapsed(e.detail.collapsed)
    window.addEventListener('sidebar-toggle', handler)
    return () => window.removeEventListener('sidebar-toggle', handler)
  }, [])

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-14 bg-card border-b border-border flex items-center px-4 z-40">
        <button onClick={() => setMobileOpen(!mobileOpen)} className="p-1">
          <Menu className="w-5 h-5 text-foreground" />
        </button>
        <span className="ml-3 font-semibold text-foreground">Drone Unit Manager</span>
      </div>

      {/* Mobile overlay backdrop */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 bg-black/50 z-40" onClick={() => setMobileOpen(false)} />
      )}

      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
      <div className={`transition-all duration-300 md:${sidebarCollapsed ? 'pl-16' : 'pl-60'} ${sidebarCollapsed ? 'md:pl-16' : 'md:pl-60'}`}>
        <div className="hidden md:block">
          <TopBar title={title} />
        </div>
        <main className="p-4 md:p-6 pt-18 md:pt-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
