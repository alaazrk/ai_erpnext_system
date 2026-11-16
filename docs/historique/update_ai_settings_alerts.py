"""
HISTORIQUE — migration d'origine (Phase 8), conservée pour mémoire.
Plus nécessaire : le champ fait partie du DocType AI Settings livré dans l'app.

Phase 8 - ERPNext AI Platform (erp_ai)
Ajoute le champ 'alert_recipients' au DocType AI Settings, pour configurer
qui reçoit les alertes automatiques (stock bas, factures en retard...).
UTILISATION :
    bench --site local.com execute erp_ai.update_ai_settings_alerts.run
"""
import frappe


def run():
    doc = frappe.get_doc("DocType", "AI Settings")
    existing = [f.fieldname for f in doc.fields]
    if "alert_recipients" in existing:
        print("[SKIP] Le champ 'alert_recipients' existe déjà.")
        return
    doc.append("fields", {
        "fieldname": "alert_recipients",
        "fieldtype": "Small Text",
        "label": "Destinataires des alertes (emails séparés par des virgules)",
        "description": "Laisse vide pour notifier automatiquement tous les System Manager.",
        "insert_after": "human_validation_required",
    })
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("[OK] Champ 'alert_recipients' ajouté à AI Settings.")
