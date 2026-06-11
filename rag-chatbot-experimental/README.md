# RAG Chatbot Experimental

Prototype local de chatbot documentaire RAG en Python. Il ingère des documents placés dans un dossier local, crée des embeddings avec Ollama, stocke les vecteurs dans ChromaDB, récupère les passages pertinents, puis génère une réponse en français avec citations.

Cette V1 est volontairement simple, démontrable et modulaire. Elle est pensée comme une base expérimentale sérieuse, pas comme une version production.

## Architecture

```text
data/documents/      -> documents source PDF, DOCX, TXT, Markdown
app/document_loader.py      -> extraction texte + métadonnées
app/chunker.py              -> découpage intelligent avec overlap
app/embeddings.py           -> embeddings locaux via Ollama /api/embed
app/vector_store.py         -> abstraction + implémentation ChromaDB persistante
app/retriever.py            -> façade de recherche hybride avec permissions
app/query_rewriter.py       -> reformulation optionnelle des questions contextuelles
app/hybrid_retriever.py     -> fusion vectorielle + lexicale
app/reranker.py             -> reranking heuristique et debug
app/llm_client.py           -> génération via Ollama /api/chat
app/rag_pipeline.py         -> orchestration ingestion + question/réponse
app/intent_router.py        -> détection greeting, small talk, question RAG, hors périmètre
app/conversation_manager.py -> historique court en mémoire pour la session
app/provider_router.py      -> provider LLM configurable mock / openrouter / ollama
app/openrouter_client.py    -> client optionnel OpenRouter pour benchmark cloud
api/main.py                 -> API FastAPI
frontend/                   -> front office React + TypeScript + Vite
ui/back_office_app.py       -> back office Streamlit pour administration et benchmarks
benchmarks/*.json           -> modèles, contextes fictifs et questions de benchmark
```

Flux principal :

```text
Documents locaux -> parsing -> chunks -> embeddings -> ChromaDB
Front React -> FastAPI /api/chat -> intent router -> conversation manager
Question documentaire -> retrieval -> contexte -> provider LLM -> réponse sourcée
```

## RAG intelligent local

Le chemin Ollama peut désormais reformuler une question contextuelle, combiner recherche vectorielle et lexicale, reranker les chunks, diversifier les synthèses multi-documents et refuser avant génération lorsque la confiance est insuffisante.

Pour le POC local, `RAG_PERMISSION_FILTERING_ENABLED=false` donne à tous les profils le même accès documentaire. Les métadonnées `allowed_groups` restent indexées et le filtrage historique peut être réactivé avec `true` pour une future phase SharePoint/Entra ID.

Diagnostic technique et configuration :

[docs/rag_intelligence_upgrade.md](docs/rag_intelligence_upgrade.md)

Les réglages `RAG_*` sont centralisés dans `.env.example`. La reformulation est optionnelle car elle ajoute un appel Ollama. OpenRouter reste désactivé dans le chemin documentaire local.

Le front office utilisateur est volontairement séparé du back office. Le front office React fournit le widget conversationnel. Streamlit reste réservé à l'administration, aux documents, aux benchmarks et aux paramètres expérimentaux.

## Stack

- Python
- FastAPI pour l'API
- React + TypeScript + Vite pour le front office conversationnel
- Streamlit pour le back office expérimental
- Ollama pour le LLM local et les embeddings
- ChromaDB pour la base vectorielle persistante
- pypdf pour les PDF
- python-docx pour les DOCX
- OpenRouter pour le benchmark cloud optionnel, sans documents réels
- pandas pour l'affichage et l'export CSV des résultats de benchmark
- pytest pour les tests

Choix pragmatique : cette V1 n'utilise pas LangChain ni LlamaIndex. Le pipeline est court, lisible et contrôlé de bout en bout. Cela facilite le debug, les tests et une future migration vers Qdrant, du reranking ou une recherche hybride.

## Prérequis

- Python 3.11 ou plus récent recommandé
- Ollama installé et lancé
- Modèles Ollama téléchargés localement
- GPU optionnel. Une RTX 4080 accélérera fortement l'inférence, mais le système fonctionne aussi CPU avec plus de latence.

## Installation

Depuis le dossier du projet :

```bash
cd rag-chatbot-experimental
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Installer Ollama :

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Sur macOS, l'installation peut aussi se faire depuis l'application officielle Ollama.

Démarrer Ollama si nécessaire :

```bash
ollama serve
```

Télécharger les modèles recommandés :

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:7b-instruct
```

