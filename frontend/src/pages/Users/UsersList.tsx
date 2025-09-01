// frontend/src/pages/Users/UsersList.tsx
// Updated to use server-side pagination + search via UsersApi.list({ page, page_size, q })
// and to import the API via the @ alias. Also hardens null-safety for optional fields.
// Based on the original file you provided. :contentReference[oaicite:0]{index=0}

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UsersApi, type User } from '@/api/client'
import { 
  PlusIcon, 
  MagnifyingGlassIcon,
  EyeIcon,
  PencilIcon,
  TrashIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  UsersIcon
} from '@heroicons/react/24/outline'

type UsersResponse = {
  items: User[]
  total: number
  page: number
  page_size: number
}

export default function UsersList() {
  const [searchTerm, setSearchTerm] = useState('')
  const [currentPage, setCurrentPage] = useState(0) // 0-based for UI; API will use 1-based
  const [limit] = useState(20)
  const queryClient = useQueryClient()

  // Reset to first page when search changes (keeps UX predictable)
  useEffect(() => {
    setCurrentPage(0)
  }, [searchTerm])

  // Fetch users with server pagination + search
  const { data, isLoading, isFetching, error, refetch } = useQuery<UsersResponse>({
    queryKey: ['users', currentPage, limit, searchTerm],
    queryFn: () =>
      UsersApi.list({
        page: currentPage + 1,
        page_size: limit,
        q: searchTerm || undefined,
      }),
    keepPreviousData: true,
    staleTime: 30_000,
  })

  // Normalize response for rendering
  const users: User[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const hasNextPage = currentPage + 1 < totalPages
  const hasPreviousPage = currentPage > 0

  // Delete (deactivate) user mutation
  const deleteMutation = useMutation({
    mutationFn: UsersApi.deactivate,
    onSuccess: () => {
      // Refresh the users list
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err) => {
      console.error('Failed to deactivate user:', err)
      alert('Failed to deactivate user. Please try again.')
    }
  })

  const handleDelete = async (userId: number, userName?: string) => {
    const label = userName && userName.trim().length > 0 ? userName : `user #${userId}`
    const confirmed = window.confirm(
      `Are you sure you want to deactivate ${label}? This action cannot be undone.`
    )
    if (confirmed) {
      deleteMutation.mutate(userId)
    }
  }

  // Client-side filtering kept (non-destructive) – server is already filtering by q
  const filteredUsers = (users || []).filter((user) => {
    const name = (user.name || '').toLowerCase()
    const email = (user.email || '').toLowerCase()
    const q = searchTerm.toLowerCase()
    return !q || name.includes(q) || email.includes(q)
  })

  const loadingOrFetching = isLoading || isFetching

  return (
    <div className="space-y-6">
      {/* Header with search and create button */}
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Users</h1>
          <p className="mt-2 text-sm text-trust-silver">
            Manage user accounts and permissions for your team
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <Link
            to="/users/create"
            className="btn-primary inline-flex items-center space-x-2"
          >
            <PlusIcon className="h-4 w-4" />
            <span>Add User</span>
          </Link>
        </div>
      </div>

      {/* Search bar */}
      <div className="glass-card p-6 rounded-large">
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <MagnifyingGlassIcon className="h-5 w-5 text-trust-silver" />
          </div>
          <input
            type="text"
            placeholder="Search users by email or name..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input-field w-full pl-10"
          />
        </div>
      </div>

      {/* Users table */}
      <div className="glass-card rounded-large overflow-hidden">
        {loadingOrFetching ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
            <p className="text-trust-silver">Loading users...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="text-critical-red">Failed to load users. Please try again.</p>
            <button className="btn-secondary mt-3" onClick={() => refetch()}>
              Retry
            </button>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="p-8 text-center">
            <UsersIcon className="mx-auto h-12 w-12 text-trust-silver mb-4" />
            <h3 className="text-lg font-medium text-white mb-2">No users found</h3>
            <p className="text-trust-silver mb-4">
              {searchTerm ? 'No users match your search criteria.' : 'Get started by adding your first user.'}
            </p>
            {!searchTerm && (
              <Link to="/users/create" className="btn-primary">
                Add User
              </Link>
            )}
          </div>
        ) : (
          <>
            <table className="table-modern">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => {
                  const initial = ((user.name && user.name[0]) || (user.email && user.email[0]) || '?').toUpperCase()
                  const created = user.created_at ? new Date(user.created_at).toLocaleDateString('en-GB') : '—'
                  return (
                    <tr key={user.id}>
                      <td>
                        <div className="flex items-center">
                          <div className="h-8 w-8 rounded-full bg-detecktiv-purple flex items-center justify-center mr-3">
                            <span className="text-sm font-medium text-white">
                              {initial}
                            </span>
                          </div>
                          <div>
                            <div className="font-medium text-white">{user.name || '—'}</div>
                            <div className="text-sm text-trust-silver">{user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="inline-flex items-center rounded-full bg-detecktiv-purple/20 px-2 py-1 text-xs font-medium text-detecktiv-purple">
                          {user.is_admin ? 'Admin' : 'User'}
                        </span>
                      </td>
                      <td>
                        <span className={user.is_active ? 'status-active' : 'status-inactive'}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="text-trust-silver">
                        {created}
                      </td>
                      <td>
                        <div className="flex items-center space-x-2">
                          <Link
                            to={`/users/${user.id}`}
                            className="text-detecktiv-purple hover:text-purple-400 transition-colors duration-200"
                            title="View user"
                          >
                            <EyeIcon className="h-4 w-4" />
                          </Link>
                          <Link
                            to={`/users/${user.id}/edit`}
                            className="text-trust-silver hover:text-white transition-colors duration-200"
                            title="Edit user"
                          >
                            <PencilIcon className="h-4 w-4" />
                          </Link>
                          <button
                            onClick={() => handleDelete(user.id, user.name || user.email)}
                            disabled={deleteMutation.isPending}
                            className="text-critical-red hover:text-red-400 transition-colors duration-200 disabled:opacity-50"
                            title="Deactivate user"
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="bg-gray-800/50 px-6 py-4 border-t border-gray-700 flex items-center justify-between">
                <div className="flex-1 flex justify-between sm:hidden">
                  <button
                    onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                    disabled={!hasPreviousPage}
                    className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setCurrentPage(currentPage + 1)}
                    disabled={!hasNextPage}
                    className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
                <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-trust-silver">
                      Showing page {currentPage + 1} of {totalPages}
                    </p>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                      disabled={!hasPreviousPage}
                      className="p-2 text-trust-silver hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                    >
                      <ChevronLeftIcon className="h-5 w-5" />
                    </button>
                    <span className="text-sm text-white">
                      {currentPage + 1} / {totalPages}
                    </span>
                    <button
                      onClick={() => setCurrentPage(currentPage + 1)}
                      disabled={!hasNextPage}
                      className="p-2 text-trust-silver hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                    >
                      <ChevronRightIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
