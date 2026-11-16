"""
HISTORIQUE — migration d'origine (Phase 8), conservée pour mémoire.
Plus nécessaire : les champs de quotas font partie du DocType AI Settings livré dans l'app.

Phase 8 - ERPNext AI Platform (erp_ai)
Ajoute les champs de quotas quotidiens au DocType AI Settings.
UTILISATION :
    bench --site local.com execute erp_ai.update_ai_settings_quotas.run
"""
import frappe


def run():
    doc = frappe.get_doc("DocType", "AI Settings")
    existing = [f.fieldname for f in doc.fields]
    changed = False
    if "max_messages_per_day" not in existing:
        doc.append("fields", {
            "fieldname": "max_messages_per_day",
            "fieldtype": "Int",
            "label": "Quota de messages par utilisateur / jour",
            "default": "200",
            "description": "0 = illimité.",
            "insert_after": "alert_recipients",
        })
        changed = True
    if "max_write_actions_per_day" not in existing:
        doc.append("fields", {
            "fieldname": "max_write_actions_per_day",
            "fieldtype": "Int",
            "label": "Quota d'actions d'écriture confirmées / jour",
            "default": "20",
            "description": "0 = illimité. Ne compte que les actions réellement exécutées (après validation).",
            "insert_after": "max_messages_per_day",
        })
        changed = True
    if changed:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        print("[OK] Champs de quotas ajoutés à AI Settings.")
    else:
        print("[SKIP] Les champs de quotas existent déjà.")
