import { useCallback, useMemo, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import type { User } from '../types/auth'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const {
    data: user,
    isLoading,
    refetch,
  } = useQuery<User | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await authApi.getMe()
      } catch {
        return null
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  const loginMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: (data) => {
      queryClient.setQueryData(['auth', 'me'], data.user)
    },
  })

  const registerMutation = useMutation({
    mutationFn: authApi.register,
  })

  const verifyOtpMutation = useMutation({
    mutationFn: authApi.verifyOtp,
    onSuccess: (data) => {
      queryClient.setQueryData(['auth', 'me'], data.user)
    },
  })

  const login = useCallback(
    async (credentials: { email: string; password: string }) => {
      await loginMutation.mutateAsync(credentials)
    },
    [loginMutation],
  )

  const register = useCallback(
    async (payload: {
      email: string
      password: string
      full_name?: string
    }) => {
      const response = await registerMutation.mutateAsync(payload)
      return response.message
    },
    [registerMutation],
  )

  const verifyOtp = useCallback(
    async (payload: { email: string; otp: string }) => {
      await verifyOtpMutation.mutateAsync(payload)
    },
    [verifyOtpMutation],
  )

  const logout = useCallback(async () => {
    await authApi.logout()
    queryClient.setQueryData(['auth', 'me'], null)
  }, [queryClient])

  const logoutAll = useCallback(async () => {
    await authApi.logoutAll()
    queryClient.setQueryData(['auth', 'me'], null)
  }, [queryClient])

  const refetchUser = useCallback(async () => {
    await refetch()
  }, [refetch])

  const value = useMemo(
    () => ({
      user: user ?? null,
      isLoading,
      isAuthenticated: Boolean(user),
      isVerified: Boolean(user?.is_verified),
      login,
      register,
      verifyOtp,
      logout,
      logoutAll,
      refetchUser,
    }),
    [
      user,
      isLoading,
      login,
      register,
      verifyOtp,
      logout,
      logoutAll,
      refetchUser,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