Alternatives LLM raisonnables pour cette V1 :

```bash
ollama pull llama3.1:8b
ollama pull mistral:7b
```

Puis modifier `OLLAMA_LLM_MODEL` dans `.env` si vous choisissez un autre modèle.

## Configuration

Variables principales dans `.env` :

```env
ENVIRONMENT=development
LLM_PROVIDER=mock
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OLLAMA_MODEL=qwen3:8b
FRONTEND_ORIGIN=http://localhost:5173
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
ALLOWED_ORIGINS_PRODUCTION=https://chatbot.example.org,https://tenant.sharepoint.com
CSP_FRAME_ANCESTORS="'self' http://localhost:5173"
PUBLIC_API_BASE_URL=http://127.0.0.1:8010
AUTH_ENABLED=false
AUTH_PROVIDER=none
DEMO_AUTH_TOKEN=
DEMO_ADMIN_AUTH_TOKEN=
ENTRA_TENANT_ID=
ENTRA_CLIENT_ID=
ENTRA_AUDIENCE=
ENTRA_ISSUER=
AUTH_REQUIRED_GROUPS=
CONVERSATION_HISTORY_LIMIT=10
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=qwen2.5:7b-instruct
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_NUM_CTX=4096
OLLAMA_NUM_PREDICT=512
OLLAMA_TEMPERATURE=0.1
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIR=data/vector_store
DOCUMENTS_DIR=data/documents
TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
DEFAULT_LANGUAGE=fr
RETRIEVAL_MIN_SCORE=0.15
EMBEDDING_BATCH_SIZE=32
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_ENABLED=false
OPENROUTER_ALLOW_DOCUMENT_CONTEXT=false
OPENROUTER_MAX_REQUESTS_PER_RUN=40
OPENROUTER_TIMEOUT_SECONDS=120
```

`CHUNK_SIZE` et `CHUNK_OVERLAP` sont exprimés en caractères approximatifs. C'est suffisant pour une V1 locale ; une V2 pourra utiliser un tokenizer exact par modèle.

`LLM_PROVIDER=mock` est le mode recommandé pour la première démo sur une machine sans GPU. `LLM_PROVIDER=ollama` active le pipeline RAG local complet. `LLM_PROVIDER=openrouter` reste un mode de test cloud ; par défaut, il n'envoie pas le contexte documentaire vers OpenRouter (`OPENROUTER_ALLOW_DOCUMENT_CONTEXT=false`) afin d'éviter toute fuite de documents internes.

## Démo superviseur

Le déroulé complet de présentation est disponible ici :

[docs/demo_superviseur.md](docs/demo_superviseur.md)

Commandes essentielles depuis la racine du projet :

```bash
chmod +x scripts/run_backend.sh scripts/run_frontend.sh scripts/check_demo_ready.sh
scripts/check_demo_ready.sh
scripts/run_backend.sh
```

Dans un second terminal :

```bash
scripts/run_frontend.sh
```

URLs de démo :

- back-end FastAPI : `http://127.0.0.1:8010/docs`
- front-end React : `http://localhost:5173`

## Mode retrieval_only

Le mode `retrieval_only` permet de tester la recherche documentaire réelle sans appeler OpenRouter, sans appeler Ollama pendant la question/réponse et sans générer de réponse LLM complète. Il lit les chunks indexés, retourne les extraits pertinents et affiche les sources.

Préparer les documents fictifs :

```bash
python scripts/load_sample_documents.py
python scripts/ingest_documents.py
```

Configurer localement :

```env
LLM_PROVIDER=retrieval_only
```

Lancer la démo :

```bash
scripts/run_backend.sh
scripts/run_frontend.sh
```

La grille de test manuelle est disponible ici :

[docs/grille_evaluation_rag.md](docs/grille_evaluation_rag.md)

## Mode Ollama local

Le mode `ollama` connecte le vrai pipeline RAG local : retrieval documentaire, construction du contexte, génération avec Ollama, réponse sourcée et refus si aucun passage pertinent n'est trouvé. Il n'utilise pas OpenRouter et ne doit être testé ici qu'avec les documents fictifs.

Pour cette étape, le modèle léger recommandé est `qwen2.5:1.5b-instruct`. `qwen2.5:7b-instruct` reste optionnel mais peut être lent sur une machine sans GPU.

