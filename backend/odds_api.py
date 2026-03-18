import requests
import math
from typing import Dict, List, Any
from diskcache import Cache
import os
import time
from datetime import datetime, timedelta, timezone

cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
cache = Cache(cache_dir)

FOOTBALL_API_BASE_URL = "https://v3.football.api-sports.io"
HOUSE_EDGE = 1.02  # 2% vantaggio del banco — applicato a tutti i mercati

# ─── UTILITY ────────────────────────────────────────────────────────────────

def _normalize_with_margin(prices: List[float], margin: float = HOUSE_EDGE) -> List[float]:
    """
    Formula corretta per applicare il margine:
    1. Rimuove il margine già incluso dal bookmaker originale
    2. Applica il nostro margine (2%)
    Così le quote rimangono in linea col mercato.
    """
    if len(prices) < 2:
        return prices
    raw_probs = [1.0 / p for p in prices]
    total = sum(raw_probs)
    if total <= 0:
        return prices
    fair_probs = [p / total for p in raw_probs]
    return [max(1.05, round(1.0 / (fp * margin), 2)) for fp in fair_probs]

def _apply_margin_to_event(event: Dict[str, Any]):
    """Applica il margine del banco a tutti i mercati NON simulati di un evento."""
    for bookmaker in event.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            if market.get('_simulated'):
                continue  # mercati simulati già hanno il margine
            outcomes = [o for o in market.get('outcomes', []) if isinstance(o.get('price'), (int, float))]
            if len(outcomes) < 2:
                continue
            prices = [o['price'] for o in outcomes]
            new_prices = _normalize_with_margin(prices)
            for o, np_ in zip(outcomes, new_prices):
                o['price'] = np_

# ─── POISSON ────────────────────────────────────────────────────────────────

def _poisson(lam: float, k: int) -> float:
    return (lam ** k * math.exp(-lam)) / math.factorial(min(k, 12))

def _lambda_from_over25(prob_over25: float) -> float:
    """Trova lambda Poisson tale che P(gol > 2.5) = prob_over25."""
    def p_over(lam):
        return 1 - math.exp(-lam) * (1 + lam + lam**2/2)
    lo, hi = 0.3, 9.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if p_over(mid) < prob_over25:
            lo = mid
        else:
            hi = mid
    return mid

def _prob_over_line(lam: float, line: float) -> float:
    k_max = int(line)
    p_under = sum(_poisson(lam, k) for k in range(k_max + 1))
    return max(0.02, min(0.98, 1.0 - p_under))

# ─── SIMULAZIONE MERCATI MANCANTI ───────────────────────────────────────────

