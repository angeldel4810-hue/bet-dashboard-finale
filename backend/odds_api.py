import requests
from typing import Dict, List, Any, Set
from diskcache import Cache
import os
import time
from datetime import datetime, timedelta, timezone

cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
cache = Cache(cache_dir)

FOOTBALL_API_BASE_URL = "https://v3.football.api-sports.io"

def get_odds_api_football(api_key: str, league_id_str: str, season: str = "2025") -> List[Dict[str, Any]]:
    """
    Recupera le quote da API-Football caricando l'intero palinsesto quotidiano.
    """
    headers = { 'x-apisports-key': api_key }
    today_now = datetime.now(timezone.utc)
    dates = [today_now.strftime("%Y-%m-%d"), (today_now + timedelta(days=1)).strftime("%Y-%m-%d")]
    
    all_normalized = []
    
    for date_str in dates:
        # Cache key v7 for force-refresh
        cache_key_date = f"af_global_odds_v7_{date_str}"
        day_odds = cache.get(cache_key_date)
        
        if day_odds is None:
            print(f"AF: Caricamento globale per {date_str}...")
            # 1. Recupero Fixtures
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
                print(f"Errore caricamento fixtures AF: {e}")

            # 2. Recupero Odds
            day_odds_dict = {}
            try:
                r_odds = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers, params={'date': date_str}, timeout=15)
                if r_odds.status_code == 200:
                    data = r_odds.json()
                    if not data.get('response') and data.get('errors'):
                        print(f"Errore API-Football: {data['errors']}")
                        # Se c'è un errore (es. rate limit), NON CACHIAMO nulla per riprovare subito
                        continue

                    total_pages = data.get('paging', {}).get('total', 1)
                    for page in range(1, total_pages + 1):
                        if page > 1:
                            # Piccola pausa tra le pagine per evitare rate limit istantaneo
                            time.sleep(0.3)
                            resp = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers, 
                                              params={'date': date_str, 'page': page}, timeout=15)
                            if resp.status_code == 200:
                                data = resp.json()
                            else: break
                        
                        for item in data.get('response', []):
                            fid = item['fixture']['id']
                            if fid in f_map:
                                norm = fast_normalize(item, f_map[fid])
                                if norm: day_odds_dict[fid] = norm
            except Exception as e:
                print(f"Errore caricamento odds AF: {e}")

            if not day_odds_dict and not f_map:
                # Cache empty list for 60 seconds to avoid API hammering on failure
                day_odds = []
                cache.set(cache_key_date, day_odds, expire=60)
            else:
                day_odds = list(day_odds_dict.values())
                # Cache valida per 10 minuti se popolata
                cache.set(cache_key_date, day_odds, expire=600)
        
        # Filtro finale
        try:
            target_id = int(league_id_str.strip())
            league_matches = [m for m in day_odds if m['league_id'] == target_id]
            all_normalized.extend(league_matches)
        except: pass

    return all_normalized

