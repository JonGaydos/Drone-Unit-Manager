import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = {
  default: 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  destructive: 'bg-destructive text-white hover:bg-destructive/90 shadow-sm',
  outline: 'border border-border bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground',
  ghost: 'text-foreground hover:bg-accent hover:text-accent-foreground',
}

const buttonSizes = {
  sm: 'h-8 px-3 text-xs rounded-md',
  default: 'h-10 px-4 py-2 text-sm rounded-lg',
  lg: 'h-12 px-6 text-base rounded-lg',
  icon: 'h-10 w-10 rounded-lg',
}

const Button = forwardRef(
  ({ className, variant = 'default', size = 'default', disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(
          'inline-flex items-center justify-center gap-2 font-medium transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          'disabled:pointer-events-none disabled:opacity-50',
          'cursor-pointer',
          buttonVariants[variant],
          buttonSizes[size],
          className
        )}
        {...props}
      >
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'

export { Button, buttonVariants, buttonSizes }