def _simulate_markets(event: Dict[str, Any]):
    """
    Genera mercati calcistici mancanti (BTTS, O/U aggiuntivi, esatto, combo)
    partendo dai mercati base (h2h, totals).
    Tutti i mercati generati hanno _simulated=True e includono già il 2% di margine.
    """
    if not event.get('bookmakers'):
        return
    m_list = event['bookmakers'][0].get('markets', [])
    m_keys = {m['key'] for m in m_list}

    def add(key, outcomes):
        m_list.append({"key": key, "outcomes": outcomes, "_simulated": True})

    h2h    = next((m for m in m_list if m['key'] == 'h2h'),    None)
    totals = next((m for m in m_list if m['key'] == 'totals'), None)

    # Quote 1X2 fair (senza margine bookmaker originale)
    h_q = x_q = a_q = None
    ph = px = pa = None
    if h2h:
        h_q = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
        a_q = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
        x_q = next((o['price'] for o in h2h['outcomes'] if o['name'] in ['Pareggio', 'Draw', 'X']), None)
        if h_q and a_q and x_q:
            raw = [1/h_q, 1/x_q, 1/a_q]
            tot = sum(raw)
            ph, px, pa = raw[0]/tot, raw[1]/tot, raw[2]/tot

    # Over 2.5 originale
    o25_q = None
    lam = None
    if totals:
        o25_q = next((o['price'] for o in totals['outcomes']
                      if o.get('point') == 2.5 and 'Over' in str(o.get('name', ''))), None)
        if o25_q:
            prob_o25 = 1.0 / float(o25_q)
            lam = _lambda_from_over25(prob_o25)

    M = HOUSE_EDGE  # 2%

    # 1. DOUBLE CHANCE
    if 'double_chance' not in m_keys and ph is not None:
        add("double_chance", [
            {"name": "1X", "price": max(1.05, round(1.0 / ((ph + px) * M), 2))},
            {"name": "X2", "price": max(1.05, round(1.0 / ((pa + px) * M), 2))},
            {"name": "12", "price": max(1.05, round(1.0 / ((ph + pa) * M), 2))},
        ])

    # 2. DRAW NO BET
    if 'draw_no_bet' not in m_keys and ph is not None:
        sum_hnx = ph + pa
        add("draw_no_bet", [
            {"name": event['home_team'], "price": max(1.05, round(1.0 / (ph / sum_hnx * M), 2))},
            {"name": event['away_team'], "price": max(1.05, round(1.0 / (pa / sum_hnx * M), 2))},
        ])

    # 3. RISULTATO 1° TEMPO (il pareggio è più probabile nel primo tempo)
    if 'h2h_1st_half' not in m_keys and ph is not None:
        # Aggiusta le probabilità: meno estreme nel 1° tempo
        ph1 = ph * 0.80 + 0.07
        pa1 = pa * 0.80 + 0.07
        px1 = max(0.05, 1.0 - ph1 - pa1)
        tot1 = ph1 + px1 + pa1
        add("h2h_1st_half", [
            {"name": event['home_team'], "price": max(1.10, round(1.0 / (ph1/tot1 * M), 2))},
            {"name": "Pareggio",          "price": max(1.40, round(1.0 / (px1/tot1 * M), 2))},
            {"name": event['away_team'], "price": max(1.10, round(1.0 / (pa1/tot1 * M), 2))},
        ])

    # 4. BTTS — correlato con Over 2.5 tramite formula calibrata
    if 'btts' not in m_keys:
        o25_ref = float(o25_q) if o25_q else 1.90
        prob_over = 1.0 / max(1.01, o25_ref)
        prob_gg = min(0.72, max(0.32, prob_over * 0.72 + 0.13))
        prob_ng = 1.0 - prob_gg
        add("btts", [
            {"name": "Goal",    "price": max(1.30, round(1.0 / (prob_gg * M), 2))},
            {"name": "No Goal", "price": max(1.30, round(1.0 / (prob_ng * M), 2))},
        ])

    # 5. OVER/UNDER LINEE AGGIUNTIVE (1.5, 3.5, 4.5) — Poisson
    if totals and lam is not None:
        existing = {o.get('point') for o in totals['outcomes']}
        for line in [1.5, 3.5, 4.5]:
            if line not in existing:
                p_ov = _prob_over_line(lam, line)
                p_un = 1.0 - p_ov
                totals['outcomes'].append({
                    "name": f"Over {line}",  "price": max(1.05, round(1.0/(p_ov*M), 2)), "point": line, "_simulated": True
                })
                totals['outcomes'].append({
                    "name": f"Under {line}", "price": max(1.05, round(1.0/(p_un*M), 2)), "point": line, "_simulated": True
                })

    # 6. RISULTATO ESATTO — Poisson da 1X2
    if 'correct_score' not in m_keys and ph is not None:
        # Stima lambda home/away da prob 1X2
        lh = max(0.4, min(3.5, -math.log(max(0.01, px + pa)) * 1.05 + 0.25))
        la = max(0.2, min(2.5, -math.log(max(0.01, px + ph)) * 0.85 + 0.05))
        scores = ["1-0","2-0","2-1","3-0","3-1","3-2","0-0","1-1","2-2","0-1","0-2","1-2","0-3","1-3","2-3"]
        ep = {}
        total_named = 0
        for s in scores:
            hg, ag = int(s[0]), int(s[2])
            p = _poisson(lh, hg) * _poisson(la, ag)
            ep[s] = p
            total_named += p
        ep["Altro"] = max(0.02, 1.0 - total_named)
        cs_outcomes = []
        for s in scores + ["Altro"]:
            p = ep.get(s, 0.02)
            cs_outcomes.append({"name": s, "price": min(99.0, max(1.05, round(1.0 / (p * M), 2)))})
        add("correct_score", cs_outcomes)

    # 7. COMBO 1X2 + GG/NG
    if 'combo_1x2_btts' not in m_keys and ph is not None:
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        gg_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'),    None) if btts_m else None
        ng_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None) if btts_m else None
        if gg_q and ng_q:
            combos = []
            for rn, rq in [("1", h_q), ("X", x_q), ("2", a_q)]:
                for bn, bq in [("GG", gg_q), ("NG", ng_q)]:
                    combos.append({"name": f"{rn}+{bn}", "price": max(1.05, round(rq * bq / M, 2))})
            add("combo_1x2_btts", combos)

    # 8. COMBO 1X2 + OVER/UNDER
    if 'combo_1x2_ou' not in m_keys and ph is not None and totals:
        lines_dict: Dict[float, Dict] = {}
        for o in totals['outcomes']:
            pt = o.get('point')
            if pt is None: continue
            pt = float(pt)
            lines_dict.setdefault(pt, {})
            if 'Over'  in str(o['name']): lines_dict[pt]['over']  = o['price']
            if 'Under' in str(o['name']): lines_dict[pt]['under'] = o['price']
        combos_ou = []
        for pt in sorted(lines_dict.keys()):
            ov_q  = lines_dict[pt].get('over')
            un_q  = lines_dict[pt].get('under')
            for rn, rq in [("1", h_q), ("X", x_q), ("2", a_q)]:
                if ov_q: combos_ou.append({"name": f"{rn}+Over {pt}",  "price": max(1.05, round(rq * ov_q / M, 2)), "point": pt})
                if un_q: combos_ou.append({"name": f"{rn}+Under {pt}", "price": max(1.05, round(rq * un_q / M, 2)), "point": pt})
        if combos_ou:
            add("combo_1x2_ou", combos_ou)


