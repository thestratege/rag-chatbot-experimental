# Plan d'évaluation RAG du simulateur SharePoint

## But

L'évaluation locale vérifie que le chatbot répond à partir des documents indexés, refuse les informations absentes et cite les bonnes sources. Elle couvre séparément le mode ouvert du POC actuel et le filtrage simulé disponible pour une phase future.

## Jeu de questions

Le fichier `tests/evaluation_questions_sharepoint_sim.json` contient les cas automatisés.

Chaque cas peut définir :

- `expected_behavior` : `answer` ou `refusal` ;
- `expected_sources_any` : au moins une source attendue ;
- `forbidden_sources` : sources qui ne doivent jamais apparaître ;
- `must_contain_any` : éléments attendus dans la réponse.
- `profile` : profil de permissions simulé propre au cas ;
- `enabled` : permet de garder un scénario de cycle de vie désactivé tant que son prérequis n'est pas préparé.
- `permission_modes` : limite le cas à `open`, `filtered` ou aux deux.

Ajouter des questions propres aux documents locaux après chaque démonstration, sans committer de contenu sensible.

## Lancement

Avec le backend simulateur démarré sur `8013` :

```bash
.venv/bin/python scripts/evaluate_rag_sharepoint_sim.py \
  --base-url http://127.0.0.1:8013 \
  --token sharepoint-sim-user \
  --profile demo-user
```

Cette commande utilise les cas `open` par défaut. Pour le mode filtré futur :

```bash
RAG_PERMISSION_FILTERING_ENABLED=true SHAREPOINT_SIM_API_PORT=8013 scripts/run_sharepoint_sim_backend.sh

.venv/bin/python scripts/evaluate_rag_sharepoint_sim.py \
  --base-url http://127.0.0.1:8013 \
  --token sharepoint-sim-user \
  --permission-mode filtered
```

Pour vérifier un document TI :

```bash
.venv/bin/python scripts/evaluate_rag_sharepoint_sim.py \
  --base-url http://127.0.0.1:8013 \
  --token sharepoint-sim-user \
  --profile demo-ti
```

Le script vérifie le provider `ollama`, les refus, les sources attendues/interdites, le profil et le temps de réponse. Il ne réindexe aucun document. Le score de confiance est affiché si l'API l'expose; l'audit JSONL et le dashboard restent les sources principales de diagnostic.

Le jeu couvre une réponse évidente, un terme exact, une question vague, un sujet absent, un document TI interdit/autorisé, une synthèse multi-documents et deux scénarios de cycle de vie désactivés par défaut.

## Mode ouvert du POC

Le mode par défaut est :

```env
RAG_PERMISSION_FILTERING_ENABLED=false
```

Les profils `demo-user`, `demo-ti`, `demo-rh` et `demo-admin` voient le même corpus. Les cas Open vérifient notamment que le document TI peut être retrouvé par plusieurs profils.

## Évaluation future du mode filtré

Pour chaque document restreint, prévoir au minimum deux cas :

1. profil non autorisé : refus ou absence de la source restreinte ;
2. profil autorisé : réponse avec la source attendue.

Une source interdite retournée est un échec critique, même si la réponse semble correcte.

Pour exécuter ces cas, démarrer le backend avec `RAG_PERMISSION_FILTERING_ENABLED=true`, puis ajouter :

```bash
--permission-mode filtered
```

## Lecture des résultats

La sortie résume :

- nombre de questions testées ;
- réussites et échecs ;
- temps moyen ;
- refus corrects ;
- sources correctes.

Compléter l'analyse avec `logs/rag_queries.jsonl` et une revue humaine de la clarté, du français et de la fidélité aux extraits.

Pour les scénarios après modification ou suppression, préparer un document fictif distinctif, synchroniser, activer le cas correspondant, puis vérifier qu'une ancienne version ou une source supprimée ne réapparaît jamais.

## Limites

- Les scores automatiques ne remplacent pas une revue humaine.
- Les performances dépendent d'Ollama, du modèle et du matériel.
- Les profils locaux ne prouvent pas encore l'intégration Entra ID.
- Les données sensibles ne doivent pas être ajoutées au jeu d'évaluation committé.
