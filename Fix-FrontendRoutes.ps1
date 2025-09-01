# Fix-FrontendRoutes.ps1
param(
  [string]$FrontendDir = ".",
  [int]$Port = 5173
)

Set-Location $FrontendDir
$src = Resolve-Path ".\src"
function ImportPath($abs) { return "./" + ($abs.Substring($src.Path.Length+1) -replace '\\','/').Replace('.tsx','') }

# Find actual component files (case-sensitive friendly)
$loginFile   = Get-ChildItem -Recurse -File -Path "$($src.Path)\pages" -Filter Login.tsx | Select-Object -First 1
$profileFile = Get-ChildItem -Recurse -File -Path "$($src.Path)\pages" -Filter Profile.tsx | Where-Object { $_.FullName -match '\\Me\\' } | Select-Object -First 1
$usersFile   = Get-ChildItem -Recurse -File -Path "$($src.Path)\pages" -Filter List.tsx   | Where-Object { $_.FullName -match '\\users\\|\\Users\\' } | Select-Object -First 1

if (-not $loginFile)   { throw "Could not find Login.tsx under src/pages/*" }
if (-not $profileFile) { throw "Could not find Profile.tsx under src/pages/Me/*" }

$loginImport   = ImportPath $loginFile.FullName
$profileImport = ImportPath $profileFile.FullName

# Ensure we have a Users page (stub if missing)
if (-not $usersFile) {
  $usersDir = Join-Path $src.Path "pages\users"
  New-Item -ItemType Directory -Force $usersDir | Out-Null
@"
import { useEffect, useState } from 'react'

export default function UsersList() {
  const [info, setInfo] = useState('Loading…')
  useEffect(() => { setInfo('Users page stub — wire your real component here.') }, [])
  return (
    <div style={{padding:'1rem'}}>
      <h2>Users</h2>
      <p>{info}</p>
    </div>
  )
}
"@ | Set-Content -Encoding UTF8 -NoNewline (Join-Path $usersDir "List.tsx")
  $usersFile = Get-ChildItem (Join-Path $usersDir "List.tsx")
}
$usersImport = ImportPath $usersFile.FullName

# Write App.tsx with correct imports and routes
@"
import { useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate } from 'react-router-dom'
import Login from '$loginImport'
import Profile from '$profileImport'
import Users from '$usersImport'

function Home() {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
    fetch(`${base}/health`).then(r => setOk(r.ok)).catch(() => setOk(false))
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
"@ | Set-Content -Encoding UTF8 -NoNewline (Join-Path $src.Path "App.tsx")

"App.tsx rewritten with:"
"  Login   -> $loginImport"
"  Profile -> $profileImport"
"  Users   -> $usersImport"

# Restart Vite on the chosen port
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  $listener | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
}
if (Test-Path "package.json") {
  try {
    $pkg = Get-Content "package.json" -Raw | ConvertFrom-Json
    if ($pkg.scripts.PSObject.Properties.Name -contains 'dev') {
      Start-Process "cmd.exe" "/c npm run dev -- --port $Port"
    } else {
      Start-Process "cmd.exe" "/c npx vite --port $Port"
    }
  } catch {
    Start-Process "cmd.exe" "/c npx vite --port $Port"
  }
}
Start-Process "http://localhost:$Port/"
