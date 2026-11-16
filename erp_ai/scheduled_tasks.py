"""
Phase 8 - ERPNext AI Platform (erp_ai)
Rapports automatiques & alertes planifiées (Automatisation & Monitoring).

EMPLACEMENT SUR LE SERVEUR :
    ~/frappe-bench/apps/erp_ai/erp_ai/scheduled_tasks.py

Destinataires des alertes (hybride) :
  - Automatique : tous les utilisateurs ayant un rôle pertinent pour le type
    d'alerte (ex : Stock User/Manager pour le stock bas), pour que la bonne
    personne soit prévenue sans configuration.
  - Manuel (en plus) : les emails renseignés dans AI Settings.alert_recipients,
    utile pour prévenir d'autres personnes (direction, etc.) au-delà des rôles.

MODIF (notifications cliquables) : le log AI Log est maintenant créé AVANT
l'envoi de la notification (au lieu d'après), pour pouvoir passer son
'document_name' à enqueue_create_notification(). Cliquer sur une
notification dans le clochon du Desk redirige désormais vers la fiche
AI Log de cette alerte, au lieu de ne mener nulle part.

TEST MANUEL (sans attendre le scheduler) :
    bench --site local.com execute erp_ai.scheduled_tasks.run_daily_alerts
"""

import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

from erp_ai.tools import list_low_stock_items, list_unpaid_invoices, list_unpaid_purchase_bills

# Rôles notifiés automatiquement, par type d'alerte
STOCK_ALERT_ROLES = ["Stock User", "Stock Manager", "System Manager"]
SALES_INVOICE_ALERT_ROLES = ["Sales User", "Sales Manager", "Accounts User", "Accounts Manager", "System Manager"]
PURCHASE_BILL_ALERT_ROLES = ["Purchase User", "Purchase Manager", "Accounts User", "Accounts Manager", "System Manager"]


def _get_role_recipients(roles):
    """Utilisateurs actifs ayant au moins un de ces rôles."""
    if not roles:
        return set()
    users = frappe.get_all(
        "Has Role",
        filters={"role": ["in", roles], "parenttype": "User"},
        pluck="parent",
    )
    return set(users) - {"Administrator", "Guest"}


def _get_manual_recipients():
    """Destinataires ajoutés manuellement dans AI Settings.alert_recipients."""
    settings = frappe.get_single("AI Settings")
    configured = getattr(settings, "alert_recipients", None)
    if not configured:
        return set()
    return {u.strip() for u in configured.split(",") if u.strip()}


def _get_recipients(roles):
    """
    Combine les destinataires automatiques (par rôle) et manuels (config).
    Repli sur les System Manager si personne n'est trouvé.
    """
    recipients = _get_role_recipients(roles) | _get_manual_recipients()
    if not recipients:
        recipients = _get_role_recipients(["System Manager"]) or {"Administrator"}
    return list(recipients)


