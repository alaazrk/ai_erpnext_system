"""
HISTORIQUE — migration d'origine (Phase 8), conservée pour mémoire.
Plus nécessaire : le champ 'user' fait partie du DocType AI Message livré dans l'app.

Phase 8 - ERPNext AI Platform (erp_ai)
Ajoute le champ 'user' au DocType AI Message, nécessaire pour calculer les
quotas de messages par utilisateur et par jour.
UTILISATION :
    bench --site local.com execute erp_ai.update_ai_message_user.run
"""
import frappe


def run():
    doc = frappe.get_doc("DocType", "AI Message")
    existing = [f.fieldname for f in doc.fields]
    if "user" in existing:
        print("[SKIP] Le champ 'user' existe déjà sur AI Message.")
        return
    doc.append("fields", {
        "fieldname": "user",
        "fieldtype": "Link",
        "options": "User",
        "label": "User",
        "in_standard_filter": 1,
        "insert_after": "conversation",
    })
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("[OK] Champ 'user' ajouté à AI Message.")
