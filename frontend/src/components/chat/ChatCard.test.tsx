import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatCard } from './ChatCard'
import { chatApi, ChatApiError } from '../../api/chat'
import { AuthContext } from '../../context/auth-context'
import type { User } from '../../types/auth'

const mockVerifiedUser: User = {
  id: 'user-123',
  email: 'analyst@example.com',
  is_active: true,
  is_verified: true,
  role: 'user',
  auth_provider: 'local',
  created_at: new Date().toISOString(),
}

const mockUnverifiedUser: User = {
  ...mockVerifiedUser,
  email: 'unverified@example.com',
  is_verified: false,
}

function renderWithAuth(
  ui: React.ReactElement,
  authValues: {
    user: User | null
    isAuthenticated: boolean
    isVerified: boolean
  },
) {
  return render(
    <AuthContext.Provider
      value={{
        user: authValues.user,
        isAuthenticated: authValues.isAuthenticated,
        isVerified: authValues.isVerified,
        isLoading: false,
        login: vi.fn(),
        logout: vi.fn(),
        logoutAll: vi.fn(),
        register: vi.fn(),
        verifyOtp: vi.fn(),
        refetchUser: vi.fn(),
      }}
    >
      {ui}
    </AuthContext.Provider>,
  )
}

describe('ChatCard AI Operations Analyst', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders header, gpt-4o-mini model badge, and suggestions when empty', () => {
    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={vi.fn()} />, {
      user: mockVerifiedUser,
      isAuthenticated: true,
      isVerified: true,
    })

    expect(screen.getByText('AI Operations Analyst')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument()
    expect(screen.getByText('Ask Business Questions')).toBeInTheDocument()
    expect(
      screen.getByText(
        /What was invoiced revenue and collected cash in September 2026\?/i,
      ),
    ).toBeInTheDocument()
  })

  it('displays authentication required banner when not authenticated', () => {
    const onOpenAuth = vi.fn()
    renderWithAuth(<ChatCard onOpenAuth={onOpenAuth} onOpenOtp={vi.fn()} />, {
      user: null,
      isAuthenticated: false,
      isVerified: false,
    })

    expect(screen.getByText('Authentication Required')).toBeInTheDocument()
    const logInBtn = screen.getByRole('button', { name: /^log in$/i })
    fireEvent.click(logInBtn)
    expect(onOpenAuth).toHaveBeenCalledTimes(1)
  })

  it('displays email verification required banner when user is not verified', () => {
    const onOpenOtp = vi.fn()
    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={onOpenOtp} />, {
      user: mockUnverifiedUser,
      isAuthenticated: true,
      isVerified: false,
    })

    expect(screen.getByText('Email Verification Required')).toBeInTheDocument()
    const verifyBtn = screen.getByRole('button', { name: /^verify email$/i })
    fireEvent.click(verifyBtn)
    expect(onOpenOtp).toHaveBeenCalledTimes(1)
  })

  it('submits a question via input, displays user bubble, assistant answer, and tool traces', async () => {
    vi.spyOn(chatApi, 'sendMessage').mockResolvedValueOnce({
      answer:
        'In September 2026, total invoiced revenue was USD 1,550.00 and collected was USD 1,000.00.',
      status: 'ok',
      as_of: '2026-10-22',
      correlation_id: 'corr-12345678',
      tool_calls: [
        {
          name: 'get_revenue_summary',
          ok: true,
          arguments: { start_date: '2026-09-01', end_date: '2026-09-30' },
          result: {
            has_data: true,
            totals: [
              { currency: 'USD', invoiced: '1550.00', collected: '1000.00' },
            ],
          },
        },
      ],
      usage: { model: 'gpt-4o-mini', input_tokens: 150, output_tokens: 45 },
    })

    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={vi.fn()} />, {
      user: mockVerifiedUser,
      isAuthenticated: true,
      isVerified: true,
    })

    const textarea = screen.getByPlaceholderText(/Ask about customer balances/i)
    fireEvent.change(textarea, {
      target: { value: 'What was our revenue in September?' },
    })

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    fireEvent.click(sendBtn)

    // User message shown
    expect(
      screen.getByText('What was our revenue in September?'),
    ).toBeInTheDocument()

    // Await assistant answer
    await waitFor(() => {
      expect(
        screen.getByText(/total invoiced revenue was USD 1,550.00/i),
      ).toBeInTheDocument()
    })

    // Grounded status badge
    expect(screen.getByText('Verified via PostgreSQL')).toBeInTheDocument()

    // Tool call pill rendered
    expect(screen.getByText('Revenue Summary')).toBeInTheDocument()

    // Expand tool call details
    const toolBtn = screen.getByRole('button', { name: /revenue summary/i })
    fireEvent.click(toolBtn)

    expect(screen.getByText('Validated Parameters:')).toBeInTheDocument()
    expect(screen.getByText('2026-09-01')).toBeInTheDocument()
    expect(screen.getByText('Query Results:')).toBeInTheDocument()
  })

  it('submits a suggested question directly when clicked', async () => {
    vi.spyOn(chatApi, 'sendMessage').mockResolvedValueOnce({
      answer: 'Overdue invoices found: 2 invoices totaling USD 463.45.',
      status: 'ok',
      as_of: '2026-10-22',
      correlation_id: 'corr-87654321',
      tool_calls: [
        {
          name: 'list_unpaid_invoices',
          ok: true,
          arguments: { overdue_only: true },
          result: { total_matching: 2, returned: 2, overdue_only: true },
        },
      ],
      usage: { model: 'gpt-4o-mini', input_tokens: 120, output_tokens: 30 },
    })

    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={vi.fn()} />, {
      user: mockVerifiedUser,
      isAuthenticated: true,
      isVerified: true,
    })

    const suggestionBtn = screen.getByRole('button', {
      name: /Which invoices are currently overdue and by how many days\?/i,
    })
    fireEvent.click(suggestionBtn)

    await waitFor(() => {
      expect(
        screen.getByText(/Overdue invoices found: 2 invoices/i),
      ).toBeInTheDocument()
    })
    expect(screen.getByText('Unpaid & Overdue Invoices')).toBeInTheDocument()
  })

  it('handles LLM not configured (503) error and displays helpful error banner', async () => {
    vi.spyOn(chatApi, 'sendMessage').mockRejectedValueOnce(
      new ChatApiError(
        'The AI assistant is not configured on this server (OPENAI_API_KEY is missing).',
        'llm_not_configured',
        'corr-err-999',
      ),
    )

    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={vi.fn()} />, {
      user: mockVerifiedUser,
      isAuthenticated: true,
      isVerified: true,
    })

    const textarea = screen.getByPlaceholderText(/Ask about customer balances/i)
    fireEvent.change(textarea, { target: { value: 'How much revenue?' } })

    const sendBtn = screen.getByRole('button', { name: /send message/i })
    fireEvent.click(sendBtn)

    await waitFor(() => {
      expect(
        screen.getAllByText(/OPENAI_API_KEY is missing/i).length,
      ).toBeGreaterThan(0)
    })
    expect(screen.getByText(/Request ID: corr-err-999/i)).toBeInTheDocument()
  })

  it('allows clearing conversation history', async () => {
    vi.spyOn(chatApi, 'sendMessage').mockResolvedValueOnce({
      answer: 'Trend is positive.',
      status: 'ok',
      as_of: '2026-10-22',
      correlation_id: 'corr-trend-1',
      tool_calls: [],
      usage: null,
    })

    renderWithAuth(<ChatCard onOpenAuth={vi.fn()} onOpenOtp={vi.fn()} />, {
      user: mockVerifiedUser,
      isAuthenticated: true,
      isVerified: true,
    })

    const textarea = screen.getByPlaceholderText(/Ask about customer balances/i)
    fireEvent.change(textarea, { target: { value: 'Show trend' } })
    fireEvent.click(screen.getByRole('button', { name: /send message/i }))

    await waitFor(() => {
      expect(screen.getByText('Trend is positive.')).toBeInTheDocument()
    })

    const clearBtn = screen.getByRole('button', { name: /clear chat/i })
    fireEvent.click(clearBtn)

    expect(screen.queryByText('Trend is positive.')).not.toBeInTheDocument()
    expect(screen.getByText('Ask Business Questions')).toBeInTheDocument()
  })
})
