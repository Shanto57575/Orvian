import { useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  LogOut,
  Shield,
} from 'lucide-react'
import { useAuth } from '../../context/useAuth'

export function UserMenu() {
  const { user, logout } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)

  if (!user) return null

  const handleLogout = async () => {
    setIsLoggingOut(true)
    setLogoutError(null)
    try {
      await logout()
      setIsOpen(false)
    } catch (err) {
      const detail = err instanceof Error ? `: ${err.message}` : ''
      setLogoutError(
        `Failed to sign out on the server${detail}. Your session is still active. Please try again.`,
      )
    } finally {
      setIsLoggingOut(false)
    }
  }

  const initials = (user.full_name || user.email)
    .split(' ')
    .map((s) => s[0])
    .join('')
    .substring(0, 2)
    .toUpperCase()

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2.5 rounded-full border border-slate-200 bg-white p-1 pr-3 shadow-xs transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
        aria-expanded={isOpen}
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
          {initials}
        </div>
        <div className="flex flex-col text-left">
          <span className="text-xs font-semibold text-slate-800 line-clamp-1 max-w-[120px]">
            {user.full_name || user.email.split('@')[0]}
          </span>
        </div>
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 z-50 mt-2 w-64 rounded-xl border border-slate-200 bg-white p-3 shadow-xl">
            <div className="border-b border-slate-100 pb-3">
              <p className="text-xs font-semibold text-slate-900 truncate">
                {user.full_name || 'Operator'}
              </p>
              <p className="text-xs text-slate-500 truncate">{user.email}</p>

              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {user.is_verified ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Verified
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                    <Clock className="h-3 w-3" />
                    Pending Verification
                  </span>
                )}
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                  <Shield className="h-3 w-3" />
                  {user.role}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 capitalize">
                  {user.auth_provider}
                </span>
              </div>
            </div>

            <div className="pt-2 space-y-1">
              {logoutError && (
                <div className="mb-2 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{logoutError}</span>
                </div>
              )}

              <button
                type="button"
                onClick={handleLogout}
                disabled={isLoggingOut}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs font-semibold text-slate-700 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-60"
              >
                {isLoggingOut ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                    <span>Signing Out...</span>
                  </>
                ) : (
                  <>
                    <LogOut className="h-4 w-4 text-slate-400" />
                    <span>Sign Out</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
