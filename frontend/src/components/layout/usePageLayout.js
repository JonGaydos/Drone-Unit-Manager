import { useCallback, useEffect, useState } from 'react'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'

/** A stored unit default layout, or null when unset or unreadable. */
function parseLayout(text) {
  if (!text) return null
  try {
    const layout = JSON.parse(text)
    return Array.isArray(layout?.order) ? layout : null
  } catch {
    return null
  }
}

/**
 * The ArrangeableGrid props for one page: the signed-in user's own layout
 * (account field `field`), the unit default (setting `settingKey`) and the
 * handlers that save them. A failed save shows a toast and rejects, so the
 * grid stays in edit mode.
 */
export function usePageLayout(field, settingKey) {
  const { user, isAdmin, updateUser } = useAuth()
  const toast = useToast()
  const [defaultLayout, setDefaultLayout] = useState(null)

  useEffect(() => {
    let alive = true
    api.get(`/settings/${settingKey}`)
      .then(row => { if (alive) setDefaultLayout(parseLayout(row?.value)) })
      .catch(() => { /* no default: tiles keep their built-in order */ })
    return () => { alive = false }
  }, [settingKey])

  const onSave = useCallback(async (layout) => {
    try {
      const saved = await api.patch('/auth/me', { [field]: layout })
      updateUser({ [field]: saved?.[field] ?? null })
      toast.success('Layout saved')
    } catch (err) {
      toast.error(err.message)
      throw err
    }
  }, [field, updateUser, toast])

  const onSaveDefault = useCallback(async (layout) => {
    try {
      await api.put('/settings', { key: settingKey, value: JSON.stringify(layout) })
      setDefaultLayout(layout)
      // An admin with a layout of their own keeps seeing it, so say why the page did not change.
      toast.success(user?.[field]
        ? 'Saved as the unit default. Your own layout still applies to you; use Reset to default to switch to it.'
        : 'Saved as the unit default')
    } catch (err) {
      toast.error(err.message)
      throw err
    }
  }, [settingKey, toast, user, field])

  return { layout: user?.[field] ?? null, defaultLayout, onSave, onSaveDefault, canSetDefault: isAdmin }
}
