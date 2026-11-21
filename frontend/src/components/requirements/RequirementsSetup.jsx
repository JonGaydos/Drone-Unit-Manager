/**
 * The Setup tab of the Compliance page, for requirements.manage only:
 * requirement templates and the requirement settings (grace days, fiscal
 * year start, emails). Starting a requirement from a template opens the
 * builder on the Flight Requirements tab.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import { useToast } from '@/contexts/ToastContext'
import { useConfirm } from '@/hooks/useConfirm'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import RequirementSettingsCard from './RequirementSettingsCard'
import { TemplatesCard } from './TemplatesCard'

export default function RequirementsSetup() {
  const toast = useToast()
  const navigate = useNavigate()
  const [confirmProps, requestConfirm] = useConfirm()
  const [templates, setTemplates] = useState([])
  const [settings, setSettings] = useState(null)

  const loadTemplates = useCallback(() => api.get('/requirements/templates')
    .then(setTemplates)
    .catch(err => toast.error(err.message)), [toast])

  useEffect(() => {
    loadTemplates()
    api.get('/requirements/settings').then(setSettings).catch(err => toast.error(err.message))
  }, [loadTemplates, toast])

  const startFromTemplate = (template) => navigate('/compliance?tab=requirements', { state: { template } })

  const renameTemplate = (template, name) => api.patch(`/requirements/templates/${template.id}`, { name })
    .then(() => { loadTemplates(); return true })
    .catch(err => { toast.error(err.message); return false })

  const removeTemplate = (template) => requestConfirm({
    title: 'Delete template',
    message: `Delete the template "${template.name}"? Requirements made from it do not change.`,
    confirmLabel: 'Delete',
    onConfirm: () => api.delete(`/requirements/templates/${template.id}`)
      .then(loadTemplates)
      .catch(err => toast.error(err.message)),
  })

  const saveSettings = (next) => api.put('/requirements/settings', next)
    .then(saved => { setSettings(saved); toast.success('Requirement settings saved'); return true })
    .catch(err => { toast.error(err.message); return false })

  return (
    <div className="space-y-6 max-w-3xl">
      <TemplatesCard templates={templates} onUse={startFromTemplate} onRename={renameTemplate} onDelete={removeTemplate} />
      <RequirementSettingsCard settings={settings} onSave={saveSettings} />
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
