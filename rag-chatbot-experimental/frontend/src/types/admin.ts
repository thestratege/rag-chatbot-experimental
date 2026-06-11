export interface SyncSummary {
  added: number;
  modified: number;
  deleted: number;
  unchanged: number;
  chunks_added: number;
  chunks_deleted: number;
  errors: number;
}

export interface SimulatorStatus {
  vector_store: string;
  documents_dir: string;
  document_count: number;
  chunk_count: number;
  last_sync_at: string | null;
  last_sync_summary: SyncSummary;
  provider: string;
  llm_model: string;
  embedding_model: string;
  rag_diagnostics?: {
    retrieval_mode: string;
    query_rewrite_enabled: boolean;
    rerank_enabled: boolean;
    permission_filtering_enabled: boolean;
    initial_top_k: number;
    final_top_k: number;
    min_confidence: number;
    latest?: {
      question_original?: string;
      question_rewritten?: string;
      query_rewrite_used?: boolean;
      retrieved_chunks_initial?: number;
      retrieved_chunks_final?: number;
      confidence?: number;
      refused?: boolean;
    };
  };
}

export interface SimulatorDocument {
  document_id: string;
  file_name: string;
  source_type: string;
  chunk_count: number;
  last_modified: string;
  indexed_at: string | null;
  status: "indexed" | "deleted" | "error";
  allowed_groups: string[];
  error: string | null;
}
