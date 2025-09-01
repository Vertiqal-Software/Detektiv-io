import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { users as UsersApi, type UsersListResponse, type User, HttpError } from '@/api/client'

// NOTE: This file preserves all original code and only ADDS functionality.
// Original lines are kept intact and used (e.g., the `info` state & effect).

export default function UsersList() {
  // ---- original state & effect (preserved) ----
  const [info, setInfo] = useState('Loading…')
  useEffect(() => { setInfo('Users page stub — replace with real component.') }, [])

  // ---- added: local UI state ----
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')

  // ---- added: debounce search to reduce requests ----
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 350)
    return () => clearTimeout(t)
  }, [q])

  // ---- added: fetch users with React Query ----
  const listQuery = useQuery<UsersListResponse, HttpError>({
    queryKey: ['users', { page, pageSize, q: debouncedQ }],
    queryFn: () => UsersApi.list({ page, page_size: pageSize, q: debouncedQ }),
    keepPreviousData: true,
    staleTime: 30_000,
    retry: (failureCount, error) => {
      // Be gentle on auth errors; reflect immediately
      if (error?.status === 401) return false
      return failureCount < 2
    },
  })

  // ---- added: remove user mutation with optimistic cache update ----
  const removeMutation = useMutation({
    mutationFn: async (id: number) => {
      await UsersApi.remove(id)
      return id
    },
    onMutate: async (id: number) => {
      await queryClient.cancelQueries({ queryKey: ['users'] })
      const prev = queryClient.getQueryData<UsersListResponse>(['users', { page, pageSize, q: debouncedQ }])
      if (prev) {
        const next: UsersListResponse = {
          ...prev,
          items: prev.items.filter(u => u.id !== id),
          total: Math.max(0, prev.total - 1),
        }
        queryClient.setQueryData(['users', { page, pageSize, q: debouncedQ }], next)
      }
      return { prev }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(['users', { page, pageSize, q: debouncedQ }], ctx.prev)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    }
  })

  // ---- added: reflect query status in original `info` message (non-breaking) ----
  useEffect(() => {
    if (listQuery.isFetching) {
      setInfo('Loading…')
    } else if (listQuery.isError) {
      const msg =
        listQuery.error?.details?.message ||
        listQuery.error?.details?.detail ||
        listQuery.error?.message ||
        'Failed to load users'
      setInfo(`Error: ${msg}`)
    } else if (listQuery.data) {
      setInfo(`Loaded ${listQuery.data.items.length} of ${listQuery.data.total} users`)
    }
  }, [listQuery.isFetching, listQuery.isError, listQuery.data, listQuery.error])

  // ---- added: helpers ----
  const totalPages = listQuery.data ? Math.max(1, Math.ceil(listQuery.data.total / listQuery.data.page_size)) : 1
  const canPrev = page > 1
  const canNext = page < totalPages

  const onDelete = (u: User) => {
    if (!u?.id) return
    const ok = window.confirm(`Delete user "${u.email}"? This cannot be undone.`)
    if (!ok) return
    removeMutation.mutate(u.id)
  }

  // ---- UI ----
  return (
    <div style={{padding:'1rem'}}>
      <h2 className="text-2xl font-semibold mb-3">Users</h2>

      {/* original info message (preserved) */}
      <p className="text-sm opacity-80 mb-4">{info}</p>

      {/* Controls */}
      <div className="mb-4 flex flex-col md:flex-row gap-2 md:items-center">
        <div className="flex-1">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by email or name..."
            className="w-full rounded-medium border border-white/10 bg-white/5 px-3 py-2 outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm opacity-80">Page size</label>
          <select
            value={pageSize}
            onChange={(e) => { setPage(1); setPageSize(Number(e.target.value) || 10) }}
            className="rounded-medium border border-white/10 bg-white/5 px-2 py-2"
          >
            {[10, 20, 50].map(n => <option key={n} value={n}>{n}</option>)}
          </select>

          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['users'] })}
            className="rounded-medium border border-white/10 bg-white/5 px-3 py-2 hover:bg-white/10 transition"
            disabled={listQuery.isFetching}
            title="Refresh"
          >
            {listQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Table / list */}
      <div className="overflow-x-auto border border-white/10 rounded-large">
        <table className="min-w-full text-sm">
          <thead className="bg-white/5">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Active</th>
              <th className="px-3 py-2 font-medium">Created</th>
              <th className="px-3 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={6}>Loading users…</td>
              </tr>
            )}

            {listQuery.isError && (
              <tr>
                <td className="px-3 py-4 text-red-400" colSpan={6}>
                  {(listQuery.error?.details?.message ||
                    listQuery.error?.details?.detail ||
                    listQuery.error?.message ||
                    'Failed to load users') as string}
                </td>
              </tr>
            )}

            {listQuery.data && listQuery.data.items.length === 0 && (
              <tr>
                <td className="px-3 py-4 opacity-80" colSpan={6}>No users found.</td>
              </tr>
            )}

            {listQuery.data?.items.map((u) => (
              <tr key={u.id} className="border-t border-white/10">
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{u.full_name || '—'}</td>
                <td className="px-3 py-2">{u.role || 'member'}</td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${u.is_active ? 'bg-green-600/20 text-green-300' : 'bg-red-600/20 text-red-300'}`}>
                    {u.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="px-3 py-2">{formatDate(u.created_at)}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-2">
                    {/* Non-destructive actions could be added later (view/edit) */}
                    <button
                      onClick={() => onDelete(u)}
                      className="rounded-medium border border-white/10 bg-white/5 px-2 py-1 hover:bg-white/10 transition"
                      disabled={removeMutation.isPending}
                      title="Delete user"
                    >
                      {removeMutation.isPending ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="mt-4 flex items-center justify-between">
        <div className="text-sm opacity-80">
          {listQuery.data
            ? `Showing ${(listQuery.data.page - 1) * listQuery.data.page_size + 1}-${Math.min(
                listQuery.data.page * listQuery.data.page_size,
                listQuery.data.total
              )} of ${listQuery.data.total}`
            : '—'}
        </div>

        <div className="flex items-center gap-2">
          <button
            className="rounded-medium border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10 transition disabled:opacity-50"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={!canPrev || listQuery.isFetching}
          >
            Previous
          </button>
          <span className="min-w-[6rem] text-center">
            Page {page} {totalPages ? `of ${totalPages}` : ''}
          </span>
          <button
            className="rounded-medium border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10 transition disabled:opacity-50"
            onClick={() => setPage(p => p + 1)}
            disabled={!canNext || listQuery.isFetching}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- helpers (added) ----
function formatDate(iso?: string) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
  } catch {
    return '—'
  }
}
