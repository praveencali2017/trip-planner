/** Server-sent events emitted by POST /api/chat — mirrors `streaming.ChatEvent` on the backend. */
export type ChatEvent =
  | { name: 'token'; data: { text: string } }
  | { name: 'status'; data: { message: string } }
  | { name: 'error'; data: { message: string } }
  | { name: 'done'; data: Record<string, never> }

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
}
