# Grille d'évaluation RAG

Cette grille sert à évaluer manuellement les réponses du chatbot sur des documents fictifs ou anonymisés avant tout passage sur des documents sensibles.

| Question testée | Réponse attendue | Source attendue | Source obtenue | Score retrieval | Réponse correcte oui/non | Hallucination oui/non | Commentaire |
|---|---|---|---|---:|---|---|---|
| Comment demander un accès ? | Procédure de demande d'accès avec rôle et justification. | procedure_acces.txt |  |  |  |  |  |
| Comment réinitialiser un mot de passe ? | Procédure de réinitialisation via support ou procédure interne. | procedure_mot_de_passe.txt |  |  |  |  |  |
| Quelles sont les bonnes pratiques d’utilisation ? | Règles d'utilisation responsable des outils internes. | politique_utilisation.txt |  |  |  |  |  |
| Résume les principales procédures disponibles dans les documents. | Synthèse des documents fictifs disponibles. | Plusieurs sources fictives |  |  |  |  |  |
| Quelle est la politique de remboursement des billets d’avion ? | Refus exact car information absente. | Aucune source pertinente trouvée. |  |  |  |  |  |

## Rappel des critères

- **Question testée** : formulation envoyée au chatbot.
- **Réponse attendue** : comportement souhaité.
- **Source attendue** : document ou chunk qui devrait être utilisé.
- **Source obtenue** : source réellement affichée par l'API ou le front-end.
- **Score retrieval** : score retourné par le retriever si disponible.
- **Réponse correcte oui/non** : évaluation humaine.
- **Hallucination oui/non** : oui si la réponse ajoute une information non présente dans les sources.
- **Commentaire** : observation libre pour améliorer chunking, retrieval ou prompt.