def fast_normalize(item: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    if not item.get('bookmakers'): return None
    # Priorità: Bet365(8), Bwin(1), Marathonbet(2), Unibet(3)
    bookie = next((b for b in item['bookmakers'] if b['id'] == 8), None)
    if not bookie: bookie = next((b for b in item['bookmakers'] if b['id'] in [1, 2, 3]), item['bookmakers'][0])
    
    bets = bookie.get('bets') or bookie.get('markets')
    if not bets: return None
    
    markets_dict = {}
    for m in bets:
        m_k = None
        m_name = m['name']
        if m_name == "Match Winner": m_k = 'h2h'
        elif m_name == "Goals Over/Under": m_k = 'totals'
        elif m_name == "Both Teams Score": m_k = 'btts'
        elif m_name == "Double Chance": m_k = 'double_chance'
        elif m_name == "Draw No Bet": m_k = 'draw_no_bet'
        elif m_name == "Exact Score": m_k = 'exact_score'
        elif m_name == "HT/FT Double": m_k = 'ht_ft'
        elif m_name == "First Half Winner": m_k = 'h2h_1st_half'
        elif m_name == "Second Half Winner": m_k = 'h2h_2nd_half'
        elif m_name == "Odd/Even": m_k = 'odd_even'
        elif m_name == "Goals Over/Under First Half": m_k = 'totals_1st_half'
        elif m_name == "Handicap Result": m_k = 'handicap_euro'
        elif m_name == "Win To Nil": m_k = 'win_to_nil'
        
        if not m_k or m_k in markets_dict: continue
        
        outcomes_dict = {}
        for val in m['values']:
            o_v = str(val['value'])
            o_n = o_v
            
            # Normalizzazione Nomi Squadre e Pareggio in tutti i mercati
            o_n = o_n.replace('Home', meta['home']).replace('Away', meta['away']).replace('Draw', 'Pareggio')
            if o_n == 'X': o_n = 'Pareggio'
            
            point = None
            if m_k == 'totals':
                if "2.5" not in o_v: continue
                point = 2.5
                o_n = "Over" if "Over" in o_v else "Under"
            
            if m_k == 'totals_1st_half':
                if "1.5" not in o_v: continue
                point = 1.5
                o_n = "1T Over" if "Over" in o_v else "1T Under"
                
            if m_k == 'btts':
                o_n = "Goal" if o_v == "Yes" else "No Goal"
                
            if m_k == 'ht_ft':
                # Riscatto la forma compatta 1/1, 1/X etc lavorando sul valore originale 'Home', 'Away', 'Draw'
                o_n = o_v.replace('Home', '1').replace('Away', '2').replace('Draw', 'X')
            
            if m_k == 'win_to_nil':
                o_n = f"Vince a Zero: {meta['home']}" if o_v == 'Home' else f"Vince a Zero: {meta['away']}" if o_v == 'Away' else o_n
            
            if o_n not in outcomes_dict:
                outcomes_dict[o_n] = {"name": o_n, "price": float(val['odd']), "point": point}
        
        if outcomes_dict:
            markets_dict[m_k] = {"key": m_k, "outcomes": list(outcomes_dict.values())}

    if not markets_dict: return None
    return {
        "id": f"af-{item['fixture']['id']}",
        "league_id": meta['league_id'],
        "sport_title": meta['league_name'],
        "commence_time": meta['time'],
        "home_team": meta['home'],
        "away_team": meta['away'],
        "bookmakers": [{"key": bookie['name'].lower(), "title": bookie['name'], "markets": list(markets_dict.values())}]
    }

def get_odds_the_odds_api(api_key: str, sport: str, regions: str = "eu") -> List[Dict[str, Any]]:
    # Se lo sport non è specificato bene, fallback al calcio mondiale
    if not sport: sport = 'soccer'
    
    # Lista mercati desiderati (CALCIO)
    soccer_mkts = "h2h,totals,spreads,btts,double_chance,draw_no_bet,h2h_1st_half,totals_1st_half,correct_score"
    # Lista mercati desiderati (BASKET)
    basket_mkts = "h2h,spreads,totals"
    # Lista mercati desiderati (TENNIS)
    tennis_mkts = "h2h,spreads,totals,outrights"
    
    markets = soccer_mkts
    if 'basketball' in sport: markets = basket_mkts
    elif 'tennis' in sport: markets = tennis_mkts
    
    cache_key = f"odds_toa_v11_{sport}_{regions}_{markets}"
    cached_data = cache.get(cache_key)
    if cached_data: return cached_data
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": api_key, 
        "regions": regions, 
        "markets": markets, 
        "oddsFormat": "decimal",
        "bookmakers": "bet365,williamhill,unibet,bwin,marathonbet,betfair_ex_eu,paddypower"
    }
    
    try:
        r = requests.get(url, params=params, timeout=12)
        if r.status_code == 422:
            # Fallback 1: Solo mercati garantiti per il piano base (H2H, Totals, Spreads)
            print(f"Fallback 422 (1) per {sport}, uso mercati piano base")
            params["markets"] = "h2h,totals,spreads"
            r = requests.get(url, params=params, timeout=12)
            
        if r.status_code == 422:
            # Fallback 2: Solo H2H e Totals (estremo)
            print(f"Fallback 422 (2) per {sport}, solo mercati minimi")
            params["markets"] = "h2h,totals"
            r = requests.get(url, params=params, timeout=12)
            
        r.raise_for_status()
        data = r.json()
        
        # Pulizia, normalizzazione e MERGE dei mercati
        for event in data:
            # Creiamo un bookmaker "virtuale" che contiene il meglio di tutti
            virtual_markets = {}
            
            # Ordiniamo i bookmaker per dare precedenza a Bet365
            sorted_bookies = sorted(event.get('bookmakers', []), 
                                 key=lambda x: 0 if x['key'] == 'bet365' else 1)
            
            for bookie in sorted_bookies:
                for market in bookie.get('markets', []):
                    m_key = market['key']
                    if m_key not in virtual_markets:
                        virtual_markets[m_key] = market
                    else:
                        # Per totals: aggiungiamo solo outcome se la linea (point) è già presente
                        # per ENTRAMBI Over e Under, evitando il mix di linee diverse
                        if m_key == 'totals':
                            existing_points = {}
                            for o in virtual_markets[m_key]['outcomes']:
                                pt = o.get('point')
                                if pt is not None:
                                    side = 'over' if 'Over' in str(o.get('name','')) else 'under'
                                    existing_points.setdefault(pt, set()).add(side)
                            for outcome in market.get('outcomes', []):
                                pt = outcome.get('point')
                                if pt is not None and outcome['name'] not in {o['name'] for o in virtual_markets[m_key]['outcomes']}:
                                    virtual_markets[m_key]['outcomes'].append(outcome)
                        else:
                            existing_outcomes = {o['name']: o for o in virtual_markets[m_key]['outcomes']}
                            for outcome in market.get('outcomes', []):
                                if outcome['name'] not in existing_outcomes:
                                    virtual_markets[m_key]['outcomes'].append(outcome)

            # Sostituiamo i bookmaker con il nostro virtuale consolidato
            event['bookmakers'] = [{
                "key": "bests_odds",
                "title": "Simus Bet Global",
                "markets": list(virtual_markets.values())
            }]

            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    for outcome in market.get('outcomes', []):
                        name = str(outcome.get('name', ''))
                        
                        # Pareggio
                        if name == 'Draw': outcome['name'] = 'Pareggio'
                        
                        # BTTS
                        if market['key'] == 'btts':
                            if name == 'Yes': outcome['name'] = 'Goal'
                            if name == 'No': outcome['name'] = 'No Goal'
                        
                        # Totals (Over/Under) — assicura che point sia float
                        if market['key'] == 'totals' and 'point' in outcome:
                            try:
                                outcome['point'] = float(outcome['point'])
                            except (ValueError, TypeError):
                                pass
                            point = outcome['point']
                            if 'Over' in name: outcome['name'] = f"Over {point}"
                            if 'Under' in name: outcome['name'] = f"Under {point}"
                                
                        # Doppia Chance
                        if market['key'] == 'double_chance':
                            if name == 'Home/Draw' or name == 'Draw/Home': outcome['name'] = '1X'
                            elif name == 'Away/Draw' or name == 'Draw/Away': outcome['name'] = 'X2'
                            elif name == 'Home/Away' or name == 'Away/Home': outcome['name'] = '12'
                            
                        # Handicap
                        if market['key'] in ['handicaps', 'alternate_totals', 'spreads'] and 'point' in outcome:
                            p = outcome['point']
                            prefix = "+" if p > 0 else ""
                            if 'Over' in name: outcome['name'] = f"Over {p}"
                            elif 'Under' in name: outcome['name'] = f"Under {p}"
                            else: outcome['name'] = f"{name} ({prefix}{p})"
                            
                        # Betfair Lay - Rimosso
                        if market['key'] == 'h2h_lay':
                            continue

            # Pulizia totals: rimuove linee incomplete (senza sia Over che Under)
            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    if market['key'] == 'totals':
                        # Raggruppa per punto
                        by_point = {}
                        for o in market['outcomes']:
                            pt = o.get('point')
                            if pt is None:
                                # Prova a estrarre il punto dal nome
                                try:
                                    pt = float(str(o['name']).split()[-1])
                                    o['point'] = pt
                                except (ValueError, IndexError):
                                    continue
                            by_point.setdefault(float(pt), []).append(o)
                        # Tieni solo linee con sia Over che Under
                        clean = []
                        for pt, outcomes in by_point.items():
                            has_over = any('Over' in str(o['name']) for o in outcomes)
                            has_under = any('Under' in str(o['name']) for o in outcomes)
                            if has_over and has_under:
                                clean.extend(outcomes)
                        market['outcomes'] = clean
        
        # SIMULA MERCATI MANCANTI (per piani API limitati)
        for event in data:
            try:
                simulate_markets(event)
            except Exception as sim_err:
                print(f"Errore simulazione mercati: {sim_err}")

        # Cache 30 minuti per migliorare la velocità
        cache.set(cache_key, data, expire=1800)
        return data
    except Exception as e:
        if 'r' in locals():
            print(f"Errore The Odds API for {sport}: {e}")
            print(f"URL: {r.url}")
            print(f"Response: {r.text}")
        else:
            print(f"Errore The Odds API for {sport}: {e}")
        return []

