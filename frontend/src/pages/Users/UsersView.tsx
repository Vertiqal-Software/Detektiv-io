// frontend/src/pages/Users/UsersView.tsx
// Strengthened wiring to API, null-safety, and UX fallbacks without removing existing features.
// - Fix API import path to alias (@/api/client)
// - Add robust typing, safe fallbacks for name/role/dates/initial
// - Keep existing layout and actions; only enhancements added

import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UsersApi, type User as ApiUser } from '@/api/client'
import {
  ArrowLeftIcon,
  PencilIcon,
  TrashIcon,
  EnvelopeIcon,
  CalendarDaysIcon,
  UserCircleIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'

type ViewUser = ApiUser & {
  role?: string
  created_at?: string
  updated_at?: string
  is_active?: boolean
}

export default function UsersView() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const userId = id ? parseInt(id, 10) : null

  // Fetch user details
  const { data: user, isLoading, error } = useQuery<ViewUser>({
    queryKey: ['user', userId],
    queryFn: () => UsersApi.get(userId!),
    enabled: !!userId,
  })

  // Deactivate user mutation
  const deleteMutation = useMutation({
    mutationFn: UsersApi.deactivate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      navigate('/users')
    },
    onError: (error) => {
      console.error('Failed to deactivate user:', error)
      alert('Failed to deactivate user. Please try again.')
    },
  })

  const formatDateDetailed = (v?: string) =>
    v
      ? new Date(v).toLocaleDateString('en-GB', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        })
      : '—'

  const handleDelete = () => {
    if (!user) return
    const label = (user.name && user.name.trim()) || user.email || `user #${user.id}`
    const confirmed = window.confirm(
      `Are you sure you want to deactivate ${label}? This action cannot be undone.`
    )
    if (confirmed) {
      deleteMutation.mutate(user.id)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Loading user details.</p>
        </div>
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center max-w-md">
          <UserCircleIcon className="mx-auto h-12 w-12 text-trust-silver mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">User not found</h3>
          <p className="text-trust-silver mb-4">
            The user you're looking for doesn't exist or you don't have permission to view them.
          </p>
          <Link to="/users" className="btn-primary">
            Back to Users
          </Link>
        </div>
      </div>
    )
  }

  const safeName = user.name || '—'
  const safeEmail = user.email || '—'
  const initial = ((user.name?.[0] ?? user.email?.[0] ?? '?') + '').toUpperCase()
  const roleLabel = (user.role && user.role.replace('_', ' ')) || (user.is_admin ? 'Admin' : 'User')
  const createdAt = formatDateDetailed(user.created_at)
  const updatedAt = formatDateDetailed(user.updated_at)
  const active = user.is_active ?? true

  return (
    <div className="space-y-6">
      {/* Header with navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/users"
            className="p-2 text-trust-silver hover:text-white transition-colors duration-200 rounded-medium hover:bg-gray-800"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold text-white">User Details</h1>
            <p className="mt-1 text-sm text-trust-silver">View and manage user information</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <Link to={`/users/${user.id}/edit`} className="btn-secondary inline-flex items-center space-x-2">
            <PencilIcon className="h-4 w-4" />
            <span>Edit</span>
          </Link>
          <button
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="btn-destructive inline-flex items-center space-x-2 disabled:opacity-50"
          >
            <TrashIcon className="h-4 w-4" />
            <span>{deleteMutation.isPending ? 'Deactivating...' : 'Deactivate'}</span>
          </button>
        </div>
      </div>

      {/* User details card */}
      <div className="glass-card rounded-large overflow-hidden">
        {/* User header */}
        <div className="bg-gradient-primary p-6">
          <div className="flex items-center space-x-4">
            <div className="h-16 w-16 rounded-large bg-white/20 backdrop-blur-glass flex items-center justify-center">
              <span className="text-2xl font-bold text-white">
                {initial}
              </span>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white">{safeName}</h2>
              <p className="text-purple-100">{safeEmail}</p>
              <div className="flex items-center space-x-4 mt-2">
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
                    active ? 'bg-success-green/20 text-success-green' : 'bg-gray-600/20 text-gray-300'
                  }`}
                >
                  {active ? 'Active' : 'Inactive'}
                </span>
                <span className="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-medium text-white capitalize">
                  {roleLabel}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* User information */}
        <div className="p-6 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {/* Basic Information */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-2">Basic Information</h3>

            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <EnvelopeIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Email</p>
                  <p className="text-sm text-trust-silver">{safeEmail}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <UserCircleIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Full Name</p>
                  <p className="text-sm text-trust-silver">{safeName}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <ShieldCheckIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Role</p>
                  <p className="text-sm text-trust-silver capitalize">{roleLabel}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Account Information */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-2">Account Information</h3>

            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Created</p>
                  <p className="text-sm text-trust-silver">{createdAt}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Last Updated</p>
                  <p className="text-sm text-trust-silver">{updatedAt}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="h-5 w-5 flex items-center justify-center mt-0.5">
                  <div className={`h-3 w-3 rounded-full ${active ? 'bg-success-green' : 'bg-gray-500'}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Status</p>
                  <p className="text-sm text-trust-silver">
                    {active ? 'Active user with full access' : 'Inactive - access suspended'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action section */}
        <div className="border-t border-gray-700 bg-gray-800/30 px-6 py-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-trust-silver">User ID: {user.id}</p>
            <div className="flex items-center space-x-3">
              <Link to={`/users/${user.id}/edit`} className="btn-secondary">
                Edit User
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
