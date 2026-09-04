import { cn } from '@/lib/utils'

const badgeVariants = {
  default: 'bg-primary text-primary-foreground',
  secondary: 'bg-secondary text-secondary-foreground',
  destructive: 'bg-destructive text-white shadow-[0_0_8px_rgba(239,68,68,0.2)]',
  outline: 'border border-border bg-transparent text-foreground',
  success: 'bg-green-500/15 text-green-600 dark:text-green-400 shadow-[0_0_8px_rgba(34,197,94,0.2)]',
  warning: 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400',
}

function Badge({ className, variant = 'default', children, ...props }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
        badgeVariants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}

export { Badge, badgeVariants }