def apply_overround(odds_data: List[Dict[str, Any]], overround_percent: float) -> List[Dict[str, Any]]:
    """
    Applica il margine della casa in modo corretto:
    1. Rimuove il margine gia incluso dal bookmaker originale (normalizza le probabilita)
    2. Applica il margine desiderato
    Evita il doppio overround che abbassava le quote sotto i valori di mercato.
    """
    target_margin = 1 + (overround_percent / 100)
    for event in odds_data:
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                outcomes = market.get('outcomes', [])
                prices = [o.get('price') for o in outcomes if isinstance(o.get('price'), (int, float))]
                if len(prices) < 2:
                    continue
                # Step 1: probabilità implicite normalizzate (rimuove margine bookmaker)
                raw_probs = [1.0 / p for p in prices]
                total = sum(raw_probs)
                if total <= 0:
                    continue
                fair_probs = [p / total for p in raw_probs]
                # Step 2: applica il nostro margine
                idx = 0
                for o in outcomes:
                    if isinstance(o.get('price'), (int, float)):
                        new_price = round(1.0 / (fair_probs[idx] * target_margin), 2)
                        o['price'] = max(1.05, new_price)
                        idx += 1
    return odds_data

def simulate_markets(event: Dict[str, Any]):
    """
    Simula mercati avanzati (Double Chance, BTTS, etc) partendo dai dati base.
    I mercati simulati vengono marcati con _simulated=True per evitare
    che main.py applichi un secondo overround sopra.
    """
    if not event.get('bookmakers'): return
    m_list = event['bookmakers'][0].get('markets', [])
    m_keys = {m['key'] for m in m_list}

    def add_market(key, outcomes):
        """Aggiunge un mercato simulato marcandolo come tale."""
        m_list.append({"key": key, "outcomes": outcomes, "_simulated": True})
    m_keys = {m['key'] for m in m_list}
    
    h2h = next((m for m in m_list if m['key'] == 'h2h'), None)
    totals = next((m for m in m_list if m['key'] == 'totals'), None)

    import math

    # Dati base per calcio
    if h2h:
        h_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
        a_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
        x_price = next((o['price'] for o in h2h['outcomes'] if o['name'] in ['Draw', 'Pareggio', 'X']), None)
        
        if h_price and x_price and a_price:
            prob_h = 1/h_price; prob_x = 1/x_price; prob_a = 1/a_price
            sum_p = prob_h + prob_x + prob_a
            ph = prob_h/sum_p; px = prob_x/sum_p; pa = prob_a/sum_p

            # 1. DOUBLE CHANCE
            if 'double_chance' not in m_keys:
                add_market("double_chance", [
                    {"name": "1X", "price": round(0.91 / (ph + px), 2)},
                    {"name": "X2", "price": round(0.91 / (pa + px), 2)},
                    {"name": "12", "price": round(0.91 / (ph + pa), 2)}
                ])

            # 2. DRAW NO BET
            if 'draw_no_bet' not in m_keys:
                add_market("draw_no_bet", [
                    {"name": event['home_team'], "price": max(1.05, round(1.0 / (ph / (ph + pa) * 1.10), 2))},
                    {"name": event['away_team'], "price": max(1.05, round(1.0 / (pa / (ph + pa) * 1.10), 2))}
                ])

            # 3. RISULTATO 1° TEMPO
            if 'h2h_1st_half' not in m_keys:
                # Il 1° tempo è più equilibrato verso il pareggio
                ph1 = max(1.05, round(h_price * 1.35, 2))
                px1 = max(1.40, round(x_price * 0.72, 2))
                pa1 = max(1.05, round(a_price * 1.35, 2))
                add_market("h2h_1st_half", [
                    {"name": event['home_team'], "price": ph1},
                    {"name": "Pareggio", "price": px1},
                    {"name": event['away_team'], "price": pa1}
                ])

    # 4. BTTS (Goal / No Goal) — formula calibrata su dati reali
    if 'btts' not in m_keys:
        o25 = 1.9
        if totals:
            o25_match = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Over' in o['name']), 1.9)
            o25 = float(o25_match)
        prob_over = 1.0 / max(1.01, o25)
        prob_gg_fair = min(0.72, max(0.32, prob_over * 0.72 + 0.13))
        prob_ng_fair = 1.0 - prob_gg_fair
        MARGIN = 1.10
        add_market("btts", [
            {"name": "Goal",    "price": max(1.30, round(1.0 / (prob_gg_fair * MARGIN), 2))},
            {"name": "No Goal", "price": max(1.30, round(1.0 / (prob_ng_fair * MARGIN), 2))}
        ])

    # 5. OVER/UNDER LINEE AGGIUNTIVE (1.5, 3.5, 4.5) — Poisson da Over 2.5
    if totals:
        existing_lines = {o.get('point') for o in totals['outcomes']}
        o25_price = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Over' in o['name']), 1.9)
        o25_price = float(o25_price)
        prob_o25 = 1.0 / max(1.01, o25_price)
        # Lambda via ricerca binaria su P(X>2.5) Poisson
        def _p_over25(lam):
            return 1 - math.exp(-lam) * (1 + lam + lam**2/2)
        lo2, hi2 = 0.5, 8.0
        for _ in range(40):
            mid2 = (lo2 + hi2) / 2
            if _p_over25(mid2) < prob_o25: lo2 = mid2
            else: hi2 = mid2
        lam = mid2
        def prob_over_line(lam, line):
            k_max = int(line)
            p_under = sum((lam**k * math.exp(-lam)) / math.factorial(k) for k in range(k_max + 1))
            return max(0.02, min(0.98, 1.0 - p_under))
        MARGIN = 1.10
        for line in [1.5, 3.5, 4.5]:
            if line not in existing_lines:
                p_over = prob_over_line(lam, line)
                p_under = 1.0 - p_over
                # Aggiungo direttamente a totals['outcomes'] (non come mercato separato)
                totals['outcomes'].append({"name": f"Over {line}",  "price": max(1.05, round(1.0/(p_over*MARGIN),  2)), "point": line, "_simulated": True})
                totals['outcomes'].append({"name": f"Under {line}", "price": max(1.05, round(1.0/(p_under*MARGIN), 2)), "point": line, "_simulated": True})

    # 6. RISULTATO ESATTO — Poisson da quote 1X2
    if 'correct_score' not in m_keys and h2h:
        h_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
        a_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
        x_price = next((o['price'] for o in h2h['outcomes'] if o['name'] in ['Draw', 'Pareggio', 'X']), None)
        if h_price and a_price and x_price:
            ph2 = 1/h_price; px2 = 1/x_price; pa2 = 1/a_price
            tot2 = ph2 + px2 + pa2
            ph2 /= tot2; px2 /= tot2; pa2 /= tot2
            lh = max(0.5, min(3.5, -math.log(max(0.01, px2 + pa2)) * 1.1 + 0.3))
            la = max(0.3, min(2.5, -math.log(max(0.01, px2 + ph2)) * 0.9 + 0.1))
            def pois(lam, k):
                return (lam**k * math.exp(-lam)) / math.factorial(min(k, 10))
            scores = ["1-0","2-0","2-1","3-0","3-1","3-2","0-0","1-1","2-2","0-1","0-2","1-2","0-3","1-3","2-3","Altro"]
            exact_probs = {}
            total_named = 0
            for s in scores[:-1]:
                hg, ag = int(s[0]), int(s[2])
                p = pois(lh, hg) * pois(la, ag)
                exact_probs[s] = p
                total_named += p
            exact_probs["Altro"] = max(0.02, 1.0 - total_named)
            MARGIN = 1.10
            cs_outcomes = []
            for s in scores:
                p = exact_probs.get(s, 0.02)
                q = round(min(99.0, max(1.05, 1.0 / max(0.001, p) / MARGIN * (1/MARGIN) * MARGIN), 2), 2)
                cs_outcomes.append({"name": s, "price": round(min(99.0, max(1.05, 1.0/(max(0.001,p)*MARGIN))), 2)})
            add_market("correct_score", cs_outcomes)

    # 7. COMBO 1X2 + GG/NG
    if 'combo_1x2_btts' not in m_keys and h2h:
        h_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
        a_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
        x_price = next((o['price'] for o in h2h['outcomes'] if o['name'] in ['Draw', 'Pareggio', 'X']), None)
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        gg_price = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'), None) if btts_m else None
        ng_price = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None) if btts_m else None
        if h_price and x_price and a_price and gg_price and ng_price:
            MARGIN = 1.10
            combo_btts = []
            for res_name, res_price in [("1", h_price), ("X", x_price), ("2", a_price)]:
                for btts_name, btts_price in [("GG", gg_price), ("NG", ng_price)]:
                    combo_price = max(1.05, round(res_price * btts_price / MARGIN, 2))
                    combo_btts.append({"name": f"{res_name}+{btts_name}", "price": combo_price})
            add_market("combo_1x2_btts", combo_btts)

    # 8. COMBO 1X2 + OVER/UNDER
    if 'combo_1x2_ou' not in m_keys and h2h and totals:
        h_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
        a_price = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
        x_price = next((o['price'] for o in h2h['outcomes'] if o['name'] in ['Draw', 'Pareggio', 'X']), None)
        if h_price and x_price and a_price:
            MARGIN = 1.10
            combo_ou = []
            lines = {}
            for o in totals['outcomes']:
                pt = o.get('point')
                if pt is not None:
                    if pt not in lines: lines[pt] = {}
                    if 'Over' in o['name']:  lines[pt]['over']  = o['price']
                    elif 'Under' in o['name']: lines[pt]['under'] = o['price']
            for pt in sorted(lines.keys()):
                over_p  = lines[pt].get('over')
                under_p = lines[pt].get('under')
                for res_name, res_price in [("1", h_price), ("X", x_price), ("2", a_price)]:
                    if over_p:
                        combo_ou.append({"name": f"{res_name}+Over {pt}",  "price": max(1.05, round(res_price * over_p  / MARGIN, 2)), "point": pt})
                    if under_p:
                        combo_ou.append({"name": f"{res_name}+Under {pt}", "price": max(1.05, round(res_price * under_p / MARGIN, 2)), "point": pt})
            if combo_ou:
                add_market("combo_1x2_ou", combo_ou)

