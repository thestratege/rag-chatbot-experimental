# Intégration SharePoint Online

## Objectif

Le chatbot reste une application autonome. SharePoint Online est un canal d'intégration : il affiche le widget, mais le front-end React et le back-end FastAPI conservent leurs responsabilités propres.

Deux niveaux sont préparés :

1. une démonstration rapide avec la page React `/embed` dans un composant Web `Embed` SharePoint ;
2. une future intégration native avec un Web Part SPFx et Microsoft Entra ID.

Aucun projet SPFx, appel Microsoft Graph ou secret front-end n'est ajouté dans cette V1.

Documents associés :

- [Garde-fous de preuve de concept](poc_guardrails.md)
- [Procédure de tests de vulnérabilités](vulnerability_testing.md)

## Vérifications effectuées sur le site SharePoint

- Domaine tenant : https://hopitalmontfort.sharepoint.com
- Site : Test Site / site de démonstration
- Page modifiable : oui
- Type de page : classique
- Option disponible : INSÉRER → Code incorporé
- Test iframe : bloqué par SharePoint
- Message observé : “Nous ne pouvons pas insérer ce code HTML car il contient un script non sécurisé.”
- HTML Field Security : accès refusé
- Conclusion : autorisation du domaine iframe à faire par un administrateur SharePoint ou administrateur de collection de sites

## Interprétation technique

Le blocage observé ne vient pas du chatbot. Il intervient avant même que le widget soit chargé : SharePoint refuse le code incorporé selon sa politique d'autorisation des iframes.

Pour intégrer le chatbot, le domaine HTTPS du front React devra être ajouté dans `HTML Field Security` par un administrateur SharePoint ou un administrateur de collection de sites. Il ne faut pas demander d'autoriser tous les domaines. La demande doit porter uniquement sur le domaine HTTPS du chatbot, par exemple `https://URL_FRONTEND_CHATBOT`.

La validation iframe reste donc envisageable, mais elle dépend d'une autorisation SharePoint explicite.

## Éléments à demander au superviseur/TI

- Confirmation que l'intégration est une preuve de concept contrôlée.
- URL HTTPS temporaire pour le front React.
- URL HTTPS temporaire pour l'API FastAPI.
- Validation du domaine qui sera autorisé dans SharePoint.
- Autorisation du domaine front dans HTML Field Security.
- Confirmation qu'aucune automatisation réelle ne doit être activée.
- Confirmation de la bibliothèque documentaire de test, si une ingestion SharePoint est envisagée plus tard.
- Validation que les tests restent sur documents fictifs ou données contrôlées.

## Architecture actuelle

```text
Page SharePoint avec Embed web part
        |
        | iframe HTTPS vers /embed
        v
Widget React/Vite hébergé
        |
        | HTTPS vers FastAPI
        v
FastAPI sécurisé
        |
        +-- LLM_PROVIDER=mock possible pour la démo visuelle
        +-- auth réelle à préparer avec Entra ID / SPFx
        +-- /health public et minimal
        +-- /api/chat protégé
        +-- /ingest réservé au rôle admin
```

La route `/embed` affiche uniquement le widget conversationnel. En mode `local`, elle peut afficher le champ token si `VITE_AUTH_DEMO_ENABLED=true`. En mode `sharepoint`, aucun champ token n'est affiché : l'utilisateur final est déjà connecté à SharePoint et ne doit pas saisir de mot de passe ou de token manuel dans le chatbot.

## Démo locale

Créer `frontend/.env.local` à partir de l'exemple si nécessaire :

```bash
cp frontend/.env.local.example frontend/.env.local
```

Les valeurs publiques locales sont :

```env
VITE_API_BASE_URL=http://127.0.0.1:8010
VITE_RUNTIME_MODE=local
VITE_AUTH_DEMO_ENABLED=true
```

Injecter les tokens mock uniquement dans le processus back-end, avec des valeurs communiquées hors du dépôt :

