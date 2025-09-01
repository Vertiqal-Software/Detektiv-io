import { useEffect, useState } from 'react'

export default function UsersList() {
  const [info, setInfo] = useState('Loading…')
  useEffect(() => { setInfo('Users page stub — replace with real component.') }, [])
  return (
    <div style={{padding:'1rem'}}>
      <h2>Users</h2>
      <p>{info}</p>
    </div>
  )
}