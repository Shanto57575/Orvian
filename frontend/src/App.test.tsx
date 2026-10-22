import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { queryClient } from './lib/queryClient'

describe('App Authentication & Shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    queryClient.clear()
  })

  it('renders Orvian header, title, and security invariants', () => {
    render(<App />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Synthetic Business Data Assistant',
    )
    expect(screen.getByText('API Health')).toBeInTheDocument()
    expect(screen.getByText('Account Status')).toBeInTheDocument()
    expect(screen.getByText('Security Invariants')).toBeInTheDocument()
    expect(screen.getByText('Synthetic Business Data Only')).toBeInTheDocument()
  })

  it('renders Sign In button when unauthenticated', () => {
    render(<App />)

    const signInButton = screen.getByRole('button', { name: /sign in/i })
    expect(signInButton).toBeInTheDocument()
  })

  it('opens login dialog when Sign In is clicked and allows toggling to register', () => {
    render(<App />)

    const signInButton = screen.getByRole('button', { name: /sign in/i })
    fireEvent.click(signInButton)

    // Check login modal appeared
    expect(
      screen.getByRole('heading', { name: /sign in to orvian/i }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()

    // Switch to registration form
    const createAccountButton = screen.getByRole('button', {
      name: /create account/i,
    })
    fireEvent.click(createAccountButton)

    expect(
      screen.getByRole('heading', { name: /create an account/i }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument()
  })

  it('initiates Google login via direct browser navigation', () => {
    Object.defineProperty(window, 'location', {
      value: { ...window.location, href: '' },
      writable: true,
      configurable: true,
    })

    render(<App />)
    const signInButton = screen.getByRole('button', { name: /sign in/i })
    fireEvent.click(signInButton)

    const googleBtn = screen.getByRole('button', { name: /google account/i })
    fireEvent.click(googleBtn)

    expect(window.location.href).toBe('/api/v1/auth/google/login')
  })

  it('preserves authenticated UI state when logout fails and displays actionable error', async () => {
    // Mock authenticated user
    vi.spyOn(global, 'fetch').mockImplementation(
      (url: string | URL | Request) => {
        const urlStr = typeof url === 'string' ? url : url.toString()
        if (urlStr.includes('/api/v1/health')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                status: 'ok',
                project: 'orvian-backend',
                environment: 'development',
                debug: true,
              }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/api/v1/auth/me')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: '123e4567-e89b-12d3-a456-426614174000',
                email: 'operator@example.com',
                full_name: 'Operator User',
                is_active: true,
                is_verified: true,
                role: 'user',
                auth_provider: 'local',
                created_at: new Date().toISOString(),
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          )
        }
        if (urlStr.includes('/api/v1/auth/logout')) {
          // Server failure on logout
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            }),
          )
        }
        return Promise.resolve(
          new Response(JSON.stringify({}), { status: 200 }),
        )
      },
    )

    render(<App />)

    // Await user authentication state
    await waitFor(() => {
      expect(
        screen.getAllByText('operator@example.com').length,
      ).toBeGreaterThan(0)
    })

    // Open UserMenu
    const userMenuBtn = screen.getByRole('button', { name: /ou/i })
    fireEvent.click(userMenuBtn)

    // Click Sign Out
    const signOutBtn = screen.getByRole('button', { name: /^sign out$/i })
    fireEvent.click(signOutBtn)

    // User must remain authenticated in UI, and actionable error shown
    await waitFor(() => {
      expect(
        screen.getByText(/failed to sign out on the server/i),
      ).toBeInTheDocument()
      expect(
        screen.getAllByText('operator@example.com').length,
      ).toBeGreaterThan(0)
    })
  })
})