def get_sports(api_key: str): return []

def get_odds_betsapi2_rapidapi(api_key: str, sport_id: str = "1") -> List[Dict[str, Any]]:
    """
    Fetch upcoming matches and their pre-match odds from BetsAPI2 on RapidAPI.
    Limits to 10 matches to save rapidapi quota.
    """
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "betsapi2.p.rapidapi.com"
    }
    
    cache_key = f"rapidapi_betsapi2_upcoming_v8_{sport_id}"
    cached_odds = cache.get(cache_key)
    if cached_odds is not None:
        return cached_odds

    print("RAPIDAPI: Fetching upcoming matches...")
    all_normalized = []
    
    try:
        # 1. Ottenere le partite in programma
        upcoming_url = "https://betsapi2.p.rapidapi.com/v1/bet365/upcoming"
        qs = {"sport_id": sport_id, "day": "today"}
        r_up = requests.get(upcoming_url, headers=headers, params=qs, timeout=15)
        
        if r_up.status_code == 200:
            data = r_up.json()
            matches = data.get('results', [])
            
            # Aumentiamo a 25 partite per mostrare "PIÙ MATCH" sul sito
            matches = matches[:25]             
            for match in matches:
                fixt_id = match.get('id')
                if not fixt_id: continue
                
                # 2. Ottenere le quote pre-match per singola partita
                odds_url = "https://betsapi2.p.rapidapi.com/v3/bet365/prematch"
                odds_qs = {"FI": str(fixt_id)}
                
                r_odds = requests.get(odds_url, headers=headers, params=odds_qs, timeout=15)
                if r_odds.status_code == 200:
                    odds_data = r_odds.json()
                    
                    if odds_data.get('results') and len(odds_data['results']) > 0:
                        raw_markets = odds_data['results'][0]
                        normalized = normalize_betsapi2(raw_markets, match)
                        if normalized:
                            all_normalized.append(normalized)
                
                # Pausa anti-spam
                time.sleep(0.5)
                
    except Exception as e:
        print(f"Errore caricamento BetsAPI2: {e}")

    # Salva in cache per 30 minuti consistentemente con TOA
    cache.set(cache_key, all_normalized, expire=1800)
    return all_normalized

