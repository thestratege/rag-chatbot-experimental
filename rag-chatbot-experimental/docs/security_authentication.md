# Préparation Microsoft Entra ID

## Objectif

Cette V1 prépare l'authentification Microsoft Entra ID sans l'activer par défaut. Le but est d'avoir une architecture prête pour protéger l'API FastAPI, identifier l'utilisateur, vérifier des groupes plus tard et appliquer des permissions documentaires.

L'authentification réelle n'est pas encore implémentée : aucun appel externe de validation JWT n'est effectué dans cette étape.

## Développement et production

En développement, la démo doit rester simple :

```env
ENVIRONMENT=development
AUTH_ENABLED=false
AUTH_PROVIDER=none
```

Avec cette configuration, l'API utilise un contexte utilisateur anonyme contrôlé : `anonymous_demo_user`. Cela permet de tester `mock`, `retrieval_only`, `ollama`, `/embed` et Swagger sans connexion Microsoft.

Pour démontrer une API protégée sans connexion Microsoft réelle :

```env
ENVIRONMENT=demo
AUTH_ENABLED=true
AUTH_PROVIDER=mock
DEMO_AUTH_TOKEN="<token-utilisateur-fourni-hors-code>"
DEMO_ADMIN_AUTH_TOKEN="<token-admin-fourni-hors-code>"
```

Dans ce mode, les routes sensibles exigent un token Bearer configurable uniquement côté back-end. Les tokens ne doivent pas être stockés dans le front-end et ce provider ne doit jamais être utilisé en production.

En production, la configuration recommandée sera :

```env
ENVIRONMENT=production
AUTH_ENABLED=true
AUTH_PROVIDER=entra
ENTRA_TENANT_ID=<tenant-id>
ENTRA_CLIENT_ID=<api-client-id>
ENTRA_AUDIENCE=<api-audience>
ENTRA_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
AUTH_REQUIRED_GROUPS=<group-id-1>,<group-id-2>
```

Ne mettez pas de secret dans ces variables côté front-end. Les identifiants publics comme `tenant_id` ou `client_id` ne remplacent pas une validation côté serveur.

## Rôle de Microsoft Entra ID

Microsoft Entra ID servira à :

- authentifier l'utilisateur ;
- émettre un token Bearer pour l'API ;
- porter l'identité et les groupes de l'utilisateur ;
- permettre au back-end de décider quelles collections ou sources sont consultables.

Le front-end ou un futur Web Part SPFx devra obtenir un token utilisateur, puis appeler FastAPI avec :

```http
Authorization: Bearer <access_token>
```

## Comportement actuel

Le module `app/auth.py` fournit déjà :

- `UserContext` ;
- `verify_auth` ;
- `get_current_user_optional` ;
- un bypass de démo si `AUTH_ENABLED=false` ;
- une erreur `401` claire si `AUTH_ENABLED=true` et aucun token Bearer n'est fourni ;
- un provider `mock` de démonstration qui compare le token sans le journaliser ;
- une fonction préparatoire de contrôle des groupes avec erreur `403`.

Avec `AUTH_PROVIDER=mock`, seuls les tokens back-end configurés dans `DEMO_AUTH_TOKEN` et `DEMO_ADMIN_AUTH_TOKEN` sont acceptés. Avec `AUTH_PROVIDER=entra`, la V1 retourne volontairement une erreur claire indiquant que la validation JWT Entra ID n'est pas encore implémentée. C'est plus sûr que d'accepter un token Entra ID non vérifié.

## Autorisations par défaut

La démo suit une logique deny-by-default lorsque `AUTH_ENABLED=true`. Toute requête API est protégée sauf si son chemin figure explicitement dans la liste publique.

Routes publiques :

- `/health` : public dans tous les environnements, avec réponse minimale ;
- `/docs`, `/docs/oauth2-redirect`, `/openapi.json`, `/redoc` : publics uniquement en `development`, `demo` et `test` pour conserver Swagger pendant la démonstration ;
- requêtes `OPTIONS` : autorisées pour que les contrôles CORS du navigateur fonctionnent.

Routes authentifiées :

- `/` ;
- `/api/chat` ;
- `/chat` ;
- `/api/conversations/reset`.

Route administrative :

- `/ingest` : nécessite le rôle `admin`.

Le garde global bloque également une nouvelle route oubliée par défaut. Les dépendances FastAPI ajoutent ensuite une règle locale explicite :

- `require_auth()` pour une route utilisateur ;
- `require_role("admin")` pour une route administrative ou documentaire sensible.

Le front-end `/embed` peut rester public parce qu'il ne lit aucun document et n'expose aucune donnée sensible. Il doit appeler l'API protégée pour obtenir une réponse documentaire.

## Identités mock de démonstration

| Identité | Variable back-end | Exemple | Rôles | Usage |
|---|---|---|---|---|
| `demo-user` | `DEMO_AUTH_TOKEN` | valeur injectée côté back-end | `demo` | Utiliser le chatbot |
| `demo-admin` | `DEMO_ADMIN_AUTH_TOKEN` | valeur injectée côté back-end | `admin` | Lancer `/ingest` |

Les tokens mock sont des valeurs de démonstration. Ils ne sont ni journalisés, ni retournés par l'API, ni préremplis dans le front-end.

## Validation JWT future

La prochaine étape consistera à valider réellement le token :

- récupérer les clés publiques Entra ID via JWKS ;
- vérifier la signature ;
- vérifier `iss`, `aud`, `exp`, `nbf` ;
- extraire l'identifiant utilisateur ;
- extraire les groupes ou rôles applicatifs ;
- rejeter les tokens expirés ou mal formés.

Cette validation doit être faite côté back-end. Le front-end ne doit jamais décider seul qu'un utilisateur est autorisé.

## Groupes et permissions documentaires

Après validation du token, le back-end pourra comparer les groupes de l'utilisateur avec `AUTH_REQUIRED_GROUPS`. Ensuite, les permissions documentaires devront être appliquées avant la génération :

- filtrer les collections ChromaDB selon l'utilisateur ;
- masquer les sources non autorisées ;
- éviter d'envoyer au LLM des extraits non consultables par l'utilisateur ;
- tracer les accès dans des logs d'audit prudents.

## SharePoint et SPFx

Pour une intégration SharePoint professionnelle, SPFx pourra agir comme enveloppe native :

```text
SharePoint SPFx Web Part
        -> obtient un token Entra ID
        -> appelle FastAPI avec Authorization: Bearer ...
        -> FastAPI valide le token
        -> FastAPI applique les permissions documentaires
```

L'iframe reste utile pour la démonstration rapide, mais elle ne remplace pas une intégration authentifiée en production.

## Limites actuelles

- Pas de validation JWT réelle.
- Pas de connexion Microsoft côté front-end.
- Pas de mapping groupes -> permissions documentaires.
- Pas de rate limiting par utilisateur.
- Pas encore d'audit logs complets.
- `/health` reste public et doit rester minimal en production.
- Le provider `mock` et `DEMO_AUTH_TOKEN` sont strictement réservés à la démonstration.
