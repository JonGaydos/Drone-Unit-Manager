/**
 * Generic CSV / XLSX import modal with column mapping. Used by the Mission
 * Log, Training Log, and Maintenance pages. The backend tells us the target
 * fields, auto-suggests a mapping, and applies it on commit.
 */
import { useState } from 'react'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { Loader2, Upload, X, AlertCircle, CheckCircle2 } from 'lucide-react'

const TITLES = {
  missions: 'Import Mission Logs',
  training: 'Import Training Logs',
  maintenance: 'Import Maintenance Records',
}

const DONT_MAP = '__none__'

export function ImportMappingModal({ entity, onClose, onComplete }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [mapping, setMapping] = useState({})
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const toast = useToast()

  const reset = () => { setFile(null); setPreview(null); setMapping({}); setResult(null) }

  const onPickFile = async (f) => {
    if (!f) return
    setBusy(true)
    setResult(null)
    const fd = new FormData()
    fd.append('file', f)
    try {
      const res = await api.upload(`/import/preview?entity=${entity}`, fd)
      setFile(f)
      setPreview(res)
      setMapping(res.suggested_mapping || {})
    } catch (err) {
      toast.error(err.message || 'Failed to read file')
      setFile(null); setPreview(null); setMapping({})
    } finally {
      setBusy(false)
    }
  }

  const setMap = (key, sourceHeader) => {
    setMapping(prev => {
      const next = { ...prev }
      if (!sourceHeader || sourceHeader === DONT_MAP) delete next[key]
      else next[key] = sourceHeader
      return next
    })
  }

  const commit = async () => {
    if (!file || !preview) return
    setBusy(true)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('mapping', JSON.stringify(mapping))
    try {
      const res = await api.upload(`/import/commit?entity=${entity}&mapping=${encodeURIComponent(JSON.stringify(mapping))}`, fd, {}, { timeout: 0 })
      setResult(res)
      if (res.created > 0) toast.success(`Imported ${res.created} record${res.created === 1 ? '' : 's'}`)
      else toast.info('No records imported')
    } catch (err) {
      toast.error(err.message || 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  const finish = () => {
    if (onComplete) onComplete()
    onClose()
  }

  const requiredMissing = (preview?.target_schema || []).filter(f => f.required && !mapping[f.key])
  const canCommit = preview && requiredMissing.length === 0 && !busy
  const rowWord = preview?.row_count === 1 ? 'row' : 'rows'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default" onClick={onClose} aria-label="Close" />
      <div className="relative bg-popover border border-border rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <h2 className="text-base font-semibold text-foreground">{TITLES[entity] || 'Import'}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Step 1: pick a file */}
          {!preview && !result && (
            <div className="text-sm text-muted-foreground space-y-3">
              <p>Upload a CSV or Excel file. The columns can be anything — you'll map them to app fields on the next step.</p>
              <label className="flex items-center gap-3 px-4 py-3 border border-dashed border-border rounded-lg cursor-pointer hover:bg-accent/40">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span>{busy ? 'Reading file…' : (file?.name || 'Choose a file…')}</span>
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(e) => onPickFile(e.target.files?.[0])}
                  disabled={busy}
                />
              </label>
            </div>
          )}

          {/* Step 2: mapping table */}
          {preview && !result && (
            <>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span><span className="font-medium text-foreground">{file?.name}</span> · {preview.row_count} row{preview.row_count === 1 ? '' : 's'} · {preview.headers.length} column{preview.headers.length === 1 ? '' : 's'}</span>
                <button onClick={reset} className="hover:text-foreground">Choose different file</button>
              </div>

              <div className="border border-border rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/40 text-muted-foreground">
                      <th className="text-left px-3 py-2 font-medium">App field</th>
                      <th className="text-left px-3 py-2 font-medium">Your column</th>
                      <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.target_schema.map(field => {
                      const chosen = mapping[field.key] || ''
                      const sample = chosen ? (preview.sample_rows[0]?.[chosen] ?? '') : ''
                      const missing = field.required && !chosen
                      return (
                        <tr key={field.key} className="border-t border-border/50">
                          <td className="px-3 py-2 align-top">
                            <div className="text-foreground">{field.label}</div>
                            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                              {field.required ? 'required' : 'optional'}{field.type ? ` · ${field.type}` : ''}
                            </div>
                            {missing && (
                              <div className="text-[10px] text-red-400 mt-0.5">Pick a column</div>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <select
                              value={chosen || DONT_MAP}
                              onChange={(e) => setMap(field.key, e.target.value)}
                              className={`w-full px-2 py-1.5 bg-secondary border rounded text-foreground text-sm ${
                                missing ? 'border-red-500/50' : 'border-border'
                              }`}
                            >
                              <option value={DONT_MAP}>— don't map —</option>
                              {preview.headers.map(h => (
                                <option key={h} value={h}>{h}</option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2 hidden sm:table-cell text-xs text-muted-foreground max-w-[180px] truncate" title={String(sample)}>
                            {String(sample || '—')}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Sample rows (first 3)</summary>
                <pre className="mt-2 p-2 bg-secondary/60 border border-border rounded overflow-x-auto text-[11px]">
                  {JSON.stringify(preview.sample_rows.slice(0, 3), null, 2)}
                </pre>
              </details>
            </>
          )}

          {/* Step 3: summary */}
          {result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-foreground">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <span className="font-medium">{result.created} record{result.created === 1 ? '' : 's'} created</span>
                {result.skipped > 0 && (
                  <span className="text-xs text-muted-foreground">· {result.skipped} skipped (missing date)</span>
                )}
              </div>
              {result.unmatched_names && Object.keys(result.unmatched_names).length > 0 && (
                <div className="border border-amber-500/30 bg-amber-500/5 rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-1 text-amber-400 font-medium mb-1">
                    <AlertCircle className="w-3.5 h-3.5" /> Members not in your roster (attributed to Unknown)
                  </div>
                  <ul className="text-muted-foreground">
                    {Object.entries(result.unmatched_names).sort((a, b) => b[1] - a[1]).map(([n, c]) => (
                      <li key={n}>{c}× {n}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.unmatched_drones && Object.keys(result.unmatched_drones).length > 0 && (
                <div className="border border-amber-500/30 bg-amber-500/5 rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-1 text-amber-400 font-medium mb-1">
                    <AlertCircle className="w-3.5 h-3.5" /> Drones not in your fleet (records skipped for these)
                  </div>
                  <ul className="text-muted-foreground">
                    {Object.entries(result.unmatched_drones).sort((a, b) => b[1] - a[1]).map(([n, c]) => (
                      <li key={n}>{c}× {n}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.errors?.length > 0 && (
                <div className="border border-red-500/30 bg-red-500/5 rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-1 text-red-400 font-medium mb-1">
                    <AlertCircle className="w-3.5 h-3.5" /> Errors
                  </div>
                  <ul className="text-muted-foreground">
                    {result.errors.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-card">
          {!result && (
            <>
              <button onClick={onClose} className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground">
                Cancel
              </button>
              {preview && (
                <button
                  onClick={commit}
                  disabled={!canCommit}
                  className="inline-flex items-center gap-2 px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  {busy ? 'Importing…' : `Import ${preview.row_count} ${rowWord}`}
                </button>
              )}
            </>
          )}
          {result && (
            <button onClick={finish} className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90">
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
