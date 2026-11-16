// Phase 9 - ERPNext AI Platform (erp_ai)
// Dashboard de supervision : usage, santé du système, quotas, alertes.
// Réservé au rôle System Manager (contrôlé aussi côté serveur dans dashboard.py).
//
// EMPLACEMENT SUR LE SERVEUR :
//   apps/erp_ai/erp_ai/erp_ai/page/ai_dashboard/ai_dashboard.js
//   (remplace le contenu existant)
//
// MODIF (section erreurs simplifiée) : plus de tableau technique (nom
// d'outil, message d'erreur brut) — remplacé par une bannière de statut
// simple ("tout va bien" / "X problèmes, contacte le développeur"), pensée
// pour un admin non-technique. Le détail technique reste consultable par
// un développeur directement dans /app/ai-log?status=Error si besoin.

frappe.pages['ai-dashboard'].on_page_load = function(wrapper) {
        const page = frappe.ui.make_app_page({
                parent: wrapper,
                title: 'AI Health',
                single_column: true,
        });
        new AIDashboard(page);
};

class AIDashboard {
        constructor(page) {
                this.page = page;
                this.page.set_primary_action('Actualiser', () => this.load());
                this.render_shell();
                this.load();
        }

        render_shell() {
                this.page.main.html(`
                        <div class="ai-dashboard-container">
                                <div class="ai-kpi-row" style="display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;"></div>

                                <div class="ai-status-banner" style="margin-bottom: 20px;"></div>
                                <div class="ai-section" style="margin-bottom: 20px;">
                                        <div style="font-weight: 600; margin-bottom: 8px;">🧭 Vue exécutive (7 derniers jours)</div>
                                        <div class="ai-snapshot-row" style="display: flex; gap: 12px; flex-wrap: wrap;"></div>
                                </div>
                                <div class="ai-charts-row" style="margin-bottom: 20px;">
                                        <div class="ai-chart-card" style="border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; background: var(--card-bg);">
                                                <div style="font-weight: 600; margin-bottom: 8px;">Messages — 7 derniers jours</div>
                                                <div class="ai-chart-messages"></div>
                                        </div>
                                </div>

                                <div class="ai-section" style="margin-bottom: 20px;">
                                        <div style="font-weight: 600; margin-bottom: 8px;">⏳ Validations en attente</div>
                                        <div class="ai-table-pending"></div>
                                </div>

                                <div class="ai-section" style="margin-bottom: 20px;">
                                        <div style="font-weight: 600; margin-bottom: 8px;">🔔 Alertes envoyées aujourd'hui</div>
                                        <div class="ai-table-alerts"></div>
                                </div>

                                <div class="ai-section" style="margin-bottom: 20px;">
                                        <div style="font-weight: 600; margin-bottom: 8px;">📊 Usage des quotas aujourd'hui</div>
                                        <div class="ai-table-quotas"></div>
                                </div>
                        </div>
                `);

                this.$kpiRow = this.page.main.find('.ai-kpi-row');
                this.$statusBanner = this.page.main.find('.ai-status-banner');
                this.$snapshotRow = this.page.main.find('.ai-snapshot-row');
                this.$chartMessages = this.page.main.find('.ai-chart-messages');
                this.$tablePending = this.page.main.find('.ai-table-pending');
                this.$tableAlerts = this.page.main.find('.ai-table-alerts');
                this.$tableQuotas = this.page.main.find('.ai-table-quotas');
        }

        load() {
                this.$kpiRow.html('<div class="text-muted small">Chargement...</div>');
                frappe.call({
                        method: 'erp_ai.dashboard.get_dashboard_data',
                        callback: (r) => {
                                if (!r.message || r.message.status !== 'ok') {
                                        const err = (r.message && r.message.error) || 'Erreur inconnue';
                                        this.$kpiRow.html(`<div class="text-danger">${frappe.utils.escape_html(err)}</div>`);
                                        return;
                                }
                                this.data = r.message;
                                this.render_kpis();
                                this.render_status_banner();
                                this.render_snapshot();
                                this.render_charts();
                                this.render_pending();
                                this.render_alerts();
                                this.render_quotas();
                        },
                        error: () => {
                                this.$kpiRow.html('<div class="text-danger">Erreur de connexion au serveur.</div>');
                        },
                });
        }

