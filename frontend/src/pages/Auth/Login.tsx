// frontend/src/pages/Auth/Login.tsx
// Fully-functional login page wired to AuthApi.login from '@/api/client'.
//
// Features:
// - Validates email & password with clear inline errors
// - Calls AuthApi.login; tokens are stored by the client on success
// - Shows server error messages (e.g., 401 invalid credentials)
// - Disable UI while pending; Enter-to-submit supported
// - Optional redirect via ?redirect=/path (defaults to /users)
//
// Styling assumes your Tailwind utility classes from other pages:
// - glass-card, input-field, btn-primary, btn-secondary, text-trust-silver, bg-gradient-primary, etc.

import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AuthApi } from '@/api/client'
import {
  EnvelopeIcon,
  LockClosedIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  const searchParams = new URLSearchParams(location.search)
  const redirectTo = searchParams.get('redirect') || '/users'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const loginMutation = useMutation({
    mutationFn: () => AuthApi.login({ email: email.trim().toLowerCase(), password }),
    onSuccess: async () => {
      // Optional: warm up "me" & invalidate any stale queries
      try {
        await AuthApi.me()
        queryClient.invalidateQueries({ queryKey: ['users'] })
      } catch {
        // Non-fatal: if /me fails for any reason, still continue navigation
      }
      navigate(redirectTo)
    },
    onError: (err: any) => {
      const message =
        err?.details?.detail ||
        err?.details?.message ||
        err?.message ||
        'Login failed. Please check your credentials.'
      // Heuristic: surface "invalid" as a credential error on password/email
      const lower = String(message).toLowerCase()
      if (lower.includes('invalid') || lower.includes('unauthorized') || err?.status === 401) {
        setErrors({ password: 'Invalid email or password' })
      } else {
        setErrors({ general: String(message) })
      }
    },
  })

  const validate = () => {
    const next: Record<string, string> = {}
    const cleanEmail = email.trim().toLowerCase()

    if (!cleanEmail) {
      next.email = 'Email is required'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      next.email = 'Please enter a valid email address'
    }

    if (!password) {
      next.password = 'Password is required'
    }

    setErrors(next)
    return Object.keys(next).length === 0
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    loginMutation.mutate()
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header / Branding */}
        <div className="text-center mb-6">
          <h1 className="text-3xl font-semibold text-white">Sign in</h1>
          <p className="mt-2 text-sm text-trust-silver">Welcome back to detecktiv.io</p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-large p-6">
          {/* General error */}
          {errors.general && (
            <div className="mb-4 bg-critical-red/10 border border-critical-red/20 rounded-medium p-3">
              <p className="text-sm text-critical-red">{errors.general}</p>
            </div>
          )}

          <form onSubmit={onSubmit} noValidate className="space-y-5">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-white mb-2">
                Email address
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <EnvelopeIcon className="h-5 w-5 text-trust-silver" />
                </div>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value.replace(/\s+/g, ''))
                    if (errors.email) setErrors((prev) => ({ ...prev, email: '' }))
                  }}
                  disabled={loginMutation.isPending}
                  className={`input-field w-full pl-10 ${
                    errors.email ? 'border-critical-red focus:ring-critical-red' : ''
                  }`}
                  placeholder="you@company.co.uk"
                />
              </div>
              {errors.email && <p className="mt-1 text-sm text-critical-red">{errors.email}</p>}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-white mb-2">
                Password
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <LockClosedIcon className="h-5 w-5 text-trust-silver" />
                </div>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (errors.password) setErrors((prev) => ({ ...prev, password: '' }))
                  }}
                  disabled={loginMutation.isPending}
                  className={`input-field w-full pl-10 pr-10 ${
                    errors.password ? 'border-critical-red focus:ring-critical-red' : ''
                  }`}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  tabIndex={-1}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-trust-silver hover:text-white transition"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                </button>
              </div>
              {errors.password && <p className="mt-1 text-sm text-critical-red">{errors.password}</p>}
            </div>

            {/* Submit */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={loginMutation.isPending}
                className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
              >
                {loginMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    <span>Signing in...</span>
                  </>
                ) : (
                  <span>Sign in</span>
                )}
              </button>
            </div>
          </form>

          {/* Footer links */}
          <div className="mt-6 text-center">
            <p className="text-sm text-trust-silver">
              Forgot your password?{' '}
              <span className="text-detecktiv-purple hover:text-purple-400 cursor-not-allowed">
                Contact your admin
              </span>
            </p>
          </div>
        </div>

        {/* Back link (optional) */}
        <div className="mt-4 text-center">
          <Link to="/" className="text-sm text-trust-silver hover:text-white">
            ← Back to home
          </Link>
        </div>
      </div>
    </div>
  )
}
