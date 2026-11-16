"""
HISTORIQUE — script d'origine de la Phase 10, conservé pour mémoire.
Il n'est PLUS nécessaire : les DocTypes "AI Document" et "AI Document Chunk"
sont maintenant livrés dans l'app (erp_ai/erp_ai/doctype/...) et sont créés
automatiquement par `bench --site <site> install-app erp_ai` ou `bench migrate`.

Script original :
    bench --site local.com execute erp_ai.create_rag_doctypes.run
"""
import frappe


def run():
    _create_ai_document()
    _create_ai_document_chunk()
    frappe.db.commit()
    print("[OK] DocTypes RAG créés (ou déjà existants).")


def _create_ai_document():
    if frappe.db.exists("DocType", "AI Document"):
        print("[SKIP] 'AI Document' existe déjà.")
        return
    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": "AI Document",
        "module": "erp ai",
        "custom": 0,
        "naming_rule": "By fieldname",
        "autoname": "field:title",
        "fields": [
            {"fieldname": "title", "fieldtype": "Data", "label": "Titre", "reqd": 1, "unique": 1},
            {"fieldname": "file", "fieldtype": "Attach", "label": "Fichier", "reqd": 1},
            {"fieldname": "status", "fieldtype": "Select", "label": "Statut",
             "options": "Pending\nProcessing\nDone\nError", "default": "Pending", "in_standard_filter": 1},
            {"fieldname": "chunk_count", "fieldtype": "Int", "label": "Nombre de fragments", "read_only": 1},
            {"fieldname": "error_message", "fieldtype": "Small Text", "label": "Message d'erreur", "read_only": 1},
            {"fieldname": "uploaded_by", "fieldtype": "Link", "options": "User", "label": "Ajouté par", "read_only": 1},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    print("[OK] DocType 'AI Document' créé.")


def _create_ai_document_chunk():
    if frappe.db.exists("DocType", "AI Document Chunk"):
        print("[SKIP] 'AI Document Chunk' existe déjà.")
        return
    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": "AI Document Chunk",
        "module": "erp ai",
        "custom": 0,
        "naming_rule": "Autoincrement",
        "fields": [
            {"fieldname": "document", "fieldtype": "Link", "options": "AI Document",
             "label": "Document source", "reqd": 1, "in_standard_filter": 1},
            {"fieldname": "chunk_index", "fieldtype": "Int", "label": "Index du fragment"},
            {"fieldname": "content", "fieldtype": "Text Editor", "label": "Contenu du fragment"},
            {"fieldname": "embedding", "fieldtype": "Long Text", "label": "Embedding (JSON)"},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    print("[OK] DocType 'AI Document Chunk' créé.")
