// frontend/src/pages/Me/Profile.tsx
// Starting from your file; fixes + adds without removing features:
// - Align import path for auth store to your actual location (`src/pages/stores/authStore.ts`)
// - Keep all improvements: inline name edit, password change, safe typing/null checks

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { auth as AuthApi, users as UsersApi, type UserUpdate } from '@/api/client'
import { useAuthStore } from '@/pages/stores/authStore' // <-- aligned path to your stores folder
import {
  UserCircleIcon,
  EnvelopeIcon,
  CalendarDaysIcon,
  ShieldCheckIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  KeyIcon,
} from '@heroicons/react/24/outline'

export default function Profile() {
  const { user: currentUser, setUser } = useAuthStore()
  const queryClient = useQueryClient()

  const [isEditing, setIsEditing] = useState(false)
  const [formData, setFormData] = useState({
    full_name: currentUser?.full_name || '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Password editor state (additive feature)
  const [showPasswordEditor, setShowPasswordEditor] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ password: '', confirm: '' })
  const [passwordMsg, setPasswordMsg] = useState<string>('')

  // Fetch fresh profile data (fix: use AuthApi.me)
  const { data: user, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: AuthApi.me,
    initialData: currentUser,
  })

  // Update profile (name/flags) mutation
  const updateMutation = useMutation({
    mutationFn: (data: UserUpdate) => UsersApi.update(user!.id, data),
    onSuccess: (updatedUser) => {
      // Update the auth store with new user data
      setUser(updatedUser as any)
      // Refresh profile query
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      setIsEditing(false)
      setErrors({})
    },
    onError: (error: any) => {
      const message = error?.details?.detail || error?.details?.message || error?.message || 'Failed to update profile'
      setErrors({ general: String(message) })
    }
  })

  // Change password mutation (additive)
  const changePasswordMutation = useMutation({
    mutationFn: (payload: { password: string }) => UsersApi.update(user!.id, payload as UserUpdate),
    onSuccess: () => {
      setPasswordMsg('Password updated successfully.')
      setPasswordForm({ password: '', confirm: '' })
      setShowPasswordEditor(false)
      setErrors({})
    },
    onError: (error: any) => {
      const message = error?.details?.detail || error?.details?.message || error?.message || 'Failed to change password'
      setErrors({ password_general: String(message) })
    }
  })

  const handleEdit = () => {
    setFormData({ full_name: user?.full_name || '' })
    setIsEditing(true)
    setErrors({})
  }

  const handleCancel = () => {
    setFormData({ full_name: user?.full_name || '' })
    setIsEditing(false)
    setErrors({})
  }

  const handleSave = () => {
    setErrors({})

    if (!formData.full_name.trim()) {
      setErrors({ full_name: 'Name is required' })
      return
    }

    updateMutation.mutate({ full_name: formData.full_name.trim() })
  }

  const onChangePassword = () => {
    setPasswordMsg('')
    setErrors((e) => ({ ...e, password_general: '', password: '', confirm: '' }))

    const p = passwordForm.password
    const c = passwordForm.confirm

    if (!p || p.length < 8) {
      setErrors((prev) => ({ ...prev, password: 'Password must be at least 8 characters' }))
      return
    }
    if (p !== c) {
      setErrors((prev) => ({ ...prev, confirm: 'Passwords do not match' }))
      return
    }

    changePasswordMutation.mutate({ password: p })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Loading your profile...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center max-w-md">
          <UserCircleIcon className="mx-auto h-12 w-12 text-trust-silver mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">Profile not found</h3>
          <p className="text-trust-silver">Unable to load your profile information.</p>
        </div>
      </div>
    )
  }

  // Safe computed values
  const safeName = user.full_name || '—'
  const initials = (safeName?.[0] || user.email?.[0] || '?').toUpperCase()
  const isActive = user.is_active ?? true
  const roleLabel = user.role
    ? user.role.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase())
    : (user as any).is_admin
      ? 'Admin'
      : 'User'
  const createdAt = user.created_at ? new Date(user.created_at).toLocaleDateString('en-GB', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  }) : '—'
  const updatedAt = user.updated_at ? new Date(user.updated_at).toLocaleDateString('en-GB') : '—'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-white">My Profile</h1>
        <p className="mt-1 text-sm text-trust-silver">
          Manage your personal account information and preferences
        </p>
      </div>

      {/* Profile card */}
      <div className="glass-card rounded-large overflow-hidden max-w-3xl">
        {/* Profile header */}
        <div className="bg-gradient-primary p-8">
          <div className="flex items-center space-x-6">
            <div className="h-20 w-20 rounded-large bg-white/20 backdrop-blur-glass flex items-center justify-center">
              <span className="text-3xl font-bold text-white">
                {initials}
              </span>
            </div>
            <div className="flex-1">
              {isEditing ? (
                <div className="space-y-2">
                  <input
                    type="text"
                    value={formData.full_name}
                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    className="bg-white/20 backdrop-blur-glass border border-white/30 text-white rounded-medium px-3 py-2 w-full max-w-xs focus:ring-2 focus:ring-white/50 focus:border-white/50"
                    placeholder="Your full name"
                    disabled={updateMutation.isPending}
                  />
                  {errors.full_name && (
                    <p className="text-sm text-red-200">{errors.full_name}</p>
                  )}
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={handleSave}
                      disabled={updateMutation.isPending}
                      className="inline-flex items-center px-3 py-1 bg-white/20 hover:bg-white/30 text-white rounded-medium text-sm transition-colors duration-200 disabled:opacity-50"
                    >
                      {updateMutation.isPending ? (
                        <div className="animate-spin rounded-full h-3 w-3 border-b border-white mr-1"></div>
                      ) : (
                        <CheckIcon className="h-3 w-3 mr-1" />
                      )}
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={handleCancel}
                      disabled={updateMutation.isPending}
                      className="inline-flex items-center px-3 py-1 text-white/70 hover:text-white rounded-medium text-sm transition-colors duration-200"
                    >
                      <XMarkIcon className="h-3 w-3 mr-1" />
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-center space-x-3">
                    <h2 className="text-2xl font-semibold text-white">{safeName}</h2>
                    <button
                      onClick={handleEdit}
                      className="p-1 text-white/70 hover:text-white transition-colors duration-200"
                      title="Edit name"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="text-purple-100 mt-1">{user.email}</p>
                  <div className="flex items-center space-x-4 mt-3">
                    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${
                      isActive
                        ? 'bg-success-green/20 text-success-green'
                        : 'bg-gray-600/20 text-gray-300'
                    }`}>
                      {isActive ? 'Active' : 'Inactive'}
                    </span>
                    <span className="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-sm font-medium text-white">
                      {roleLabel}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Profile details */}
        <div className="p-8 grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* Account Information */}
          <div className="space-y-6">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-3">
              Account Information
            </h3>

            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <EnvelopeIcon className="h-5 w-5 text-detecktiv-purple mt-1" />
                <div>
                  <p className="text-sm font-medium text-white">Email Address</p>
                  <p className="text-sm text-trust-silver">{user.email}</p>
                  <p className="text-xs text-trust-silver mt-1">
                    Used for sign-in and notifications
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <UserCircleIcon className="h-5 w-5 text-detecktiv-purple mt-1" />
                <div>
                  <p className="text-sm font-medium text-white">Display Name</p>
                  <p className="text-sm text-trust-silver">{safeName}</p>
                  <p className="text-xs text-trust-silver mt-1">
                    How your name appears throughout the platform
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <ShieldCheckIcon className="h-5 w-5 text-detecktiv-purple mt-1" />
                <div>
                  <p className="text-sm font-medium text-white">Role & Permissions</p>
                  <p className="text-sm text-trust-silver capitalize">
                    {roleLabel}
                  </p>
                  <p className="text-xs text-trust-silver mt-1">
                    Determines your access level and capabilities
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Activity & History */}
          <div className="space-y-6">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-3">
              Activity & History
            </h3>

            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-1" />
                <div>
                  <p className="text-sm font-medium text-white">Account Created</p>
                  <p className="text-sm text-trust-silver">
                    {createdAt}
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-1" />
                <div>
                  <p className="text-sm font-medium text-white">Last Profile Update</p>
                  <p className="text-sm text-trust-silver">
                    {updatedAt}
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="h-5 w-5 flex items-center justify-center mt-1">
                  <div className={`h-3 w-3 rounded-full ${isActive ? 'bg-success-green' : 'bg-gray-500'}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Account Status</p>
                  <p className="text-sm text-trust-silver">
                    {isActive ? 'Active and in good standing' : 'Account suspended'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Error display */}
        {errors.general && (
          <div className="border-t border-gray-700 p-6">
            <div className="bg-critical-red/10 border border-critical-red/20 rounded-medium p-4">
              <p className="text-sm text-critical-red">{errors.general}</p>
            </div>
          </div>
        )}

        {/* Footer information */}
        <div className="border-t border-gray-700 bg-gray-800/30 px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-white">detecktiv.io Account</p>
              <p className="text-xs text-trust-silver">
                Part of VDI's customer intelligence platform
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-trust-silver">User ID: {user.id}</p>
              <p className="text-xs text-trust-silver">
                For support, contact your system administrator
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick actions card (kept) + inline password editor (added) */}
      <div className="glass-card p-6 rounded-large max-w-md">
        <h3 className="text-lg font-medium text-white mb-4">Quick Actions</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between py-2">
            <span className="text-sm text-trust-silver">Change Password</span>
            <button
              className="text-sm text-detecktiv-purple hover:text-purple-400 transition-colors duration-200"
              onClick={() => {
                setPasswordMsg('')
                setErrors((e) => ({ ...e, password_general: '', password: '', confirm: '' }))
                setShowPasswordEditor((v) => !v)
              }}
            >
              {showPasswordEditor ? 'Close' : 'Update'}
            </button>
          </div>

          {showPasswordEditor && (
            <div className="rounded-medium border border-gray-700 p-3 space-y-3">
              {errors.password_general && (
                <div className="bg-critical-red/10 border border-critical-red/20 rounded-medium p-2">
                  <p className="text-xs text-critical-red">{errors.password_general}</p>
                </div>
              )}
              {passwordMsg && (
                <div className="bg-success-green/10 border border-success-green/20 rounded-medium p-2">
                  <p className="text-xs text-success-green">{passwordMsg}</p>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-white mb-1">New Password *</label>
                <div className="relative">
                  <KeyIcon className="h-4 w-4 text-trust-silver absolute left-3 top-2.5" />
                  <input
                    type="password"
                    value={passwordForm.password}
                    onChange={(e) => {
                      setPasswordMsg('')
                      setPasswordForm((prev) => ({ ...prev, password: e.target.value }))
                      if (errors.password) setErrors((prev) => ({ ...prev, password: '' }))
                    }}
                    className={`input-field w-full pl-9 ${errors.password ? 'border-critical-red focus:ring-critical-red' : ''}`}
                    placeholder="Minimum 8 characters"
                    disabled={changePasswordMutation.isPending}
                    autoComplete="new-password"
                  />
                </div>
                {errors.password && <p className="mt-1 text-xs text-critical-red">{errors.password}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-white mb-1">Confirm Password *</label>
                <div className="relative">
                  <KeyIcon className="h-4 w-4 text-trust-silver absolute left-3 top-2.5" />
                  <input
                    type="password"
                    value={passwordForm.confirm}
                    onChange={(e) => {
                      setPasswordMsg('')
                      setPasswordForm((prev) => ({ ...prev, confirm: e.target.value }))
                      if (errors.confirm) setErrors((prev) => ({ ...prev, confirm: '' }))
                    }}
                    className={`input-field w-full pl-9 ${errors.confirm ? 'border-critical-red focus:ring-critical-red' : ''}`}
                    placeholder="Re-enter the new password"
                    disabled={changePasswordMutation.isPending}
                    autoComplete="new-password"
                  />
                </div>
                {errors.confirm && <p className="mt-1 text-xs text-critical-red">{errors.confirm}</p>}
              </div>

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setPasswordForm({ password: '', confirm: '' })
                    setShowPasswordEditor(false)
                    setPasswordMsg('')
                    setErrors((e) => ({ ...e, password_general: '', password: '', confirm: '' }))
                  }}
                  className="btn-secondary"
                  disabled={changePasswordMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={onChangePassword}
                  className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  disabled={changePasswordMutation.isPending}
                >
                  {changePasswordMutation.isPending ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>Saving…</span>
                    </>
                  ) : (
                    <span>Save Password</span>
                  )}
                </button>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between py-2">
            <span className="text-sm text-trust-silver">Security Settings</span>
            <button className="text-sm text-detecktiv-purple hover:text-purple-400 transition-colors duration-200">
              Manage
            </button>
          </div>
          <div className="flex items-center justify-between py-2">
            <span className="text-sm text-trust-silver">Download Data</span>
            <button className="text-sm text-detecktiv-purple hover:text-purple-400 transition-colors duration-200">
              Export
            </button>
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-gray-700">
          <p className="text-xs text-trust-silver">
            <strong>Note:</strong> Some account changes require administrator approval.
            Contact your system administrator for role changes or account deactivation.
          </p>
        </div>
      </div>
    </div>
  )
}
