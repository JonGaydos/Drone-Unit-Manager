import { cn } from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

const trendConfig = {
  up: {
    icon: TrendingUp,
    color: 'text-green-600 dark:text-green-400',
  },
  down: {
    icon: TrendingDown,
    color: 'text-red-600 dark:text-red-400',
  },
  neutral: {
    icon: Minus,
    color: 'text-muted-foreground',
  },
}

function StatCard({ title, value, subtitle, icon: Icon, trend, className }) {
  const trendInfo = trend ? trendConfig[trend] : null
  const TrendIcon = trendInfo?.icon

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-6 shadow-sm',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-muted-foreground">{title}</span>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-foreground">
              {value}
            </span>
            {TrendIcon && (
              <TrendIcon className={cn('h-4 w-4', trendInfo.color)} />
            )}
          </div>
          {subtitle && (
            <span className={cn('text-sm', trendInfo ? trendInfo.color : 'text-muted-foreground')}>
              {subtitle}
            </span>
          )}
        </div>
        {Icon && (
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
      </div>
    </div>
  )
}

export { StatCard }
