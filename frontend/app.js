const state = {
    token: localStorage.getItem('token'),
    role: localStorage.getItem('role'),
    odds: [],
    slip: [],
    timer: 60,
    searchQuery: '',
    settings: null,
    crash: {
        ws: null,
        status: 'waiting',
        multiplier: 1.0,
        history: [],
        betting: false,
        activeBet: null // { id, amount }
    },
    blackjack: {
        game_id: null,
        player_hand: [],
        dealer_hand: [],
        player_score: 0,
        dealer_score: 0,
        status: null,
        bet: 0
    },
    sette_mezzo: {
        game_id: null,
        player_hand: [],
        dealer_hand: [],
        player_score: 0,
        dealer_score: 0,
        status: 'betting',
        bet: 0
    },
    virtual: {
        status: 'BETTING',
        timeLeft: 0,
        currentMatchday: 0,
        matches: [],
        standings: [],
        lastFetch: 0,
        polling: null,
        clock: 0
    }
};

window.api = {
    async request(path, options = {}) {
        const headers = { 'Content-Type': 'application/json' };
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
        try {
            const response = await fetch(`/api${path}`, { ...options, headers });
            if (response.status === 401) { auth.logout(); return null; }
            const data = await response.json();
            if (!response.ok) {
                alert(data?.detail || data?.error || 'Errore del server');
                return null;
            }
            return data;
        } catch (e) {
            console.error('API Error:', e);
            alert('Errore di connessione al server');
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
        // Mostra navbar mobile
        const mobileNav = document.getElementById('mobile-nav');
        if (mobileNav) mobileNav.classList.add("active");
        if (state.role === 'admin') {
            document.getElementById('nav-admin').classList.remove('hidden');
            const mobAdmin = document.getElementById('mob-nav-admin');
            if (mobAdmin) mobAdmin.classList.remove('hidden');
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
        const sections = ['odds', 'admin', 'mybets', 'casino', 'crash', 'blackjack', 'sette-mezzo', 'baccarat', 'virtual'];
        sections.forEach(s => {
            const el = document.getElementById(`section-${s}`);
            if (el) el.classList.add('hidden');
            const navEl = document.getElementById(`nav-${s}`);
            if (navEl) navEl.classList.remove('active');

            const mobNavEl = document.getElementById(`mob-nav-${s}`);
            if (mobNavEl) mobNavEl.classList.remove('active');
        });

        const targetEl = document.getElementById(`section-${section}`);
        if (targetEl) targetEl.classList.remove('hidden');

        // Mappa per accendere il link corretto nel menu
        const navMap = {
            'odds': 'nav-odds',
            'admin': 'nav-admin',
            'mybets': 'nav-mybets',
            'casino': 'nav-casino',
            'crash': 'nav-casino',
            'blackjack': 'nav-casino',
            'sette-mezzo': 'nav-casino',
            'virtual': 'nav-casino'
        };
        // Mappa mobile nav
        const mobNavMap = {
            'odds': 'mob-nav-odds',
            'admin': 'mob-nav-admin',
            'mybets': 'mob-nav-mybets',
            'casino': 'mob-nav-casino',
            'crash': 'mob-nav-casino',
            'blackjack': 'mob-nav-casino',
            'virtual': 'mob-nav-casino'
        };

        const targetNavId = navMap[section];
        const targetNav = document.getElementById(targetNavId);
        if (targetNav) targetNav.classList.add('active');

        const targetMobNavId = mobNavMap[section];
        const targetMobNav = document.getElementById(targetMobNavId);
        if (targetMobNav) targetMobNav.classList.add('active');

        if (section === 'admin') admin.init();
        if (section === 'mybets') bets.loadHistory();
        if (section === 'crash') crash.init();
        if (section === 'virtual') { virtual.init(); if (window.innerWidth <= 600) virtual.applyMobileLayout(); }
    }
};

window.setteMezzo = {
    async deal() {
        const amountInput = document.getElementById('sm-bet-amount');
        const rawVal = amountInput.value.replace(',', '.');
        const bet = parseFloat(rawVal);
        if (isNaN(bet) || bet < 0.20) return alert("Scommessa minima €0.20");
        if (bet > state.balance) return alert("Saldo insufficiente");

        const res = await api.request('/sette-mezzo/deal', {
            method: 'POST',
            body: JSON.stringify({ bet })
        });

        if (res) {
            state.sette_mezzo = { ...state.sette_mezzo, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        }
    },
    async hit() {
        if (state.sette_mezzo.status !== 'playing') return;
        const res = await api.request('/sette-mezzo/hit', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.sette_mezzo.game_id })
        });
        if (res) {
            state.sette_mezzo = { ...state.sette_mezzo, ...res };
            this.updateUI();
            if (res.status === 'bust') {
                this._handleEndAlert(res);
            }
        }
    },
    async stand() {
        if (state.sette_mezzo.status !== 'playing') return;
        const res = await api.request('/sette-mezzo/stand', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.sette_mezzo.game_id })
        });
        if (res) {
            state.sette_mezzo = { ...state.sette_mezzo, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        }
    },
    _handleEndAlert(res) {
        if (res.status === 'win') setTimeout(() => alert("HAI VINTO!"), 500);
        else if (res.status === 'win_natural') setTimeout(() => alert("7 e Mezzo Naturale! Hai Mangiato il banco!"), 500);
        else if (res.status === 'loss') setTimeout(() => alert("Il Banco vince."), 500);
        else if (res.status === 'push') setTimeout(() => alert("Pareggio (Push). La tua puntata è stata rimborsata."), 500);
        else if (res.status === 'bust') setTimeout(() => alert("Hai sballato!"), 500);
    },
    updateUI() {
        const sm = state.sette_mezzo;

        const makeCard = (c) => {
            const isMatta = c.matta;
            const rank = c.rank;
            const suitStr = c.suit;

            let suitEmj = suitStr;
            let color = '#333';
            if (suitStr === 'Denari') { suitEmj = '🪙'; color = '#d4af37'; }
            else if (suitStr === 'Coppe') { suitEmj = '🏆'; color = '#d32f2f'; }
            else if (suitStr === 'Bastoni') { suitEmj = '🏏'; color = '#388e3c'; }
            else if (suitStr === 'Spade') { suitEmj = '⚔️'; color = '#1976d2'; }

            if (isMatta) suitEmj = '★';

            const bgColor = isMatta ? 'linear-gradient(135deg, #ffd700, #ff8c00)' : '#f8f1e5'; // Un bianco antico/panna
            const bdColor = isMatta ? '#b8860b' : color;

            const div = document.createElement('div');
            div.className = 'card-item fade-in';
            div.style.cssText = `width: 70px; height: 100px; background: ${bgColor}; border-radius: 8px; border: 2px solid ${bdColor}; color: ${color}; flex-shrink: 0; display: flex; flex-direction: column; justify-content: space-between; padding: 5px; font-weight: bold; position: relative; box-shadow: 0 5px 15px rgba(0,0,0,0.3); font-family: 'Times New Roman', serif;`;

            if (rank === '?') {
                // Carta coperta
                div.style.background = 'linear-gradient(135deg, #2b3a55, #1d2538)';
                div.style.color = '#fff';
                div.style.border = '2px solid #5a7bba';
                div.innerHTML = `<div style="font-size: 2rem; align-self: center; margin-top: 20px;">?</div>`;
            } else {
                div.innerHTML = `<div style="font-size: 1.1rem; line-height: 1;">${rank}</div><div style="font-size: 2rem; align-self: center;">${suitEmj}</div><div style="font-size: 1.1rem; line-height: 1; transform: rotate(180deg);">${rank}</div>`;
            }
            return div;
        };

        const cardDrawer = (cards, containerId) => {
            const container = document.getElementById(containerId);
            const lastGameId = container.dataset.gameId;
            const isNewGame = lastGameId !== String(sm.game_id);

            let existingCount = container.querySelectorAll('.card-item').length;
            if (isNewGame) {
                existingCount = 0;
                container.dataset.gameId = String(sm.game_id);
                container.innerHTML = '';
            }

            if (existingCount === cards.length) return;

            let i = existingCount;
            const drawNext = () => {
                if (i >= cards.length) return;

                const cardEl = makeCard(cards[i]);
                cardEl.classList.add('dealt-card');
                container.appendChild(cardEl);

                i++;
                if (i < cards.length) setTimeout(drawNext, 400); // 400ms delay per carta
            };
            drawNext();
        };

        cardDrawer(sm.dealer_hand, 'sm-dealer-cards');
        cardDrawer(sm.player_hand, 'sm-player-cards');

        document.getElementById('sm-player-score').innerText = sm.player_score || 0;
        document.getElementById('sm-dealer-score').innerText = sm.dealer_score || '?';

        // Attiva/disattiva controlli
        const cStart = document.getElementById('sm-controls-start');
        const cAct = document.getElementById('sm-controls-action');

        if (sm.status === 'playing') {
            cStart.classList.add('hidden');
            cAct.classList.remove('hidden');
        } else {
            cStart.classList.remove('hidden');
            cAct.classList.add('hidden');
        }

        const msg = document.getElementById('sm-game-message');
        if (sm.status === 'win') msg.innerText = 'HAI VINTO!';
        else if (sm.status === 'win_natural') msg.innerText = '7 E MEZZO NATURALE!';
        else if (sm.status === 'loss') msg.innerText = 'IL BANCO VINCE';
        else if (sm.status === 'bust') msg.innerText = 'SBALLATO!';
        else if (sm.status === 'push') msg.innerText = 'PAREGGIO (PUSH)';
        else msg.innerText = 'PIAZZA LA TUA PUNTATA';
    }
};

