"""
Phase 7 - ERPNext AI Platform (erp_ai)
Agents IA spécialisés par domaine (section 10 du rapport de projet).

EMPLACEMENT SUR LE SERVEUR :
    ~/frappe-bench/apps/erp_ai/erp_ai/agents.py

Chaque agent expose un sous-ensemble d'outils adapté à son domaine (issus
de tools.TOOLS_SCHEMA), avec une personnalité (persona) dédiée injectée
dans le prompt système par ollama_client.chat(). L'agent Directeur n'a que
2 outils (get_executive_snapshot + consult_agent) : il lit la vue exécutive
puis délègue aux agents spécialisés, ce qui garde son prompt léger (cause du
timeout Ollama quand il recevait les 33 outils). L'agent RH n'est volontairement
pas défini : aucun DocType RH actif sur le site (constat de la Phase 0).

Pour ajouter un agent : ajoute une entrée à AGENTS avec label, description,
persona, et la liste des noms d'outils (voir tools.TOOLS_REGISTRY pour la
liste complète des noms disponibles). "tools": None donne accès à tout.
"""

from erp_ai.tools import TOOLS_SCHEMA

import frappe

AGENTS = {
    "commercial": {
        "label": "Agent Commercial",
        "description": "CRM, devis, commandes, gestion des clients",
        "roles": ["Sales User", "Sales Manager", "System Manager"],
        "persona": (
            "Tu es l'Agent Commercial d'ERPNext AI Platform. Ton domaine : le CRM, "
            "les leads, les opportunités, les devis, les commandes clients et la "
            "gestion de la relation client. Reste concentré sur ces sujets ; pour "
            "toute question hors de ton domaine (stock, achats, finance détaillée), "
            "indique clairement à l'utilisateur qu'il devrait plutôt utiliser "
            "l'agent correspondant."
        ),
        "tools": [
            "search_customer", "search_lead", "search_opportunity", "get_customer_details",
            "search_quotation", "search_sales_order", "list_unpaid_invoices",
            "create_lead", "create_customer", "create_opportunity",
            "create_quotation", "create_sales_order", "get_sales_summary",
            "update_opportunity", "update_quotation", "update_sales_order",
        ],
    },
    "finance": {
        "label": "Agent Finance",
        "description": "Factures, paiements, rapports financiers",
        "roles": ["Accounts User", "Accounts Manager", "System Manager"],
        "persona": (
            "Tu es l'Agent Finance d'ERPNext AI Platform. Ton domaine : les "
            "factures clients et fournisseurs, les impayés, les échéances de "
            "paiement et les indicateurs financiers. Reste concentré sur ces "
            "sujets ; pour toute question hors de ton domaine (CRM, stock), "
            "indique clairement à l'utilisateur qu'il devrait plutôt utiliser "
            "l'agent correspondant."
        ),
        "tools": [
            "list_unpaid_invoices", "list_unpaid_purchase_bills",
            "search_sales_order", "search_purchase_order",
            "get_sales_summary", "get_purchase_summary",
        ],
    },
    "stock": {
        "label": "Agent Stock",
        "description": "Inventaire, mouvements, réapprovisionnement",
        "roles": ["Stock User", "Stock Manager", "System Manager"],
        "persona": (
            "Tu es l'Agent Stock d'ERPNext AI Platform. Ton domaine : les articles, "
            "les niveaux de stock par entrepôt, les mouvements de stock et le "
            "réapprovisionnement. Reste concentré sur ces sujets ; pour toute "
            "question hors de ton domaine (ventes, achats, finance), indique "
            "clairement à l'utilisateur qu'il devrait plutôt utiliser l'agent "
            "correspondant."
        ),
        "tools": [
            "search_item", "get_item_stock", "list_low_stock_items",
            "get_stock_ledger", "create_item", "receive_stock", "get_stock_summary","update_item"
        ],
    },
    "achat": {
        "label": "Agent Achat",
        "description": "Fournisseurs, commandes d'achat, propositions",
        "roles": ["Purchase User", "Purchase Manager", "System Manager"],
        "persona": (
            "Tu es l'Agent Achat d'ERPNext AI Platform. Ton domaine : les "
            "fournisseurs, les commandes d'achat et les factures fournisseurs. "
            "Reste concentré sur ces sujets ; pour toute question hors de ton "
            "domaine (ventes, CRM, stock détaillé), indique clairement à "
            "l'utilisateur qu'il devrait plutôt utiliser l'agent correspondant."
        ),
        "tools": [
            "search_supplier", "get_supplier_details", "search_purchase_order",
            "list_unpaid_purchase_bills", "create_supplier", "create_purchase_order",
            "get_purchase_summary",
        ],
    },

    "documents": {
        "label": "Agent Documents",
        "description": "Recherche dans les documents internes (procédures, contrats, catalogues)",
        "roles": [],
        "persona": (
            "Tu es l'Agent Documents d'ERPNext AI Platform. Ton unique domaine : "
            "répondre à partir des documents internes indexés (procédures, contrats, "
            "catalogues, notes internes). Utilise TOUJOURS search_documents pour "
            "répondre — ne réponds jamais de mémoire générale sur un sujet qui "
            "pourrait être couvert par un document interne. Si search_documents ne "
            "retourne rien de pertinent, dis-le clairement plutôt que d'inventer "
            "une réponse."
        ),
        "tools": ["search_documents"],
    },

    "directeur": {
        "label": "Agent Directeur",
        "description": "Vision transverse, indicateurs consolidés, aide à la décision",
        "roles": [
            "System Manager", "Sales Manager", "Purchase Manager",
            "Accounts Manager", "Stock Manager",
        ],
        "persona": (
            "Tu es l'Agent Directeur d'ERPNext AI Platform. Tu n'as PAS accès "
            "directement aux outils détaillés de chaque domaine. Ta méthode : "
            "1) appelle TOUJOURS get_executive_snapshot en premier pour avoir "
            "une vue d'ensemble (ventes, achats, stock, impayés) ; "
            "2) si la question nécessite un détail que le snapshot ne couvre "
            "pas (un client précis, un article, une commande...), utilise "
            "consult_agent pour déléguer cette question à l'agent spécialisé "
            "concerné (commercial, finance, stock, achat, documents) plutôt "
            "que de deviner. Synthétise ensuite en une réponse claire et "
            "orientée décision, sans jargon technique."
        ),
        "tools": ["get_executive_snapshot", "consult_agent"],
    },
}


