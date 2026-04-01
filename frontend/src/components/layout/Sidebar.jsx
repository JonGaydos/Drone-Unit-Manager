/**
 * Collapsible sidebar navigation with role-based filtering and configurable item order.
 */
import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/api/client'
import {
  LayoutDashboard,
  BarChart3,
  Users,
  Box,
  ShieldCheck,
  Wrench,
  Camera,
  FileText,
  FolderOpen,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  ClipboardCheck,
  Target,
  GraduationCap,
  ScrollText,
  AlertTriangle,
  CloudSun,
  ClipboardList,
  Shield,
  BookOpen,
  Radar,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

/** @type {Array<{to: string, icon: Function, label: string, badge?: string, adminOnly?: boolean}>} Navigation menu items. */
const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/weather', icon: CloudSun, label: 'Weather' },
  { to: '/airspace', icon: Radar, label: 'Airspace' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/flight-plans', icon: ClipboardCheck, label: 'Flight Plans', badge: 'pendingPlansCount' },
  { to: '/checklists', icon: ClipboardList, label: 'Checklists' },
  { to: '/flights', icon: QuadcopterIcon, label: 'Flights', badge: 'reviewCount' },
  { to: '/missions', icon: Target, label: 'Mission Log' },
  { to: '/training', icon: GraduationCap, label: 'Training Log' },
  { to: '/pilots', icon: Users, label: 'Pilots' },
  { to: '/fleet', icon: Box, label: 'Fleet' },
  { to: '/certifications', icon: ShieldCheck, label: 'Certifications' },
  { to: '/maintenance', icon: Wrench, label: 'Maintenance' },
  { to: '/media', icon: Camera, label: 'Photo Gallery' },
  { to: '/documents', icon: FolderOpen, label: 'Documents' },
  { to: '/reports', icon: FileText, label: 'Reports' },
  { to: '/compliance', icon: Shield, label: 'Compliance' },
  { to: '/alerts', icon: Bell, label: 'Alerts' },
  { to: '/incidents', icon: AlertTriangle, label: 'Activity Reports' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/audit-log', icon: ScrollText, label: 'Audit Log', adminOnly: true },
]

/**
 * Sidebar navigation component with collapse toggle and mobile slide-in support.
 * Fetches badge counts for flights needing review and pending flight plans.
 * Supports server-side configuration for item visibility and ordering.
 * @param {Object} props
 * @param {boolean} props.mobileOpen - Whether the mobile sidebar drawer is open.
 * @param {Function} props.onMobileClose - Callback to close the mobile sidebar.
 */
export function Sidebar({ mobileOpen, onMobileClose }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebar-collapsed') === 'true')
  const [reviewCount, setReviewCount] = useState(0)
  const [pendingPlansCount, setPendingPlansCount] = useState(0)
  const { user, logout, isAdmin } = useAuth()
  const location = useLocation()

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      localStorage.setItem('sidebar-collapsed', String(next))
      globalThis.dispatchEvent(new CustomEvent('sidebar-toggle', { detail: { collapsed: next } }))
      return next
    })
  }

  const [sidebarConfig, setSidebarConfig] = useState(null)

  useEffect(() => {
    api.get('/flights/count?review_status=needs_review')
      .then(data => setReviewCount(data.count))
      .catch(err => console.warn('Failed to fetch review count:', err.message))
    api.get('/flight-plans/pending/count')
      .then(data => setPendingPlansCount(data.count))
      .catch(err => console.warn('Failed to fetch pending plans count:', err.message))
    api.get('/settings')
      .then(data => {
        const cfg = data.find(s => s.key === 'sidebar_config')
        if (cfg?.value) {
          try { setSidebarConfig(JSON.parse(cfg.value)) } catch { /* invalid JSON, keep defaults */ }
        }
      })
      .catch(err => console.warn('Failed to fetch sidebar config:', err.message))
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
        <QuadcopterIcon className="w-7 h-7 text-primary shrink-0" />
        {(!collapsed || mobileOpen) && (
          <span className="ml-3 font-semibold text-lg text-foreground whitespace-nowrap">
            Drone Unit Manager
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {(() => {
          let items = navItems.filter(item => !item.adminOnly || isAdmin)
          if (sidebarConfig && Array.isArray(sidebarConfig)) {
            // Build a map of path -> config
            const configMap = {}
            sidebarConfig.forEach(c => { configMap[c.to] = c })
            // Filter visible and sort by order
            items = items
              .filter(item => {
                const cfg = configMap[item.to]
                return !cfg || cfg.visible !== false
              })
              .sort((a, b) => {
                const aOrder = configMap[a.to]?.order ?? 999
                const bOrder = configMap[b.to]?.order ?? 999
                return aOrder - bOrder
              })
          }
          return items
        })().map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={() => onMobileClose?.()}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-all duration-150 hover:translate-x-0.5',
                isActive
                  ? 'bg-primary/10 text-primary border-l-2 border-primary font-medium'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground'
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
            {(!collapsed || mobileOpen) && item.badge === 'pendingPlansCount' && pendingPlansCount > 0 && (
              <span className="bg-amber-500 text-white text-xs px-1.5 py-0.5 rounded-full font-medium">
                {pendingPlansCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User Manual link */}
      <div className="px-2 pb-2">
        <NavLink
          to="/manual"
          onClick={() => onMobileClose?.()}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 px-4 py-2.5 mx-0 rounded-lg text-sm transition-all duration-150 hover:translate-x-0.5',
              isActive
                ? 'bg-primary/10 text-primary border-l-2 border-primary font-medium'
                : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
            )
          }
        >
          <BookOpen className="w-5 h-5 shrink-0" />
          {(!collapsed || mobileOpen) && (
            <span className="whitespace-nowrap">User Manual</span>
          )}
        </NavLink>
      </div>

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
