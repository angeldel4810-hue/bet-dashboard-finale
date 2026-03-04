window.state = {
    token: localStorage.getItem('token'),
    role: localStorage.getItem('role'),
    odds: [],
    slip: [],
    timer: 60,
    searchQuery: '',
    settings: null
};

window.api = {
    async request(path, options = {}) {
        const headers = { 'Content-Type': 'application/json' };
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

        try {
            const response = await fetch(`/api${path}`, { ...options, headers });
            if (response.status === 401) {
                auth.logout();
                return null;
            }
            return await response.json();
        } catch (e) {
            console.error('API Error:', e);
            return null;
        }
    }
};

window.auth = {
    async login() {
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const res = await api.request('/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });

        if (res && res.access_token) {
            state.token = res.access_token;
            state.role = res.role;
            localStorage.setItem('token', res.access_token);
            localStorage.setItem('role', res.role);
            ui.showDashboard();
            dashboard.init();
        } else {
            document.getElementById('login-error').classList.remove('hidden');
            document.getElementById('login-error').innerText = 'Credenziali non valide';
        }
    },
    logout() {
        state.token = null;
        state.role = null;
        localStorage.clear();
        location.reload();
    }
};

window.ui = {
    showDashboard() {
        document.getElementById('login-page').classList.add('hidden');
        document.getElementById('main-dashboard').classList.remove('hidden');
        if (state.role === 'admin') {
            document.getElementById('nav-admin').classList.remove('hidden');
        }
        this.fetchBalance();
    },
    closeModal() {
        document.getElementById('modal-user').classList.add('hidden');
    },
    toggleExtra(id) {
        const el = document.getElementById(`extra-${id}`);
        if (el) el.classList.toggle('hidden');
    },
    toggleSlip() {
        const dropdown = document.getElementById('slip-dropdown');
        dropdown.classList.toggle('hidden');
    },
    filterMatches() {
        dashboard.renderOdds();
    },
    updateSlipUI() {
        const count = state.slip.length;
        document.getElementById('slip-count').innerText = count;

        const itemsContainer = document.getElementById('slip-items');
        if (count === 0) {
            itemsContainer.innerHTML = '<p style="text-align:center; color:var(--text-secondary)">La schedina è vuota</p>';
            document.getElementById('slip-total-odds').innerText = '1.00';
            this.updatePotentialWin();
            return;
        }

        let totalOdds = 1;
        itemsContainer.innerHTML = state.slip.map((item, idx) => {
            totalOdds *= item.odds;
            return `
                <div style="background:rgba(0,0,0,0.2); padding:10px; border-radius:5px; margin-bottom:10px; font-size:0.8rem;">
                    <div style="display:flex; justify-content:space-between;">
                        <span style="font-weight:bold;">${item.selection}</span>
                        <span style="color:var(--success)">@${item.odds.toFixed(2)}</span>
                    </div>
                    <div style="color:var(--text-secondary)">${item.event}</div>
                    <div style="text-align:right; margin-top:5px;">
                        <button onclick="bets.removeFromSlip(${idx})" style="width:auto; padding:2px 5px; font-size:0.7rem; background:var(--danger)">Rimuovi</button>
                    </div>
                </div>
            `;
        }).join('');

        document.getElementById('slip-total-odds').innerText = totalOdds.toFixed(2);
        this.updatePotentialWin();
    },
    updatePotentialWin() {
        const totalOdds = parseFloat(document.getElementById('slip-total-odds').innerText);
        const amount = parseFloat(document.getElementById('slip-amount').value) || 0;
        const potential = (totalOdds * amount).toFixed(2);
        document.getElementById('slip-potential-win').innerText = `€${potential}`;
    },
    openAllOdds(eventId) {
        const event = state.odds.find(o => o.id === eventId);
        if (!event) return;

        document.getElementById('modal-match-name').innerText = `${event.home_team} vs ${event.away_team}`;
        document.getElementById('modal-match-time').innerText = new Date(event.commence_time).toLocaleString();

        const container = document.getElementById('modal-markets-container');
        const labels = {
            // CALCIO - Mercati Principali
            'h2h': 'Esito Finale 1X2',
            'totals': 'Under/Over (Totali)',
            'btts': 'Goal / No Goal',
            'double_chance': 'Doppia Chance',
            'draw_no_bet': 'Draw No Bet',
            'outrights': 'Vincente Finale',

            // CALCIO - Tempi e Gol
            'h2h_1st_half': 'Risultato 1° Tempo',
            'h2h_2nd_half': 'Risultato 2° Tempo',
            'totals_1st_half': 'Under/Over 1° Tempo',
            'totals_2nd_half': 'Under/Over 2° Tempo',
            'ht_ft': 'Parziale / Finale',
            'correct_score': 'Risultato Esatto',
            'exact_score': 'Risultato Esatto',
            'clean_sheet': 'Clean Sheet (Porta Inviolata)',
            'win_to_nil': 'Vince a Zero',
            'odd_even': 'Pari / Dispari',

            // CALCIO - Handicap e Linee
            'spreads': 'Handicap / Spread',
            'handicaps': 'Handicap Asiatico',
            'alternate_totals': 'Over/Under (Linee Aggiuntive)',
            'alternate_spreads': 'Handicap (Linee Aggiuntive)',
            'handicap_euro': 'Handicap Europeo',

            // CALCIO - Eventi Partita
            'total_corners': 'Totale Calci d\'Angolo',
            'total_cards': 'Totale Cartellini',
            'booking_points': 'Punti Cartellini',

            // CALCIO - Marcatori e Giocatori
            'player_anytime_scorer': 'Marcatore (Sempre)',
            'player_first_scorer': 'Marcatore (Primo)',
            'player_last_scorer': 'Marcatore (Ultimo)',
            'player_shots': 'Tiri Giocatore',
            'player_shots_on_target': 'Tiri in Porta Giocatore',
            'player_assists': 'Assist Giocatore',
            'player_anytime_card': 'Cartellino Giocatore',

            // BASKET
            'points_spread': 'Handicap Punti',
            'points_totals': 'Over/Under Punti',

            // TENNIS
            'set_winner': 'Vincente Set',
            'set_spreads': 'Handicap Set',
            'set_totals': 'Under/Over Set',
            'game_spreads': 'Handicap Game',
            'game_totals': 'Under/Over Game'
        };

        const bookmaker = event.bookmakers[0];
        if (!bookmaker) {
            container.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-secondary)">Dati non disponibili per questo evento.</div>';
            document.getElementById('all-odds-modal').classList.remove('hidden');
            return;
        }

        container.innerHTML = bookmaker.markets
            .filter(m => m.key !== 'h2h_lay') // <--- RIMUOVI BANCA (EXCHANGE)
            .map(m => {
                const marketLabel = labels[m.key] || m.key.toUpperCase();
                const outcomesHtml = m.outcomes.map(o => {
                    let name = o.name;
                    if (m.key === 'btts') {
                        name = (name === 'Yes' ? 'Goal' : 'No Goal');
                    } else if (m.key.includes('totals') && o.point !== undefined) {
                        if (!name.includes(o.point.toString())) {
                            name = `${o.name} ${o.point}`;
                        }
                    } else if (o.description) {
                        name = `${o.description}: ${o.name}`;
                    } else if (o.point !== undefined) {
                        name = `${o.name} (${o.point > 0 ? '+' : ''}${o.point})`;
                    }

                    const isSelected = state.slip.some(s => s.eventId === event.id && s.market === m.key && s.selection === name);

                    return `
                    <div class="price-row ${isSelected ? 'selected' : ''}" style="cursor:pointer" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', '${m.key}', '${name}', ${o.price}); ui.closeAllOdds();">
                        <span>${name}</span>
                        <span class="price-val">${o.price.toFixed(2)}</span>
                    </div>
                `;
                }).join('');

                return `
                <div class="market-group">
                    <h4 style="color:var(--accent); font-size:0.8rem; margin-bottom:10px; text-transform:uppercase;">${marketLabel}</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px;">
                        ${outcomesHtml}
                    </div>
                </div>
            `;
            }).join('');

        document.getElementById('all-odds-modal').classList.remove('hidden');

        document.getElementById('all-odds-modal').classList.remove('hidden');
    },
    closeAllOdds() {
        document.getElementById('all-odds-modal').classList.add('hidden');
    },
    async fetchBalance() {
        const res = await api.request('/user/balance');
        if (res) {
            state.balance = res.balance;
            document.getElementById('user-balance-nav').innerText = `Saldo: €${state.balance.toFixed(2)}`;
        }
    }
};