def _log_alert(tool_name, details_text, count=None, status="Success"):
    """
    Enregistre le log de l'alerte et retourne son nom, pour pouvoir y lier
    la notification correspondante (voir _notify).

    'details_text' est un texte lisible en français (pas du JSON) : ce log
    est destiné à être consulté par un utilisateur non-technique qui clique
    depuis une notification, contrairement aux logs des autres outils
    (search_*, create_*...) qui restent en JSON pour un usage développeur.
    'count' est stocké dans un champ dédié, pour affichage direct sans
    parsing côté dashboard.
    """
    doc = frappe.get_doc({
        "doctype": "AI Log",
        "user": "Administrator",
        "tool_name": tool_name,
        "status": status,
        "details": details_text,
        "count": count,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _notify(users, subject, html, document_name=None):
    """
    Envoie une notification Desk (clochon). Si document_name est fourni,
    cliquer sur la notification redirige vers cette fiche AI Log — sinon
    (compatibilité) la notification n'est liée à aucun document précis.
    """
    if not users:
        return
    enqueue_create_notification(users, {
        "type": "Alert",
        "document_type": "AI Log",
        "document_name": document_name,
        "subject": subject,
        "email_content": html,
    })


def check_low_stock_alerts():
    """Alerte si des articles sont sous leur seuil de réapprovisionnement."""
    result = list_low_stock_items()
    items = result.get("results", [])
    if not items:
        print("[OK] Aucune alerte stock bas.")
        return

    lines_html = "".join(
        f"<li>{i['item_name']} ({i['item_code']}) — {i['actual_qty']} en stock "
        f"dans {i['warehouse']} (seuil : {i['niveau_reappro']})</li>"
        for i in items
    )
    html = f"<p>{len(items)} article(s) sous le seuil de réapprovisionnement :</p><ul>{lines_html}</ul>"

    lines_text = "\n".join(
        f"- {i['item_name']} ({i['item_code']}) : {i['actual_qty']} en stock dans "
        f"{i['warehouse']} (seuil configuré : {i['niveau_reappro']})"
        for i in items
    )
    details_text = f"{len(items)} article(s) sous le seuil de réapprovisionnement :\n\n{lines_text}"

    # Le log est créé D'ABORD, pour pouvoir lier la notification à sa fiche.
    log_name = _log_alert("alert_low_stock", details_text, count=len(items))

    recipients = _get_recipients(STOCK_ALERT_ROLES)
    _notify(recipients, f" {len(items)} article(s) en stock bas", html, document_name=log_name)
    print(f"[OK] Alerte stock bas envoyée à {recipients} ({len(items)} article(s)).")


def check_overdue_sales_invoices():
    """Alerte sur les factures clients impayées et déjà échues."""
    result = list_unpaid_invoices()
    today = frappe.utils.nowdate()
    overdue = [i for i in result.get("results", []) if i.get("due_date") and str(i["due_date"]) < today]
    if not overdue:
        print("[OK] Aucune facture client en retard.")
        return

    lines_html = "".join(
        f"<li>{i['customer']} — {i['name']} : {i['outstanding_amount']} restant dû "
        f"(échéance dépassée le {i['due_date']})</li>"
        for i in overdue
    )
    html = f"<p>{len(overdue)} facture(s) client en retard de paiement :</p><ul>{lines_html}</ul>"

    lines_text = "\n".join(
        f"- {i['customer']} — facture {i['name']} : {i['outstanding_amount']} restant dû "
        f"(échéance dépassée le {i['due_date']})"
        for i in overdue
    )
    details_text = f"{len(overdue)} facture(s) client en retard de paiement :\n\n{lines_text}"

    log_name = _log_alert("alert_overdue_sales_invoices", details_text, count=len(overdue))

    recipients = _get_recipients(SALES_INVOICE_ALERT_ROLES)
    _notify(recipients, f" {len(overdue)} facture(s) client en retard", html, document_name=log_name)
    print(f"[OK] Alerte factures clients en retard envoyée à {recipients} ({len(overdue)} facture(s)).")


def check_overdue_purchase_bills():
    """Alerte sur les factures fournisseurs impayées et déjà échues."""
    result = list_unpaid_purchase_bills()
    today = frappe.utils.nowdate()
    overdue = [i for i in result.get("results", []) if i.get("due_date") and str(i["due_date"]) < today]
    if not overdue:
        print("[OK] Aucune facture fournisseur en retard.")
        return

    lines_html = "".join(
        f"<li>{i['supplier']} — {i['name']} : {i['outstanding_amount']} restant dû "
        f"(échéance dépassée le {i['due_date']})</li>"
        for i in overdue
    )
    html = f"<p>{len(overdue)} facture(s) fournisseur en retard de paiement :</p><ul>{lines_html}</ul>"

    lines_text = "\n".join(
        f"- {i['supplier']} — facture {i['name']} : {i['outstanding_amount']} restant dû "
        f"(échéance dépassée le {i['due_date']})"
        for i in overdue
    )
    details_text = f"{len(overdue)} facture(s) fournisseur en retard de paiement :\n\n{lines_text}"

    log_name = _log_alert("alert_overdue_purchase_bills", details_text, count=len(overdue))

    recipients = _get_recipients(PURCHASE_BILL_ALERT_ROLES)
    _notify(recipients, f" {len(overdue)} facture(s) fournisseur en retard", html, document_name=log_name)
    print(f"[OK] Alerte factures fournisseurs en retard envoyée à {recipients} ({len(overdue)} facture(s)).")


def run_hourly_check():
    """
    Appelée toutes les heures par le scheduler. N'exécute les alertes que si
    l'heure actuelle correspond à AI Settings.alert_hour (choisie par l'utilisateur).
    """
    settings = frappe.get_single("AI Settings")
    target_hour = settings.get("alert_hour")
    if target_hour is None:
        target_hour = 6  # valeur par défaut si le champ n'est pas encore configuré

    current_hour = frappe.utils.now_datetime().hour
    if current_hour != int(target_hour):
        print(f"[SKIP] Heure actuelle ({current_hour}h) ≠ heure configurée ({target_hour}h). Pas d'alerte envoyée.")
        return

    run_daily_alerts()


def run_daily_alerts():
    """Point d'entrée appelé quotidiennement par le scheduler Frappe."""
    print("=== Vérification quotidienne des alertes erp_ai ===")
    check_low_stock_alerts()
    check_overdue_sales_invoices()
    check_overdue_purchase_bills()
    print("=== Terminé ===")