import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

const Input = forwardRef(({ className, label, id, type = 'text', ...props }, ref) => {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-foreground"
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        type={type}
        className={cn(
          'flex h-10 w-full rounded-lg border border-border bg-secondary px-3 py-2 text-sm text-foreground',
          'placeholder:text-muted-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'transition-colors',
          className
        )}
        {...props}
      />
    </div>
  )
})

Input.displayName = 'Input'

export { Input }
