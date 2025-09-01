// frontend/src/pages/Users/UsersCreate.tsx
// Strengthened wiring & validation without removing your existing features.  :contentReference[oaicite:0]{index=0}
//
// Improvements:
// - Use alias import for API: '@/api/client'
// - Map UI `role` → backend `is_admin` while preserving your role select
// - Stricter validation (email format, name required, password min 8 + confirm)
// - Trim/sanitize inputs; clear field errors on change
// - Better error surfacing from backend (detail/message)
// - Disable buttons while pending; navigate to the new user's page on success

import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { UsersApi, type UserCreate } from '@/api/client'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'

type CreateFormData = {
  email: string
  name: string
  role: 'user' | 'admin' | 'sales_director' | 'account_manager'
  password: string
  confirm_password?: string
}

export default function UsersCreate() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formData, setFormData] = useState<CreateFormData>({
    email: '',
    name: '',
    role: 'user', // Default role
    password: '',
    confirm_password: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Map UI form → API payload
  const toCreate = (data: CreateFormData): UserCreate => {
    const payload: UserCreate = {
      email: data.email.trim().toLowerCase(),
      name: data.name.trim(),
      password: data.password.trim(),
      is_admin: data.role === 'admin',
      // NOTE: other UI roles (sales_director/account_manager) map to standard users for now
    }
    return payload
  }

  // Create user mutation
  const createMutation = useMutation({
    mutationFn: (payload: CreateFormData) => UsersApi.create(toCreate(payload)),
    onSuccess: (newUser) => {
      // Refresh the users list
      queryClient.invalidateQueries({ queryKey: ['users'] })
      // Navigate to the new user's detail page
      navigate(`/users/${newUser.id}`)
    },
    onError: (error: any) => {
      // Surface backend-provided details when available
      const message =
        error?.details?.detail ||
        error?.details?.message ||
        error?.message ||
        'Failed to create user.'
      // Handle common uniqueness error heuristically if provided as plain text
      if (String(message).toLowerCase().includes('exist')) {
        setErrors({ email: 'A user with this email already exists' })
      } else {
        setErrors({ general: String(message) })
      }
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setErrors({})

    const cleanEmail = formData.email.trim().toLowerCase()
    const cleanName = formData.name.trim()
    const cleanPassword = formData.password

    // Basic validation
    const newErrors: Record<string, string> = {}

    if (!cleanEmail) {
      newErrors.email = 'Email is required'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      newErrors.email = 'Please enter a valid email address'
    }

    if (!cleanName) {
      newErrors.name = 'Name is required'
    }

    if (!cleanPassword) {
      newErrors.password = 'Password is required'
    } else if (cleanPassword.length < 8) {
      newErrors.password = 'Password must be at least 8 characters'
    }

    if ((formData.confirm_password || '').length > 0 && formData.confirm_password !== cleanPassword) {
      newErrors.confirm_password = 'Passwords do not match'
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    createMutation.mutate({
      ...formData,
      email: cleanEmail,
      name: cleanName,
      password: cleanPassword,
    })
  }

  const handleInputChange = (field: keyof CreateFormData, value: string) => {
    // Normalize email to trim spaces on input; leave others as-is (trim on submit)
    const v = field === 'email' ? value.replace(/\s+/g, '') : value
    setFormData((prev) => ({ ...prev, [field]: v }))
    // Clear field error as user types
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: '' }))
    }
  }

  return (
    <div className="space-y-6">
      {/* Header with back button */}
      <div className="flex items-center space-x-4">
        <Link
          to="/users"
          className="p-2 text-trust-silver hover:text-white transition-colors duration-200 rounded-medium hover:bg-gray-800"
        >
          <ArrowLeftIcon className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-white">Create New User</h1>
          <p className="mt-1 text-sm text-trust-silver">
            Add a new team member to your detecktiv.io platform
          </p>
        </div>
      </div>

      {/* Create form */}
      <div className="glass-card p-8 rounded-large max-w-2xl">
        <form onSubmit={handleSubmit} className="space-y-6" noValidate>
          {/* General error */}
          {errors.general && (
            <div className="bg-critical-red/10 border border-critical-red/20 rounded-medium p-4">
              <p className="text-sm text-critical-red">{errors.general}</p>
            </div>
          )}

          {/* Email field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-white mb-2">
              Email Address *
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={formData.email}
              onChange={(e) => handleInputChange('email', e.target.value)}
              className={`input-field w-full ${errors.email ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="john.smith@company.co.uk"
              disabled={createMutation.isPending}
            />
            {errors.email && <p className="mt-1 text-sm text-critical-red">{errors.email}</p>}
          </div>

          {/* Name field */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-white mb-2">
              Full Name *
            </label>
            <input
              id="name"
              type="text"
              autoComplete="name"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className={`input-field w-full ${errors.name ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="John Smith"
              disabled={createMutation.isPending}
            />
            {errors.name && <p className="mt-1 text-sm text-critical-red">{errors.name}</p>}
          </div>

          {/* Role field */}
          <div>
            <label htmlFor="role" className="block text-sm font-medium text-white mb-2">
              Role
            </label>
            <select
              id="role"
              value={formData.role}
              onChange={(e) => handleInputChange('role', e.target.value)}
              className="input-field w-full"
              disabled={createMutation.isPending}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="sales_director">Sales Director</option>
              <option value="account_manager">Account Manager</option>
            </select>
            <p className="mt-1 text-sm text-trust-silver">
              Choosing <strong>Admin</strong> grants administrator permissions. Other roles are treated as standard
              users (you can add granular permissions later).
            </p>
          </div>

          {/* Password field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-white mb-2">
              Temporary Password *
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={formData.password}
              onChange={(e) => handleInputChange('password', e.target.value)}
              className={`input-field w-full ${errors.password ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="Minimum 8 characters"
              disabled={createMutation.isPending}
            />
            {errors.password && <p className="mt-1 text-sm text-critical-red">{errors.password}</p>}
            <p className="mt-1 text-sm text-trust-silver">
              The user can change this after first login.
            </p>
          </div>

          {/* Confirm Password field (optional but recommended) */}
          <div>
            <label htmlFor="confirm_password" className="block text-sm font-medium text-white mb-2">
              Confirm Password
            </label>
            <input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              value={formData.confirm_password}
              onChange={(e) => handleInputChange('confirm_password', e.target.value)}
              className={`input-field w-full ${errors.confirm_password ? 'border-critical-red focus:ring-critical-red' : ''}`}
              placeholder="Re-enter the password"
              disabled={createMutation.isPending}
            />
            {errors.confirm_password && (
              <p className="mt-1 text-sm text-critical-red">{errors.confirm_password}</p>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end space-x-4 pt-6 border-t border-gray-700">
            <Link to="/users" className="btn-secondary">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {createMutation.isPending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Creating...</span>
                </>
              ) : (
                <span>Create User</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
