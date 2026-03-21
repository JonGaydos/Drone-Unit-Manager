import { Construction } from 'lucide-react'

export default function PlaceholderPage({ title = 'Coming Soon' }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <Construction className="w-12 h-12 text-muted-foreground mb-4" />
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <p className="text-sm text-muted-foreground mt-1">This section will be available in a future phase.</p>
    </div>
  )
}
