import { useState } from 'react'
import {
  AlertCircle,
  Database,
  Lock,
  Play,
  ShieldCheck,
  Unlock,
} from 'lucide-react'
import { authApi } from '../../api/auth'
import { useAuth } from '../../context/useAuth'

export function ProtectedDemoCard({ onOpenAuth }: { onOpenAuth: () => void }) {
  const { user, isAuthenticated, isVerified } = useAuth()
  const [result, setResult] = useState<{
    status: string
    message: string
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleTestProtectedEndpoint = async () => {
    setIsLoading(false)
    setError(null)
    setResult(null)

    if (!isAuthenticated) {
      onOpenAuth()
      return
    }

    setIsLoading(true)
    try {
      const data = await authApi.checkProtectedVerification()
      setResult(data)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to access protected resource',
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
            <Database className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Protected Business Data Access
            </h3>
            <p className="text-xs text-slate-500">
              Backend-enforced permission guard (`require_verified_user`)
            </p>
          </div>
        </div>

        <div>
          {isVerified ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
              <Unlock className="h-3.5 w-3.5" />
              Access Eligible
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 border border-slate-200">
              <Lock className="h-3.5 w-3.5" />
              {isAuthenticated ? 'Verification Required' : 'Sign-in Required'}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs text-slate-600 leading-relaxed">
        This endpoint verifies session validity, double-submit CSRF tokens, and
        mandatory email verification on the FastAPI server before granting
        access to synthetic customer & invoice analytics.
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={handleTestProtectedEndpoint}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-slate-800 disabled:opacity-60"
        >
          <Play className="h-3.5 w-3.5 fill-white" />
          <span>Test Verification Guard</span>
        </button>

        {user && (
          <span className="text-xs text-slate-500">
            Current account: <strong>{user.email}</strong> (
            {user.is_verified ? 'Verified' : 'Unverified'})
          </span>
        )}
      </div>

      {result && (
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <div>
            <p className="font-semibold">Backend authorization check passed:</p>
            <p className="mt-0.5 text-emerald-700">{result.message}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <p className="font-semibold">Backend guard rejected request:</p>
            <p className="mt-0.5">{error}</p>
          </div>
        </div>
      )}
    </div>
  )
}
