from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.rag_pipeline import RAGPipeline  # noqa: E402


st.set_page_config(page_title="Chatbot RAG local", layout="wide")


@st.cache_resource(show_spinner=False)
def get_pipeline() -> RAGPipeline:
    return RAGPipeline(settings)


pipeline = get_pipeline()

st.title("Chatbot documentaire RAG local")

with st.sidebar:
    st.subheader("Configuration")
    st.write(f"LLM : `{settings.ollama_llm_model}`")
    st.write(f"Embeddings : `{settings.ollama_embedding_model}`")
    st.write(f"Vector DB : `{settings.vector_db_type}`")
    st.write(f"Top K : `{settings.top_k}`")
    st.divider()

    if st.button("Lancer l'ingestion", width="stretch"):
        with st.spinner("Ingestion des documents en cours..."):
            try:
                result = pipeline.ingest_documents()
                st.success(
                    f"{result.chunks_indexed} chunk(s) indexé(s) "
                    f"depuis {result.documents_loaded} partie(s) documentaire(s)."
                )
                if result.failed_files:
                    st.warning(f"{len(result.failed_files)} fichier(s) ignoré(s).")
            except Exception as exc:
                st.error(f"Erreur d'ingestion : {exc}")

    if st.button("Réinitialiser la base vectorielle", width="stretch"):
        try:
            pipeline.reset_vector_store()
            st.success("Base vectorielle réinitialisée.")
        except Exception as exc:
            st.error(f"Erreur de réinitialisation : {exc}")

    try:
        health = pipeline.health()
        st.divider()
        st.write(f"Chunks indexés : `{health.get('collection_count')}`")
        st.write("Ollama : OK" if health.get("ollama") else "Ollama : attention")
        st.write("ChromaDB : OK" if health.get("vector_store") else "ChromaDB : attention")
    except Exception as exc:
        st.warning(f"Statut indisponible : {exc}")


question = st.text_area("Question", placeholder="Ex. Quelle est la procédure pour demander un accès ?", height=120)
top_k = st.slider("Nombre de passages à récupérer", min_value=1, max_value=10, value=settings.top_k)

if st.button("Envoyer", type="primary"):
    if not question.strip():
        st.warning("Veuillez saisir une question.")
    else:
        with st.spinner("Recherche dans les documents et génération de la réponse..."):
            try:
                response = pipeline.answer_question(question, top_k=top_k)
                st.subheader("Réponse")
                st.markdown(response.answer)

                st.subheader("Sources")
                if not response.sources:
                    st.info("Aucune source pertinente retournée.")
                for index, source in enumerate(response.sources, start=1):
                    page_label = f", page {source.page}" if source.page else ""
                    score_label = f" · score {source.score:.2f}" if source.score is not None else ""
                    with st.expander(f"{index}. {source.file_name}{page_label} · {source.chunk_id}{score_label}"):
                        st.write(source.excerpt)
            except Exception as exc:
                st.error(f"Erreur : {exc}")
