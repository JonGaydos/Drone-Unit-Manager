import { useAuth } from '@/contexts/AuthContext'

// The app's ProtectedRoute renders a page only once auth has settled, so a page
// always mounts knowing its permissions. Tests mount the same way.
export function AuthSettled({ children }) {
  const { loading } = useAuth()
  return loading ? null : children
}
