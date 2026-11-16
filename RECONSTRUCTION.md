# Notes de reconstruction (16/11/2026)

Le dépôt a été reconstruit à partir des fichiers récupérés et de l'historique
des conversations. Ce fichier dit d'où vient chaque morceau, pour savoir quoi
vérifier sur le serveur.

## Fichiers d'origine (récupérés tels quels)

`tools.py`, `agents.py`, `ollama_client.py`, `rag.py`, `scheduled_tasks.py`,
`dashboard.py`, `hooks.py`, `modules.txt`, `patches.txt`, `__init__.py`,
`page/ai_chat/*`, `page/ai_dashboard/*`, `doctype/ai_conversation/ai_conversation.json`.

## Corrections appliquées (validées dans l'historique, absentes des fichiers)

| Fichier | Changement |
|---|---|
| `tools.py` → `consult_agent` | Vérification `is_agent_allowed` : le Directeur ne peut plus consulter un agent interdit au rôle de l'utilisateur. |
| `doctype/ai_settings` | Champ `human_validation_required` et valeurs par défaut des quotas (200 / 20) repris des migrations récupérées. |
| `agents.py` | Suppression de `_get_consolidation_tools_for_user` (reste de l'Agent Consolidation abandonné, référençait une variable inexistante) ; docstring mise à jour. |
| `ollama_client.py` | Ponctuation du prompt système ; en-tête de docstring. |

## Fichiers RECONSTRUITS (à comparer avec le serveur si possible)

Ces définitions ont été déduites des champs utilisés dans le code ; les noms
de champs sont donc forcément bons, mais labels, nommage et options peuvent
différer de l'original :

- `doctype/ai_message/ai_message.json` (+ `.py`)
- `doctype/ai_log/ai_log.json` (+ `.py`)
- `doctype/ai_settings/ai_settings.json` (+ `.py`)
- `doctype/ai_document/ai_document.json` (repris du script `create_rag_doctypes.py`)
- `doctype/ai_document_chunk/ai_document_chunk.json` (idem)
- `doctype/ai_conversation/ai_conversation.py`
- `doctype/ai_document/ai_document.js` (était un Client Script créé dans l'UI)
- `pyproject.toml`, `README.md`, `license.txt`, `.gitignore`

Si le serveur `aisrv` tourne encore, les vrais JSON sont dans
`~/frappe-bench/apps/erp_ai/erp_ai/erp_ai/doctype/` : ils font foi.

## Fichiers de l'arborescence d'origine encore manquants

Aucun n'est nécessaire pour faire tourner l'app : les migrations sont remplacées
par les JSON des DocTypes et des pages, créés par `install-app` / `migrate`.

| Fichier | Rôle | Important ? |
|---|---|---|
| `seed_test_data.py`, `seed_stock_purchase.py` | Données de test CRM/Ventes et Stock/Achats | Utile pour les démos |
| `test_tools_phase4.py` | Tests des outils | Utile |
| `create_ai_dashboard_page.py` | Création de la page AI Dashboard | Non (remplacé par `ai_dashboard.json`) |
| `update_ai_log_count.py`, `update_ai_log_status.py` | Champs `count` et statuts d'AI Log | Non (déjà dans `ai_log.json`) |
| `update_ai_settings_alert_hour.py` | Champ `alert_hour` | Non (déjà dans `ai_settings.json`) |
| `setup.py` | Ancien packaging | Non (remplacé par `pyproject.toml`) |

Migrations récupérées et rangées dans `docs/historique/` : `create_rag_doctypes`,
`update_ai_settings_embedding`, `update_ai_message_user`,
`update_ai_settings_quotas`, `update_ai_settings_alerts`.

Le dossier de la page dashboard s'appelle `ai_dashboard` (avec underscore) :
c'est le nom que Frappe attend pour la page `ai-dashboard`, même si
l'arborescence d'origine montrait `ai-dashboard/`.

## Problèmes connus (non corrigés, pour garder le comportement d'origine)

1. **Permissions réservées au System Manager** sur AI Conversation, AI Message
   et AI Document. Conséquences pour un utilisateur non-admin :
   - `list_conversations` et `_get_history` passent par `frappe.get_all`
     (qui applique les droits) → historique vide, aucune mémoire de conversation ;
   - l'Agent Documents est ouvert à tous, mais `search_documents` renvoie
     « Permission refusée ».
   Correctif possible : donner `read` (avec « if owner » pour les conversations)
   aux rôles métier, ou lire ces tables avec `ignore_permissions`.
2. **`update_customer` et `update_supplier`** sont dans `WRITE_TOOLS` et ont un
   libellé dans le chat, mais aucun agent ne les expose depuis que le
   Directeur n'a plus que 2 outils. À ajouter respectivement aux listes des
   agents `commercial` et `achat`.
3. Si le **Client Script « Indexer »** existe encore sur le site, il fera
   doublon avec `ai_document.js` → le désactiver.
4. Le rapport annonce 14 fonctions d'écriture ; le code en compte 15
   (`receive_stock` inclus).
