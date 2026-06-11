# Garde-fous de preuve de concept

## Statut

Cette intégration est une preuve de concept contrôlée, pas une installation définitive. Elle sert à valider l'architecture, l'expérience `/embed`, la séparation front/back et la faisabilité SharePoint avant tout branchement réel.

## Garde-fous obligatoires

- Aucun envoi automatique de courriel réel.
- Aucune modification réelle de listes SharePoint.
- Aucune suppression ou écriture dans SharePoint.
- Aucune ingestion globale de documents réels.
- Aucun accès à documents sensibles non validés.
- Utilisation de documents fictifs ou d'une bibliothèque de test uniquement.
- `LLM_PROVIDER=mock` ou modèle local contrôlé pendant les tests.
- Aucun appel externe non validé.
- Aucun secret côté front-end.
- Les logs ne doivent pas contenir de données sensibles.
- Tout branchement Power Automate ou Microsoft Graph devra être validé séparément.

## Données autorisées pendant le POC

- Documents fictifs du projet.
- Documents explicitement fournis pour test.
- Bibliothèque SharePoint de test validée par le superviseur ou l'équipe TI.
- Questions de démonstration ne contenant pas de données personnelles, médicales, financières ou confidentielles.

## Actions interdites pendant le POC

- Déploiement sur un domaine public sans validation.
- Tunnel externe exposant l'API locale sans autorisation.
- Connexion Microsoft Graph réelle sans cadrage.
- Power Automate modifiant des listes, envoyant des courriels ou créant des tickets réels.
- Indexation d'une bibliothèque documentaire complète sans filtrage.
- Utilisation d'OpenRouter avec de vrais documents.

## Critère de passage à l'étape suivante

Avant toute intégration réelle, obtenir :

- une URL HTTPS front validée ;
- une URL HTTPS API validée ;
- l'autorisation du domaine front dans HTML Field Security ;
- une bibliothèque documentaire de test ;
- une validation sécurité sur les vulnérabilités applicatives ;
- un accord écrit sur les automatisations autorisées ou interdites.
