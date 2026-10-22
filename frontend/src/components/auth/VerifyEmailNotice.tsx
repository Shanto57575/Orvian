import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Mail,
} from 'lucide-react'
import { authApi } from '../../api/auth'
import { useAuth } from '../../context/useAuth'

interface VerifyEmailNoticeProps {
  onOpenOtp?: () => void
}

export function VerifyEmailNotice({ onOpenOtp }: VerifyEmailNoticeProps = {}) {
  const { user, refetchUser } = useAuth()
  const [isResending, setIsResending] = useState(false)
  const [resendStatus, setResendStatus] = useState<string | null>(null)
  const [verificationError, setVerificationError] = useState<string | null>(
    null,
  )
  const [isVerifyingToken, setIsVerifyingToken] = useState(false)
  const [verificationSuccess, setVerificationSuccess] = useState(false)

  // Auto-verify if on verification path or explicit verify_token (never on reset-password)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const isReset =
      window.location.pathname.includes('reset') || params.has('reset_token')
    if (isReset) return

    const isVerifyPath =
      window.location.pathname.includes('verify') || params.has('verify_token')
    const token = isVerifyPath
      ? params.get('token') || params.get('verify_token')
      : null

    if (!token) return

    let isMounted = true
    const verify = async () => {
      setIsVerifyingToken(true)
      setVerificationError(null)
      try {
        await authApi.verifyEmail(token)
        if (isMounted) {
          setVerificationSuccess(true)
          await refetchUser()
          // Clean token from URL
          const url = new URL(window.location.href)
          url.searchParams.delete('token')
          url.searchParams.delete('verify_token')
          window.history.replaceState({}, '', url.pathname + url.search)
        }
      } catch (err) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : 'Verification failed'
          // If already verified, treat gracefully as verified!
          if (msg.toLowerCase().includes('already verified')) {
            setVerificationSuccess(true)
            await refetchUser()
            const url = new URL(window.location.href)
            url.searchParams.delete('token')
            url.searchParams.delete('verify_token')
            window.history.replaceState({}, '', url.pathname + url.search)
          } else {
            setVerificationError(msg)
          }
        }
      } finally {
        if (isMounted) {
          setIsVerifyingToken(false)
        }
      }
    }

    void verify()

    return () => {
      isMounted = false
    }
  }, [refetchUser])

  const handleResend = async () => {
    if (!user) return
    setIsResending(true)
    setResendStatus(null)
    try {
      const res = await authApi.resendVerification(user.email)
      setResendStatus(res.message)
    } catch (err) {
      setResendStatus(
        err instanceof Error
          ? err.message
          : 'Failed to send verification email',
      )
    } finally {
      setIsResending(false)
    }
  }

  if (isVerifyingToken) {
    return (
      <div className="flex items-center justify-center gap-3 border-b border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
        <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
        <span>Verifying your email address...</span>
      </div>
    )
  }

  if (verificationSuccess) {
    return (
      <div className="flex items-center justify-between border-b border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
          <span className="font-medium">
            Email verified successfully! All protected features are now
            unlocked.
          </span>
        </div>
      </div>
    )
  }

  if (verificationError) {
    return (
      <div className="flex items-center justify-between border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
          <span>{verificationError}</span>
        </div>
        {user && !user.is_verified && (
          <button
            type="button"
            onClick={handleResend}
            disabled={isResending}
            className="font-semibold text-red-700 underline hover:text-red-900"
          >
            Resend Link
          </button>
        )}
      </div>
    )
  }

  if (!user || user.is_verified) {
    return null
  }

  return (
    <div className="border-b border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-950 backdrop-blur-xs">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
          <span>
            <strong className="font-semibold">Action required:</strong> Please
            verify your email address (<strong>{user.email}</strong>) to access
            all data assistant features.
          </span>
        </div>
        <div className="flex items-center gap-3">
          {onOpenOtp && (
            <button
              type="button"
              onClick={onOpenOtp}
              className="inline-flex items-center gap-1.5 rounded-md bg-amber-700 px-3 py-1 text-xs font-semibold text-white shadow-xs transition hover:bg-amber-800"
            >
              <span>Enter Code</span>
            </button>
          )}
          {resendStatus ? (
            <span className="text-xs font-medium text-emerald-800">
              {resendStatus}
            </span>
          ) : (
            <button
              type="button"
              onClick={handleResend}
              disabled={isResending}
              className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1 text-xs font-semibold text-white shadow-xs transition hover:bg-amber-700 disabled:opacity-60"
            >
              {isResending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Sending...</span>
                </>
              ) : (
                <>
                  <Mail className="h-3 w-3" />
                  <span>Resend Verification</span>
                </>
              )}
            </button>
          )}
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-amber-800 hover:text-amber-950"
          >
            <span>Need Help?</span>
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>
    </div>
  )
}
