import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export function formatDuration(seconds) {
  if (!seconds) return '—'
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hrs > 0) return `${hrs}h ${mins}m`
  return `${mins}m ${secs}s`
}

export function formatHours(seconds) {
  if (!seconds) return '0.0'
  return (seconds / 3600).toFixed(1)
}

export function metersToFeet(m) {
  if (m == null) return null
  return Math.round(m * 3.28084)
}

export function mpsToMph(mps) {
  if (mps == null) return null
  return Math.round(mps * 2.23694 * 10) / 10
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
