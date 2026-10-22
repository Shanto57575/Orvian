import { apiRequest } from './auth'
import type { ChatRequest, ChatResponse } from '../types/chat'

export class ChatApiError extends Error {
  code: string
  correlationId?: string

  constructor(message: string, code = 'unknown_error', correlationId?: string) {
    super(message)
    this.name = 'ChatApiError'
    this.code = code
    this.correlationId = correlationId
  }
}

export const chatApi = {
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    try {
      return await apiRequest<ChatResponse>('/api/v1/chat', {
        method: 'POST',
        body: JSON.stringify(request),
      })
    } catch (err: unknown) {
      // Parse structured FastAPI HTTPException detail if available
      if (err instanceof Error) {
        try {
          const parsed = JSON.parse(err.message)
          if (parsed && typeof parsed === 'object') {
            const code = parsed.code || 'error'
            const message = parsed.message || err.message
            const correlationId = parsed.correlation_id
            throw new ChatApiError(message, code, correlationId)
          }
        } catch {
          // err.message is not JSON; check for known status strings
          if (err.message.includes('401')) {
            throw new ChatApiError(
              'Authentication required. Please sign in.',
              'unauthorized',
            )
          }
          if (
            err.message.includes('403') ||
            err.message.toLowerCase().includes('verification required')
          ) {
            throw new ChatApiError(
              'Email verification required before accessing business data.',
              'verification_required',
            )
          }
          if (err.message.includes('429')) {
            throw new ChatApiError(
              'Rate limit exceeded. Please wait a minute before trying again.',
              'rate_limited',
            )
          }
          throw new ChatApiError(err.message)
        }
      }
      throw new ChatApiError(
        'An unexpected error occurred while communicating with the assistant.',
      )
    }
  },
}