```bash
ENVIRONMENT=demo \
AUTH_ENABLED=true \
AUTH_PROVIDER=mock \
DEMO_AUTH_TOKEN="<token-utilisateur-fourni-hors-code>" \
DEMO_ADMIN_AUTH_TOKEN="<token-admin-fourni-hors-code>" \
LLM_PROVIDER=mock \
scripts/run_backend.sh
```

Dans un second terminal :

```bash
scripts/run_frontend.sh
```

Puis ouvrir :

```text
http://localhost:5173/embed
http://localhost:5173/embed-test.html
```

Le token utilisateur doit être saisi manuellement dans le widget. Ne jamais le placer dans `frontend/.env.local`, une query string ou le code source.

`frontend/public/embed-test.html` simule localement une intégration iframe 420x700. Cette page n'est pas SharePoint ; elle sert uniquement à vérifier l'apparence et le comportement du widget `/embed` avant un hébergement HTTPS.

## Intégration rapide avec Embed web part

Pour SharePoint Online, héberger le front-end et FastAPI sur des URL HTTPS joignables par les utilisateurs. `localhost` ne fonctionne que sur la machine locale et ne constitue pas un hébergement SharePoint.

Configurer le front hébergé :

```env
VITE_API_BASE_URL=https://URL_BACKEND_FASTAPI
VITE_RUNTIME_MODE=sharepoint
VITE_AUTH_DEMO_ENABLED=false
```

Avec cette configuration, `/embed` masque toujours le champ token, même si le widget est intégré dans une iframe. Cette V1 prépare donc l'intégration visuelle SharePoint sans demander de mot de passe utilisateur final.

Ajouter dans SharePoint un composant Web `Embed`, puis coller :

```html
<iframe
  src="https://URL_FRONTEND_CHATBOT/embed"
  width="420"
  height="700"
  style="border:0;"
></iframe>
```

Le domaine du widget devra être autorisé par la politique du tenant SharePoint.

## Configuration back-end pour SharePoint

Pour l'intégration iframe SharePoint, l'API doit au minimum autoriser les origines nécessaires et rester en HTTPS :

```env
SHAREPOINT_TENANT_ORIGIN=https://hopitalmontfort.sharepoint.com
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://hopitalmontfort.sharepoint.com,https://URL_FRONTEND_CHATBOT
CSP_FRAME_ANCESTORS="'self' https://hopitalmontfort.sharepoint.com"
```

Les règles importantes :

- ne jamais utiliser `allow_origins=["*"]` avec des credentials ;
- autoriser l'origine du front hébergé, car les appels API de l'iframe proviennent de `https://URL_FRONTEND_CHATBOT` ;
- autoriser aussi le tenant SharePoint en prévision d'un appel direct futur depuis SPFx ;
- conserver les headers CORS sur les réponses `401` et `403` afin que le navigateur affiche une erreur d'authentification lisible ;
- garder `/health` public et minimal ;
- garder `/api/chat` protégé et `/ingest` réservé au rôle `admin`.

Le provider `mock` peut encore servir à une démonstration locale contrôlée, mais il ne doit pas être utilisé comme mécanisme d'authentification final dans SharePoint. En production SharePoint, le champ token manuel doit rester masqué et l'authentification doit passer par l'architecture Entra ID / SPFx ou par un mécanisme d'API sécurisé validé par l'équipe TI.

## CSP et iframe

`CSP_FRAME_ANCESTORS` prépare l'en-tête :

```http
Content-Security-Policy: frame-ancestors 'self' https://hopitalmontfort.sharepoint.com
```

Le back-end FastAPI ajoute cet en-tête à ses réponses. Pour autoriser réellement l'intégration de `/embed`, le même `frame-ancestors` doit surtout être configuré sur l'hébergement statique ou le reverse proxy qui sert le front-end React. Un en-tête posé uniquement sur les réponses API ne contrôle pas l'affichage de la page React dans une iframe.

