// frontend/src/pages/Users/UsersEdit.tsx
// Start point: your current file, strengthened without removing features.  :contentReference[oaicite:0]{index=0}
//
// Improvements:
// - Fix API import to use alias (@/api/client)
// - Robust typing (ViewUser + UserUpdate), null-safety for dates/fields
// - Keep existing fields (name, role, is_active) and add optional password change
// - Map role → is_admin for backend while preserving your role UI
// - Better error handling & disabled states during save
// - Keep layout/sections you already had

import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UsersApi, type User as ApiUser, type UserUpdate } from '@/api/client'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'

type ViewUser = ApiUser & {
  role?: string
  created_at?: string
  updated_at?: string
  is_active?: boolean
}

type FormData = {
  name: string
  role: string
  is_active: boolean
  password?: string
  confirm_password?: string
}

export default function UsersEdit() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const userId = id ? parseInt(id, 10) : null

  const [formData, setFormData] = useState<FormData>({
    name: '',
    role: 'user',
    is_active: true,
    password: '',
    confirm_password: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Fetch user details
  const { data: user, isLoading, error } = useQuery<ViewUser>({
    queryKey: ['user', userId],
    queryFn: () => UsersApi.get(userId!),
    enabled: !!userId,
  })

  // Update form data when user is loaded
  useEffect(() => {
    if (user) {
      setFormData((prev) => ({
        ...prev,
        name: user.name || '',
        // Prefer explicit admin → 'admin'; otherwise keep server-provided role or default 'user'
        role: user.is_admin ? 'admin' : (user.role || 'user'),
        is_active: user.is_active !== false,
      }))
    }
  }, [user])

  // Prepare PATCH -> only the fields backend expects
  const toPatch = (data: FormData): UserUpdate => {
    const patch: UserUpdate = {
      name: data.name?.trim(),
      is_active: data.is_active,
      is_admin: data.role === 'admin', // Map your UI 'role' to backend permission
    }
    if (data.password && data.password.trim().length > 0) {
      patch.password = data.password.trim()
    }
    return patch
  }

  // Update user mutation
  const updateMutation = useMutation({
    mutationFn: (patch: UserUpdate) => UsersApi.update(userId!, patch),
    onSuccess: (updatedUser) => {
      // Refresh queries
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['user', userId] })
      // Navigate back to user details
      navigate(`/users/${updatedUser.id}`)
    },
    onError: (err: any) => {
      // Try to surface server-provided detail/message when available
      const message =
        err?.details?.detail ||
        err?.details?.message ||
        err?.message ||
        'Failed to save changes.'
      setErrors({ general: String(message) })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setErrors({})

    // Basic validation
    const newErrors: Record<string, string> = {}

    if (!formData.name || !formData.name.trim()) {
      newErrors['name'] = 'Name is required'
    }

    if (formData.password && formData.password.length > 0) {
      if (formData.password.length < 8) {
        newErrors['password'] = 'Password must be at least 8 characters'
      }
      if (formData.password !== formData.confirm_password) {
        newErrors['confirm_password'] = 'Passwords do not match'
      }
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    updateMutation.mutate(toPatch(formData))
  }

  const handleInputChange = (field: keyof FormData, value: string | boolean) => {
    setFormData((prev) => ({ ...prev, [field]: value } as FormData))
    // Clear error when user starts typing/toggling that field
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: '' }))
    }
  }

  const safeCreated =
    user?.created_at ? new Date(user.created_at).toLocaleDateString('en-GB') : '—'
  const safeUpdated =
    user?.updated_at ? new Date(user.updated_at).toLocaleDateString('en-GB') : '—'

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Loading user details...</p>
        </div>
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center max-w-md">
          <h3 className="text-lg font-medium text-white mb-2">User not found</h3>
          <p className="text-trust-silver mb-4">
            The user you're trying to edit doesn't exist or you don't have permission.
          </p>
          <Link to="/users" className="btn-primary">
            Back to Users
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-4">
        <Link
          to={`/users/${user.id}`}
          className="p-2 text-trust-silver hover:text-white transition-colors duration-200 rounded-medium hover:bg-gray-800"
        >
          <ArrowLeftIcon className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-white">Edit User</h1>
          <p className="mt-1 text-sm text-trust-silver">
            Update {(user.name && user.name.trim()) || user.email || `user #${user.id}`}'s account information
          </p>
        </div>
      </div>

      {/* Edit form */}
      <div className="glass-card p-8 rounded-large max-w-2xl">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* General error */}
          {errors.general && (
            <div className="bg-critical-red/10 border border-critical-red/20 rounded-medium p-4">
              <p className="text-sm text-critical-red">{errors.general}</p>
            </div>
          )}

          {/* Current email (read-only) */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">Email Address</label>
            <div className="input-field bg-gray-700 text-trust-silver cursor-not-allowed">{user.email}</div>
            <p className="mt-1 text-sm text-trust-silver">
              Email addresses cannot be changed. Contact system administrator if needed.
            </p>
          </div>

          {/* Name field */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-white mb-2">
              Full Name *
            </label>
            <input
              id="name"
              type="text"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className={`input-field w-full ${errors.name ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="John Smith"
              disabled={updateMutation.isPending}
            />
            {errors.name && <p className="mt-1 text-sm text-critical-red">{errors.name}</p>}
          </div>

          {/* Role field (maps to is_admin for backend) */}
          <div>
            <label htmlFor="role" className="block text-sm font-medium text-white mb-2">
              Role
            </label>
            <select
              id="role"
              value={formData.role}
              onChange={(e) => handleInputChange('role', e.target.value)}
              className="input-field w-full"
              disabled={updateMutation.isPending}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              {/* keep your domain roles for UI semantics */}
              <option value="sales_director">Sales Director</option>
              <option value="account_manager">Account Manager</option>
            </select>
            <p className="mt-1 text-sm text-trust-silver">
              Choosing <strong>Admin</strong> grants administrator permissions. Other roles are treated as standard users.
            </p>
          </div>

          {/* Optional: Set/Reset password */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">Password (optional)</label>
            <input
              type="password"
              autoComplete="new-password"
              value={formData.password}
              onChange={(e) => handleInputChange('password', e.target.value)}
              className={`input-field w-full ${errors.password ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="Set a new password (leave blank to keep current)"
              disabled={updateMutation.isPending}
            />
            {errors.password && <p className="mt-1 text-sm text-critical-red">{errors.password}</p>}

            <label className="block text-sm font-medium text-white mt-4 mb-2">Confirm Password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={formData.confirm_password}
              onChange={(e) => handleInputChange('confirm_password', e.target.value)}
              className={`input-field w-full ${errors.confirm_password ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="Re-enter the new password"
              disabled={updateMutation.isPending}
            />
            {errors.confirm_password && (
              <p className="mt-1 text-sm text-critical-red">{errors.confirm_password}</p>
            )}
            <p className="mt-1 text-xs text-trust-silver">
              Minimum 8 characters. Leave blank if you don't want to change the password.
            </p>
          </div>

          {/* Active status */}
          <div>
            <label className="block text-sm font-medium text-white mb-3">Account Status</label>
            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={() => handleInputChange('is_active', !formData.is_active)}
                disabled={updateMutation.isPending}
                className={`
                  relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 
                  ${formData.is_active ? 'bg-success-green' : 'bg-gray-600'}
                  ${updateMutation.isPending ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                `}
                aria-pressed={formData.is_active}
                aria-label="Toggle account active status"
              >
                <span
                  className={`
                    inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200
                    ${formData.is_active ? 'translate-x-6' : 'translate-x-1'}
                  `}
                />
              </button>
              <span className="text-sm text-white">{formData.is_active ? 'Active' : 'Inactive'}</span>
            </div>
            <p className="mt-2 text-sm text-trust-silver">
              {formData.is_active
                ? 'User can sign in and access the platform'
                : 'User account is deactivated and cannot sign in'}
            </p>
          </div>

          {/* Account timestamps */}
          <div className="border-t border-gray-700 pt-6">
            <h3 className="text-sm font-medium text-white mb-3">Account History</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-trust-silver">Created</p>
                <p className="text-sm text-white">{safeCreated}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-trust-silver">Last Updated</p>
                <p className="text-sm text-white">{safeUpdated}</p>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end space-x-4 pt-6 border-t border-gray-700">
            <Link to={`/users/${user.id}`} className="btn-secondary">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {updateMutation.isPending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Changes</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
