import type { Source } from "../types/chat";

interface SourcesPanelProps {
  sources: Source[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <details className="sources-panel">
      <summary>Sources ({sources.length})</summary>
      <div className="sources-list">
        {sources.map((source) => (
          <div className="source-item" key={`${source.file_name}-${source.chunk_id}`}>
            <div className="source-title">
              <strong>{source.file_name}</strong>
              {source.page ? <span>page {source.page}</span> : null}
              <span>{source.chunk_id}</span>
            </div>
            <p>{source.excerpt}</p>
            {typeof source.score === "number" ? <small>Score {source.score.toFixed(2)}</small> : null}
          </div>
        ))}
      </div>
    </details>
  );
}
