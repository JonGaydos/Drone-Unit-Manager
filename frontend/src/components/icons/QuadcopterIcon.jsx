/**
 * Custom SVG icon depicting a quadcopter drone.
 * Renders a top-down view with four arms, motor mounts, and propeller arcs.
 * @param {Object} props
 * @param {string} [props.className] - CSS classes for sizing and color.
 * @param {Object} [props...rest] - Additional SVG attributes passed through.
 */
export function QuadcopterIcon({ className, ...props }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Center body */}
      <rect x="10" y="10" width="4" height="4" rx="0.75" />
      {/* Arms */}
      <line x1="10" y1="11" x2="6" y2="7" />
      <line x1="14" y1="11" x2="18" y2="7" />
      <line x1="10" y1="13" x2="6" y2="17" />
      <line x1="14" y1="13" x2="18" y2="17" />
      {/* Motor mounts */}
      <circle cx="5.5" cy="6.5" r="1" />
      <circle cx="18.5" cy="6.5" r="1" />
      <circle cx="5.5" cy="17.5" r="1" />
      <circle cx="18.5" cy="17.5" r="1" />
      {/* Propeller arcs */}
      <path d="M2.5 6.5a3 3 0 0 1 6 0" />
      <path d="M15.5 6.5a3 3 0 0 1 6 0" />
      <path d="M2.5 17.5a3 3 0 0 0 6 0" />
      <path d="M15.5 17.5a3 3 0 0 0 6 0" />
    </svg>
  )
}
