# Test RAG local avec PDF

## Objectif

Ce test valide une chaîne PDF isolée sans supprimer les documents fictifs ni l'index Chroma principal :

```text
data/pdf_test_documents
  -> extraction PDF page par page
  -> chunks
  -> embeddings Ollama
  -> data/vector_store_pdf_test
  -> FastAPI /chat et /api/chat
  -> qwen3:14b
```

OpenRouter reste désactivé. Les documents et embeddings restent dans l'environnement local configuré.

## Dossiers isolés

- Déposer les PDF texte dans `data/pdf_test_documents/`.
- L'index dédié est créé dans `data/vector_store_pdf_test/`.
- Ne pas supprimer `data/documents/` ni `data/vector_store/`.

Les PDF et les fichiers Chroma de test sont ignorés par Git.

## Configuration temporaire

Les scripts dédiés appliquent uniquement au processus lancé :

```env
DOCUMENTS_DIR=data/pdf_test_documents
CHROMA_PERSIST_DIR=data/vector_store_pdf_test
TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
MAX_CONTEXT_CHARS=12000
OLLAMA_NUM_PREDICT=768
LLM_PROVIDER=ollama
OPENROUTER_ENABLED=false
```

Le vrai `.env` n'est pas modifié. Il n'est donc pas nécessaire de le restaurer.

## Ingestion

Vérifier que les PDF sont présents :

```bash
find data/pdf_test_documents -maxdepth 1 -type f -name "*.pdf"
```

Lancer l'ingestion isolée :

```bash
scripts/ingest_pdf_test.sh
```

Le résultat doit indiquer des parties PDF, des chunks et des chunks indexés. Un PDF scanné sans texte est ignoré avec un message indiquant qu'un OCR serait nécessaire.

## Lancer le back-end PDF

Arrêter le back-end courant sur `8010`, puis lancer :

```bash
scripts/run_pdf_test_backend.sh
```

Pour conserver le back-end principal et tester sur un autre port :

```bash
PDF_TEST_API_PORT=8012 scripts/run_pdf_test_backend.sh
```

Dans ce cas, cibler `http://127.0.0.1:8012` dans les commandes `curl` ou dans une instance front temporaire.

Pour utiliser un front temporaire sur `http://127.0.0.1:5174`, autoriser explicitement
cette origine pour le processus PDF :

```bash
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174 \
PDF_TEST_API_PORT=8012 scripts/run_pdf_test_backend.sh
```

Cette surcharge reste limitée au processus et ne modifie pas le vrai `.env`.

## Questions terminal

```bash
curl -s http://127.0.0.1:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Résume les documents disponibles."}' | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Quels sont les points importants du document ?"}' | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Quelles sont les étapes, obligations ou conditions principales mentionnées dans les documents ?"}' | python3 -m json.tool
```

Question hors contexte :

```bash
curl -s http://127.0.0.1:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Quelle est la procédure de remboursement des billets d avion ?"}' | python3 -m json.tool
```

## Test React

Avec le back-end PDF sur `8010` :

```bash
scripts/run_frontend.sh
```

Puis ouvrir `http://localhost:5173` et tester :

- `Résume les documents disponibles.`
- `Quels sont les points importants du document ?`
- `Quelles procédures, obligations ou conditions sont mentionnées ?`
- `Y a-t-il des dates, responsables, étapes ou conditions importantes ?`
- `Que dois-je retenir pour une démonstration à mon superviseur ?`

Vérifier :

- `Provider ollama · RAG` ;
- réponses Markdown propres ;
- sources contenant les noms des PDF et les numéros de page ;
- aucune pensée interne ;
- refus clair pour une question absente.

Pour conserver le front principal et tester une instance temporaire sur `5174` :

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8012 \
VITE_RUNTIME_MODE=local \
VITE_AUTH_DEMO_ENABLED=false \
npm run dev -- --host 127.0.0.1 --port 5174
```

## Vérifier Ollama

Pendant ou après une question :

```bash
curl http://10.100.1.210:11434/api/ps
```

Le serveur doit montrer `qwen3:14b` et possiblement `nomic-embed-text:latest`.

## Retour à la configuration initiale

Le vrai `.env` n'ayant pas été modifié, arrêter le back-end PDF puis relancer simplement :

```bash
scripts/run_backend.sh
```

Le projet réutilisera `data/documents/` et `data/vector_store/` selon la configuration initiale.

## Résultats observés le 9 juin 2026

PDF utilisés pour ce premier test :

- `Représentations sociales et culturelles de l'ingénieur - Rapport.pdf` ;
- `vryzas.pdf` ;
- `Enonces_developpement_durable_OIQ_VF.pdf`.

Résultat de l'ingestion isolée :

- 99 pages ou parties PDF lues ;
- 260 chunks créés ;
- 260 chunks indexés dans `data/vector_store_pdf_test` ;
- aucun document en erreur ;
- métadonnées conservées : fichier, chemin, type, page, date d'ingestion et identifiant de chunk.

Validations réussies :

- l'API `/chat` répond à partir des PDF et retourne les pages, chunks, extraits et scores ;
- Ollama utilise `qwen3:14b` pour la génération et `nomic-embed-text:latest` pour les embeddings ;
- le front React affiche `Provider ollama · RAG`, le Markdown et le panneau de sources ;
- la question de remboursement absente produit le refus attendu sans source.

Observations qualitatives :

- `Résume les documents disponibles.` produit une synthèse sourcée exploitable ;
- `Quels sont les points importants du document ?` produit une réponse sourcée, mais mélange plusieurs PDF puisque la question ne désigne pas un document précis ;
- certaines formulations très générales comme `Quelles procédures, obligations ou conditions sont mentionnées ?` peuvent être refusées ;
- `Que dois-je retenir pour une démonstration à mon superviseur ?` demande une clarification, ce qui évite une réponse inventée mais montre que le routage peut encore être enrichi.

## Limites connues

- Les PDF scannés nécessitent un OCR, non inclus dans ce test.
- L'extraction de tableaux et de mises en page complexes peut être imparfaite.
- Les réponses de synthèse longues peuvent être tronquées selon `OLLAMA_NUM_PREDICT`.
- Une question très générale sur plusieurs PDF peut récupérer des passages partiels ; vérifier les sources et pages retournées.
- Les deux PDF volumineux `notes_preparatoires-fr.pdf` et le manuel de management n'ont pas été ingérés pendant ce premier test afin de garder une validation rapide et isolée.