        _kpi_card(label, value, color) {
                return `
                        <div style="
                                flex: 1; min-width: 160px;
                                border: 1px solid var(--border-color);
                                border-radius: 8px;
                                padding: 14px 16px;
                                background: var(--card-bg);
                        ">
                                <div class="text-muted small">${frappe.utils.escape_html(label)}</div>
                                <div style="font-size: 26px; font-weight: 700; color: ${color || 'var(--text-color)'};">${value}</div>
                        </div>
                `;
        }

        render_kpis() {
                const d = this.data;
                this.$kpiRow.html(
                        this._kpi_card('Messages aujourd\'hui', d.messages_today) +
                        this._kpi_card('Utilisateurs actifs aujourd\'hui', d.active_users_today) +
                        this._kpi_card('Validations en attente', d.pending_validations.length, d.pending_validations.length ? 'var(--yellow-600, #b7791f)' : null)
                );
        }

        // Bannière de statut simple, sans détail technique : pensée pour un
        // admin non-technique qui a juste besoin de savoir si tout va bien.
        render_status_banner() {
                const count = this.data.error_count_7d || 0;
                const isOk = count === 0;

                const banner = isOk
                        ? `<div style="
                                        padding: 12px 16px; border-radius: 8px;
                                        background: var(--green-100, #e6f4ea); color: var(--green-700, #1e6b34);
                                        border: 1px solid var(--green-300, #a8dab5);
                                        font-weight: 500;
                                ">✅ Tout fonctionne normalement — aucun problème technique détecté sur les 7 derniers jours.</div>`
                        : `<div style="
                                        padding: 12px 16px; border-radius: 8px;
                                        background: var(--red-100, #fdecea); color: var(--red-700, #a02622);
                                        border: 1px solid var(--red-300, #f3b3ae);
                                        font-weight: 500;
                                ">⚠️ ${count} problème(s) technique(s) détecté(s) sur les 7 derniers jours — contacte le développeur pour vérifier.</div>`;

                this.$statusBanner.html(banner);
        }
        
        render_snapshot() {
                const snap = this.data.executive_snapshot;
                if (!snap || snap.error) {
                        this.$snapshotRow.html(`<div class="text-muted small">${frappe.utils.escape_html((snap && snap.error) || 'Snapshot indisponible.')}</div>`);
                        return;
                }

                const cur = snap.currency || '';
                const fmt = (v) => `${frappe.format(v || 0, { fieldtype: 'Currency' })} ${cur}`;

                this.$snapshotRow.html(
                        this._kpi_card('Chiffre d\'affaires (7j)', fmt(snap.ventes.chiffre_affaires)) +
                        this._kpi_card('Impayés clients', fmt(snap.ventes.impayes_clients), snap.ventes.impayes_clients > 0 ? 'var(--red-600, #c62828)' : null) +
                        this._kpi_card('Dépenses (7j)', fmt(snap.achats.depenses)) +
                        this._kpi_card('Dettes fournisseurs', fmt(snap.achats.dettes_fournisseurs), snap.achats.dettes_fournisseurs > 0 ? 'var(--red-600, #c62828)' : null) +
                        this._kpi_card('Articles sous seuil', snap.stock.articles_sous_seuil, snap.stock.articles_sous_seuil > 0 ? 'var(--yellow-600, #b7791f)' : null) +
                        this._kpi_card('Articles à zéro', snap.stock.articles_a_zero, snap.stock.articles_a_zero > 0 ? 'var(--red-600, #c62828)' : null)
                );
        }
        
        render_charts() {
                const d = this.data;

                const days = [];
                const counts = [];
                const byDay = {};
                (d.messages_last_7_days || []).forEach(row => { byDay[row.day] = row.count; });
                for (let i = 6; i >= 0; i--) {
                        const date = frappe.datetime.add_days(frappe.datetime.now_date(), -i);
                        days.push(frappe.datetime.str_to_user(date).slice(0, 5));
                        counts.push(byDay[date] || 0);
                }

                this.$chartMessages.empty();
                if (typeof frappe.Chart !== 'undefined') {
                        new frappe.Chart(this.$chartMessages[0], {
                                data: {
                                        labels: days,
                                        datasets: [{ name: 'Messages', values: counts }],
                                },
                                type: 'line',
                                height: 220,
                                colors: ['#5e64ff'],
                        });
                } else {
                        this.$chartMessages.html('<div class="text-muted small">Graphique indisponible.</div>');
                }
        }

