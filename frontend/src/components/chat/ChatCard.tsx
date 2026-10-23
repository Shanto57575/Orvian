import { useState, useRef, useEffect } from 'react'
import {
  Send,
  Sparkles,
  Bot,
  User,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Database,
  Lock,
  Mail,
  Loader2,
  HelpCircle,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react'
import { chatApi, ChatApiError } from '../../api/chat'
import { useAuth } from '../../context/useAuth'
import type { ChatMessageItem } from '../../types/chat'
import { CitationList } from './CitationList'
import { ToolTraceCard } from './ToolTraceCard'

const SUGGESTED_QUESTIONS = [
  'What was invoiced revenue and collected cash in September 2026?',
  'Which invoices are currently overdue and by how many days?',
  'Which overdue invoices breach company collections policy and what tier applies?',
  'What are standard net payment terms and credit limits by customer segment?',
]

interface ChatCardProps {
  onOpenAuth: () => void
  onOpenOtp: () => void
}

export function ChatCard({ onOpenAuth, onOpenOtp }: ChatCardProps) {
  const { isAuthenticated, isVerified } = useAuth()
  const [messages, setMessages] = useState<ChatMessageItem[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<{
    message: string
    code?: string
    correlationId?: string
  } | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }

  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom()
    }
  }, [messages, isLoading])

  const handleSend = async (messageText?: string) => {
    const textToSend = (messageText ?? inputValue).trim()
    if (!textToSend || isLoading) return

    setApiError(null)

    // User message
    const userMsg: ChatMessageItem = {
      id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
    }

    setMessages((prev) => [...prev, userMsg])
    setInputValue('')
    setIsLoading(true)

    try {
      const response = await chatApi.sendMessage({ message: textToSend })

      const assistantMsg: ChatMessageItem = {
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + 1),
        role: 'assistant',
        content: response.answer,
        status: response.status,
        as_of: response.as_of,
        tool_calls: response.tool_calls,
        citations: response.citations ?? [],
        usage: response.usage,
        correlation_id: response.correlation_id,
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
      }

      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: unknown) {
      if (err instanceof ChatApiError) {
        setApiError({
          message: err.message,
          code: err.code,
          correlationId: err.correlationId,
        })
        const errorMsg: ChatMessageItem = {
          id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + 1),
          role: 'assistant',
          content: err.message,
          status: 'error',
          correlation_id: err.correlationId,
          timestamp: new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          }),
          error: err.code,
        }
        setMessages((prev) => [...prev, errorMsg])
      } else {
        const errorMsg: ChatMessageItem = {
          id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + 1),
          role: 'assistant',
          content:
            err instanceof Error
              ? err.message
              : 'An unexpected error occurred.',
          status: 'error',
          timestamp: new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          }),
        }
        setMessages((prev) => [...prev, errorMsg])
      }
    } finally {
      setIsLoading(false)
      // Focus textarea back
      textareaRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClearHistory = () => {
    setMessages([])
    setApiError(null)
  }

  const renderStatusBadge = (status?: string) => {
    switch (status) {
      case 'ok':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3" />
            Verified via PostgreSQL
          </span>
        )
      case 'no_data':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-[10px] font-semibold text-blue-700 border border-blue-200">
            <Database className="h-3 w-3" />
            No Records Found
          </span>
        )
      case 'limit_reached':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-[10px] font-semibold text-amber-700 border border-amber-200">
            <AlertCircle className="h-3 w-3" />
            Tool Limit Reached
          </span>
        )
      case 'ungrounded':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-[10px] font-semibold text-purple-700 border border-purple-200">
            <ShieldCheck className="h-3 w-3" />
            Grounded Guard Refusal
          </span>
        )
      case 'error':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-50 text-[10px] font-semibold text-rose-700 border border-rose-200">
            <AlertCircle className="h-3 w-3" />
            Error
          </span>
        )
      default:
        return null
    }
  }

  return (
    <div className="flex flex-col h-[680px] rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden font-sans">
      {/* Top Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/70 backdrop-blur-xs">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-sm text-slate-900">
                AI Operations Analyst
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                gpt-4o-mini
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Read-only PostgreSQL + pgvector policy RAG assistant &middot;
              Parameterized tools only
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClearHistory}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition"
              title="Reset conversation history"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Clear Chat</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Conversation Container */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5 bg-gradient-to-b from-slate-50/30 to-white">
        {/* State Banners: Unauthenticated */}
        {!isAuthenticated && (
          <div className="flex items-start justify-between gap-4 p-4 rounded-xl border border-blue-200 bg-blue-50/80 text-xs text-blue-900">
            <div className="flex items-start gap-3">
              <Lock className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-sm text-blue-950">
                  Authentication Required
                </p>
                <p className="mt-0.5 text-blue-800 leading-relaxed">
                  Sign in to query synthetic accounts receivable, invoices,
                  payments, and company policy documents.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onOpenAuth}
              className="shrink-0 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 shadow-xs transition"
            >
              Log In
            </button>
          </div>
        )}

        {/* State Banners: Unverified */}
        {isAuthenticated && !isVerified && (
          <div className="flex items-start justify-between gap-4 p-4 rounded-xl border border-amber-200 bg-amber-50/80 text-xs text-amber-900">
            <div className="flex items-start gap-3">
              <Mail className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-sm text-amber-950">
                  Email Verification Required
                </p>
                <p className="mt-0.5 text-amber-800 leading-relaxed">
                  Access to financial queries requires verified email
                  credentials. Please enter your 6-digit OTP code to continue.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onOpenOtp}
              className="shrink-0 px-3 py-1.5 rounded-lg bg-amber-600 text-white font-semibold text-xs hover:bg-amber-700 shadow-xs transition"
            >
              Verify Email
            </button>
          </div>
        )}

        {/* Empty State / Suggestions */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full py-8 text-center max-w-lg mx-auto">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 mb-3 shadow-xs">
              <Sparkles className="h-6 w-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">
              Ask Business Questions
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm leading-relaxed">
              Orvian answers queries directly from verified customer/invoice
              database records and cited company policy documents. No
              model-generated SQL is ever executed.
            </p>

            <div className="w-full mt-6 space-y-2 text-left">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider px-1">
                <HelpCircle className="h-3.5 w-3.5" />
                <span>Suggested Questions</span>
              </div>
              <div className="grid grid-cols-1 gap-2">
                {SUGGESTED_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    type="button"
                    disabled={!isAuthenticated || !isVerified || isLoading}
                    onClick={() => handleSend(question)}
                    className="group flex items-center justify-between p-3 rounded-xl border border-slate-200/90 bg-white hover:border-blue-300 hover:bg-blue-50/40 text-left transition shadow-2xs disabled:opacity-50 disabled:pointer-events-none"
                  >
                    <span className="text-xs text-slate-700 group-hover:text-blue-900 leading-snug">
                      {question}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-300 group-hover:text-blue-600 shrink-0 ml-2 transition-transform group-hover:translate-x-0.5" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Message Thread */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs">
                <Bot className="h-4 w-4" />
              </div>
            )}

            <div
              className={`flex flex-col max-w-[85%] sm:max-w-[75%] rounded-2xl p-4 space-y-2 text-xs leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-xs shadow-xs'
                  : 'bg-white border border-slate-200/90 text-slate-800 rounded-bl-xs shadow-xs'
              }`}
            >
              {/* Header for assistant message */}
              {msg.role === 'assistant' && (
                <div className="flex items-center justify-between gap-2 pb-1 border-b border-slate-100">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-slate-900 text-xs">
                      Orvian Analyst
                    </span>
                    {renderStatusBadge(msg.status)}
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {msg.timestamp}
                  </span>
                </div>
              )}

              {/* Message Content */}
              <div className="whitespace-pre-wrap font-sans text-xs">
                {msg.content}
              </div>

              {/* Verified Policy Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <CitationList citations={msg.citations} />
              )}

              {/* Tool Execution Drawer */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="pt-2 border-t border-slate-100 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                    <Database className="h-3 w-3" />
                    <span>
                      Database & Policy Queries Executed ({msg.tool_calls.length}
                      ):
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {msg.tool_calls.map((trace, idx) => (
                      <ToolTraceCard
                        key={`${trace.name}-${idx}`}
                        trace={trace}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Assistant Message Telemetry Footer */}
              {msg.role === 'assistant' &&
                (msg.usage || msg.correlation_id || msg.as_of) && (
                  <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400 font-mono">
                    <div className="flex items-center gap-2">
                      {msg.as_of && <span>as_of: {msg.as_of}</span>}
                      {msg.usage && (
                        <span>
                          tokens: {msg.usage.input_tokens}in /{' '}
                          {msg.usage.output_tokens}out
                        </span>
                      )}
                    </div>
                    {msg.correlation_id && (
                      <span
                        className="truncate max-w-[140px]"
                        title={msg.correlation_id}
                      >
                        id: {msg.correlation_id.slice(0, 12)}...
                      </span>
                    )}
                  </div>
                )}
            </div>

            {msg.role === 'user' && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white shadow-xs">
                <User className="h-4 w-4" />
              </div>
            )}
          </div>
        ))}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs">
              <Bot className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-2.5 rounded-2xl bg-white border border-slate-200 p-3.5 text-xs text-slate-600 shadow-xs">
              <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              <span>
                Querying read-only business data & policy documents...
              </span>
            </div>
          </div>
        )}

        {/* API Error Callout */}
        {apiError && (
          <div className="p-3 rounded-xl border border-rose-200 bg-rose-50 text-xs text-rose-900 flex items-start gap-2.5">
            <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-rose-950">
                Query Failed: {apiError.code || 'Error'}
              </p>
              <p className="mt-0.5 text-rose-800">{apiError.message}</p>
              {apiError.correlationId && (
                <p className="mt-1 font-mono text-[10px] text-rose-600">
                  Request ID: {apiError.correlationId}
                </p>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form Bar */}
      <div className="p-4 border-t border-slate-100 bg-white">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            handleSend()
          }}
          className="relative flex flex-col gap-2"
        >
          <div className="relative flex items-center">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!isAuthenticated || !isVerified || isLoading}
              placeholder={
                !isAuthenticated
                  ? 'Please sign in to ask business questions...'
                  : !isVerified
                    ? 'Email verification required before sending queries...'
                    : 'Ask about customer balances, invoices, collected revenue, or company policies... (Enter to send)'
              }
              rows={2}
              maxLength={2000}
              className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 pr-20 text-xs text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-50 transition"
            />
            <div className="absolute right-2.5 bottom-2.5 flex items-center gap-1.5">
              <button
                type="submit"
                disabled={
                  !inputValue.trim() ||
                  !isAuthenticated ||
                  !isVerified ||
                  isLoading
                }
                className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs transition hover:bg-blue-700 disabled:opacity-40 disabled:hover:bg-blue-600"
                aria-label="Send message"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
            <span>Enter to send &middot; Shift + Enter for newline</span>
            <span
              className={
                inputValue.length > 1800 ? 'text-amber-600 font-semibold' : ''
              }
            >
              {inputValue.length} / 2000
            </span>
          </div>
        </form>
      </div>
    </div>
  )
}
