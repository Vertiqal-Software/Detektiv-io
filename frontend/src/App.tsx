import { useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate } from 'react-router-dom'
import Login from './pages/Auth/Login'
import Profile from './pages/Me/Profile'
import Users from './pages/users/List'

function Home() {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
    fetch(${base}/health).then(r => setOk(r.ok)).catch(() => setOk(false))
  }, [])
  return (
    <div style={{padding:'1rem'}}>
      <h1>Detecktiv.io</h1>
      <p>Health check: {ok === true ? '✅ API reachable' : ok === false ? '❌ API not reachable' : '…'}</p>
      <nav style={{marginTop:'1rem', display:'grid', gap:'0.5rem'}}>
        <Link to="/login">Login</Link>
        <Link to="/users">Users</Link>
        <Link to="/me">My Profile</Link>
      </nav>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/auth/login" element={<Login />} />
      <Route path="/users/*" element={<Users />} />
      <Route path="/me" element={<Profile />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}