# Widget installable et intégration SharePoint

## Objectif

Le chatbot doit rester un widget autonome, installable progressivement dans plusieurs contextes : site interne, portail métier, SharePoint, intranet ou page de démonstration. L'objectif est d'éviter une dépendance directe à SharePoint tout en préparant une intégration SharePoint professionnelle plus tard.

Pour la procédure SharePoint Online pas à pas, la checklist de démonstration et la trajectoire Microsoft Graph, consulter :

[docs/sharepoint_integration.md](sharepoint_integration.md)

## Pourquoi ne pas dépendre directement de SharePoint

Le chatbot a deux responsabilités séparées :

- le front-end affiche l'expérience conversationnelle ;
- le back-end FastAPI gère le RAG, les providers LLM, les sources et la sécurité documentaire.

Le rendre directement dépendant de SharePoint dès maintenant rendrait la V1 plus lourde à maintenir. Une approche autonome permet :

- une démonstration rapide par iframe ;
- une installation future sur d'autres sites ;
- une migration plus simple vers un Web Component ;
- une évolution SPFx propre lorsque l'authentification et les permissions seront prêtes.

## Architecture cible

```text
Page hôte ou SharePoint
        |
        | iframe, script widget ou SPFx
        v
Widget React autonome
        |
        | HTTPS /api/chat
        v
Back-end FastAPI sécurisé
        |
        +-- intent router
        +-- conversation manager
        +-- retrieval / ChromaDB
        +-- Ollama local
        +-- permissions futures
```

Le front-end ne contient jamais de clé API et n'accède jamais directement aux documents.

## Option 1 : iframe / Embed

Cette option est recommandée à court terme pour une démonstration rapide dans SharePoint ou dans n'importe quelle page qui accepte une iframe.

### URL locale

```text
http://localhost:5173/embed?apiBaseUrl=http://127.0.0.1:8010&theme=ism&title=Assistant%20DPC&compact=true
```

### Exemple iframe local

```html
<iframe
  src="http://localhost:5173/embed?apiBaseUrl=http://127.0.0.1:8010&theme=ism&title=Assistant%20DPC&compact=true"
  width="420"
  height="650"
  style="border:0; border-radius:16px; overflow:hidden;"
  title="Assistant DPC">
</iframe>
```

### Exemple iframe production

```html
<iframe
  src="https://chatbot.example.org/embed?apiBaseUrl=https://api-chatbot.example.org&theme=ism&title=Assistant%20DPC&compact=true"
  width="420"
  height="650"
  style="border:0; border-radius:16px; overflow:hidden;"
  title="Assistant DPC">
</iframe>
```

### Paramètres query string

- `apiBaseUrl` : URL du back-end FastAPI.
- `theme` : `default` ou `ism`.
- `title` : titre affiché dans le widget.
- `providerLabel` : libellé court affiché sous le titre.
- `compact` : `true` pour adapter l'interface à un iframe réduit.

Ne passez jamais de clé API, secret, jeton utilisateur ou information sensible dans la query string.

### Page de test locale

```text
http://localhost:5173/embed-test.html
```

Cette page contient un iframe local vers `/embed` et permet de vérifier rapidement :

- l'affichage dans un cadre 420x650 ;
- la communication avec FastAPI ;
- les sources ;
- le refus d'hallucination ;
- le comportement responsive.

## Option 2 : Web Component

Cette option est recommandée à moyen terme pour les sites qui acceptent du JavaScript personnalisé.

Exemple cible :

```html
<script src="https://chatbot.example.org/widget/ism-chatbot.js"></script>

<ism-chatbot
  api-base-url="https://api-chatbot.example.org"
  theme="ism"
  title="Assistant DPC">
</ism-chatbot>
```

Cette approche permettrait une installation plus propre sur plusieurs sites, sans iframe. Elle devra toutefois être validée selon les politiques de sécurité du site hôte :

- autorisation des scripts externes ;
- Content Security Policy ;
- gestion de l'authentification ;
- isolation CSS ;
- compatibilité navigateur.

Le Web Component n'est pas implémenté dans cette V1. La page `/embed` prépare déjà les paramètres qui seront utiles à ce futur composant.

## Option 3 : SPFx Web Part

