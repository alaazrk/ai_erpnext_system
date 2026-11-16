"""
Phase 4 + Phase 6 + Phase 8 - ERPNext AI Platform (erp_ai)
Registre des outils (Tools) que le LLM peut appeler.

EMPLACEMENT SUR LE SERVEUR :
    ~/frappe-bench/apps/erp_ai/erp_ai/tools.py

Pour ajouter un nouvel outil plus tard :
  1. Écrire la fonction Python (avec vérification de permissions).
  2. L'ajouter à TOOLS_REGISTRY.
  3. Décrire son schéma JSON dans TOOLS_SCHEMA (format attendu par Ollama).
  4. Si c'est une action d'écriture (create/update/delete), ajouter son nom
     à WRITE_TOOLS pour forcer le circuit de validation humaine.

NOTE PÉRIMÈTRE : le module RH n'est volontairement pas couvert ici — Phase 0
a constaté qu'aucun DocType RH n'est actif sur le site (agent RH écarté du
MVP). À réintégrer plus tard si le module est activé.
"""

import re

import frappe


def _find_item_by_fuzzy_name(code):
    """
    Si un item_code n'existe pas tel quel, tente de retrouver l'article
    correspondant par son item_name (le modèle invente parfois un code
    plausible plutôt que d'utiliser le vrai code existant).
    """
    tokens = [t.lower() for t in re.split(r"[_\-\s]+", code) if t]
    if not tokens:
        return []
    candidates = frappe.get_all("Item", fields=["item_code", "item_name"], limit=200)
    return [c for c in candidates if all(tok in c["item_name"].lower() for tok in tokens)]


# ===========================================================================
# CRM / VENTES
# ===========================================================================

