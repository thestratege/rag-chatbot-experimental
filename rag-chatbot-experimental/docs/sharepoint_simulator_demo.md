# Démonstration de bibliothèque SharePoint simulée

## Objectif

Le simulateur reproduit localement le comportement attendu d'une bibliothèque SharePoint vivante, sans appeler Microsoft Graph et sans modifier un vrai site SharePoint :

```text
data/sharepoint_simulator/documents
  -> synchronisation incrémentale
  -> data/vector_store_sharepoint_sim
  -> FastAPI :8013
  -> Ollama local/distant
  -> React et dashboard /admin
```

Le backend principal, `data/documents` et `data/vector_store` ne sont jamais supprimés ni remplacés.

## Préparer l'environnement

```bash
scripts/setup_sharepoint_simulator.sh
```

Ce script crée :

- `data/sharepoint_simulator/documents` : bibliothèque simulée ;
- `data/sharepoint_simulator/archive` : zone disponible pour les démonstrations ;
- `data/sharepoint_simulator/permissions.json` : groupes locaux ;
- `data/vector_store_sharepoint_sim` : index Chroma isolé ;
- `logs/sharepoint_simulator.log` et `logs/rag_queries.jsonl` lors de l'utilisation.

Les documents, index, états et logs du simulateur sont ignorés par Git.

## Synchronisation incrémentale

Déposer des fichiers `.txt`, `.md` ou `.pdf` texte dans :

```text
data/sharepoint_simulator/documents
```

Puis lancer :

```bash
scripts/sync_sharepoint_simulator.sh
```

Le résumé distingue les documents ajoutés, modifiés, supprimés et inchangés. Pour une modification, les anciens chunks du document sont supprimés avant l'ajout des nouveaux. Pour une suppression, le document passe au statut `deleted` et ses chunks ne sont plus recherchables.

L'état est conservé dans `data/sharepoint_simulator/index_state.json`.

## Démarrer la démonstration

Terminal backend :

```bash
SHAREPOINT_SIM_API_PORT=8013 scripts/run_sharepoint_sim_backend.sh
```

Le script utilise uniquement des variables de processus. Il ne modifie pas le vrai `.env`, désactive OpenRouter et active l'authentification mock locale :

- utilisateur : `sharepoint-sim-user` ;
- administrateur : `sharepoint-sim-admin`.

Ces valeurs sont des identifiants de POC locaux, pas des secrets de production.

Terminal frontend :

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8013 \
VITE_RUNTIME_MODE=local \
VITE_AUTH_DEMO_ENABLED=true \
npm run dev
```

Ouvrir :

- chatbot : `http://localhost:5173` ;
- dashboard : `http://localhost:5173/admin?apiBaseUrl=http://127.0.0.1:8013`.

Dans le chatbot, activer le mode démo authentifié et utiliser `sharepoint-sim-user`. Dans le dashboard, utiliser `sharepoint-sim-admin`.

## Scénario ajout, modification et suppression

1. Poser une question avant l'ajout du document et constater le refus.
2. Ajouter un document dans `data/sharepoint_simulator/documents`.
3. Lancer `scripts/sync_sharepoint_simulator.sh` ou utiliser le bouton **Synchroniser** du dashboard.
4. Poser la même question et vérifier la source.
5. Modifier le contenu du fichier.
6. Synchroniser et vérifier que la réponse et le chunk ont changé.
7. Supprimer le fichier.
8. Synchroniser et vérifier que le document est `deleted` et n'apparaît plus dans les sources.

## Permissions simulées

Pour le POC local actuel, le mode par défaut est un accès documentaire ouvert :

```env
RAG_PERMISSION_FILTERING_ENABLED=false
```

Tous les profils de démonstration interrogent alors le même corpus indexé. Les groupes et métadonnées `allowed_groups` restent conservés dans l'index, l'état du simulateur, l'audit et le dashboard, mais ils ne bloquent aucun chunk.

Le comportement historique peut être réactivé pour une démonstration future :

```env
RAG_PERMISSION_FILTERING_ENABLED=true
```

Le fichier `data/sharepoint_simulator/permissions.json` associe un fichier à des groupes :

```json
{
  "procedure_publique.txt": ["public"],
  "procedure_ti.txt": ["TI", "admin"],
  "procedure_rh.txt": ["RH", "admin"]
}
```

