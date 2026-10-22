import type {
  AuthResponse,
  GoogleAuthResponse,
  MessageResponse,
  User,
  UserSessionInfo,
} from '../types/auth'

function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/(?:^|;\s*)orvian_csrf=([^;]+)/)
  return match?.[1] ? decodeURIComponent(match[1]) : null
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  const method = (options.method || 'GET').toUpperCase()
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    const csrfToken = getCsrfToken()
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    }
  }

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: 'include',
  })

  let data: unknown
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    data = await response.json()
  }

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`
    if (data && typeof data === 'object' && 'detail' in data) {
      errorMessage = String((data as { detail: unknown }).detail)
    }
    throw new Error(errorMessage)
  }

  return data as T
}

export const authApi = {
  async register(body: {
    email: string
    password: string
    full_name?: string
  }): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  async verifyOtp(body: { email: string; otp: string }): Promise<AuthResponse> {
    return apiRequest<AuthResponse>('/api/v1/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  async resendOtp(email: string): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/resend-otp', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async login(body: {
    email: string
    password: string
  }): Promise<AuthResponse> {
    return apiRequest<AuthResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  async logout(): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/logout', {
      method: 'POST',
    })
  },

  async logoutAll(): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/logout-all', {
      method: 'POST',
    })
  },

  async getMe(): Promise<User> {
    return apiRequest<User>('/api/v1/auth/me', {
      method: 'GET',
    })
  },

  async getSessions(): Promise<UserSessionInfo[]> {
    return apiRequest<UserSessionInfo[]>('/api/v1/auth/sessions', {
      method: 'GET',
    })
  },

  async verifyEmail(token: string): Promise<AuthResponse> {
    return apiRequest<AuthResponse>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    })
  },

  async resendVerification(email: string): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async forgotPassword(email: string): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  async resetPassword(body: {
    token: string
    new_password: string
  }): Promise<MessageResponse> {
    return apiRequest<MessageResponse>('/api/v1/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  async getGoogleLoginUrl(): Promise<GoogleAuthResponse> {
    return apiRequest<GoogleAuthResponse>('/api/v1/auth/google/login', {
      method: 'GET',
    })
  },

  async checkProtectedVerification(): Promise<{
    status: string
    message: string
  }> {
    return apiRequest<{ status: string; message: string }>(
      '/api/v1/auth/protected-verification-check',
      { method: 'GET' },
    )
  },
}
