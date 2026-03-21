import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export function formatDuration(seconds) {
  if (!seconds) return '0m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function formatHours(seconds) {
  if (!seconds) return '0.0'
  return (seconds / 3600).toFixed(1)
}

export function normalizeDateValue(value) {
  if (!value) return value
  // Handle dates like "0026-12-12" → "2026-12-12"
  const match = value.match(/^00(\d{2})-/)
  if (match) {
    const yr = parseInt(match[1])
    const century = yr >= 50 ? '19' : '20'
    return value.replace(/^00\d{2}/, century + match[1])
  }
  return value
}
