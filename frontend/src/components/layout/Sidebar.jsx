import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/api/client'
import {
  LayoutDashboard,
  BarChart3,
  Plane,
  Users,
  Box,
  ShieldCheck,
  Wrench,
  Image,
  FileText,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  ClipboardCheck,
  Target,
  GraduationCap,
} from 'lucide-react'
import { useEffect } from 'react'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/flights', icon: Plane, label: 'Flights', badge: 'reviewCount' },
  { to: '/missions', icon: Target, label: 'Mission Log' },
  { to: '/training', icon: GraduationCap, label: 'Training Log' },
  { to: '/pilots', icon: Users, label: 'Pilots' },
  { to: '/fleet', icon: Box, label: 'Fleet' },
  { to: '/certifications', icon: ShieldCheck, label: 'Certifications' },
  { to: '/maintenance', icon: Wrench, label: 'Maintenance' },
  { to: '/media', icon: Image, label: 'Media' },
  { to: '/reports', icon: FileText, label: 'Reports' },
  { to: '/alerts', icon: Bell, label: 'Alerts' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar({ mobileOpen, onMobileClose }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebar-collapsed') === 'true')
  const [reviewCount, setReviewCount] = useState(0)
  const { user, logout } = useAuth()
  const location = useLocation()

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      localStorage.setItem('sidebar-collapsed', String(next))
      window.dispatchEvent(new CustomEvent('sidebar-toggle', { detail: { collapsed: next } }))
      return next
    })
  }

  useEffect(() => {
    api.get('/flights/count?review_status=needs_review')
      .then(data => setReviewCount(data.count))
      .catch(() => {})
  }, [location.pathname])

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 bg-sidebar border-r border-border flex flex-col transition-all duration-300 z-50',
        // Mobile: slide in/out
        'max-md:w-60',
        mobileOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full',
        // Desktop: collapse behavior
        collapsed ? 'md:w-16' : 'md:w-60'
      )}
    >
      {/* Logo */}
      <div className="h-16 max-md:h-14 flex items-center px-4 border-b border-border">
        <Plane className="w-7 h-7 text-primary shrink-0" />
        {(!collapsed || mobileOpen) && (
          <span className="ml-3 font-semibold text-lg text-foreground whitespace-nowrap">
            Drone Unit Mgr
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={() => onMobileClose?.()}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-colors',
                isActive
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
              )
            }
          >
            <item.icon className="w-5 h-5 shrink-0" />
            {(!collapsed || mobileOpen) && (
              <span className="flex-1 whitespace-nowrap">{item.label}</span>
            )}
            {(!collapsed || mobileOpen) && item.badge === 'reviewCount' && reviewCount > 0 && (
              <span className="bg-destructive text-destructive-foreground text-xs px-1.5 py-0.5 rounded-full font-medium">
                {reviewCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div className="border-t border-border p-3">
        {(!collapsed || mobileOpen) && user && (
          <div className="flex items-center gap-2 px-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary text-sm font-medium">
              {user.display_name?.charAt(0) || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{user.display_name}</p>
              <p className="text-xs text-muted-foreground">{user.role}</p>
            </div>
            <button onClick={logout} aria-label="Log out" className="text-muted-foreground hover:text-foreground p-1">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
        <button
          onClick={toggleCollapsed}
          aria-label="Toggle sidebar"
          className="hidden md:flex w-full items-center justify-center p-2 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent rounded-lg transition-colors"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </aside>
  )
}
