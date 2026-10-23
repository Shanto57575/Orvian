/**
 * Types for the Orvian AI Operations Analyst Chat Interface.
 * Mirrors backend Pydantic schemas in backend/app/schemas/chat.py.
 */

export interface ToolCallTrace {
  name: string
  ok: boolean
  arguments?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  error_code?: string | null
}

export interface DocumentCitation {
  citation_id: string
  doc_key: string
  document_title: string
  category: string
  version: string
  effective_date: string
  section_title: string
  page_number: number
  similarity_score: number
  excerpt: string
}

export interface ChatUsage {
  model: string
  input_tokens: number
  output_tokens: number
}

export type ChatResponseStatus =
  | 'ok'
  | 'no_data'
  | 'limit_reached'
  | 'ungrounded'

export interface ChatResponse {
  answer: string
  status: ChatResponseStatus
  as_of: string
  tool_calls: ToolCallTrace[]
  citations?: DocumentCitation[]
  usage?: ChatUsage | null
  correlation_id: string
}

export interface ChatRequest {
  message: string
}

export interface ChatErrorDetail {
  code: string
  message: string
  correlation_id?: string
}

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: ChatResponseStatus | 'error'
  as_of?: string
  tool_calls?: ToolCallTrace[]
  citations?: DocumentCitation[]
  usage?: ChatUsage | null
  correlation_id?: string
  timestamp: string
  error?: string
}
