import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type FormEvent,
  type ClipboardEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  KeyRound,
  Loader2,
  RotateCcw,
} from 'lucide-react'
import { useAuth } from '../../context/useAuth'
import { authApi } from '../../api/auth'

interface VerifyOtpModalProps {
  email: string
  onSuccess: () => void
  onSwitchToLogin: () => void
}

export function VerifyOtpModal({
  email,
  onSuccess,
  onSwitchToLogin,
}: VerifyOtpModalProps) {
  const { verifyOtp } = useAuth()
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [error, setError] = useState<string | null>(null)
  const [infoMessage, setInfoMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isResending, setIsResending] = useState(false)
  const [resendCountdown, setResendCountdown] = useState(60)

  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  useEffect(() => {
    if (resendCountdown > 0) {
      const timer = setTimeout(() => setResendCountdown((c) => c - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCountdown])

  const submitOtp = useCallback(
    async (codeToVerify: string) => {
      if (isSubmitting) return
      setError(null)
      setInfoMessage(null)

      if (codeToVerify.length !== 6) {
        setError('Please enter all 6 digits of your verification code.')
        return
      }

      setIsSubmitting(true)
      try {
        await verifyOtp({ email, otp: codeToVerify })
        onSuccess()
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : 'Invalid or expired verification code. Please try again.',
        )
      } finally {
        setIsSubmitting(false)
      }
    },
    [email, isSubmitting, onSuccess, verifyOtp],
  )

  const handleBoxChange = (index: number, e: ChangeEvent<HTMLInputElement>) => {
    const rawVal = e.target.value.replace(/\D/g, '')
    if (!rawVal) {
      const updated = [...digits]
      updated[index] = ''
      setDigits(updated)
      return
    }

    const char = rawVal.slice(-1)
    const updated = [...digits]
    updated[index] = char
    setDigits(updated)
    setError(null)

    // Advance to next box
    if (index < 5) {
      inputRefs.current[index + 1]?.focus()
    }

    // If all 6 digits are entered, automatically verify without clicking
    const fullCode = updated.join('')
    if (fullCode.length === 6 && !updated.includes('')) {
      submitOtp(fullCode)
    }
  }

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      if (!digits[index] && index > 0) {
        e.preventDefault()
        const updated = [...digits]
        updated[index - 1] = ''
        setDigits(updated)
        inputRefs.current[index - 1]?.focus()
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault()
      inputRefs.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < 5) {
      e.preventDefault()
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const pasted = e.clipboardData
      .getData('text')
      .trim()
      .replace(/\D/g, '')
      .slice(0, 6)

    if (!pasted) return

    const updated = ['', '', '', '', '', '']
    for (let i = 0; i < pasted.length; i++) {
      const char = pasted[i]
      if (char) {
        updated[i] = char
      }
    }
    setDigits(updated)
    setError(null)

    const nextIndex = Math.min(pasted.length, 5)
    inputRefs.current[nextIndex]?.focus()

    // If 6 digits pasted, trigger automatic verification immediately
    if (pasted.length === 6) {
      submitOtp(pasted)
    }
  }

  const handleManualSubmit = (e: FormEvent) => {
    e.preventDefault()
    submitOtp(digits.join(''))
  }

  const handleResend = async () => {
    if (resendCountdown > 0 || isResending) return
    setIsResending(true)
    setError(null)
    try {
      await authApi.resendOtp(email)
      setInfoMessage('A new 6-digit verification code has been sent!')
      setResendCountdown(60)
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to resend code. Please try again.',
      )
    } finally {
      setIsResending(false)
    }
  }

  const isComplete = digits.every((d) => d.length === 1)

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-900/5">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
          <KeyRound className="h-6 w-6" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-900">
          Enter Verification Code
        </h2>
        <p className="mt-1.5 text-xs text-slate-600">
          We sent a 6-digit code to{' '}
          <strong className="text-slate-800">{email}</strong>
        </p>
      </div>

      {error && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {infoMessage && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{infoMessage}</span>
        </div>
      )}

      <form onSubmit={handleManualSubmit} className="space-y-6">
        <div>
          <label className="block text-center text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            6-Digit Verification Code
          </label>
          <div className="flex items-center justify-center gap-2 sm:gap-2.5">
            {digits.map((digit, index) => (
              <input
                key={index}
                ref={(el) => {
                  inputRefs.current[index] = el
                }}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="\d*"
                maxLength={1}
                value={digit}
                disabled={isSubmitting}
                onChange={(e) => handleBoxChange(index, e)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                onPaste={handlePaste}
                className={`h-13 w-11 sm:h-14 sm:w-12 rounded-xl text-center font-mono text-2xl font-bold transition-all border-2 ${
                  digit
                    ? 'border-blue-600 bg-blue-50/30 text-blue-950 ring-2 ring-blue-500/10'
                    : 'border-slate-200 bg-slate-50 text-slate-800 hover:border-slate-300'
                } focus:border-blue-600 focus:bg-white focus:outline-hidden focus:ring-4 focus:ring-blue-500/20 disabled:opacity-50`}
              />
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={isSubmitting || !isComplete}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Verifying Code...</span>
            </>
          ) : (
            <span>Verify & Sign In</span>
          )}
        </button>
      </form>

      <div className="mt-6 flex flex-col items-center gap-3 border-t border-slate-100 pt-5 text-xs text-slate-600">
        <div className="flex items-center gap-1.5">
          <span>Didn&apos;t receive the code?</span>
          <button
            type="button"
            onClick={handleResend}
            disabled={resendCountdown > 0 || isResending}
            className="inline-flex items-center gap-1 font-semibold text-blue-600 hover:text-blue-700 disabled:text-slate-400 disabled:cursor-not-allowed"
          >
            {isResending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RotateCcw className="h-3 w-3" />
            )}
            <span>
              {resendCountdown > 0
                ? `Resend in ${resendCountdown}s`
                : 'Resend code'}
            </span>
          </button>
        </div>

        <button
          type="button"
          onClick={onSwitchToLogin}
          className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-800 transition mt-1"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Sign In</span>
        </button>
      </div>
    </div>
  )
}