Cette option est recommandée à long terme pour une intégration SharePoint professionnelle.

Architecture cible :

```text
SharePoint SPFx Web Part
        |
        | encapsule ou charge le widget React
        v
Widget chatbot
        |
        | appelle le back-end FastAPI sécurisé
        v
API RAG + permissions documentaires
        |
        +-- Microsoft Entra ID
        +-- groupes utilisateurs
        +-- audit logs
        +-- permissions par document ou collection
```

SPFx permettra :

- une installation native dans SharePoint ;
- Microsoft Entra ID ;
- le passage d'un jeton utilisateur au back-end ;
- des permissions par groupe ;
- une gouvernance plus alignée avec Microsoft 365.

Le projet SPFx complet n'est pas créé maintenant. Il faudra le faire lorsque l'authentification, les permissions et le modèle de déploiement seront validés.

## Comparaison des options

| Option | Usage recommandé | Avantages | Limites |
|---|---|---|---|
| iframe / Embed | Démo rapide | Simple, portable, peu coûteux | Contrôle limité, dépend des politiques iframe |
| Web Component | Multi-sites moyen terme | Installation propre avec script et balise | Demande validation CSP et scripts externes |
| SPFx Web Part | SharePoint production | Natif SharePoint, Entra ID, gouvernance | Plus long à développer et déployer |

## Recommandations

- Court terme : utiliser `/embed` dans une iframe.
- Moyen terme : préparer un Web Component si plusieurs sites non SharePoint doivent installer le chatbot.
- Long terme : créer un SPFx Web Part pour SharePoint avec Microsoft Entra ID et permissions documentaires.

## Configuration locale

Terminal 1 :

```bash
ollama serve
```

Terminal 2 :

```bash
cd /Users/barbellaellobe/Documents/ChatBootMonfort/rag-chatbot-experimental
source .venv/bin/activate
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:1.5b-instruct scripts/run_backend.sh
```

Terminal 3 :

```bash
cd /Users/barbellaellobe/Documents/ChatBootMonfort/rag-chatbot-experimental
scripts/run_frontend.sh
```

Tester :

```text
http://localhost:5173
http://localhost:5173/embed?apiBaseUrl=http://127.0.0.1:8010&theme=ism&title=Assistant%20DPC&compact=true
http://localhost:5173/embed-test.html
```

## Configuration production

- Héberger le front-end React sur un domaine interne, par exemple `https://chatbot.example.org`.
- Héberger FastAPI sur un domaine API, par exemple `https://api-chatbot.example.org`.
- Configurer `ALLOWED_ORIGINS_PRODUCTION` côté API avec les origines autorisées.
- Servir tout le trafic en HTTPS.
- Restreindre CORS et les politiques iframe.

Exemple de configuration :

```env
ENVIRONMENT=production
ALLOWED_ORIGINS_PRODUCTION=https://chatbot.example.org,https://tenant.sharepoint.com
CSP_FRAME_ANCESTORS="'self' https://chatbot.example.org https://tenant.sharepoint.com"
PUBLIC_API_BASE_URL=https://api-chatbot.example.org
```

## Sécurité minimale avant intégration

Avant une intégration réelle dans SharePoint ou un autre portail, appliquer au minimum ces règles :

- CORS allowlist : déclarer seulement les origines front-end autorisées avec `ALLOWED_ORIGINS` en développement et `ALLOWED_ORIGINS_PRODUCTION` en production.
- Iframe allowlist : contrôler les domaines qui peuvent intégrer le widget avec `CSP_FRAME_ANCESTORS`.
- CSP `frame-ancestors` : autoriser uniquement le site du widget, les pages hôtes validées et le tenant SharePoint prévu.
- HTTPS obligatoire en production pour le front-end, l'API et la page hôte.
- Aucun secret dans le front-end, dans les query strings ou dans `frontend/.env.local`.
- OpenRouter réservé aux benchmarks ou aux données fictives/anonymisées.
- Ollama local recommandé pour les documents internes.
- Logs prudents : ne pas journaliser le contenu complet des documents, les clés API ou les jetons.
- Authentification future : Microsoft Entra ID ou mécanisme interne à ajouter avant données sensibles.
- Permissions documentaires futures : filtrer les sources selon l'utilisateur ou le groupe avant génération.