# ─── THE ODDS API ────────────────────────────────────────────────────────────

def get_odds_the_odds_api(api_key: str, sport: str, regions: str = "eu") -> List[Dict[str, Any]]:
    if not sport: sport = 'soccer'

    # Solo calcio — mercati principali
    markets = "h2h,totals,btts,double_chance,draw_no_bet,h2h_1st_half,correct_score"

    cache_key = f"odds_toa_v12_{sport}_{regions}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "bookmakers": "bet365,williamhill,unibet,bwin,marathonbet,paddypower"
    }

    try:
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 422:
            params["markets"] = "h2h,totals,btts"
            r = requests.get(url, params=params, timeout=12)
        if r.status_code == 422:
            params["markets"] = "h2h,totals"
            r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()

        for event in data:
            # Merge bookmaker → un unico "best odds" con precedenza Bet365
            virtual_markets: Dict[str, Any] = {}
            sorted_bookies = sorted(event.get('bookmakers', []),
                                    key=lambda x: 0 if x['key'] == 'bet365' else 1)
            for bookie in sorted_bookies:
                for market in bookie.get('markets', []):
                    mk = market['key']
                    if mk not in virtual_markets:
                        virtual_markets[mk] = market
                    else:
                        existing = {o['name'] for o in virtual_markets[mk]['outcomes']}
                        for o in market.get('outcomes', []):
                            if o['name'] not in existing:
                                virtual_markets[mk]['outcomes'].append(o)

            event['bookmakers'] = [{
                "key": "simus_bet",
                "title": "Simus Bet",
                "markets": list(virtual_markets.values())
            }]

            # Normalizzazione nomi
            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    mk = market['key']
                    for o in market.get('outcomes', []):
                        name = str(o.get('name', ''))
                        if name == 'Draw': o['name'] = 'Pareggio'
                        if mk == 'btts':
                            if name in ['Yes', 'yes']: o['name'] = 'Goal'
                            if name in ['No', 'no']:   o['name'] = 'No Goal'
                        if mk == 'totals' and 'point' in o:
                            try: o['point'] = float(o['point'])
                            except: pass
                            if 'Over'  in name: o['name'] = f"Over {o['point']}"
                            if 'Under' in name: o['name'] = f"Under {o['point']}"
                        if mk == 'double_chance':
                            if name in ['Home/Draw','Draw/Home']: o['name'] = '1X'
                            elif name in ['Away/Draw','Draw/Away']: o['name'] = 'X2'
                            elif name in ['Home/Away','Away/Home']: o['name'] = '12'

            # Pulizia totals: tieni solo linee con Over E Under
            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    if market['key'] != 'totals': continue
                    by_pt: Dict[float, List] = {}
                    for o in market['outcomes']:
                        pt = o.get('point')
                        if pt is None:
                            try: pt = float(str(o['name']).split()[-1]); o['point'] = pt
                            except: continue
                        by_pt.setdefault(float(pt), []).append(o)
                    clean = []
                    for pt, outs in by_pt.items():
                        if any('Over' in str(o['name']) for o in outs) and any('Under' in str(o['name']) for o in outs):
                            clean.extend(outs)
                    market['outcomes'] = clean

            # Applica margine 2% ai mercati API originali
            _apply_margin_to_event(event)

            # Simula mercati mancanti (già con 2% incluso)
            try:
                _simulate_markets(event)
            except Exception as e:
                print(f"[simulate_markets] {e}")

        cache.set(cache_key, data, expire=1800)
        return data

    except Exception as e:
        print(f"Errore The Odds API ({sport}): {e}")
        return []


# ─── API-FOOTBALL ────────────────────────────────────────────────────────────