N'autoriser que les sites hôtes validés. Ne pas ouvrir `frame-ancestors` à tous les domaines.

## Checklist prêt pour intégration SharePoint

### Déjà validé

- Domaine SharePoint identifié.
- Page modifiable.
- Code incorporé disponible.
- Iframe bloquée par politique SharePoint.
- Accès HTML Field Security refusé.
- Mode `/embed` prêt localement.
- Mode SharePoint sans champ token préparé.
- Tests automatisés validés.
- Build React validé.
- Procédure de tests de vulnérabilités créée.

### À obtenir

- URL HTTPS front React.
- URL HTTPS API FastAPI.
- Domaine du front autorisé dans HTML Field Security.
- Confirmation POC contrôlée.
- Bibliothèque documentaire de test.
- Validation TI avant automatisation réelle.
- Validation sécurité avant exposition réseau.

## Limites du provider mock

`AUTH_PROVIDER=mock` et `LLM_PROVIDER=mock` servent uniquement à présenter l'expérience en local ou dans une démonstration très contrôlée :

- le token est saisi manuellement ;
- les utilisateurs ne sont pas connectés avec leur identité Microsoft ;
- les permissions documentaires réelles ne sont pas appliquées ;
- le mode mock est refusé par la configuration en `ENVIRONMENT=production`.

Ne pas utiliser cette configuration avec des documents sensibles ni comme expérience utilisateur finale SharePoint.

## Cible future SPFx et Entra ID

Pour une intégration native SharePoint, un Web Part SPFx remplacera l'iframe :

```text
SharePoint SPFx Web Part
        |
        | SPFx ou MSAL récupère un access token Entra ID
        v
Widget React
        |
        | Authorization: Bearer <access_token>
        v
FastAPI
        |
        +-- valide le JWT via les clés JWKS Entra ID
        +-- vérifie issuer, audience, expiration et scopes ou groupes
        +-- mappe les groupes Entra ID vers les rôles user/admin
        +-- applique les permissions documentaires
```

À cette étape, `AUTH_PROVIDER=mock` sera remplacé par `AUTH_PROVIDER=entra`. Le back-end devra être l'unique autorité de validation ; le front-end ne devra jamais décider seul des droits d'accès.

## Cible future Microsoft Graph

L'ingestion SharePoint devra être ciblée et gouvernée :

1. sélectionner explicitement une bibliothèque documentaire autorisée ;
2. lire les fichiers via Microsoft Graph avec une identité applicative contrôlée ;
3. découper et indexer les contenus dans ChromaDB ou Qdrant ;
4. ajouter aux chunks les métadonnées :
   - `site_id`
   - `drive_id`
   - `item_id`
   - `source_url`
   - `allowed_groups`
   - `confidentiality_level`
5. filtrer les documents autorisés avant le retrieval et avant tout envoi d'extraits au LLM.

Éviter toute ingestion globale non contrôlée du tenant SharePoint.

## Prérequis à valider avec l'équipe TI

- URL HTTPS interne pour héberger le front-end React.
- URL HTTPS interne pour exposer FastAPI.
- Domaine SharePoint exact : `https://hopitalmontfort.sharepoint.com`.
- Autorisation d'utiliser le composant Web `Embed`.
- Allowlist du domaine du widget dans les politiques SharePoint.
- Reverse proxy ou hébergement statique capable de servir `Content-Security-Policy: frame-ancestors ...`.
- Stratégie future d'enregistrement d'application Entra ID.
- Groupes Entra ID destinés aux rôles utilisateur et administrateur.
- Bibliothèque documentaire SharePoint ciblée et règles de confidentialité.

## Prochaine étape

Après validation de la démo iframe, préparer une spécification SPFx/Entra ID : enregistrement d'application, audience API, scopes, groupes, stratégie JWT/JWKS côté FastAPI et filtrage documentaire par permissions.
