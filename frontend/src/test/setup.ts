import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// Default mock for global.fetch in JSDOM environment
global.fetch = vi.fn().mockImplementation((url: string | URL | Request) => {
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
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )
  }

  if (urlStr.includes('/api/v1/auth/me')) {
    return Promise.resolve(
      new Response(JSON.stringify({ detail: 'Not authenticated' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  }

  return Promise.resolve(
    new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
})
