/**
 * Canonical sidebar navigation metadata, shared by the Sidebar component and
 * the Settings sidebar-config editor so the two never drift.
 */
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Box,
  Calendar,
  Camera,
  ClipboardCheck,
  ClipboardList,
  CloudSun,
  FileText,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  PackageCheck,
  Radar,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Stamp,
  Target,
  Users,
  Wrench,
} from 'lucide-react'
import { QuadcopterIcon } from '@/components/icons/QuadcopterIcon'

/** Section order for the grouped (default) sidebar layout. */
export const GROUP_ORDER = ['Overview', 'Flight Ops', 'Fleet & Crew', 'Compliance', 'Media & Reports', 'System']

/** @type {Array<{to: string, icon: Function, label: string, group: string, badge?: string, adminOnly?: boolean}>} Navigation menu items. */
export const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', group: 'Overview' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics', group: 'Overview' },
  { to: '/weather', icon: CloudSun, label: 'Weather', group: 'Flight Ops' },
  { to: '/airspace', icon: Radar, label: 'Airspace', group: 'Flight Ops' },
  { to: '/flight-plans', icon: ClipboardCheck, label: 'Flight Plans', badge: 'pendingPlansCount', group: 'Flight Ops' },
  { to: '/checklists', icon: ClipboardList, label: 'Checklists', group: 'Flight Ops' },
  { to: '/flights', icon: QuadcopterIcon, label: 'Flights', badge: 'reviewCount', group: 'Flight Ops' },
  { to: '/missions', icon: Target, label: 'Mission Log', group: 'Flight Ops' },
  { to: '/training', icon: GraduationCap, label: 'Training Log', group: 'Flight Ops' },
  { to: '/calendar', icon: Calendar, label: 'Calendar', group: 'Flight Ops' },
  { to: '/pilots', icon: Users, label: 'Pilots', group: 'Fleet & Crew' },
  { to: '/fleet', icon: Box, label: 'Fleet', group: 'Fleet & Crew' },
  { to: '/certifications', icon: ShieldCheck, label: 'Certifications', group: 'Fleet & Crew' },
  { to: '/maintenance', icon: Wrench, label: 'Maintenance', group: 'Fleet & Crew' },
  { to: '/checkouts', icon: PackageCheck, label: 'Checkouts', group: 'Fleet & Crew' },
  { to: '/compliance', icon: Shield, label: 'Compliance', group: 'Compliance' },
  { to: '/operating-authority', icon: Stamp, label: 'Operating Authority', group: 'Compliance' },
  { to: '/alerts', icon: Bell, label: 'Alerts', group: 'Compliance' },
  { to: '/incidents', icon: AlertTriangle, label: 'Activity Reports', group: 'Compliance' },
  { to: '/media', icon: Camera, label: 'Photo Gallery', group: 'Media & Reports' },
  { to: '/documents', icon: FolderOpen, label: 'Documents', group: 'Media & Reports' },
  { to: '/reports', icon: FileText, label: 'Reports', group: 'Media & Reports' },
  { to: '/settings', icon: Settings, label: 'Settings', group: 'System' },
  { to: '/audit-log', icon: ScrollText, label: 'Audit Log', adminOnly: true, group: 'System' },
]

/** {to, label, group} projection (no icons) for the Settings sidebar editor. */
export const SIDEBAR_META = NAV_ITEMS.map(({ to, label, group }) => ({ to, label, group }))