def get_odds_api_football(api_key: str, league_id_str: str, season: str = "2025") -> List[Dict[str, Any]]:
    headers = {'x-apisports-key': api_key}
    today_now = datetime.now(timezone.utc)
    dates = [today_now.strftime("%Y-%m-%d"), (today_now + timedelta(days=1)).strftime("%Y-%m-%d")]
    all_normalized = []

    for date_str in dates:
        cache_key_date = f"af_global_odds_v8_{date_str}"
        day_odds = cache.get(cache_key_date)

        if day_odds is None:
            print(f"AF: Caricamento per {date_str}...")
            f_map = {}
            try:
                f_r = requests.get(f"{FOOTBALL_API_BASE_URL}/fixtures", headers=headers, params={'date': date_str}, timeout=15)
                if f_r.status_code == 200:
                    for f in f_r.json().get('response', []):
                        f_map[f['fixture']['id']] = {
                            'home': f['teams']['home']['name'],
                            'away': f['teams']['away']['name'],
                            'time': f['fixture']['date'],
                            'league_id': f['league']['id'],
                            'league_name': f['league']['name']
                        }
            except Exception as e:
                print(f"Errore fixtures AF: {e}")

            day_odds_dict = {}
            try:
                r_odds = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers, params={'date': date_str}, timeout=15)
                if r_odds.status_code == 200:
                    data = r_odds.json()
                    if not data.get('response') and data.get('errors'):
                        print(f"Errore AF: {data['errors']}")
                        day_odds = []; cache.set(cache_key_date, day_odds, expire=60); continue
                    total_pages = data.get('paging', {}).get('total', 1)
                    for page in range(1, total_pages + 1):
                        if page > 1:
                            time.sleep(0.3)
                            resp = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers,
                                                params={'date': date_str, 'page': page}, timeout=15)
                            if resp.status_code == 200: data = resp.json()
                            else: break
                        for item in data.get('response', []):
                            fid = item['fixture']['id']
                            if fid in f_map:
                                norm = _fast_normalize_af(item, f_map[fid])
                                if norm: day_odds_dict[fid] = norm
            except Exception as e:
                print(f"Errore odds AF: {e}")

            day_odds = list(day_odds_dict.values())
            cache.set(cache_key_date, day_odds, expire=600 if day_odds else 60)

        try:
            target_id = int(league_id_str.strip())
            all_normalized.extend(m for m in day_odds if m['league_id'] == target_id)
        except: pass

    return all_normalized


