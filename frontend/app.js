const state = {
    token: localStorage.getItem('token'),
    role: localStorage.getItem('role'),
    username: localStorage.getItem('username'),
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
            let data;
            try {
                data = await response.json();
            } catch(e) {
                if (!response.ok) {
                    alert(`Errore server (${response.status})`);
                    return null;
                }
                return {}; // empty success
            }

            if (!response.ok) {
                const msg = data?.detail || `Errore ${response.status}`;
                alert(`Errore: ${msg}`);
                return null;
            }
            return data;
        } catch (e) {
            console.error('API Error:', e);
            alert(`Errore di connessione o del server. Controlla la console.`);
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
            state.username = username;
            localStorage.setItem('token', res.access_token);
            localStorage.setItem('role', res.role);
            localStorage.setItem('username', username);
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
        state.username = null;
        localStorage.clear();
        location.reload();
    },
};

window.ui = {
    showDashboard() {
        document.getElementById('login-page').classList.add('hidden');
        document.getElementById('main-dashboard').classList.remove('hidden');
        if (state.role === 'admin') {
            document.getElementById('nav-admin').classList.remove('hidden');
            const mobAdmin = document.getElementById('mob-nav-admin');
            if (mobAdmin) mobAdmin.classList.remove('hidden');
            const timerArea = document.getElementById('admin-timer-area');
            if (timerArea) timerArea.style.display = 'flex';
        }
        // Mostra link Profilo nella nav desktop
        const navProfile = document.getElementById('nav-profile');
        if (navProfile) navProfile.classList.remove('hidden');
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

        // Salva l'evento corrente e mostra la schermata dedicata
        state._currentMatchEvent = event;
        matchDetail.open(event);
    },
        closeAllOdds() {
        document.getElementById('all-odds-modal').classList.add('hidden');
    },
    async fetchBalance() {
        const res = await api.request('/user/balance');
        if (res) {
            state.balance = res.balance;
            if (res.username) state.username = res.username;
            document.getElementById('user-balance-nav').innerText = `Saldo: €${state.balance.toFixed(2)}`;
            // Aggiorna profilo se aperto
            const profileBalance = document.getElementById('profile-balance');
            if (profileBalance) profileBalance.innerText = `€${state.balance.toFixed(2)}`;
            const profileUsername = document.getElementById('profile-username');
            if (profileUsername && res.username) profileUsername.innerText = res.username;
            const avatarLetter = document.getElementById('profile-avatar-letter');
            if (avatarLetter && res.username) avatarLetter.innerText = res.username[0].toUpperCase();
        }
    }
};

