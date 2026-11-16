"""
ERPNext AI Platform (erp_ai) - RAG documentaire.

Indexation de fichiers (PDF / DOCX / TXT / MD) et recherche par similarité
sémantique, pour que l'assistant réponde à partir de documents internes
(contrats, procédures, catalogues...) en plus des données structurées d'ERPNext.

Pipeline : fichier -> texte -> fragments (~250 mots) -> embeddings (Ollama)
-> stockage dans "AI Document Chunk" -> recherche par similarité cosinus.

Prérequis :
  - dépendances Python : pypdf, python-docx (déclarées dans pyproject.toml)
  - modèle d'embedding sur le serveur Ollama : ollama pull nomic-embed-text
  - workers de fond actifs (l'indexation automatique passe par la file "long")

Indexation manuelle (sans attendre) :
  bench --site votre-site execute erp_ai.rag.process_document --args "['TITRE_DU_DOC']"
"""

import json
import math

import frappe
import requests


CHUNK_SIZE_WORDS = 250
CHUNK_OVERLAP_WORDS = 40


def _get_settings():
    return frappe.get_single("AI Settings")


def _get_embedding_model():
    return _get_settings().get("embedding_model") or "nomic-embed-text"


# ---------------------------------------------------------------------------
# Extraction de texte
# ---------------------------------------------------------------------------

def _extract_text(file_path):
    """Extrait le texte brut d'un fichier PDF, DOCX, TXT ou MD."""
    lower = file_path.lower()

    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            frappe.throw("Le paquet 'pypdf' n'est pas installé (pip install pypdf).")
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if lower.endswith(".docx"):
        try:
            import docx
        except ImportError:
            frappe.throw("Le paquet 'python-docx' n'est pas installé (pip install python-docx).")
        d = docx.Document(file_path)

        parts = [p.text for p in d.paragraphs if p.text.strip()]

        # Les tableaux ne sont PAS inclus dans d.paragraphs : sans cette boucle,
        # tout contenu présenté en tableau serait invisible pour l'indexation.
        for table in d.tables:
            for row in table.rows:
                cells_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells_text:
                    parts.append(" | ".join(cells_text))

        return "\n".join(parts)

    if lower.endswith(".txt") or lower.endswith(".md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    frappe.throw(f"Format de fichier non supporté : '{file_path}'. Formats acceptés : PDF, DOCX, TXT, MD.")


def _get_file_path(doc):
    """Chemin disque du fichier attaché à un AI Document (public ou privé)."""
    file_name = frappe.db.get_value("File", {"file_url": doc.file}, "name")
    if not file_name:
        frappe.throw(f"Fichier introuvable dans ERPNext : {doc.file}")
    return frappe.get_doc("File", file_name).get_full_path()


# ---------------------------------------------------------------------------
# Découpage en fragments
# ---------------------------------------------------------------------------

def _chunk_text(text, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    """Découpe en fragments d'environ chunk_size mots, avec recouvrement."""
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap if end < len(words) else end
    return chunks


# ---------------------------------------------------------------------------
# Embeddings (via Ollama)
# ---------------------------------------------------------------------------

def _get_embedding(text):
    """Retourne le vecteur d'embedding d'un texte (liste de floats)."""
    settings = _get_settings()
    resp = requests.post(
        f"{settings.ollama_server_url}/api/embeddings",
        json={"model": _get_embedding_model(), "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("embedding")


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Indexation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def process_document(document_name):
    """
    Extrait le texte du fichier d'un AI Document, le découpe, génère un
    embedding par fragment et enregistre le tout dans AI Document Chunk.
    Les anciens fragments du document sont remplacés (ré-indexation).
    """
    if not frappe.has_permission("AI Document", "write"):
        return {"error": "Permission refusée."}

    doc = frappe.get_doc("AI Document", document_name)
    doc.status = "Processing"
    doc.error_message = None
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        text = _extract_text(_get_file_path(doc))
        if not text or not text.strip():
            raise Exception("Aucun texte extrait du fichier (fichier vide ou scanné sans OCR).")

        frappe.db.delete("AI Document Chunk", {"document": document_name})

        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            embedding = _get_embedding(chunk)
            frappe.get_doc({
                "doctype": "AI Document Chunk",
                "document": document_name,
                "chunk_index": i,
                "content": chunk,
                "embedding": json.dumps(embedding),
            }).insert(ignore_permissions=True)

        doc.status = "Done"
        doc.chunk_count = len(chunks)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "ok", "chunks_created": len(chunks)}

    except Exception as e:
        frappe.db.rollback()
        doc.reload()
        doc.status = "Error"
        doc.error_message = str(e)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(title=f"erp_ai RAG: échec indexation {document_name}", message=str(e))
        return {"error": str(e)}


def auto_index_on_save(doc, method=None):
    """
    Hook (doc_events > AI Document > after_insert) : indexe automatiquement
    le document en tâche de fond dès son enregistrement, pour que
    l'utilisateur n'ait rien d'autre à faire qu'uploader son fichier.
    """
    if doc.file and doc.status == "Pending":
        frappe.enqueue(
            "erp_ai.rag.process_document",
            queue="long",
            timeout=1800,
            enqueue_after_commit=True,
            document_name=doc.name,
        )


# ---------------------------------------------------------------------------
# Recherche par similarité
# ---------------------------------------------------------------------------

def search_documents(query, top_k=5):
    """
    Retourne les top_k fragments les plus proches de la requête, tous
    documents indexés confondus. Utilisé par l'outil search_documents (tools.py).
    """
    if not query:
        return {"error": "Le paramètre 'query' est requis."}

    query_embedding = _get_embedding(query)
    if not query_embedding:
        return {"error": "Impossible de générer l'embedding de la requête (serveur Ollama ou modèle d'embedding indisponible)."}

    chunks = frappe.get_all("AI Document Chunk", fields=["name", "document", "content", "embedding"])
    if not chunks:
        return {"results": [], "count": 0, "message": "Aucun document indexé pour l'instant."}

    scored = []
    for c in chunks:
        try:
            emb = json.loads(c["embedding"])
        except (TypeError, ValueError):
            continue
        scored.append({
            "document": c["document"],
            "content": c["content"],
            "score": round(_cosine_similarity(query_embedding, emb), 4),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:int(top_k)]
    return {"results": top, "count": len(top)}
