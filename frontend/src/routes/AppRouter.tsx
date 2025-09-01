// frontend/src/routes/AppRouter.tsx
// Central route configuration using React Router v6+
// - Wires public + protected routes
// - Uses <RequireAuth> and <RequireGuest> guards
// - Redirects unknown paths to a sensible default
//
// Starting from your file; adds the /users/me (Profile) route without removing anything. :contentReference[oaicite:0]{index=0}

import { Routes, Route, Navigate } from 'react-router-dom'

// Guards
import { RequireAuth, RequireGuest } from '@/routes/RequireAuth'

// Auth
import Login from '@/pages/Auth/Login'

// Users
import UsersList from '@/pages/Users/UsersList'
import UsersCreate from '@/pages/Users/UsersCreate'
import UsersView from '@/pages/Users/UsersView'
import UsersEdit from '@/pages/Users/UsersEdit'

// Me (Profile)
import Profile from '@/pages/Me/Profile'

export default function AppRouter() {
  return (
    <Routes>
      {/* Public / Guest routes */}
      <Route
        path="/login"
        element={
          <RequireGuest>
            <Login />
          </RequireGuest>
        }
      />

      {/* Protected routes */}
      <Route element={<RequireAuth />}>
        {/* Default home → Users list (adjust to your dashboard if needed) */}
        <Route path="/" element={<Navigate to="/users" replace />} />

        {/* Users */}
        <Route path="/users" element={<UsersList />} />
        <Route path="/users/create" element={<UsersCreate />} />
        <Route path="/users/:id" element={<UsersView />} />
        <Route path="/users/:id/edit" element={<UsersEdit />} />

        {/* Me (Profile) */}
        <Route path="/users/me" element={<Profile />} />
      </Route>

      {/* Fallback: redirect unknown routes */}
      <Route path="*" element={<Navigate to="/users" replace />} />
    </Routes>
  )
}
