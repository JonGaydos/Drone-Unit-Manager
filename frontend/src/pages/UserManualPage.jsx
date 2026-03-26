import { useState } from 'react'
import { BookOpen, ChevronRight, ChevronDown, Search } from 'lucide-react'

const sections = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    content: [
      {
        title: 'First-Run Setup',
        body: 'On first launch, the application displays a setup wizard. Enter your organization name, your name, and create an admin account. No default credentials exist — the first account created becomes the administrator.'
      },
      {
        title: 'User Roles',
        body: `The application has four roles with increasing permissions:

• **Viewer** — Read-only access to all data.
• **Pilot** — Can view data and submit flight plans. Pilots can edit their own profile.
• **Supervisor** — Can approve flights, manage pilots, create/edit most records, and generate reports.
• **Admin** — Full access including user management, system settings, and audit log.`
      },
      {
        title: 'Navigating the App',
        body: 'Use the sidebar on the left to navigate between sections. The sidebar can be collapsed using the arrow at the bottom. On mobile devices, tap the menu icon in the top-left corner to open the sidebar.'
      },
    ]
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    content: [
      {
        title: 'Overview',
        body: 'The dashboard provides a snapshot of your drone program: total flights, flight hours, active pilots, fleet size, flights needing review, and upcoming certification expirations. Click any stat card to navigate to its detail page.'
      },
      {
        title: 'Recent Flights',
        body: 'The recent flights table shows the last 10 flights. Click a flight date to view its full detail page with telemetry, map, and equipment information.'
      },
      {
        title: 'Certification Expirations',
        body: 'Certifications expiring within 90 days are shown with color-coded badges: green (60+ days), amber (30-60 days), and red (under 30 days or expired).'
      },
    ]
  },
  {
    id: 'flights',
    title: 'Flights',
    content: [
      {
        title: 'Viewing Flights',
        body: 'The Flights page shows all recorded flights with filtering by date range, pilot, vehicle, purpose, and review status. Use the text search to find flights by pilot name, vehicle, purpose, or location.'
      },
      {
        title: 'Adding Flights Manually',
        body: 'Click "Add Flight" to record a flight manually. Select the pilot, vehicle, date, duration, purpose, and optionally a takeoff address and case number.'
      },
      {
        title: 'Reviewing Flights',
        body: 'Flights imported from the Skydio API arrive with "Needs Review" status. Supervisors can review individual flights via the inline edit button, or use "Approve All" to mark all pending flights as reviewed.'
      },
      {
        title: 'Flight Detail',
        body: 'Click a flight ID to see the full detail page. If telemetry data was synced, you\'ll see an interactive map with the flight path and charts for altitude, speed, and battery level over time.'
      },
    ]
  },
  {
    id: 'fleet',
    title: 'Fleet Management',
    content: [
      {
        title: 'Vehicles',
        body: 'The Fleet page shows all drones, batteries, and controllers. Click any item to view its detail page with flight history, maintenance records, and specifications.'
      },
      {
        title: 'Batteries',
        body: 'Battery records track serial numbers, cycle counts, and health status. Battery assignments to flights are tracked automatically when imported from the API.'
      },
      {
        title: 'Controllers',
        body: 'Remote controller inventory is tracked separately. Controllers can be assigned to specific vehicles or shared across the fleet.'
      },
      {
        title: 'Components',
        body: 'Component-level tracking (propellers, gimbals, cameras) lets you monitor individual parts with flight hours, installation dates, and warranty information.'
      },
      {
        title: 'Equipment Checkout',
        body: 'The equipment checkout system provides chain-of-custody tracking. Check equipment out to a pilot, and check it back in when returned.'
      },
    ]
  },
  {
    id: 'pilots',
    title: 'Pilots',
    content: [
      {
        title: 'Pilot Profiles',
        body: 'Each pilot has a profile with contact information, badge number, photo, and status (active/inactive). Click a pilot\'s name to view their full profile with flight history, certifications, and training records.'
      },
      {
        title: 'Pilot Currency',
        body: 'Currency rules define how many flight hours a pilot must log within a given period (e.g., 3 hours in 90 days). The system automatically tracks compliance and alerts when a pilot is approaching non-currency.'
      },
    ]
  },
  {
    id: 'certifications',
    title: 'Certifications',
    content: [
      {
        title: 'Certification Types',
        body: 'Create custom certification types from the Settings page (e.g., Part 107, TRUST, Night Waiver). Each type can have custom status labels and renewal periods.'
      },
      {
        title: 'Tracking Expirations',
        body: 'The Certifications page shows a matrix of all pilots and their certification statuses. Color-coded badges indicate valid, expiring soon, or expired status. The system generates alerts for upcoming expirations.'
      },
    ]
  },
  {
    id: 'maintenance',
    title: 'Maintenance',
    content: [
      {
        title: 'Maintenance Records',
        body: 'Record maintenance events for any vehicle, battery, or controller. Include the date, description, technician, cost, and any related documents.'
      },
      {
        title: 'Recurring Schedules',
        body: 'Set up recurring maintenance schedules (monthly, quarterly, yearly) for automatic reminders. The system tracks when each item is next due and generates alerts when overdue.'
      },
    ]
  },
  {
    id: 'weather',
    title: 'Weather',
    content: [
      {
        title: 'Weather Briefing',
        body: 'The Weather page provides a live aviation weather briefing using METAR and TAF data. Enter a location (airport code, city, or GPS coordinates) to get current conditions.'
      },
      {
        title: 'GO/NO-GO Advisory',
        body: 'Based on your configured weather thresholds (wind speed, visibility, cloud ceiling), the system provides a GO, CAUTION, or NO-GO advisory. Configure thresholds from the Settings page.'
      },
    ]
  },
  {
    id: 'flight-plans',
    title: 'Flight Plans & Checklists',
    content: [
      {
        title: 'Flight Plan Submission',
        body: 'Pilots can submit flight plans for supervisor approval. Include the mission objective, location, date/time, equipment, and weather conditions.'
      },
      {
        title: 'Pre-Flight Checklists',
        body: 'Create custom pre-flight checklist templates from the Checklists page. Pilots complete checklists before each flight, and completed checklists are stored for compliance records.'
      },
    ]
  },
  {
    id: 'documents',
    title: 'Documents & Photos',
    content: [
      {
        title: 'Document Storage',
        body: 'Upload and organize documents in folders. System folders (General, Certifications, Insurance, Maintenance, Reports) are created automatically. Create custom folders for additional organization. Documents uploaded from pilot profiles and certifications are auto-filed.'
      },
      {
        title: 'Photo Gallery',
        body: 'Upload photos from flights, training, and events. Photos are organized by date with a lightbox viewer. Associate pilots with photos for easy reference.'
      },
    ]
  },
  {
    id: 'reports',
    title: 'Reports & Analytics',
    content: [
      {
        title: 'PDF Reports',
        body: `Generate professional PDF reports with your organization\'s logo and branding. Available report types:

• Flight Summary — All flights within a date range
• Pilot Hours — Flight hours by pilot
• Equipment Utilization — Usage statistics per vehicle
• Pilot Activity Summary — Per-pilot activity report
• Annual Unit Report — Yearly program summary
• Certifications — Current certification status
• Battery Status — Battery health and usage
• Maintenance History — Maintenance records by date range`
      },
      {
        title: 'CSV Export',
        body: 'Every list page supports CSV export. Click the "Export CSV" button to download the current view as a spreadsheet.'
      },
      {
        title: 'Analytics',
        body: 'The Analytics page provides interactive Power BI-style charts. Click any chart element (a pilot, year, purpose, or vehicle) to cross-filter all other charts. The map shows all flight locations.'
      },
    ]
  },
  {
    id: 'compliance',
    title: 'Compliance',
    content: [
      {
        title: 'Compliance Score',
        body: 'The Compliance page calculates a 0-100 score based on certification status, registration status, maintenance compliance, and pilot currency. Each category shows what\'s compliant and what needs attention.'
      },
    ]
  },
  {
    id: 'incidents',
    title: 'Activity Reports (Incidents)',
    content: [
      {
        title: 'Incident Reporting',
        body: 'Report incidents including crashes, near-misses, equipment failures, and successes (missing persons found, suspects located, evidence collected). Each report includes severity level, description, corrective actions, and can be linked to flights, pilots, and vehicles.'
      },
    ]
  },
  {
    id: 'integrations',
    title: 'API Integrations',
    content: [
      {
        title: 'Skydio Cloud API',
        body: `To connect to the Skydio Cloud API:

1. Log into Skydio Cloud at cloud.skydio.com
2. Go to Settings > Integrations > API Tokens
3. Create a token with read access to: Flights, Flight Telemetry, Vehicles, Batteries, Controllers, Users, Attachments, Sensor Packages
4. In Drone Unit Manager, go to Settings > Skydio Cloud API
5. Enter the API Token and Token ID
6. Click "Test Connection", then "Sync All"

For automatic pilot matching, ensure each pilot\'s profile has their Skydio account email address.`
      },
      {
        title: 'Excel Import',
        body: 'Import flight data from Excel spreadsheets with a sheet named "Skydio" containing columns for Flight ID, Vehicle, Pilot, timestamps, location, duration, and equipment. An optional "Pilot Info" sheet imports certification data.'
      },
    ]
  },
  {
    id: 'settings',
    title: 'Settings & Admin',
    content: [
      {
        title: 'Organization Settings',
        body: 'Configure your organization name, logo, and timezone from the Settings page.'
      },
      {
        title: 'User Management',
        body: 'Admins can create, edit, and deactivate user accounts from Settings > Users. Assign roles and link users to pilot profiles for permissions-based access.'
      },
      {
        title: 'Audit Log',
        body: 'The Audit Log (admin only) shows a complete history of all actions taken in the system: who did what, when, and what changed. Use it for accountability and compliance auditing.'
      },
    ]
  },
  {
    id: 'backup',
    title: 'Backup & Restore',
    content: [
      {
        title: 'Backing Up Your Data',
        body: `All data is stored in the /app/data volume. To create a backup:

1. Stop the container: docker stop drone-unit-manager
2. Copy the data directory:
   - drone_unit_manager.db (main database)
   - telemetry.db (flight telemetry)
   - uploads/ (documents and photos)
3. Restart the container: docker start drone-unit-manager`
      },
      {
        title: 'Restoring From Backup',
        body: 'To restore, stop the container, copy your backup files into the data directory, and restart. The application will automatically detect and use the existing database.'
      },
    ]
  },
]

