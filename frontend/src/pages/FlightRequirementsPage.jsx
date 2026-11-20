/**
 * Flight Requirements, under Compliance in the sidebar: every requirement with
 * its current progress for anyone with requirements.view; the builder,
 * templates and settings for those with requirements.manage.
 */
import { Navigate } from 'react-router-dom'
import { CalendarClock } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import RequirementsTab from '@/components/requirements/RequirementsTab'

export default function FlightRequirementsPage() {
  const { can } = useAuth()
  // Without view, the page sends the user home, as the route guard does for the audit log.
  if (!can('requirements.view')) return <Navigate to="/" replace />
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
          <CalendarClock className="w-5 h-5 text-primary" aria-hidden="true" /> Flight Requirements
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Flight time pilots must log in a period, such as 15 minutes on each model every quarter.
        </p>
      </div>
      <RequirementsTab />
    </div>
  )
}
