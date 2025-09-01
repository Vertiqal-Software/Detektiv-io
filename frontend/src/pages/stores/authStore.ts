// frontend/src/stores/authStore.ts
// Authentication state (Context + Hook) wired to our API client.
// - Persists session via tokens managed in '@/api/client'
// - Bootstraps on app load by calling AuthApi.me() if tokens exist
// - Exposes login(), logout(), setUser(), refreshProfile()
// - Listens for cross-tab storage changes to keep sessions in sync
//
// Note: main.tsx already wraps the app with <AuthProvider>  :contentReference[oaicite:0]{index=0}

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AuthApi, getAccessToken, getRefreshToken, clearTokens } from '@/api/client'

/** User shape as returned by the API (kept flexible for backend evolution) */
export type AuthUser = {
  id: number
  email: string
  name?: string
  is_admin?: boolean
  created_at?: string
  updated_at?: string
  // Add any future fields safely…
  [key: string]: any
}

type AuthContextValue = {
  /** Has the store completed its initial check (so routes can decide what to render) */
  initialized: boolean
  /** True while a login or bootstrap request is in-flight */
  loading: boolean
  /** Current signed-in user (null if signed out) */
  user: AuthUser | null
  /** Convenience boolean */
  isAuthenticated: boolean

  /** Perform login, store tokens (handled by AuthApi.login), fetch profile, return the user */
  login: (email: string, password: string) => Promise<AuthUser>
  /** Clears tokens, resets user, and clears relevant caches */
  logout: () => Promise<void>
  /** Manually refresh the profile from the API (useful after profile edits) */
  refreshProfile: () => Promise<AuthUser | null>
  /** Directly set user (e.g., after partial inline edits) */
  setUser: (u: AuthUser | null) => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

/** Provider wrapping the app (configured in src/main.tsx)  :contentReference[oaicite:1]{index=1} */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [initialized, setInitialized] = useState(false)
  const [loading, setLoading] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)

  const isAuthenticated = !!user

  /** Load the current profile if tokens exist; otherwise, mark as initialized */
  const bootstrap = useCallback(async () => {
    const hasAnyToken = !!getAccessToken() || !!getRefreshToken()
    if (!hasAnyToken) {
      setInitialized(true)
      return
    }

    setLoading(true)
    try {
      const me = await AuthApi.me()
      setUser(me || null)
    } catch {
      // Tokens might be invalid/expired; clear them to avoid loops
      clearTokens()
      setUser(null)
    } finally {
      setLoading(false)
      setInitialized(true)
    }
  }, [])

  /** Call on mount */
  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  /** Keep auth state in sync across tabs/windows */
  useEffect(() => {
    const STORAGE_KEY = 'detecktiv.auth' // matches the key in '@/api/client'
    const onStorage = () => {
      // If tokens have been removed in another tab, sign out here too
      const stillAuthed = !!getAccessToken() || !!getRefreshToken()
      if (!stillAuthed) setUser(null)
    }
    window.addEventListener('storage', (e) => {
      if (e.key === STORAGE_KEY) onStorage()
    })
    return () => window.removeEventListener('storage', onStorage as any)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true)
    try {
      // AuthApi.login stores tokens internally on success
      await AuthApi.login({ email: email.trim().toLowerCase(), password })
      // Always fetch a fresh profile post-login (more reliable than trusting login payload)
      const me = await AuthApi.me()
      setUser(me || null)
      return me as AuthUser
    } catch (err) {
      // Leave tokens as-is if the client didn't store them (login failed)
      setUser(null)
      throw err
    } finally {
      setLoading(false)
      if (!initialized) setInitialized(true)
    }
  }, [initialized])

  const logout = useCallback(async () => {
    // Clear tokens (client-side) and user state
    AuthApi.logout()
    setUser(null)
    // Clear React Query cache to avoid leaking protected data
    try {
      queryClient.clear()
    } catch {
      // non-fatal
    }
  }, [queryClient])

  const refreshProfile = useCallback(async () => {
    setLoading(true)
    try {
      const me = await AuthApi.me()
      setUser(me || null)
      return me || null
    } catch {
      // If this fails (e.g., 401), clear tokens and sign out
      clearTokens()
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const value: AuthContextValue = useMemo(
    () => ({
      initialized,
      loading,
      user,
      isAuthenticated,
      login,
      logout,
      refreshProfile,
      setUser,
    }),
    [initialized, loading, user, isAuthenticated, login, logout, refreshProfile]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Consumer hook for components/pages */
export function useAuthStore(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuthStore must be used within an AuthProvider')
  }
  return ctx
}