def get_agent_tools_schema(agent_key, user=None):
    """Retourne le sous-ensemble de TOOLS_SCHEMA correspondant à l'agent."""
    agent = AGENTS.get(agent_key)
    if not agent or agent["tools"] is None:
        return TOOLS_SCHEMA
    allowed = set(agent["tools"])
    return [t for t in TOOLS_SCHEMA if t["function"]["name"] in allowed]

def get_agent_persona(agent_key):
    """Retourne la personnalité/consigne de domaine de l'agent."""
    agent = AGENTS.get(agent_key)
    return agent["persona"] if agent else AGENTS["directeur"]["persona"]


# ===========================================================================
# Contrôle d'accès par rôle (Phase 8 — Sécurité renforcée)
# ===========================================================================

def get_allowed_agents(user=None):
    """
    Retourne le sous-ensemble d'AGENTS accessible à l'utilisateur, selon ses
    rôles Frappe. Un agent sans liste de rôles définie est ouvert à tous.
    """
    user = user or frappe.session.user
    user_roles = set(frappe.get_roles(user))
    allowed = {}
    for key, agent in AGENTS.items():
        required_roles = set(agent.get("roles", []))
        if not required_roles or (user_roles & required_roles):
            allowed[key] = agent
    return allowed


def is_agent_allowed(agent_key, user=None):
    """Vérifie si l'utilisateur a le droit d'utiliser cet agent."""
    return agent_key in get_allowed_agents(user)