const router = {
    navigate(section) {
        const sections = ['odds', 'admin', 'mybets', 'casino', 'crash', 'blackjack', 'sette-mezzo', 'baccarat', 'virtual', 'profile'];
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
            'virtual': 'nav-casino',
            'profile': 'nav-profile'
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
            'virtual': 'mob-nav-casino',
            'profile': 'mob-nav-profile'
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
        if (section === 'profile') profile.init();
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
    _activeLeagueFilter: 'today',

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
            this.renderLeagueFilters([]);
            return;
        }

        const cutoff = new Date(Date.now() + 60 * 1000);
        let filteredOdds = state.odds.filter(e => !e.commence_time || new Date(e.commence_time) > cutoff);

        // Costruisci filtri lega
        this.renderLeagueFilters(filteredOdds);

        // Applica filtro lega attivo
        const activeFilter = this._activeLeagueFilter;
        if (activeFilter === 'today') {
            const today = new Date();
            const todayStr = today.toDateString();
            const tomorrowStr = new Date(today.getTime() + 86400000).toDateString();
            filteredOdds = filteredOdds.filter(e => {
                const d = new Date(e.commence_time).toDateString();
                return d === todayStr || d === tomorrowStr;
            });
        } else if (activeFilter !== 'all') {
            filteredOdds = filteredOdds.filter(e => (e.sport_title || '') === activeFilter);
        }

        if (query) {
            filteredOdds = filteredOdds.filter(event => {
                const h = (event.home_team || '').toLowerCase();
                const a = (event.away_team || '').toLowerCase();
                const s = (event.sport_title || '').toLowerCase();
                return h.includes(query) || a.includes(query) || s.includes(query);
            });
        }

        if (filteredOdds.length === 0) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-secondary);">Nessun match trovato.</div>`;
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

            const btts = bookmaker?.markets.find(m => m.key === 'btts');
            const goalPrice = btts?.outcomes.find(o => ['Yes', 'Goal'].includes(o.name))?.price;
            const nogoalPrice = btts?.outcomes.find(o => ['No', 'No Goal'].includes(o.name))?.price;

            const totals = bookmaker?.markets.find(m => m.key === 'totals');
            const over25Price = totals?.outcomes.find(o => o.name.includes('Over') && o.point === 2.5)?.price;
            const under25Price = totals?.outcomes.find(o => o.name.includes('Under') && o.point === 2.5)?.price;

            const eventDate = new Date(event.commence_time);
            const dateStr = eventDate.toLocaleDateString('it-IT', {day:'2-digit', month:'2-digit'});
            const timeStr = eventDate.toLocaleTimeString('it-IT', {hour:'2-digit', minute:'2-digit'});
            const isToday = eventDate.toDateString() === new Date().toDateString();
            const dayLabel = isToday ? 'Oggi' : dateStr;

            return `
            <div class="odd-card fade-in">
                <div class="sport-tag">${event.sport_title}</div>
                <div class="event-name" title="${event.home_team} vs ${event.away_team}">
                    ${event.home_team} vs ${event.away_team}
                </div>
                <div style="font-size: 0.7rem; color: var(--text-secondary); margin-bottom: 0.8rem; display:flex; align-items:center; gap:6px;">
                    <span style="background:rgba(99,179,237,0.15); color:var(--accent); padding:1px 7px; border-radius:10px; font-weight:600;">${dayLabel}</span>
                    <span>${timeStr}</span>
                </div>
                
                <div class="main-prices" style="margin-bottom: 8px;">
                    <div class="price-btn ${isHomeSel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', '${event.home_team}', ${homePrice?.price || 0})">
                        <span class="label">1</span>
                        <span class="val">${homePrice?.price.toFixed(2) || '-'}</span>
                    </div>
                    ${drawPrice ? `<div class="price-btn ${isDrawSel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', 'Pareggio', ${drawPrice.price})">
                        <span class="label">X</span>
                        <span class="val">${drawPrice.price.toFixed(2)}</span>
                    </div>` : ''}
                    <div class="price-btn ${isAwaySel ? 'selected' : ''}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'h2h', '${event.away_team}', ${awayPrice?.price || 0})">
                        <span class="label">2</span>
                        <span class="val">${awayPrice?.price.toFixed(2) || '-'}</span>
                    </div>
                </div>

                <div style="display: flex; gap: 5px; margin-bottom: 10px;">
                    <div class="price-btn mini ${goalPrice ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'btts', 'Goal', ${goalPrice || 0})" style="flex:1; padding: 5px;" title="Goal Goal - Entrambe segnano">
                        <span class="label" style="font-size:0.6rem">GG</span>
                        <span class="val" style="font-size:0.75rem">${goalPrice?.toFixed(2) || ''}</span>
                    </div>
                    <div class="price-btn mini ${nogoalPrice ? '' : 'hidden'}" onclick="bets.addToSlip('${event.id}', '${event.home_team} vs ${event.away_team}', 'btts', 'No Goal', ${nogoalPrice || 0})" style="flex:1; padding: 5px;" title="No Goal - Almeno una non segna">
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
    },

    renderLeagueFilters(odds) {
        const bar = document.getElementById('league-filter-bar');
        if (!bar) return;

        // Raccogli leghe uniche
        const leagueSet = new Set();
        const today = new Date().toDateString();
        const tomorrow = new Date(Date.now() + 86400000).toDateString();
        let hasTodayTomorrow = false;
        odds.forEach(e => {
            if (e.sport_title) leagueSet.add(e.sport_title);
            const d = new Date(e.commence_time).toDateString();
            if (d === today || d === tomorrow) hasTodayTomorrow = true;
        });

        const leagues = [...leagueSet].sort();
        const active = this._activeLeagueFilter;

        const btn = (key, label, icon='') => {
            const isActive = active === key;
            return `<button onclick="dashboard.setLeagueFilter('${key}')" style="
                width:auto!important; display:inline-block!important; white-space:nowrap!important;
                padding:6px 14px; border-radius:20px; border:none; cursor:pointer;
                font-size:0.78rem; font-weight:${isActive?'700':'500'};
                background:${isActive?'var(--accent)':'rgba(255,255,255,0.07)'};
                background-image:none!important;
                color:${isActive?'#0a0a1a':'var(--text-secondary)'};
                transition:all 0.2s; flex-shrink:0; text-transform:none; letter-spacing:normal;
                box-shadow:none;
            ">${icon}${label}</button>`;
        };

        let html = btn('all', 'Tutte', '🌐 ');
        if (hasTodayTomorrow) html += btn('today', 'Oggi / Domani', '📅 ');
        leagues.forEach(l => {
            const short = l.replace(' - ITALY','').replace(' - ENGLAND','').replace(' - SPAIN','')
                          .replace(' - GERMANY','').replace(' - FRANCE','').replace(' - EUROPE','');
            html += btn(l, short);
        });

        bar.innerHTML = html;
    },

    setLeagueFilter(key) {
        this._activeLeagueFilter = key;
        this.renderOdds();
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

        const tabEl = document.getElementById(`admin-tab-${tabName}`);
        if (tabEl) tabEl.classList.remove('hidden');

        // Find active button safely without querySelector attribute selector issues
        document.querySelectorAll('.admin-tab').forEach(btn => {
            if (btn.onclick && btn.onclick.toString().includes(`'${tabName}'`)) {
                btn.classList.add('active');
            }
        });

        if (tabName === 'dashboard') this.loadDashboardKPIs();
        if (tabName === 'deposits') this.loadDeposits();
        if (tabName === 'withdrawals') this.loadWithdrawals();
        if (tabName === 'bonuses') this.loadAdminBonuses();
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
        if (!detail.bets || detail.bets.length === 0) {
            betsContainer.innerHTML = '<p style="color:var(--text-secondary); text-align:center; padding:1rem;">Nessuna scommessa sportiva.</p>';
        } else {
            betsContainer.innerHTML = detail.bets.map(b => {
                const betDate = b.created_at ? new Date(b.created_at) : null;
                const betTimeStr = betDate ? betDate.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) + ' — ' + betDate.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '';
                return `
                <div style="background:rgba(255,255,255,0.05); padding:1rem; border-radius:8px; margin-bottom:1rem; border-left: 4px solid ${b.status === 'won' ? 'var(--success)' : b.status === 'lost' ? 'var(--danger)' : b.status === 'cancelled' ? 'var(--text-secondary)' : 'var(--accent)'}">
                    <div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">
                         <span>€${Number(b.amount).toFixed(2)} → €${Number(b.potential_win).toFixed(2)}</span>
                         ${betTimeStr ? `<span style="color:var(--text-secondary); font-size:0.75rem;">🕐 ${betTimeStr}</span>` : ''}
                    </div>
                    ${(b.selections || []).map(s => {
                        let scoreBadge = '';
                        if (s.v_score !== undefined) {
                            let textOpts = {'scheduled': 'In Arrivo', 'live': 'Live', 'finished': 'Terminata'};
                            let bg = s.v_status === 'finished' ? '#ffd700' : (s.v_status === 'live' ? '#ff4d4d' : '#4caf50');
                            scoreBadge = `<span style="background:${bg}; color:#000; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.75rem; margin-left:10px;">Risultato: ${s.v_score} (${textOpts[s.v_status] || s.v_status})</span>`;
                        }
                        return `
                        <div style="font-size:0.85rem; margin-bottom:3px; opacity:0.8; display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
                            • ${s.home_team} vs ${s.away_team}: <b>${s.selection}</b> <span>@${Number(s.odds).toFixed(2)}</span> ${scoreBadge}
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
            `}).join('');
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
                        <div style="color: var(--text-secondary); font-size: 0.75rem;">${{
                        'admin_adjustment': '⚙️ Rettifica admin',
                        'deposit': '💳 Ricarica',
                        'withdrawal_requested': '🏦 Prelievo richiesto',
                        'withdrawal_approved': '✅ Prelievo approvato',
                        'withdrawal_rejected': '❌ Prelievo rifiutato',
                    }[t.type] || t.type} ${t.reason ? '— ' + t.reason : ''}</div>
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

        // Render casino bets
        window.admin._casinoBets = detail.casino_bets || [];
        window.admin._renderCasinoBets(window.admin._casinoBets);
    },
    _renderCasinoBets(bets) {
        const container = document.getElementById('detail-casino-container');
        if (!container) return;
        if (!bets || bets.length === 0) {
            container.innerHTML = '<p style="color:var(--text-secondary); text-align:center; padding:1rem;">Nessuna giocata casino.</p>';
            return;
        }
        const gameIcons = {
            'Blackjack': '🃏', 'Baccarat': '🎴', 'Sette e Mezzo': '7️⃣'
        };
        container.innerHTML = bets.map(b => {
            let timeStr = '--:--', dateStr = '--/--/--';
            try {
                const date = new Date(b.created_at);
                if (!isNaN(date)) {
                    timeStr = date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
                    dateStr = date.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' });
                }
            } catch(e) {}
            const isWin = b.status === 'won';
            const isLoss = b.status === 'lost';
            const amount = Number(b.amount) || 0;
            const payout = Number(b.payout) || 0;
            const netChange = isWin ? (payout - amount) : (isLoss ? -amount : 0);
            // Crash icon: check event_id or game name
            const isCrash = (b.event_id === 'casino_crash' || (b.game && b.game.toLowerCase().startsWith('crash')));
            const icon = isCrash ? '💥' : (gameIcons[b.game] || '🎰');
            const borderColor = isWin ? 'var(--success)' : isLoss ? 'var(--danger)' : 'var(--text-secondary)';
            return `
                <div style="display:flex; align-items:center; gap:12px; padding:10px 8px; border-bottom:1px solid rgba(255,255,255,0.06); border-left:3px solid ${borderColor}; margin-bottom:4px;">
                    <div style="font-size:1.4rem; min-width:28px; text-align:center;">${icon}</div>
                    <div style="flex:1; min-width:0;">
                        <div style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
                            <span style="font-weight:bold; color:var(--text-primary);">${b.game || 'Casino'}</span>
                            <span style="color:var(--text-secondary); font-size:0.75rem;">🕐 ${timeStr} — ${dateStr}</span>
                        </div>
                        <div style="display:flex; gap:16px; margin-top:4px; font-size:0.8rem; flex-wrap:wrap;">
                            <span>Puntata: <b style="color:var(--text-primary);">€${amount.toFixed(2)}</b></span>
                            <span>Ritorno: <b style="color:${isWin ? 'var(--success)' : 'var(--text-secondary)'};">€${payout.toFixed(2)}</b></span>
                            <span style="color:${netChange >= 0 ? 'var(--success)' : 'var(--danger)'}; font-weight:bold;">
                                ${netChange >= 0 ? '+' : ''}€${netChange.toFixed(2)}
                            </span>
                        </div>
                    </div>
                    <div style="text-align:right; font-size:0.75rem; font-weight:bold; text-transform:uppercase; color:${borderColor}; min-width:40px;">${b.status || ''}</div>
                </div>
            `;
        }).join('');
    },
    filterCasino(type) {
        document.querySelectorAll('.casino-filter-btn').forEach(btn => {
            btn.style.background = 'rgba(255,255,255,0.1)';
        });
        const activeBtn = document.getElementById(`casino-filter-${type}`);
        if (activeBtn) activeBtn.style.background = 'var(--accent)';

        const allBets = window.admin._casinoBets || [];
        const filtered = type === 'all' ? allBets : allBets.filter(b => (b.game || '').toLowerCase().includes(type));
        window.admin._renderCasinoBets(filtered);
    },
    _casinoBets: [],
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
    async loadDeposits() {
        const container = document.getElementById('admin-deposits-container');
        if (!container) return;
        container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Caricamento...</div>';
        const data = await api.request('/admin/deposits');
        if (!data) {
            container.innerHTML = '<div style="text-align:center;color:var(--danger);padding:2rem;">Errore caricamento.</div>';
            return;
        }
        if (data.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Nessuna richiesta di ricarica.</div>';
            return;
        }
        const statusColors = { pending: '#f59e0b', approved: 'var(--success)', rejected: 'var(--danger)' };
        const statusLabels = { pending: '⏳ In attesa', approved: '✅ Approvata', rejected: '❌ Rifiutata' };
        container.innerHTML = data.map(d => `
            <div style="background:var(--card-bg);border:1px solid var(--border-color);border-left:4px solid ${statusColors[d.status]||'#aaa'};border-radius:10px;padding:1rem;margin-bottom:0.8rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.5rem;">
                    <div style="display:flex;gap:8px;align-items:center;">
                        <span style="font-weight:800;color:var(--accent);">${d.username}</span>
                        <span style="font-size:0.75rem;color:var(--text-secondary);">#${d.id} · ${d.created_at ? new Date(d.created_at).toLocaleString('it-IT') : '---'}</span>
                    </div>
                    <span style="font-weight:900;color:${statusColors[d.status]||'#aaa'};font-size:0.85rem;">${statusLabels[d.status]||d.status}</span>
                </div>
                <div style="font-size:0.88rem;margin-bottom:4px;">💶 Ricarica: <b>€${(d.amount||0).toFixed(2)}</b></div>
                ${parseFloat(d.bonus_amount||0) > 0 ? `<div style="font-size:0.82rem;color:#ffd700;margin-bottom:4px;">🎁 Bonus: <b>+€${parseFloat(d.bonus_amount).toFixed(2)}</b></div>` : ''}
                <div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:0.6rem;">Totale accredito se approvata: <b style="color:var(--success);">€${(parseFloat(d.amount||0)+parseFloat(d.bonus_amount||0)).toFixed(2)}</b></div>
                ${d.status === 'pending' ? `
                    <div style="display:flex;gap:8px;">
                        <button onclick="admin.resolveDeposit(event, ${d.id},'approved')" style="background:var(--success);width:auto;padding:5px 16px;font-size:0.82rem;">✅ Approva</button>
                        <button onclick="admin.resolveDeposit(event, ${d.id},'rejected')" style="background:var(--danger);width:auto;padding:5px 16px;font-size:0.82rem;">❌ Rifiuta</button>
                    </div>` : ''}
            </div>
        `).join('');
    },

    async resolveDeposit(e, did, status) {
        const btn = e.target;
        const originalText = btn.innerText;
        const label = status === 'approved' ? 'approvare' : 'rifiutare';
        if (!confirm(`Sei sicuro di voler ${label} questa ricarica?`)) return;
        
        btn.disabled = true;
        btn.innerText = 'Elaborazione...';
        
        const res = await api.request(`/admin/deposits/${did}/resolve`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        
        if (res) {
            this.loadDeposits();
        } else {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    },

    async loadWithdrawals() {
        const container = document.getElementById('admin-withdrawals-container');
        if (!container) return;
        container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Caricamento...</div>';
        const data = await api.request('/admin/withdrawals');
        if (!data) {
            container.innerHTML = '<div style="text-align:center;color:var(--danger);padding:2rem;">Errore caricamento. Le tabelle potrebbero non essere ancora create — riavvia il server.</div>';
            return;
        }
        if (data.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:2rem;">Nessuna richiesta di prelievo ancora.</div>';
            return;
        }
        const statusColors = { pending: 'var(--accent)', approved: 'var(--success)', rejected: 'var(--danger)' };
        const statusLabels = { pending: '⏳ In attesa', approved: '✅ Approvato', rejected: '❌ Rifiutato' };
        container.innerHTML = data.map(w => `
            <div style="background:var(--card-bg); border:1px solid var(--border-color); border-left:4px solid ${statusColors[w.status]||'#aaa'}; border-radius:10px; padding:1rem; margin-bottom:0.8rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.5rem;">
                    <div style="display:flex; gap:8px; align-items:center;">
                        <span style="font-weight:800; color:var(--accent);">${w.username}</span>
                        <span style="font-size:0.75rem; color:var(--text-secondary);">#${w.id} · ${w.created_at ? new Date(w.created_at).toLocaleString('it-IT') : '---'}</span>
                    </div>
                    <span style="font-weight:900; color:${statusColors[w.status]||'#aaa'}; font-size:0.85rem;">${statusLabels[w.status]||w.status}</span>
                </div>
                <div style="font-size:0.88rem; margin-bottom:4px;">💶 <b>€${(w.amount||0).toFixed(2)}</b></div>
                <div style="font-size:0.82rem; color:var(--text-secondary); font-family:monospace; margin-bottom:4px;">IBAN: ${w.iban}</div>
                <div style="font-size:0.82rem; color:var(--text-secondary); margin-bottom:0.6rem;">Intestatario: ${w.holder_name}</div>
                ${w.status === 'pending' ? `
                    <div style="display:flex; gap:8px;">
                        <button onclick="admin.resolveWithdrawal(event, ${w.id},'approved')" style="background:var(--success);width:auto;padding:5px 16px;font-size:0.82rem;">✅ Approva</button>
                        <button onclick="admin.resolveWithdrawal(event, ${w.id},'rejected')" style="background:var(--danger);width:auto;padding:5px 16px;font-size:0.82rem;">❌ Rifiuta</button>
                    </div>` : ''}
            </div>
        `).join('');
    },

    async resolveWithdrawal(e, wid, status) {
        const btn = e.target;
        const originalText = btn.innerText;
        const label = status === 'approved' ? 'approvare' : 'rifiutare';
        if (!confirm(`Sei sicuro di voler ${label} questo prelievo?`)) return;
        
        btn.disabled = true;
        btn.innerText = 'Elaborazione...';

        const res = await api.request(`/admin/withdrawals/${wid}/resolve`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        
        if (res) {
            this.loadWithdrawals();
        } else {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    },

    async loadAdminBonuses() {
        const container = document.getElementById('admin-bonuses-list');
        if (!container) return;

        // Popola select utenti (solo la prima volta)
        const userSelect = document.getElementById('bonus-user-target');
        if (userSelect && userSelect.options.length <= 1) {
            const users = await api.request('/admin/users');
            if (users) {
                users.forEach(u => {
                    const opt = document.createElement('option');
                    opt.value = u.id;
                    opt.innerText = u.username;
                    userSelect.appendChild(opt);
                });
            }
        }

        const data = await api.request('/admin/bonuses');
        if (!data || data.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:1.5rem;">Nessun bonus creato.</div>';
            return;
        }
        container.innerHTML = data.map(b => {
            const bonusParts = [];
            if (b.bonus_percent > 0) bonusParts.push(`+${b.bonus_percent}%`);
            if (b.bonus_fixed > 0) bonusParts.push(`+€${parseFloat(b.bonus_fixed).toFixed(2)}`);
            const isPersonal = b.assigned_to_user_id || b.assigned_username;
            return `
            <div style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color); border-left:4px solid ${isPersonal ? '#a855f7' : '#ffd700'}; border-radius:10px; padding:0.9rem 1rem; margin-bottom:0.7rem; display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap;">
                <div>
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <span style="font-weight:800; color:${isPersonal ? '#a855f7' : '#ffd700'};">${b.title}</span>
                        ${isPersonal
                            ? `<span style="font-size:0.7rem;background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid #a855f7;border-radius:20px;padding:1px 8px;">👤 ${b.assigned_username || 'utente #'+b.assigned_to_user_id}</span>`
                            : `<span style="font-size:0.7rem;background:rgba(255,215,0,0.15);color:#ffd700;border:1px solid #ffd700;border-radius:20px;padding:1px 8px;">🌍 Globale</span>`
                        }
                    </div>
                    <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">${b.description || '---'}</div>
                    <div style="font-size:0.78rem; margin-top:4px;">
                        Bonus: <b>${bonusParts.join(' + ') || '—'}</b>
                        &nbsp;·&nbsp; Min. ricarica: <b>€${parseFloat(b.min_deposit||0).toFixed(0)}</b>
                        &nbsp;·&nbsp; Stato: <b style="color:${b.active ? 'var(--success)' : 'var(--danger)'};">${b.active ? 'Attivo' : 'Disattivato'}</b>
                    </div>
                </div>
                ${b.active ? `<button onclick="admin.deleteBonus(${b.id})" style="background:var(--danger);width:auto;padding:5px 14px;font-size:0.82rem;flex-shrink:0;">Disattiva</button>` : ''}
            </div>`;
        }).join('');
    },

    async createBonus() {
        const title = document.getElementById('bonus-title').value.trim();
        const desc = document.getElementById('bonus-desc').value.trim();
        const min_deposit = parseFloat(document.getElementById('bonus-min').value || 0);
        const bonus_percent = parseInt(document.getElementById('bonus-percent').value || 0);
        const bonus_fixed = parseFloat(document.getElementById('bonus-fixed').value || 0);
        const max_deposit = parseFloat(document.getElementById('bonus-max')?.value || 0);
        const userTarget = document.getElementById('bonus-user-target').value;
        const assigned_to_user_id = userTarget ? parseInt(userTarget) : null;

        if (!title) return alert('Inserisci un titolo per il bonus');
        if (bonus_percent === 0 && bonus_fixed === 0) return alert('Inserisci almeno un bonus (% o fisso)');

        const res = await api.request('/admin/bonuses', {
            method: 'POST',
            body: JSON.stringify({ title, description: desc, min_deposit, max_deposit, bonus_percent, bonus_fixed, assigned_to_user_id })
        });
        if (res) {
            document.getElementById('bonus-title').value = '';
            document.getElementById('bonus-desc').value = '';
            document.getElementById('bonus-min').value = '0';
            if (document.getElementById('bonus-max')) document.getElementById('bonus-max').value = '0';
            document.getElementById('bonus-percent').value = '0';
            document.getElementById('bonus-fixed').value = '0';
            document.getElementById('bonus-user-target').value = '';
            this.loadAdminBonuses();
        }
    },

    async deleteBonus(bid) {
        if (!confirm('Disattivare questo bonus? Gli utenti non potranno più usarlo.')) return;
        const res = await api.request(`/admin/bonuses/${bid}`, { method: 'DELETE' });
        if (res) this.loadAdminBonuses();
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
            // Blocca scommesse virtuali se non siamo in fase BETTING
            if (String(eventId).startsWith('v_') && state.virtual.status !== 'BETTING') {
                alert('Le scommesse virtuali sono chiuse. Attendi la prossima giornata.');
                return;
            }
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
        if (!odds || odds < 1.01) return; // quota non valida, non aggiungere
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
            alert('L\'importo minimo della scommessa è €0.20');
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
        const tbodyMobile = document.getElementById('virtual-standings-body-mobile');
        if (!tbody && !tbodyMobile) return;

        if (!state.virtual.standings || !Array.isArray(state.virtual.standings)) return;

        try {
            const rows = state.virtual.standings.map((s, i) => `
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
            if (tbody) tbody.innerHTML = rows;
            if (tbodyMobile) tbodyMobile.innerHTML = rows;

            // Gestione visibilità: JS è più affidabile delle media query su Safari iOS
            const isMobile = window.innerWidth <= 900;
            const sidebar = document.querySelector('.virtual-sidebar');
            const mobileWrap = document.getElementById('virtual-standings-mobile-wrap');
            if (sidebar) sidebar.style.display = isMobile ? 'none' : '';
            if (mobileWrap) mobileWrap.style.display = isMobile ? 'block' : 'none';
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

window.profile = {
    _bonuses: [],
    _selectedBonusId: null,

    init() {
        // Usa immediatamente i dati già in state (sincrono, nessuna attesa)
        const username = state.username || localStorage.getItem('username') || '---';
        const balance = state.balance || 0;

        const g = (id) => document.getElementById(id);
        if (g('profile-username')) g('profile-username').innerText = username;
        if (g('profile-avatar-letter')) g('profile-avatar-letter').innerText = username !== '---' ? username[0].toUpperCase() : '?';
        if (g('profile-balance')) g('profile-balance').innerText = `€${balance.toFixed(2)}`;
        if (g('deposit-username-hint')) g('deposit-username-hint').innerText = username;

        // Poi aggiorna in background
        this._refreshAndLoadBonuses();
    },

    async _refreshAndLoadBonuses() {
        const res = await api.request('/user/balance');
        if (res) {
            state.balance = res.balance;
            state.username = res.username || state.username;
            if (res.username) localStorage.setItem('username', res.username);
            const g = (id) => document.getElementById(id);
            const u = state.username || '---';
            if (g('profile-username')) g('profile-username').innerText = u;
            if (g('profile-avatar-letter')) g('profile-avatar-letter').innerText = u !== '---' ? u[0].toUpperCase() : '?';
            if (g('profile-balance')) g('profile-balance').innerText = `€${res.balance.toFixed(2)}`;
            if (g('deposit-username-hint')) g('deposit-username-hint').innerText = u;
            if (g('user-balance-nav')) g('user-balance-nav').innerText = `Saldo: €${res.balance.toFixed(2)}`;
        }
        await this.loadBonuses();
    },

    async loadBonuses() {
        const bonuses = await api.request('/bonuses');
        this._bonuses = bonuses || [];
        const container = document.getElementById('profile-bonuses-list');
        if (!container) return;

        if (!bonuses || bonuses.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);font-size:0.85rem;padding:0.8rem 0;">Nessun bonus disponibile al momento.</div>';
            return;
        }

        container.innerHTML = bonuses.map(b => {
            const used = b.already_used;
            const isPersonal = !!b.is_personal;
            const borderColor = used ? 'rgba(255,255,255,0.08)' : (isPersonal ? '#a855f7' : '#ffd700');
            const titleColor = used ? 'var(--text-secondary)' : (isPersonal ? '#a855f7' : '#ffd700');
            const parts = [];
            if (b.bonus_percent > 0) parts.push(`+${b.bonus_percent}%`);
            if (b.bonus_fixed > 0) parts.push(`+€${parseFloat(b.bonus_fixed).toFixed(2)}`);
            if (b.min_deposit > 0) parts.push(`min. €${parseFloat(b.min_deposit).toFixed(0)}`);

            return `<div style="border:2px solid ${borderColor}; border-radius:12px; padding:0.8rem 1rem; display:flex; justify-content:space-between; align-items:center; gap:0.8rem; margin-bottom:8px; ${used ? 'opacity:0.4;' : ''}">
                <div style="flex:1; min-width:0;">
                    <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:2px;">
                        <b style="color:${titleColor}; font-size:0.9rem;">${b.title}</b>
                        ${isPersonal && !used ? '<span style="font-size:0.65rem;background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid #a855f7;border-radius:20px;padding:1px 7px;">🎁 Solo per te</span>' : ''}
                    </div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);">${b.description || parts.join(' · ')}</div>
                    <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:1px;">${parts.join(' · ')}</div>
                </div>
                <div style="flex-shrink:0;">
                    ${used
                        ? '<span style="font-size:0.75rem;color:var(--text-secondary);">✅ Usato</span>'
                        : `<button onclick="profile.openDepositWithBonus(${b.id})"
                            style="background:${isPersonal ? '#a855f7' : '#ffd700'};color:#000;border:none;border-radius:8px;padding:7px 14px;font-weight:800;font-size:0.8rem;cursor:pointer;">
                            Usa
                          </button>`
                    }
                </div>
            </div>`;
        }).join('');
    },

    openDepositWithBonus(bonusId) {
        this._selectedBonusId = bonusId;
        this.openDeposit('card');
    },

    openDeposit(method) {
        const icons = { card: '💳', apple: '🍎', google: 'G' };
        const names = { card: 'Carta di credito / debito', apple: 'Apple Pay', google: 'Google Pay' };
        const g = (id) => document.getElementById(id);
        if (g('deposit-method-icon')) g('deposit-method-icon').innerText = icons[method] || '💳';
        if (g('deposit-method-name')) g('deposit-method-name').innerText = names[method] || 'Ricarica';
        const username = state.username || localStorage.getItem('username') || '---';
        if (g('deposit-username-hint')) g('deposit-username-hint').innerText = username;
        this.renderDepositBonuses();
        const modal = g('modal-deposit');
        if (modal) { modal.classList.add('visible'); document.body.style.overflow = 'hidden'; }
    },

    closeDeposit() {
        const modal = document.getElementById('modal-deposit');
        if (modal) { modal.classList.remove('visible'); document.body.style.overflow = ''; }
    },

    renderDepositBonuses() {
        const available = this._bonuses.filter(b => !b.already_used);
        const section = document.getElementById('deposit-bonus-section');
        const listEl = document.getElementById('deposit-bonus-list');
        if (!section || !listEl) return;

        if (available.length === 0) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';

        listEl.innerHTML = available.map(b => {
            const sel = this._selectedBonusId === b.id;
            const color = sel ? '#ffd700' : 'rgba(255,255,255,0.12)';
            const bg = sel ? 'rgba(255,215,0,0.08)' : 'transparent';
            return `<div onclick="profile.selectBonus(${b.id})"
                style="border:2px solid ${color};border-radius:10px;padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;background:${bg};margin-bottom:6px;transition:all 0.15s;">
                <div>
                    <div style="font-weight:700;font-size:0.85rem;color:${sel ? '#ffd700' : 'white'};">${b.title}</div>
                    <div style="font-size:0.72rem;color:var(--text-secondary);">${b.description || ''}</div>
                </div>
                <span style="font-size:1.1rem;">${sel ? '✅' : '⬜'}</span>
            </div>`;
        }).join('') + `<div onclick="profile.selectBonus(null)"
            style="border:2px solid ${!this._selectedBonusId ? '#ffd700' : 'rgba(255,255,255,0.12)'};border-radius:10px;padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;background:${!this._selectedBonusId ? 'rgba(255,215,0,0.08)' : 'transparent'};transition:all 0.15s;">
            <div style="font-size:0.85rem;color:var(--text-secondary);">Nessun bonus</div>
            <span style="font-size:1.1rem;">${!this._selectedBonusId ? '✅' : '⬜'}</span>
        </div>`;
    },

    selectBonus(id) {
        this._selectedBonusId = id;
        this.renderDepositBonuses();
    },

    onDepositAmountChange() {
        // placeholder — nessuna azione necessaria per ora
    },

    // Apre SumUp E invia richiesta di ricarica in attesa di approvazione admin
    async proceedDeposit() {
        const amountEl = document.getElementById('deposit-amount-input');
        const amount = parseFloat(amountEl ? amountEl.value : 0);

        if (!amount || amount <= 0) {
            alert('Inserisci un importo valido prima di procedere.');
            return;
        }

        const PAY_URL = 'https://pay.sumup.com/b2c/QEAW96U8';

        // 1. Apri la finestra SUBITO — prima di qualsiasi await
        //    Safari blocca window.open() se chiamato dopo operazioni async.
        //    Usiamo meta refresh invece di location.href: Safari lo considera
        //    navigazione interna alla finestra già aperta, non un nuovo popup.
        const payWin = window.open('', '_blank');
        if (payWin) {
            payWin.document.write(
                '<html><head>' +
                '<title>Reindirizzamento pagamento...</title>' +
                '<meta name="viewport" content="width=device-width,initial-scale=1">' +
                '</head><body style="font-family:sans-serif;display:flex;flex-direction:column;' +
                'align-items:center;justify-content:center;height:100vh;margin:0;' +
                'background:#1a1a2e;color:#fff;gap:16px;">' +
                '<p style="font-size:1.2rem;margin:0;">⏳ Reindirizzamento al pagamento...</p>' +
                '<p style="font-size:0.85rem;color:#aaa;margin:0;">Non chiudere questa finestra</p>' +
                '</body></html>'
            );
            payWin.document.close();
        }

        // 2. Invia richiesta al backend
        const res = await api.request('/deposit/request', {
            method: 'POST',
            body: JSON.stringify({ amount, bonus_id: this._selectedBonusId || null })
        });

        if (!res) {
            if (payWin && !payWin.closed) payWin.close();
            return;
        }

        // 3. Reindirizza — metodo universale cross-browser incluso Safari
        if (payWin && !payWin.closed) {
            // Prima prova location.href (funziona su Chrome/Firefox)
            try {
                payWin.location.href = PAY_URL;
            } catch(e) {
                // Safari fallback: riscrivi la pagina con meta refresh immediato
                payWin.document.open();
                payWin.document.write(
                    '<html><head>' +
                    '<meta http-equiv="refresh" content="0;url=' + PAY_URL + '">' +
                    '<title>Reindirizzamento...</title>' +
                    '</head><body style="font-family:sans-serif;display:flex;align-items:center;' +
                    'justify-content:center;height:100vh;margin:0;background:#1a1a2e;color:#fff;">' +
                    '<p>Reindirizzamento...</p>' +
                    '<script>window.location.replace("' + PAY_URL + '")<\/script>' +
                    '</body></html>'
                );
                payWin.document.close();
            }
        } else {
            // Finestra chiusa dall'utente: apri link direttamente nella pagina corrente
            window.location.href = PAY_URL;
        }

        // 4. Reset e chiudi modal
        if (amountEl) amountEl.value = '';
        this._selectedBonusId = null;
        this.closeDeposit();

        const bonusMsg = parseFloat(res.bonus_amount||0) > 0
            ? '\n🎁 Bonus di €' + parseFloat(res.bonus_amount).toFixed(2) + ' verrà accreditato dopo approvazione.'
            : '';
        alert('✅ ' + res.message + bonusMsg);
    },

    async applyBonus(bonusId, amount) {
        const bonus = this._bonuses.find(b => b.id === bonusId);
        if (!bonus) return;
        if (amount < (bonus.min_deposit || 0)) {
            alert(`⚠️ Importo minimo per questo bonus: €${bonus.min_deposit}`);
            return;
        }
        const res = await api.request('/bonuses/apply', {
            method: 'POST',
            body: JSON.stringify({ bonus_id: bonusId, deposit_amount: amount })
        });
        if (res && res.new_balance !== undefined) {
            state.balance = res.new_balance;
            const navEl = document.getElementById('user-balance-nav');
            if (navEl) navEl.innerText = `Saldo: €${res.new_balance.toFixed(2)}`;
            const profileBal = document.getElementById('profile-balance');
            if (profileBal) profileBal.innerText = `€${res.new_balance.toFixed(2)}`;
            alert(`🎁 ${res.message}`);
            await this.loadBonuses();
        }
    },

    openWithdrawal() {
        const modal = document.getElementById('modal-withdrawal');
        if (modal) { modal.classList.add('visible'); document.body.style.overflow = 'hidden'; }
    },

    closeWithdrawal() {
        const modal = document.getElementById('modal-withdrawal');
        if (modal) { modal.classList.remove('visible'); document.body.style.overflow = ''; }
    },

    async submitWithdrawal() {
        const amountEl = document.getElementById('wd-amount');
        const ibanEl = document.getElementById('wd-iban');
        const nameEl = document.getElementById('wd-name');
        const amount = parseFloat(amountEl ? amountEl.value : 0);
        const iban = ibanEl ? ibanEl.value.trim() : '';
        const name = nameEl ? nameEl.value.trim() : '';

        if (!amount || amount < 5) return alert('Importo minimo €5.00');
        if (!iban) return alert('Inserisci il tuo IBAN');
        if (!name) return alert('Inserisci il nome intestatario');

        const res = await api.request('/withdrawal/request', {
            method: 'POST',
            body: JSON.stringify({ amount, iban, name })
        });

        if (res && res.new_balance !== undefined) {
            state.balance = res.new_balance;
            const navEl = document.getElementById('user-balance-nav');
            if (navEl) navEl.innerText = `Saldo: €${res.new_balance.toFixed(2)}`;
            if (amountEl) amountEl.value = '';
            if (ibanEl) ibanEl.value = '';
            if (nameEl) nameEl.value = '';
            this.closeWithdrawal();
            const profileBal = document.getElementById('profile-balance');
            if (profileBal) profileBal.innerText = `€${res.new_balance.toFixed(2)}`;
            alert('✅ Richiesta inviata. Il saldo è già stato aggiornato.');
        }
    }
};


window.matchDetail = {
    _activeTab: 'principali',

    _labels: {
        'h2h': 'Esito Finale 1X2',
        'totals': 'Under/Over (Totali)',
        'btts': 'Goal / No Goal',
        'double_chance': 'Doppia Chance',
        'draw_no_bet': 'Draw No Bet',
        'correct_score': 'Risultato Esatto',
        'h2h_1st_half': 'Risultato 1° Tempo',
        'h2h_2nd_half': 'Risultato 2° Tempo',
        'totals_1st_half': 'Under/Over 1° Tempo',
        'totals_2nd_half': 'Under/Over 2° Tempo',
        'alternate_totals': 'Over/Under (Linee Aggiuntive)',
        'alternate_spreads': 'Handicap (Linee Aggiuntive)',
        'spreads': 'Handicap / Spread',
        'draw_no_bet': 'Draw No Bet',
        'combo_1x2_btts':    'Combo 1X2 + GG/NG',
        'combo_1x2_ou':      'Combo 1X2 + Over/Under',
        'combo_dc_btts':     'Doppia Chance + GG/NG',
        'combo_dc_ou':       'Doppia Chance + Over/Under',
        'combo_dnb_btts':    'Draw No Bet + GG/NG',
        'combo_dnb_ou':      'Draw No Bet + Over/Under',
        'combo_1x2_btts_ou': 'Tripla Combo 1X2 + GG/NG + Over/Under',
        'combo_ht_btts':     '1° Tempo + GG/NG',
        'combo_ht_ou':       '1° Tempo + Over/Under',
        'odd_even':             'Pari / Dispari Gol',
        'multigol':             'Multigol Totale',
        'multigol_home':        'Multigol Casa',
        'multigol_away':        'Multigol Ospite',
        'combo_1x2_multigol':   '1X2 + Multigol',
        'combo_dc_multigol':    'Doppia Chance + Multigol',
        'combo_ou_btts':        'Over/Under + GG/NG',
        'combo_multigol_btts':  'Multigol + GG/NG',
        'total_goals_exact':    'Gol Esatti Totali',
        'combo_1x2_total_goals':'1X2 + Gol Esatti',
        // Tennis
        'set_spreads': 'Handicap Set (±1.5)',
        'set_totals':  'Totale Set',
        'game_spreads':'Handicap Game',
        'game_totals': 'Over/Under Game',
    },

    _tabs: {
        // Tab calcio
        'principali': ['h2h', 'totals', 'btts', 'double_chance', 'draw_no_bet', 'correct_score', 'odd_even'],
        'tempi':      ['h2h_1st_half', 'combo_ht_btts', 'combo_ht_ou'],
        'handicap':   ['draw_no_bet', 'combo_dnb_btts', 'combo_dnb_ou'],
        'combo':      ['combo_1x2_btts','combo_1x2_ou','combo_dc_btts','combo_dc_ou','combo_dnb_btts','combo_dnb_ou','combo_1x2_btts_ou','combo_ht_btts','combo_ht_ou','combo_ou_btts'],
        'multigol':   ['multigol','multigol_home','multigol_away','total_goals_exact','combo_1x2_multigol','combo_dc_multigol','combo_multigol_btts','combo_1x2_total_goals'],
        'tutto':      null,
        // Tab tennis
        'tennis_principali': ['h2h', 'set_spreads', 'set_totals', 'h2h_1st_half'],
        'tennis_tutto':       null,
    },

    open(event) {
        // _activeTab viene impostato sotto dopo il rilevamento tennis
        const section = document.getElementById('section-match-detail');
        const oddsSection = document.getElementById('section-odds');
        if (!section || !oddsSection) return;

        // Titolo e orario
        const eventDate = new Date(event.commence_time);
        const dateStr = eventDate.toLocaleDateString('it-IT', {weekday:'long', day:'2-digit', month:'long'});
        const timeStr = eventDate.toLocaleTimeString('it-IT', {hour:'2-digit', minute:'2-digit'});

        document.getElementById('md-league').innerText = event.sport_title || '';
        document.getElementById('md-home').innerText = event.home_team;
        document.getElementById('md-away').innerText = event.away_team;
        document.getElementById('md-date').innerText = `${dateStr} — ${timeStr}`;

        // Reset stato dropdown per la nuova partita
        this._dropdownState = {};

        // Rileva se è tennis
        const isTennis = ['tennis','atp','wta','itf','challenger']
            .some(kw => (event.sport_title || '').toLowerCase().includes(kw));
        this._activeTab = isTennis ? 'tennis_principali' : 'principali';

        // Ricostruisci tab bar via JS (garantisce layout cross-browser)
        const tabBar = document.getElementById('md-tab-bar');
        if (tabBar) {
            const tabs = isTennis ? [
                {key:'tennis_principali', label:'Principali'},
                {key:'tennis_tutto',      label:'Tutto'},
            ] : [
                {key:'principali', label:'Principali'},
                {key:'tempi',      label:'Tempi'},
                {key:'handicap',   label:'Handicap'},
                {key:'combo',      label:'Combo'},
                {key:'multigol',   label:'Multigol'},
                {key:'tutto',      label:'Tutto'},
            ];
            tabBar.innerHTML = tabs.map(t => `
                <button class="md-tab-btn" data-tab="${t.key}" onclick="matchDetail.switchTab('${t.key}')"
                    style="width:auto!important;display:inline-block!important;white-space:nowrap!important;padding:8px 18px;border-radius:20px;border:none;cursor:pointer;font-size:0.82rem;font-weight:${t.key==='principali'?'700':'500'};background:${t.key==='principali'?'var(--accent)':'rgba(255,255,255,0.08)'};color:${t.key==='principali'?'#0a0a1a':'var(--text-secondary)'};flex:0 0 auto;min-width:max-content;transition:all 0.2s;text-transform:none;letter-spacing:normal;box-shadow:none;background-image:none;">${t.label}</button>
            `).join('');
        }

        // Mostra schermata
        oddsSection.classList.add('hidden');
        section.classList.remove('hidden');

        this.renderTab(event);
    },

    close() {
        const section = document.getElementById('section-match-detail');
        const oddsSection = document.getElementById('section-odds');
        if (section) section.classList.add('hidden');
        if (oddsSection) oddsSection.classList.remove('hidden');
        state._currentMatchEvent = null;
    },

    switchTab(tab) {
        this._activeTab = tab;
        const event = state._currentMatchEvent;
        if (!event) return;

        // Aggiorna stile bottoni tab
        document.querySelectorAll('.md-tab-btn').forEach(btn => {
            const isActive = btn.dataset.tab === tab;
            btn.style.background = isActive ? 'var(--accent)' : 'rgba(255,255,255,0.08)';
            btn.style.color = isActive ? '#0a0a1a' : 'var(--text-secondary)';
            btn.style.fontWeight = isActive ? '700' : '500';
        });

        this.renderTab(event);
    },

    // Mercati che usano il dropdown selector stile Sisal
    _DROPDOWN_MARKETS: new Set(['multigol','multigol_home','multigol_away','combo_1x2_multigol','combo_dc_multigol','combo_multigol_btts','combo_1x2_total_goals']),
    _dropdownState: {}, // market_key → selected_prefix

    renderTab(event) {
        const container = document.getElementById('md-markets-container');
        if (!container) return;

        const bookmaker = event.bookmakers?.[0];
        if (!bookmaker) {
            container.innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">Mercati non disponibili.</p>';
            return;
        }

        const tabKeys = this._tabs[this._activeTab];
        let markets;
        if (tabKeys === null) {
            markets = bookmaker.markets.filter(m => m.key !== 'h2h_lay');
        } else {
            markets = tabKeys.map(key => bookmaker.markets.find(m => m.key === key)).filter(Boolean);
            if (markets.length === 0) markets = bookmaker.markets.filter(m => m.key !== 'h2h_lay');
        }

        if (markets.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">Nessun mercato disponibile per questa sezione.</p>';
            return;
        }

        container.innerHTML = markets.map(m => {
            const label = this._labels[m.key] || m.key.replace(/_/g,' ').toUpperCase();

            // ── Mercati con DROPDOWN (stile Sisal) ──────────────────────────
            if (this._DROPDOWN_MARKETS.has(m.key)) {
                return this._renderDropdownMarket(event, m, label);
            }

            // ── Mercati normali (lista verticale) ───────────────────────────
            const outcomesHtml = m.outcomes.map(o => {
                let name = o.name;
                if (m.key === 'btts') {
                    name = ['Yes','yes','Goal','GG','1'].includes(name) ? 'Goal' : 'No Goal';
                } else if (m.key.includes('totals') && o.point !== undefined) {
                    if (!name.includes(o.point.toString())) name = `${o.name} ${o.point}`;
                } else if (o.point !== undefined && !m.key.includes('combo')) {
                    if (!name.includes(String(o.point))) name = `${o.name} (${o.point > 0 ? '+' : ''}${o.point})`;
                }
                const isSel = state.slip.some(s => s.eventId === event.id && s.market === m.key && s.selection === name);
                const safeEvent = (event.home_team + ' vs ' + event.away_team).replace(/'/g, "\'");
                const safeName = name.replace(/'/g, "\'");
                return `<div class="price-row ${isSel ? 'selected' : ''}" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,${isSel?'0.2':'0.07'});margin-bottom:6px;transition:all 0.15s;"
                    onclick="bets.addToSlip('${event.id}','${safeEvent}','${m.key}','${safeName}',${o.price}); matchDetail.refreshSelections();">
                    <span style="color:var(--text-primary);font-size:0.88rem;">${name}</span>
                    <span style="color:var(--accent);font-weight:700;font-size:0.95rem;">${o.price.toFixed(2)}</span>
                </div>`;
            }).join('');

            return `<div style="margin-bottom:1.5rem;">
                <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.08em;color:var(--accent);text-transform:uppercase;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid rgba(99,179,237,0.2);">${label}</div>
                <div>${outcomesHtml}</div>
            </div>`;
        }).join('');
    },

    _renderDropdownMarket(event, m, label) {
        // Estrai prefissi unici per il dropdown (es. "1+", "X+", "2+", oppure "Casa:", "Ospite:")
        // Per multigol semplice: non serve dropdown — mostra griglia diretta
        if (m.key === 'multigol' || m.key === 'total_goals_exact') {
            return this._renderMultigolGrid(event, m, label);
        }

        // Per combo: raggruppa per prefisso (parte prima del "+")
        const groups = {};
        const groupOrder = [];
        m.outcomes.forEach(o => {
            const plusIdx = o.name.indexOf('+');
            const prefix = plusIdx > -1 ? o.name.substring(0, plusIdx) : o.name;
            if (!groups[prefix]) { groups[prefix] = []; groupOrder.push(prefix); }
            groups[prefix].push(o);
        });

        if (groupOrder.length <= 1) {
            return this._renderMultigolGrid(event, m, label);
        }

        const mkId = m.key.replace(/_/g, '-');
        const selectedPrefix = this._dropdownState[m.key] || groupOrder[0];
        const safeEvent = (event.home_team + ' vs ' + event.away_team).replace(/'/g, "\'");

        const selectedOutcomes = groups[selectedPrefix] || [];
        const outcomesHtml = selectedOutcomes.map(o => {
            const name = o.name;
            const isSel = state.slip.some(s => s.eventId === event.id && s.market === m.key && s.selection === name);
            const safeName = name.replace(/'/g, "\'");
            return `<div style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:8px;background:${isSel?'rgba(99,179,237,0.15)':'rgba(255,255,255,0.04)'};border:1px solid rgba(255,255,255,${isSel?'0.2':'0.07'});margin-bottom:6px;transition:all 0.15s;"
                onclick="bets.addToSlip('${event.id}','${safeEvent}','${m.key}','${safeName}',${o.price}); matchDetail.refreshSelections();">
                <span style="color:var(--text-primary);font-size:0.88rem;">${name}</span>
                <span style="color:var(--accent);font-weight:700;font-size:0.95rem;">${o.price.toFixed(2)}</span>
            </div>`;
        }).join('');

        const options = groupOrder.map(p =>
            `<option value="${p}" ${p === selectedPrefix ? 'selected' : ''}>${p}</option>`
        ).join('');

        return `<div style="margin-bottom:1.5rem;">
            <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.08em;color:var(--accent);text-transform:uppercase;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid rgba(99,179,237,0.2);">${label}</div>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
                <select id="dd-${mkId}" onchange="matchDetail._onDropdownChange('${m.key}','${event.id}')"
                    style="width:auto!important;background:var(--card-bg);color:var(--text-primary);border:1px solid var(--border-color);border-radius:8px;padding:7px 12px;font-size:0.85rem;cursor:pointer;outline:none;min-width:120px;">
                    ${options}
                </select>
                <span style="color:var(--text-secondary);font-size:0.78rem;">seleziona per filtrare</span>
            </div>
            <div id="dd-content-${mkId}">${outcomesHtml}</div>
        </div>`;
    },

    _renderMultigolGrid(event, m, label) {
        // Griglia compatta stile Sisal per multigol puro e gol esatti
        const safeEvent = (event.home_team + ' vs ' + event.away_team).replace(/'/g, "\'");
        const outcomesHtml = m.outcomes.map(o => {
            const name = o.name;
            const isSel = state.slip.some(s => s.eventId === event.id && s.market === m.key && s.selection === name);
            const safeName = name.replace(/'/g, "\'");
            // Label breve: rimuovi "Multigol " e "Gol" ecc.
            const shortLabel = name.replace('Multigol ', '').replace(' Gol', 'G').replace('Casa: ','C:').replace('Ospite: ','O:');
            return `<div style="cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 8px;border-radius:8px;background:${isSel?'rgba(99,179,237,0.18)':'rgba(255,255,255,0.05)'};border:1px solid rgba(255,255,255,${isSel?'0.25':'0.08'});transition:all 0.15s;text-align:center;"
                onclick="bets.addToSlip('${event.id}','${safeEvent}','${m.key}','${safeName}',${o.price}); matchDetail.refreshSelections();">
                <span style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:4px;font-weight:600;">${shortLabel}</span>
                <span style="color:var(--accent);font-weight:700;font-size:0.95rem;">${o.price.toFixed(2)}</span>
            </div>`;
        }).join('');
        return `<div style="margin-bottom:1.5rem;">
            <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.08em;color:var(--accent);text-transform:uppercase;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid rgba(99,179,237,0.2);">${label}</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;">${outcomesHtml}</div>
        </div>`;
    },

    _onDropdownChange(marketKey, eventId) {
        const event = state._currentMatchEvent;
        if (!event) return;
        const mkId = marketKey.replace(/_/g, '-');
        const sel = document.getElementById('dd-' + mkId);
        if (!sel) return;
        this._dropdownState[marketKey] = sel.value;

        const bookmaker = event.bookmakers?.[0];
        const m = bookmaker?.markets.find(x => x.key === marketKey);
        if (!m) return;

        const groups = {};
        m.outcomes.forEach(o => {
            const plusIdx = o.name.indexOf('+');
            const prefix = plusIdx > -1 ? o.name.substring(0, plusIdx) : o.name;
            if (!groups[prefix]) groups[prefix] = [];
            groups[prefix].push(o);
        });

        const safeEvent = (event.home_team + ' vs ' + event.away_team).replace(/'/g, "\'");
        const selectedOutcomes = groups[sel.value] || [];
        const contentEl = document.getElementById('dd-content-' + mkId);
        if (!contentEl) return;
        contentEl.innerHTML = selectedOutcomes.map(o => {
            const name = o.name;
            const isSel = state.slip.some(s => s.eventId === event.id && s.market === marketKey && s.selection === name);
            const safeName = name.replace(/'/g, "\'");
            return `<div style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:8px;background:${isSel?'rgba(99,179,237,0.15)':'rgba(255,255,255,0.04)'};border:1px solid rgba(255,255,255,${isSel?'0.2':'0.07'});margin-bottom:6px;transition:all 0.15s;"
                onclick="bets.addToSlip('${event.id}','${safeEvent}','${marketKey}','${safeName}',${o.price}); matchDetail.refreshSelections();">
                <span style="color:var(--text-primary);font-size:0.88rem;">${name}</span>
                <span style="color:var(--accent);font-weight:700;font-size:0.95rem;">${o.price.toFixed(2)}</span>
            </div>`;
        }).join('');
    },

    refreshSelections() {
        const event = state._currentMatchEvent;
        if (event) {
            this.renderTab(event);
            // Aggiorna anche le card nella lista (stato selezione nei bottoni)
            if (typeof dashboard !== 'undefined' && dashboard.renderOdds) {
                dashboard.renderOdds();
            }
        }
    }
};

window.onload = () => {
    if (state.token) {
        // Small delay to ensure DOM is fully parsed
        setTimeout(() => {
            ui.showDashboard();
            dashboard.init();
            router.navigate('odds');
        }, 50);
    }
};
