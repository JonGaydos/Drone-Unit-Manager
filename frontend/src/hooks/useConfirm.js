/**
 * Custom hook for managing confirmation dialog state.
 */
import { useState, useCallback } from 'react'

/**
 * Hook for managing confirmation dialogs.
 * Returns a tuple of [ConfirmDialog props, requestConfirm trigger function].
 *
 * @example
 *   const [confirm, requestConfirm] = useConfirm()
 *   // In handler: requestConfirm({ title, message, onConfirm: () => doThing() })
 *   // In render: <ConfirmDialog {...confirm} />
 *
 * @returns {[Object, Function]} Props to spread on ConfirmDialog, and a function to open it.
 */
export function useConfirm() {
  const [state, setState] = useState({
    open: false,
    title: '',
    message: '',
    confirmLabel: 'Confirm',
    confirmVariant: 'danger',
    onConfirm: null,
  })

  const requestConfirm = useCallback(({ title, message, confirmLabel, confirmVariant, onConfirm }) => {
    setState({
      open: true,
      title: title || 'Confirm',
      message: message || 'Are you sure?',
      confirmLabel: confirmLabel || 'Confirm',
      confirmVariant: confirmVariant || 'danger',
      onConfirm,
    })
  }, [])

  const close = useCallback(() => {
    setState(prev => ({ ...prev, open: false }))
  }, [])

  const props = {
    open: state.open,
    onClose: close,
    onConfirm: state.onConfirm || (() => {}),
    title: state.title,
    message: state.message,
    confirmLabel: state.confirmLabel,
    confirmVariant: state.confirmVariant,
  }

  return [props, requestConfirm]
}
