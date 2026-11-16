"""
Phase 2 + Phase 4 + Phase 6 - ERPNext AI Platform (erp_ai)
Module de connexion à Ollama, avec support du Tool Calling (Phase 4) et du
circuit de validation humaine pour les actions d'écriture (Phase 6).

EMPLACEMENT SUR LE SERVEUR :
    ~/frappe-bench/apps/erp_ai/erp_ai/ollama_client.py
"""

import json
import requests
import frappe

from erp_ai.tools import TOOLS_SCHEMA, execute_tool, WRITE_TOOLS
from erp_ai.agents import AGENTS, get_agent_tools_schema, get_agent_persona, get_allowed_agents, is_agent_allowed

MAX_TOOL_ITERATIONS = 6
FALLBACK_REPLY = "Je n'ai pas pu formuler de réponse finale à partir des résultats obtenus. Peux-tu reformuler ou préciser ta demande ?"


def get_settings():
    """Récupère la configuration AI Settings (Single DocType)."""
    settings = frappe.get_single("AI Settings")
    if not settings.ollama_server_url:
        frappe.throw("Ollama Server URL n'est pas configuré dans AI Settings.")
    return settings


@frappe.whitelist()
def ping():
    """Vérifie que le serveur Ollama répond."""
    settings = get_settings()
    try:
        resp = requests.get(f"{settings.ollama_server_url}/api/tags", timeout=5)
        resp.raise_for_status()
        return {"status": "ok", "message": "Ollama server is reachable."}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def list_models():
    """Liste les modèles disponibles sur le serveur Ollama."""
    settings = get_settings()
    try:
        resp = requests.get(f"{settings.ollama_server_url}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return {"status": "ok", "models": models}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}


def _call_ollama(settings, messages, use_tools=True, tools_schema=None):
    """Appel brut à /api/chat, avec ou sans outils (schéma spécifique à l'agent si fourni)."""
    payload = {
        "model": settings.default_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": settings.temperature or 0.3,
        },
    }
    if use_tools:
        payload["tools"] = tools_schema if tools_schema is not None else TOOLS_SCHEMA

    resp = requests.post(
        f"{settings.ollama_server_url}/api/chat",
        json=payload,
        timeout=240,
    )
    resp.raise_for_status()
    return resp.json()