def _fast_normalize_af(item: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    if not item.get('bookmakers'): return None
    bookie = next((b for b in item['bookmakers'] if b['id'] == 8), None)
    if not bookie: bookie = next((b for b in item['bookmakers'] if b['id'] in [1, 2, 3]), item['bookmakers'][0])
    bets = bookie.get('bets') or bookie.get('markets')
    if not bets: return None

    NAME_MAP = {
        "Match Winner": 'h2h', "Goals Over/Under": 'totals',
        "Both Teams Score": 'btts', "Double Chance": 'double_chance',
        "Draw No Bet": 'draw_no_bet', "Exact Score": 'correct_score',
        "First Half Winner": 'h2h_1st_half',
    }
    markets_dict = {}
    for m in bets:
        mk = NAME_MAP.get(m['name'])
        if not mk or mk in markets_dict: continue
        outcomes = []
        for val in m['values']:
            ov = str(val['value'])
            on = ov.replace('Home', meta['home']).replace('Away', meta['away']).replace('Draw', 'Pareggio')
            if on == 'X': on = 'Pareggio'
            point = None
            if mk == 'totals':
                if "2.5" not in ov: continue
                point = 2.5
                on = "Over 2.5" if "Over" in ov else "Under 2.5"
            if mk == 'btts':
                on = "Goal" if ov == "Yes" else "No Goal"
            outcomes.append({"name": on, "price": float(val['odd']), "point": point})
        if outcomes:
            markets_dict[mk] = {"key": mk, "outcomes": outcomes}

    if not markets_dict: return None
    event = {
        "id": f"af-{item['fixture']['id']}",
        "league_id": meta['league_id'],
        "sport_title": meta['league_name'],
        "commence_time": meta['time'],
        "home_team": meta['home'],
        "away_team": meta['away'],
        "bookmakers": [{"key": "af", "title": "AF", "markets": list(markets_dict.values())}]
    }
    _apply_margin_to_event(event)
    _simulate_markets(event)
    return event


# ─── BETSAPI2 ────────────────────────────────────────────────────────────────

def get_odds_betsapi2_rapidapi(api_key: str, sport_id: str = "1") -> List[Dict[str, Any]]:
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": "betsapi2.p.rapidapi.com"}
    cache_key = f"rapidapi_betsapi2_v9_{sport_id}"
    cached = cache.get(cache_key)
    if cached is not None: return cached

    all_normalized = []
    try:
        r_up = requests.get("https://betsapi2.p.rapidapi.com/v1/bet365/upcoming",
                            headers=headers, params={"sport_id": sport_id, "day": "today"}, timeout=15)
        if r_up.status_code == 200:
            matches = r_up.json().get('results', [])[:25]
            for match in matches:
                fid = match.get('id')
                if not fid: continue
                r_odds = requests.get("https://betsapi2.p.rapidapi.com/v3/bet365/prematch",
                                      headers=headers, params={"FI": str(fid)}, timeout=15)
                if r_odds.status_code == 200:
                    res = r_odds.json().get('results', [])
                    if res:
                        norm = _normalize_betsapi2(res[0], match)
                        if norm: all_normalized.append(norm)
                time.sleep(0.5)
    except Exception as e:
        print(f"Errore BetsAPI2: {e}")

    cache.set(cache_key, all_normalized, expire=1800)
    return all_normalized


def _normalize_betsapi2(raw: Dict[str, Any], meta: dict) -> Dict[str, Any]:
    home = meta.get('home', {}).get('name', 'Home')
    away = meta.get('away', {}).get('name', 'Away')
    ct = str(meta.get('time', ''))
    try:
        if ct.isdigit():
            ct = datetime.fromtimestamp(int(ct), tz=timezone.utc).isoformat()
    except: pass

    def sp(cat): return raw.get(cat, {}).get('sp', {})
    main_sp  = sp('main')
    goals_sp = sp('goals')
    halves_sp = sp('halves')

    markets_dict = {}

    # H2H
    ftr = main_sp.get('full_time_result', {})
    if ftr and ftr.get('odds'):
        outcomes = []
        for o in ftr['odds']:
            n = home if o['name']=='1' else (away if o['name']=='2' else 'Pareggio')
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['h2h'] = {"key": "h2h", "outcomes": outcomes}

    # BTTS
    btts = main_sp.get('both_teams_to_score', {})
    if btts and btts.get('odds'):
        outcomes = [{"name": "Goal" if o['name']=='Yes' else "No Goal",
                     "price": float(o.get('odds', 0))} for o in btts['odds']]
        if outcomes: markets_dict['btts'] = {"key": "btts", "outcomes": outcomes}

    # TOTALS Over/Under 2.5
    ou = goals_sp.get('goals_over_under', {}) or main_sp.get('goals_over_under', {})
    if ou and ou.get('odds'):
        outcomes = []
        for o in ou['odds']:
            pt = o.get('name')
            if pt != '2.5': continue
            hdr = o.get('header', '')
            outcomes.append({"name": f"{'Over' if 'Over' in hdr else 'Under'} 2.5",
                             "price": float(o.get('odds', 0)), "point": 2.5})
        if outcomes: markets_dict['totals'] = {"key": "totals", "outcomes": outcomes}

    # CORRECT SCORE
    cs = main_sp.get('correct_score', {})
    if cs and cs.get('odds'):
        outcomes = [{"name": o.get('name'), "price": float(o.get('odds', 0))} for o in cs['odds'][:16]]
        if outcomes: markets_dict['correct_score'] = {"key": "correct_score", "outcomes": outcomes}

    # 1° TEMPO
    h1r = halves_sp.get('half_time_result', {})
    if h1r and h1r.get('odds'):
        outcomes = []
        for o in h1r['odds']:
            n = home if o['name']=='1' else (away if o['name']=='2' else 'Pareggio')
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['h2h_1st_half'] = {"key": "h2h_1st_half", "outcomes": outcomes}

    if not markets_dict: return None
    event = {
        "id": f"b365-{meta.get('id')}",
        "sport_title": meta.get('league', {}).get('name', 'Soccer'),
        "commence_time": ct,
        "home_team": home,
        "away_team": away,
        "bookmakers": [{"key": "bet365", "title": "Bet365", "markets": list(markets_dict.values())}]
    }
    _apply_margin_to_event(event)
    _simulate_markets(event)
    return event


# ─── APPLY OVERROUND (chiamata da main.py — ora è un no-op perché il margine
#     è già applicato dentro odds_api.py) ─────────────────────────────────────

def apply_overround(odds_data: List[Dict[str, Any]], overround_percent: float) -> List[Dict[str, Any]]:
    """
    Mantenuto per compatibilità con main.py.
    Il margine è già applicato a monte in odds_api.py — questa funzione non fa nulla.
    """
    return odds_data

def get_sports(api_key: str): return []
