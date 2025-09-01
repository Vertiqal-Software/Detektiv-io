// frontend/src/routes/RequireAuth.tsx
// Guard components for React Router v6+
// - <RequireAuth> protects routes, redirects to /login?redirect=<current>
// - Optional admin check via requireAdmin
// - <RequireGuest> redirects signed-in users away from auth pages
// - Uses the Auth store we created at '@/stores/authStore'
// - Shows a minimal branded loading state while auth initializes

import { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

type RequireAuthProps = {
  children?: ReactNode
  /** When true, only allow users with is_admin === true */
  requireAdmin?: boolean
  /** Optional: where to send non-admins; defaults to '/users' */
  fallbackForNonAdmin?: string
}

export function RequireAuth(props: RequireAuthProps) {
  const { children, requireAdmin = false, fallbackForNonAdmin = '/users' } = props
  const { initialized, loading, isAuthenticated, user } = useAuthStore()
  const location = useLocation()

  // While the auth store bootstraps (checking tokens → /me), show a friendly loader
  if (!initialized || loading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <div className="glass-card p-8 rounded-large text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Checking your session…</p>
        </div>
      </div>
    )
  }

  // If not signed in → redirect to login with redirect back to current URL
  if (!isAuthenticated) {
    const redirect = encodeURIComponent(
      `${location.pathname}${location.search || ''}${location.hash || ''}`
    )
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }

  // Optional admin gate
  if (requireAdmin && !user?.is_admin) {
    // You can replace this with a dedicated "403" page later if desired
    return <Navigate to={fallbackForNonAdmin} replace />
  }

  // Render children if provided, else render the nested route via <Outlet />
  return <>{children ?? <Outlet />}</>
}

type RequireGuestProps = {
  children?: ReactNode
  /** Where to send already-signed-in users who try to access guest-only pages */
  redirectTo?: string
}

/** Use on pages like /login to prevent signed-in users from seeing them */
export function RequireGuest({ children, redirectTo = '/users' }: RequireGuestProps) {
  const { initialized, loading, isAuthenticated } = useAuthStore()

  if (!initialized || loading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <div className="glass-card p-8 rounded-large text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Preparing…</p>
        </div>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />
  }

  return <>{children ?? <Outlet />}</>
}

export default RequireAuth