const router = {
    navigate(section) {
        const sections = ['odds', 'admin', 'mybets'];
        sections.forEach(s => {
            const el = document.getElementById(`section-${s}`);
            if (el) el.classList.add('hidden');
            const navEl = document.getElementById(`nav-${s}`);
            if (navEl) navEl.classList.remove('active');
        });

        const targetEl = document.getElementById(`section-${section}`);
        if (targetEl) targetEl.classList.remove('hidden');
        const targetNav = document.getElementById(`nav-${section}`);
        if (targetNav) targetNav.classList.add('active');

        if (section === 'admin') admin.init();
        if (section === 'mybets') bets.loadHistory();
    }
};

window.dashboard = {
    init() {
        this.fetchOdds();
        // Carichiamo subito le impostazioni per evitare attese nel render
        api.request('/settings').then(s => {
            if (s) state.settings = s;
        });
        setInterval(() => this.updateTimer(), 1000);
    },
    async fetchOdds() {
        const odds = await api.request('/odds');
        if (odds) state.odds = odds;

        if (!state.settings) {
            state.settings = await api.request('/settings');
        }

        this.renderOdds();
        state.timer = 60;
        ui.fetchBalance();
    },
    updateTimer() {
        state.timer--;
        if (state.timer <= 0) this.fetchOdds();
        document.getElementById('update-timer').innerText = `Prossimo aggiornamento: ${state.timer}s`;
    },
    renderOdds() {
        const container = document.getElementById('odds-container');
        if (!container) return;

        const searchInput = document.getElementById('match-search');
        const query = (searchInput?.value || '').toLowerCase();

        const settings = state.settings;
        ui.fetchBalance();
        document.getElementById('update-timer').innerText = `Prossimo aggiornamento: ${state.timer}s`;

        if (state.odds.length === 0) {
            let msg = 'Nessuna partita disponibile.';
            if (settings && settings.odds_source === 'api') {
                msg += ' Controlla la API Key nell\'area Admin o seleziona la modalità Manuale.';
            } else {
                msg += ' Aggiungi delle partite dal pannello di Amministrazione.';
            }
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 4rem;">${msg}</div>`;
            return;
        }

        let filteredOdds = state.odds;
        if (query) {
            filteredOdds = state.odds.filter(event => {
                const h = (event.home_team || '').toLowerCase();
                const a = (event.away_team || '').toLowerCase();
                const s = (event.sport_title || '').toLowerCase();
                return h.includes(query) || a.includes(query) || s.includes(query);
            });
        }

        if (filteredOdds.length === 0) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-secondary);">Nessun match trovato per "${query}".</div>`;
            return;
        }

        container.innerHTML = filteredOdds.map(event => {
            const bookmaker = event.bookmakers[0];
            const h2h = bookmaker?.markets.find(m => m.key === 'h2h');
            const h2h_outcomes = h2h?.outcomes || [];

            const homePrice = h2h_outcomes.find(o => o.name === event.home_team);
            const drawPrice = h2h_outcomes.find(o => ['Draw', 'X', 'Pareggio'].includes(o.name));
            const awayPrice = h2h_outcomes.find(o => o.name === event.away_team);

            const isHomeSel = state.slip.some(s => s.eventId === event.id && s.market === 'h2h' && s.selection === event.home_team);
            const isDrawSel = state.slip.some(s => s.eventId === event.id && s.market === 'h2h' && (s.selection === 'X' || s.selection === 'Pareggio' || s.selection === 'Draw'));
            const isAwaySel = state.slip.some(s => s.eventId === event.id && s.market === 'h2h' && s.selection === event.away_team);

            // MERCATI SECONDARI DIRETTI (G/NG, U/O 2.5)
            const btts = bookmaker?.markets.find(m => m.key === 'btts');
            const goalPrice = btts?.outcomes.find(o => ['Yes', 'Goal'].includes(o.name))?.price;
            const nogoalPrice = btts?.outcomes.find(o => ['No', 'No Goal'].includes(o.name))?.price;

            const totals = bookmaker?.markets.find(m => m.key === 'totals');
            const over25Price = totals?.outcomes.find(o => o.name.includes('Over') && o.point === 2.5)?.price;
            const under25Price = totals?.outcomes.find(o => o.name.includes('Under') && o.point === 2.5)?.price;

            return `
            <div class="odd-card fade-in">
                <div class="sport-tag">${event.sport_title}</div>
                <div class="event-name" title="${event.home_team} vs ${event.away_team}">
                    ${event.home_team} vs ${event.away_team}
                </div>
                <div style="font-size: 0.7rem; color: var(--text-secondary); margin-bottom: 0.8rem;">
                    ${new Date(event.commence_time).toLocaleString()}
                </div>
                
                <div class="main-prices" style="margin-bottom: 8px;">
                    <div class="price-btn ${isHomeSel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', '${event.home_team}', ${homePrice?.price || 0})">
                        <span class="label">1</span>
                        <span class="val">${homePrice?.price.toFixed(2) || '-'}</span>
                    </div>
                    <div class="price-btn ${isDrawSel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', 'Pareggio', ${drawPrice?.price || 0})">
                        <span class="label">X</span>
                        <span class="val">${drawPrice?.price.toFixed(2) || '-'}</span>
                    </div>
                    <div class="price-btn ${isAwaySel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', '${event.away_team}', ${awayPrice?.price || 0})">
                        <span class="label">2</span>
                        <span class="val">${awayPrice?.price.toFixed(2) || '-'}</span>
                    </div>
                </div>

                <div style="display: flex; gap: 5px; margin-bottom: 10px;">
                    <div class="price-btn mini ${goalPrice ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'btts', 'Goal', ${goalPrice || 0})" style="flex:1; padding: 5px;">
                        <span class="label" style="font-size:0.6rem">G</span>
                        <span class="val" style="font-size:0.75rem">${goalPrice?.toFixed(2) || ''}</span>
                    </div>
                    <div class="price-btn mini ${nogoalPrice ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'btts', 'No Goal', ${nogoalPrice || 0})" style="flex:1; padding: 5px;">
                        <span class="label" style="font-size:0.6rem">NG</span>
                        <span class="val" style="font-size:0.75rem">${nogoalPrice?.toFixed(2) || ''}</span>
                    </div>
                    <div class="price-btn mini ${over25Price ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'totals', 'Over 2.5', ${over25Price || 0})" style="flex:1; padding: 5px;">
                        <span class="label" style="font-size:0.6rem">O2.5</span>
                        <span class="val" style="font-size:0.75rem">${over25Price?.toFixed(2) || ''}</span>
                    </div>
                    <div class="price-btn mini ${under25Price ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'totals', 'Under 2.5', ${under25Price || 0})" style="flex:1; padding: 5px;">
                        <span class="label" style="font-size:0.6rem">U2.5</span>
                        <span class="val" style="font-size:0.75rem">${under25Price?.toFixed(2) || ''}</span>
                    </div>
                </div>

                <button class="more-btn" onclick="ui.openAllOdds('${event.id}')" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);">
                   Tutte le Quote (${bookmaker?.markets.length || 0})
                </button>
            </div>
        `;
        }).join('');
    }
};

