# Portfolio technical audit

Audit date: 2026-10-25. Source reviewed: `5b49233d439ec5179e75a433e7480a77f2e7a368` on `main`. The application root is the nested `rag-chatbot-experimental/` directory.

## Implemented architecture

```text
Documents -> loader -> character-based chunks -> Ollama embeddings -> ChromaDB
React widget -> FastAPI -> intent routing / conversation history
Documentary question -> vector + lexical retrieval -> heuristic reranking
                     -> confidence checks -> local LLM -> answer with sources
```

Relevant modules:

| Concern | Source |
| --- | --- |
| Ingestion | `app/document_loader.py`, `app/chunker.py`, `app/embeddings.py` |
| Vector storage | `app/vector_store.py` |
| Retrieval | `app/hybrid_retriever.py`, `app/retriever.py`, `app/reranker.py` |
| Optional question rewriting and orchestration | `app/query_rewriter.py`, `app/rag_pipeline.py` |
| API and authentication | `api/main.py`, `app/auth.py` |
| User interface | React/TypeScript/Vite in `frontend/` |
| Administration | Streamlit in `ui/` |
| Local integration simulation | `app/sharepoint_simulator.py` |

Mock and retrieval-only modes support demonstrations. Optional OpenRouter benchmarking is separated from the local documentary path and uses fictional contexts by default.

## Important documentation correction

The final README section “Limites de cette V1” is older than several current modules. In particular, the source already contains hybrid retrieval, heuristic reranking, mock authentication and a local incremental-index simulator. The older claims that all of these are absent should not be used to describe the present code.

The specific limits still apply:

- `app/auth.py` returns HTTP 501 for Entra authentication: real JWT signature/issuer/audience validation is not implemented.
- The SharePoint library is simulated locally; this is not a live Microsoft Graph or SPFx integration.
- `app/config.py` defaults authentication and document permission filtering to disabled for the local POC.
- Mock tokens are a demonstration mechanism, not production identity.
- Real-world answer quality, access-control assurance, latency and production deployment have not been established by this audit.

## Verification performed

Static Python AST parsing passed for 49 Python files in the reviewed source, scripts, UI and tests. The large `scripts/benchmark_openrouter_models.py` runner was excluded from this static check.

The tree contains 17 Python test modules and frontend scripts `test:assistant-content` and `test:chat-api`. Their existence is not a passing test result.

Not executed during this audit: `pytest`, Node tests, frontend build, Ollama inference, ChromaDB runtime, OpenRouter calls, live SharePoint/Entra integration, quality evaluations and latency benchmarks. `benchmarks/results/` contains only a placeholder at the reviewed revision; no measured result is claimed.

## Reproducibility checklist for the next run

1. Use an isolated environment and fictional sample documents.
2. Install the declared Python and frontend dependencies.
3. Run `pytest` from the nested application root.
4. Run the two frontend test scripts and `npm run build` inside `frontend/`.
5. Record model/version, hardware, dataset and configuration before any RAG benchmark.
6. Verify Entra/Graph separately when those integrations are implemented.

Do not publish internal documents, credentials or employer material merely because this repository is public.

## Résumé français

POC documentaire modulaire avec FastAPI, React, Ollama et ChromaDB. Les modules comprennent recherche hybride, reranking heuristique et citations. Les tests sont présents mais leur réussite n'est pas attestée ici. Entra ID réel, Microsoft Graph et une validation production restent à réaliser; aucun résultat chiffré n'est inventé.
