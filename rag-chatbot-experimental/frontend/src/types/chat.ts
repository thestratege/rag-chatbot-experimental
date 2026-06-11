export type Intent =
  | "greeting"
  | "small_talk"
  | "capability_question"
  | "rag_question"
  | "clarification_needed"
  | "out_of_scope"
  | "unknown";

export type Provider = "mock" | "retrieval_only" | "openrouter" | "ollama";

export interface Source {
  file_name: string;
  page: string | null;
  chunk_id: string;
  excerpt: string;
  score: number | null;
}

export interface ChatApiRequest {
  conversation_id: string | null;
  message: string;
  mode: "auto";
}

export interface ChatApiResponse {
  conversation_id: string;
  answer: string;
  intent: Intent;
  used_rag: boolean;
  sources: Source[];
  provider: Provider;
  routing_profile?: string | null;
  routing_score?: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: Intent;
  usedRag?: boolean;
  provider?: Provider;
  sources?: Source[];
  isError?: boolean;
}

export type WidgetTheme = "default" | "ism";

export interface WidgetConfig {
  apiBaseUrl?: string;
  theme: WidgetTheme;
  title: string;
  providerLabel?: string;
  compact: boolean;
  embed: boolean;
}
