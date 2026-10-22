import { useEffect, useState } from 'react'
import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import {
  Activity,
  CheckCircle2,
  Layers,
  Lock,
  LogIn,
  ShieldCheck,
  Sparkles,
  UserCheck,
  X,
} from 'lucide-react'
import { queryClient } from './lib/queryClient'
import { AuthProvider } from './context/AuthContext'
import { useAuth } from './context/useAuth'
import { LoginForm } from './components/auth/LoginForm'
import { RegisterForm } from './components/auth/RegisterForm'
import { VerifyOtpModal } from './components/auth/VerifyOtpModal'
import { ForgotPasswordModal } from './components/auth/ForgotPasswordModal'
import { ResetPasswordModal } from './components/auth/ResetPasswordModal'
import { VerifyEmailNotice } from './components/auth/VerifyEmailNotice'
import { UserMenu } from './components/auth/UserMenu'
import { ProtectedDemoCard } from './components/auth/ProtectedDemoCard'
import { ChatCard } from './components/chat/ChatCard'

interface HealthResponse {
  status: string
  project: string
  environment: string
  debug: boolean
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/v1/health')
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return response.json()
}

function StatusCard() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
  })

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Activity className="h-5 w-5" />
        </div>
        <div>
          <h3 className="font-semibold text-slate-900">API Health</h3>
          <p className="text-xs text-slate-500">
            FastAPI runtime & connection status
          </p>
        </div>
      </div>
      <div className="mt-4 pt-4 border-t border-slate-100">
        {isPending ? (
          <p className="text-xs text-slate-400 animate-pulse">
            Checking backend status...
          </p>
        ) : isError ? (
          <div className="flex items-center gap-2 text-xs font-medium text-amber-600">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            <span>Backend offline (start FastAPI on port 8000)</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs font-medium text-emerald-600">
            <CheckCircle2 className="h-4 w-4" />
            <span>
              Backend Online ({data.project} &middot; {data.environment})
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function MainContent() {
  const { user, isAuthenticated, isVerified } = useAuth()
  const [authView, setAuthView] = useState<'login' | 'register' | 'otp' | null>(
    null,
  )
  const [otpEmail, setOtpEmail] = useState('')
  const [isForgotOpen, setIsForgotOpen] = useState(false)
  const [resetToken, setResetToken] = useState<string | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)

  // Check URL query parameters for reset token or OAuth errors
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    const isResetPath =
      window.location.pathname.includes('reset') || params.has('reset_token')
    if (token && isResetPath) {
      setResetToken(token)
    }

    const errorParam = params.get('auth_error') || params.get('error')
    if (errorParam) {
      setAuthError(errorParam)
      setAuthView('login')
      const cleanUrl = new URL(window.location.href)
      cleanUrl.searchParams.delete('auth_error')
      cleanUrl.searchParams.delete('error')
      window.history.replaceState({}, '', cleanUrl.pathname + cleanUrl.search)
    }
  }, [])

  return (
    <div className="min-h-screen bg-slate-50/60 text-slate-900 flex flex-col font-sans">
      {/* Email Verification Banner */}
      <VerifyEmailNotice
        onOpenOtp={() => {
          if (user?.email) {
            setOtpEmail(user.email)
            setAuthView('otp')
          }
        }}
      />

      {/* Navigation Header */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-xs">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-sm shadow-xs">
              O
            </div>
            <span className="font-bold text-lg tracking-tight text-slate-900">
              Orvian
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
              AI Analyst Active
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <span>Synthetic Business Data Only</span>
            </div>

            {isAuthenticated ? (
              <UserMenu />
            ) : (
              <button
                type="button"
                onClick={() => setAuthView('login')}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-blue-700"
              >
                <LogIn className="h-3.5 w-3.5" />
                <span>Sign In</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-10 flex flex-col gap-8">
        {/* Welcome Section */}
        <div className="flex flex-col gap-2 max-w-3xl">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-blue-600">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Secure Authentication & Session Management</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Synthetic Business Data Assistant
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed">
            Production-oriented authentication architecture with Argon2id
            password hashing, mandatory email verification, Google OAuth2
            integration, HttpOnly session cookies, CSRF double-submit
            protection, and backend-enforced route authorization.
          </p>
        </div>

        {/* Feature Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <StatusCard />

          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
                <UserCheck className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900">Account Status</h3>
                <p className="text-xs text-slate-500">Session & role guard</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-slate-100 flex flex-col gap-1.5 text-xs">
              {isAuthenticated ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Logged in as:</span>
                    <span className="font-medium text-slate-800 truncate max-w-[160px]">
                      {user?.email}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Email Verification:</span>
                    <span
                      className={`font-semibold ${
                        isVerified ? 'text-emerald-600' : 'text-amber-600'
                      }`}
                    >
                      {isVerified ? 'Verified' : 'Pending Verification'}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex items-center gap-2 text-slate-500">
                  <Lock className="h-4 w-4 text-slate-400" />
                  <span>No active session. Please sign in.</span>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50 text-purple-600">
                <Layers className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900">
                  Security Invariants
                </h3>
                <p className="text-xs text-slate-500">
                  Strict baseline controls
                </p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-slate-100 flex flex-wrap gap-1.5 text-[11px]">
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                Argon2id Hashing
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                HttpOnly Sessions
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                Double-Submit CSRF
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                Single-Use Tokens
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                OAuth Safe Linking
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-medium">
                SlowAPI Rate Limits
              </span>
            </div>
          </div>
        </div>

        {/* AI Operations Analyst Workspace */}
        <section aria-label="AI Operations Analyst" className="w-full">
          <ChatCard
            onOpenAuth={() => setAuthView('login')}
            onOpenOtp={() => {
              if (user?.email) {
                setOtpEmail(user.email)
                setAuthView('otp')
              }
            }}
          />
        </section>

        {/* Live Backend Permission Test */}
        <div className="w-full">
          <ProtectedDemoCard onOpenAuth={() => setAuthView('login')} />
        </div>
      </main>

      {/* Auth Modal Overlay */}
      {authView && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="relative">
            <button
              type="button"
              onClick={() => setAuthView(null)}
              className="absolute -top-3 -right-3 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-500 shadow-md transition hover:bg-slate-100 hover:text-slate-800"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </button>
            {authView === 'login' ? (
              <LoginForm
                initialError={authError}
                onSwitchToRegister={() => {
                  setAuthError(null)
                  setAuthView('register')
                }}
                onSwitchToForgotPassword={() => {
                  setAuthError(null)
                  setAuthView(null)
                  setIsForgotOpen(true)
                }}
                onSuccess={() => {
                  setAuthError(null)
                  setAuthView(null)
                }}
              />
            ) : authView === 'register' ? (
              <RegisterForm
                onSwitchToLogin={() => setAuthView('login')}
                onRegistered={(email) => {
                  setOtpEmail(email)
                  setAuthView('otp')
                }}
              />
            ) : (
              <VerifyOtpModal
                email={otpEmail}
                onSuccess={() => setAuthView(null)}
                onSwitchToLogin={() => setAuthView('login')}
              />
            )}
          </div>
        </div>
      )}

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotOpen}
        onClose={() => setIsForgotOpen(false)}
      />

      {/* Reset Password Modal (URL Token Triggered) */}
      {resetToken && (
        <ResetPasswordModal
          token={resetToken}
          onClose={() => {
            setResetToken(null)
            const cleanUrl = new URL(window.location.href)
            cleanUrl.searchParams.delete('token')
            cleanUrl.searchParams.delete('reset_token')
            window.history.replaceState(
              {},
              '',
              cleanUrl.search ? cleanUrl.pathname + cleanUrl.search : '/',
            )
          }}
          onSuccess={() => {
            setResetToken(null)
            const cleanUrl = new URL(window.location.href)
            cleanUrl.searchParams.delete('token')
            cleanUrl.searchParams.delete('reset_token')
            window.history.replaceState(
              {},
              '',
              cleanUrl.search ? cleanUrl.pathname + cleanUrl.search : '/',
            )
            setAuthView('login')
          }}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        Orvian &copy; 2026 &middot; Synthetic Business Data Assistant &middot;
        Native Windows Development
      </footer>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MainContent />
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