        _empty_row(colspan, text) {
                return `<tr><td colspan="${colspan}" class="text-muted text-center" style="padding: 12px;">${text}</td></tr>`;
        }

        _table(headers, rowsHtml) {
                return `
                        <table class="table table-bordered" style="margin-bottom: 0;">
                                <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
                                <tbody>${rowsHtml}</tbody>
                        </table>
                `;
        }

        render_pending() {
                const rows = this.data.pending_validations || [];
                const html = rows.length
                        ? rows.map(r => `
                                <tr>
                                        <td><a href="/app/ai-log/${r.name}" target="_blank">${r.name}</a></td>
                                        <td>${frappe.utils.escape_html(r.tool_name)}</td>
                                        <td>${frappe.utils.escape_html(r.user || '')}</td>
                                        <td>${frappe.datetime.comment_when(r.creation)}</td>
                                </tr>
                        `).join('')
                        : this._empty_row(4, 'Aucune action en attente de validation.');

                this.$tablePending.html(this._table(['ID', 'Outil', 'Utilisateur', 'Depuis'], html));
        }

        // Où rediriger selon le type d'alerte : les factures ont une vue liste
        // ERPNext toute faite qu'on peut filtrer directement sur les impayées.
        // Le stock bas n'a pas d'équivalent (comparaison entre deux tables, pas
        // un simple filtre de champ) : on renvoie vers la fiche du log, qui
        // contient le détail structuré (article, entrepôt, seuil) généré au
        // moment de l'alerte.
        _go_to_alert(tool_name, log_name) {
                if (tool_name === 'alert_overdue_sales_invoices') {
                        frappe.set_route('List', 'Sales Invoice', { outstanding_amount: ['>', 0], docstatus: 1 });
                } else if (tool_name === 'alert_overdue_purchase_bills') {
                        frappe.set_route('List', 'Purchase Invoice', { outstanding_amount: ['>', 0], docstatus: 1 });
                } else {
                        // alert_low_stock et tout type futur non mappé explicitement
                        frappe.set_route('Form', 'AI Log', log_name);
                }
        }

        render_alerts() {
                const rows = this.data.alerts_today || [];
                const html = rows.length
                        ? rows.map(r => `
                                <tr class="ai-alert-row" data-tool="${frappe.utils.escape_html(r.tool_name)}" data-log="${frappe.utils.escape_html(r.name)}" style="cursor: pointer;">
                                        <td>${frappe.utils.escape_html(r.tool_name)}</td>
                                        <td>${r.count != null ? r.count : ''}</td>
                                        <td>${frappe.datetime.comment_when(r.creation)}</td>
                                </tr>
                        `).join('')
                        : this._empty_row(3, "Aucune alerte envoyée aujourd'hui.");

                this.$tableAlerts.html(this._table(['Type', 'Nombre concerné', 'Heure'], html));
                this.$tableAlerts.find('.ai-alert-row').on('click', (e) => {
                        const $row = $(e.currentTarget);
                        this._go_to_alert($row.data('tool'), $row.data('log'));
                });
                this.$tableAlerts.find('.ai-alert-row').on('mouseenter', (e) => $(e.currentTarget).css('background', 'var(--bg-color)'));
                this.$tableAlerts.find('.ai-alert-row').on('mouseleave', (e) => $(e.currentTarget).css('background', 'transparent'));
        }

        render_quotas() {
                const rows = this.data.quota_usage_today || [];
                const html = rows.length
                        ? rows.map(r => {
                                const msgOver = r.message_limit && r.message_count >= r.message_limit;
                                const writeOver = r.write_limit && r.write_count >= r.write_limit;
                                return `
                                        <tr>
                                                <td>${frappe.utils.escape_html(r.user)}</td>
                                                <td style="color: ${msgOver ? 'var(--red-600, #c62828)' : 'inherit'}; font-weight: ${msgOver ? '600' : 'normal'};">
                                                        ${r.message_count} / ${r.message_limit || '∞'}
                                                </td>
                                                <td style="color: ${writeOver ? 'var(--red-600, #c62828)' : 'inherit'}; font-weight: ${writeOver ? '600' : 'normal'};">
                                                        ${r.write_count} / ${r.write_limit || '∞'}
                                                </td>
                                        </tr>
                                `;
                        }).join('')
                        : this._empty_row(3, "Aucun message envoyé aujourd'hui.");

                this.$tableQuotas.html(this._table(['Utilisateur', 'Messages', 'Actions d\'écriture'], html));
        }
}