def search_customer(query=None):
    """Recherche des clients par nom. Sans 'query', retourne les 10 clients les plus récents. Lecture seule."""
    if not frappe.has_permission("Customer", "read"):
        return {"error": "Permission refusée pour lire les clients."}

    filters = [["customer_name", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Customer",
        filters=filters,
        fields=["name", "customer_name", "customer_group", "territory", "mobile_no"],
        order_by="creation desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def search_lead(query=None):
    """Recherche des leads par nom ou nom d'entreprise. Sans 'query', retourne les 10 leads les plus récents. Lecture seule."""
    if not frappe.has_permission("Lead", "read"):
        return {"error": "Permission refusée pour lire les leads."}

    if query:
        results = frappe.get_all(
            "Lead",
            or_filters=[
                ["Lead", "lead_name", "like", f"%{query}%"],
                ["Lead", "company_name", "like", f"%{query}%"],
            ],
            fields=["name", "lead_name", "company_name", "status", "email_id", "mobile_no"],
            limit=5,
        )
    else:
        results = frappe.get_all(
            "Lead",
            fields=["name", "lead_name", "company_name", "status", "email_id", "mobile_no"],
            order_by="creation desc",
            limit=10,
        )
    return {"results": results, "count": len(results)}


def search_opportunity(query=None):
    """Recherche des opportunités par nom de client/party. Sans 'query', retourne les 10 plus récentes. Lecture seule."""
    if not frappe.has_permission("Opportunity", "read"):
        return {"error": "Permission refusée pour lire les opportunités."}

    filters = [["party_name", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Opportunity",
        filters=filters,
        fields=["name", "party_name", "status", "opportunity_amount", "sales_stage", "transaction_date"],
        order_by="transaction_date desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def get_customer_details(customer_name):
    """Récupère la fiche complète d'un client, avec ses contacts associés. Lecture seule."""
    if not frappe.has_permission("Customer", "read"):
        return {"error": "Permission refusée pour lire les clients."}

    if not customer_name:
        return {"error": "Le paramètre 'customer_name' est requis."}

    if not frappe.db.exists("Customer", customer_name):
        match = frappe.get_all(
            "Customer",
            filters=[["customer_name", "like", f"%{customer_name}%"]],
            fields=["name"],
            limit=1,
        )
        if not match:
            return {"error": f"Aucun client trouvé pour '{customer_name}'."}
        customer_name = match[0]["name"]

    customer = frappe.get_doc("Customer", customer_name)
    contacts = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Customer",
            "link_name": customer_name,
            "parenttype": "Contact",
        },
        fields=["parent"],
    )
    contact_details = []
    for c in contacts:
        contact_doc = frappe.get_doc("Contact", c["parent"])
        contact_details.append({
            "name": contact_doc.name,
            "email": contact_doc.email_id,
            "phone": contact_doc.mobile_no or contact_doc.phone,
        })

    return {
        "customer_name": customer.customer_name,
        "customer_group": customer.customer_group,
        "territory": customer.territory,
        "customer_type": customer.customer_type,
        "contacts": contact_details,
    }


def search_quotation(query=None):
    """Recherche des devis par nom de client. Sans 'query', retourne les 10 plus récents. Lecture seule."""
    if not frappe.has_permission("Quotation", "read"):
        return {"error": "Permission refusée pour lire les devis."}

    filters = [["party_name", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Quotation",
        filters=filters,
        fields=["name", "party_name", "status", "grand_total", "transaction_date", "valid_till"],
        order_by="transaction_date desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def search_sales_order(query=None):
    """Recherche des commandes clients par nom de client. Sans 'query', retourne les 10 plus récentes. Lecture seule."""
    if not frappe.has_permission("Sales Order", "read"):
        return {"error": "Permission refusée pour lire les commandes clients."}

    filters = [["customer", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "status", "grand_total", "delivery_date", "per_delivered", "per_billed"],
        order_by="transaction_date desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def list_unpaid_invoices(customer_name=None):
    """
    Liste les factures clients avec un solde restant dû (outstanding_amount > 0).
    Si customer_name est fourni, filtre sur ce client. Sinon, retourne les 10
    factures impayées les plus récentes tous clients confondus. Lecture seule.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        return {"error": "Permission refusée pour lire les factures."}

    filters = [["outstanding_amount", ">", 0], ["docstatus", "=", 1]]
    if customer_name:
        filters.append(["customer", "like", f"%{customer_name}%"])

    results = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["name", "customer", "grand_total", "outstanding_amount", "due_date", "status"],
        order_by="due_date asc",
        limit=10,
    )
    return {"results": results, "count": len(results)}


# ===========================================================================
# STOCK
# ===========================================================================

def search_item(query=None):
    """Recherche des articles par code ou nom. Sans 'query', retourne les 10 plus récents. Lecture seule."""
    if not frappe.has_permission("Item", "read"):
        return {"error": "Permission refusée pour lire les articles."}

    if query:
        results = frappe.get_all(
            "Item",
            or_filters=[
                ["item_code", "like", f"%{query}%"],
                ["item_name", "like", f"%{query}%"],
            ],
            fields=["item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "disabled"],
            limit=5,
        )
    else:
        results = frappe.get_all(
            "Item",
            fields=["item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "disabled"],
            order_by="creation desc",
            limit=10,
        )
    return {"results": results, "count": len(results)}


def get_item_stock(item_code):
    """Récupère le stock actuel d'un article, détaillé par entrepôt. Lecture seule."""
    if not frappe.has_permission("Bin", "read"):
        return {"error": "Permission refusée pour lire le stock."}

    if not item_code:
        return {"error": "Le paramètre 'item_code' est requis."}

    if not frappe.db.exists("Item", item_code):
        match = frappe.get_all(
            "Item",
            filters=[["item_name", "like", f"%{item_code}%"]],
            fields=["name"],
            limit=1,
        )
        if not match:
            return {"error": f"Aucun article trouvé pour '{item_code}'."}
        item_code = match[0]["name"]

    results = frappe.get_all(
        "Bin",
        filters={"item_code": item_code},
        fields=["warehouse", "actual_qty", "reserved_qty", "projected_qty"],
    )
    total_actual_qty = sum(r["actual_qty"] for r in results)

    return {
        "item_code": item_code,
        "total_actual_qty": total_actual_qty,
        "par_entrepot": results,
    }


def list_low_stock_items(warehouse=None):
    """
    Liste les articles dont le stock actuel est sous le niveau de
    réapprovisionnement défini (table Item Reorder). Si warehouse est fourni,
    filtre sur cet entrepôt. Lecture seule.
    """
    if not frappe.has_permission("Item", "read") or not frappe.has_permission("Bin", "read"):
        return {"error": "Permission refusée pour lire les articles ou le stock."}

    conditions = ""
    values = {"limit": 10}
    if warehouse:
        conditions = "AND bin.warehouse = %(warehouse)s"
        values["warehouse"] = warehouse

    query = f"""
        SELECT
            ir.parent AS item_code,
            i.item_name,
            bin.warehouse,
            bin.actual_qty,
            ir.warehouse_reorder_level AS niveau_reappro
        FROM `tabItem Reorder` ir
        JOIN `tabItem` i ON i.name = ir.parent
        JOIN `tabBin` bin ON bin.item_code = ir.parent AND bin.warehouse = ir.warehouse
        WHERE bin.actual_qty < ir.warehouse_reorder_level
        {conditions}
        LIMIT %(limit)s
    """
    results = frappe.db.sql(query, values, as_dict=True)
    return {"results": results, "count": len(results)}


def get_stock_ledger(item_code, warehouse=None):
    """Récupère les 5 derniers mouvements de stock d'un article. Lecture seule."""
    if not frappe.has_permission("Stock Ledger Entry", "read"):
        return {"error": "Permission refusée pour lire les mouvements de stock."}

    if not item_code:
        return {"error": "Le paramètre 'item_code' est requis."}

    filters = [["item_code", "=", item_code]]
    if warehouse:
        filters.append(["warehouse", "=", warehouse])

    results = frappe.get_all(
        "Stock Ledger Entry",
        filters=filters,
        fields=["posting_date", "warehouse", "actual_qty", "qty_after_transaction", "voucher_type", "voucher_no"],
        order_by="posting_date desc, posting_time desc",
        limit=5,
    )
    return {"results": results, "count": len(results)}


# ===========================================================================
# ACHATS / BUYING
# ===========================================================================

def search_supplier(query=None):
    """Recherche des fournisseurs par nom. Sans 'query', retourne les 10 plus récents. Lecture seule."""
    if not frappe.has_permission("Supplier", "read"):
        return {"error": "Permission refusée pour lire les fournisseurs."}

    filters = [["supplier_name", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Supplier",
        filters=filters,
        fields=["name", "supplier_name", "supplier_group", "supplier_type", "country", "mobile_no"],
        order_by="creation desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def get_supplier_details(supplier_name):
    """Récupère la fiche complète d'un fournisseur, avec ses contacts associés. Lecture seule."""
    if not frappe.has_permission("Supplier", "read"):
        return {"error": "Permission refusée pour lire les fournisseurs."}

    if not supplier_name:
        return {"error": "Le paramètre 'supplier_name' est requis."}

    if not frappe.db.exists("Supplier", supplier_name):
        match = frappe.get_all(
            "Supplier",
            filters=[["supplier_name", "like", f"%{supplier_name}%"]],
            fields=["name"],
            limit=1,
        )
        if not match:
            return {"error": f"Aucun fournisseur trouvé pour '{supplier_name}'."}
        supplier_name = match[0]["name"]

    supplier = frappe.get_doc("Supplier", supplier_name)
    contacts = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Supplier",
            "link_name": supplier_name,
            "parenttype": "Contact",
        },
        fields=["parent"],
    )
    contact_details = []
    for c in contacts:
        contact_doc = frappe.get_doc("Contact", c["parent"])
        contact_details.append({
            "name": contact_doc.name,
            "email": contact_doc.email_id,
            "phone": contact_doc.mobile_no or contact_doc.phone,
        })

    return {
        "supplier_name": supplier.supplier_name,
        "supplier_group": supplier.supplier_group,
        "supplier_type": supplier.supplier_type,
        "country": supplier.country,
        "contacts": contact_details,
    }


def search_purchase_order(query=None):
    """Recherche des commandes fournisseurs par nom de fournisseur. Sans 'query', retourne les 10 plus récentes. Lecture seule."""
    if not frappe.has_permission("Purchase Order", "read"):
        return {"error": "Permission refusée pour lire les commandes fournisseurs."}

    filters = [["supplier", "like", f"%{query}%"]] if query else None
    results = frappe.get_all(
        "Purchase Order",
        filters=filters,
        fields=["name", "supplier", "status", "grand_total", "schedule_date", "per_received", "per_billed"],
        order_by="transaction_date desc",
        limit=5 if query else 10,
    )
    return {"results": results, "count": len(results)}


def list_unpaid_purchase_bills(supplier_name=None):
    """
    Liste les factures fournisseurs avec un solde restant dû (outstanding_amount > 0).
    Si supplier_name est fourni, filtre sur ce fournisseur. Sinon, retourne les 10
    factures impayées les plus récentes tous fournisseurs confondus. Lecture seule.
    """
    if not frappe.has_permission("Purchase Invoice", "read"):
        return {"error": "Permission refusée pour lire les factures fournisseurs."}

    filters = [["outstanding_amount", ">", 0], ["docstatus", "=", 1]]
    if supplier_name:
        filters.append(["supplier", "like", f"%{supplier_name}%"])

    results = frappe.get_all(
        "Purchase Invoice",
        filters=filters,
        fields=["name", "supplier", "grand_total", "outstanding_amount", "due_date", "status"],
        order_by="due_date asc",
        limit=10,
    )
    return {"results": results, "count": len(results)}


# ===========================================================================
# RAG DOCUMENTAIRE (Phase 10)
# ===========================================================================

def search_documents(query, top_k=5):
    """Recherche dans les documents indexés (contrats, procédures, catalogues...) par similarité sémantique. Lecture seule."""
    if not frappe.has_permission("AI Document", "read"):
        return {"error": "Permission refusée pour lire les documents."}
    if not query:
        return {"error": "Le paramètre 'query' est requis."}

    from erp_ai.rag import search_documents as rag_search
    return rag_search(query, top_k=top_k)


# ===========================================================================
# ACTIONS D'ÉCRITURE (Phase 6 + Phase 8) — nécessitent une validation humaine
# ===========================================================================
# Ces outils NE sont jamais exécutés directement par ollama_client.chat().
# Ils sont listés ici pour leur schéma JSON (décrit au LLM) et leur fonction
# d'exécution réelle, appelée seulement après confirmation explicite de
# l'utilisateur via confirm_action() dans ollama_client.py.

def _get_default_company():
    companies = frappe.get_all("Company", pluck="name", limit=1)
    return companies[0] if companies else None


def _create_linked_contact(link_doctype, link_name, contact_person=None, email_id=None, mobile_no=None):
    """
    Crée un Contact lié (Dynamic Link) à un Customer/Supplier, si au moins une
    info de contact a été fournie. Best-effort : une erreur ici n'empêche pas
    la création du Customer/Supplier lui-même.
    """
    if not (contact_person or email_id or mobile_no):
        return None
    try:
        parts = (contact_person or link_name).split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": first_name,
            "last_name": last_name,
            "email_ids": [{"email_id": email_id, "is_primary": 1}] if email_id else [],
            "phone_nos": [{"phone": mobile_no, "is_primary_phone": 1}] if mobile_no else [],
            "links": [{"link_doctype": link_doctype, "link_name": link_name}],
        })
        contact.insert(ignore_permissions=True)
        return contact.name
    except Exception:
        frappe.log_error(title=f"erp_ai: échec création contact lié ({link_doctype} {link_name})")
        return None


def create_lead(lead_name, company_name=None, email_id=None, mobile_no=None):
    """Crée un nouveau lead. ACTION D'ÉCRITURE — appelée uniquement après validation humaine."""
    if not frappe.has_permission("Lead", "create"):
        return {"error": "Permission refusée pour créer un lead."}

    if not lead_name:
        return {"error": "Le paramètre 'lead_name' est requis."}

    doc = frappe.get_doc({
        "doctype": "Lead",
        "lead_name": lead_name,
        "company_name": company_name,
        "email_id": email_id,
        "mobile_no": mobile_no,
        "status": "Lead",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"created": True, "name": doc.name, "lead_name": doc.lead_name}


def create_supplier(supplier_name, supplier_type="Company", supplier_group=None,
                     country=None, mobile_no=None, email_id=None, tax_id=None, contact_person=None):
    """
    Crée un nouveau fournisseur, avec ses informations de contact courantes.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Supplier", "create"):
        return {"error": "Permission refusée pour créer un fournisseur."}

    if not supplier_name:
        return {"error": "Le paramètre 'supplier_name' est requis."}

    default_group = frappe.get_all("Supplier Group", limit=1, pluck="name")
    doc = frappe.get_doc({
        "doctype": "Supplier",
        "supplier_name": supplier_name,
        "supplier_type": supplier_type,
        "supplier_group": supplier_group if (supplier_group and frappe.db.exists("Supplier Group", supplier_group)) else (default_group[0] if default_group else None),
        "country": country if (country and frappe.db.exists("Country", country)) else None,
        "mobile_no": mobile_no,
        "tax_id": tax_id,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    contact_name = _create_linked_contact("Supplier", doc.name, contact_person, email_id, mobile_no)

    return {
        "created": True,
        "name": doc.name,
        "supplier_name": doc.supplier_name,
        "contact_created": contact_name,
    }


def create_customer(customer_name, customer_type="Company", customer_group=None, territory=None,
                     mobile_no=None, email_id=None, tax_id=None, contact_person=None):
    """
    Crée un nouveau client, avec ses informations de contact courantes.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Customer", "create"):
        return {"error": "Permission refusée pour créer un client."}

    if not customer_name:
        return {"error": "Le paramètre 'customer_name' est requis."}

    default_group = frappe.get_all("Customer Group", limit=1, pluck="name")
    default_territory = frappe.get_all("Territory", limit=1, pluck="name")
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": customer_type,
        "customer_group": customer_group if (customer_group and frappe.db.exists("Customer Group", customer_group)) else (default_group[0] if default_group else None),
        "territory": territory if (territory and frappe.db.exists("Territory", territory)) else (default_territory[0] if default_territory else None),
        "mobile_no": mobile_no,
        "tax_id": tax_id,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    contact_name = _create_linked_contact("Customer", doc.name, contact_person, email_id, mobile_no)

    return {
        "created": True,
        "name": doc.name,
        "customer_name": doc.customer_name,
        "contact_created": contact_name,
    }

def _resolve_party_name(doctype, name, name_field):
    """Retrouve le nom exact d'un Customer/Supplier, par correspondance approchée si besoin."""
    if frappe.db.exists(doctype, name):
        return name
    match = frappe.get_all(doctype, filters=[[name_field, "like", f"%{name}%"]], fields=["name"], limit=1)
    return match[0]["name"] if match else None


def update_supplier(supplier_name, supplier_type=None, supplier_group=None,
                     country=None, mobile_no=None, tax_id=None):
    """
    Met à jour un fournisseur existant. Seuls les champs fournis (non vides)
    sont modifiés — un champ omis ou vide laisse la valeur actuelle inchangée.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Supplier", "write"):
        return {"error": "Permission refusée pour modifier un fournisseur."}
    if not supplier_name:
        return {"error": "Le paramètre 'supplier_name' est requis."}

    resolved = _resolve_party_name("Supplier", supplier_name, "supplier_name")
    if not resolved:
        return {"error": f"Aucun fournisseur trouvé pour '{supplier_name}'."}

    doc = frappe.get_doc("Supplier", resolved)
    changed = []
    for field, value in [
        ("supplier_type", supplier_type),
        ("supplier_group", supplier_group if (supplier_group and frappe.db.exists("Supplier Group", supplier_group)) else None),
        ("country", country if (country and frappe.db.exists("Country", country)) else None),
        ("mobile_no", mobile_no),
        ("tax_id", tax_id),
    ]:
        if value not in (None, ""):
            doc.set(field, value)
            changed.append(field)

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "fields_changed": changed}


def update_customer(customer_name, customer_type=None, customer_group=None, territory=None,
                     mobile_no=None, tax_id=None):
    """
    Met à jour un client existant. Seuls les champs fournis (non vides)
    sont modifiés — un champ omis ou vide laisse la valeur actuelle inchangée.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Customer", "write"):
        return {"error": "Permission refusée pour modifier un client."}
    if not customer_name:
        return {"error": "Le paramètre 'customer_name' est requis."}

    resolved = _resolve_party_name("Customer", customer_name, "customer_name")
    if not resolved:
        return {"error": f"Aucun client trouvé pour '{customer_name}'."}

    doc = frappe.get_doc("Customer", resolved)
    changed = []
    for field, value in [
        ("customer_type", customer_type),
        ("customer_group", customer_group if (customer_group and frappe.db.exists("Customer Group", customer_group)) else None),
        ("territory", territory if (territory and frappe.db.exists("Territory", territory)) else None),
        ("mobile_no", mobile_no),
        ("tax_id", tax_id),
    ]:
        if value not in (None, ""):
            doc.set(field, value)
            changed.append(field)

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "fields_changed": changed}

def create_opportunity(party_name, opportunity_amount=None):
    """Crée une nouvelle opportunité pour un client existant. ACTION D'ÉCRITURE — appelée uniquement après validation humaine."""
    if not frappe.has_permission("Opportunity", "create"):
        return {"error": "Permission refusée pour créer une opportunité."}

    if not party_name:
        return {"error": "Le paramètre 'party_name' est requis."}

    if not frappe.db.exists("Customer", party_name):
        return {"error": f"Aucun client '{party_name}' trouvé. Crée d'abord le client, ou vérifie l'orthographe."}

    doc = frappe.get_doc({
        "doctype": "Opportunity",
        "opportunity_from": "Customer",
        "party_name": party_name,
        "opportunity_amount": opportunity_amount,
        "status": "Open",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"created": True, "name": doc.name, "party_name": doc.party_name}

def _get_draft_doc(doctype, name):
    """Récupère un document existant, en vérifiant qu'il est encore en brouillon (docstatus=0)."""
    if not frappe.db.exists(doctype, name):
        return None, {"error": f"{doctype} introuvable : '{name}'. Utilise l'outil de recherche correspondant pour retrouver son identifiant exact."}
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus != 0:
        return None, {"error": f"{doctype} '{name}' est déjà soumis — modification impossible depuis le chat. Passe par ERPNext directement (Annuler puis Modifier)."}
    return doc, None


def update_opportunity(opportunity_name, status=None, opportunity_amount=None):
    """
    Met à jour une opportunité existante (statut, montant). Seuls les champs
    fournis sont modifiés. ACTION D'ÉCRITURE — appelée uniquement après
    validation humaine.
    """
    if not frappe.has_permission("Opportunity", "write"):
        return {"error": "Permission refusée pour modifier une opportunité."}
    if not opportunity_name:
        return {"error": "Le paramètre 'opportunity_name' est requis."}
    if not frappe.db.exists("Opportunity", opportunity_name):
        return {"error": f"Aucune opportunité trouvée pour '{opportunity_name}'. Utilise search_opportunity pour retrouver son identifiant exact."}

    doc = frappe.get_doc("Opportunity", opportunity_name)
    changed = []
    valid_statuses = ["Open", "Quotation", "Converted", "Lost", "Replied", "Closed"]
    if status not in (None, ""):
        if status not in valid_statuses:
            return {"error": f"Statut invalide : '{status}'. Valeurs possibles : {', '.join(valid_statuses)}."}
        doc.set("status", status)
        changed.append("status")
    if opportunity_amount not in (None, ""):
        doc.set("opportunity_amount", opportunity_amount)
        changed.append("opportunity_amount")

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "fields_changed": changed}


def update_quotation(quotation_name, valid_till=None, items=None):
    """
    Met à jour un devis encore en brouillon (date de validité et/ou lignes
    d'articles). ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Quotation", "write"):
        return {"error": "Permission refusée pour modifier un devis."}
    if not quotation_name:
        return {"error": "Le paramètre 'quotation_name' est requis."}

    doc, err = _get_draft_doc("Quotation", quotation_name)
    if err:
        return err

    changed = []
    if valid_till not in (None, ""):
        try:
            doc.set("valid_till", frappe.utils.getdate(valid_till))
            changed.append("valid_till")
        except Exception:
            return {"error": f"Date invalide : '{valid_till}'. Format attendu AAAA-MM-JJ."}

    if items:
        resolved_items, item_err = _validate_items(items)
        if item_err:
            return item_err
        doc.set("items", [])
        for i in resolved_items:
            doc.append("items", {"item_code": i["item_code"], "qty": i["qty"], "rate": i.get("rate")})
        changed.append("items")

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "grand_total": doc.grand_total, "fields_changed": changed}


def update_sales_order(sales_order_name, delivery_date=None, items=None):
    """
    Met à jour une commande client encore en brouillon (date de livraison
    et/ou lignes d'articles). ACTION D'ÉCRITURE — appelée uniquement après
    validation humaine.
    """
    if not frappe.has_permission("Sales Order", "write"):
        return {"error": "Permission refusée pour modifier une commande client."}
    if not sales_order_name:
        return {"error": "Le paramètre 'sales_order_name' est requis."}

    doc, err = _get_draft_doc("Sales Order", sales_order_name)
    if err:
        return err

    changed = []
    if delivery_date not in (None, ""):
        try:
            doc.set("delivery_date", frappe.utils.getdate(delivery_date))
            changed.append("delivery_date")
        except Exception:
            return {"error": f"Date invalide : '{delivery_date}'. Format attendu AAAA-MM-JJ."}

    if items:
        resolved_items, item_err = _validate_items(items)
        if item_err:
            return item_err
        doc.set("items", [])
        for i in resolved_items:
            doc.append("items", {"item_code": i["item_code"], "qty": i["qty"], "rate": i.get("rate")})
        changed.append("items")

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "grand_total": doc.grand_total, "fields_changed": changed}

def create_item(item_code, item_name, rate=None):
    """Crée un nouvel article. ACTION D'ÉCRITURE — appelée uniquement après validation humaine."""
    if not frappe.has_permission("Item", "create"):
        return {"error": "Permission refusée pour créer un article."}

    if not item_code or not item_name:
        return {"error": "Les paramètres 'item_code' et 'item_name' sont requis."}

    if frappe.db.exists("Item", item_code):
        return {"error": f"Un article avec le code '{item_code}' existe déjà."}

    item_group = frappe.get_all("Item Group", filters={"is_group": 0}, limit=1, pluck="name")
    uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.get_all("UOM", limit=1, pluck="name")

    doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_name,
        "item_group": item_group[0] if item_group else "All Item Groups",
        "stock_uom": uom if isinstance(uom, str) else (uom[0] if uom else "Nos"),
        "is_stock_item": 1,
        "standard_rate": rate,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"created": True, "name": doc.name, "item_code": doc.item_code}

def update_item(item_code, item_name=None, rate=None, disabled=None):
    """
    Met à jour un article existant. Seuls les champs fournis (non vides/None)
    sont modifiés — un champ omis laisse la valeur actuelle inchangée.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Item", "write"):
        return {"error": "Permission refusée pour modifier un article."}
    if not item_code:
        return {"error": "Le paramètre 'item_code' est requis."}

    if not frappe.db.exists("Item", item_code):
        matches = _find_item_by_fuzzy_name(item_code)
        if len(matches) == 1:
            item_code = matches[0]["item_code"]
        elif matches:
            suggestions = ", ".join(f"{m['item_code']} ({m['item_name']})" for m in matches[:5])
            return {"error": f"Article introuvable : '{item_code}'. Suggestions : {suggestions}. Corrige le champ item_code dans le formulaire."}
        else:
            return {"error": f"Article introuvable : '{item_code}'. Vérifie le code exact avec search_item."}

    doc = frappe.get_doc("Item", item_code)
    changed = []
    if item_name not in (None, ""):
        doc.set("item_name", item_name)
        changed.append("item_name")
    if rate not in (None, ""):
        doc.set("standard_rate", rate)
        changed.append("standard_rate")
    if disabled is not None:
        doc.set("disabled", 1 if disabled else 0)
        changed.append("disabled")

    if not changed:
        return {"error": "Aucun champ valide à mettre à jour n'a été fourni."}

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"updated": True, "name": doc.name, "fields_changed": changed}

def _validate_items(items):
    """
    Vérifie chaque ligne d'articles. Si un item_code n'existe pas tel quel
    (le modèle en a parfois halluciné un plausible), tente de le résoudre
    automatiquement par son nom ; sinon renvoie une erreur avec suggestions
    exploitables (l'utilisateur peut corriger le champ dans le formulaire).
    """
    if not items or not isinstance(items, list):
        return None, {"error": "Le paramètre 'items' doit être une liste non vide de {item_code, qty, rate}."}

    resolved = []
    for line in items:
        code = line.get("item_code")
        if not code:
            return None, {"error": "item_code manquant pour une ligne d'article."}

        if not frappe.db.exists("Item", code):
            matches = _find_item_by_fuzzy_name(code)
            if len(matches) == 1:
                code = matches[0]["item_code"]  # résolution automatique, code corrigé
            elif matches:
                suggestions = ", ".join(f"{m['item_code']} ({m['item_name']})" for m in matches[:5])
                return None, {"error": f"Article introuvable : '{code}'. Suggestions : {suggestions}. Corrige le champ item_code dans le formulaire."}
            else:
                return None, {"error": f"Article introuvable : '{code}'. Vérifie le code exact avec search_item, ou corrige-le dans le formulaire."}

        if not line.get("qty") or float(line.get("qty")) <= 0:
            return None, {"error": f"Quantité invalide pour l'article '{code}'."}

        resolved.append({**line, "item_code": code})

    return resolved, None


def create_quotation(customer_name, items, valid_till=None):
    """
    Crée un devis (Quotation) pour un client, avec ses lignes d'articles.
    Le document est créé en BROUILLON (non soumis) — une revue/soumission
    manuelle dans ERPNext reste nécessaire avant envoi au client.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Quotation", "create"):
        return {"error": "Permission refusée pour créer un devis."}
    if not customer_name or not frappe.db.exists("Customer", customer_name):
        return {"error": f"Client introuvable : '{customer_name}'."}

    items, err = _validate_items(items)
    if err:
        return err

    valid_till_date = None
    if valid_till:
        try:
            valid_till_date = frappe.utils.getdate(valid_till)
        except Exception:
            valid_till_date = None
    if not valid_till_date or valid_till_date < frappe.utils.getdate(frappe.utils.nowdate()):
        valid_till_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)

    company = _get_default_company()
    doc = frappe.get_doc({
        "doctype": "Quotation",
        "quotation_to": "Customer",
        "party_name": customer_name,
        "company": company,
        "valid_till": valid_till_date,
        "items": [{"item_code": i["item_code"], "qty": i["qty"], "rate": i.get("rate")} for i in items],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {
        "created": True,
        "name": doc.name,
        "customer_name": customer_name,
        "grand_total": doc.grand_total,
        "status": "Brouillon (non soumis) — à valider dans ERPNext.",
    }


def create_sales_order(customer_name, items, delivery_date=None):
    """
    Crée une commande client (Sales Order), avec ses lignes d'articles.
    Le document est créé en BROUILLON (non soumis) — une revue/soumission
    manuelle dans ERPNext reste nécessaire pour qu'elle devienne effective.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Sales Order", "create"):
        return {"error": "Permission refusée pour créer une commande client."}
    if not customer_name or not frappe.db.exists("Customer", customer_name):
        return {"error": f"Client introuvable : '{customer_name}'."}

    items, err = _validate_items(items)
    if err:
        return err

    delivery_date_final = None
    if delivery_date:
        try:
            delivery_date_final = frappe.utils.getdate(delivery_date)
        except Exception:
            delivery_date_final = None
    if not delivery_date_final or delivery_date_final < frappe.utils.getdate(frappe.utils.nowdate()):
        delivery_date_final = frappe.utils.add_days(frappe.utils.nowdate(), 14)

    company = _get_default_company()
    doc = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": customer_name,
        "company": company,
        "delivery_date": delivery_date_final,
        "items": [{"item_code": i["item_code"], "qty": i["qty"], "rate": i.get("rate")} for i in items],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {
        "created": True,
        "name": doc.name,
        "customer_name": customer_name,
        "grand_total": doc.grand_total,
        "status": "Brouillon (non soumis) — à valider dans ERPNext.",
    }


def create_purchase_order(supplier_name, items, schedule_date=None):
    """
    Crée une commande fournisseur (Purchase Order), avec ses lignes d'articles.
    Le document est créé en BROUILLON (non soumis) — une revue/soumission
    manuelle dans ERPNext reste nécessaire pour qu'elle devienne effective.
    ACTION D'ÉCRITURE — appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Purchase Order", "create"):
        return {"error": "Permission refusée pour créer une commande fournisseur."}
    if not supplier_name or not frappe.db.exists("Supplier", supplier_name):
        return {"error": f"Fournisseur introuvable : '{supplier_name}'."}

    items, err = _validate_items(items)
    if err:
        return err

    schedule_date_final = None
    if schedule_date:
        try:
            schedule_date_final = frappe.utils.getdate(schedule_date)
        except Exception:
            schedule_date_final = None
    if not schedule_date_final or schedule_date_final < frappe.utils.getdate(frappe.utils.nowdate()):
        schedule_date_final = frappe.utils.add_days(frappe.utils.nowdate(), 14)

    company = _get_default_company()
    doc = frappe.get_doc({
        "doctype": "Purchase Order",
        "supplier": supplier_name,
        "company": company,
        "schedule_date": schedule_date_final,
        "items": [{"item_code": i["item_code"], "qty": i["qty"], "rate": i.get("rate")} for i in items],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {
        "created": True,
        "name": doc.name,
        "supplier_name": supplier_name,
        "grand_total": doc.grand_total,
        "status": "Brouillon (non soumis) — à valider dans ERPNext.",
    }


def receive_stock(item_code, qty, warehouse=None, rate=None):
    """
    Augmente le stock d'un article via une entrée de stock (Material Receipt),
    soumise immédiatement (impact réel sur le stock). ACTION D'ÉCRITURE —
    appelée uniquement après validation humaine.
    """
    if not frappe.has_permission("Stock Entry", "create"):
        return {"error": "Permission refusée pour créer un mouvement de stock."}
    if not item_code:
        return {"error": "Le paramètre 'item_code' est requis."}
    if not qty or float(qty) <= 0:
        return {"error": "La quantité doit être un nombre positif."}

    if not frappe.db.exists("Item", item_code):
        matches = _find_item_by_fuzzy_name(item_code)
        if len(matches) == 1:
            item_code = matches[0]["item_code"]
        elif matches:
            suggestions = ", ".join(f"{m['item_code']} ({m['item_name']})" for m in matches[:5])
            return {"error": f"Article introuvable : '{item_code}'. Suggestions : {suggestions}. Corrige le champ item_code dans le formulaire."}
        else:
            return {"error": f"Article introuvable : '{item_code}'. Vérifie le code exact avec search_item."}

    if warehouse and not frappe.db.exists("Warehouse", warehouse):
        return {"error": f"Entrepôt introuvable : '{warehouse}'."}
    if not warehouse:
        default_warehouses = frappe.get_all("Warehouse", filters={"is_group": 0}, limit=1, pluck="name")
        warehouse = default_warehouses[0] if default_warehouses else None
    if not warehouse:
        return {"error": "Aucun entrepôt disponible sur ce site."}

    company = _get_default_company()
    doc = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": company,
        "items": [{
            "item_code": item_code,
            "qty": qty,
            "t_warehouse": warehouse,
            "basic_rate": rate or 0,
        }],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    return {
        "created": True,
        "name": doc.name,
        "item_code": item_code,
        "warehouse": warehouse,
        "qty": qty,
        "status": "Entrée de stock soumise — le stock est déjà mis à jour.",
    }


# ===========================================================================
# SYNTHÈSES CHIFFRÉES (analyse, stratégie, consolidation) — lecture seule
# ===========================================================================
# Ces outils calculent de vraies statistiques agrégées à partir des données
# réelles, pour que le modèle puisse répondre à des questions d'analyse ou
# de stratégie avec des chiffres concrets, au lieu de lister 10 lignes
# brutes ou de demander les données à l'utilisateur.

def get_sales_summary(period_days=30):
    """
    Statistiques agrégées des ventes sur une période : chiffre d'affaires
    facturé, nombre de factures et commandes, top 5 clients par CA, total
    des impayés (tous horizons). Lecture seule.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        return {"error": "Permission refusée pour lire les ventes."}

    period_days = int(period_days or 30)
    start_date = frappe.utils.add_days(frappe.utils.nowdate(), -period_days)

    total_revenue = frappe.db.sql(
        "SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Invoice` "
        "WHERE docstatus = 1 AND posting_date >= %(start)s",
        {"start": start_date},
    )[0][0]

    invoice_count = frappe.db.count("Sales Invoice", {"docstatus": 1, "posting_date": [">=", start_date]})
    order_count = frappe.db.count("Sales Order", {"docstatus": 1, "transaction_date": [">=", start_date]})

    top_customers = frappe.db.sql(
        "SELECT customer, SUM(grand_total) AS total FROM `tabSales Invoice` "
        "WHERE docstatus = 1 AND posting_date >= %(start)s "
        "GROUP BY customer ORDER BY total DESC LIMIT 5",
        {"start": start_date},
        as_dict=True,
    )

    total_outstanding = frappe.db.sql(
        "SELECT COALESCE(SUM(outstanding_amount), 0) FROM `tabSales Invoice` "
        "WHERE docstatus = 1 AND outstanding_amount > 0"
    )[0][0]

    return {
        "period_days": period_days,
        "currency": frappe.db.get_value("Company", _get_default_company(), "default_currency"),
        "total_revenue": total_revenue,
        "invoice_count": invoice_count,
        "sales_order_count": order_count,
        "top_customers": top_customers,
        "total_outstanding_all_time": total_outstanding,
    }


def get_purchase_summary(period_days=30):
    """
    Statistiques agrégées des achats sur une période : dépenses facturées,
    nombre de factures et commandes, top 5 fournisseurs par dépense, total
    des dettes fournisseurs (tous horizons). Lecture seule.
    """
    if not frappe.has_permission("Purchase Invoice", "read"):
        return {"error": "Permission refusée pour lire les achats."}

    period_days = int(period_days or 30)
    start_date = frappe.utils.add_days(frappe.utils.nowdate(), -period_days)

    total_spend = frappe.db.sql(
        "SELECT COALESCE(SUM(grand_total), 0) FROM `tabPurchase Invoice` "
        "WHERE docstatus = 1 AND posting_date >= %(start)s",
        {"start": start_date},
    )[0][0]

    bill_count = frappe.db.count("Purchase Invoice", {"docstatus": 1, "posting_date": [">=", start_date]})
    order_count = frappe.db.count("Purchase Order", {"docstatus": 1, "transaction_date": [">=", start_date]})

    top_suppliers = frappe.db.sql(
        "SELECT supplier, SUM(grand_total) AS total FROM `tabPurchase Invoice` "
        "WHERE docstatus = 1 AND posting_date >= %(start)s "
        "GROUP BY supplier ORDER BY total DESC LIMIT 5",
        {"start": start_date},
        as_dict=True,
    )

    total_payable = frappe.db.sql(
        "SELECT COALESCE(SUM(outstanding_amount), 0) FROM `tabPurchase Invoice` "
        "WHERE docstatus = 1 AND outstanding_amount > 0"
    )[0][0]

    return {
        "period_days": period_days,
        "currency": frappe.db.get_value("Company", _get_default_company(), "default_currency"),
        "total_spend": total_spend,
        "purchase_invoice_count": bill_count,
        "purchase_order_count": order_count,
        "top_suppliers": top_suppliers,
        "total_payable_all_time": total_payable,
    }


def get_stock_summary():
    """
    Statistiques agrégées du stock : nombre d'articles actifs, nombre
    d'articles sous le seuil de réapprovisionnement, nombre d'articles à
    zéro, valeur totale estimée du stock. Lecture seule.
    """
    if not frappe.has_permission("Item", "read") or not frappe.has_permission("Bin", "read"):
        return {"error": "Permission refusée pour lire le stock."}

    total_items = frappe.db.count("Item", {"disabled": 0, "is_stock_item": 1})

    low_stock_count = list_low_stock_items().get("count", 0)

    zero_stock_count = frappe.db.sql(
        "SELECT COUNT(DISTINCT item_code) FROM `tabBin` WHERE actual_qty <= 0"
    )[0][0]

    total_stock_value = frappe.db.sql(
        "SELECT COALESCE(SUM(stock_value), 0) FROM `tabBin`"
    )[0][0]

    return {
        "currency": frappe.db.get_value("Company", _get_default_company(), "default_currency"),
        "total_active_items": total_items,
        "low_stock_count": low_stock_count,
        "zero_stock_count": zero_stock_count,
        "estimated_total_stock_value": total_stock_value,
    }

def get_executive_snapshot():
    """
    Vue exécutive consolidée : ventes/achats 7 jours, impayés clients/
    fournisseurs, alerte stock. Un seul appel, pensé pour l'agent Directeur
    AVANT toute décision d'approfondir via consult_agent. Lecture seule.
    """
    sales = get_sales_summary(period_days=7)
    purchase = get_purchase_summary(period_days=7)
    stock = get_stock_summary()

    return {
        "period_days": 7,
        "currency": sales.get("currency"),
        "ventes": {
            "chiffre_affaires": sales.get("total_revenue"),
            "impayes_clients": sales.get("total_outstanding_all_time"),
        },
        "achats": {
            "depenses": purchase.get("total_spend"),
            "dettes_fournisseurs": purchase.get("total_payable_all_time"),
        },
        "stock": {
            "articles_sous_seuil": stock.get("low_stock_count"),
            "articles_a_zero": stock.get("zero_stock_count"),
            "valeur_stock": stock.get("estimated_total_stock_value"),
        },
    }


def consult_agent(agent_key, question):
    """
    Délègue une question à un agent spécialisé (commercial/finance/stock/
    achat/documents), qui exécute lui-même ses outils et renvoie une
    synthèse texte. Utilisé par le Directeur pour approfondir un domaine
    après get_executive_snapshot. Lecture seule.
    """
    valid_agents = {"commercial", "finance", "stock", "achat", "documents"}
    if agent_key not in valid_agents:
        return {"error": f"Agent inconnu : '{agent_key}'. Agents disponibles : {', '.join(valid_agents)}."}
    if not question:
        return {"error": "Le paramètre 'question' est requis."}

    # Le Directeur ne doit pas contourner la restriction par rôle des agents.
    from erp_ai.agents import is_agent_allowed
    if not is_agent_allowed(agent_key):
        return {"error": f"Tu n'as pas la permission de consulter l'agent '{agent_key}' avec ton rôle actuel."}

    from erp_ai.ollama_client import run_agent_query
    return run_agent_query(agent_key, question)

# Ensemble des noms d'outils considérés comme des actions d'écriture.
# ollama_client.py s'en sert pour déclencher le circuit de validation
# humaine au lieu d'une exécution immédiate.
WRITE_TOOLS = {
    "create_lead",
    "create_supplier",
    "create_customer",
    "update_supplier",
    "update_customer",
    "create_opportunity",
    "update_opportunity",
    "update_quotation",
    "update_sales_order",
    "create_item",
    "update_item",
    "create_quotation",
    "create_sales_order",
    "create_purchase_order",
    "receive_stock",


}


# ===========================================================================
# Registre : nom d'outil -> fonction Python
# ===========================================================================
TOOLS_REGISTRY = {
    "search_customer": search_customer,
    "search_lead": search_lead,
    "search_opportunity": search_opportunity,
    "get_customer_details": get_customer_details,
    "search_quotation": search_quotation,
    "search_sales_order": search_sales_order,
    "list_unpaid_invoices": list_unpaid_invoices,
    "search_item": search_item,
    "get_item_stock": get_item_stock,
    "list_low_stock_items": list_low_stock_items,
    "get_stock_ledger": get_stock_ledger,
    "search_supplier": search_supplier,
    "get_supplier_details": get_supplier_details,
    "search_purchase_order": search_purchase_order,
    "list_unpaid_purchase_bills": list_unpaid_purchase_bills,
    "create_lead": create_lead,
    "create_supplier": create_supplier,
    "create_customer": create_customer,
    "update_supplier": update_supplier,
    "update_customer": update_customer,
    "create_opportunity": create_opportunity,
    "update_opportunity": update_opportunity,
    "update_quotation": update_quotation,
    "update_sales_order": update_sales_order,
    "create_item": create_item,
    "update_item": update_item,
    "create_quotation": create_quotation,
    "create_sales_order": create_sales_order,
    "create_purchase_order": create_purchase_order,
    "receive_stock": receive_stock,
    "get_sales_summary": get_sales_summary,
    "get_purchase_summary": get_purchase_summary,
    "get_stock_summary": get_stock_summary,
    "get_executive_snapshot": get_executive_snapshot,
    "consult_agent": consult_agent,
    "search_documents": search_documents,

}


# ===========================================================================
# Schéma JSON décrivant les outils au LLM (format Ollama / OpenAI function calling)
# ===========================================================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_customer",
            "description": "Recherche des clients ERPNext par nom (recherche partielle), ou liste "
                            "les plus récents si aucun nom n'est précisé. Utilise cet outil quand "
                            "l'utilisateur demande des informations sur un client, veut vérifier "
                            "s'il existe, veut son numéro/territoire, ou veut la liste des clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom (ou partie du nom) du client à rechercher. Optionnel : omets ce paramètre pour lister les clients récents."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_lead",
            "description": "Recherche des leads (prospects non encore convertis en clients) par "
                            "nom de contact ou nom d'entreprise, ou liste les plus récents si aucun "
                            "nom n'est précisé. Utilise cet outil pour les questions sur les prospects, "
                            "leur statut de qualification, leurs coordonnées, ou pour lister les leads actuels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom du lead ou de son entreprise à rechercher. Optionnel : omets ce paramètre pour lister les leads récents."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_opportunity",
            "description": "Recherche des opportunités commerciales par nom de client, ou liste les "
                            "plus récentes si aucun nom n'est précisé. Utilise cet outil pour les "
                            "questions sur le pipeline commercial, le statut d'une affaire en cours, "
                            "le montant potentiel d'une vente, ou pour lister les opportunités actuelles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom du client/party lié à l'opportunité recherchée. Optionnel : omets ce paramètre pour lister les opportunités récentes."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_details",
            "description": "Récupère la fiche complète d'un client précis : groupe, territoire, "
                            "type, et ses contacts associés (email, téléphone). Utilise cet outil "
                            "quand l'utilisateur veut le détail complet d'un client déjà identifié, "
                            "notamment ses coordonnées de contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom exact ou approximatif du client."},
                },
                "required": ["customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_quotation",
            "description": "Recherche des devis (Quotation) par nom de client, ou liste les plus "
                            "récents si aucun nom n'est précisé. Utilise cet outil pour les questions "
                            "sur les devis envoyés, leur statut, leur montant, ou pour lister les devis récents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom du client lié au devis recherché. Optionnel : omets ce paramètre pour lister les devis récents."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sales_order",
            "description": "Recherche des commandes clients (Sales Order) par nom de client, ou "
                            "liste les plus récentes si aucun nom n'est précisé. Utilise cet outil "
                            "pour les questions sur les commandes en cours, leur statut de livraison "
                            "ou de facturation, ou pour lister les commandes récentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom du client lié à la commande recherchée. Optionnel : omets ce paramètre pour lister les commandes récentes."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unpaid_invoices",
            "description": "Liste les factures clients impayées (solde restant dû > 0), triées "
                            "par date d'échéance. Utilise cet outil pour les questions sur les "
                            "impayés clients, les retards de paiement reçus, ou les relances à faire. "
                            "Le paramètre customer_name est optionnel : sans lui, retourne les "
                            "impayés de tous les clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom du client à filtrer (optionnel)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_item",
            "description": "Recherche des articles ERPNext par code ou nom (recherche partielle), "
                            "ou liste les plus récents si aucun nom n'est précisé. Utilise cet outil "
                            "quand l'utilisateur cherche un article, veut vérifier son existence, son "
                            "groupe d'article, son unité de mesure, ou veut la liste des articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code ou nom (ou partie du nom) de l'article recherché. Optionnel : omets ce paramètre pour lister les articles récents."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_item_stock",
            "description": "Récupère le stock actuel d'un article donné, détaillé par entrepôt "
                            "(quantité disponible, réservée, projetée). Utilise cet outil pour les "
                            "questions sur la disponibilité ou la quantité en stock d'un article précis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string", "description": "Code ou nom de l'article."},
                },
                "required": ["item_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_low_stock_items",
            "description": "Liste les articles dont le stock actuel est sous leur niveau de "
                            "réapprovisionnement défini. Utilise cet outil pour les questions sur "
                            "les articles à recommander, les ruptures de stock imminentes, ou les "
                            "besoins de réapprovisionnement. Le paramètre warehouse est optionnel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "warehouse": {"type": "string", "description": "Nom de l'entrepôt à filtrer (optionnel)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_ledger",
            "description": "Récupère les derniers mouvements de stock (entrées/sorties) d'un "
                            "article précis. Utilise cet outil pour les questions sur l'historique "
                            "des mouvements, les dernières entrées ou sorties d'un article.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string", "description": "Code de l'article."},
                    "warehouse": {"type": "string", "description": "Nom de l'entrepôt à filtrer (optionnel)."},
                },
                "required": ["item_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_supplier",
            "description": "Recherche des fournisseurs ERPNext par nom (recherche partielle), ou "
                            "liste les plus récents si aucun nom n'est précisé. Utilise cet outil "
                            "quand l'utilisateur demande des informations sur un fournisseur, veut "
                            "vérifier son existence, ou veut la liste des fournisseurs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom (ou partie du nom) du fournisseur à rechercher. Optionnel : omets ce paramètre pour lister les fournisseurs récents."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_supplier_details",
            "description": "Récupère la fiche complète d'un fournisseur précis : groupe, type, "
                            "pays, et ses contacts associés (email, téléphone). Utilise cet outil "
                            "quand l'utilisateur veut le détail complet d'un fournisseur déjà "
                            "identifié, y compris son pays.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Nom exact ou approximatif du fournisseur."},
                },
                "required": ["supplier_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_purchase_order",
            "description": "Recherche des commandes fournisseurs (Purchase Order) par nom de "
                            "fournisseur, ou liste les plus récentes si aucun nom n'est précisé. "
                            "Utilise cet outil pour les questions sur les commandes d'achat en cours, "
                            "leur statut de réception ou de facturation, ou pour lister les commandes récentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom du fournisseur lié à la commande recherchée. Optionnel : omets ce paramètre pour lister les commandes récentes."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unpaid_purchase_bills",
            "description": "Liste les factures fournisseurs impayées (solde restant dû > 0), "
                            "triées par date d'échéance. Utilise cet outil pour les questions sur "
                            "les dettes fournisseurs, les paiements à effectuer, ou les échéances "
                            "d'achat à venir. Le paramètre supplier_name est optionnel : sans lui, "
                            "retourne les impayés de tous les fournisseurs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Nom du fournisseur à filtrer (optionnel)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_lead",
            "description": "Crée un nouveau lead (prospect individuel non encore client) dans "
                            "ERPNext. N'utilise CET outil QUE si l'utilisateur demande explicitement "
                            "un lead/prospect — jamais pour un client ou un fournisseur, qui ont "
                            "chacun leur propre outil de création. ACTION D'ÉCRITURE : cette action "
                            "sera proposée à l'utilisateur pour validation humaine avant d'être "
                            "réellement exécutée — informe l'utilisateur que tu vas soumettre cette "
                            "création pour approbation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_name": {"type": "string", "description": "Nom complet du lead (obligatoire)."},
                    "company_name": {"type": "string", "description": "Nom de l'entreprise du lead (optionnel)."},
                    "email_id": {"type": "string", "description": "Adresse email du lead (optionnel)."},
                    "mobile_no": {"type": "string", "description": "Numéro de téléphone mobile (optionnel)."},
                },
                "required": ["lead_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_supplier",
            "description": "Crée un nouveau fournisseur dans ERPNext. N'utilise CET outil QUE si "
                            "l'utilisateur demande explicitement un fournisseur — jamais pour un "
                            "lead ou un client, qui ont chacun leur propre outil de création. "
                            "IMPORTANT : inclus TOUJOURS tous les paramètres optionnels dans ton "
                            "appel, même avec une valeur vide (\"\") si l'utilisateur ne les a pas "
                            "donnés — cela permet d'afficher une fiche complète à remplir/corriger "
                            "dans le formulaire de validation, sans que l'utilisateur ait besoin de "
                            "la redemander explicitement. Ne pose pas de question de clarification "
                            "pour ces champs optionnels : propose directement la fiche vide. "
                            "ACTION D'ÉCRITURE : cette action sera proposée à l'utilisateur pour "
                            "validation humaine avant d'être réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Nom du fournisseur (obligatoire)."},
                    "supplier_type": {"type": "string", "description": "Type : 'Company' ou 'Individual' (optionnel, par défaut 'Company')."},
                    "supplier_group": {"type": "string", "description": "Groupe de fournisseur (optionnel — laisse vide si inconnu, l'utilisateur le complétera dans la fiche)."},
                    "country": {"type": "string", "description": "Pays du fournisseur, nom exact ERPNext (ex: 'Algeria') (optionnel — laisse vide si inconnu)."},
                    "mobile_no": {"type": "string", "description": "Numéro de téléphone mobile (optionnel — laisse vide si inconnu)."},
                    "email_id": {"type": "string", "description": "Adresse email du contact (optionnel — laisse vide si inconnu)."},
                    "tax_id": {"type": "string", "description": "Numéro d'identification fiscale / RC (optionnel — laisse vide si inconnu)."},
                    "contact_person": {"type": "string", "description": "Nom de la personne à contacter chez ce fournisseur (optionnel — laisse vide si inconnu)."},
                },
                "required": ["supplier_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_customer",
            "description": "Crée un nouveau client dans ERPNext. N'utilise CET outil QUE si "
                            "l'utilisateur demande explicitement un client — jamais pour un lead "
                            "ou un fournisseur. IMPORTANT : inclus TOUJOURS tous les paramètres "
                            "optionnels dans ton appel, même avec une valeur vide (\"\") si "
                            "l'utilisateur ne les a pas donnés — cela permet d'afficher une fiche "
                            "complète à remplir/corriger dans le formulaire de validation, sans que "
                            "l'utilisateur ait besoin de la redemander explicitement. Ne pose pas de "
                            "question de clarification pour ces champs optionnels : propose "
                            "directement la fiche vide. ACTION D'ÉCRITURE : cette action sera "
                            "proposée à l'utilisateur pour validation humaine avant d'être réellement "
                            "exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom du client (obligatoire)."},
                    "customer_type": {"type": "string", "description": "Type : 'Company' ou 'Individual' (optionnel, par défaut 'Company')."},
                    "customer_group": {"type": "string", "description": "Groupe de client (optionnel — laisse vide si inconnu)."},
                    "territory": {"type": "string", "description": "Territoire du client (optionnel — laisse vide si inconnu)."},
                    "mobile_no": {"type": "string", "description": "Numéro de téléphone mobile (optionnel — laisse vide si inconnu)."},
                    "email_id": {"type": "string", "description": "Adresse email du contact (optionnel — laisse vide si inconnu)."},
                    "tax_id": {"type": "string", "description": "Numéro d'identification fiscale / RC (optionnel — laisse vide si inconnu)."},
                    "contact_person": {"type": "string", "description": "Nom de la personne à contacter chez ce client (optionnel — laisse vide si inconnu)."},
                },
                "required": ["customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_supplier",
            "description": "Modifie un fournisseur EXISTANT (pas une création). IMPORTANT : "
                            "appelle TOUJOURS get_supplier_details d'abord pour connaître les "
                            "valeurs actuelles, et inclus-les dans les champs non concernés par "
                            "la modification demandée — un champ laissé vide ou omis N'écrase PAS "
                            "la valeur actuelle, mais l'utilisateur doit voir les valeurs réelles "
                            "dans le formulaire de validation, pas des champs vides. ACTION "
                            "D'ÉCRITURE : proposée pour validation humaine avant exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Nom exact ou approximatif du fournisseur à modifier (obligatoire)."},
                    "supplier_type": {"type": "string", "description": "Nouveau type : 'Company' ou 'Individual' (optionnel)."},
                    "supplier_group": {"type": "string", "description": "Nouveau groupe de fournisseur (optionnel)."},
                    "country": {"type": "string", "description": "Nouveau pays, nom exact ERPNext ex: 'Algeria' (optionnel)."},
                    "mobile_no": {"type": "string", "description": "Nouveau numéro de mobile (optionnel)."},
                    "tax_id": {"type": "string", "description": "Nouveau numéro fiscal / RC (optionnel)."},
                },
                "required": ["supplier_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_customer",
            "description": "Modifie un client EXISTANT (pas une création). IMPORTANT : appelle "
                            "TOUJOURS get_customer_details d'abord pour connaître les valeurs "
                            "actuelles, et inclus-les dans les champs non concernés par la "
                            "modification demandée — un champ laissé vide ou omis N'écrase PAS la "
                            "valeur actuelle. ACTION D'ÉCRITURE : proposée pour validation humaine "
                            "avant exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom exact ou approximatif du client à modifier (obligatoire)."},
                    "customer_type": {"type": "string", "description": "Nouveau type : 'Company' ou 'Individual' (optionnel)."},
                    "customer_group": {"type": "string", "description": "Nouveau groupe de client (optionnel)."},
                    "territory": {"type": "string", "description": "Nouveau territoire (optionnel)."},
                    "mobile_no": {"type": "string", "description": "Nouveau numéro de mobile (optionnel)."},
                    "tax_id": {"type": "string", "description": "Nouveau numéro fiscal / RC (optionnel)."},
                },
                "required": ["customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_opportunity",
            "description": "Crée une nouvelle opportunité commerciale pour un client déjà existant "
                            "dans ERPNext. Le client doit exister au préalable (utilise create_customer "
                            "d'abord si besoin). ACTION D'ÉCRITURE : cette action sera proposée à "
                            "l'utilisateur pour validation humaine avant d'être réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "party_name": {"type": "string", "description": "Nom exact du client déjà existant (obligatoire)."},
                    "opportunity_amount": {"type": "number", "description": "Montant potentiel de l'opportunité (optionnel)."},
                },
                "required": ["party_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_opportunity",
            "description": "Modifie une opportunité EXISTANTE (statut ou montant). IMPORTANT : "
                            "appelle TOUJOURS search_opportunity d'abord pour obtenir l'identifiant "
                            "exact — un client peut avoir plusieurs opportunités. Un champ omis "
                            "N'écrase PAS la valeur actuelle. ACTION D'ÉCRITURE : proposée pour "
                            "validation humaine avant exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_name": {"type": "string", "description": "Identifiant exact de l'opportunité (obligatoire, ex: CRM-OPP-2026-00003)."},
                    "status": {"type": "string", "description": "Nouveau statut : Open, Quotation, Converted, Lost, Replied ou Closed (optionnel)."},
                    "opportunity_amount": {"type": "number", "description": "Nouveau montant potentiel (optionnel)."},
                },
                "required": ["opportunity_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_quotation",
            "description": "Modifie un devis EXISTANT encore en brouillon (date de validité et/ou "
                            "lignes d'articles). IMPORTANT : appelle TOUJOURS search_quotation "
                            "d'abord pour obtenir l'identifiant exact. Si items est fourni, il "
                            "REMPLACE entièrement les lignes existantes — inclus toutes les lignes "
                            "voulues, pas seulement celles à ajouter. ACTION D'ÉCRITURE : proposée "
                            "pour validation humaine avant exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quotation_name": {"type": "string", "description": "Identifiant exact du devis (obligatoire, ex: SAL-QTN-2026-00011)."},
                    "valid_till": {"type": "string", "description": "Nouvelle date de validité, format AAAA-MM-JJ (optionnel)."},
                    "items": {
                        "type": "array",
                        "description": "Nouvelles lignes d'articles, remplace les lignes existantes (optionnel).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_code": {"type": "string", "description": "Code de l'article existant."},
                                "qty": {"type": "number", "description": "Quantité."},
                                "rate": {"type": "number", "description": "Prix unitaire (optionnel)."},
                            },
                            "required": ["item_code", "qty"],
                        },
                    },
                },
                "required": ["quotation_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_sales_order",
            "description": "Modifie une commande client EXISTANTE encore en brouillon (date de "
                            "livraison et/ou lignes d'articles). IMPORTANT : appelle TOUJOURS "
                            "search_sales_order d'abord pour obtenir l'identifiant exact. Si items "
                            "est fourni, il REMPLACE entièrement les lignes existantes. ACTION "
                            "D'ÉCRITURE : proposée pour validation humaine avant exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sales_order_name": {"type": "string", "description": "Identifiant exact de la commande (obligatoire, ex: SAL-ORD-2026-00010)."},
                    "delivery_date": {"type": "string", "description": "Nouvelle date de livraison, format AAAA-MM-JJ (optionnel)."},
                    "items": {
                        "type": "array",
                        "description": "Nouvelles lignes d'articles, remplace les lignes existantes (optionnel).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_code": {"type": "string", "description": "Code de l'article existant."},
                                "qty": {"type": "number", "description": "Quantité."},
                                "rate": {"type": "number", "description": "Prix unitaire (optionnel)."},
                            },
                            "required": ["item_code", "qty"],
                        },
                    },
                },
                "required": ["sales_order_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_item",
            "description": "Crée un nouvel article dans ERPNext. ACTION D'ÉCRITURE : cette action "
                            "sera proposée à l'utilisateur pour validation humaine avant d'être "
                            "réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string", "description": "Code unique de l'article (obligatoire)."},
                    "item_name": {"type": "string", "description": "Nom de l'article (obligatoire)."},
                    "rate": {"type": "number", "description": "Prix de vente standard (optionnel)."},
                },
                "required": ["item_code", "item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_item",
            "description": "Modifie un article EXISTANT (pas une création) : nom, prix standard, "
                            "ou statut actif/désactivé. IMPORTANT : appelle TOUJOURS search_item "
                            "d'abord pour connaître l'item_code exact et les valeurs actuelles — "
                            "n'invente jamais un item_code. Un champ omis N'écrase PAS la valeur "
                            "actuelle. ACTION D'ÉCRITURE : proposée pour validation humaine avant "
                            "exécution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string", "description": "Code exact de l'article à modifier (obligatoire)."},
                    "item_name": {"type": "string", "description": "Nouveau nom de l'article (optionnel)."},
                    "rate": {"type": "number", "description": "Nouveau prix de vente standard (optionnel)."},
                    "disabled": {"type": "boolean", "description": "true pour désactiver l'article, false pour le réactiver (optionnel)."},
                },
                "required": ["item_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_quotation",
            "description": "Crée un devis pour un client existant, avec une ou plusieurs lignes "
                            "d'articles. Le devis est créé en brouillon (non soumis), une revue "
                            "manuelle dans ERPNext reste nécessaire avant envoi au client. Le client "
                            "et chaque article doivent déjà exister. IMPORTANT : appelle TOUJOURS "
                            "search_item d'abord pour obtenir l'item_code exact de chaque article "
                            "— n'invente JAMAIS un item_code à partir du nom de l'article. ACTION "
                            "D'ÉCRITURE : cette action sera proposée à l'utilisateur pour validation "
                            "humaine avant d'être réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom exact du client existant (obligatoire)."},
                    "items": {
                        "type": "array",
                        "description": "Lignes d'articles du devis (obligatoire, au moins une ligne).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_code": {"type": "string", "description": "Code de l'article existant."},
                                "qty": {"type": "number", "description": "Quantité."},
                                "rate": {"type": "number", "description": "Prix unitaire (optionnel, sinon prix standard de l'article)."},
                            },
                            "required": ["item_code", "qty"],
                        },
                    },
                    "valid_till": {"type": "string", "description": "Date de validité du devis, format AAAA-MM-JJ (optionnel — omets ce paramètre plutôt que de deviner une date ; une valeur par défaut sûre sera utilisée)."},
                },
                "required": ["customer_name", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_sales_order",
            "description": "Crée une commande client pour un client existant, avec une ou plusieurs "
                            "lignes d'articles. La commande est créée en brouillon (non soumise), "
                            "une revue manuelle dans ERPNext reste nécessaire pour qu'elle devienne "
                            "effective. Le client et chaque article doivent déjà exister. IMPORTANT : "
                            "appelle TOUJOURS search_item d'abord pour obtenir l'item_code exact de "
                            "chaque article — n'invente JAMAIS un item_code à partir du nom de "
                            "l'article. ACTION D'ÉCRITURE : cette action sera proposée à l'utilisateur "
                            "pour validation humaine avant d'être réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nom exact du client existant (obligatoire)."},
                    "items": {
                        "type": "array",
                        "description": "Lignes d'articles de la commande (obligatoire, au moins une ligne).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_code": {"type": "string", "description": "Code de l'article existant."},
                                "qty": {"type": "number", "description": "Quantité."},
                                "rate": {"type": "number", "description": "Prix unitaire (optionnel, sinon prix standard de l'article)."},
                            },
                            "required": ["item_code", "qty"],
                        },
                    },
                    "delivery_date": {"type": "string", "description": "Date de livraison souhaitée, format AAAA-MM-JJ (optionnel)."},
                },
                "required": ["customer_name", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_purchase_order",
            "description": "Crée une commande fournisseur pour un fournisseur existant, avec une "
                            "ou plusieurs lignes d'articles. La commande est créée en brouillon (non "
                            "soumise), une revue manuelle dans ERPNext reste nécessaire pour qu'elle "
                            "devienne effective. Le fournisseur et chaque article doivent déjà "
                            "exister. IMPORTANT : appelle TOUJOURS search_item d'abord pour obtenir "
                            "l'item_code exact de chaque article — n'invente JAMAIS un item_code à "
                            "partir du nom de l'article. ACTION D'ÉCRITURE : cette action sera "
                            "proposée à l'utilisateur pour validation humaine avant d'être réellement "
                            "exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Nom exact du fournisseur existant (obligatoire)."},
                    "items": {
                        "type": "array",
                        "description": "Lignes d'articles de la commande (obligatoire, au moins une ligne).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_code": {"type": "string", "description": "Code de l'article existant."},
                                "qty": {"type": "number", "description": "Quantité."},
                                "rate": {"type": "number", "description": "Prix unitaire (optionnel)."},
                            },
                            "required": ["item_code", "qty"],
                        },
                    },
                    "schedule_date": {"type": "string", "description": "Date de réception souhaitée, format AAAA-MM-JJ (optionnel)."},
                },
                "required": ["supplier_name", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_stock",
            "description": "Augmente le stock d'un article existant (entrée de stock / réception, "
                            "impact réel et immédiat après validation — pas un brouillon). Utilise "
                            "cet outil quand l'utilisateur demande d'ajouter, d'augmenter ou de "
                            "recevoir du stock pour un article. IMPORTANT : appelle TOUJOURS "
                            "search_item d'abord pour obtenir l'item_code exact — n'invente JAMAIS "
                            "un item_code à partir du nom de l'article. ACTION D'ÉCRITURE : cette "
                            "action sera proposée à l'utilisateur pour validation humaine avant "
                            "d'être réellement exécutée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string", "description": "Code exact de l'article existant (obligatoire)."},
                    "qty": {"type": "number", "description": "Quantité à ajouter au stock (obligatoire)."},
                    "warehouse": {"type": "string", "description": "Entrepôt de réception (optionnel — un entrepôt par défaut sera utilisé si omis)."},
                    "rate": {"type": "number", "description": "Coût unitaire de la réception (optionnel)."},
                },
                "required": ["item_code", "qty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_summary",
            "description": "Calcule des statistiques agrégées RÉELLES sur les ventes : chiffre "
                            "d'affaires facturé sur la période, nombre de factures/commandes, top "
                            "5 clients par chiffre d'affaires, total des impayés. UTILISE CET OUTIL "
                            "SYSTÉMATIQUEMENT dès qu'on te demande une analyse, une stratégie, un "
                            "conseil, un bilan ou une consolidation sur les ventes — ne demande "
                            "JAMAIS ces chiffres à l'utilisateur, calcule-les toi-même avec cet "
                            "outil, puis construis ton analyse et tes recommandations à partir des "
                            "résultats obtenus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {"type": "integer", "description": "Nombre de jours sur lesquels calculer la période (optionnel, 30 par défaut)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_summary",
            "description": "Calcule des statistiques agrégées RÉELLES sur les achats : dépenses "
                            "facturées sur la période, nombre de factures/commandes, top 5 "
                            "fournisseurs par dépense, total des dettes fournisseurs. UTILISE CET "
                            "OUTIL SYSTÉMATIQUEMENT dès qu'on te demande une analyse, une stratégie, "
                            "un conseil, un bilan ou une consolidation sur les achats — ne demande "
                            "JAMAIS ces chiffres à l'utilisateur, calcule-les toi-même avec cet "
                            "outil, puis construis ton analyse et tes recommandations à partir des "
                            "résultats obtenus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {"type": "integer", "description": "Nombre de jours sur lesquels calculer la période (optionnel, 30 par défaut)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_summary",
            "description": "Calcule des statistiques agrégées RÉELLES sur le stock : nombre "
                            "d'articles actifs, nombre sous le seuil de réapprovisionnement, "
                            "nombre à zéro, valeur totale estimée du stock. UTILISE CET OUTIL "
                            "SYSTÉMATIQUEMENT dès qu'on te demande une analyse, une stratégie, un "
                            "conseil, un bilan ou une consolidation sur le stock/l'inventaire — ne "
                            "demande JAMAIS ces chiffres à l'utilisateur, calcule-les toi-même avec "
                            "cet outil.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_executive_snapshot",
            "description": "Vue exécutive consolidée en un seul appel : ventes/achats des 7 "
                            "derniers jours, impayés, alertes stock. TOUJOURS appeler cet outil "
                            "EN PREMIER pour toute question de l'agent Directeur, avant de "
                            "décider s'il faut approfondir avec consult_agent.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consult_agent",
            "description": "Délègue une question précise à un agent spécialisé qui a accès à "
                            "ses propres outils détaillés. À utiliser quand get_executive_snapshot "
                            "ne suffit pas (détail d'un client, d'un article, d'une commande...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_key": {"type": "string", "description": "commercial, finance, stock, achat ou documents."},
                    "question": {"type": "string", "description": "Question précise en langage naturel."},
                },
                "required": ["agent_key", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Recherche dans les documents indexés (contrats, procédures, "
                            "catalogues, notes internes...) par similarité de sens, pas seulement "
                            "par mot-clé exact. Utilise cet outil pour toute question dont la "
                            "réponse pourrait se trouver dans un document uploadé plutôt que dans "
                            "les données structurées ERPNext (clients, factures, stock...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La question ou le sujet à rechercher dans les documents."},
                    "top_k": {"type": "integer", "description": "Nombre de fragments à retourner (optionnel, 5 par défaut)."},
                },
                "required": ["query"],
            },
        },
    },
]


def execute_tool(tool_name, arguments):
    """Exécute un outil du registre et retourne son résultat (dict)."""
    fn = TOOLS_REGISTRY.get(tool_name)
    if not fn:
        return {"error": f"Outil inconnu : {tool_name}"}
    try:
        return fn(**arguments)
    except Exception as e:
        frappe.log_error(title=f"erp_ai tool error: {tool_name}", message=str(e))
        return {"error": str(e)}