def _stream_ollama(settings, messages, tools_schema, stream_id):
    """
    Appelle Ollama en streaming (NDJSON) et publie chaque fragment de texte
    en temps réel via Frappe realtime (WebSocket), si stream_id est fourni.
    Retourne le message complet accumulé (content + tool_calls éventuels),
    au même format que _call_ollama (non-streaming), pour rester compatible
    avec le reste de la boucle de tool calling.
    """
    payload = {
        "model": settings.default_model,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {"temperature": settings.temperature or 0.3},
    }
    if tools_schema is not None:
        payload["tools"] = tools_schema

    accumulated_content = ""
    tool_calls = None

    with requests.post(
        f"{settings.ollama_server_url}/api/chat",
        json=payload,
        stream=True,
        timeout=180,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message", {}) or {}
            delta = msg.get("content", "")
            if delta:
                accumulated_content += delta
                if stream_id:
                    frappe.publish_realtime(
                        f"erp_ai_stream_{stream_id}",
                        {"delta": delta},
                        user=frappe.session.user,
                    )
            if msg.get("tool_calls"):
                tool_calls = msg["tool_calls"]

            if chunk.get("done"):
                break

    return {"message": {"role": "assistant", "content": accumulated_content, "tool_calls": tool_calls}}


def _call_ollama_maybe_stream(settings, messages, tools_schema, stream_id, use_tools=True):
    """Bascule automatiquement en streaming si un stream_id est fourni par le frontend."""
    if stream_id:
        return _stream_ollama(settings, messages, tools_schema if use_tools else None, stream_id)
    return _call_ollama(settings, messages, use_tools=use_tools, tools_schema=tools_schema)


def _log_tool_call(conversation, tool_name, arguments, result, status):
    """Enregistre l'appel d'outil dans AI Log pour traçabilité."""
    doc = frappe.get_doc({
        "doctype": "AI Log",
        "conversation": conversation,
        "user": frappe.session.user,
        "tool_name": tool_name,
        "status": status,
        "details": json.dumps({"arguments": arguments, "result": result}, default=str, ensure_ascii=False),
    })
    doc.insert(ignore_permissions=True)


def _log_message(conversation, role, content):
    """Enregistre un message dans AI Message, lié à une AI Conversation.
    Le champ 'content' est obligatoire côté DocType : on ne l'enregistre
    jamais vide pour éviter de faire planter toute la requête chat().
    """
    if not content or not str(content).strip():
        content = FALLBACK_REPLY
    doc = frappe.get_doc({
        "doctype": "AI Message",
        "conversation": conversation,
        "role": role,
        "content": content,
        "user": frappe.session.user,
    })
    doc.insert(ignore_permissions=True)


def _count_today(doctype, filters):
    """Compte les enregistrements d'un DocType créés aujourd'hui, filtres additionnels inclus."""
    filters = dict(filters)
    filters["creation"] = [">=", frappe.utils.nowdate()]
    return frappe.db.count(doctype, filters)


def _check_message_quota(user):
    """Vérifie le quota quotidien de messages (AI Settings.max_messages_per_day). None = OK."""
    settings = get_settings()
    limit = settings.get("max_messages_per_day") or 0
    if not limit:
        return None
    count = _count_today("AI Message", {"user": user, "role": "user"})
    if count >= limit:
        return f"Quota quotidien de {limit} messages atteint. Réessaie demain."
    return None


def _check_write_quota(user):
    """Vérifie le quota quotidien d'actions d'écriture confirmées. None = OK."""
    settings = get_settings()
    limit = settings.get("max_write_actions_per_day") or 0
    if not limit:
        return None
    count = _count_today("AI Log", {"user": user, "status": "Success", "tool_name": ["in", list(WRITE_TOOLS)]})
    if count >= limit:
        return f"Quota quotidien de {limit} actions d'écriture atteint. Réessaie demain."
    return None


def _get_history(conversation, limit=20):
    """
    Récupère les derniers échanges (user/assistant) d'une conversation, pour
    les réinjecter dans le contexte envoyé au modèle. Sans ça, chaque message
    est traité isolément et le modèle n'a aucune mémoire de la conversation.
    Limité aux N derniers messages pour ne pas faire exploser le contexte.
    """
    if not conversation:
        return []
    messages = frappe.get_all(
        "AI Message",
        filters={"conversation": conversation, "role": ["in", ["user", "assistant"]]},
        fields=["role", "content"],
        order_by="creation asc",
        limit=limit,
    )
    return [{"role": m["role"], "content": m["content"]} for m in messages]


@frappe.whitelist()
def chat(message, model=None, conversation=None, agent=None, stream_id=None):
    """
    Envoie un message au modèle. Si le modèle décide d'utiliser un outil
    (Tool Calling), on l'exécute et on renvoie le résultat au modèle pour
    qu'il formule sa réponse finale.

    Le paramètre 'agent' (commercial/finance/stock/achat/directeur) restreint
    les outils disponibles au sous-ensemble du domaine et ajoute une persona
    dédiée au prompt système. Par défaut : agent Directeur (accès complet).
    """
    settings = get_settings()

    agent_key = agent if agent in AGENTS else "directeur"

    if not is_agent_allowed(agent_key):
        return {
            "status": "error",
            "message": f"Tu n'as pas la permission d'utiliser l'agent « {AGENTS[agent_key]['label']} ». "
                       "Contacte un administrateur si tu penses que c'est une erreur.",
        }

    quota_error = _check_message_quota(frappe.session.user)
    if quota_error:
        return {"status": "error", "message": quota_error}

    agent_tools_schema = get_agent_tools_schema(agent_key, user=frappe.session.user)
    agent_persona = get_agent_persona(agent_key)

    messages = [
        {
            "role": "system",
            "content": (
                f"{agent_persona} "
                "Utilise les outils disponibles quand c'est pertinent pour "
                "répondre avec des données réelles. "
                "Si la demande nécessite plusieurs informations (ex: devis, commandes "
                "et factures d'un même client), appelle tous les outils nécessaires "
                "AVANT de rédiger ta réponse finale. Pour toute création de donnée "
                "(lead, fournisseur, client...), utilise EXACTEMENT l'outil "
                "correspondant au type d'objet demandé — ne substitue jamais un "
                "outil de création par un autre, même s'il te semble proche. Si "
                "aucun outil ne correspond exactement à la demande, dis-le "
                "explicitement plutôt que d'utiliser un outil approximatif. "
                "Quand tu proposes une création, remplis TOUJOURS tous les "
                "paramètres optionnels disponibles dans le schéma de l'outil "
                "(même par une chaîne vide si l'information manque) pour que "
                "l'utilisateur reçoive directement une fiche complète à corriger "
                "— ne lui demande jamais s'il veut voir la fiche, propose-la "
                "d'emblée dès que la création est demandée. "
                "N'INVENTE JAMAIS la valeur d'un paramètre obligatoire qui n'a "
                "pas été fourni par l'utilisateur (dates, quantités, montants, "
                "prix...). Si une information nécessaire manque, pose une "
                "question de clarification avant d'appeler l'outil plutôt que "
                "de deviner une valeur. "
                "RÈGLE CRITIQUE pour les questions d'analyse, de stratégie, de "
                "conseil, de bilan ou de consolidation (ex : \"conseille-moi sur "
                "mes achats\", \"analyse mes ventes\", \"consolidation de mon "
                "activité\") : tu DOIS TOUJOURS appeler les outils pertinents "
                "(get_sales_summary, get_purchase_summary, get_stock_summary, "
                "list_unpaid_invoices, list_unpaid_purchase_bills, etc.) pour "
                "récupérer les VRAIES données AVANT de répondre. Il est INTERDIT "
                "de demander à l'utilisateur de te fournir des chiffres ou des "
                "noms que tu peux toi-même obtenir avec tes outils — l'utilisateur "
                "attend une analyse construite sur des données réelles, pas des "
                "conseils génériques ni une liste de questions. Si un outil "
                "renvoie un résultat vide ou à zéro, dis-le explicitement (ex : "
                "\"aucune vente enregistrée sur cette période\") plutôt que de "
                "demander la donnée. Ne pose une question à l'utilisateur que "
                "si aucun outil ne peut raisonnablement fournir l'information "
                "(ex : ses objectifs business, son budget cible). "
                "Tu peux utiliser le format Markdown "
                "(listes, gras, tableaux) dans tes réponses quand cela aide à "
                "la lisibilité. Réponds toujours en français, de façon concise. "
                "Quand un outil retourne un champ 'currency', UTILISE EXACTEMENT ce code "
                "pour exprimer les montants (ex: DZD) — n'invente JAMAIS une devise "
                "(FCFA, €, $...) si elle n'a pas été explicitement fournie par l'outil."
            ),
        },
    ]
    messages.extend(_get_history(conversation))
    messages.append({"role": "user", "content": message})

    tools_used = []

    try:
        data = _call_ollama_maybe_stream(settings, messages, agent_tools_schema, stream_id, use_tools=True)
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}

    iterations = 0
    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            break

        messages.append(assistant_msg)

        for call in tool_calls:
            fn = call.get("function", {})
            tool_name = fn.get("name")
            arguments = fn.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            if tool_name in WRITE_TOOLS:
                log = frappe.get_doc({
                    "doctype": "AI Log",
                    "conversation": conversation,
                    "user": frappe.session.user,
                    "tool_name": tool_name,
                    "status": "Pending Validation",
                    "details": json.dumps({"arguments": arguments}, default=str, ensure_ascii=False),
                })
                log.insert(ignore_permissions=True)
                frappe.db.commit()

                result = {
                    "status": "pending_validation",
                    "validation_id": log.name,
                    "message": (
                        f"Action '{tool_name}' proposée avec les paramètres {arguments}. "
                        f"En attente de validation humaine (ID: {log.name}). "
                        "Informe l'utilisateur qu'il doit confirmer cette action."
                    ),
                }
                tools_used.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "pending": True,
                    "validation_id": log.name,
                })
            else:
                result = execute_tool(tool_name, arguments)
                status = "Error" if isinstance(result, dict) and result.get("error") else "Success"

                tools_used.append({"tool": tool_name, "arguments": arguments, "result": result})
                _log_tool_call(conversation, tool_name, arguments, result, status)

            messages.append({
                "role": "tool",
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

        try:
            data = _call_ollama_maybe_stream(settings, messages, agent_tools_schema, stream_id, use_tools=True)
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": str(e)}
    else:
        assistant_msg = data.get("message", {})
        if assistant_msg.get("tool_calls"):
            messages.append({
                "role": "user",
                "content": "Réponds maintenant en texte, à partir des résultats déjà obtenus, sans appeler d'autre outil.",
            })
            try:
                data = _call_ollama_maybe_stream(settings, messages, None, stream_id, use_tools=False)
            except requests.exceptions.RequestException as e:
                return {"status": "error", "message": str(e)}

    reply = data.get("message", {}).get("content", "") or FALLBACK_REPLY

    if conversation:
        _log_message(conversation, "user", message)
        if tools_used:
            _log_message(conversation, "tool", json.dumps(tools_used, default=str, ensure_ascii=False))
        _log_message(conversation, "assistant", reply)
        frappe.db.commit()

    return {"status": "ok", "reply": reply, "tools_used": tools_used}

def run_agent_query(agent_key, question, user=None):
    """
    Exécute une question sur un agent spécialisé, en interne (pas d'historique
    de conversation, pas de streaming) — utilisé par l'outil consult_agent.
    Les actions d'écriture proposées par l'agent consulté ne sont PAS
    auto-exécutées.
    """
    settings = get_settings()
    user = user or frappe.session.user

    agent_tools_schema = get_agent_tools_schema(agent_key, user=user)
    agent_persona = get_agent_persona(agent_key)

    messages = [
        {"role": "system", "content": agent_persona + " Réponds de façon concise, en français."},
        {"role": "user", "content": question},
    ]

    try:
        data = _call_ollama(settings, messages, use_tools=True, tools_schema=agent_tools_schema)
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

    iterations = 0
    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        assistant_msg = data.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            break

        messages.append(assistant_msg)

        for call in tool_calls:
            fn = call.get("function", {})
            tool_name = fn.get("name")
            arguments = fn.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            if tool_name in WRITE_TOOLS:
                result = {
                    "status": "info",
                    "message": f"L'action '{tool_name}' ne peut pas être proposée depuis une "
                                "consultation inter-agents. Demande-la directement dans le chat "
                                "de l'agent concerné pour la valider.",
                }
            else:
                result = execute_tool(tool_name, arguments)
                status = "Error" if isinstance(result, dict) and result.get("error") else "Success"
                _log_tool_call(None, tool_name, arguments, result, status)

            messages.append({
                "role": "tool",
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

        try:
            data = _call_ollama(settings, messages, use_tools=True, tools_schema=agent_tools_schema)
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    reply = data.get("message", {}).get("content", "") or FALLBACK_REPLY
    return {"agent": agent_key, "reply": reply}

@frappe.whitelist()
def list_agents():
    """Liste les agents accessibles à l'utilisateur courant (filtrés par rôle)."""
    allowed = get_allowed_agents()
    return {
        "status": "ok",
        "agents": [
            {"key": k, "label": v["label"], "description": v["description"]}
            for k, v in allowed.items()
        ],
    }




@frappe.whitelist()
def confirm_action(validation_id, arguments=None):
    """Exécute réellement une action d'écriture en attente, après validation."""
    log = frappe.get_doc("AI Log", validation_id)
    if log.status != "Pending Validation":
        return {"status": "error", "message": f"Cette action n'est plus en attente (statut actuel : {log.status})."}

    quota_error = _check_write_quota(frappe.session.user)
    if quota_error:
        return {"status": "error", "message": quota_error}

    if arguments:
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Paramètres invalides (JSON incorrect)."}
    else:
        arguments = json.loads(log.details or "{}").get("arguments", {})

    result = execute_tool(log.tool_name, arguments)
    is_error = isinstance(result, dict) and result.get("error")

    log.status = "Error" if is_error else "Success"
    log.details = json.dumps({"arguments": arguments, "result": result}, default=str, ensure_ascii=False)
    log.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "error" if is_error else "ok", "result": result}


@frappe.whitelist()
def reject_action(validation_id):
    """Annule une action d'écriture en attente, sans l'exécuter."""
    log = frappe.get_doc("AI Log", validation_id)
    if log.status != "Pending Validation":
        return {"status": "error", "message": f"Cette action n'est plus en attente (statut actuel : {log.status})."}

    log.status = "Rejected"
    log.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok", "message": "Action annulée."}


@frappe.whitelist()
def create_conversation(title=None):
    """Crée une nouvelle AI Conversation pour l'utilisateur courant."""
    doc = frappe.get_doc({
        "doctype": "AI Conversation",
        "user": frappe.session.user,
        "title": title or "Nouvelle conversation",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok", "conversation": doc.name}


@frappe.whitelist()
def list_conversations():
    """
    Liste les conversations de l'utilisateur courant, les plus récentes
    d'abord. Utilisé pour afficher l'historique dans le chat.
    """
    conversations = frappe.get_all(
        "AI Conversation",
        filters={"user": frappe.session.user},
        fields=["name", "title", "started_on", "status"],
        order_by="started_on desc",
        limit=50,
    )
    return {"status": "ok", "conversations": conversations}


@frappe.whitelist()
def get_conversation_messages(conversation):
    """
    Récupère les messages user/assistant (pas les messages techniques 'tool')
    d'une conversation, pour ré-afficher son historique dans le chat.
    """
    if not frappe.db.exists("AI Conversation", conversation):
        return {"status": "error", "message": "Conversation introuvable."}

    conv = frappe.get_doc("AI Conversation", conversation)
    if conv.user != frappe.session.user and "System Manager" not in frappe.get_roles():
        return {"status": "error", "message": "Accès refusé à cette conversation."}

    messages = frappe.get_all(
        "AI Message",
        filters={"conversation": conversation, "role": ["in", ["user", "assistant"]]},
        fields=["role", "content", "creation"],
        order_by="creation asc",
    )
    return {"status": "ok", "messages": messages, "title": conv.title}