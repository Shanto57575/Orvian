import { createContext } from 'react'
import type { User } from '../types/auth'

export interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  isVerified: boolean
  login: (credentials: { email: string; password: string }) => Promise<void>
  register: (payload: {
    email: string
    password: string
    full_name?: string
  }) => Promise<string>
  verifyOtp: (payload: { email: string; otp: string }) => Promise<void>
  logout: () => Promise<void>
  logoutAll: () => Promise<void>
  refetchUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined)