window.admin = {
    async init() {
        await this.loadSettings();
        this.loadUsers();
        this.loadManualOdds();
        this.loadAllBets();
        this.switchTab('dashboard');
    },
    switchTab(tabName) {
        document.querySelectorAll('.admin-tab-content').forEach(el => el.classList.add('hidden'));
        document.querySelectorAll('.admin-tab').forEach(el => el.classList.remove('active'));

        document.getElementById(`admin-tab-${tabName}`).classList.remove('hidden');
        document.querySelector(`.admin-tab[onclick="admin.switchTab('${tabName}')"]`).classList.add('active');

        if (tabName === 'dashboard') {
            this.loadDashboardKPIs();
        }
    },
    async loadDashboardKPIs() {
        const users = await api.request('/admin/users');
        const bets = await api.request('/admin/bets');

        if (users && bets) {
            document.getElementById('kpi-users').innerText = users.length;

            const totalBalance = users.reduce((sum, u) => sum + u.balance, 0);
            document.getElementById('kpi-balances').innerText = `€${totalBalance.toFixed(2)}`;

            const pendingBets = bets.filter(b => b.status === 'pending');
            const totalExposure = pendingBets.reduce((sum, b) => sum + b.potential_win, 0);
            document.getElementById('kpi-exposure').innerText = `€${totalExposure.toFixed(2)}`;

            const wonBets = bets.filter(b => b.status === 'won');
            const lostBets = bets.filter(b => b.status === 'lost');
            const totalBetAmount = bets.reduce((sum, b) => sum + b.amount, 0);
            const totalPaidOut = wonBets.reduce((sum, b) => sum + b.potential_win, 0);

            const profit = totalBetAmount - totalPaidOut;
            const profitEl = document.getElementById('kpi-profit');
            profitEl.innerText = `€${profit.toFixed(2)}`;
            profitEl.className = `kpi-value ${profit >= 0 ? 'success' : 'danger'}`;
        }
    },
    async loadSettings() {
        const settings = await api.request('/settings');
        if (settings) {
            document.getElementById('setting-overround').value = settings.overround;
            document.getElementById('setting-apikey').value = settings.apikey || '';
            document.getElementById('setting-source').value = settings.odds_source || 'manual';
        }
    },
    async saveSettings() {
        const overround = document.getElementById('setting-overround').value;
        const apikey = document.getElementById('setting-apikey').value;
        const odds_source = document.getElementById('setting-source').value;
        await api.request('/settings', {
            method: 'POST',
            body: JSON.stringify({ overround, apikey, odds_source })
        });
        state.settings = null; // Forza il refresh al prossimo render
        dashboard.fetchOdds();
        alert('Impostazioni salvate!');
    },
    async loadUsers() {
        const users = await api.request('/admin/users');
        if (users) {
            const tableBody = document.getElementById('user-table-body');
            tableBody.innerHTML = users.map(u => `
                <tr>
                    <td>${u.username}</td>
                    <td><span style="color:${u.status === 'blocked' ? 'var(--danger)' : 'var(--success)'};">${u.status}</span></td>
                    <td><span style="color:var(--success); font-weight:bold;">€${u.balance.toFixed(2)}</span></td>
                    <td>
                        <button onclick="admin.openUserDetail(${u.id})" style="width:auto; padding:3px 8px;">Dettagli</button>
                    </td>
                </tr>
            `).join('');
        }
    },
    async openUserDetail(userId) {
        this.currentUserId = userId;
        const detail = await api.request(`/admin/users/${userId}/detail`);
        if (!detail) return;

        // Populate info
        document.getElementById('detail-username').innerText = detail.username;
        document.getElementById('detail-status').innerText = detail.status;
        document.getElementById('detail-status').style.color = detail.status === 'blocked' ? 'var(--danger)' : 'var(--success)';
        document.getElementById('detail-created').innerText = new Date(detail.created_at).toLocaleDateString();
        document.getElementById('detail-balance').innerText = `€${detail.balance.toFixed(2)}`;

        // Populate bets
        const betsContainer = document.getElementById('detail-bets-container');
        if (detail.bets.length === 0) {
            betsContainer.innerHTML = '<p>Nessuna scommessa.</p>';
        } else {
            betsContainer.innerHTML = detail.bets.map(b => `
                <div style="background:rgba(255,255,255,0.05); padding:1rem; border-radius:8px; margin-bottom:1rem; border-left: 4px solid ${b.status === 'won' ? 'var(--success)' : b.status === 'lost' ? 'var(--danger)' : b.status === 'cancelled' ? 'var(--text-secondary)' : 'var(--accent)'}">
                    <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                         <span>€${b.amount.toFixed(2)} -> €${b.potential_win.toFixed(2)}</span>
                    </div>
                    ${b.selections.map(s => `
                        <div style="font-size:0.85rem; margin-bottom:3px; opacity:0.8;">
                            • ${s.home_team} vs ${s.away_team}: <b>${s.selection}</b> @${s.odds.toFixed(2)}
                        </div>
                    `).join('')}
                    <div style="margin-top:0.8rem; display:flex; gap:10px;">
                        ${b.status === 'pending' ? `
                            <button onclick="admin.forceUserBet(${b.id}, 'won')" style="background:var(--success); width:auto; padding:5px 10px;">V</button>
                            <button onclick="admin.forceUserBet(${b.id}, 'lost')" style="background:var(--danger); width:auto; padding:5px 10px;">P</button>
                            <button onclick="admin.forceUserBet(${b.id}, 'cancelled')" style="background:var(--text-secondary); width:auto; padding:5px 10px;">A</button>
                        ` : `<span style="text-transform:uppercase; font-weight:bold;">${b.status}</span>`}
                    </div>
                </div>
            `).join('');
        }

        // Populate transactions
        const txContainer = document.getElementById('detail-transactions-container');
        if (detail.transactions.length === 0) {
            txContainer.innerHTML = '<p>Nessuna transazione.</p>';
        } else {
            txContainer.innerHTML = detail.transactions.map(t => `
                <div style="border-bottom: 1px solid var(--border-color); padding: 8px 0; display: flex; justify-content: space-between;">
                    <div>
                        <div style="font-weight: bold; color: ${t.amount >= 0 ? 'var(--success)' : 'var(--danger)'}">
                            ${t.amount >= 0 ? '+' : ''}${t.amount.toFixed(2)}
                        </div>
                        <div style="color: var(--text-secondary); font-size: 0.75rem;">${t.type} - ${t.reason || ''}</div>
                    </div>
                    <div style="text-align: right;">
                        <div>€${t.balance_after.toFixed(2)}</div>
                        <div style="color: var(--text-secondary); font-size: 0.75rem;">${new Date(t.timestamp).toLocaleDateString()}</div>
                    </div>
                </div>
            `).join('');
        }

        document.getElementById('user-table-body').closest('div.admin-section').classList.add('hidden');
        document.getElementById('admin-user-detail').classList.remove('hidden');
    },
    closeUserDetail() {
        document.getElementById('admin-user-detail').classList.add('hidden');
        document.getElementById('user-table-body').closest('div.admin-section').classList.remove('hidden');
        this.currentUserId = null;
        this.loadUsers();
    },
    async toggleUserBlock() {
        if (!this.currentUserId) return;
        const detail = await api.request(`/admin/users/${this.currentUserId}/detail`);
        const newStatus = detail.status === 'blocked' ? 'active' : 'blocked';
        await api.request(`/admin/users/${this.currentUserId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status: newStatus })
        });
        this.openUserDetail(this.currentUserId);
    },
    async changeUserPassword() {
        if (!this.currentUserId) return;
        const newPassword = document.getElementById('detail-new-password').value;
        if (!newPassword || newPassword.length < 4) {
            alert("La password deve essere lunga almeno 4 caratteri.");
            return;
        }
        if (!confirm("Sei sicuro di voler cambiare la password a questo utente?")) return;

        const res = await api.request(`/admin/users/${this.currentUserId}/password`, {
            method: 'POST',
            body: JSON.stringify({ password: newPassword })
        });

        if (res) {
            alert("Password cambiata con successo!");
            document.getElementById('detail-new-password').value = '';
        }
    },
    async logBalanceAdjustment(amount, reason = "Manual Adjustment") {
        if (!this.currentUserId) return;
        if (!amount || isNaN(amount)) return alert("Importo non valido");
        await api.request('/admin/balance', {
            method: 'POST',
            body: JSON.stringify({ user_id: this.currentUserId, amount: amount, reason: reason })
        });
        this.openUserDetail(this.currentUserId);
    },
    detailAdjustBalance(multiplier) {
        const val = parseFloat(document.getElementById('detail-amount').value);
        if (isNaN(val) || val <= 0) return alert("Inserisci un importo valido");
        const reason = document.getElementById('detail-reason').value || "Manual Adjust";
        this.logBalanceAdjustment(val * multiplier, reason);
        document.getElementById('detail-amount').value = '';
        document.getElementById('detail-reason').value = '';
    },
    async detailSetBalance() {
        const val = parseFloat(document.getElementById('detail-amount').value);
        if (isNaN(val) || val < 0) return alert("Inserisci un importo valido per il saldo");
        const reason = document.getElementById('detail-reason').value || "Set Exact Balance";
        const detail = await api.request(`/admin/users/${this.currentUserId}/detail`);
        const diff = val - detail.balance;
        this.logBalanceAdjustment(diff, reason);
        document.getElementById('detail-amount').value = '';
        document.getElementById('detail-reason').value = '';
    },
    async detailResetBalance() {
        if (!confirm("Sicuro di voler azzerare il saldo dell'utente?")) return;
        const detail = await api.request(`/admin/users/${this.currentUserId}/detail`);
        const diff = -detail.balance;
        const reason = document.getElementById('detail-reason').value || "Reset Balance to 0";
        this.logBalanceAdjustment(diff, reason);
    },
    async forceUserBet(betId, status) {
        if (!confirm(`Sei sicuro di segnare questa giocata come ${status.toUpperCase()}?`)) return;
        const res = await api.request('/admin/resolve-bet', {
            method: 'POST',
            body: JSON.stringify({ bet_id: betId, status: status })
        });
        if (res) {
            this.openUserDetail(this.currentUserId);
            this.loadAllBets(); // Keep global list updated
            ui.fetchBalance(); // Refresh balance for admin if needed
        }
    },
    async loadAllBets() {
        const bets = await api.request('/admin/all-bets');
        if (bets) {
            const container = document.getElementById('admin-bets-container');
            container.innerHTML = bets.map(b => `
                <div style="background:rgba(255,255,255,0.05); padding:1rem; border-radius:8px; margin-bottom:1rem; border-left: 4px solid ${b.status === 'won' ? 'var(--success)' : b.status === 'lost' ? 'var(--danger)' : 'var(--accent)'}">
                    <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                        <span style="font-weight:bold; color:var(--accent)">Giocata di: ${b.username}</span>
                        <span>€${b.amount.toFixed(2)} -> €${b.potential_win.toFixed(2)}</span>
                    </div>
                    ${b.selections.map(s => `
                        <div style="font-size:0.85rem; margin-bottom:3px; opacity:0.8;">
                            • ${s.home_team} vs ${s.away_team}: <b>${s.selection}</b> @${s.odds.toFixed(2)}
                        </div>
                    `).join('')}
                    <div style="margin-top:0.8rem; display:flex; gap:10px;">
                        ${b.status === 'pending' ? `
                            <button onclick="admin.resolveBet(${b.id}, 'won')" style="background:var(--success); width:auto; padding:5px 15px;">Vincente</button>
                            <button onclick="admin.resolveBet(${b.id}, 'lost')" style="background:var(--danger); width:auto; padding:5px 15px;">Perdente</button>
                        ` : `<span style="text-transform:uppercase; font-weight:bold;">${b.status === 'won' ? 'VINTA ✅' : 'PERSA ❌'}</span>`}
                    </div>
                </div>
            `).join('');
        }
    },
    async resolveBet(betId, status) {
        if (!confirm(`Sei sicuro di segnare questa giocata come ${status.toUpperCase()}?`)) return;
        const res = await api.request('/admin/resolve-bet', {
            method: 'POST',
            body: JSON.stringify({ bet_id: betId, status: status })
        });
        if (res) {
            this.loadAllBets();
            ui.fetchBalance(); // Refresh balance for the user whose bet was resolved
        }
    },
    showAddUserModal() {
        document.getElementById('modal-user').classList.remove('hidden');
    },
    async createUser() {
        const username = document.getElementById('new-username').value;
        const password = document.getElementById('new-password').value;
        await api.request('/admin/users', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        ui.closeModal();
        this.loadUsers();
    },
    async deleteUser(id) {
        if (confirm('Sei sicuro di voler eliminare questo utente?')) {
            await api.request(`/admin/users/${id}`, { method: 'DELETE' });
            this.loadUsers();
        }
    },
    async loadManualOdds() {
        const odds = await api.request('/odds');
        const tbody = document.getElementById('manual-odds-table-body');
        const settings = await api.request('/settings');

        if (settings.odds_source !== 'manual') {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center">Sorgente impostata su API Live. Cambia in Manuale per gestire qui.</td></tr>';
            return;
        }

        if (odds) {
            tbody.innerHTML = odds.map(o => `
                <tr>
                    <td>${o.home_team} vs ${o.away_team}</td>
                    <td>${o.sport_title}</td>
                    <td>${o.bookmakers[0].markets[0].outcomes.map(out => `${out.name}: ${out.price}`).join(' | ')}</td>
                    <td>
                        <button onclick="admin.deleteManualOdd(${o.id})" style="width: auto; padding: 5px 10px; background: var(--danger);">Elimina</button>
                    </td>
                </tr>
            `).join('');
        }
    },
    async addManualOdd() {
        const data = {
            sport_title: document.getElementById('m-sport').value,
            home_team: document.getElementById('m-home').value,
            away_team: document.getElementById('m-away').value,
            commence_time: document.getElementById('m-time').value,
            price_home: parseFloat(document.getElementById('m-p1').value),
            price_draw: parseFloat(document.getElementById('m-px').value) || null,
            price_away: parseFloat(document.getElementById('m-p2').value),
            price_over: parseFloat(document.getElementById('m-over').value) || null,
            price_under: parseFloat(document.getElementById('m-under').value) || null,
            price_goal: parseFloat(document.getElementById('m-goal').value) || null,
            price_nogoal: parseFloat(document.getElementById('m-nogoal').value) || null
        };

        await api.request('/admin/manual-odds', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        alert('Partita aggiunta!');
        this.loadManualOdds();
    },
    async deleteManualOdd(id) {
        await api.request(`/admin/manual-odds/${id}`, { method: 'DELETE' });
        this.loadManualOdds();
    }
};

window.bets = {
    addToSlip(eventId, event, market, selection, odds) {
        if (state.slip.some(s => s.eventId === eventId)) {
            // Se la selezione è identica, la rimuoviamo (toggle)
            const sameIdx = state.slip.findIndex(s => s.eventId === eventId && s.market === market && s.selection === selection);
            if (sameIdx !== -1) {
                this.removeFromSlip(sameIdx);
                return;
            }
            alert('Hai già una selezione per questa partita!');
            return;
        }
        state.slip.push({ eventId, event, market, selection, odds });
        ui.updateSlipUI();
        dashboard.renderOdds();
    },
    removeFromSlip(index) {
        state.slip.splice(index, 1);
        ui.updateSlipUI();
        dashboard.renderOdds();
    },
    async placeBet() {
        const amount = parseFloat(document.getElementById('slip-amount').value);
        if (!amount || amount <= 0) return alert('Inserisci un importo valido');
        if (amount < 2) { // Minimum bet amount
            alert('L\'importo minimo è €2.00');
            return;
        }
        if (amount > state.balance) return alert('Saldo insufficiente!');

        const totalOdds = parseFloat(document.getElementById('slip-total-odds').innerText);
        const potentialWin = parseFloat((totalOdds * amount).toFixed(2));

        const betData = {
            amount: amount,
            total_odds: totalOdds,
            potential_win: potentialWin,
            selections: state.slip.map(s => ({
                event_id: s.eventId,
                market: s.market,
                selection: s.selection,
                odds: s.odds,
                home_team: s.event.split(' vs ')[0],
                away_team: s.event.split(' vs ')[1]
            }))
        };

        const res = await api.request('/bets', {
            method: 'POST',
            body: JSON.stringify(betData)
        });

        if (res) {
            alert(res.message);
            state.slip = [];
            ui.updateSlipUI();
            ui.toggleSlip();
        }
    },
    async loadHistory() {
        const history = await api.request('/my-bets');
        const container = document.getElementById('my-bets-container');
        if (history) {
            container.innerHTML = history.map(bet => `
                <div style="background:var(--card-bg); border:1px solid var(--border-color); border-radius:12px; padding:1.5rem; margin-bottom:1.5rem;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:1rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:0.5rem;">
                        <span style="color:var(--text-secondary)">ID: #${bet.id} | ${new Date(bet.created_at).toLocaleString()}</span>
                        <span style="font-weight:bold; color:${bet.status === 'won' ? 'var(--success)' : bet.status === 'lost' ? 'var(--danger)' : 'var(--accent)'}">${bet.status.toUpperCase()}</span>
                    </div>
                    ${bet.selections.map(s => `
                        <div style="margin-bottom:8px; font-size:0.9rem;">
                            <b>${s.selection}</b> <span style="color:var(--text-secondary)">@${s.odds.toFixed(2)}</span><br>
                            ${s.home_team} vs ${s.away_team} (${s.market})
                        </div>
                    `).join('')}
                    <div style="margin-top:1rem; display:flex; justify-content:space-between; font-weight:bold;">
                        <span>Importo: €${bet.amount.toFixed(2)}</span>
                        <span>Potential Win: €${bet.potential_win.toFixed(2)}</span>
                    </div>
                </div>
            `).join('');
        }
    }
};

// Start
if (state.token) {
    ui.showDashboard();
    dashboard.init();
}
