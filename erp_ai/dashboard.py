"""
Phase 9 - ERPNext AI Platform (erp_ai)
Backend du dashboard de supervision (AI Dashboard) : fournit les données
consommées par erp_ai/page/ai-dashboard/ai-dashboard.js.

EMPLACEMENT SUR LE SERVEUR :
    ~/frappe-bench/apps/erp_ai/erp_ai/dashboard.py

Réservé au rôle System Manager (vérifié ici ET par la Page AI Dashboard).
"""

import frappe
from frappe.utils import nowdate, add_days
from erp_ai.tools import get_executive_snapshot

def _check_access():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Accès réservé aux System Manager.", frappe.PermissionError)


@frappe.whitelist()
def get_dashboard_data():
    """Point d'entrée unique consommé par le dashboard (un seul appel réseau)."""
    try:
        _check_access()
    except frappe.PermissionError:
        return {"status": "error", "error": "Accès réservé aux System Manager."}

    today = nowdate()
    seven_days_ago = add_days(today, -6)  # 7 jours glissants, aujourd'hui inclus

    # --- KPIs ---------------------------------------------------------
    messages_today = frappe.db.count("AI Message", {"role": "user", "creation": [">=", today]})

    users_today_raw = frappe.get_all(
        "AI Message",
        filters={"role": "user", "creation": [">=", today]},
        pluck="user",
    )
    users_today = sorted({u for u in users_today_raw if u})
    active_users_today = len(users_today)

    pending_validations = frappe.get_all(
        "AI Log",
        filters={"status": "Pending Validation"},
        fields=["name", "tool_name", "user", "creation"],
        order_by="creation desc",
        limit=50,
    )

    # --- Messages des 7 derniers jours, groupés par jour ---------------
    messages_last_7_days = frappe.db.sql(
        """
        SELECT DATE(creation) AS day, COUNT(*) AS count
        FROM `tabAI Message`
        WHERE role = 'user' AND creation >= %(start)s
        GROUP BY DATE(creation)
        ORDER BY day ASC
        """,
        {"start": seven_days_ago},
        as_dict=True,
    )
    for row in messages_last_7_days:
        row["day"] = str(row["day"])

    # --- Alertes envoyées aujourd'hui (tool_name préfixé 'alert_') ------
    alerts_today = frappe.get_all(
        "AI Log",
        filters={"tool_name": ["like", "alert_%"], "creation": [">=", today]},
        fields=["name", "tool_name", "count", "creation"],
        order_by="creation desc",
    )

    # --- Erreurs sur 7 jours (bannière de statut simple) ----------------
    error_count_7d = frappe.db.count("AI Log", {
        "status": "Error",
        "creation": [">=", seven_days_ago],
    })

    # --- Usage des quotas aujourd'hui, par utilisateur actif ------------
    from erp_ai.tools import WRITE_TOOLS

    settings = frappe.get_single("AI Settings")
    message_limit = settings.get("max_messages_per_day") or 0
    write_limit = settings.get("max_write_actions_per_day") or 0

    quota_usage_today = []
    for user in users_today:
        message_count = frappe.db.count("AI Message", {
            "role": "user", "user": user, "creation": [">=", today],
        })
        write_count = frappe.db.count("AI Log", {
            "user": user,
            "status": "Success",
            "tool_name": ["in", list(WRITE_TOOLS)],
            "creation": [">=", today],
        })
        quota_usage_today.append({
            "user": user,
            "message_count": message_count,
            "message_limit": message_limit,
            "write_count": write_count,
            "write_limit": write_limit,
        })
    snapshot = get_executive_snapshot()
    return {
        "status": "ok",
        "messages_today": messages_today,
        "active_users_today": active_users_today,
        "pending_validations": pending_validations,
        "messages_last_7_days": messages_last_7_days,
        "alerts_today": alerts_today,
        "error_count_7d": error_count_7d,
        "quota_usage_today": quota_usage_today,
        "executive_snapshot": snapshot,
    }