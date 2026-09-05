import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import { normalizeDateValue } from '@/lib/utils'
import { sortVehicles, sortPilotsActiveFirst } from '@/lib/formatters'
import { FileBarChart, Upload, Loader2, Download, FileText, FileDown } from 'lucide-react'

/**
 * Which filters each report type actually applies, mirroring the generators in
 * backend/app/routers/reports.py. Offering a picker the generator ignores is
 * worse than not offering it: the report looks filtered and is not.
 */
const REPORT_FILTERS = {
  flight_summary: { pilots: true, vehicles: true },
  pilot_hours: { pilots: true, vehicles: true },
  equipment_utilization: { pilots: true, vehicles: true },
  pilot_certifications: { pilots: true, vehicles: false },
  battery_status: { pilots: false, vehicles: false },
  maintenance_history: { pilots: false, vehicles: false },
  pilot_activity_summary: { pilots: true, vehicles: true },
  annual_unit_report: { pilots: false, vehicles: false },
  per_pilot_annual_review: { pilots: true, vehicles: false },
}

/** Unknown types keep both pickers rather than silently hiding controls. */
const filtersFor = (type) => REPORT_FILTERS[type] || { pilots: true, vehicles: true }

const REPORT_TYPES = [
  { value: 'flight_summary', label: 'Flight Summary' },
  { value: 'pilot_hours', label: 'Pilot Hours' },
  { value: 'equipment_utilization', label: 'Equipment Utilization' },
  { value: 'pilot_certifications', label: 'Pilot Certifications' },
  { value: 'battery_status', label: 'Battery Status' },
  { value: 'maintenance_history', label: 'Maintenance History' },
  { value: 'pilot_activity_summary', label: 'Pilot Activity Summary' },
  { value: 'annual_unit_report', label: 'Annual Unit Report' },
  { value: 'per_pilot_annual_review', label: 'Per-Pilot Annual Review' },
]

