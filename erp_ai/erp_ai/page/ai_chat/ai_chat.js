// Phase 3 (complétée) + Phase 6 - ERPNext AI Platform (erp_ai)
// Interface de chat : historique des conversations, rendu Markdown des
// réponses, formulaire éditable pour les actions d'écriture en attente.
//
// EMPLACEMENT SUR LE SERVEUR :
//   apps/erp_ai/erp_ai/erp_ai/page/ai_chat/ai_chat.js
//   (remplace le contenu existant)

frappe.pages['ai-chat'].on_page_load = function(wrapper) {
        const page = frappe.ui.make_app_page({
                parent: wrapper,
                title: 'AI Chat',
                single_column: true,
        });

        new AIChat(page);
};

class AIChat {
        constructor(page) {
                this.page = page;
                this.conversation = null;
                this.TOOL_LABELS = {
                        create_lead: 'Nouveau lead',
                        create_supplier: 'Nouveau fournisseur',
                        create_customer: 'Nouveau client',
                        create_opportunity: 'Nouvelle opportunité',
            update_opportunity: 'Modifier une opportunité',
            update_quotation: 'Modifier un devis',
            update_sales_order: 'Modifier une commande client',
                        create_item: 'Nouvel article',
            update_item: 'Modifier un article',
                        create_quotation: 'Nouveau devis',
                        create_sales_order: 'Nouvelle commande client',
                        create_purchase_order: 'Nouvelle commande fournisseur',
            update_supplier: 'Modifier un fournisseur',
            update_customer: 'Modifier un client',
                };

                this.setup_page_buttons();
                this.render();
                this.load_agents();
        }

        load_agents() {
                frappe.call({
                        method: 'erp_ai.ollama_client.list_agents',
                        callback: (r) => {
                                this.agents = (r.message && r.message.agents) || [];
                                const $select = this.page.main.find('.ai-agent-select');
                                $select.empty();

                                if (!this.agents.length) {
                                        this.$messages.html('<p class="text-muted">Aucun agent ne t\'est accessible avec ton rôle actuel. Contacte un administrateur.</p>');
                                        return;
                                }

                                this.agents.forEach((a) => {
                                        $select.append(`<option value="${a.key}" title="${frappe.utils.escape_html(a.description)}">${frappe.utils.escape_html(a.label)}</option>`);
                                });

                                // Agent Directeur par défaut si accessible, sinon le premier agent autorisé
                                const hasDirecteur = this.agents.some(a => a.key === 'directeur');
                                const defaultAgent = hasDirecteur ? 'directeur' : this.agents[0].key;
                                $select.val(defaultAgent);
                                this.agent = defaultAgent;
                                this.start_new_conversation();
                        },
                });
        }

        setup_page_buttons() {
                this.page.set_primary_action('+ Nouvelle conversation', () => this.start_new_conversation());
                this.page.add_button('🕓 Historique', () => this.show_history_dialog());
        }

