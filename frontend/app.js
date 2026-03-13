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
        status: 'betting', // betting, playing, win, loss, bust, push
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
    },
    baccarat: {
        lastResult: null,
        status: 'betting', // betting, dealing, result
        player_hand: [],
        banker_hand: [],
        player_score: 0,
        banker_score: 0,
        winner: null,
        bets: { player: 0, banker: 0, tie: 0, player_pair: 0, banker_pair: 0 }
    }
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
            const data = await response.json();
            if (!response.ok) {
                const msg = data?.detail || `Errore ${response.status}`;
                alert(`Errore: ${msg}`);
                return null;
            }
            return data;
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
            const mobAdmin = document.getElementById('mob-nav-admin');
            if (mobAdmin) mobAdmin.classList.remove('hidden');
            // Timer e pulsante refresh solo per admin
            const timerArea = document.getElementById('admin-timer-area');
            if (timerArea) timerArea.style.display = 'flex';
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
            'baccarat': 'nav-casino',
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
            'baccarat': 'mob-nav-casino',
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
        if (section === 'virtual') virtual.init();
        if (section === 'baccarat') { baccarat.initChips(); baccarat.updateUI(); }
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
        api.request('/settings').then(s => {
            if (s) state.settings = s;
        });
        // Aggiorna il countdown ogni minuto
        setInterval(() => this.updateTimer(), 60000);
    },
    async fetchOdds(forceRefresh = false) {
        if (forceRefresh && state.role === 'admin') {
            await api.request('/odds/force-refresh', { method: 'POST' });
        }
        const odds = await api.request('/odds');
        if (odds) state.odds = odds;

        if (!state.settings) {
            state.settings = await api.request('/settings');
        }

        // Legge i minuti rimanenti reali dal server (non riparte sempre da 6h)
        const status = await api.request('/odds/status');
        if (status && status.next_fetch_in_minutes > 0) {
            state.timer = status.next_fetch_in_minutes;
        } else {
            state.timer = 360; // fallback
        }

        this.renderOdds();
        ui.fetchBalance();
        this.updateTimerDisplay();
    },
    updateTimer() {
        if (state.timer > 0) state.timer--;
        if (state.timer <= 0) this.fetchOdds();
        this.updateTimerDisplay();
    },
    updateTimerDisplay() {
        const el = document.getElementById('update-timer');
        if (!el) return;
        if (state.timer <= 0) {
            el.innerText = 'Aggiornamento in corso...';
        } else if (state.timer >= 60) {
            const h = Math.floor(state.timer / 60);
            const m = state.timer % 60;
            el.innerText = `Prossimo aggiornamento: ${h}h ${m}m`;
        } else {
            el.innerText = `Prossimo aggiornamento: ${state.timer}m`;
        }
    },
    renderOdds() {
        const container = document.getElementById('odds-container');
        if (!container) return;

        const searchInput = document.getElementById('match-search');
        const query = (searchInput?.value || '').toLowerCase();

        const settings = state.settings;
        ui.fetchBalance();
        this.updateTimerDisplay();

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

        const cutoff = new Date(Date.now() + 60 * 1000);
        let filteredOdds = state.odds.filter(e => !e.commence_time || new Date(e.commence_time) > cutoff);
        if (query) {
            filteredOdds = filteredOdds.filter(event => {
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
        const oddsStatus = await api.request('/odds/status');

        if (users && bets) {
            document.getElementById('kpi-users').innerText = users.length;

            const totalBalance = users.reduce((sum, u) => sum + u.balance, 0);
            document.getElementById('kpi-balances').innerText = `€${totalBalance.toFixed(2)}`;

            const pendingBets = bets.filter(b => b.status === 'pending');
            const totalExposure = pendingBets.reduce((sum, b) => sum + b.potential_win, 0);
            document.getElementById('kpi-exposure').innerText = `€${totalExposure.toFixed(2)}`;

            const wonBets = bets.filter(b => b.status === 'won');
            const totalBetAmount = bets.reduce((sum, b) => sum + b.amount, 0);
            const totalPaidOut = wonBets.reduce((sum, b) => sum + b.potential_win, 0);

            const profit = totalBetAmount - totalPaidOut;
            const profitEl = document.getElementById('kpi-profit');
            profitEl.innerText = `€${profit.toFixed(2)}`;
            profitEl.className = `kpi-value ${profit >= 0 ? 'success' : 'danger'}`;
        }

        // Mostra stato cache API quote
        const apiStatusEl = document.getElementById('kpi-api-cache');
        if (apiStatusEl && oddsStatus) {
            if (oddsStatus.last_fetch) {
                apiStatusEl.innerHTML = `
                    <div style="font-size:0.8rem; color: var(--text-secondary); margin-top: 0.5rem; padding: 0.6rem; background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border-color);">
                        📡 <strong>Cache Quote API</strong><br>
                        Ultima fetch: <strong>${oddsStatus.last_fetch}</strong> &nbsp;|&nbsp;
                        Prossimo aggiornamento: <strong>${oddsStatus.next_fetch_in_minutes} min</strong> &nbsp;|&nbsp;
                        Partite in cache: <strong>${oddsStatus.cached_events}</strong>
                        <button onclick="admin.forceRefreshOdds()" style="margin-left:1rem; font-size:0.75rem; padding:3px 10px; background:#e63946; border:none; color:white; border-radius:5px; cursor:pointer;">⚡ Forza aggiornamento</button>
                    </div>`;
            } else {
                apiStatusEl.innerHTML = `<div style="font-size:0.8rem; color: var(--text-secondary); margin-top:0.5rem;">📡 Nessuna fetch API ancora effettuata (modalità manuale o cache vuota)</div>`;
            }
        }
    },
    async forceRefreshOdds() {
        if (!confirm('Sei sicuro? Questa operazione consuma crediti API.')) return;
        await dashboard.fetchOdds(true);
        alert('Quote aggiornate!');
        this.loadDashboardKPIs();
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

        // Handle error response or missing data
        if (!detail || detail.detail) {
            alert("Errore nel caricamento dei dettagli: " + (detail ? detail.detail : "Connessione fallita"));
            return;
        }

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
                    ${b.selections.map(s => {
                        let scoreBadge = '';
                        if (s.v_score !== undefined) {
                            let textOpts = {'scheduled': 'In Arrivo', 'live': 'Live', 'finished': 'Terminata'};
                            let bg = s.v_status === 'finished' ? '#ffd700' : (s.v_status === 'live' ? '#ff4d4d' : '#4caf50');
                            scoreBadge = `<span style="background:${bg}; color:#000; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.75rem; margin-left:10px;">Risultato: ${s.v_score} (${textOpts[s.v_status] || s.v_status})</span>`;
                        }
                        return `
                        <div style="font-size:0.85rem; margin-bottom:3px; opacity:0.8; display:flex; align-items:center;">
                            • ${s.home_team} vs ${s.away_team}: <b style="margin-left:5px;">${s.selection}</b> <span style="margin-left:5px;">@${s.odds.toFixed(2)}</span> ${scoreBadge}
                        </div>
                    `}).join('')}
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
    _adminBets: [],
    _adminBetFilters: { sport: true, virtual: true },

    toggleBetFilter(cat) {
        this._adminBetFilters[cat] = !this._adminBetFilters[cat];
        const check = document.getElementById(`abf-${cat}-check`);
        const label = document.getElementById(`abf-${cat}`);
        if (check) check.innerText = this._adminBetFilters[cat] ? '✅' : '⬜';
        if (label) label.style.opacity = this._adminBetFilters[cat] ? '1' : '0.4';
        this.renderAdminBets();
    },

    renderAdminBets() {
        const container = document.getElementById('admin-bets-container');
        if (!container) return;

        const statusFilter = document.getElementById('abf-status')?.value || '';
        const userFilter = (document.getElementById('abf-user')?.value || '').toLowerCase().trim();

        const filtered = this._adminBets.filter(b => {
            if (!this._adminBetFilters[b.category]) return false;
            if (statusFilter && b.status !== statusFilter) return false;
            if (userFilter && !(b.username || '').toLowerCase().includes(userFilter)) return false;
            return true;
        });

        if (filtered.length === 0) {
            container.innerHTML = `<div style="text-align:center; color:var(--text-secondary); padding:2rem; font-size:0.9rem;">Nessuna scommessa trovata.</div>`;
            return;
        }

        const catColors = { sport: '#3498db', virtual: '#9b59b6', casino: '#e67e22' };

        container.innerHTML = filtered.map(b => {
            const catColor = catColors[b.category] || '#aaa';
            const statusColor = b.status === 'won' ? 'var(--success)' : b.status === 'lost' ? 'var(--danger)' : 'var(--accent)';
            const statusLabel = { won: 'VINTA ✅', lost: 'PERSA ❌', pending: 'IN CORSO ⏳', void: 'ANNULLATA ↩️' }[b.status] || b.status.toUpperCase();

            let bodyHtml = '';
            if (b.category === 'casino') {
                const profit = (b.potential_win || 0) - (b.amount || 0);
                bodyHtml = `<div style="font-size:0.85rem; color:var(--text-secondary); padding:4px 0;">
                    Gioco: <b style="color:white;">${b.game}</b>
                    &nbsp;·&nbsp; Quota: <b style="color:white;">${(b.total_odds||0).toFixed(2)}x</b>
                    &nbsp;·&nbsp; Esito: <b style="color:${profit>=0?'var(--success)':'var(--danger)'};">${profit>=0?'+':''}€${profit.toFixed(2)}</b>
                </div>`;
            } else {
                bodyHtml = (b.selections || []).map(s => {
                    let scoreBadge = '';
                    if (s.v_score !== undefined) {
                        const textOpts = { scheduled: 'In Arrivo', live: 'Live', finished: 'Terminata' };
                        const bg = s.v_status === 'finished' ? '#ffd700' : (s.v_status === 'live' ? '#ff4d4d' : '#4caf50');
                        scoreBadge = `<span style="background:${bg};color:#000;padding:1px 6px;border-radius:4px;font-weight:bold;font-size:0.7rem;margin-left:8px;">${s.v_score} (${textOpts[s.v_status]||s.v_status})</span>`;
                    }
                    return `<div style="font-size:0.83rem; margin:2px 0; opacity:0.85;">
                        • ${s.home_team||'---'} vs ${s.away_team||'---'}: <b>${s.selection}</b> <span style="color:var(--text-secondary);">@${(s.odds||0).toFixed(2)}</span>${scoreBadge}
                    </div>`;
                }).join('');
            }

            const resolveButtons = b.status === 'pending' && b.category !== 'casino'
                ? `<button onclick="admin.resolveBet(${b.id}, 'won')" style="background:var(--success);width:auto;padding:4px 14px;font-size:0.82rem;">Vincente</button>
                   <button onclick="admin.resolveBet(${b.id}, 'lost')" style="background:var(--danger);width:auto;padding:4px 14px;font-size:0.82rem;">Perdente</button>`
                : `<span style="font-weight:700;font-size:0.82rem;color:${statusColor};">${statusLabel}</span>`;

            return `<div style="background:rgba(255,255,255,0.04); padding:0.9rem 1rem; border-radius:10px; margin-bottom:0.8rem; border-left:4px solid ${catColor};">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.5rem;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:0.7rem; font-weight:700; color:${catColor}; background:${catColor}22; padding:2px 10px; border-radius:20px; border:1px solid ${catColor}44;">${b.game||b.category}</span>
                        <span style="font-weight:700; color:var(--accent);">${b.username}</span>
                        <span style="font-size:0.75rem; color:var(--text-secondary);">#${b.id}</span>
                    </div>
                    <span style="font-size:0.85rem;">€${(b.amount||0).toFixed(2)} → €${(b.potential_win||0).toFixed(2)}</span>
                </div>
                ${bodyHtml}
                <div style="margin-top:0.6rem; display:flex; gap:8px; align-items:center;">${resolveButtons}</div>
            </div>`;
        }).join('');
    },

    async loadAllBets() {
        const bets = await api.request('/admin/bets');
        if (bets) {
            this._adminBets = bets;
            this.renderAdminBets();
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
        // Controllo tempo: blocca silenziosamente partite già iniziate o entro 1 min
        if (!String(eventId).startsWith('v_')) {
            const matchData = (state.odds || []).find(e => e.id === eventId);
            if (!matchData) return; // non in cache = già scaduta
            if (matchData.commence_time) {
                const startTime = new Date(matchData.commence_time);
                if (startTime <= new Date(Date.now() + 60 * 1000)) return;
            }
        }

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
        if (amount < 0.20) { // Minimum bet amount
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
    _filters: { sport: true, virtual: true },
    _allBets: [],

    toggleFilter(cat) {
        this._filters[cat] = !this._filters[cat];
        // Aggiorna icona spunta
        const checkEl = document.getElementById(`filter-${cat}-check`);
        const labelEl = document.getElementById(`filter-${cat}-label`);
        if (checkEl) checkEl.innerText = this._filters[cat] ? '✅' : '⬜';
        if (labelEl) labelEl.style.opacity = this._filters[cat] ? '1' : '0.4';
        this.renderBets();
    },

    renderBets() {
        const container = document.getElementById('my-bets-container');
        if (!container) return;

        const filtered = this._allBets.filter(b => this._filters[b.category] === true);

        if (filtered.length === 0) {
            container.innerHTML = `<div style="text-align:center; color:var(--text-secondary); padding:3rem 0; font-size:0.95rem;">Nessuna scommessa trovata per i filtri selezionati.</div>`;
            return;
        }

        const catColors = { sport: '#3498db', virtual: '#9b59b6', casino: '#e67e22' };
        const catLabels = { sport: '⚽ Sport', virtual: '🕹️ Virtuale', casino: '🎰 Casinò' };

        container.innerHTML = filtered.map(bet => {
            let dateStr = '---';
            try { if (bet.created_at) dateStr = new Date(bet.created_at).toLocaleString('it-IT'); } catch(e) {}

            const statusColor = bet.status === 'won' ? 'var(--success)' : bet.status === 'lost' ? 'var(--danger)' : 'var(--accent)';
            const statusLabel = { won: '✅ VINTO', lost: '❌ PERSO', pending: '⏳ IN CORSO', void: '↩️ ANNULLATO' }[bet.status] || bet.status.toUpperCase();
            const catColor = catColors[bet.category] || '#aaa';
            const catLabel = catLabels[bet.category] || bet.category;
            const gameLabel = bet.game || catLabel;

            // Corpo scommessa in base al tipo
            let bodyHtml = '';

            if (bet.category === 'casino' && bet.game === 'Crash Game') {
                const mult = (bet.crash_multiplier || 0);
                bodyHtml = `
                    <div style="font-size:0.9rem; color:var(--text-secondary); padding:6px 0;">
                        Cashout: <b style="color:white;">${mult > 0 ? mult.toFixed(2) + 'x' : '—'}</b>
                        &nbsp;·&nbsp; Vincita: <b style="color:${bet.status === 'won' ? 'var(--success)' : 'var(--text-secondary)'};">€${(bet.potential_win || 0).toFixed(2)}</b>
                    </div>`;
            } else if (bet.category === 'casino') {
                const profit = (bet.potential_win || 0) - (bet.amount || 0);
                const profitColor = profit >= 0 ? 'var(--success)' : 'var(--danger)';
                bodyHtml = `
                    <div style="font-size:0.9rem; color:var(--text-secondary); padding:6px 0;">
                        Esito: <b style="color:${profitColor};">${profit >= 0 ? '+' : ''}€${profit.toFixed(2)}</b>
                        &nbsp;·&nbsp; Quota: <b style="color:white;">${(bet.total_odds || 0).toFixed(2)}x</b>
                    </div>`;
            } else {
                bodyHtml = (bet.selections || []).map(s => `
                    <div style="margin:4px 0; font-size:0.875rem; padding:6px 10px; background:rgba(255,255,255,0.04); border-radius:8px;">
                        <span style="font-weight:700;">${s.selection || '---'}</span>
                        <span style="color:var(--text-secondary); margin-left:6px;">@${(s.odds || 0).toFixed(2)}</span>
                        <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:2px;">
                            ${s.home_team || '---'} vs ${s.away_team || '---'}
                            ${s.market ? `· <i>${s.market}</i>` : ''}
                        </div>
                    </div>`).join('');
            }

            return `
            <div style="background:var(--card-bg); border:1px solid var(--border-color); border-left:4px solid ${catColor}; border-radius:12px; padding:1rem 1.2rem; margin-bottom:1rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem; flex-wrap:wrap; gap:0.4rem;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <span style="font-size:0.7rem; font-weight:700; color:${catColor}; background:${catColor}22; padding:2px 10px; border-radius:20px; border:1px solid ${catColor}44;">${gameLabel}</span>
                        <span style="font-size:0.75rem; color:var(--text-secondary);">#${bet.id} · ${dateStr}</span>
                    </div>
                    <span style="font-weight:900; font-size:0.85rem; color:${statusColor};">${statusLabel}</span>
                </div>
                ${bodyHtml}
                <div style="display:flex; justify-content:space-between; margin-top:0.7rem; padding-top:0.6rem; border-top:1px solid rgba(255,255,255,0.06); font-size:0.85rem;">
                    <span style="color:var(--text-secondary);">Puntata: <b style="color:white;">€${(bet.amount || 0).toFixed(2)}</b></span>
                    <span style="color:var(--text-secondary);">Vincita pot.: <b style="color:white;">€${(bet.potential_win || 0).toFixed(2)}</b></span>
                </div>
            </div>`;
        }).join('');
    },

    async loadHistory() {
        const history = await api.request('/my-bets');
        if (!history) return;
        this._allBets = history;
        this.renderBets();
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
    init() {
        if (state.virtual.polling) clearInterval(state.virtual.polling);
        state.virtual.polling = setInterval(() => this.tick(), 1000);
        this.fetchStatus();
        this.fetchStandings();
        this.fetchMatches();

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
                    <td style="padding: 8px 4px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <img src="${s.logo || ''}" style="width: 16px; height: 16px; object-fit: contain; flex-shrink:0;" onerror="this.src='https://cdn-icons-png.flaticon.com/512/53/53283.png'">
                            <span>${s.team_name || '---'}</span>
                        </div>
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
                    <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:10px 12px; border-radius:8px; border:${border}; gap:8px;">
                        <span style="font-size:0.85rem; flex:1; font-weight:600; word-break:break-word;">${hName}</span>
                        <span style="background:#000; color:${scoreColor}; padding:4px 10px; border-radius:4px; font-weight:900; flex-shrink:0; min-width:54px; text-align:center; font-family:monospace; font-size:1rem; border:1px solid #333;">
                            ${m.home_score || 0} - ${m.away_score || 0}
                        </span>
                        <span style="font-size:0.85rem; flex:1; text-align:right; font-weight:600; word-break:break-word;">${aName}</span>
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

window.baccarat = {
    // Fiches disponibili: valore e colore
    CHIPS: [
        { value: 0.20, color: '#bbb',    label: '0.20', id: '020' },
        { value: 0.50, color: '#a0522d', label: '0.50', id: '050' },
        { value: 1,    color: '#1a73e8', label: '1',    id: '1' },
        { value: 2,    color: '#28a745', label: '2',    id: '2' },
        { value: 5,    color: '#e63946', label: '5',    id: '5' },
        { value: 10,   color: '#6f42c1', label: '10',   id: '10' },
        { value: 25,   color: '#fd7e14', label: '25',   id: '25' },
        { value: 50,   color: '#ffd700', label: '50',   id: '50' },
    ],
    selectedChip: 1,

    initChips() {
        const container = document.getElementById('bac-chips');
        if (!container) return;
        container.innerHTML = this.CHIPS.map(c => `
            <div id="bac-chip-${c.id}"
                 onclick="baccarat.selectChip('${c.id}', ${c.value})"
                 style="
                    width:52px; height:52px; border-radius:50%;
                    background: ${c.color};
                    border: 3px solid ${c.value === this.selectedChip ? 'white' : 'rgba(255,255,255,0.3)'};
                    box-shadow: ${c.value === this.selectedChip ? '0 0 12px white' : '0 2px 6px rgba(0,0,0,0.5)'};
                    display:flex; align-items:center; justify-content:center;
                    font-weight:900; font-size:0.75rem; color:white;
                    cursor:pointer; transition: all 0.15s; user-select:none;
                    text-shadow: 0 1px 3px rgba(0,0,0,0.7);
                 ">€${c.label}</div>
        `).join('');
    },

    selectChip(chipId, val) {
        this.selectedChip = val;
        // Aggiorna bordi
        this.CHIPS.forEach(c => {
            const el = document.getElementById(`bac-chip-${c.id}`);
            if (!el) return;
            el.style.border = `3px solid ${c.value === val ? 'white' : 'rgba(255,255,255,0.3)'}`;
            el.style.boxShadow = c.value === val ? '0 0 12px white' : '0 2px 6px rgba(0,0,0,0.5)';
        });
    },

    setBet(type) {
        if (state.baccarat.status !== 'betting') return;
        const amount = this.selectedChip;
        // Usa interi (centesimi) per evitare floating point
        const currentCents = Math.round((state.baccarat.bets[type] || 0) * 100);
        const addCents = Math.round(amount * 100);
        state.baccarat.bets[type] = (currentCents + addCents) / 100;
        this.updateUI();
    },

    clearBets() {
        if (state.baccarat.status !== 'betting') return;
        state.baccarat.bets = { player: 0, banker: 0, tie: 0, player_pair: 0, banker_pair: 0 };
        this.updateUI();
    },

    isDealing: false,

    async deal() {
        if (this.isDealing) return;
        const totalCents = Object.values(state.baccarat.bets).reduce((a, b) => a + Math.round(b * 100), 0);
        const total = totalCents / 100;
        if (totalCents < 20) return alert("Puntata minima €0.20!");
        if (total > state.balance) return alert("Saldo insufficiente");

        this.isDealing = true;
        state.baccarat.status = 'dealing';
        state.baccarat.lastResult = null;

        const btn = document.querySelector('button[onclick="baccarat.deal()"]');
        if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; btn.innerText = '⏳ DISTRIBUZIONE...'; }

        this.updateUI();

        let res = null;
        try {
            res = await api.request('/baccarat/deal', {
                method: 'POST',
                body: JSON.stringify(state.baccarat.bets)
            });
        } catch(e) {
            console.error('Baccarat deal error:', e);
        }

        if (!res || !res.game) {
            state.baccarat.status = 'betting';
            this.isDealing = false;
            if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerText = 'DISTRIBUISCI'; }
            this.updateUI();
            return;
        }

        const g = res.game;
        const delay = ms => new Promise(r => setTimeout(r, ms));
        const pContainer = document.getElementById('bac-player-cards');
        const bContainer = document.getElementById('bac-banker-cards');
        if (pContainer) pContainer.innerHTML = '';
        if (bContainer) bContainer.innerHTML = '';

        const dealCard = (card, container) => {
            if (!container) return;
            const el = this.renderCardEl(card);
            el.classList.add('dealt-card');
            container.appendChild(el);
        };

        const msgEl = document.getElementById('bac-msg');

        if (msgEl) { msgEl.innerHTML = 'Distribuzione...'; msgEl.style.color = 'white'; }
        dealCard(g.player[0], pContainer); await delay(380);
        dealCard(g.banker[0], bContainer); await delay(380);
        dealCard(g.player[1], pContainer); await delay(380);
        dealCard(g.banker[1], bContainer); await delay(380);

        document.getElementById('bac-player-score').innerText = g.player_score;
        document.getElementById('bac-banker-score').innerText = g.banker_score;

        if (g.player.length > 2) {
            if (msgEl) msgEl.innerHTML = 'Terza carta al Giocatore...';
            await delay(300);
            dealCard(g.player[2], pContainer);
            await delay(380);
        }
        if (g.banker.length > 2) {
            if (msgEl) msgEl.innerHTML = 'Terza carta al Banco...';
            await delay(300);
            dealCard(g.banker[2], bContainer);
            await delay(380);
        }

        document.getElementById('bac-player-score').innerText = g.player_score;
        document.getElementById('bac-banker-score').innerText = g.banker_score;
        await delay(400);

        state.baccarat.player_hand = g.player;
        state.baccarat.banker_hand = g.banker;
        state.baccarat.player_score = g.player_score;
        state.baccarat.banker_score = g.banker_score;
        state.baccarat.winner = g.winner;
        state.baccarat.lastResult = g;
        state.baccarat.status = 'result';

        state.balance = res.balance;
        const balEl = document.getElementById('user-balance-nav');
        if (balEl) balEl.innerText = `Saldo: €${res.balance.toFixed(2)}`;

        this.showResult(g);
        this.isDealing = false;
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerText = 'DISTRIBUISCI'; }

        setTimeout(() => {
            if (state.baccarat.status === 'result') this.reset();
        }, 5000);
    },

    showResult(g) {
        const msgEl = document.getElementById('bac-msg');
        if (!msgEl) return;
        const winner = g.winner === 'tie' ? '🤝 PAREGGIO' : (g.winner === 'player' ? '🔵 PUNTO VINCE' : '🔴 BANCO VINCE');
        let pairs = '';
        if (g.player_pair) pairs += `<span style="font-size:0.8rem;color:#00ff88"> +PLAYER PAIR ×${g.player_pair_mult}</span>`;
        if (g.banker_pair) pairs += `<span style="font-size:0.8rem;color:#ffd700"> +BANKER PAIR ×${g.banker_pair_mult}</span>`;
        const profit = g.payout - g.total_bet;
        const col = profit >= 0 ? '#00ff88' : '#ff4444';
        const profitStr = (profit >= 0 ? '+' : '') + '€' + profit.toFixed(2);
        msgEl.innerHTML = `<div style="font-size:1.2rem;font-weight:900">${winner}${pairs}</div><div style="font-size:1.7rem;color:${col};margin-top:4px;font-weight:900">${profitStr}</div>`;
        msgEl.style.color = 'gold';
    },

    reset() {
        state.baccarat.status = 'betting';
        state.baccarat.player_hand = [];
        state.baccarat.banker_hand = [];
        state.baccarat.bets = { player: 0, banker: 0, tie: 0, player_pair: 0, banker_pair: 0 };
        this.updateUI();
    },

    updateUI() {
        if (!document.getElementById('bac-chip-020')) this.initChips();

        document.getElementById('bac-player-score').innerText = state.baccarat.player_hand.length ? state.baccarat.player_score : '0';
        document.getElementById('bac-banker-score').innerText = state.baccarat.banker_hand.length ? state.baccarat.banker_score : '0';

        for (const [type, amt] of Object.entries(state.baccarat.bets)) {
            const el = document.getElementById(`bac-bet-${type}`);
            if (el) el.innerText = amt > 0 ? `€${amt.toFixed(2)}` : '';
        }

        ['player','banker','tie','player_pair','banker_pair'].forEach(type => {
            const zone = document.getElementById(`bac-zone-${type}`);
            if (!zone) return;
            zone.style.opacity = state.baccarat.bets[type] > 0 ? '1' : (state.baccarat.status === 'betting' ? '0.85' : '0.6');
        });

        const msg = document.getElementById('bac-msg');
        if (!msg) return;
        if (state.baccarat.status === 'betting') {
            msg.innerHTML = 'Piazza le tue fiches';
            msg.style.color = 'gold';
            const pCards = document.getElementById('bac-player-cards');
            const bCards = document.getElementById('bac-banker-cards');
            if (pCards) pCards.innerHTML = '';
            if (bCards) bCards.innerHTML = '';
        } else if (state.baccarat.status === 'dealing') {
            msg.innerHTML = 'Distribuzione...';
            msg.style.color = 'white';
        }
    },

    renderCardEl(card) {
        const isRed = card.suit === '♥' || card.suit === '♦';
        const suitColor = isRed ? '#cc0000' : '#111';
        // rank font più piccolo per 10 (2 cifre)
        const rankSize = card.rank === '10' ? '0.75rem' : '0.9rem';

        const div = document.createElement('div');
        div.style.cssText = `
            width: 58px;
            height: 86px;
            background: white;
            border-radius: 9px;
            border: 1.5px solid #c0c0c0;
            box-shadow: 2px 4px 14px rgba(0,0,0,0.55);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 5px 5px 4px;
            flex-shrink: 0;
            color: ${suitColor};
            font-family: 'Georgia', serif;
            user-select: none;
        `;

        // Angolo top-left
        const tl = document.createElement('div');
        tl.style.cssText = `line-height:1; font-weight:700;`;
        tl.innerHTML = `<div style="font-size:${rankSize};">${card.rank}</div><div style="font-size:0.8rem; margin-top:1px;">${card.suit}</div>`;

        // Seme centrale
        const center = document.createElement('div');
        center.style.cssText = `font-size:1.8rem; text-align:center; line-height:1;`;
        center.innerText = card.suit;

        // Angolo bottom-right (ruotato)
        const br = document.createElement('div');
        br.style.cssText = `line-height:1; font-weight:700; transform:rotate(180deg); text-align:left;`;
        br.innerHTML = `<div style="font-size:${rankSize};">${card.rank}</div><div style="font-size:0.8rem; margin-top:1px;">${card.suit}</div>`;

        div.appendChild(tl);
        div.appendChild(center);
        div.appendChild(br);
        return div;
    }
};

window.onload = () => {
    if (state.token) {
        ui.showDashboard();
        dashboard.init();
        router.navigate('odds');
    }
};
