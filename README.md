# ERPNext AI Platform (`erp_ai`)

**Assistant intelligent local pour ERPNext.** Chaque collaborateur dialogue en
français avec les données réelles de l'entreprise (clients, ventes, stock,
achats, factures) et obtient des réponses immédiates, sans naviguer dans les
menus ni construire de filtres.

Le modèle d'IA tourne **entièrement en local** via [Ollama] : aucune donnée de
l'entreprise n'est envoyée à un service externe (OpenAI, Google ou autre).

> *« Quelles sont mes factures impayées ? »* · *« Quels articles sont en rupture ? »*
> · *« Fais-moi un bilan de l'activité cette semaine. »*

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Sécurité et gouvernance](#sécurité-et-gouvernance)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Structure du projet](#structure-du-projet)
- [Tests rapides](#tests-rapides)
- [Feuille de route](#feuille-de-route)

---

## Fonctionnalités

### 1. Chat IA avec agents spécialisés par métier

Une page de chat intégrée à ERPNext (`/app/ai-chat`). Plutôt qu'un assistant
générique, l'utilisateur choisit un **agent expert de son domaine**, limité aux
données qui le concernent et visible uniquement par les rôles correspondants.

| Agent | Domaine | Exemple de question |
|---|---|---|
| **Commercial** | Clients, prospects, opportunités, devis, commandes | « Où en est le devis de la Sarl Elkantara ? » |
| **Finance** | Factures, impayés, échéances de paiement | « Quelles factures sont en retard ce mois-ci ? » |
| **Stock** | Articles, niveaux de stock, réapprovisionnement | « Le fer à béton est-il en rupture ? » |
| **Achat** | Fournisseurs, commandes d'achat | « Quelles commandes sont en cours chez ce fournisseur ? » |
| **Documents** | Contrats, procédures, catalogues internes | « Que dit notre procédure de validation d'achat ? » |
| **Directeur** | Vision transverse, aide à la décision | « Fais-moi un bilan de l'activité cette semaine » |

### 2. Recherche en langage naturel dans les données réelles

L'agent interroge ERPNext en temps réel via le *tool calling* : clients,
fournisseurs, articles, devis, commandes, factures, fiches complètes avec
contacts, impayés triés par échéance, historique des mouvements de stock.
Aucune réponse inventée : si l'outil ne renvoie rien, l'assistant le dit.

### 3. Création et modification avec validation humaine obligatoire

L'assistant peut **proposer** de créer ou modifier un enregistrement (client,
fournisseur, lead, opportunité, article, devis, commande, entrée de stock…),
mais ne l'exécute **jamais automatiquement** :

- un formulaire pré-rempli s'affiche dans le chat, chaque champ est modifiable ;
- l'utilisateur **confirme** ou **annule** ;
- devis et commandes sont créés **en brouillon** : une revue dans ERPNext reste
  nécessaire avant tout envoi.

### 4. Recherche documentaire (RAG)

L'assistant répond aussi à partir de **documents internes** (PDF, DOCX, TXT, MD) :

1. l'utilisateur uploade un fichier dans *AI Document* ;
2. l'indexation démarre **automatiquement** en arrière-plan : extraction du
   texte (tableaux Word compris), découpage en fragments d'environ 250 mots avec
   chevauchement, calcul d'un embedding par fragment (`nomic-embed-text`) ;
3. à chaque question, les 5 fragments les plus proches **par le sens**
   (similarité cosinus) sont fournis au modèle.

Pas de base vectorielle externe : tout est stocké dans ERPNext, suffisant pour
quelques milliers de fragments. Un bouton **« Indexer »** permet de relancer
l'indexation manuellement.

### 5. Analyses et bilans chiffrés

Sur une demande comme « analyse mes ventes » ou « fais-moi un bilan »,
l'assistant calcule de **vraies statistiques** : chiffre d'affaires, top
clients et fournisseurs, impayés et dettes, état du stock, dans la devise
réelle de la société.

L'agent **Directeur** commence par une vue exécutive consolidée (ventes,
achats, stock, impayés sur 7 jours) en un seul appel, puis **délègue** si
besoin une question précise à l'agent spécialisé concerné.

### 6. Confort d'usage

- Réponses affichées **en streaming**, au fil de leur génération
- **Dictée vocale** (Chrome / Edge)
- **Historique** des conversations, rechargeable
- Réponses mises en forme en **Markdown** (listes, tableaux, gras)

### 7. Tableau de bord de supervision

Page `/app/ai-dashboard`, réservée aux System Manager :

- messages et utilisateurs actifs du jour, courbe sur 7 jours ;
- bannière de statut simple (« tout va bien » / « X problèmes détectés ») ;
- vue exécutive (CA, impayés, dépenses, dettes, articles sous seuil / à zéro) ;
- actions en attente de validation ;
- alertes envoyées dans la journée, cliquables ;
- usage des quotas par utilisateur.

### 8. Alertes automatiques

Chaque jour, à une **heure configurable**, le système vérifie :

- les articles passés sous leur seuil de réapprovisionnement ;
- les factures clients impayées et échues ;
- les factures fournisseurs impayées et échues.

Les personnes concernées sont notifiées **selon leur rôle** ERPNext, plus une
liste de destinataires manuelle optionnelle. Chaque notification est cliquable.

---

## Sécurité et gouvernance

| Principe | Mise en œuvre |
|---|---|
| **Aucune écriture automatique** | Toute création ou modification passe par une validation humaine explicite. |
| **Permissions ERPNext respectées** | Chaque outil vérifie les droits de l'utilisateur connecté. |
| **Agents restreints par rôle** | Un collaborateur ne voit que les agents de ses fonctions ; le Directeur ne peut pas consulter un agent interdit au rôle de l'utilisateur. |
| **Traçabilité complète** | Questions, outils appelés, actions proposées, validées ou refusées sont enregistrés avec l'identité de l'utilisateur (*AI Log*). |
| **Quotas configurables** | Nombre maximal de messages et d'actions d'écriture par utilisateur et par jour. |
| **Hébergement 100 % local** | Le modèle et les données ne quittent pas l'infrastructure. |

---

## Architecture

```
Navigateur (page AI Chat)
        │  frappe.call + WebSocket (streaming)
        ▼
ollama_client.chat()  ──►  Ollama (LLM local)
        │                       │ tool_calls
        ▼                       ▼
agents.py (persona + outils autorisés)   tools.py (36 outils, Frappe ORM)
        │                                      │
        │      écriture ? ──► AI Log « Pending Validation »
        │                      └► confirm_action / reject_action
        ▼
     ERPNext
```

L'agent Directeur ne reçoit que deux outils, ce qui garde son prompt léger :

```
Agent Directeur
   ├── get_executive_snapshot   vue 7 jours : ventes, achats, impayés, stock
   └── consult_agent ─────────► commercial | finance | stock | achat | documents
                                (lecture seule, droits du rôle respectés)
```

---

## Installation

**Prérequis :** Frappe / ERPNext v15, un serveur Ollama accessible, des workers
de fond actifs (queue `long`, pour l'indexation des documents).

```bash
cd ~/frappe-bench
bench get-app https://github.com/<ton-compte>/erp_ai.git
bench --site <site> install-app erp_ai
bench --site <site> migrate
bench build --app erp_ai
bench restart
```

Côté Ollama :

```bash
ollama pull qwen3              # modèle de chat
ollama pull nomic-embed-text   # modèle d'embedding pour le RAG
```

Dépendances Python installées automatiquement : `requests`, `pypdf`, `python-docx`.

---

## Configuration

Dans ERPNext, ouvre **AI Settings** :

| Champ | Rôle | Défaut |
|---|---|---|
| Ollama Server URL | Adresse du serveur Ollama | `http://localhost:11434` |
| Modèle de chat | Modèle utilisé pour répondre | `qwen3:latest` |
| Température | Créativité des réponses | `0.3` |
| Modèle d'embedding | Modèle utilisé pour le RAG | `nomic-embed-text` |
| Validation humaine obligatoire | Circuit de confirmation des écritures | activé |
| Destinataires des alertes | Emails en plus des rôles concernés | vide |
| Heure d'envoi des alertes | 0 à 23 | `6` |
| Quota de messages / jour | `0` = illimité | `200` |
| Quota d'actions d'écriture / jour | `0` = illimité | `20` |

---

## Utilisation

- **Chat :** `/app/ai-chat`, choisir un agent puis poser sa question.
- **Documents :** `/app/ai-document/new`, saisir un titre, joindre le fichier,
  enregistrer. Le statut passe de *Pending* à *Done* une fois l'indexation terminée.
- **Supervision :** `/app/ai-dashboard`.
- **Traçabilité :** `/app/ai-log`.

---

## Structure du projet

```
erp_ai/
├── pyproject.toml
├── erp_ai/
│   ├── hooks.py              doc_events (RAG) + scheduler (alertes)
│   ├── ollama_client.py      connexion Ollama, boucle tool calling, chat, quotas, streaming
│   ├── tools.py              registre des outils (lecture, écriture, synthèses, RAG)
│   ├── agents.py             agents par domaine + contrôle d'accès par rôle
│   ├── rag.py                extraction, découpage, embeddings, recherche
│   ├── dashboard.py          backend du tableau de bord
│   ├── scheduled_tasks.py    alertes automatiques
│   └── erp_ai/               module « ERP AI »
│       ├── doctype/
│       │   ├── ai_settings/        configuration
│       │   ├── ai_conversation/    historique des discussions
│       │   ├── ai_message/         messages utilisateur / assistant
│       │   ├── ai_log/             traçabilité et validations
│       │   ├── ai_document/        documents RAG
│       │   └── ai_document_chunk/  fragments indexés + embeddings
│       └── page/
│           ├── ai_chat/            interface de chat
│           └── ai_dashboard/       supervision
└── docs/historique/          scripts de migration d'origine (non nécessaires)
```

---

## Tests rapides

```bash
bench --site <site> execute erp_ai.ollama_client.ping
bench --site <site> execute erp_ai.ollama_client.chat --kwargs "{'message': 'bonjour'}"
bench --site <site> execute erp_ai.scheduled_tasks.run_daily_alerts
bench --site <site> execute erp_ai.rag.process_document --args "['TITRE_DU_DOC']"
```

---

## Feuille de route

| Étape | Contenu | Statut |
|---|---|---|
| **MVP** | Chat connecté aux données réelles, outils essentiels (CRM, ventes, stock, achats), validation humaine | Réalisé |
| **Produit** | RAG documentaire, analyses chiffrées, alertes, quotas, tableau de bord | Réalisé, en phase de test |
| **Plateforme** | Généralisation aux équipes, nouveaux domaines (RH si le module est activé) | À venir |

---

## Licence

MIT

[Ollama]: https://ollama.com