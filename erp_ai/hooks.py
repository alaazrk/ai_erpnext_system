app_name = "erp_ai"
app_title = "Erp Ai"
app_publisher = "hw"
app_description = "ERPNext AI Platform - assistant IA local pour ERPNext"
app_email = "alaa@hw.com"
app_license = "mit"

# ---------------------------------------------------------------------------
# Événements de documents
# ---------------------------------------------------------------------------
# Indexation RAG automatique : dès qu'un AI Document est créé (fichier
# uploadé), il est découpé et indexé sans action manuelle.
doc_events = {
    "AI Document": {
        "after_insert": "erp_ai.rag.auto_index_on_save",
    },
}

# ---------------------------------------------------------------------------
# Tâches planifiées
# ---------------------------------------------------------------------------
# Vérification horaire : n'envoie les alertes (stock bas, factures en retard)
# que si l'heure actuelle correspond à AI Settings.alert_hour.
scheduler_events = {
    "hourly": [
        "erp_ai.scheduled_tasks.run_hourly_check",
    ],
}