def normalize_betsapi2(raw_markets: Dict[str, Any], match_meta: dict) -> Dict[str, Any]:
    markets_dict = {}
    
    home_team = match_meta.get('home', {}).get('name', 'Home')
    away_team = match_meta.get('away', {}).get('name', 'Away')
    commence_time = str(match_meta.get('time', ''))
    try:
        if commence_time.isdigit():
            dt = datetime.fromtimestamp(int(commence_time), tz=timezone.utc)
            commence_time = dt.isoformat()
    except: pass
    
    # helper for nested SP lookups
    def get_sp(cat_key):
        return raw_markets.get(cat_key, {}).get('sp', {})

    main_sp = get_sp('main')
    goals_sp = get_sp('goals')
    halves_sp = get_sp('halves')
    corners_sp = get_sp('corners')
    cards_sp = get_sp('cards')

    # 1. H2H
    ft_res = main_sp.get('full_time_result', {})
    if ft_res and ft_res.get('odds'):
        outcomes = []
        for o in ft_res['odds']:
            nm = o.get('name')
            if nm == '1': n = home_team
            elif nm == '2': n = away_team
            else: n = 'Pareggio'
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['h2h'] = {"key": "h2h", "outcomes": outcomes}

    # 2. BTTS
    btts = main_sp.get('both_teams_to_score', {})
    if btts and btts.get('odds'):
        outcomes = []
        for o in btts['odds']:
            n = 'Goal' if o.get('name') == 'Yes' else 'No Goal'
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['btts'] = {"key": "btts", "outcomes": outcomes}

    # 3. DOUBLE CHANCE
    dc = main_sp.get('double_chance', {})
    if dc and dc.get('odds'):
        outcomes = []
        # Mapping 1X, X2, 12
        for o in dc['odds']:
            n = o.get('name')
            if n == '1X': outcomes.append({"name": "1X", "price": float(o.get('odds', 0))})
            elif n == 'X2': outcomes.append({"name": "X2", "price": float(o.get('odds', 0))})
            elif n == '12': outcomes.append({"name": "12", "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['double_chance'] = {"key": "double_chance", "outcomes": outcomes}

    # 4. DRAW NO BET
    dnb = main_sp.get('draw_no_bet', {})
    if dnb and dnb.get('odds'):
        outcomes = []
        for o in dnb['odds']:
            n = home_team if o.get('name') == '1' else away_team
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['draw_no_bet'] = {"key": "draw_no_bet", "outcomes": outcomes}

    # 5. TOTALS (Over/Under 2.5 is prioritized)
    ou = goals_sp.get('goals_over_under', {}) or main_sp.get('goals_over_under', {})
    if ou and ou.get('odds'):
        outcomes = []
        for o in ou['odds']:
            point = o.get('name')
            header = o.get('header')
            n = f"{header} {point}"
            if point == "2.5": # Backwards compatibility for UI
                n = header 
            outcomes.append({"name": n, "price": float(o.get('odds', 0)), "point": float(point)})
        if outcomes: markets_dict['totals'] = {"key": "totals", "outcomes": outcomes}

    # 6. CORRECT SCORE
    cs = main_sp.get('correct_score', {})
    if cs and cs.get('odds'):
        outcomes = [{"name": o.get('name'), "price": float(o.get('odds', 0))} for o in cs['odds'][:12]] # Limit to 12
        if outcomes: markets_dict['correct_score'] = {"key": "correct_score", "outcomes": outcomes}

    # 7. CORNERS
    tc = corners_sp.get('total_corners', {}) or main_sp.get('total_corners', {})
    if tc and tc.get('odds'):
        outcomes = []
        for o in tc['odds']:
            outcomes.append({"name": f"{o.get('header')} {o.get('name')}", "price": float(o.get('odds', 0)), "point": float(o.get('name', 0))})
        if outcomes: markets_dict['total_corners'] = {"key": "total_corners", "outcomes": outcomes}

    # 8. 1ST HALF RESULT
    h1r = halves_sp.get('half_time_result', {})
    if h1r and h1r.get('odds'):
        outcomes = []
        for o in h1r['odds']:
            nm = o.get('name')
            if nm == '1': n = home_team
            elif nm == '2': n = away_team
            else: n = 'Pareggio'
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes: markets_dict['h2h_1st_half'] = {"key": "h2h_1st_half", "outcomes": outcomes}

    if not markets_dict: return None
    
    league_name = match_meta.get('league', {}).get('name', 'Bet365 Soccer')
    return {
        "id": f"b365-{match_meta.get('id')}",
        "sport_title": league_name,
        "commence_time": commence_time,
        "home_team": home_team,
        "away_team": away_team,
        "bookmakers": [{"key": "bet365", "title": "Bet365", "markets": list(markets_dict.values())}]
    }
