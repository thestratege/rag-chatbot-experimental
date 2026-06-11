# Démo superviseur - Chatbot RAG expérimental

## Objectif de la V1

Cette V1 démontre une base expérimentale propre pour un chatbot documentaire interne. L'objectif est de valider l'expérience utilisateur et l'architecture cible avant de brancher le vrai pipeline RAG local sur une machine équipée d'une RTX 4080.

Le prototype permet déjà de :

- tenir une conversation simple ;
- reconnaître une question documentaire ;
- répondre avec des sources ;
- refuser d'inventer quand l'information est absente ;
- séparer clairement le front-end utilisateur, le back-end et le back office.

## Architecture actuelle

```text
Front-end React/Vite
        |
        | HTTP /api/chat
        v
Back-end FastAPI
        |
        +-- conversation_manager.py
        +-- intent_router.py
        +-- provider_router.py
        +-- rag_pipeline.py
        |
        +-- provider mock / openrouter / ollama
```

Le front-end React est le front office utilisateur. Le back-end FastAPI expose l'API conversationnelle. Streamlit reste un back office séparé pour l'administration, les benchmarks et les paramètres expérimentaux.

## Séparation front-end / back-end

Le front-end ne contient aucune clé API, aucune logique RAG et aucun accès direct aux documents. Il envoie uniquement les messages utilisateur au back-end FastAPI via HTTP.

Le back-end porte la logique sensible :

- classification d'intention ;
- mémoire conversationnelle courte ;
- décision d'utiliser ou non le RAG ;
- appel au provider LLM configuré ;
- récupération et formatage des sources.

Cette séparation prépare une future intégration dans SharePoint ou dans un autre portail interne.

## Rôle du mode mock

Le mode `mock` permet de tester l'expérience complète sans GPU, sans Ollama et sans service cloud. Il simule les grandes familles de documents fictifs :

- demande d'accès ;
- réinitialisation de mot de passe ;
- création de rapport ;
- support utilisateur ;
- politique d'utilisation.

Ce mode est utile pour la démo superviseur parce qu'il est stable, rapide et ne transmet aucun document sensible à un service externe.

## Rôle futur d'Ollama + RTX 4080

La version finale visée reste locale. Sur la machine équipée d'une RTX 4080, le provider `ollama` permettra de connecter le vrai pipeline RAG :

- ingestion des vrais documents locaux ;
- embeddings locaux ;
- stockage ChromaDB ;
- retrieval ;
- génération locale avec un modèle Ollama.

Les modèles candidats à tester localement sont notamment `qwen3:8b`, `qwen3:14b` et `gpt-oss:20b` si disponible dans Ollama.

## Rôle futur de SharePoint

Le front-end React actuel est conçu comme un widget conversationnel. Il pourra être intégré plus tard dans un site SharePoint, soit rapidement via iframe, soit proprement via SharePoint Framework.

## Commandes de lancement

Depuis la racine du projet :

```bash
chmod +x scripts/run_backend.sh scripts/run_frontend.sh scripts/check_demo_ready.sh
```

Lancer le back-end :

```bash
scripts/run_backend.sh
```

URL back-end à ouvrir :

```text
http://127.0.0.1:8010/docs
```

Dans un deuxième terminal, lancer le front-end :

```bash
scripts/run_frontend.sh
```

URL front-end à ouvrir :

```text
http://localhost:5173
```

Back office Streamlit, si nécessaire :

```bash
streamlit run ui/back_office_app.py
```

## Configuration front-end

Le front-end peut utiliser un fichier local :

```bash
cp frontend/.env.local.example frontend/.env.local
```

Contenu attendu :

```env
VITE_API_BASE_URL=http://127.0.0.1:8010
```

Ce fichier ne contient aucun secret.

## Vérification rapide

Avant la démo :

```bash
scripts/check_demo_ready.sh
```

Le script vérifie la présence des fichiers utiles, le fait que `.env` ne soit pas suivi par Git, les documents fictifs, la configuration front-end et les tests Python si `.venv` est disponible.

## Questions de démonstration

1. Bonjour

Résultat attendu :
Le chatbot répond à la salutation, `intent = greeting`, `used_rag = false`.

2. Je veux comprendre comment tu peux m’aider.

Résultat attendu :
Le chatbot explique ses capacités, `intent = capability_question`, `used_rag = false`.

3. Comment demander un accès ?

Résultat attendu :
Le chatbot répond avec une source `procedure_acces.txt`.

4. Quelles sont les bonnes pratiques d’utilisation ?

Résultat attendu :
Le chatbot répond avec une source `politique_utilisation.txt`.

5. Résume les principales procédures disponibles dans les documents.

Résultat attendu :
Le chatbot produit une synthèse avec plusieurs sources.

6. Quelle est la politique de remboursement des billets d’avion ?

