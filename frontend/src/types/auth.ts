export interface User {
  id: string
  email: string
  full_name?: string | null
  is_active: boolean
  is_verified: boolean
  role: 'user' | 'admin'
  auth_provider: 'local' | 'google'
  created_at: string
}

export interface UserSessionInfo {
  id: string
  ip_address?: string | null
  user_agent?: string | null
  created_at: string
  expires_at: string
}

export interface AuthResponse {
  message: string
  user: User
}

export interface MessageResponse {
  message: string
}

export interface RegisterResponse {
  message: string
  email: string
  dev_otp?: string | null
}

export interface VerifyOtpRequest {
  email: string
  otp: string
}

export interface GoogleAuthResponse {
  authorization_url: string
  state: string
}

export interface ApiError {
  detail: string
}