Préparer Ollama :

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:1.5b-instruct
```

Préparer les documents fictifs :

```bash
python scripts/load_sample_documents.py
python scripts/ingest_documents.py
```

Lancer le back-end avec Ollama :

```bash
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:1.5b-instruct scripts/run_backend.sh
```

Dans un autre terminal :

```bash
scripts/run_frontend.sh
```

Test manuel API :

```bash
curl -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"comment demander un acces","mode":"auto"}'
```

Questions à tester :

- `comment demander un acces`
- `mot de passe oublie`
- `bonnes pratiques utilisation`
- `resumer les procedures`
- `quelle est la politique de remboursement des billets d’avion ?`

Résultats attendus :

- réponse naturelle générée par Ollama ;
- sources conservées dans la réponse API ;
- `provider = ollama` ;
- refus exact pour la question absente.

## Simulateur local de bibliothèque SharePoint

Le simulateur local permet de démontrer l'ajout, la modification, la suppression et la réindexation incrémentale de documents, ainsi que des permissions documentaires simulées, sans appeler Microsoft Graph ni modifier un vrai site SharePoint.

Guide complet :

[docs/sharepoint_simulator_demo.md](docs/sharepoint_simulator_demo.md)

Plan d'évaluation :

[docs/rag_evaluation_plan.md](docs/rag_evaluation_plan.md)

Commandes essentielles :

```bash
scripts/setup_sharepoint_simulator.sh
scripts/sync_sharepoint_simulator.sh
SHAREPOINT_SIM_API_PORT=8013 scripts/run_sharepoint_sim_backend.sh
```

Dashboard local :

```text
http://localhost:5173/admin?apiBaseUrl=http://127.0.0.1:8013
```

Ce mode utilise un index Chroma isolé dans `data/vector_store_sharepoint_sim`, désactive OpenRouter et réserve les routes `/admin/index/*` au rôle administrateur local. Les profils et permissions simulés devront être remplacés par Microsoft Graph et Entra ID dans l'environnement TI.

## Widget installable et intégration SharePoint

Le chatbot reste autonome : le front-end React peut être intégré dans une page web ou SharePoint sans rendre le projet dépendant de SharePoint.

Documentation complète :

[docs/integration_widget.md](docs/integration_widget.md)

Guide dédié à la démonstration SharePoint Online :

[docs/sharepoint_integration.md](docs/sharepoint_integration.md)

Mode iframe local :

```html
<iframe
  src="http://localhost:5173/embed?apiBaseUrl=http://127.0.0.1:8010&theme=ism&title=Assistant%20DPC&compact=true"
  width="420"
  height="650"
  style="border:0; border-radius:16px; overflow:hidden;"
  title="Assistant DPC">
</iframe>
```

Commandes de test local :

```bash
scripts/run_backend.sh
scripts/run_frontend.sh
```

Puis ouvrir :

```text
http://localhost:5173/embed?apiBaseUrl=http://127.0.0.1:8010&theme=ism&title=Assistant%20DPC&compact=true
http://localhost:5173/embed-test.html
```

SPFx est prévu plus tard comme option professionnelle SharePoint avec Microsoft Entra ID et permissions documentaires. Aucun projet SPFx n'est créé dans cette V1.

## Sécurité du widget installable

Le durcissement minimal du widget est documenté ici :

[docs/integration_widget.md](docs/integration_widget.md)

La configuration côté API repose sur une allowlist CORS et une politique iframe configurable :

```env
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
ALLOWED_ORIGINS_PRODUCTION=https://chatbot.example.org,https://tenant.sharepoint.com
CSP_FRAME_ANCESTORS="'self' http://localhost:5173"
```

En production, utiliser HTTPS, déclarer uniquement les domaines autorisés et éviter `allow_origins=["*"]`. Le front-end ne contient aucune clé API et n'accède jamais directement aux documents. L'authentification, le rate limiting, les permissions documentaires et Microsoft Entra ID restent des étapes V2/V3.

## Préparation Microsoft Entra ID

L'authentification Microsoft Entra ID est préparée côté back-end, mais elle n'est pas activée par défaut pour la démo locale.

Documentation complète :

[docs/security_authentication.md](docs/security_authentication.md)

Configuration de démo :

```env
AUTH_ENABLED=false
AUTH_PROVIDER=none
```

Configuration cible future :

```env
AUTH_ENABLED=true
AUTH_PROVIDER=entra
ENTRA_TENANT_ID=
ENTRA_CLIENT_ID=
ENTRA_AUDIENCE=
ENTRA_ISSUER=
AUTH_REQUIRED_GROUPS=
```

Lorsque `AUTH_ENABLED=true`, `/api/chat` attendra un token `Authorization: Bearer ...`. La validation JWT Entra ID complète reste une étape future et devra être faite côté back-end.

## Démo sécurité avec AUTH_ENABLED=true

Le provider `mock` permet de démontrer la protection des routes sensibles sans brancher Microsoft Entra ID. Il est réservé à la démo et ne doit jamais être utilisé en production.

Lancer le back-end en mode mock sécurisé :

```bash
ENVIRONMENT=demo \
AUTH_ENABLED=true \
AUTH_PROVIDER=mock \
DEMO_AUTH_TOKEN="<token-utilisateur-fourni-hors-code>" \
DEMO_ADMIN_AUTH_TOKEN="<token-admin-fourni-hors-code>" \
LLM_PROVIDER=mock \
scripts/run_backend.sh
```

Préparer le front de démonstration sans y stocker le token :

```bash
[ -f frontend/.env.local ] || cp frontend/.env.local.example frontend/.env.local
scripts/run_frontend.sh
```

`frontend/.env.local.example` active uniquement l'affichage du champ de saisie. Si `frontend/.env.local` existait déjà, vérifier qu'il contient ces valeurs publiques :

```env
VITE_API_BASE_URL=http://127.0.0.1:8010
VITE_AUTH_DEMO_ENABLED=true
```

Redémarrer Vite après toute modification de `.env.local`. Saisir manuellement le token utilisateur fourni hors du dépôt dans le widget. Le token reste en mémoire dans le navigateur et n'est jamais inclus dans le code front-end.

### Diagnostic front vers FastAPI

Si le widget affiche une erreur réseau :

1. Vérifier que FastAPI écoute réellement sur `8010` avec `curl -i http://127.0.0.1:8010/health`.
2. Vérifier `frontend/.env.local` avec les deux lignes publiques ci-dessus.
3. Redémarrer `scripts/run_frontend.sh` après une modification Vite.
4. Ouvrir la console navigateur en développement. Les logs `[chat-api]` indiquent uniquement l'URL API, l'endpoint, la présence ou l'absence d'un token et le code HTTP. Le token complet n'est jamais journalisé.

Le service front construit une URL absolue de la forme `http://127.0.0.1:8010/api/chat`. Il n'utilise pas `/api/chat` comme URL relative et ne dépend pas d'un proxy Vite.

### Validation de la démo sécurité

Health ouvert et headers HTTP :

```bash
curl -i http://127.0.0.1:8010/health
```

Chat principal sans token : doit retourner `401`.

```bash
curl -i -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"Bonjour","mode":"auto"}'
```

Chat principal avec mauvais token : doit retourner `401`.

```bash
curl -i -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mauvais-token" \
  -d '{"conversation_id":null,"message":"Bonjour","mode":"auto"}'
```

Chat principal avec token de démo valide : doit retourner `200`.

```bash
curl -i -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEMO_AUTH_TOKEN" \
  -d '{"conversation_id":null,"message":"Bonjour","mode":"auto"}'
```

Test CORS autorisé :

```bash
curl -i -X OPTIONS http://127.0.0.1:8010/api/chat \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST"
```

Test CORS non autorisé :

```bash
curl -i -X OPTIONS http://127.0.0.1:8010/api/chat \
  -H "Origin: http://site-non-autorise.com" \
  -H "Access-Control-Request-Method: POST"
```

La route historique `/chat` est également protégée. Pour une démonstration légère sans appel Ollama, privilégier `/api/chat` avec un message conversationnel comme `Bonjour`.

### Autorisations par défaut

La démo applique une politique deny-by-default lorsque `AUTH_ENABLED=true` :

- `/health` est explicitement public et retourne uniquement un état minimal ;
- Swagger (`/docs`, `/openapi.json`, `/redoc`) reste explicitement public en `development`, `demo` et `test` uniquement ;
- `/`, `/api/chat`, `/chat` et `/api/conversations/reset` exigent un utilisateur authentifié ;
- `/ingest` exige le rôle `admin` ;
- toute nouvelle route API est protégée par défaut par le garde global, même si une dépendance locale a été oubliée ;
- `/embed` reste public côté front-end, car il n'expose aucun document et doit appeler l'API protégée pour obtenir une réponse.

Deux identités mock sont prévues :

| Identité | Token de démo | Rôles | Usage |
|---|---|---|---|
| `demo-user` | valeur de `DEMO_AUTH_TOKEN` | `demo` | Chatbot |
| `demo-admin` | valeur de `DEMO_ADMIN_AUTH_TOKEN` | `admin` | Ingestion |

Preuves supplémentaires pour `/ingest` :

```bash
# Sans token : 401
curl -i -X POST http://127.0.0.1:8010/ingest

# Token demo-user : 403
curl -i -X POST http://127.0.0.1:8010/ingest \
  -H "Authorization: Bearer $DEMO_AUTH_TOKEN"

# Token demo-admin : passe au traitement normal
curl -i -X POST http://127.0.0.1:8010/ingest \
  -H "Authorization: Bearer $DEMO_ADMIN_AUTH_TOKEN"
```

## Prochaine étape : benchmark Ollama sur RTX 4080

Le benchmark Ollama ne doit être lancé que lorsque la machine équipée de la RTX 4080 est disponible. L'objectif sera de comparer des modèles locaux sur les mêmes questions documentaires, sans envoyer de documents vers un service externe.

Modèles candidats :

- `qwen3:4b`
- `qwen3:8b`
- `qwen3:14b`
- `llama3.1:8b`
- `mistral:7b`
- `gpt-oss:20b` si disponible localement

À ce stade, aucune commande Ollama n'est lancée automatiquement par le projet.

## Utilisation

### Démo sans RTX 4080

Pour une démo sûre sur une machine légère, chargez les documents fictifs, gardez `LLM_PROVIDER=mock`, puis lancez le backend et le front React :

```bash
python scripts/load_sample_documents.py
uvicorn api.main:app --reload
```

Dans un autre terminal :

```bash
cd frontend
npm install
npm run dev
```

Ouvrez ensuite `http://localhost:5173`. Le widget peut saluer, converser brièvement, simuler des réponses documentaires avec sources et refuser une information absente sans appeler Ollama ni OpenRouter.

### RAG local Ollama

1. Placez vos documents dans :

```text
data/documents/
```

Formats supportés :

- `.txt`
- `.md`
- `.pdf`
- `.docx`

2. Lancez l'ingestion :

```bash
python scripts/ingest_documents.py
```

3. Lancez l'API :

```bash
uvicorn api.main:app --reload
```

4. Lancez l'interface Streamlit dans un autre terminal :

```bash
streamlit run ui/streamlit_app.py
```

Pour le front office utilisateur moderne, utilisez plutôt :

```bash
cd frontend
npm install
npm run dev
```

Le back office Streamlit reste disponible pour l'administration :

```bash
streamlit run ui/back_office_app.py
```

## API

Statut du service :

```bash
curl http://127.0.0.1:8010/
```

Health check :

```bash
curl http://127.0.0.1:8010/health
```

Ingestion :

```bash
curl -X POST http://127.0.0.1:8010/ingest
```

Question :

```bash
curl -X POST http://127.0.0.1:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Quelle est la procédure pour demander un accès ?","top_k":5}'
```

Réponse attendue :

```json
{
  "answer": "Réponse structurée en français.",
  "sources": [
    {
      "file_name": "procedure_acces.pdf",
      "page": "2",
      "chunk_id": "procedure-acces-p2-c1-abc123",
      "excerpt": "Extrait utilisé...",
      "score": 0.86
    }
  ]
}
```

Endpoint conversationnel utilisé par le front React :

```bash
curl -X POST http://127.0.0.1:8010/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"Bonjour","mode":"auto"}'
```

Réponse :

```json
{
  "conversation_id": "uuid",
  "answer": "Réponse en français.",
  "intent": "greeting",
  "used_rag": false,
  "sources": [],
  "provider": "mock"
}
```

Réinitialiser une conversation :

```bash
curl -X POST http://127.0.0.1:8010/api/conversations/reset \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"uuid"}'
```

## Exemples de questions

- Quelle est la procédure pour demander un accès ?
- Quels documents sont nécessaires pour créer un compte ?
- Qui doit valider une demande ?
- Quels sont les délais indiqués dans les documents ?
- Quelle est la politique de conservation mentionnée ?

Si l'information n'est pas présente dans les passages récupérés, le chatbot doit répondre :

```text
Je ne trouve pas cette information dans les documents fournis.
```

## Réinitialisation

Pour vider la collection vectorielle :

```bash
python scripts/reset_vector_store.py
```

Vous pouvez ensuite relancer :

```bash
python scripts/ingest_documents.py
```

## Tests

Les tests unitaires évitent Ollama et ChromaDB autant que possible via des doubles simples :

```bash
pytest
```

Couverture minimale :

- chunking ;
- filtrage retrieval ;
- refus sans contexte ;
- présence des sources dans la réponse.
- routage d'intention ;
- mémoire conversationnelle ;
- endpoint `/api/chat` en mode mock.

## Benchmark OpenRouter prudent

Le projet inclut un benchmark OpenRouter optionnel pour comparer des modèles gratuits sans faire tourner de modèles lourds sur une machine locale limitée à 8 Go de RAM. Cette phase sert à explorer des candidats. Le système final reste local avec Ollama, ChromaDB, les vrais documents dans `data/documents/` et, à terme, une machine équipée d'une RTX 4080.

Le benchmark OpenRouter est volontairement séparé du pipeline local :

- il utilise uniquement les contextes fictifs/anonymisés de `benchmarks/rag_test_contexts.json` ;
- il ne lit jamais `data/documents/` ;
- il vérifie les modèles via `GET /models` avant d'appeler `chat/completions` ;
- il limite le nombre de modèles, de questions et le rythme des requêtes.

On n'utilise pas `openrouter/free` pour ce benchmark, car ce routeur choisit automatiquement le modèle. Pour une comparaison sérieuse, chaque requête doit viser un `model_id` explicite et validé.

### Configuration OpenRouter

Créez une clé API OpenRouter, puis ajoutez-la dans `.env` :

```env
OPENROUTER_API_KEY=sk-or-v1-REPLACE_WITH_YOUR_OWN_KEY-cle
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_ENABLED=true
OPENROUTER_MAX_REQUESTS_PER_RUN=40
OPENROUTER_TIMEOUT_SECONDS=120
OPENROUTER_REQUEST_DELAY_SECONDS=35
OPENROUTER_MAX_MODELS_PER_RUN=3
OPENROUTER_MAX_QUESTIONS_PER_RUN=3
OPENROUTER_RETRY_ON_429=true
OPENROUTER_MAX_RETRIES=1
```

Documentation officielle :

- https://openrouter.ai/docs/quickstart/
- https://openrouter.ai/docs/api-reference/overview/

### Découvrir les modèles gratuits disponibles

Il faut commencer par lister les modèles gratuits réellement disponibles, car les slugs `:free` changent et certains modèles peuvent disparaître ou être temporairement indisponibles.

```bash
python scripts/list_openrouter_models.py
```

Sorties :

```text
benchmarks/results/openrouter_free_models_YYYYMMDD_HHMMSS.json
benchmarks/results/openrouter_free_models_YYYYMMDD_HHMMSS.csv
```

Le CSV contient `model_id`, `name`, `context_length`, `provider_family`, `pricing` et `supported_parameters`.

Le benchmark safe active par défaut le trio prioritaire suivant dans `benchmarks/openrouter_models.json` :

- `qwen/qwen3-next-80b-a3b-instruct:free` pour calibrer une future reproduction locale Qwen via Ollama ;
- `meta-llama/llama-3.3-70b-instruct:free` comme baseline généraliste multilingue forte ;
- `openai/gpt-oss-20b:free` comme comparaison gratuite raisonnable et potentiellement plus stable.

Les autres modèles gratuits observés restent candidats optionnels désactivés par défaut.

### Phase 1 : Availability benchmark

Cette phase répond à une seule question factuelle simple avec plusieurs modèles gratuits validés via `/models`. Elle sert uniquement à savoir quels modèles répondent réellement sans être bloqués par les limites 429.

```bash
python scripts/benchmark_openrouter_models.py --availability
```

Modèles inclus :

- `openai/gpt-oss-20b:free`
- `z-ai/glm-4.5-air:free`
- `google/gemma-4-31b-it:free`
- `google/gemma-4-26b-a4b-it:free`
- `nvidia/nemotron-nano-9b-v2:free`
- `nvidia/nemotron-nano-12b-v2-vl:free`
- `deepseek/deepseek-v4-flash:free`
- `qwen/qwen3-next-80b-a3b-instruct:free`
- `meta-llama/llama-3.3-70b-instruct:free`

Le rapport indique pour chaque modèle : statut, code HTTP, temps de réponse, longueur de réponse et erreur éventuelle.

### Phase 2 : Quality benchmark

Cette phase sélectionne automatiquement les modèles ayant obtenu au moins un `success` dans le dernier availability benchmark, puis teste leur qualité RAG sur plusieurs questions.

```bash
python scripts/benchmark_openrouter_models.py --quality-from-last-availability --max-questions 3
```

Le rapport distingue disponibilité, qualité RAG, sources citées, refus d'hallucination et recommandation provisoire.

### Mini-test final anti-hallucination

Après la phase qualité, lancez le test final sur les trois modèles exploitables identifiés :

```bash
python scripts/benchmark_openrouter_models.py --hallucination-check
```

Modèles testés :

- `openai/gpt-oss-20b:free`
- `z-ai/glm-4.5-air:free`
- `nvidia/nemotron-nano-12b-v2-vl:free`

Question testée :

```text
Quelle est la politique de remboursement des frais de déplacement ?
```

Réponse attendue exactement :

```text
Je ne trouve pas cette information dans les documents fournis.

Sources :
- Aucune source pertinente trouvée.
```

Le rapport indique quels modèles refusent correctement, inventent une réponse, citent une source non pertinente ou ne sont pas évaluables à cause d'une limite API.

### Lancer un smoke test

Le smoke test consomme peu de quota : 1 à 2 modèles valides, 1 question.

```bash
python scripts/benchmark_openrouter_models.py --smoke-test
```

Il sert à confirmer que la clé API, `/models` et au moins un modèle répondent correctement.

### Lancer un benchmark safe

Le mode safe est le mode recommandé pour comparer les modèles gratuits sans saturer le quota :

```bash
python scripts/benchmark_openrouter_models.py --safe
```

Ce mode :

- valide les modèles via `/models` ;
- ignore les modèles introuvables avant tout appel `chat/completions` ;
- teste au maximum 3 modèles et 3 questions par défaut ;
- attend au moins 35 secondes entre deux requêtes ;
- respecte `Retry-After` sur les 429 ;
- réessaie une seule fois une requête limitée ;
- exporte JSON, CSV et Markdown.

Commande explicite recommandée :

```bash
python scripts/benchmark_openrouter_models.py --safe --max-models 3 --max-questions 3
```

Vous pouvez aussi forcer le trio prioritaire :

```bash
python scripts/benchmark_openrouter_models.py --safe --models qwen/qwen3-next-80b-a3b-instruct:free meta-llama/llama-3.3-70b-instruct:free openai/gpt-oss-20b:free --max-questions 3
```

Sorties :

```text
benchmarks/results/benchmark_openrouter_YYYYMMDD_HHMMSS.json
benchmarks/results/benchmark_openrouter_YYYYMMDD_HHMMSS.csv
benchmarks/results/benchmark_openrouter_YYYYMMDD_HHMMSS.md
```

### Back office benchmark

```bash
streamlit run ui/back_office_app.py
```

Le back office permet de :

- voir les modèles configurés ;
- lister les modèles gratuits disponibles ;
- lancer un smoke test ;
- lancer un benchmark safe ;
- afficher le dernier CSV de découverte ;
- afficher le dernier CSV de benchmark ;
- afficher le dernier rapport Markdown.

### Lire les statuts

- `success` / HTTP 200 : le modèle a répondu et la réponse est analysable.
- `model_not_found` / HTTP 404 : le slug n'est pas disponible ou aucun endpoint ne sert ce modèle ; le benchmark ne doit pas insister.
- `rate_limited` / HTTP 429 : OpenRouter ou le fournisseur upstream limite temporairement le modèle gratuit ; le script attend puis réessaie une seule fois.
- `timeout` : la réponse n'est pas arrivée avant `OPENROUTER_TIMEOUT_SECONDS`.
- `api_error` : autre erreur HTTP ou réseau.

Le rapport Markdown contient un résumé exécutif, les modèles testés avec succès, les modèles ignorés, les rate limits, un classement provisoire et une recommandation prudente. Les modèles sont classés seulement s'ils ont au moins 3 réponses réussies.

### Sécurité du benchmark

N'envoyez pas de documents internes sensibles vers OpenRouter. Le benchmark est découplé du dossier `data/documents/` et n'utilise que `benchmarks/rag_test_contexts.json`. Pour vos documents réels, utilisez le pipeline local Ollama.

## Intégration SharePoint

Le front office React est préparé pour être intégré plus tard dans SharePoint comme widget conversationnel. Aucune clé API, logique RAG ou lecture documentaire n'est présente côté navigateur : le widget appelle uniquement le backend FastAPI.

### Option 1 — Démo rapide avec iframe / Embed web part

1. Construire le front-end :

```bash
cd frontend
npm install
npm run build
```

2. Héberger le dossier `frontend/dist/` sur un emplacement interne accessible aux utilisateurs.
3. Intégrer l'URL dans SharePoint avec le composant Web `Embed`.
4. Autoriser le domaine du front-end dans SharePoint si la politique du tenant le demande.
5. Configurer `FRONTEND_ORIGIN` côté FastAPI avec l'origine exacte du front-end hébergé.

Pour la démo locale :

```env
FRONTEND_ORIGIN=http://localhost:5173
```

En production interne, évitez `*` dans CORS. Déclarez uniquement les domaines autorisés.

### Option 2 — Version professionnelle avec SPFx Web Part

La version robuste consistera à créer un SharePoint Framework Web Part, réutiliser le composant React du chatbot, puis appeler le backend FastAPI depuis ce Web Part. Cette option permettra d'ajouter ensuite :

- authentification Microsoft Entra ID ;
- passage d'un jeton utilisateur au backend ;
- permissions par utilisateur ou groupe ;
- audit logs ;
- déploiement contrôlé dans le tenant Microsoft 365.

Le SPFx complet n'est pas développé dans cette V1 pour garder le prototype clair. Le widget React actuel reste compatible iframe et suffisamment séparé pour faciliter cette migration.

## Docker Compose

Le fichier `docker-compose.yml` fournit seulement Ollama pour garder la V1 simple :

```bash
docker compose up -d
docker exec -it rag-chatbot-ollama ollama pull nomic-embed-text
docker exec -it rag-chatbot-ollama ollama pull qwen2.5:7b-instruct
```

L'API et Streamlit se lancent localement avec Python. Une dockerisation complète de l'application est prévue en V2.

## Gestion des erreurs prévue

La V1 gère explicitement :

- Ollama non démarré ;
- modèle LLM absent ;
- modèle embedding absent ;
- dossier de documents vide ;
- base vectorielle vide ;
- document illisible ;
- question vide ;
- contexte insuffisant ;
- timeout du LLM ou des embeddings.

## Sécurité et confidentialité

- Les documents restent locaux.
- Le pipeline RAG principal n'appelle aucune API externe pour les embeddings ou la génération.
- Le benchmark OpenRouter est optionnel et n'envoie que des contextes fictifs/anonymisés.
- Le front-end React ne contient aucune clé API, aucun accès documentaire direct et aucune logique RAG.
- Le provider OpenRouter du front office ne reçoit aucun contexte documentaire par défaut.
- Le contenu complet des documents n'est pas loggé.
- Aucun secret n'est hardcodé.
- Cette V1 n'est pas prête pour des données hautement sensibles en production.
- Une version production devrait ajouter authentification, permissions, audit logs, chiffrement, monitoring et politiques de rétention.

## Limites de cette V1

- Pas d'authentification.
- Pas de permissions par utilisateur ou par document.
- Pas de reranking.
- Pas de recherche hybride dense + sparse.
- Chunking basé sur caractères, pas sur tokenizer exact.
- Citations par page pour PDF lorsque disponible, mais pas encore par section/titre.
- Réingestion globale plutôt que suppression/réingestion fine par document.
- Pas d'évaluation automatique de la qualité des réponses.
- Pas de streaming de réponse.
- Pas de monitoring applicatif avancé.

## Roadmap V2

- Migration vers Qdrant.
- Recherche hybride dense + sparse.
- Reranking.
- Authentification.
- Permissions utilisateurs.
- Intégration SharePoint / Microsoft Graph.
- Traçabilité des questions.
- Dashboard d'évaluation.
- Feedback utilisateur.
- Évaluation automatique des réponses.
- Monitoring.
- Dockerisation complète.
- Déploiement interne.
- Support multilingue français/anglais.
- Citations plus précises par page et section.
- Gestion des documents mis à jour.
- Suppression/réingestion par document.
- Amélioration du chunking par titres et sections.

## Notes de conception

L'abstraction `VectorStore` isole ChromaDB du reste du pipeline. Pour migrer vers Qdrant, il faudra principalement ajouter une classe `QdrantVectorStore` avec les mêmes méthodes :

- `add_chunks`
- `query`
- `reset`
- `count`
- `is_available`

L'abstraction `OllamaEmbeddingClient` et `OllamaLLMClient` garde les appels modèle dans des modules dédiés. Le pipeline RAG reste donc testable sans service externe.
