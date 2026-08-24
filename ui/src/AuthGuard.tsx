import { useEffect, useState } from 'react'
import { handleCallback, isAuthenticated } from './auth'
import Login from './pages/Login'
 
interface Props {
  children: React.ReactNode
}
 
export default function AuthGuard({ children }: Props) {
  const [checking, setChecking] = useState(true)
  const [authed,   setAuthed]   = useState(false)
 
  useEffect(() => {
    async function init() {
      // Handle Cognito callback (returning from Okta login)
      if (window.location.search.includes('code=')) {
        const ok = await handleCallback()
        if (ok) {
          setAuthed(true)
          setChecking(false)
          return
        }
      }
 
      // Handle post-logout redirect
      if (window.location.search.includes('logged_out=true')) {
        window.history.replaceState({}, '', window.location.pathname)
        setAuthed(false)
        setChecking(false)
        return
      }
 
      if (isAuthenticated()) {
        setAuthed(true)
      }
 
      setChecking(false)
    }
 
    init()
  }, [])
 
  if (checking) {
    return (
      <div style={{
        minHeight:      '100vh',
        display:        'flex',
        flexDirection:  'column',
        alignItems:     'center',
        justifyContent: 'center',
        gap:            16,
        background:     'var(--bg)',
      }}>
        <div className="spinner" />
        <p className="spinner-label">Loading...</p>
      </div>
    )
  }
 
  if (!authed) {
    return <Login />
  }
 
  return <>{children}</>
}
 