        render() {
                this.page.main.html(`
                        <div class="ai-chat-container" style="max-width: 800px; margin: 0 auto;">
                                <div class="ai-agent-row" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                        <label class="text-muted small" style="margin: 0; white-space: nowrap;">Agent :</label>
                                        <select class="form-control ai-agent-select" style="max-width: 260px;"></select>
                                </div>
                                <div class="ai-chat-title text-muted small" style="margin-bottom: 6px;"></div>
                                <div class="ai-chat-messages" style="
                                        height: 55vh;
                                        overflow-y: auto;
                                        border: 1px solid var(--border-color);
                                        border-radius: 8px;
                                        padding: 16px;
                                        margin-bottom: 12px;
                                        background: var(--card-bg);
                                "></div>
                                <div class="ai-chat-input-row" style="display: flex; gap: 8px;">
                    <textarea class="ai-chat-input form-control" rows="2"
                      placeholder="Écris ta question ici... (Entrée pour envoyer, Maj+Entrée pour une nouvelle ligne)"
                     style="resize: none;"></textarea>
                    <button class="btn btn-default ai-chat-mic" title="Dicter" style="white-space: nowrap;">
                      🎤
                    </button>
                    <button class="btn btn-primary ai-chat-send" style="white-space: nowrap;">
                      Envoyer
                    </button>
                </div>
                `);

                this.$agentSelect = this.page.main.find('.ai-agent-select');
                this.$title = this.page.main.find('.ai-chat-title');
                this.$messages = this.page.main.find('.ai-chat-messages');
                this.$input = this.page.main.find('.ai-chat-input');
                this.$send = this.page.main.find('.ai-chat-send');
        this.$mic = this.page.main.find('.ai-chat-mic');
        this.setup_voice_input();
                this.$status = this.page.main.find('.ai-chat-status');

                this.$send.on('click', () => this.send_message());
                this.$input.on('keydown', (e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                this.send_message();
                        }
                });
                this.$agentSelect.on('change', () => {
                        this.agent = this.$agentSelect.val();
                        // Changer d'agent démarre une nouvelle conversation, pour ne pas
                        // mélanger les contextes/outils de deux domaines différents.
                        this.start_new_conversation();
                });
        }

    setup_voice_input() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        // Navigateur non compatible (Firefox notamment) : bouton désactivé plutôt que caché,
        // pour que l'utilisateur comprenne pourquoi ça ne marche pas.
        this.$mic.prop('disabled', true).attr('title', 'Dictée non supportée sur ce navigateur (utilise Chrome ou Edge).');
        return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.lang = 'fr-FR';
    this.recognition.interimResults = false;
    this.recognition.continuous = false;

    let listening = false;

    this.recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        const current = this.$input.val();
        this.$input.val(current ? `${current} ${transcript}` : transcript);
    };

    this.recognition.onerror = (event) => {
        this.$status.text(`Erreur de dictée : ${event.error}`);
    };

    this.recognition.onstart = () => {
        listening = true;
        this.$mic.addClass('btn-danger').removeClass('btn-default');
        this.$status.text('Écoute en cours...');
    };

    this.recognition.onend = () => {
        listening = false;
        this.$mic.removeClass('btn-danger').addClass('btn-default');
        this.$status.text('');
    };

    this.$mic.on('click', () => {
        if (listening) {
            this.recognition.stop();
        } else {
            this.recognition.start();
        }
    });
    }

        start_new_conversation() {
                this.$messages && this.$messages.empty();
                frappe.call({
                        method: 'erp_ai.ollama_client.create_conversation',
                        args: { title: 'Conversation du ' + frappe.datetime.now_datetime() },
                        callback: (r) => {
                                if (r.message && r.message.status === 'ok') {
                                        this.conversation = r.message.conversation;
                                        this.$title && this.$title.text('Nouvelle conversation');
                                }
                        },
                });
        }

        // Affiche la liste des conversations passées, cliquables pour les recharger
        show_history_dialog() {
                frappe.call({
                        method: 'erp_ai.ollama_client.list_conversations',
                        callback: (r) => {
                                const conversations = (r.message && r.message.conversations) || [];
                                const dialog = new frappe.ui.Dialog({
                                        title: 'Historique des conversations',
                                        size: 'small',
                                });

                                if (!conversations.length) {
                                        dialog.$body.html('<p class="text-muted">Aucune conversation précédente.</p>');
                                } else {
                                        const list = $('<div class="ai-history-list"></div>');
                                        conversations.forEach((c) => {
                                                const row = $(`
                                                        <div class="ai-history-row" style="
                                                                padding: 8px 10px;
                                                                border-radius: 6px;
                                                                cursor: pointer;
                                                                margin-bottom: 4px;
                                                        ">
                                                                <div style="font-weight: 500;">${frappe.utils.escape_html(c.title || c.name)}</div>
                                                                <div class="text-muted small">${frappe.datetime.comment_when(c.started_on)}</div>
                                                        </div>
                                                `);
                                                row.on('mouseenter', () => row.css('background', 'var(--bg-color)'));
                                                row.on('mouseleave', () => row.css('background', 'transparent'));
                                                row.on('click', () => {
                                                        dialog.hide();
                                                        this.load_conversation(c.name, c.title);
                                                });
                                                list.append(row);
                                        });
                                        dialog.$body.html(list);
                                }

                                dialog.show();
                        },
                });
        }

        // Charge et affiche l'historique d'une conversation passée
        load_conversation(conversation, title) {
                frappe.call({
                        method: 'erp_ai.ollama_client.get_conversation_messages',
                        args: { conversation },
                        callback: (r) => {
                                if (!r.message || r.message.status !== 'ok') {
                                        frappe.msgprint('Impossible de charger cette conversation.');
                                        return;
                                }
                                this.conversation = conversation;
                                this.$title.text(title || 'Conversation');
                                this.$messages.empty();
                                (r.message.messages || []).forEach((m) => this.add_message(m.role, m.content));
                        },
                });
        }

        // Rend le texte en Markdown pour les réponses de l'assistant (listes,
        // gras, tableaux...), en texte brut échappé pour les messages utilisateur.
        add_message(role, content) {
                const is_user = role === 'user';
                const renderedContent = is_user
                        ? frappe.utils.escape_html(content)
                        : frappe.markdown(content || '');

                const bubble = $(`
                        <div class="ai-chat-bubble" style="
                                margin-bottom: 12px;
                                display: flex;
                                justify-content: ${is_user ? 'flex-end' : 'flex-start'};
                        ">
                                <div class="ai-bubble-content" style="
                                        max-width: 75%;
                                        padding: 8px 12px;
                                        border-radius: 10px;
                                        background: ${is_user ? 'var(--primary)' : 'var(--bg-color)'};
                                        color: ${is_user ? 'var(--primary-inverse, #fff)' : 'var(--text-color)'};
                                        border: ${is_user ? 'none' : '1px solid var(--border-color)'};
                                        word-wrap: break-word;
                                ">${renderedContent}</div>
                        </div>
                `);
                this.$messages.append(bubble);
                this.$messages.scrollTop(this.$messages[0].scrollHeight);
                return bubble;
        }

        _build_field(key, value) {
                const label = key.replace(/_/g, ' ');
                const isArray = Array.isArray(value);
                const isNumber = typeof value === 'number';

                if (isArray) {
                        return `
                                <div class="ai-field" style="margin-bottom: 8px;">
                                        <label style="font-size: 12px; text-transform: capitalize; color: var(--text-muted); display: block; margin-bottom: 2px;">
                                                ${frappe.utils.escape_html(label)} (JSON)
                                        </label>
                                        <textarea class="form-control ai-field-input" data-key="${key}" data-type="json" rows="3"
                                                style="font-family: monospace; font-size: 12px;"
                                        >${frappe.utils.escape_html(JSON.stringify(value, null, 2))}</textarea>
                                </div>
                        `;
                }

                return `
                        <div class="ai-field" style="margin-bottom: 8px;">
                                <label style="font-size: 12px; text-transform: capitalize; color: var(--text-muted); display: block; margin-bottom: 2px;">
                                        ${frappe.utils.escape_html(label)}
                                </label>
                                <input class="form-control ai-field-input" data-key="${key}" data-type="${isNumber ? 'number' : 'text'}"
                                        type="${isNumber ? 'number' : 'text'}"
                                        value="${frappe.utils.escape_html(value === null || value === undefined ? '' : value)}" />
                        </div>
                `;
        }

        add_pending_action(toolUse) {
                const fieldsHtml = Object.entries(toolUse.arguments)
                        .map(([k, v]) => this._build_field(k, v))
                        .join('');

                const friendlyLabel = this.TOOL_LABELS[toolUse.tool] || 'Nouvelle action';
                const card = $(`
                        <div class="ai-chat-bubble" style="margin-bottom: 12px; display: flex; justify-content: flex-start;">
                                <div class="ai-pending-card" style="
                                        max-width: 90%;
                                        width: 90%;
                                        padding: 12px 14px;
                                        border-radius: 10px;
                                        background: var(--bg-color);
                                        border: 1px solid var(--yellow-400, #f0b429);
                                ">
                                        <div style="font-weight: 600; margin-bottom: 10px;">
                                                📝 ${frappe.utils.escape_html(friendlyLabel)}
                                                <span class="text-muted small" style="font-weight: normal;"> — vérifie / corrige avant de créer</span>
                                        </div>
                                        <div class="ai-pending-fields">${fieldsHtml}</div>
                                        <button class="btn btn-sm btn-success ai-confirm-btn" style="margin-right: 6px; margin-top: 4px;">
                                                ✅ Créer
                                        </button>
                                        <button class="btn btn-sm btn-danger ai-reject-btn" style="margin-top: 4px;">
                                                ❌ Annuler
                                        </button>
                                        <div class="ai-pending-result text-muted small" style="margin-top: 8px;"></div>
                                </div>
                        </div>
                `);

                const $result = card.find('.ai-pending-result');
                const $confirmBtn = card.find('.ai-confirm-btn');
                const $rejectBtn = card.find('.ai-reject-btn');

                $confirmBtn.on('click', () => {
                        const edited = {};
                        let parseError = null;
                        card.find('.ai-field-input').each(function () {
                                const $f = $(this);
                                const key = $f.data('key');
                                const type = $f.data('type');
                                const raw = $f.val();
                                if (type === 'json') {
                                        try {
                                                edited[key] = raw.trim() ? JSON.parse(raw) : [];
                                        } catch (e) {
                                                parseError = `Champ '${key}' : JSON invalide.`;
                                        }
                                } else if (type === 'number') {
                                        edited[key] = raw === '' ? null : Number(raw);
                                } else {
                                        edited[key] = raw === '' ? null : raw;
                                }
                        });

                        if (parseError) {
                                $result.html(`<span style="color: var(--red-600, #c62828);">⚠️ ${frappe.utils.escape_html(parseError)}</span>`);
                                return;
                        }

                        $confirmBtn.prop('disabled', true);
                        $rejectBtn.prop('disabled', true);
                        card.find('.ai-field-input').prop('disabled', true);
                        $result.text('Exécution en cours...');

                        frappe.call({
                                method: 'erp_ai.ollama_client.confirm_action',
                                args: {
                                        validation_id: toolUse.validation_id,
                                        arguments: JSON.stringify(edited),
                                },
                                callback: (r) => {
                                        if (r.message && r.message.status === 'ok') {
                                                $result.html('<span style="color: var(--green-600, #2e7d32);">✅ Action confirmée et exécutée avec succès.</span>');
                                        } else {
                                                const err = (r.message && r.message.result && r.message.result.error) || (r.message && r.message.message) || 'Erreur inconnue';
                                                $result.html(`<span style="color: var(--red-600, #c62828);">⚠️ Erreur : ${frappe.utils.escape_html(err)}</span>`);
                                        }
                                },
                                error: () => {
                                        $result.html('<span style="color: var(--red-600, #c62828);">⚠️ Erreur de connexion.</span>');
                                },
                        });
                });

                $rejectBtn.on('click', () => {
                        $confirmBtn.prop('disabled', true);
                        $rejectBtn.prop('disabled', true);
                        card.find('.ai-field-input').prop('disabled', true);
                        frappe.call({
                                method: 'erp_ai.ollama_client.reject_action',
                                args: { validation_id: toolUse.validation_id },
                                callback: () => {
                                        $result.text('❌ Action annulée.');
                                },
                        });
                });

                this.$messages.append(card);
                this.$messages.scrollTop(this.$messages[0].scrollHeight);
        }

        send_message() {
	const message = this.$input.val().trim();
	if (!message) return;

	this.add_message('user', message);
	this.$input.val('');
	this.$send.prop('disabled', true);
	this.$status.text('L\'assistant réfléchit...');

	// Bulle assistant vide, remplie au fur et à mesure par le streaming
	const streamId = frappe.utils.get_random(10);
	const $bubble = this.add_message('assistant', '');
	const $content = $bubble.find('.ai-bubble-content');
	let streamedText = '';

	const eventName = `erp_ai_stream_${streamId}`;
	const onDelta = (data) => {
		streamedText += data.delta;
		$content.html(frappe.markdown(streamedText));
		this.$messages.scrollTop(this.$messages[0].scrollHeight);
	};
	frappe.realtime.on(eventName, onDelta);

	frappe.call({
		method: 'erp_ai.ollama_client.chat',
		args: {
			message: message,
			conversation: this.conversation,
			agent: this.agent,
			stream_id: streamId,
		},
		callback: (r) => {
			frappe.realtime.off(eventName, onDelta);
			this.$send.prop('disabled', false);
			this.$status.text('');

			if (r.message && r.message.status === 'ok') {
				// Remplace par la version finale du serveur, au cas où un
				// fragment de streaming aurait été perdu en route.
				$content.html(frappe.markdown(r.message.reply || ''));

				const toolsUsed = r.message.tools_used || [];
				toolsUsed.filter(t => t.pending).forEach(t => this.add_pending_action(t));
			} else {
				const err = (r.message && r.message.message) || 'Erreur inconnue';
				$content.html(frappe.utils.escape_html('⚠️ Erreur: ' + err));
			}
		},
		error: () => {
			frappe.realtime.off(eventName, onDelta);
			this.$send.prop('disabled', false);
			this.$status.text('');
			$content.html('⚠️ Erreur de connexion au serveur.');
		},
	});
}
}