export default function UserManualPage() {
  const [expandedSections, setExpandedSections] = useState(new Set(sections.map(s => s.id)))
  const [search, setSearch] = useState('')

  const toggleSection = (id) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredSections = search
    ? sections.filter(s =>
        s.title.toLowerCase().includes(search.toLowerCase()) ||
        s.content.some(c =>
          c.title.toLowerCase().includes(search.toLowerCase()) ||
          c.body.toLowerCase().includes(search.toLowerCase())
        )
      )
    : sections

  const renderMarkdown = (text) => {
    return text.split('\n').map((line, i) => {
      if (line.startsWith('• **')) {
        const match = line.match(/^• \*\*(.+?)\*\*(.*)$/)
        if (match) {
          return (
            <div key={i} className="flex gap-2 ml-2 mt-1">
              <span className="text-muted-foreground">•</span>
              <span><strong className="text-foreground">{match[1]}</strong>{match[2]}</span>
            </div>
          )
        }
      }
      if (line.startsWith('• ')) {
        return (
          <div key={i} className="flex gap-2 ml-2 mt-1">
            <span className="text-muted-foreground">•</span>
            <span>{line.slice(2)}</span>
          </div>
        )
      }
      if (line.match(/^\d+\./)) {
        return (
          <div key={i} className="ml-2 mt-1">{line}</div>
        )
      }
      if (line.trim() === '') return <div key={i} className="h-2" />
      return <span key={i}>{line} </span>
    })
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
          <BookOpen className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Manual</h1>
          <p className="text-sm text-muted-foreground">Complete guide to using Drone Unit Manager</p>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search manual..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {filteredSections.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No sections match your search.
        </div>
      )}

      {filteredSections.map(section => (
        <div key={section.id} className="bg-card border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => toggleSection(section.id)}
            className="w-full flex items-center justify-between p-5 text-left hover:bg-muted/30 transition-colors"
          >
            <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
            {expandedSections.has(section.id) ? (
              <ChevronDown className="w-5 h-5 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="w-5 h-5 text-muted-foreground shrink-0" />
            )}
          </button>
          {expandedSections.has(section.id) && (
            <div className="px-5 pb-5 space-y-4">
              {section.content.map((item, idx) => (
                <div key={idx}>
                  <h3 className="text-sm font-semibold text-foreground mb-1.5">{item.title}</h3>
                  <div className="text-sm text-muted-foreground leading-relaxed">
                    {renderMarkdown(item.body)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