export default function ReportsPage() {
  const [pilots, setPilots] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [reportResult, setReportResult] = useState(null)
  const [error, setError] = useState(null)


  // Form state
  const [reportType, setReportType] = useState('flight_summary')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [selectedPilots, setSelectedPilots] = useState([])
  const [selectedVehicles, setSelectedVehicles] = useState([])
  const [pilotSearch, setPilotSearch] = useState('')
  const [vehicleSearch, setVehicleSearch] = useState('')
  // Off by default: a report is the unit's own activity unless asked otherwise.
  const [includeNonUnit, setIncludeNonUnit] = useState(false)
  const [logoFile, setLogoFile] = useState(null)
  const [orgLogoUrl, setOrgLogoUrl] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get('/pilots'),
      api.get('/vehicles'),
      api.get('/settings').catch(() => []),
    ]).then(([p, v, s]) => {
      setPilots(p)
      setVehicles(v)
      // Check if org logo exists in settings
      const logoSetting = s.find?.(item => item.key === 'org_logo')
      if (logoSetting?.value) {
        setOrgLogoUrl(logoSetting.value)
      }
      try {
        const saved = JSON.parse(localStorage.getItem('dum_report_config') || 'null')
        if (saved) {
          if (saved.reportType) setReportType(saved.reportType)
          if (saved.dateFrom) setDateFrom(saved.dateFrom)
          if (saved.dateTo) setDateTo(saved.dateTo)
          if (Array.isArray(saved.selectedPilots)) setSelectedPilots(saved.selectedPilots)
          if (Array.isArray(saved.selectedVehicles)) setSelectedVehicles(saved.selectedVehicles)
        }
      } catch { /* ignore */ }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  // Persist the selection whenever it changes so an un-generated config survives a
  // reload. Guarded on !loading so the initial mount (before the saved config is
  // applied) does not overwrite storage with empty defaults.
  useEffect(() => {
    if (loading) return
    try {
      localStorage.setItem('dum_report_config', JSON.stringify({ reportType, dateFrom, dateTo, selectedPilots, selectedVehicles }))
    } catch { /* ignore quota */ }
  }, [loading, reportType, dateFrom, dateTo, selectedPilots, selectedVehicles])

  const togglePilot = (id) => {
    setSelectedPilots(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    )
  }

  const toggleVehicle = (id) => {
    setSelectedVehicles(prev =>
      prev.includes(id) ? prev.filter(v => v !== id) : [...prev, id]
    )
  }

  const visiblePilots = sortPilotsActiveFirst(pilots).filter(p => {
    if (!pilotSearch) return true
    return (p.full_name || '').toLowerCase().includes(pilotSearch.toLowerCase())
  })

  const visibleVehicles = sortVehicles(vehicles).filter(v => {
    if (!vehicleSearch) return true
    const q = vehicleSearch.toLowerCase()
    return (v.manufacturer || '').toLowerCase().includes(q) ||
           (v.model || '').toLowerCase().includes(q) ||
           (v.nickname || '').toLowerCase().includes(q) ||
           (v.serial_number || '').toLowerCase().includes(q)
  })

  const activeFilters = filtersFor(reportType)

  // Only send a filter the chosen report actually applies. Selections are kept
  // in state so switching report types and back restores them, but sending a
  // filter the generator ignores would also make the preview header claim a
  // narrowing that never happened.
  const filterPayload = () => ({
    pilot_ids: activeFilters.pilots && selectedPilots.length > 0 ? selectedPilots : undefined,
    vehicle_ids: activeFilters.vehicles && selectedVehicles.length > 0 ? selectedVehicles : undefined,
    include_non_unit: includeNonUnit || undefined,
  })

  const selectAllPilots = () => setSelectedPilots(visiblePilots.map(p => p.id))
  const clearAllPilots = () => setSelectedPilots([])
  const selectAllVehicles = () => setSelectedVehicles(visibleVehicles.map(v => v.id))
  const clearAllVehicles = () => setSelectedVehicles([])

  const applyDatePreset = (preset) => {
    const fmt = (d) => d.toISOString().slice(0, 10)
    const today = new Date()
    if (preset === 'last30') {
      const from = new Date(); from.setDate(from.getDate() - 30)
      setDateFrom(fmt(from)); setDateTo(fmt(today))
    } else if (preset === 'last90') {
      const from = new Date(); from.setDate(from.getDate() - 90)
      setDateFrom(fmt(from)); setDateTo(fmt(today))
    } else if (preset === 'ytd') {
      setDateFrom(`${today.getFullYear()}-01-01`); setDateTo(fmt(today))
    } else if (preset === 'lastyear') {
      const ly = today.getFullYear() - 1
      setDateFrom(`${ly}-01-01`); setDateTo(`${ly}-12-31`)
    } else if (preset === 'clear') {
      setDateFrom(''); setDateTo('')
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    setReportResult(null)

    try {
      const config = {
        report_type: reportType,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        ...filterPayload(),
      }

      try {
        localStorage.setItem('dum_report_config', JSON.stringify({ reportType, dateFrom, dateTo, selectedPilots, selectedVehicles }))
      } catch { /* ignore quota */ }

      // If a manual logo is selected, convert to base64; otherwise use org logo
      if (logoFile) {
        const reader = new FileReader()
        const base64 = await new Promise((resolve, reject) => {
          reader.onload = () => resolve(reader.result)
          reader.onerror = reject
          reader.readAsDataURL(logoFile)
        })
        config.logo_base64 = base64
      } else if (orgLogoUrl) {
        // Fetch org logo and convert to base64
        try {
          const token = localStorage.getItem('token')
          const logoRes = await fetch(orgLogoUrl, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          })
          if (logoRes.ok) {
            const blob = await logoRes.blob()
            const base64 = await new Promise((resolve) => {
              const reader = new FileReader()
              reader.onload = () => resolve(reader.result)
              reader.readAsDataURL(blob)
            })
            config.logo_base64 = base64
          }
        } catch { /* ignore logo fetch errors */ }
      }

      const result = await api.post('/reports/generate', config, { timeout: 120000 })
      setReportResult(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleDownloadPdf = async () => {
    setGenerating(true)
    setError(null)
    try {
      const config = {
        report_type: reportType,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        ...filterPayload(),
      }
      await api.downloadPost('/reports/generate/pdf', config, { timeout: 120000 })
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleDownloadPilotZip = async () => {
    setGenerating(true)
    setError(null)
    try {
      const config = {
        report_type: 'per_pilot_annual_review',
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        // This path always generates the per-pilot review, so ask the table
        // about that type rather than whatever is currently selected.
        pilot_ids: filtersFor('per_pilot_annual_review').pilots && selectedPilots.length > 0
          ? selectedPilots
          : undefined,
        vehicle_ids: undefined,
        include_non_unit: includeNonUnit || undefined,
      }
      await api.downloadPost('/reports/per-pilot/zip', config, { timeout: 0 })
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleExportCSV = (type) => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    api.download(`/export/${type}/csv?${params.toString()}`)
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config Panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-card border border-border rounded-xl p-5">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <FileBarChart className="w-5 h-5 text-primary" /> Report Builder
            </h2>

            <div className="space-y-4">
              {/* Report Type */}
              <div>
                <label htmlFor="report-type" className="block text-sm font-medium text-foreground mb-1">Report Type</label>
                <select id="report-type"
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value)}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                >
                  {REPORT_TYPES.map(rt => (
                    <option key={rt.value} value={rt.value}>{rt.label}</option>
                  ))}
                </select>
              </div>

              {/* Date Range */}
              <div>
                <label htmlFor="date-range" className="block text-sm font-medium text-foreground mb-1">Date Range</label>
                <div className="flex flex-wrap gap-1 mb-2">
                  <button type="button" onClick={() => applyDatePreset('last30')} className="px-2 py-0.5 text-xs bg-secondary hover:bg-accent border border-border rounded-full text-foreground">Last 30d</button>
                  <button type="button" onClick={() => applyDatePreset('last90')} className="px-2 py-0.5 text-xs bg-secondary hover:bg-accent border border-border rounded-full text-foreground">Last 90d</button>
                  <button type="button" onClick={() => applyDatePreset('ytd')} className="px-2 py-0.5 text-xs bg-secondary hover:bg-accent border border-border rounded-full text-foreground">YTD</button>
                  <button type="button" onClick={() => applyDatePreset('lastyear')} className="px-2 py-0.5 text-xs bg-secondary hover:bg-accent border border-border rounded-full text-foreground">Last year</button>
                  <button type="button" onClick={() => applyDatePreset('clear')} className="px-2 py-0.5 text-xs bg-secondary hover:bg-accent border border-border rounded-full text-muted-foreground">All time</button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input id="date-range"
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setDateFrom(n) } }}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) { e.target.value = n; setDateTo(n) } }}
                    className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>

                {/* Vendor and guest operators are excluded by default: their
                    sorties are real, but they are not the unit's own activity. */}
                <div className="flex items-start gap-2 mt-3">
                  <input
                    id="include-non-unit"
                    type="checkbox"
                    checked={includeNonUnit}
                    onChange={(e) => setIncludeNonUnit(e.target.checked)}
                    className="mt-0.5 rounded border-border"
                  />
                  <div>
                    <label htmlFor="include-non-unit" className="block text-sm text-foreground cursor-pointer">
                      Include non-unit flights
                    </label>
                    <p className="text-xs text-muted-foreground">
                      Adds vendor and guest operators, and any flight marked as not the unit&apos;s.
                    </p>
                  </div>
                </div>
              </div>

              {/* Pilot Select — hidden for reports whose generator ignores it */}
              {activeFilters.pilots && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-medium text-foreground">Pilots</p>
                  <div className="flex gap-2 text-xs">
                    <button type="button" onClick={selectAllPilots} className="text-primary hover:underline">Select all</button>
                    <button type="button" onClick={clearAllPilots} className="text-muted-foreground hover:underline">Clear</button>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-1">Leave empty to include all</p>
                <input
                  type="text"
                  value={pilotSearch}
                  onChange={(e) => setPilotSearch(e.target.value)}
                  placeholder="Search pilots..."
                  className="w-full mb-1 px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <div className="bg-secondary border border-border rounded-lg p-2 max-h-36 overflow-y-auto space-y-1">
                  {visiblePilots.length === 0 && <p className="text-xs text-muted-foreground px-1">{pilots.length === 0 ? 'No pilots available' : 'No matches'}</p>}
                  {visiblePilots.map(p => (
                    <label key={p.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-accent/30 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedPilots.includes(p.id)}
                        onChange={() => togglePilot(p.id)}
                        className="rounded border-border"
                      />
                      <span className="text-sm text-foreground">{p.full_name}</span>
                    </label>
                  ))}
                </div>
                {selectedPilots.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">{selectedPilots.length} selected</p>
                )}
              </div>
              )}

              {/* Vehicle Select — hidden for reports whose generator ignores it */}
              {activeFilters.vehicles && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-medium text-foreground">Vehicles</p>
                  <div className="flex gap-2 text-xs">
                    <button type="button" onClick={selectAllVehicles} className="text-primary hover:underline">Select all</button>
                    <button type="button" onClick={clearAllVehicles} className="text-muted-foreground hover:underline">Clear</button>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-1">Leave empty to include all</p>
                <input
                  type="text"
                  value={vehicleSearch}
                  onChange={(e) => setVehicleSearch(e.target.value)}
                  placeholder="Search vehicles..."
                  className="w-full mb-1 px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <div className="bg-secondary border border-border rounded-lg p-2 max-h-36 overflow-y-auto space-y-1">
                  {visibleVehicles.length === 0 && <p className="text-xs text-muted-foreground px-1">{vehicles.length === 0 ? 'No vehicles available' : 'No matches'}</p>}
                  {visibleVehicles.map(v => (
                    <label key={v.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-accent/30 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedVehicles.includes(v.id)}
                        onChange={() => toggleVehicle(v.id)}
                        className="rounded border-border"
                      />
                      <span className="text-sm text-foreground">{v.manufacturer} {v.model}{v.nickname ? ` (${v.nickname})` : ''}</span>
                    </label>
                  ))}
                </div>
                {selectedVehicles.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">{selectedVehicles.length} selected</p>
                )}
              </div>
              )}

              {/* Logo Upload */}
              <div>
                <p className="block text-sm font-medium text-foreground mb-1">Logo</p>
                {orgLogoUrl && !logoFile && (
                  <div className="flex items-center gap-2 mb-2">
                    <img src={orgLogoUrl} alt="Org logo" className="w-8 h-8 object-contain rounded border border-border" />
                    <span className="text-xs text-emerald-400">Using organization logo from settings</span>
                  </div>
                )}
                <label className="flex items-center gap-2 px-3 py-2 bg-secondary border border-border rounded-lg text-sm cursor-pointer hover:bg-accent/30 transition-colors">
                  <Upload className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground truncate">{logoFile ? logoFile.name : 'Override with custom logo...'}</span>
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => setLogoFile(e.target.files[0] || null)}
                  />
                </label>
              </div>

              {/* Generate Buttons */}
              <div className="flex gap-2">
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {generating ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Generating...</>
                  ) : (
                    <><FileBarChart className="w-4 h-4" /> Generate</>
                  )}
                </button>
                <button
                  onClick={handleDownloadPdf}
                  disabled={generating}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
                  title="Download PDF"
                >
                  <FileDown className="w-4 h-4" /> PDF
                </button>
              </div>
              {reportType === 'per_pilot_annual_review' && (
                <button
                  onClick={handleDownloadPilotZip}
                  disabled={generating}
                  className="w-full flex items-center justify-center gap-2 py-2 bg-secondary border border-border text-foreground rounded-lg text-xs font-medium hover:bg-accent disabled:opacity-50"
                  title="One PDF per pilot, bundled as a zip"
                >
                  <Download className="w-3.5 h-3.5" /> Download PDF Pack (one per pilot)
                </button>
              )}

              {/* Quick CSV Exports */}
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted-foreground mb-2">Quick CSV Exports</p>
                <div className="space-y-1">
                  <button onClick={() => handleExportCSV('flights')} className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent rounded-lg">
                    <Download className="w-3.5 h-3.5" /> Export Flights CSV
                  </button>
                  <button onClick={() => handleExportCSV('pilots')} className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent rounded-lg">
                    <Download className="w-3.5 h-3.5" /> Export Pilots CSV
                  </button>
                  <button onClick={() => handleExportCSV('vehicles')} className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent rounded-lg">
                    <Download className="w-3.5 h-3.5" /> Export Vehicles CSV
                  </button>
                  <button onClick={() => handleExportCSV('incidents')} className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent rounded-lg">
                    <Download className="w-3.5 h-3.5" /> Export Incidents CSV
                  </button>
                  <button onClick={() => handleExportCSV('flight-plans')} className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent rounded-lg">
                    <Download className="w-3.5 h-3.5" /> Export Flight Plans CSV
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Preview Panel */}
        <div className="lg:col-span-2">
          <div className="bg-card border border-border rounded-xl p-5 min-h-[400px]">
            <h2 className="text-lg font-semibold text-foreground mb-4">Report Preview</h2>

            {error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                {error}
              </div>
            )}

            {!reportResult && !error && !generating && (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <FileText className="w-12 h-12 text-muted-foreground mb-3 opacity-50" />
                <p className="text-muted-foreground text-sm">Configure your report settings and click Generate to see a preview.</p>
                <p className="text-muted-foreground text-xs mt-1">Select a report type, date range, and optional filters.</p>
              </div>
            )}

            {generating && (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="w-10 h-10 border-2 border-primary border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-muted-foreground text-sm">Generating report...</p>
              </div>
            )}

            {reportResult && !generating && (
              <div className="space-y-4">
                {/* Report Header */}
                <div className="border-b border-border pb-3">
                  <h3 className="text-foreground font-semibold">
                    {reportResult.title || REPORT_TYPES.find(r => r.value === reportType)?.label || 'Report'}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(() => {
                      if (dateFrom && dateTo) return `${dateFrom} to ${dateTo}`
                      if (dateFrom) return `From ${dateFrom}`
                      if (dateTo) return `Through ${dateTo}`
                      return 'All dates'
                    })()}
                    {selectedPilots.length > 0 ? ` | ${selectedPilots.length} pilots` : ''}
                    {selectedVehicles.length > 0 ? ` | ${selectedVehicles.length} vehicles` : ''}
                  </p>
                </div>

                {/* Summary Cards */}
                {reportResult.summary && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(reportResult.summary).map(([key, value]) => (
                      <div key={key} className="bg-muted/30 rounded-lg p-3">
                        <p className="text-xs text-muted-foreground capitalize">{key.replaceAll('_', ' ')}</p>
                        <p className="text-lg font-semibold text-foreground mt-0.5">{value}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Multi-section layout (Annual Unit Report, Per-Pilot Annual Review, etc.) */}
                {reportResult.sections && reportResult.sections.length > 0 && (
                  <div className="space-y-6">
                    {reportResult.sections.map((sec, idx) => (
                      <div key={`sec-${idx}-${sec.title}`} className="space-y-3">
                        <h4 className="text-foreground font-semibold text-base border-b border-border pb-1">{sec.title}</h4>
                        {sec.narrative && (
                          <p className="text-sm text-foreground leading-relaxed">{sec.narrative}</p>
                        )}
                        {sec.summary && (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                            {Object.entries(sec.summary).map(([k, v]) => (
                              <div key={k} className="bg-muted/30 rounded-lg p-2">
                                <p className="text-xs text-muted-foreground capitalize">{k.replaceAll('_', ' ')}</p>
                                <p className="text-base font-semibold text-foreground mt-0.5">{v}</p>
                              </div>
                            ))}
                          </div>
                        )}
                        {sec.rows && sec.rows.length > 0 && sec.columns && (
                          <div className="overflow-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-border bg-muted/30">
                                  {sec.columns.map((col) => (
                                    <th key={col} className="text-left px-3 py-1.5 font-medium text-muted-foreground text-xs capitalize">{col}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {sec.rows.map((row, ri) => (
                                  <tr key={`r-${ri}-${Object.values(row).join('|')}`} className="border-b border-border/50 hover:bg-accent/30">
                                    {Object.entries(row).map(([colKey, val]) => (
                                      <td key={colKey} className="px-3 py-1.5 text-foreground text-xs">{val == null ? '—' : String(val)}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        {sec.rows?.length === 0 && !sec.narrative && (
                          <p className="text-xs text-muted-foreground italic">No data for this section.</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Data Table - legacy single-section render */}
                {!reportResult.sections && reportResult.rows && reportResult.rows.length > 0 && (
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border bg-muted/30">
                          {(reportResult.columns || Object.keys(reportResult.rows[0])).map((col) => (
                            <th key={col} className="text-left px-4 py-2 font-medium text-muted-foreground text-xs capitalize">
                              {typeof col === 'string' ? col.replaceAll('_', ' ') : col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {reportResult.rows.map((row) => (
                          <tr key={Object.values(row).join('|')} className="border-b border-border/50 hover:bg-accent/30">
                            {Object.entries(row).map(([colKey, val]) => (
                              <td key={colKey} className="px-4 py-2 text-foreground text-xs">{val == null ? '—' : String(val)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {!reportResult.sections && reportResult.rows?.length === 0 && (
                  <p className="text-center py-8 text-muted-foreground">No data matches the selected filters</p>
                )}

                {/* Download Link */}
                {reportResult.download_url && (
                  <a
                    href={reportResult.download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90"
                  >
                    <Download className="w-4 h-4" /> Download Report
                  </a>
                )}

                {reportResult.message && (
                  <p className="text-sm text-foreground">{reportResult.message}</p>
                )}

                {/* Fallback: raw JSON if no recognized structure */}
                {!reportResult.summary && !reportResult.rows && !reportResult.download_url && !reportResult.message && !reportResult.title && (
                  <pre className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-4 overflow-auto max-h-64">
                    {JSON.stringify(reportResult, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
