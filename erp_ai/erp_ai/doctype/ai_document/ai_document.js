// Phase 10 - ERPNext AI Platform (erp_ai)
// Bouton "Indexer" sur la fiche AI Document : relance manuellement
// l'indexation (utile si le fichier a été remplacé, car le hook after_insert
// ne se redéclenche pas sur une simple modification).
//
// NOTE : à l'origine ce code était un Client Script créé dans l'interface
// ERPNext (/app/client-script). Il est maintenant livré avec l'app. Si le
// Client Script existe encore sur ton site, désactive-le pour éviter d'avoir
// deux boutons "Indexer".

frappe.ui.form.on('AI Document', {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button('🔄 Indexer', () => {
			frappe.call({
				method: 'erp_ai.rag.process_document',
				args: { document_name: frm.doc.name },
				freeze: true,
				freeze_message: 'Indexation en cours...',
				callback: (r) => {
					if (r.message && r.message.status === 'ok') {
						frappe.msgprint(`✅ ${r.message.chunks_created} fragment(s) créé(s).`);
						frm.reload_doc();
					} else {
						frappe.msgprint(`⚠️ Erreur : ${(r.message && r.message.error) || 'inconnue'}`);
					}
				},
			});
		});
	},
});