window.blackjack = {
    async deal() {
        const amountInput = document.getElementById('bj-bet-amount');
        const rawVal = amountInput.value.replace(',', '.');
        const bet = parseFloat(rawVal);
        if (isNaN(bet) || bet < 0.20) return alert("Scommessa minima €0.20");
        if (bet > state.balance) return alert("Saldo insufficiente");

        const res = await api.request('/blackjack/deal', {
            method: 'POST',
            body: JSON.stringify({ bet })
        });

        if (res) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        }
    },
    async hit() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/hit', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            if (res.status === 'bust') {
                this._handleEndAlert(res);
            }
        }
    },
    async stand() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/stand', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        }
    },
    async split() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/split', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res && !res.error) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        } else if (res && res.error) {
            alert(res.error);
        }
    },
    async doubleDown() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/double', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res && !res.error) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        } else if (res && res.error) {
            alert(res.error);
        }
    },
    async insurance() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/insurance', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res && !res.error) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            if (res.insurance_payout) alert("Assicurazione vinta! +" + res.insurance_payout + "€");
            this._handleEndAlert(res);
        } else if (res && res.error) {
            alert(res.error);
        }
    },
    async skipInsurance() {
        if (state.blackjack.status !== 'playing') return;
        const res = await api.request('/blackjack/skip_insurance', {
            method: 'POST',
            body: JSON.stringify({ game_id: state.blackjack.game_id })
        });
        if (res && !res.error) {
            state.blackjack = { ...state.blackjack, ...res };
            this.updateUI();
            ui.fetchBalance();
            this._handleEndAlert(res);
        } else if (res && res.error) {
            alert(res.error);
        }
    },
    _handleEndAlert(res) {
        if (res.status === 'win') setTimeout(() => alert("HAI VINTO!"), 1800);
        else if (res.status === 'win_bj') setTimeout(() => alert("BLACKJACK! Hai vinto!"), 1800);
        else if (res.status === 'loss') setTimeout(() => alert("Il Banco vince."), 1800);
        else if (res.status === 'push') setTimeout(() => alert("Pareggio."), 1800);
        else if (res.status === 'split_end') setTimeout(() => alert("Partita SPLIT terminata. Totale vinto: " + (res.payout || 0) + "€"), 1800);
        else if (res.status === 'bust') setTimeout(() => alert("Hai sballato!"), 1800);
    },
    updateUI() {
        const bj = state.blackjack;

        const makeCard = (c) => {
            const color = c.suit === '\u2665' || c.suit === '\u2666' ? 'red' : 'black';
            const div = document.createElement('div');
            div.className = 'card-item';
            div.style.cssText = `width: 70px; height: 100px; background: white; border-radius: 8px; border: 2px solid #333; color: ${color}; flex-shrink: 0; display: flex; flex-direction: column; justify-content: space-between; padding: 5px; font-weight: bold; position: relative; box-shadow: 0 5px 15px rgba(0,0,0,0.3);`;
            div.innerHTML = `<div style="font-size: 1rem; line-height: 1;">${c.rank}</div><div style="font-size: 2rem; align-self: center;">${c.suit}</div><div style="font-size: 1rem; line-height: 1; transform: rotate(180deg);">${c.rank}</div>`;
            return div;
        };

        const cardHelper = (cards, containerId, forceRedraw = false, startDelay = 0) => {
            const container = document.getElementById(containerId);
            const lastGameId = container.dataset.gameId;
            const isNewGame = lastGameId !== String(bj.game_id);

            if (isNewGame) {
                container.innerHTML = '';
                container.dataset.gameId = String(bj.game_id);
            }

            let existingNodes = Array.from(container.children);
            let existingCount = existingNodes.length;

            if (!isNewGame && forceRedraw && existingCount > 1 && cards.length > 1) {
                // Flip the dealer's face-down card at index 1 in-place without clearing the whole container
                const newSecondCard = makeCard(cards[1]);
                container.replaceChild(newSecondCard, existingNodes[1]);
            }

            if (existingCount === cards.length && !isNewGame) return;

            let i = existingCount;
            const drawNext = () => {
                if (i >= cards.length) return;

                const div = makeCard(cards[i]);
                div.classList.add('dealt-card');
                container.appendChild(div);

                i++;
                if (i < cards.length) setTimeout(drawNext, 400);
            };

            if (isNewGame && startDelay > 0) setTimeout(drawNext, startDelay);
            else drawNext();
        };

        // When game is over, force-redraw dealer hand to reveal hidden card
        const gameOver = ['win', 'loss', 'push', 'bust', 'win_bj', 'split_end'].includes(bj.status);
        const isInitialDeal = bj.status === 'playing' && bj.player_hand && bj.player_hand.length === 2;

        cardHelper(bj.player_hand, 'bj-player-cards', false, 0);
        cardHelper(bj.dealer_hand, 'bj-dealer-cards', gameOver, isInitialDeal ? 200 : 0);

        document.getElementById('bj-player-score').innerText = `Punteggio: ${bj.player_score}`;
        document.getElementById('bj-dealer-score').innerText = `Punteggio: ${bj.dealer_score}`;

        const statusEl = document.getElementById('bj-status');
        const betControls = document.getElementById('bj-bet-controls');
        const actionControls = document.getElementById('bj-action-controls');
        const splitBtn = document.getElementById('bj-split-btn');

        // Split Button visibility
        if (bj.status === 'playing' && bj.player_hand && bj.player_hand.length === 2 && !bj.is_split && (bj.player_hand[0].value === bj.player_hand[1].value || bj.player_hand[0].rank === bj.player_hand[1].rank)) {
            splitBtn.classList.remove('hidden');
        } else {
            if (splitBtn) splitBtn.classList.add('hidden');
        }

        if (bj.status === 'playing') {
            if (bj.is_split) {
                statusEl.innerText = `SPLIT - Gioca Mano ${bj.active_hand_num}`;
            } else {
                statusEl.innerText = 'Tocca a te!';
            }
            betControls.classList.add('hidden');
            actionControls.classList.remove('hidden');
        } else {
            betControls.classList.remove('hidden');
            actionControls.classList.add('hidden');

            if (bj.is_split && bj.status === 'split_end') {
                statusEl.innerText = `FINE SPLIT (Premi Gioca)`;
            } else if (bj.status === 'win') statusEl.innerText = 'HAI VINTO!';
            else if (bj.status === 'loss') statusEl.innerText = 'BANCO VINCE';
            else if (bj.status === 'bust') statusEl.innerText = 'SBALLATO!';
            else if (bj.status === 'push') statusEl.innerText = 'PAREGGIO (Push)';
            else statusEl.innerText = 'Piazza la tua puntata';
        }
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
        await this.loadUsers();
        await this.loadManualOdds();
        await this.loadAllBets();
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
            state.settings = settings;
            const overroundEl = document.getElementById('setting-overround');
            const houseEdgeEl = document.getElementById('setting-crash-house-edge');
            const virtualEdgeEl = document.getElementById('setting-virtual-house-edge');
            const apiKeyEl = document.getElementById('setting-apikey');
            const sourceEl = document.getElementById('setting-source');

            if (overroundEl) overroundEl.value = settings.overround;
            if (houseEdgeEl) houseEdgeEl.value = settings.crash_house_edge || '3';
            if (virtualEdgeEl) virtualEdgeEl.value = settings.virtual_house_edge || '15';
            if (apiKeyEl) apiKeyEl.value = settings.apikey || '';
            if (sourceEl) sourceEl.value = settings.odds_source || 'manual';
        }
    },
    async saveSettings() {
        const overround = document.getElementById('setting-overround').value;
        const crash_house_edge = document.getElementById('setting-crash-house-edge').value;
        const virtual_house_edge = document.getElementById('setting-virtual-house-edge').value;
        const apikey = document.getElementById('setting-apikey').value;
        const odds_source = document.getElementById('setting-source').value;
        await api.request('/settings', {
            method: 'POST',
            body: JSON.stringify({ overround, crash_house_edge, virtual_house_edge, apikey, odds_source })
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

        // Safe population
        document.getElementById('detail-username').innerText = detail.username || '---';
        document.getElementById('detail-status').innerText = detail.status || '---';
        document.getElementById('detail-status').style.color = detail.status === 'blocked' ? 'var(--danger)' : 'var(--success)';

        try {
            document.getElementById('detail-created').innerText = detail.created_at ? new Date(detail.created_at).toLocaleDateString() : '---';
        } catch (e) {
            document.getElementById('detail-created').innerText = '---';
        }

        document.getElementById('detail-balance').innerText = `€${(detail.balance || 0).toFixed(2)}`;

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
                    ${(b.selections||[]).map(s => { const isV=(s.event_id||'').startsWith('v_'); const r=s.match_result; const badge=isV?(r==='In corso'?`<span style="background:rgba(0,200,100,0.15);color:#00c864;border-radius:5px;padding:1px 6px;font-size:0.75rem;margin-left:5px;">⏱ In corso</span>`:r?`<span style="background:rgba(255,200,0,0.12);color:#f5c842;border-radius:5px;padding:1px 6px;font-size:0.75rem;margin-left:5px;">⚽ ${r}</span>`:`<span style="opacity:0.4;font-size:0.75rem;margin-left:5px;">In attesa</span>`):''; return `<div style="font-size:0.85rem;margin-bottom:4px;">• ${s.home_team||'?'} vs ${s.away_team||'?'}: <b>${s.selection||'?'}</b> @${(s.odds||0).toFixed(2)}${badge}</div>`; }).join('')}
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
        const bets = await api.request('/admin/bets');
        if (bets) {
            const container = document.getElementById('admin-bets-container');
            container.innerHTML = bets.map(b => `
                <div style="background:rgba(255,255,255,0.05); padding:1rem; border-radius:8px; margin-bottom:1rem; border-left: 4px solid ${b.status === 'won' ? 'var(--success)' : b.status === 'lost' ? 'var(--danger)' : 'var(--accent)'}">
                    <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                        <span style="font-weight:bold; color:var(--accent)">Giocata di: ${b.username}</span>
                        <span>€${b.amount.toFixed(2)} -> €${b.potential_win.toFixed(2)}</span>
                    </div>
                    ${(b.selections||[]).map(s => { const isV=(s.event_id||'').startsWith('v_'); const r=s.match_result; const badge=isV?(r==='In corso'?`<span style="background:rgba(0,200,100,0.15);color:#00c864;border-radius:5px;padding:1px 6px;font-size:0.75rem;margin-left:5px;">⏱ In corso</span>`:r?`<span style="background:rgba(255,200,0,0.12);color:#f5c842;border-radius:5px;padding:1px 6px;font-size:0.75rem;margin-left:5px;">⚽ ${r}</span>`:`<span style="opacity:0.4;font-size:0.75rem;margin-left:5px;">In attesa</span>`):''; return `<div style="font-size:0.85rem;margin-bottom:4px;">• ${s.home_team||'?'} vs ${s.away_team||'?'}: <b>${s.selection||'?'}</b> @${(s.odds||0).toFixed(2)}${badge}</div>`; }).join('')}
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
        const settings = state.settings || await api.request('/settings');
        if (!tbody) return;

        if (settings && settings.odds_source !== 'manual') {
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
        // Controllo se stiamo cercando di mischiare Reale e Virtuale
        if (state.slip.length > 0) {
            const isNewVirtual = String(eventId).startsWith('v_');
            const isExistingVirtual = String(state.slip[0].eventId).startsWith('v_');

            if (isNewVirtual !== isExistingVirtual) {
                alert('Non è possibile combinare scommesse reali e virtuali!');
                return;
            }
        }

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
        if (amount < 1) { // Minimum bet amount
            alert('L\'importo minimo della scommessa è €1.00');
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
        if (history && container) {
            container.innerHTML = history.map(bet => {
                let dateStr = '---';
                try {
                    if (bet.created_at) dateStr = new Date(bet.created_at).toLocaleString();
                } catch (e) { }

                return `
                <div style="background:var(--card-bg); border:1px solid var(--border-color); border-radius:12px; padding:1.5rem; margin-bottom:1.5rem;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:1rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:0.5rem;">
                        <span style="color:var(--text-secondary)">ID: #${bet.id} | ${dateStr}</span>
                        <span style="font-weight:bold; color:${bet.status === 'won' ? 'var(--success)' : bet.status === 'lost' ? 'var(--danger)' : 'var(--accent)'}">${bet.status.toUpperCase()}</span>
                    </div>
                    ${(bet.selections || []).map(s => `
                        <div style="margin-bottom:8px; font-size:0.9rem;">
                            <b>${s.selection || '---'}</b> <span style="color:var(--text-secondary)">@${(s.odds || 0).toFixed(2)}</span><br>
                            ${s.home_team || '---'} vs ${s.away_team || '---'} (${s.market || '---'})
                        </div>
                    `).join('')}
                    <div style="margin-top:1rem; display:flex; justify-content:space-between; font-weight:bold;">
                        <span>Importo: €${(bet.amount || 0).toFixed(2)}</span>
                        <span>Potential Win: €${(bet.potential_win || 0).toFixed(2)}</span>
                    </div>
                </div>
            `;
            }).join('');
        }
    }
};

window.crash = {
    init() {
        if (!state.crash.ws || state.crash.ws.readyState === WebSocket.CLOSED) {
            this.connect();
        }
        this.drawGraph();
    },
    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws/crash`;
        state.crash.ws = new WebSocket(wsUrl);

        state.crash.ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            this.handleMessage(data);
        };

        state.crash.ws.onclose = () => {
            console.log("WebSocket Crash chiuso. Riconnessione tra 3 secondi...");
            setTimeout(() => this.connect(), 3000);
        };
    },
    handleMessage(data) {
        if (data.type === 'init') {
            state.crash.status = data.status;
            state.crash.multiplier = data.multiplier;
            state.crash.history = data.history || [];
            this.updateUI();
            this.updateHistory();
        } else if (data.type === 'waiting') {
            state.crash.status = 'waiting';
            document.getElementById('crash-status-text').innerText = `Prossimo round tra ${data.time}s`;
            document.getElementById('crash-multiplier').style.color = 'white';
            document.getElementById('crash-multiplier').innerText = `1.00x`;
            this.updateUI();
        } else if (data.type === 'running') {
            state.crash.status = 'running';
            state.crash.multiplier = data.multiplier;
            document.getElementById('crash-status-text').innerText = 'In volo...';
            document.getElementById('crash-multiplier').innerText = `${data.multiplier.toFixed(2)}x`;
            this.updateUI();
        } else if (data.type === 'crashed') {
            state.crash.status = 'crashed';
            state.crash.multiplier = data.multiplier;
            state.crash.history = data.history;
            state.crash.activeBet = null;
            document.getElementById('crash-status-text').innerText = 'CRASH!';
            document.getElementById('crash-multiplier').innerText = `${data.multiplier.toFixed(2)}x`;
            document.getElementById('crash-multiplier').style.color = 'var(--danger)';
            this.updateUI();
            this.updateHistory();
            ui.fetchBalance();
        }
    },
    updateUI() {
        const btn = document.getElementById('crash-bet-btn');
        const amountInput = document.getElementById('crash-bet-amount');
        if (!btn || !amountInput) return;

        if (state.crash.status === 'waiting') {
            if (!state.crash.activeBet) {
                btn.innerText = 'SCOMMETTI';
                btn.style.background = 'var(--accent)';
                btn.disabled = false;
                btn.onclick = () => this.placeBet();
                amountInput.disabled = false;
            } else {
                btn.innerText = 'SCOMMESSA PIAZZATA';
                btn.style.background = 'var(--text-secondary)';
                btn.disabled = true;
            }
        } else if (state.crash.status === 'running') {
            if (state.crash.activeBet) {
                const payout = (state.crash.activeBet.amount * state.crash.multiplier).toFixed(2);
                btn.innerText = `INCASSA €${payout}`;
                btn.style.background = 'var(--success)';
                btn.disabled = false;
                btn.onclick = () => this.cashOut();
            } else {
                btn.innerText = 'IN CORSO...';
                btn.style.background = 'var(--text-secondary)';
                btn.disabled = true;
            }
            amountInput.disabled = true;
        } else {
            // Crashed
            btn.innerText = 'CRASHATO';
            btn.style.background = 'var(--danger)';
            btn.disabled = true;
            amountInput.disabled = true;
        }
    },
    async placeBet() {
        const amountInput = document.getElementById('crash-bet-amount');
        const rawVal = amountInput.value.replace(',', '.');
        const amount = parseFloat(rawVal);
        if (isNaN(amount) || amount < 0.20) return alert("Scommessa minima €0.20");
        if (amount > state.balance) return alert("Saldo insufficiente");

        const res = await api.request('/crash/bet', {
            method: 'POST',
            body: JSON.stringify({ amount })
        });

        if (res) {
            state.crash.activeBet = { id: res.bet_id, amount };
            ui.fetchBalance();
            this.updateUI();
        }
    },
    async cashOut() {
        if (!state.crash.activeBet) return;
        const res = await api.request('/crash/cashout', {
            method: 'POST',
            body: JSON.stringify({ bet_id: state.crash.activeBet.id })
        });

        if (res) {
            alert(`Hai vinto €${res.payout.toFixed(2)}!`);
            state.crash.activeBet = null;
            ui.fetchBalance();
            this.updateUI();
        }
    },
    updateHistory() {
        const container = document.getElementById('crash-history');
        if (!container) return;
        container.innerHTML = state.crash.history.slice(-10).reverse().map(m => `
            <div style="background: ${m >= 2 ? 'var(--success)' : 'rgba(255,255,255,0.1)'}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem;">
                ${m.toFixed(2)}x
            </div>
        `).join('');
    },
    drawGraph() {
        const canvas = document.getElementById('crash-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        const animate = () => {
            if (document.getElementById('section-crash').classList.contains('hidden')) return;

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (state.crash.status === 'running') {
                ctx.beginPath();
                ctx.strokeStyle = '#ffbb00';
                ctx.lineWidth = 4;
                ctx.moveTo(0, canvas.height);

                // Disegna una curva basata sul moltiplicatore attuale
                const progress = Math.min((state.crash.multiplier - 1) / 10, 1);
                const targetX = canvas.width * 0.8 * progress;
                const targetY = canvas.height - (canvas.height * 0.8 * progress);

                ctx.quadraticCurveTo(canvas.width * 0.4, canvas.height, targetX, targetY);
                ctx.stroke();
            }

            requestAnimationFrame(animate);
        };
        animate();
    }
};

window.virtual = {
    applyMobileLayout() {
        if (window.innerWidth > 600) return;
        setTimeout(() => {
            const live        = document.getElementById("virtual-live-board");
            const matchesEl   = document.getElementById("virtual-matches-container");
            const standingsEl = document.getElementById("virtual-standings-body");
            if (!live || !matchesEl) return;

            // Risale alle sezioni card contenitori
            const getBlock = el => el.closest("[class*='admin-section']") || el.closest("[style*='border-radius']") || el.parentElement;
            const liveBlock     = live;
            const matchesBlock  = getBlock(matchesEl);
            const standingsBlock = standingsEl ? getBlock(standingsEl) : null;

            // Trova il container comune più vicino
            const parent = liveBlock.parentElement;
            if (!parent) return;

            // Imposta flex sul parent per usare order
            parent.style.cssText += ";display:flex!important;flex-direction:column!important;gap:16px;";

            // Assegna order direttamente agli elementi
            liveBlock.style.order = "1";
            matchesBlock.style.order = "2";
            if (standingsBlock) standingsBlock.style.order = "3";

            // Forza anche i match container interni a colonna singola
            if (matchesEl) {
                matchesEl.style.cssText += ";display:flex!important;flex-direction:column!important;gap:12px;";
            }
            const liveMatches = document.getElementById("virtual-live-matches");
            if (liveMatches) {
                liveMatches.style.cssText += ";display:flex!important;flex-direction:column!important;gap:8px;";
            }
        }, 400);
    },
    init() {
        if (state.virtual.polling) clearInterval(state.virtual.polling);
        state.virtual.polling = setInterval(() => this.tick(), 1000);
        this.fetchStatus();
        this.fetchStandings();
        this.fetchMatches();
        // Riordina layout su mobile dopo che il DOM è pronto
        if (window.innerWidth <= 600) setTimeout(() => this.applyMobileLayout(), 800);

        // Optional: polling for my-bets if on bets section
        if (state.betsPolling) clearInterval(state.betsPolling);
        state.betsPolling = setInterval(() => {
            if (!document.getElementById('section-bets').classList.contains('hidden')) {
                bets.loadHistory();
            }
        }, 5000);
    },
    async tick() {
        if (state.virtual.status === 'BETTING' && state.virtual.timeLeft > 0) {
            state.virtual.timeLeft--;
            this.updateTimerUI();
        }

        if (Date.now() - state.virtual.lastFetch > 3000) {
            await this.fetchStatus();
        }
    },
    async fetchStatus() {
        const data = await api.request('/virtual/status');
        if (data) {
            const statusChanged = state.virtual.status !== data.phase;
            const matchdayChanged = state.virtual.currentMatchday !== data.matchday;

            state.virtual.status = data.phase || 'BETTING';
            state.virtual.timeLeft = data.timer || 0;
            state.virtual.currentMatchday = data.matchday || 0;
            state.virtual.finishedMatchday = data.finished_matchday || 0;
            state.virtual.clock = data.clock || "0'";
            state.virtual.actionText = data.action_text || '';
            state.virtual.lastFetch = Date.now();

            this.updateStatusUI();

            if (statusChanged || matchdayChanged || state.virtual.status === 'LIVE' || state.virtual.status === 'FINALIZING' || state.virtual.status === 'FINISHED') {
                this.fetchMatches().catch(e => console.error("Error fetching matches:", e));
                if (statusChanged || matchdayChanged) {
                    this.fetchStandings().catch(e => console.error("Error fetching standings:", e));
                    ui.fetchBalance();
                }
            }
        }
    },
    async fetchMatches() {
        // Carica le partite per il betting (sempre current_matchday)
        const matches = await api.request('/virtual/matches');
        if (matches) {
            state.virtual.matches = matches;
            this.renderMatches();
        }
        // Carica le partite per il tabellone (usa finished_matchday durante FINISHED)
        if (state.virtual.status === 'LIVE' || state.virtual.status === 'FINALIZING' || state.virtual.status === 'FINISHED') {
            const liveMatches = await api.request('/virtual/live');
            if (liveMatches) {
                state.virtual.liveMatches = liveMatches;
                this.renderLiveBoard();
            }
        }
    },
    async fetchStandings() {
        const standings = await api.request('/virtual/standings');
        if (standings) {
            state.virtual.standings = standings;
            this.renderStandings();
        }
    },
    updateTimerUI() {
        const timerEl = document.getElementById('virtual-timer');
        if (!timerEl) return;

        if (state.virtual.status === 'BETTING' || state.virtual.status === 'FINISHED') {
            const m = Math.floor(state.virtual.timeLeft / 60);
            const s = state.virtual.timeLeft % 60;
            timerEl.innerText = `${m}:${s < 10 ? '0' : ''}${s}`;
            timerEl.style.color = state.virtual.timeLeft < 30 ? 'var(--danger)' : 'var(--accent)';
            document.getElementById('virtual-timer-label').innerText = 'Alla Giornata';
        } else {
            timerEl.innerText = 'LIVE';
            timerEl.style.color = 'var(--danger)';
            document.getElementById('virtual-timer-label').innerText = 'In Corso';
        }
    },
    updateStatusUI() {
        const header = document.getElementById('virtual-header');
        const badge = document.getElementById('virtual-status-badge');
        const liveBoard = document.getElementById('virtual-live-board');

        const currentMatchday = state.virtual.currentMatchday;
        const finishedMatchday = state.virtual.finishedMatchday;
        const displayDay = state.virtual.status === 'FINISHED' ? finishedMatchday : currentMatchday;

        if (header) header.innerText = `Campionato Virtuale - Giornata ${displayDay}`;
        if (badge) {
            if (state.virtual.status === 'BETTING') {
                badge.innerText = 'BETTING';
                badge.style.background = 'var(--accent)';
            } else if (state.virtual.status === 'LIVE') {
                badge.innerText = 'LIVE';
                badge.style.background = 'var(--danger)';
            } else if (state.virtual.status === 'FINISHED') {
                badge.innerText = 'RISULTATI';
                badge.style.background = '#9b59b6';
            }
        }

        if (state.virtual.status === 'LIVE' || state.virtual.status === 'FINALIZING' || state.virtual.status === 'FINISHED') {
            if (liveBoard) liveBoard.classList.remove('hidden');
        } else {
            if (liveBoard) liveBoard.classList.add('hidden');
        }

        this.updateTimerUI();
    },
    renderStandings() {
        const tbody = document.getElementById('virtual-standings-body');
        if (!tbody) return;

        if (!state.virtual.standings || !Array.isArray(state.virtual.standings)) return;

        try {
            tbody.innerHTML = state.virtual.standings.map((s, i) => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding: 8px 4px;">${i + 1}</td>
                    <td style="padding: 8px 4px; display: flex; align-items: center; gap: 8px;">
                        <img src="${s.logo || ''}" style="width: 16px; height: 16px; object-fit: contain;" onerror="this.src='https://cdn-icons-png.flaticon.com/512/53/53283.png'">
                        ${s.team_name || '---'}
                    </td>
                    <td style="padding: 8px 4px; font-weight: bold;">${s.points || 0}</td>
                    <td style="padding: 8px 4px; color: var(--text-secondary);">${s.played || 0}</td>
                </tr>
            `).join('');
        } catch (e) {
            console.error("Error rendering standings:", e);
        }
    },
    expandedMatches: new Set(),
    toggleMatchOdds(matchId) {
        if (this.expandedMatches.has(matchId)) {
            this.expandedMatches.delete(matchId);
        } else {
            this.expandedMatches.add(matchId);
        }
        this.renderMatches(); // Rirenderizza solo la parte HTML per aggiornare la grid
    },
    renderMatches() {
        const container = document.getElementById('virtual-matches-container');
        if (!container) return;

        const isBettingDisabled = state.virtual.status === 'LIVE';

        if (!state.virtual.matches || !Array.isArray(state.virtual.matches)) return;

        try {
            container.innerHTML = state.virtual.matches.map(m => {
                const homeName = (m.home_team && m.home_team.name) ? m.home_team.name : 'Casa';
                const homeLogo = (m.home_team && m.home_team.logo) ? m.home_team.logo : '';
                const awayName = (m.away_team && m.away_team.name) ? m.away_team.name : 'Ospiti';
                const awayLogo = (m.away_team && m.away_team.logo) ? m.away_team.logo : '';
                const dis = isBettingDisabled ? 'disabled' : '';

                // Helper per pulsante quota
                const mkBtn = (sel, label, odds) => {
                    const safe = (Number(odds) || 1).toFixed(2);
                    const isSel = this.isSelected(m.id, sel) ? 'selected' : '';
                    return `<button onclick="virtual.addToSlip(${m.id},'${homeName} vs ${awayName}','bet','${sel}',${safe})"
                        class="price-btn ${isSel}" ${dis} style="font-size:0.75rem; padding:8px 6px;">
                        <span class="label" style="font-weight:600;">${label}</span>
                        <span class="val" style="margin-left:auto;">${safe}</span>
                    </button>`;
                };

                // Combo odds
                const combo = m.odds_combo || {};
                const exact = m.odds_exact || {};

                // Sezione Combo 1X2 + Over/Under (iterata su tutte le soglie X.5)
                const thresholds = [1.5, 2.5, 3.5, 4.5];
                let comboOUHtml = '';
                thresholds.forEach(t => {
                    const order = [`1+Over ${t}`, `1+Under ${t}`, `X+Over ${t}`, `X+Under ${t}`, `2+Over ${t}`, `2+Under ${t}`];
                    // Recupero quanti e quali pulsanti esistono validi
                    const btns = order.map(k => combo[k] ? mkBtn(k, k.replace(`Over ${t}`, `O${t}`).replace(`Under ${t}`, `U${t}`), combo[k]) : '').filter(Boolean).join('');
                    if (btns) {
                        comboOUHtml += `<div style="margin-top:15px;">
                            <div style="font-size:0.75rem; color:var(--text-secondary); font-weight:600; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; display:block; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:4px;">Combo 1X2 + Over/Under ${t}</div>
                            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">${btns}</div>
                        </div>`;
                    }
                });

                // Sezione Combo 1X2 + GG/NG
                const comboGGOrder = ['1+GG', '1+NG', 'X+GG', 'X+NG', '2+GG', '2+NG'];
                const comboGGBtns = comboGGOrder.map(k => combo[k] ? mkBtn(k, k, combo[k]) : '').join('');

                // Risultati Esatti: Ordina mettendo "Altro" in fondo
                const exactBtns = Object.entries(exact)
                    .sort((a, b) => {
                        if (a[0] === "Altro") return 1;
                        if (b[0] === "Altro") return -1;
                        return a[1] - b[1]; // Poi per probabilità stimata o score (lascio valore)
                    })
                    .map(([score, odd]) => mkBtn(score === 'Altro' ? 'Esatto Altro' : `Esatto ${score}`, score, odd))
                    .join('');

                const secStyle = 'margin-top:15px;';
                const lblStyle = 'font-size:0.75rem; color:var(--text-secondary); font-weight:600; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; display:block; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:4px;';

                const isExpanded = this.expandedMatches.has(m.id);

                return `
                <div style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 1.2rem;">
                    <!-- Header squadre e Tasto Espandi -->
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
                        <div style="display:flex; align-items:center; gap:8px; font-weight:bold; font-size:1rem;">
                            <img src="${homeLogo}" style="width:24px;height:24px;object-fit:contain;" onerror="this.src='https://cdn-icons-png.flaticon.com/512/53/53283.png'">
                            ${homeName}
                        </div>
                        <span style="color:var(--text-secondary);font-size:0.8rem;font-weight:600;padding: 0 10px;">VS</span>
                        <div style="display:flex; align-items:center; gap:8px; font-weight:bold; font-size:1rem;">
                            ${awayName}
                            <img src="${awayLogo}" style="width:24px;height:24px;object-fit:contain;" onerror="this.src='https://cdn-icons-png.flaticon.com/512/53/53283.png'">
                        </div>
                    </div>

                    <!-- 1X2 Visibile -->
                    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; margin-bottom: ${isExpanded ? '12px' : '0'};">
                        ${mkBtn('1', '1', m.odds_1)}${mkBtn('X', 'X', m.odds_x)}${mkBtn('2', '2', m.odds_2)}
                    </div>

                    <!-- Sezione Nascosta per i mercati extra -->
                    <div style="display: ${isExpanded ? 'block' : 'none'}; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
                        <!-- Goal / No Goal -->
                        <div style="${secStyle}">
                            <div style="${lblStyle}">Goal / No Goal</div>
                            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">
                                ${mkBtn('Goal', 'Goal', m.odds_gg)}
                                ${mkBtn('No Goal', 'No Goal', m.odds_ng)}
                            </div>
                        </div>

                        <!-- Over/Under -->
                        <div style="${secStyle}">
                            <div style="${lblStyle}">Over / Under</div>
                            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">
                                ${combo['Over 1.5'] ? mkBtn('Over 1.5', 'Over 1.5', combo['Over 1.5']) : ''}
                                ${combo['Under 1.5'] ? mkBtn('Under 1.5', 'Under 1.5', combo['Under 1.5']) : ''}
                                ${mkBtn('Over 2.5', 'Over 2.5', m.odds_over25)}
                                ${mkBtn('Under 2.5', 'Under 2.5', m.odds_under25)}
                                ${combo['Over 3.5'] ? mkBtn('Over 3.5', 'Over 3.5', combo['Over 3.5']) : ''}
                                ${combo['Under 3.5'] ? mkBtn('Under 3.5', 'Under 3.5', combo['Under 3.5']) : ''}
                                ${combo['Over 4.5'] ? mkBtn('Over 4.5', 'Over 4.5', combo['Over 4.5']) : ''}
                                ${combo['Under 4.5'] ? mkBtn('Under 4.5', 'Under 4.5', combo['Under 4.5']) : ''}
                            </div>
                        </div>

                        <!-- Tutte le Combo 1X2 + Over/Under (1.5, 2.5, 3.5, 4.5) -->
                        ${comboOUHtml}

                        <!-- Combo 1X2 + GG/NG -->
                        ${comboGGBtns ? `<div style="${secStyle}">
                            <div style="${lblStyle}">Combo 1X2 + Goal/No Goal</div>
                            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">${comboGGBtns}</div>
                        </div>` : ''}

                        <!-- Risultati Esatti -->
                        ${exactBtns ? `<div style="${secStyle}">
                            <div style="${lblStyle}">Risultato Esatto</div>
                            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">${exactBtns}</div>
                        </div>` : ''}
                    </div>

                    <!-- Tasto per espandere -->
                    <button onclick="virtual.toggleMatchOdds(${m.id})" style="width:100%; background:transparent; border:none; color:var(--accent); cursor:pointer; font-weight:bold; font-size:0.8rem; margin-top:12px; display:flex; justify-content:center; align-items:center; gap:6px;">
                        ${isExpanded ? '▲ Chiudi' : '▼ Altre Quote...'}
                    </button>
                </div>
                `;
            }).join('');
        } catch (e) {
            console.error("Error rendering matches:", e);
            if (container) container.innerHTML = '<div style="color:red;font-weight:bold;padding:20px;">ERRORE JS:<br>' + e.message + '<br>' + e.stack + '</div>';
        }
    },
    renderLiveBoard() {
        const container = document.getElementById('virtual-live-matches');
        const clockEl = document.getElementById('virtual-clock');
        if (!container) return;

        if (!state.virtual.liveMatches || !Array.isArray(state.virtual.liveMatches)) return;

        const isFinished = state.virtual.status === 'FINISHED';

        // Aggiorna testo azione o titolo
        if (clockEl) {
            if (isFinished) {
                clockEl.innerText = '🏆 Risultati Finali';
                clockEl.style.color = 'var(--accent)';
            } else {
                clockEl.innerText = state.virtual.actionText || '🏟️ In corso...';
                clockEl.style.color = 'var(--danger)';
            }
        }

        try {
            container.innerHTML = state.virtual.liveMatches.map(m => {
                const hName = (m.home_team && m.home_team.name) ? m.home_team.name : '---';
                const aName = (m.away_team && m.away_team.name) ? m.away_team.name : '---';
                const scoreColor = isFinished ? '#ffd700' : '#00ff88';
                const border = isFinished ? '1px solid rgba(255,215,0,0.3)' : '1px solid rgba(255,255,255,0.05)';

                return `
                    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: ${border};">
                    <span style="font-size: 0.85rem; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600;">${hName}</span>
                    <span style="background: #000; color: ${scoreColor}; padding: 4px 12px; border-radius: 4px; font-weight: 900; margin: 0 15px; min-width: 60px; text-align: center; font-family: monospace; font-size: 1.1rem; border: 1px solid #333;">
                        ${m.home_score || 0} - ${m.away_score || 0}
                    </span>
                    <span style="font-size: 0.85rem; flex: 1; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600;">${aName}</span>
                </div>
                    `;
            }).join('');
        } catch (e) {
            console.error("Error rendering live board:", e);
        }
    },
    isSelected(matchId, selection) {
        return state.slip.some(s => s.eventId === 'v_' + matchId && s.selection === selection);
    },
    addToSlip(matchId, event, market, selection, odds) {
        bets.addToSlip('v_' + matchId, event, market, selection, odds);
        this.renderMatches(); // Re-render per mostrare il bordo selezionato
    }
};

window.onload = () => {
    if (state.token) {
        ui.showDashboard();
        dashboard.init();
        router.navigate('odds');
    }
};

// --- BACCARAT ---
const baccarat = {
    sleep(ms) { return new Promise(r => setTimeout(r, ms)); },

    animateCard(container, card) {
        return new Promise(resolve => {
            const isRed = card.suit === '♥' || card.suit === '♦';
            const el = document.createElement('div');
            el.style.cssText = 'background:white;color:' + (isRed ? '#e17055' : '#2d3436') + ';border-radius:8px;padding:8px 10px;min-width:44px;text-align:center;font-size:1.1rem;font-weight:bold;box-shadow:0 4px 12px rgba(0,0,0,0.5);opacity:0;transform:translateY(-25px) scale(0.85);transition:opacity 0.3s ease,transform 0.3s cubic-bezier(0.34,1.4,0.64,1);display:inline-block;margin:2px;';
            el.innerHTML = '<div>' + card.rank + '</div><div>' + card.suit + '</div>';
            container.appendChild(el);
            requestAnimationFrame(() => { requestAnimationFrame(() => {
                el.style.opacity = '1';
                el.style.transform = 'translateY(0) scale(1)';
            }); });
            setTimeout(resolve, 350);
        });
    },

    resetUI() {
        const btn = document.getElementById('bac-deal-btn');
        const playerCards = document.getElementById('bac-player-cards');
        const bankerCards = document.getElementById('bac-banker-cards');
        const resultEl = document.getElementById('bac-result');
        if (playerCards) playerCards.innerHTML = '';
        if (bankerCards) bankerCards.innerHTML = '';
        if (resultEl) resultEl.style.display = 'none';
        const ps = document.getElementById('bac-player-score');
        const bs = document.getElementById('bac-banker-score');
        if (ps) ps.innerText = '-';
        if (bs) bs.innerText = '-';
        if (btn) btn.disabled = false;
    },

    async deal() {
        const player = parseFloat(document.getElementById('bac-bet-player').value || 0);
        const tie    = parseFloat(document.getElementById('bac-bet-tie').value    || 0);
        const banker = parseFloat(document.getElementById('bac-bet-banker').value || 0);
        const pp     = parseFloat(document.getElementById('bac-player-pair').value || 0);
        const bp     = parseFloat(document.getElementById('bac-banker-pair').value || 0);

        const total = player + tie + banker + pp + bp;
        if (total < 0.20) return alert('Inserisci almeno €0.20 su una puntata');

        const btn         = document.getElementById('bac-deal-btn');
        const playerCards = document.getElementById('bac-player-cards');
        const bankerCards = document.getElementById('bac-banker-cards');
        const resultEl    = document.getElementById('bac-result');

        this.resetUI();
        btn.disabled = true;

        try {
            const res = await api.request('/baccarat/deal', {
                method: 'POST',
                body: JSON.stringify({ player, tie, banker, player_pair: pp, banker_pair: bp })
            });

            if (!res) return;

            // Animazione: P1, B1, P2, B2, [P3], [B3]
            const seq = [
                { c: playerCards, card: res.player[0] },
                { c: bankerCards, card: res.banker[0] },
                { c: playerCards, card: res.player[1] },
                { c: bankerCards, card: res.banker[1] },
            ];
            if (res.player[2]) seq.push({ c: playerCards, card: res.player[2] });
            if (res.banker[2]) seq.push({ c: bankerCards, card: res.banker[2] });

            for (const item of seq) {
                await this.animateCard(item.c, item.card);
                await this.sleep(100);
            }

            // Punteggi
            await this.sleep(200);
            document.getElementById('bac-player-score').innerText = res.player_score;
            document.getElementById('bac-banker-score').innerText = res.banker_score;

            // Risultato
            await this.sleep(400);
            const labels = { player: 'GIOCATORE', banker: 'BANCO', tie: 'PAREGGIO' };
            let msg = labels[res.winner] + ' VINCE';
            if (res.player_pair) msg += '\nCoppia Giocatore: ' + (res.player_pair_label || '');
            if (res.banker_pair) msg += '\nCoppia Banco: ' + (res.banker_pair_label || '');
            const profit = res.profit;
            msg += profit >= 0 ? '\n+€' + res.payout.toFixed(2) : '\n-€' + Math.abs(profit).toFixed(2);

            resultEl.innerText = msg;
            resultEl.style.background = profit >= 0 ? 'rgba(0,184,148,0.15)' : 'rgba(214,48,49,0.15)';
            resultEl.style.color      = profit >= 0 ? '#00b894' : '#d63031';
            resultEl.style.border     = '1px solid ' + (profit >= 0 ? 'rgba(0,184,148,0.4)' : 'rgba(214,48,49,0.3)');
            resultEl.style.opacity    = '0';
            resultEl.style.transition = 'opacity 0.4s';
            resultEl.style.display    = 'block';
            requestAnimationFrame(() => { requestAnimationFrame(() => { resultEl.style.opacity = '1'; }); });

            // Saldo dopo risultato
            await this.sleep(300);
            if (res.new_balance !== undefined) {
                state.balance = res.new_balance;
                document.getElementById('user-balance-nav').innerText = 'Saldo: €' + res.new_balance.toFixed(2);
            } else {
                ui.fetchBalance();
            }
        } catch (err) {
            console.error('Baccarat error:', err);
        } finally {
            btn.disabled = false;
        }
    }
};
