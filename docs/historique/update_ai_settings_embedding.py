"""
HISTORIQUE — script d'origine de la Phase 10, conservé pour mémoire.
Il n'est PLUS nécessaire : le champ 'embedding_model' fait maintenant partie
du DocType "AI Settings" livré dans l'app.

Script original :
    bench --site local.com execute erp_ai.update_ai_settings_embedding.run
"""
import frappe


def run():
    doc = frappe.get_doc("DocType", "AI Settings")
    existing = [f.fieldname for f in doc.fields]
    if "embedding_model" in existing:
        print("[SKIP] Le champ 'embedding_model' existe déjà.")
        return
    doc.append("fields", {
        "fieldname": "embedding_model",
        "fieldtype": "Data",
        "label": "Modèle d'embedding (RAG)",
        "default": "nomic-embed-text",
        "description": "Modèle Ollama utilisé pour indexer/rechercher les documents. "
                        "Doit être téléchargé au préalable côté serveur : ollama pull nomic-embed-text",
    })
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("[OK] Champ 'embedding_model' ajouté à AI Settings.")
