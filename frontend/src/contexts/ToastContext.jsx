import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { X, CheckCircle, AlertTriangle, Info, XCircle } from 'lucide-react'

const ToastContext = createContext()

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timeoutRef = useRef({})

  useEffect(() => {
    return () => {
      Object.values(timeoutRef.current).forEach(clearTimeout)
    }
  }, [])

  const addToast = useCallback((message, type = 'info', duration = 5000) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    if (duration > 0) {
      timeoutRef.current[id] = setTimeout(() => removeToast(id), duration)
    }
  }, [])

  const removeToast = useCallback((id) => {
    clearTimeout(timeoutRef.current[id])
    delete timeoutRef.current[id]
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = {
    success: (msg) => addToast(msg, 'success'),
    error: (msg) => addToast(msg, 'error'),
    warning: (msg) => addToast(msg, 'warning'),
    info: (msg) => addToast(msg, 'info'),
  }

  const icons = { success: CheckCircle, error: XCircle, warning: AlertTriangle, info: Info }
  const colors = {
    success: 'bg-green-500/10 border-green-500/30 text-green-400',
    error: 'bg-red-500/10 border-red-500/30 text-red-400',
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
    info: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
        {toasts.map(t => {
          const Icon = icons[t.type]
          return (
            <div key={t.id} className={`flex items-start gap-3 px-4 py-3 rounded-lg border ${colors[t.type]} shadow-lg animate-in slide-in-from-right`}>
              <Icon className="w-5 h-5 shrink-0 mt-0.5" />
              <p className="text-sm flex-1">{t.message}</p>
              <button onClick={() => removeToast(t.id)} className="shrink-0" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