Un fichier absent de cette configuration reçoit `["public"]`.

Profils locaux disponibles :

| Profil | Groupes |
|---|---|
| `anonymous_demo_user` | public |
| `demo-user` | public |
| `demo-ti` | public, TI |
| `demo-rh` | public, RH |
| `demo-manager` | public, gestionnaires |
| `demo-admin` | public, TI, RH, gestionnaires, admin |

Le header `X-Demo-Profile` est accepté uniquement lorsque le simulateur est actif dans un environnement local. Il ne constitue pas un mécanisme de sécurité de production.

Test public :

```bash
curl http://127.0.0.1:8013/api/chat \
  -H "Authorization: Bearer sharepoint-sim-user" \
  -H "X-Demo-Profile: demo-user" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"Quelle est la procédure TI ?","mode":"auto"}'
```

Test TI :

```bash
curl http://127.0.0.1:8013/api/chat \
  -H "Authorization: Bearer sharepoint-sim-user" \
  -H "X-Demo-Profile: demo-ti" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":null,"message":"Quelle est la procédure TI ?","mode":"auto"}'
```

Lorsque `RAG_PERMISSION_FILTERING_ENABLED=true`, la règle appliquée dans le retriever est stricte : un chunk n'est jamais retourné si ses `allowed_groups` ne croisent pas les groupes effectifs de l'utilisateur. Lorsqu'il vaut `false`, les profils voient tous les mêmes documents, sous réserve de la pertinence du retrieval.

## Endpoints admin locaux

Les routes suivantes exigent le rôle `admin` :

- `GET /admin/index/status`
- `GET /admin/index/documents`
- `POST /admin/index/sync`
- `POST /admin/index/reset-simulator`

Exemple :

```bash
curl http://127.0.0.1:8013/admin/index/status \
  -H "Authorization: Bearer sharepoint-sim-admin"
```

Le reset vide seulement l'index du simulateur lorsque `SHAREPOINT_SIMULATOR_ENABLED=true`.

## Audit

Lorsque `RAG_AUDIT_LOG_ENABLED=true`, chaque question RAG écrit une ligne JSON dans :

```text
logs/rag_queries.jsonl
```

Le journal contient le temps de réponse, le provider, les sources, l'utilisateur et ses groupes, ainsi que la question originale/reformulée, le mode de retrieval, la confiance, les nombres de chunks initiaux/finals et l'état du filtrage documentaire. Aucun token n'est journalisé. Pour un futur environnement sensible, la question devra être masquée ou pseudonymisée selon la politique de conservation.

Le dashboard `/admin` affiche aussi un bloc **Diagnostic RAG** avec le mode de recherche, la reformulation, le reranking, le filtrage des permissions, les top-k, le seuil de confiance et le dernier diagnostic observé.

## Limites

- Le header de profil et les tokens mock sont réservés au POC local.
- L'indexation simultanée par plusieurs processus n'est pas gérée.
- Les PDF scannés nécessitent un OCR.
- Le filtrage repose sur les métadonnées locales, pas sur les permissions SharePoint réelles.
- Le dashboard admin n'est pas une console de production.
- Microsoft Graph, les webhooks SharePoint et Entra ID restent à intégrer par l'équipe TI.

## Remplacement futur

Dans l'architecture cible, Microsoft Graph remplacera le dossier simulé et fournira les identifiants, versions et permissions. Microsoft Entra ID remplacera les tokens et profils de démonstration. Le vector store, le retriever filtré, l'audit et l'API pourront rester les mêmes avec des adaptateurs de production.

## Validation locale observée le 9 juin 2026

La validation a utilisé uniquement les documents fictifs de `data/sample_documents`.

- première synchronisation : 6 documents ajoutés, 6 chunks ajoutés, 0 erreur ;
- synchronisation sans changement : 6 documents inchangés, 0 embedding recalculé ;
- modification de `procedure_ti.txt` : 1 document modifié, 1 ancien chunk supprimé, 1 nouveau chunk ajouté ;
- suppression simulée par déplacement vers `archive` : 1 document supprimé et 1 chunk retiré ;
- profil public : refus exact pour la question TI et aucune source retournée ;
- profil TI : réponse avec la seule source `procedure_ti.txt` ;
- endpoint admin : 6 documents indexés et 6 chunks visibles ;
- audit JSONL : profils, temps de réponse et sources enregistrés sans token.
