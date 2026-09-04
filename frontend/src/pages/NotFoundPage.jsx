import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="text-5xl font-bold text-foreground">404</p>
      <p className="mt-2 text-muted-foreground">That page doesn't exist.</p>
      <Link to="/" className="mt-4 text-primary hover:underline">Back to dashboard</Link>
    </div>
  )
}
