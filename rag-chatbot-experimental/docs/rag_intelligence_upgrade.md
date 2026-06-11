# RAG Intelligence Upgrade

## Diagnostic initial

Avant cette évolution, une question documentaire suivait un chemin simple :

```text
question -> embedding Ollama -> recherche vectorielle Chroma top-k
-> filtrage par seuil et profil documentaire -> contexte
-> génération Ollama -> réponse et sources
```

Le retriever récupérait le `TOP_K` configuré, puis `RAGPipeline` pouvait resserrer les résultats par marge de score ou par fichier attendu. Chroma appliquait déjà les permissions `allowed_groups` avant de retourner les chunks. Les sources API étaient construites depuis `file_name`, `page`, `chunk_id`, l'extrait et le score.

Les limites principales étaient la dépendance au seul score vectoriel, le manque de reformulation des questions contextuelles, l'absence de reranking explicable, une stratégie de confiance limitée et une synthèse multi-documents encore très liée au corpus de démonstration.

## Chaîne améliorée

```text
question originale
-> reformulation optionnelle avec historique court
-> retrieval vectoriel large + recherche lexicale autorisée
-> fusion et déduplication
-> reranking heuristique explicable
-> diversité multi-documents
-> seuil de confiance et refus
-> contexte enrichi
-> génération Ollama contrôlée
-> sources, audit et diagnostic admin
```

### Reformulation optionnelle

`app/query_rewriter.py` transforme seulement les questions courtes ou contextuelles en questions autonomes. Il utilise Ollama local, ne répond jamais à la question et revient silencieusement à la question originale en cas d'échec. L'historique transmis est limité aux derniers messages utiles.

### Recherche hybride

`app/hybrid_retriever.py` combine :

- les résultats vectoriels Chroma ;
- une recherche lexicale sur les chunks déjà filtrés par permissions ;
- une fusion pondérée et dédupliquée par `chunk_id`.

Lorsque `RAG_PERMISSION_FILTERING_ENABLED=true`, la recherche lexicale appelle `fetch_all(allowed_groups=...)` et un chunk interdit ne peut pas réapparaître lors de la fusion. Le POC local utilise `false` par défaut : tous les profils interrogent le même corpus, tandis que les métadonnées de permissions restent conservées.

### Reranking et diversité

`app/reranker.py` combine score initial, termes exacts, correspondance approximative, nom de fichier, section et pénalité des chunks trop courts. Chaque résultat contient un bloc de debug avec score initial, score final, termes trouvés et raison.

Pour une synthèse ou une comparaison, le pipeline limite le nombre de chunks par document afin de couvrir plusieurs sources.

### Confiance et refus

Le pipeline refuse avant l'appel LLM lorsqu'aucun chunk ne passe le seuil ou lorsque le meilleur score est inférieur à `RAG_MIN_CONFIDENCE`. Pour une question vague avec résultats trop proches, il demande une précision. Cette logique évite de laisser le modèle compléter un contexte pauvre avec ses connaissances générales.

## Métadonnées et observabilité

Les nouveaux chargements ajoutent notamment `document_id`, `file_path`, `file_hash`, `last_modified`, `indexed_at`, `section_title` et `allowed_groups`. Les anciens chunks restent compatibles; une réingestion est nécessaire pour enrichir leur métadonnée.

L'audit JSONL contient désormais la question originale et reformulée, le mode de retrieval, les nombres de chunks initiaux et finaux et la confiance. Le dashboard admin affiche une synthèse de la configuration RAG et le dernier diagnostic observé.

## Configuration

Les réglages sont documentés dans `.env.example`. Les valeurs importantes sont :

```env
RAG_QUERY_REWRITE_ENABLED=true
RAG_HYBRID_SEARCH_ENABLED=true
RAG_VECTOR_TOP_K=12
RAG_KEYWORD_TOP_K=12
RAG_FINAL_TOP_K=5
RAG_RERANK_ENABLED=true
RAG_CONFIDENCE_ENABLED=true
RAG_MIN_CONFIDENCE=0.35
RAG_DIVERSITY_ENABLED=true
RAG_MAX_CHUNKS_PER_DOCUMENT=2
```

La reformulation ajoute un appel Ollama et doit rester désactivable lorsque la latence est prioritaire. OpenRouter n'intervient pas dans cette chaîne.

## Limites restantes

- Le reranker est heuristique, pas un cross-encoder spécialisé.
- La recherche lexicale parcourt les chunks autorisés; elle devra migrer vers un index sparse dédié à grande échelle.
- Le score fusionné est utile pour le tri, mais doit être calibré sur un corpus réel avant production.
- La reformulation dépend de la qualité du modèle Ollama et de l'historique disponible.
- Les métadonnées de section sont approximatives pour TXT/DOCX et absentes pour certains PDF.
- Les permissions du simulateur ne remplacent pas Entra ID et les permissions SharePoint réelles.