Résultat attendu :
Le chatbot refuse proprement :

```text
Je ne trouve pas cette information dans les documents fournis.

Sources :
- Aucune source pertinente trouvée.
```

## Tolérance aux erreurs utilisateur

La V1 ne dépend plus uniquement d'une liste de phrases exactes. Le routeur d'intention applique maintenant :

- une normalisation du texte : minuscules, accents retirés, apostrophes harmonisées, ponctuation simplifiée ;
- des profils d'intention comme `access_request`, `password_reset`, `usage_policy` ou `global_summary` ;
- une correspondance approximative avec `difflib`, la librairie standard Python ;
- un score de confiance ;
- une demande de clarification lorsque le score est incertain.

Cela permet de reconnaître des formulations imparfaites comme :

```text
comment demender un acces
mot de passe oublie
resumer les procedures
comment tu peux maider
```

Les comportements critiques restent conservés : une salutation ne déclenche pas le RAG, une question sur les capacités reste conversationnelle, et un sujet absent comme le remboursement de billets d'avion produit le refus exact.

## Mode retrieval_only

Le mode `retrieval_only` sert à tester la recherche documentaire réelle sans générer une réponse complète avec un LLM.

Il permet de :

- lire les chunks déjà indexés dans ChromaDB ;
- chercher localement les passages pertinents ;
- afficher les sources et les scores ;
- vérifier que le chunking et les sources sont exploitables ;
- éviter tout appel OpenRouter ;
- éviter tout appel Ollama pendant la question/réponse.

Ce mode est utile avant le test sur RTX 4080 : il valide la partie documentaire du RAG sans dépendre d'un modèle lourd. La réponse produite est volontairement simple : elle liste les extraits retrouvés et les sources associées.

Commandes de préparation avec documents fictifs :

```bash
python scripts/load_sample_documents.py
python scripts/ingest_documents.py
```

Configuration à utiliser :

```env
LLM_PROVIDER=retrieval_only
```

Puis lancer :

```bash
scripts/run_backend.sh
scripts/run_frontend.sh
```

## Mode Ollama local

Le mode `ollama` valide l'intégration technique complète du RAG local :

```text
question utilisateur -> retrieval -> contexte documentaire -> génération Ollama -> réponse avec sources
```

Il ne doit pas appeler OpenRouter. Pour cette étape, il faut utiliser uniquement les documents fictifs et un modèle léger comme `qwen2.5:1.5b-instruct`.

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

Lancer le back-end :

```bash
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:1.5b-instruct scripts/run_backend.sh
```

Lancer le front-end dans un autre terminal :

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
- sources conservées ;
- refus exact pour la question absente ;
- `provider = ollama`.

## Explication pour le superviseur

“Cette V1 démontre l’architecture cible du chatbot : un front-end React séparé du back-end FastAPI. Le chatbot peut tenir une conversation simple, reconnaître une question documentaire, répondre avec des sources et refuser d’inventer lorsque l’information est absente. Le mode mock permet de tester l’expérience utilisateur sans GPU et sans envoyer de documents sensibles vers un service externe. La prochaine étape sera de connecter le vrai RAG local via Ollama sur la RTX 4080, puis de préparer l’intégration SharePoint.”

## Intégration SharePoint

### Option A — Démo rapide

- héberger le front-end React ;
- l'intégrer dans SharePoint via iframe / Embed web part ;
- configurer CORS côté FastAPI avec l'origine du site SharePoint ou du front-end hébergé ;
- utiliser cette approche pour un prototype rapide.

Cette option permet de montrer vite le widget dans un environnement SharePoint, sans développer un composant SharePoint complet.

### Option B — Version professionnelle

- transformer le widget React en SharePoint Framework Web Part ;
- ajouter Microsoft Entra ID ;
- appeler le back-end FastAPI avec authentification ;
- gérer les permissions plus tard.

Cette option est celle à privilégier pour une version interne robuste, avec contrôle des accès, audit et intégration Microsoft 365.

## Limites de la V1

- Le mode mock simule les réponses documentaires.
- Le vrai RAG local doit encore être testé sur la RTX 4080.
- La mémoire conversationnelle est en RAM.
- Il n'y a pas encore d'authentification.
- Les permissions par utilisateur et par document ne sont pas encore gérées.
- L'intégration SharePoint est documentée mais pas encore développée en SPFx.
- Le back office Streamlit reste expérimental.

## Prochaine étape technique

1. Tester Ollama sur la RTX 4080 avec des modèles 8B à 20B.
2. Brancher le provider `ollama` sur le vrai corpus documentaire.
3. Évaluer la qualité RAG sur des questions métier.
4. Stabiliser l'authentification et les permissions.
5. Préparer l'intégration SharePoint en iframe pour prototype, puis SPFx pour la version professionnelle.
