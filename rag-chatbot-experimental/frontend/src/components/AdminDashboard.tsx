import { AlertTriangle, Database, FileText, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { getSimulatorDocuments, getSimulatorStatus, syncSimulator } from "../services/adminApi";
import type { SimulatorDocument, SimulatorStatus } from "../types/admin";

interface AdminDashboardProps {
  apiBaseUrl?: string;
}

export function AdminDashboard({ apiBaseUrl }: AdminDashboardProps) {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<SimulatorStatus | null>(null);
  const [documents, setDocuments] = useState<SimulatorDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextStatus, nextDocuments] = await Promise.all([
        getSimulatorStatus(apiBaseUrl, token),
        getSimulatorDocuments(apiBaseUrl, token)
      ]);
      setStatus(nextStatus);
      setDocuments(nextDocuments);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Impossible de charger le statut.");
    } finally {
      setLoading(false);
    }
  }

  async function synchronize() {
    setLoading(true);
    setError(null);
    try {
      await syncSimulator(apiBaseUrl, token);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Synchronisation impossible.");
      setLoading(false);
    }
  }

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <p className="admin-eyebrow">POC local</p>
          <h1>Bibliothèque SharePoint simulée</h1>
          <p>Suivi de l’index incrémental, des documents et des erreurs d’ingestion.</p>
        </div>
        <div className="admin-actions">
          <button type="button" className="admin-secondary-button" onClick={refresh} disabled={loading}>
            <RefreshCw size={17} />
            Actualiser
          </button>
          <button type="button" className="admin-primary-button" onClick={synchronize} disabled={loading}>
            <Database size={17} />
            Synchroniser
          </button>
        </div>
      </header>

      <section className="admin-auth-strip">
        <ShieldCheck size={18} />
        <label>
          Token administrateur local
          <input
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Token démo fourni au lancement"
            autoComplete="off"
          />
        </label>
        <span>Aucun token n’est stocké dans le frontend.</span>
      </section>

      {error ? (
        <div className="admin-error">
          <AlertTriangle size={18} />
          {error}
        </div>
      ) : null}

      <section className="admin-metrics" aria-label="Statut de l’index">
        <Metric icon={<FileText size={20} />} label="Documents indexés" value={status?.document_count ?? "—"} />
        <Metric icon={<Database size={20} />} label="Chunks" value={status?.chunk_count ?? "—"} />
        <Metric label="Provider" value={status?.provider ?? "—"} />
        <Metric label="Dernière synchronisation" value={formatDate(status?.last_sync_at)} />
      </section>

      <section className="admin-runtime">
        <div><span>LLM</span><strong>{status?.llm_model ?? "—"}</strong></div>
        <div><span>Embeddings</span><strong>{status?.embedding_model ?? "—"}</strong></div>
        <div><span>Documents</span><strong>{status?.documents_dir ?? "—"}</strong></div>
        <div><span>Vector store</span><strong>{status?.vector_store ?? "—"}</strong></div>
      </section>

      <section className="admin-rag-diagnostics">
        <div className="admin-section-heading">
          <div>
            <h2>Diagnostic RAG</h2>
            <p>Configuration active et dernier retrieval observé par l’API.</p>
          </div>
        </div>
        <div className="admin-diagnostic-grid">
          <Diagnostic label="Recherche" value={status?.rag_diagnostics?.retrieval_mode ?? "—"} />
          <Diagnostic label="Reformulation" value={enabledLabel(status?.rag_diagnostics?.query_rewrite_enabled)} />
          <Diagnostic label="Reranking" value={enabledLabel(status?.rag_diagnostics?.rerank_enabled)} />
          <Diagnostic
            label="Filtrage permissions"
            value={enabledLabel(status?.rag_diagnostics?.permission_filtering_enabled)}
          />
          <Diagnostic
            label="Top-k initial / final"
            value={status?.rag_diagnostics ? `${status.rag_diagnostics.initial_top_k} / ${status.rag_diagnostics.final_top_k}` : "—"}
          />
          <Diagnostic label="Confiance minimale" value={formatScore(status?.rag_diagnostics?.min_confidence)} />
          <Diagnostic label="Dernière confiance" value={formatScore(status?.rag_diagnostics?.latest?.confidence)} />
          <Diagnostic
            label="Chunks initiaux / finaux"
            value={status?.rag_diagnostics?.latest
              ? `${status.rag_diagnostics.latest.retrieved_chunks_initial ?? 0} / ${status.rag_diagnostics.latest.retrieved_chunks_final ?? 0}`
              : "—"}
          />
          <Diagnostic
            label="Dernière décision"
            value={status?.rag_diagnostics?.latest?.refused === undefined
              ? "—"
              : status.rag_diagnostics.latest.refused ? "Refus" : "Réponse"}
          />
        </div>
      </section>

      <section className="admin-document-section">
        <div className="admin-section-heading">
          <div>
            <h2>Documents</h2>
            <p>{documents.length} entrée(s) suivie(s), incluant les suppressions et erreurs.</p>
          </div>
          {loading ? <span className="admin-loading">Mise à jour…</span> : null}
        </div>
        <div className="admin-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Document</th>
                <th>Statut</th>
                <th>Groupes</th>
                <th>Chunks</th>
                <th>Indexé le</th>
                <th>Erreur</th>
              </tr>
            </thead>
            <tbody>
              {documents.length ? documents.map((document) => (
                <tr key={document.document_id}>
                  <td><strong>{document.file_name}</strong><span>{document.source_type}</span></td>
                  <td><span className={`admin-status admin-status-${document.status}`}>{document.status}</span></td>
                  <td>{document.allowed_groups.join(", ")}</td>
                  <td>{document.chunk_count}</td>
                  <td>{formatDate(document.indexed_at)}</td>
                  <td>{document.error || "—"}</td>
                </tr>
              )) : (
                <tr><td colSpan={6} className="admin-empty">Actualisez pour charger l’état du simulateur.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon?: ReactNode; label: string; value: string | number }) {
  return <div className="admin-metric">{icon}<span>{label}</span><strong>{value}</strong></div>;
}

function Diagnostic({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function enabledLabel(value?: boolean): string {
  return value === undefined ? "—" : value ? "Activé" : "Désactivé";
}

function formatScore(value?: number): string {
  return value === undefined ? "—" : value.toFixed(3);
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("fr-CA", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