## Sécurité front-end

- Aucune clé API dans le front-end.
- Aucun secret dans les query strings.
- `theme`, `title`, `providerLabel` et `compact` sont uniquement des paramètres UI.
- `apiBaseUrl` doit pointer vers une API maîtrisée.
- Le front-end n'accède jamais directement aux documents.

## Sécurité API

- HTTPS obligatoire en production.
- CORS avec allowlist stricte via `ALLOWED_ORIGINS` et `ALLOWED_ORIGINS_PRODUCTION`.
- Ne pas utiliser `allow_origins=["*"]` en production.
- Authentification future à ajouter.
- Rate limiting futur à ajouter.
- Validation stricte des inputs.
- Logs sans contenu documentaire sensible.

Le back-end conserve `FRONTEND_ORIGIN` pour compatibilité, mais privilégie `ALLOWED_ORIGINS` en développement et `ALLOWED_ORIGINS_PRODUCTION` en production. Pour une production interne, déclarer uniquement les domaines nécessaires.

## Sécurité iframe

- Configurer les domaines autorisés.
- Prévoir une politique `Content-Security-Policy` avec `frame-ancestors`, pilotée par `CSP_FRAME_ANCESTORS`.
- Éviter d'autoriser tous les domaines.
- Vérifier les restrictions SharePoint Embed web part.
- Utiliser HTTPS en production.

`ALLOWED_FRAME_ANCESTORS` reste accepté comme alias de compatibilité, mais `CSP_FRAME_ANCESTORS` est le nom recommandé pour les nouveaux déploiements.

## Sécurité documentaire

- Documents indexés localement.
- OpenRouter réservé aux benchmarks ou données fictives.
- Ollama local recommandé pour documents internes.
- Permissions documentaires à prévoir avant toute donnée sensible.
- Ne pas indexer de données sensibles sans validation de gouvernance.

## Sécurité SharePoint future

- Microsoft Entra ID.
- Groupes utilisateurs.
- Permissions par document ou collection.
- SPFx comme enveloppe native future.
- Audit logs et traçabilité des questions.

## Authentification future

L'iframe simple reste l'option de démonstration rapide. Elle montre le widget, le dialogue, les sources et l'intégration visuelle dans une page hôte.

Pour prouver la protection des routes avant Entra ID, la démo peut utiliser temporairement `AUTH_PROVIDER=mock` et un token back-end configurable. Le widget permet de saisir ce token manuellement si `VITE_AUTH_DEMO_ENABLED=true`. Aucun token n'est embarqué dans le code front-end.

En production, l'API FastAPI devra être protégée. Le front-end ne doit pas contenir de secret et ne doit jamais valider seul les droits d'accès. Le back-end devra recevoir un token Bearer, vérifier sa signature, contrôler l'audience, l'émetteur, l'expiration et les groupes autorisés.

Dans SharePoint, l'approche professionnelle sera de créer plus tard un Web Part SPFx. Ce Web Part pourra obtenir un token Microsoft Entra ID pour l'utilisateur connecté, puis appeler le back-end FastAPI avec `Authorization: Bearer ...`.

Architecture cible :

```text
SharePoint / SPFx
        -> token utilisateur Microsoft Entra ID
        -> API FastAPI protégée
        -> validation JWT
        -> contrôle groupes / permissions
        -> retrieval uniquement sur documents autorisés
```

La préparation technique est décrite ici :

[docs/security_authentication.md](security_authentication.md)

## Limites actuelles

- `/embed` ne gère pas encore l'authentification utilisateur.
- Le Web Component n'est pas encore implémenté.
- SPFx n'est pas encore développé.
- Les permissions documentaires ne sont pas encore appliquées.
- Le contrôle de domaine iframe et CSP devra être configuré lors du déploiement.

## Prochaines étapes

1. Tester `/embed` localement avec les trois modes : `mock`, `retrieval_only`, `ollama`.
2. Héberger une version interne de démonstration.
3. Valider les domaines CORS et iframe autorisés.
4. Définir le modèle d'authentification Microsoft Entra ID.
5. Choisir entre Web Component et SPFx selon les politiques de sécurité du portail cible.
