// frontend/src/components/Header.tsx
// Detecktiv.io – App Header (responsive, auth-aware, minimal + clean)
import { useState, useRef, useEffect } from 'react'
import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import {
  Bars3Icon,
  XMarkIcon,
  UserCircleIcon,
  ArrowRightOnRectangleIcon,
  UsersIcon,
} from '@heroicons/react/24/outline'

function classNames(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(' ')
}

export default function Header() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!menuRef.current) return
      if (!menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    window.addEventListener('click', onClick)
    return () => window.removeEventListener('click', onClick)
  }, [])

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const initials = (user?.name || user?.email || '?')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join('')

  const onLogout = async () => {
    await logout()
    navigate('/login')
  }

  const navItems = [
    { to: '/users', label: 'Users', icon: UsersIcon },
    // Add more when ready, e.g. { to: '/companies', label: 'Companies', icon: BuildingOfficeIcon }
  ]

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-gray-950/70 backdrop-blur-glass">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Left: Brand + Desktop Nav */}
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-medium bg-detecktiv-purple flex items-center justify-center">
              <span className="text-white font-bold">D</span>
            </div>
            <span className="hidden sm:inline text-white font-semibold tracking-wide">detecktiv.io</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    classNames(
                      'px-3 py-2 rounded-medium text-sm font-medium transition-colors duration-200',
                      isActive ? 'bg-white/10 text-white' : 'text-trust-silver hover:text-white hover:bg-white/5'
                    )
                  }
                >
                  <span className="inline-flex items-center gap-2">
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </span>
                </NavLink>
              )
            })}
          </nav>
        </div>

        {/* Right: User Menu */}
        <div className="flex items-center gap-3">
          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 rounded-medium text-trust-silver hover:text-white hover:bg-white/5 transition"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {mobileOpen ? <XMarkIcon className="h-6 w-6" /> : <Bars3Icon className="h-6 w-6" />}
          </button>

          {/* Profile */}
          <div className="relative" ref={menuRef}>
            <button
              className="flex items-center gap-3 p-1 rounded-medium hover:bg-white/5 transition"
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <div className="h-9 w-9 rounded-full bg-white/10 flex items-center justify-center">
                {user ? (
                  <span className="text-sm font-semibold text-white">{initials || '?'}</span>
                ) : (
                  <UserCircleIcon className="h-6 w-6 text-trust-silver" />
                )}
              </div>
              <div className="hidden sm:flex flex-col items-start">
                <span className="text-sm text-white leading-none">
                  {user?.name || 'Guest'}
                </span>
                <span className="text-xs text-trust-silver leading-none">
                  {user?.email || 'Not signed in'}
                </span>
              </div>
            </button>

            {/* Dropdown */}
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-2 w-56 glass-card shadow-card border border-white/10 p-2"
              >
                {user ? (
                  <>
                    <Link
                      to="/users/me"
                      className="flex items-center gap-2 px-3 py-2 rounded-medium text-sm text-white hover:bg-white/5"
                      role="menuitem"
                    >
                      <UserCircleIcon className="h-5 w-5 text-trust-silver" />
                      <span>My Profile</span>
                    </Link>
                    <button
                      onClick={onLogout}
                      className="flex w-full items-center gap-2 px-3 py-2 rounded-medium text-sm text-white hover:bg-white/5"
                      role="menuitem"
                    >
                      <ArrowRightOnRectangleIcon className="h-5 w-5 text-trust-silver" />
                      <span>Sign out</span>
                    </button>
                  </>
                ) : (
                  <Link
                    to="/login"
                    className="flex items-center gap-2 px-3 py-2 rounded-medium text-sm text-white hover:bg-white/5"
                    role="menuitem"
                  >
                    <ArrowRightOnRectangleIcon className="h-5 w-5 text-trust-silver" />
                    <span>Sign in</span>
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileOpen && (
        <div className="md:hidden border-t border-white/10 bg-gray-950">
          <nav className="px-4 py-3 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const active = location.pathname.startsWith(item.to)
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={classNames(
                    'flex items-center gap-3 px-3 py-2 rounded-medium text-sm font-medium',
                    active ? 'bg-white/10 text-white' : 'text-trust-silver hover:text-white hover:bg-white/5'
                  )}
                >
                  <Icon className="h-5 w-5" />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      )}
    </header>
  )
}
