// frontend/src/pages/stores/authStore.ts
// Authentication state (Context + Hook) wired to our API client.
// - Persists session via tokens managed in '@/api/client'
// - Bootstraps on app load by calling AuthApi.me() if tokens exist
// - Exposes login(), logout(), setUser(), refreshProfile()
// - Listens for cross-tab storage changes to keep sessions in sync
//
// Note: We’ll add <AuthProvider> around <App /> in main.tsx after you approve that change.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  auth as AuthApi,              // matches our client.ts named export
  getAccessToken,
  getRefreshToken,
  clearTokens,
} from '@/api/client'

/** User shape as returned by the API (kept flexible for backend evolution) */
export type AuthUser = {
  id: number
  email: string
  full_name?: string | null
  role?: string | null
  is_active?: boolean
  is_superuser?: boolean
  tenant_id?: number | null
  created_at?: string
  updated_at?: string
  // Allow additional fields without breaking:
  [key: string]: any
}

type AuthContextValue = {
  /** Has the store completed its initial check (so routes can decide what to render) */
  initialized: boolean
  /** True while a login/profile request is in-flight */
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

/** Provider wrapping the app */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [initialized, setInitialized] = useState(false)
  const [loading, setLoading] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)

  const isAuthenticated = !!user

  /**
   * Bootstrap: if tokens exist, fetch profile; otherwise mark as initialized.
   * We don't throw here—store should settle gracefully even on invalid tokens.
   */
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

  useEffect(() => {
    // Initial load
    bootstrap()
  }, [bootstrap])

  /**
   * Cross-tab/session sync: watch for our token storage key changes.
   * client.ts uses STORAGE_KEY = 'detecktiv.tokens'
   */
  useEffect(() => {
    const STORAGE_KEY = 'detecktiv.tokens'
    const onStorage = (e: StorageEvent) => {
      if (e.key && e.key !== STORAGE_KEY) return
      // If tokens were removed in another tab, reflect sign-out here too.
      const stillAuthed = !!getAccessToken() || !!getRefreshToken()
      if (!stillAuthed) {
        setUser(null)
        // also clear caches for safety
        queryClient.clear()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [queryClient])

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true)
    try {
      // AuthApi.login stores tokens internally on success
      await AuthApi.login({ email: email.trim().toLowerCase(), password })
      // Always fetch a fresh profile post-login (more reliable than trusting login payload)
      const me = await AuthApi.me()
      setUser(me || null)
      // Warm up common queries
      queryClient.invalidateQueries({ queryKey: ['users'] })
      return (me || null) as AuthUser
    } catch (err) {
      // Leave tokens as-is if the client didn't store them (login failed)
      setUser(null)
      throw err
    } finally {
      setLoading(false)
      if (!initialized) setInitialized(true)
    }
  }, [initialized, queryClient])

  const logout = useCallback(async () => {
    // In this simple client, logout is client-side only: clear tokens & caches.
    // (Server-side revocation exists via token_version increment when you implement it.)
    setLoading(true)
    try {
      clearTokens()
      setUser(null)
      // Clear cached queries to avoid leaking previous user's data
      await queryClient.clear()
    } finally {
      setLoading(false)
      setInitialized(true)
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
