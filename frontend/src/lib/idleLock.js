/** Minutes an admin can choose for the idle lock. */
export const IDLE_LOCK_MINUTES = [30, 60, 120, 240, 360, 480, 720]

/** Option text for an idle lock choice in minutes. */
export const idleLockLabel = (minutes) => {
  if (minutes < 60) return `${minutes} minutes`
  return minutes === 60 ? '1 hour' : `${minutes / 60} hours`
}
