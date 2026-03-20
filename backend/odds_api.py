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
HOUSE_EDGE = 1.07  # 7% vantaggio del banco

# ─── UTILITY ────────────────────────────────────────────────────────────────

def _normalize_with_margin(prices: List[float], margin: float = HOUSE_EDGE) -> List[float]:
    if len(prices) < 2:
        return prices
    raw_probs = [1.0 / p for p in prices]
    total = sum(raw_probs)
    if total <= 0:
        return prices
    fair_probs = [p / total for p in raw_probs]
    return [max(1.05, round(1.0 / (fp * margin), 2)) for fp in fair_probs]

def _apply_margin_to_event(event: Dict[str, Any]):
    for bookmaker in event.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            if market.get('_simulated'):
                continue
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
    if not event.get('bookmakers'):
        return
    m_list = event['bookmakers'][0].get('markets', [])
    m_keys = {m['key'] for m in m_list}

    def add(key, outcomes):
        m_list.append({"key": key, "outcomes": outcomes, "_simulated": True})

    h2h    = next((m for m in m_list if m['key'] == 'h2h'),    None)
    totals = next((m for m in m_list if m['key'] == 'totals'), None)

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

    o25_q = None
    lam = None
    if totals:
        o25_q = next((o['price'] for o in totals['outcomes']
                      if o.get('point') == 2.5 and 'Over' in str(o.get('name', ''))), None)
        if o25_q:
            # Usa la prob implicita diretta (formula correlazione calibrata su prob implicite)
            prob_o25 = min(0.95, max(0.05, 1.0 / float(o25_q)))
            lam = _lambda_from_over25(prob_o25)

    M = HOUSE_EDGE

    # Stima lambda casa e ospite — usato da tutti i mercati con correlazione
    lam_h = lam_a = None
    if lam is not None and ph is not None and pa is not None:
        ratio_h = ph / max(0.01, ph + pa)
        lam_h = max(0.3, min(3.5, lam * ratio_h * 1.05))
        lam_a = max(0.2, min(2.5, lam * (1.0 - ratio_h) * 0.95))

    # 1. DOUBLE CHANCE
    if 'double_chance' not in m_keys and ph is not None:
        add("double_chance", [
            {"name": "1X", "price": max(1.05, round(1.0 / ((ph + px) * M), 2))},
            {"name": "X2", "price": max(1.05, round(1.0 / ((pa + px) * M), 2))},
            {"name": "12", "price": max(1.05, round(1.0 / ((ph + pa) * M), 2))},
        ])

    # 2. DRAW NO BET
    if 'draw_no_bet' not in m_keys and ph is not None:
        sum_hna = ph + pa
        add("draw_no_bet", [
            {"name": event['home_team'], "price": max(1.05, round(1.0 / (ph / sum_hna * M), 2))},
            {"name": event['away_team'], "price": max(1.05, round(1.0 / (pa / sum_hna * M), 2))},
        ])

    # 3. RISULTATO 1° TEMPO
    if 'h2h_1st_half' not in m_keys and ph is not None:
        ph1 = ph * 0.80 + 0.07
        pa1 = pa * 0.80 + 0.07
        px1 = max(0.05, 1.0 - ph1 - pa1)
        tot1 = ph1 + px1 + pa1
        add("h2h_1st_half", [
            {"name": event['home_team'], "price": max(1.10, round(1.0 / (ph1/tot1 * M), 2))},
            {"name": "Pareggio",         "price": max(1.40, round(1.0 / (px1/tot1 * M), 2))},
            {"name": event['away_team'], "price": max(1.10, round(1.0 / (pa1/tot1 * M), 2))},
        ])

    # 4. BTTS
    if 'btts' not in m_keys:
        # Usa Poisson bivariata se disponibile, altrimenti formula calibrata
        if lam_h is not None and lam_a is not None:
            p_gg = sum(_poisson(lam_h,h)*_poisson(lam_a,a)
                       for h in range(8) for a in range(8) if h>0 and a>0)
            p_ng = max(0.01, 1.0 - p_gg)
        else:
            o25_ref = float(o25_q) if o25_q else 1.90
            prob_over = min(0.95, max(0.05, 1.0 / o25_ref))
            p_gg = min(0.72, max(0.28, prob_over * 0.72 + 0.13))
            p_ng = 1.0 - p_gg
        add("btts", [
            {"name": "Goal",    "price": max(1.20, round(1.0 / (p_gg * M), 2))},
            {"name": "No Goal", "price": max(1.20, round(1.0 / (p_ng * M), 2))},
        ])

    # 5. OVER/UNDER AGGIUNTIVE (1.5, 3.5, 4.5)
    if totals and lam is not None:
        existing = {o.get('point') for o in totals['outcomes']}
        for line in [1.5, 3.5, 4.5]:
            if line not in existing:
                p_ov = _prob_over_line(lam, line)
                p_un = 1.0 - p_ov
                totals['outcomes'].append({"name": f"Over {line}",  "price": max(1.05, round(1.0/(p_ov*M), 2)), "point": line, "_simulated": True})
                totals['outcomes'].append({"name": f"Under {line}", "price": max(1.05, round(1.0/(p_un*M), 2)), "point": line, "_simulated": True})

    # 6. RISULTATO ESATTO
    if 'correct_score' not in m_keys and ph is not None:
        if lam is not None:
            lam_total = lam
        else:
            lam_total = max(1.8, min(4.0, 2.5 / max(0.01, px + 0.3)))
        ratio_h = ph / max(0.01, ph + pa)
        lh = max(0.5, min(3.5, lam_total * ratio_h * 1.05))
        la = max(0.3, min(2.5, lam_total * (1.0 - ratio_h) * 0.95))
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
            cs_outcomes.append({"name": s, "price": min(66.0, max(1.05, round(1.0 / (p * M), 2)))})
        add("correct_score", cs_outcomes)

    # 7. COMBO 1X2 + GG/NG — Poisson bivariata per correlazione reale
    # (se vince "1" con GG, significa che l'ospite ha segnato almeno 1 → correlazione forte)
    if 'combo_1x2_btts' not in m_keys and ph is not None and lam_h is not None:
        combos_1x2_btts = []
        for hg in range(10):
            for ag in range(10):
                p = _poisson(lam_h, hg) * _poisson(lam_a, ag)
                res = "1" if hg > ag else ("X" if hg == ag else "2")
                gg  = hg > 0 and ag > 0
                key_name = f"{res}+{'GG' if gg else 'NG'}"
                # accumula probs
                existing = next((c for c in combos_1x2_btts if c['name']==key_name), None)
                if existing: existing['_p'] += p
                else: combos_1x2_btts.append({'name': key_name, '_p': p})
        # Converti in quote
        final = []
        for c in combos_1x2_btts:
            if c['_p'] > 0.005:
                final.append({"name": c['name'], "price": max(1.05, round(1.0/(c['_p']*M), 2))})
        # Ordine canonico: 1+GG, 1+NG, X+GG, X+NG, 2+GG, 2+NG
        order = ["1+GG","1+NG","X+GG","X+NG","2+GG","2+NG"]
        final.sort(key=lambda x: order.index(x['name']) if x['name'] in order else 99)
        if final:
            add("combo_1x2_btts", final)

    # 8. COMBO 1X2 + OVER/UNDER — Poisson bivariata per correlazione
    if 'combo_1x2_ou' not in m_keys and ph is not None and lam_h is not None and totals:
        lines_set = set()
        for o in totals['outcomes']:
            pt = o.get('point')
            if pt is not None: lines_set.add(float(pt))
        combos_ou = []
        for pt in sorted(lines_set):
            # accumula P(res AND over/under) via Poisson
            acc = {"1_over":0,"1_under":0,"X_over":0,"X_under":0,"2_over":0,"2_under":0}
            for hg in range(10):
                for ag in range(10):
                    p = _poisson(lam_h, hg) * _poisson(lam_a, ag)
                    res = "1" if hg>ag else ("X" if hg==ag else "2")
                    is_over = (hg+ag) > pt
                    acc[f"{res}_{'over' if is_over else 'under'}"] += p
            for rn in ["1","X","2"]:
                p_ov = acc[f"{rn}_over"];  p_un = acc[f"{rn}_under"]
                if p_ov > 0.003: combos_ou.append({"name": f"{rn}+Over {pt}",  "price": max(1.05, min(99.0, round(1.0/(p_ov*M),2))), "point": pt})
                if p_un > 0.003: combos_ou.append({"name": f"{rn}+Under {pt}", "price": max(1.05, min(99.0, round(1.0/(p_un*M),2))), "point": pt})
        if combos_ou:
            add("combo_1x2_ou", combos_ou)

    # ── Helper: costruisci lines_dict da totals (riusato da più combo) ──
    def _build_lines():
        if not totals:
            return {}
        ld: Dict[float, Dict] = {}
        for o in totals['outcomes']:
            pt = o.get('point')
            if pt is None: continue
            pt = float(pt)
            ld.setdefault(pt, {})
            if 'Over'  in str(o['name']): ld[pt]['over']  = o['price']
            if 'Under' in str(o['name']): ld[pt]['under'] = o['price']
        return ld

    # 9. DOPPIA CHANCE + GG/NG
    if 'combo_dc_btts' not in m_keys and ph is not None:
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        dc_m   = next((m for m in m_list if m['key'] == 'double_chance'), None)
        if btts_m and dc_m:
            gg_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'),    None)
            ng_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None)
            if gg_q and ng_q:
                combos = []
                for dc_o in dc_m['outcomes']:
                    dcn, dcq = dc_o['name'], dc_o['price']
                    combos.append({"name": f"{dcn}+GG", "price": max(1.05, round(dcq * gg_q / M, 2))})
                    combos.append({"name": f"{dcn}+NG", "price": max(1.05, round(dcq * ng_q / M, 2))})
                add("combo_dc_btts", combos)

    # 10. DOPPIA CHANCE + OVER/UNDER — Poisson bivariata
    if 'combo_dc_ou' not in m_keys and ph is not None and lam_h is not None:
        dc_map = {"1X": lambda hg,ag: hg>=ag, "X2": lambda hg,ag: hg<=ag, "12": lambda hg,ag: hg!=ag}
        combos = []
        for pt in [1.5, 2.5, 3.5, 4.5]:
            for dcn, dc_fn in dc_map.items():
                p_ov = p_un = 0.0
                for hg in range(10):
                    for ag in range(10):
                        p = _poisson(lam_h,hg)*_poisson(lam_a,ag)
                        if dc_fn(hg,ag):
                            if (hg+ag)>pt: p_ov+=p
                            else: p_un+=p
                if p_ov>0.003: combos.append({"name":f"{dcn}+Over {pt}", "price":max(1.05,min(99.0,round(1.0/(p_ov*M),2))),"point":pt})
                if p_un>0.003: combos.append({"name":f"{dcn}+Under {pt}","price":max(1.05,min(99.0,round(1.0/(p_un*M),2))),"point":pt})
        if combos:
            add("combo_dc_ou", combos)

    # 11. DRAW NO BET + GG/NG
    if 'combo_dnb_btts' not in m_keys and ph is not None:
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        dnb_m  = next((m for m in m_list if m['key'] == 'draw_no_bet'), None)
        if btts_m and dnb_m:
            gg_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'),    None)
            ng_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None)
            if gg_q and ng_q:
                combos = []
                for dnb_o in dnb_m['outcomes']:
                    dn, dq = dnb_o['name'], dnb_o['price']
                    combos.append({"name": f"{dn}+GG",      "price": max(1.05, round(dq * gg_q / M, 2))})
                    combos.append({"name": f"{dn}+No Goal", "price": max(1.05, round(dq * ng_q / M, 2))})
                add("combo_dnb_btts", combos)

    # 12. DRAW NO BET + OVER/UNDER — Poisson bivariata
    if 'combo_dnb_ou' not in m_keys and ph is not None and lam_h is not None:
        # DNB: home_team = casa vince (hg>ag), away_team = ospite vince (ag>hg)
        ht = event.get('home_team',''); at = event.get('away_team','')
        dnb_map = {ht: lambda hg,ag: hg>ag, at: lambda hg,ag: ag>hg}
        combos = []
        for pt in [1.5, 2.5, 3.5, 4.5]:
            for dn, dnb_fn in dnb_map.items():
                p_ov = p_un = 0.0
                for hg in range(10):
                    for ag in range(10):
                        p = _poisson(lam_h,hg)*_poisson(lam_a,ag)
                        if dnb_fn(hg,ag):
                            if (hg+ag)>pt: p_ov+=p
                            else: p_un+=p
                if p_ov>0.003: combos.append({"name":f"{dn}+Over {pt}", "price":max(1.05,min(99.0,round(1.0/(p_ov*M),2))),"point":pt})
                if p_un>0.003: combos.append({"name":f"{dn}+Under {pt}","price":max(1.05,min(99.0,round(1.0/(p_un*M),2))),"point":pt})
        if combos:
            add("combo_dnb_ou", combos)

    # 13. TRIPLA COMBO: 1X2 + GG/NG + OVER/UNDER 2.5
    if 'combo_1x2_btts_ou' not in m_keys and ph is not None:
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        if btts_m and totals:
            gg_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'),    None)
            ng_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None)
            ov25 = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Over'  in str(o['name'])), None)
            un25 = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Under' in str(o['name'])), None)
            if gg_q and ng_q and ov25 and un25:
                combos = []
                for rn, rq in [("1", h_q), ("X", x_q), ("2", a_q)]:
                    for bn, bq in [("GG", gg_q), ("NG", ng_q)]:
                        for ouln, ouq in [("Over 2.5", ov25), ("Under 2.5", un25)]:
                            combos.append({"name": f"{rn}+{bn}+{ouln}", "price": max(1.05, round(rq * bq * ouq / (M * M), 2))})
                add("combo_1x2_btts_ou", combos)

    # 14. 1° TEMPO + GG/NG
    if 'combo_ht_btts' not in m_keys and ph is not None:
        ht_m   = next((m for m in m_list if m['key'] == 'h2h_1st_half'), None)
        btts_m = next((m for m in m_list if m['key'] == 'btts'), None)
        if ht_m and btts_m:
            gg_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'Goal'),    None)
            ng_q = next((o['price'] for o in btts_m['outcomes'] if o['name'] == 'No Goal'), None)
            if gg_q and ng_q:
                combos = []
                for ht_o in ht_m['outcomes']:
                    hn = "1" if ht_o['name'] == event.get('home_team') else ("2" if ht_o['name'] == event.get('away_team') else "X")
                    hq = ht_o['price']
                    combos.append({"name": f"HT:{hn}+GG", "price": max(1.05, round(hq * gg_q / M, 2))})
                    combos.append({"name": f"HT:{hn}+NG", "price": max(1.05, round(hq * ng_q / M, 2))})
                add("combo_ht_btts", combos)

    # 15. 1° TEMPO + OVER/UNDER 2.5 FINALE
    if 'combo_ht_ou' not in m_keys and ph is not None:
        ht_m = next((m for m in m_list if m['key'] == 'h2h_1st_half'), None)
        if ht_m and totals:
            ov25 = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Over'  in str(o['name'])), None)
            un25 = next((o['price'] for o in totals['outcomes'] if o.get('point') == 2.5 and 'Under' in str(o['name'])), None)
            if ov25 and un25:
                combos = []
                for ht_o in ht_m['outcomes']:
                    hn = "1" if ht_o['name'] == event.get('home_team') else ("2" if ht_o['name'] == event.get('away_team') else "X")
                    hq = ht_o['price']
                    combos.append({"name": f"HT:{hn}+Over 2.5",  "price": max(1.05, round(hq * ov25 / M, 2))})
                    combos.append({"name": f"HT:{hn}+Under 2.5", "price": max(1.05, round(hq * un25 / M, 2))})
                add("combo_ht_ou", combos)

    # 16. PARI / DISPARI GOL
    if 'odd_even' not in m_keys and lam is not None:
        import math as _m
        p_even = sum(_poisson(lam, k) for k in range(0, 13, 2))
        p_odd  = 1.0 - p_even
        add("odd_even", [
            {"name": "Pari",    "price": max(1.60, round(1.0 / (p_even * M), 2))},
            {"name": "Dispari", "price": max(1.60, round(1.0 / (p_odd  * M), 2))},
        ])


    # ── Helper Poisson ───────────────────────────────────────────────────────
    def _p_exact(lam_x, n):
        """P(squadra segna esattamente n gol) con lambda lam_x."""
        return max(1e-9, _poisson(lam_x, n))

    def _p_range(lam_x, lo, hi):
        """P(squadra segna tra lo e hi gol inclusi)."""
        return max(0.005, sum(_poisson(lam_x, k) for k in range(lo, hi + 1)))

    def _p_ge(lam_x, lo):
        """P(squadra segna >= lo gol)."""
        return max(0.005, 1.0 - sum(_poisson(lam_x, k) for k in range(0, lo)))

    # ─── 17. MULTIGOL TOTALE (tutti i range sensati) ─────────────────────────
    if 'multigol' not in m_keys and lam is not None:
        ranges = [
            ("0-1", 0, 1), ("0-2", 0, 2), ("0-3", 0, 3), ("0-6", 0, 6),
            ("1-2", 1, 2), ("1-3", 1, 3), ("1-4", 1, 4), ("1-5", 1, 5), ("1-6", 1, 6),
            ("2-3", 2, 3), ("2-4", 2, 4), ("2-5", 2, 5), ("2-6", 2, 6),
            ("3-4", 3, 4), ("3-5", 3, 5), ("3-6", 3, 6),
            ("4-6", 4, 6), ("5-6", 5, 6),
            ("5+",  5, 12), ("6+", 6, 12), ("7+", 7, 12),
        ]
        mg_outcomes = []
        for label, lo, hi in ranges:
            p = _p_range(lam, lo, hi)
            mg_outcomes.append({"name": f"Multigol {label}", "price": max(1.05, min(99.0, round(1.0 / (p * M), 2)))})
        add("multigol", mg_outcomes)

    # ─── 18. MULTIGOL CASA (gol segnati dalla squadra di casa) ───────────────
    if 'multigol_home' not in m_keys and lam_h is not None:
        ranges_sq = [
            ("0",   0, 0), ("1",   1, 1), ("2",   2, 2), ("3+", 3, 12),
            ("0-1", 0, 1), ("0-2", 0, 2), ("1-2", 1, 2), ("1-3", 1, 3),
            ("2-3", 2, 3), ("2-4", 2, 4), ("3-4", 3, 4), ("4+", 4, 12),
        ]
        outcomes = []
        for label, lo, hi in ranges_sq:
            if lo == hi:
                p = _p_exact(lam_h, lo) if lo < 3 else _p_ge(lam_h, 3)
            else:
                p = _p_range(lam_h, lo, hi)
            outcomes.append({"name": f"Casa: {label}", "price": max(1.05, min(66.0, round(1.0 / (p * M), 2)))})
        add("multigol_home", outcomes)

    # ─── 19. MULTIGOL OSPITE (gol segnati dalla squadra ospite) ──────────────
    if 'multigol_away' not in m_keys and lam_a is not None:
        outcomes = []
        ranges_sq = [
            ("0",   0, 0), ("1",   1, 1), ("2",   2, 2), ("3+", 3, 12),
            ("0-1", 0, 1), ("0-2", 0, 2), ("1-2", 1, 2), ("1-3", 1, 3),
            ("2-3", 2, 3), ("2-4", 2, 4), ("3-4", 3, 4), ("4+", 4, 12),
        ]
        for label, lo, hi in ranges_sq:
            if lo == hi:
                p = _p_exact(lam_a, lo) if lo < 3 else _p_ge(lam_a, 3)
            else:
                p = _p_range(lam_a, lo, hi)
            outcomes.append({"name": f"Ospite: {label}", "price": max(1.05, min(66.0, round(1.0 / (p * M), 2)))})
        add("multigol_away", outcomes)

    # ─── 20. COMBO 1X2 + MULTIGOL TOTALE ─────────────────────────────────────
    if 'combo_1x2_multigol' not in m_keys and ph is not None and lam is not None:
        ranges_mg = [
            ("1-2", 1, 2), ("1-3", 1, 3), ("1-4", 1, 4),
            ("2-3", 2, 3), ("2-4", 2, 4), ("2-5", 2, 5),
            ("3-4", 3, 4), ("3-5", 3, 5), ("3+", 3, 12),
        ]
        combos = []
        for rn, rq in [("1", h_q), ("X", x_q), ("2", a_q)]:
            if rq is None: continue
            p_r = 1.0 / rq
            for label, lo, hi in ranges_mg:
                p_mg = _p_range(lam, lo, hi)
                price = max(1.05, round(1.0 / (p_r * p_mg * M), 2))
                combos.append({"name": f"{rn}+Multigol {label}", "price": price})
        if combos:
            add("combo_1x2_multigol", combos)

    # ─── 21. COMBO DOPPIA CHANCE + MULTIGOL ──────────────────────────────────
    if 'combo_dc_multigol' not in m_keys and ph is not None and lam is not None:
        dc_m = next((m for m in m_list if m['key'] == 'double_chance'), None)
        if dc_m:
            ranges_mg = [("1-2", 1, 2), ("1-3", 1, 3), ("2-3", 2, 3), ("2-4", 2, 4), ("3+", 3, 12)]
            combos = []
            for dc_o in dc_m['outcomes']:
                dcn, dcq = dc_o['name'], dc_o['price']
                p_dc = 1.0 / dcq
                for label, lo, hi in ranges_mg:
                    p_mg = _p_range(lam, lo, hi)
                    price = max(1.05, round(1.0 / (p_dc * p_mg * M), 2))
                    combos.append({"name": f"{dcn}+Multigol {label}", "price": price})
            if combos:
                add("combo_dc_multigol", combos)

    # ─── 22. COMBO OVER/UNDER + GG/NG ────────────────────────────────────────
    # Usa simulazione Poisson bivariata per catturare la correlazione reale
    # (Over 2.5+GG e Under 2.5+NG sono correlati positivamente — non indipendenti)
    if 'combo_ou_btts' not in m_keys and lam_h is not None and lam_a is not None:
        combos = []
        for pt in [1.5, 2.5, 3.5, 4.5]:
            # Calcola P(Over pt AND GG), P(Over pt AND NG), P(Under pt AND GG), P(Under pt AND NG)
            p_gg_over = p_ng_over = p_gg_under = p_ng_under = 0.0
            for hg in range(10):
                for ag in range(10):
                    p = _poisson(lam_h, hg) * _poisson(lam_a, ag)
                    is_over = (hg + ag) > pt
                    is_gg   = hg > 0 and ag > 0
                    if is_over and is_gg:     p_gg_over  += p
                    elif is_over and not is_gg: p_ng_over  += p
                    elif not is_over and is_gg: p_gg_under += p
                    else:                       p_ng_under += p
            # Quote con margine
            def _safe_q(p): return max(1.05, min(99.0, round(1.0 / (p * M), 2))) if p > 0.005 else None
            q_go = _safe_q(p_gg_over);  q_no = _safe_q(p_ng_over)
            q_gu = _safe_q(p_gg_under); q_nu = _safe_q(p_ng_under)
            if q_go:  combos.append({"name": f"Over {pt}+GG",      "price": q_go,  "point": pt})
            if q_no:  combos.append({"name": f"Over {pt}+No Goal", "price": q_no,  "point": pt})
            if q_gu:  combos.append({"name": f"Under {pt}+GG",     "price": q_gu,  "point": pt})
            if q_nu:  combos.append({"name": f"Under {pt}+No Goal","price": q_nu,  "point": pt})
        if combos:
            add("combo_ou_btts", combos)

    # ─── 23. MULTIGOL + GG/NG — Poisson bivariata ──────────────────────────
    if 'combo_multigol_btts' not in m_keys and lam_h is not None:
        ranges_mg = [("1-2",1,2),("2-3",2,3),("1-3",1,3),("2-4",2,4),("3-5",3,5),("3+",3,12)]
        combos = []
        for label, lo, hi in ranges_mg:
            p_gg = p_ng = 0.0
            for hg in range(10):
                for ag in range(10):
                    p = _poisson(lam_h, hg) * _poisson(lam_a, ag)
                    total = hg + ag
                    in_range = lo <= total <= hi
                    is_gg = hg > 0 and ag > 0
                    if in_range and is_gg:     p_gg += p
                    elif in_range and not is_gg: p_ng += p
            if p_gg > 0.003: combos.append({"name": f"Multigol {label}+GG",      "price": max(1.05, round(1.0/(p_gg*M),2))})
            if p_ng > 0.003: combos.append({"name": f"Multigol {label}+No Goal", "price": max(1.05, round(1.0/(p_ng*M),2))})
        if combos:
            add("combo_multigol_btts", combos)

    # ─── 24. GOL ESATTI TOTALI (0..6+) ───────────────────────────────────────
    if 'total_goals_exact' not in m_keys and lam is not None:
        outcomes = []
        for n in range(7):
            if n < 6:
                p = _p_exact(lam, n)
                label = f"{n} Gol"
            else:
                p = max(0.005, _p_ge(lam, 6))
                label = "6+ Gol"
            outcomes.append({"name": label, "price": max(1.05, min(66.0, round(1.0 / (p * M), 2)))})
        add("total_goals_exact", outcomes)

    # ─── 25. COMBO 1X2 + GOL ESATTI — solo range sensati per ciascun esito ──
    if 'combo_1x2_total_goals' not in m_keys and ph is not None and lam is not None:
        combos = []
        # Per "1" (casa vince): 1+ gol in casa garantiti → escludiamo 0 gol totali
        # Per "X" (pareggio):   almeno 0 gol; 0-0 possibile ma non misto
        # Per "2" (ospite vince): 1+ gol ospite garantiti
        goals_map = {
            "1": [(1, "1 Gol"), (2, "2 Gol"), (3, "3 Gol"), (4, "4+ Gol")],
            "X": [(0, "0 Gol"), (1, "1 Gol"), (2, "2 Gol"), (3, "3 Gol"), (4, "4+ Gol")],
            "2": [(1, "1 Gol"), (2, "2 Gol"), (3, "3 Gol"), (4, "4+ Gol")],
        }
        for rn, rq in [("1", h_q), ("X", x_q), ("2", a_q)]:
            if rq is None: continue
            p_r = 1.0 / rq
            for n, glabel in goals_map[rn]:
                if n < 4:
                    p_g = _p_exact(lam, n)
                else:
                    p_g = max(0.005, _p_ge(lam, 4))
                price = max(1.05, min(66.0, round(1.0 / (p_r * p_g * M), 2)))
                combos.append({"name": f"{rn}+{glabel}", "price": price})
        if combos:
            add("combo_1x2_total_goals", combos)




def _is_tennis_event(event: Dict[str, Any]) -> bool:
    sport = (event.get('sport_title') or event.get('sport_key') or '').lower()
    return any(kw in sport for kw in ['tennis','atp','wta','itf','challenger'])

def _simulate_tennis_markets(event: Dict[str, Any]):
    """Genera mercati tennis: vincitore partita, handicap set, over/under game."""
    if not event.get('bookmakers'):
        return
    m_list = event['bookmakers'][0].get('markets', [])
    m_keys = {m['key'] for m in m_list}
    M = HOUSE_EDGE

    def add(key, outcomes):
        m_list.append({"key": key, "outcomes": outcomes, "_simulated": True})

    # Quote base dalla h2h (vincitore partita)
    h2h = next((m for m in m_list if m['key'] == 'h2h'), None)
    if not h2h:
        return

    h_q = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['home_team']), None)
    a_q = next((o['price'] for o in h2h['outcomes'] if o['name'] == event['away_team']), None)
    if not h_q or not a_q:
        return

    ph = 1.0 / h_q
    pa = 1.0 / a_q
    tot = ph + pa
    ph /= tot; pa /= tot

    # 1. HANDICAP SET (+1.5 / -1.5) — simulato
    if 'set_spreads' not in m_keys:
        # Stima P(vince 2-0) vs P(vince 2-1) per calcolare l'handicap
        # Modello: P(home vince set) proporzionale a ph
        p_set_h = min(0.92, max(0.08, ph * 0.85 + 0.075))  # calibrato
        p_set_a = 1.0 - p_set_h

        # Bo3: P(2-0) = p^2, P(2-1) = 2*p*(1-p)*p, P(1-2) = ..., P(0-2) = (1-p)^2
        p_home_20 = p_set_h ** 2
        p_home_21 = 2 * p_set_h * p_set_a * p_set_h
        p_away_20 = p_set_a ** 2
        p_away_21 = 2 * p_set_a * p_set_h * p_set_a

        # -1.5 set home = home vince SENZA perdere un set (2-0)
        # +1.5 set home = home vince ANCHE perdendo un set, O perde entrambi i set ≤ 2
        p_h_minus15 = p_home_20  # casa vince 2-0
        p_a_minus15 = p_away_20  # ospite vince 2-0
        p_h_plus15  = p_home_20 + p_home_21 + p_away_21  # casa perde max 1 set, oppure ospite vince 2-1
        p_a_plus15  = p_away_20 + p_away_21 + p_home_21

        add("set_spreads", [
            {"name": f"{event['home_team']} -1.5",  "price": max(1.05, round(1.0/(p_h_minus15*M), 2)), "point": -1.5},
            {"name": f"{event['home_team']} +1.5",  "price": max(1.05, round(1.0/(p_h_plus15*M), 2)),  "point": 1.5},
            {"name": f"{event['away_team']} -1.5",  "price": max(1.05, round(1.0/(p_a_minus15*M), 2)), "point": -1.5},
            {"name": f"{event['away_team']} +1.5",  "price": max(1.05, round(1.0/(p_a_plus15*M), 2)),  "point": 1.5},
        ])

    # 2. TOTALE SET (Over/Under 2.5) — Bo3
    if 'set_totals' not in m_keys:
        p_set_h = min(0.92, max(0.08, ph * 0.85 + 0.075))
        p_set_a = 1.0 - p_set_h
        # 2 set = una squadra vince 2-0
        p_2sets = p_set_h**2 + p_set_a**2
        # 3 set = qualcuno vince 2-1
        p_3sets = 1.0 - p_2sets
        add("set_totals", [
            {"name": "Under 2.5 Set", "price": max(1.05, round(1.0/(p_2sets*M), 2)), "point": 2.5},
            {"name": "Over 2.5 Set",  "price": max(1.05, round(1.0/(p_3sets*M), 2)), "point": 2.5},
        ])

    # 3. DOPPIA CHANCE TENNIS (non esiste, ma aggiungiamo risultato set per set)
    # Chi vince il 1° set (utile per live betting)
    if 'h2h_1st_half' not in m_keys:
        p_set_h = min(0.92, max(0.08, ph * 0.85 + 0.075))
        p_set_a = 1.0 - p_set_h
        add("h2h_1st_half", [
            {"name": event['home_team'], "price": max(1.05, round(1.0/(p_set_h*M), 2))},
            {"name": event['away_team'], "price": max(1.05, round(1.0/(p_set_a*M), 2))},
        ])


# ─── THE ODDS API ────────────────────────────────────────────────────────────

def get_odds_the_odds_api(api_key: str, sport: str, regions: str = "eu") -> List[Dict[str, Any]]:
    if not sport:
        sport = 'soccer'

    markets = "h2h,totals,btts,double_chance,draw_no_bet,h2h_1st_half,correct_score"
    cache_key = f"odds_toa_v13_{sport}_{regions}"
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
            # Merge bookmaker con precedenza Bet365
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

            event['bookmakers'] = [{"key": "simus_bet", "title": "Simus Bet", "markets": list(virtual_markets.values())}]

            # Normalizzazione nomi — OGNI mercato trattato separatamente
            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    mk = market['key']
                    for o in market.get('outcomes', []):
                        name = str(o.get('name', ''))
                        if name == 'Draw':
                            o['name'] = 'Pareggio'
                        if mk == 'btts':
                            if name in ['Yes', 'yes', 'Goal', 'GG', '1']:
                                o['name'] = 'Goal'
                            elif name in ['No', 'no', 'No Goal', 'NG', '2']:
                                o['name'] = 'No Goal'
                        elif mk == 'totals' and 'point' in o:
                            try:
                                o['point'] = float(o['point'])
                            except Exception:
                                pass
                            if 'Over' in name:
                                o['name'] = f"Over {o['point']}"
                            elif 'Under' in name:
                                o['name'] = f"Under {o['point']}"
                        elif mk == 'double_chance':
                            if name in ['Home/Draw', 'Draw/Home']:
                                o['name'] = '1X'
                            elif name in ['Away/Draw', 'Draw/Away']:
                                o['name'] = 'X2'
                            elif name in ['Home/Away', 'Away/Home']:
                                o['name'] = '12'
                    # Goal sempre prima di No Goal
                    if mk == 'btts':
                        market['outcomes'].sort(key=lambda o: 0 if o.get('name') == 'Goal' else 1)

            # Pulizia totals: tieni solo linee con Over E Under
            for bookie in event.get('bookmakers', []):
                for market in bookie.get('markets', []):
                    if market['key'] != 'totals':
                        continue
                    by_pt: Dict[float, List] = {}
                    for o in market['outcomes']:
                        pt = o.get('point')
                        if pt is None:
                            try:
                                pt = float(str(o['name']).split()[-1])
                                o['point'] = pt
                            except Exception:
                                continue
                        by_pt.setdefault(float(pt), []).append(o)
                    clean = []
                    for pt, outs in by_pt.items():
                        if (any('Over' in str(o['name']) for o in outs) and
                                any('Under' in str(o['name']) for o in outs)):
                            clean.extend(outs)
                    market['outcomes'] = clean

            # Applica margine 7%
            _apply_margin_to_event(event)
            # Genera mercati mancanti
            try:
                if _is_tennis_event(event):
                    _simulate_tennis_markets(event)
                else:
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
        cache_key_date = f"af_global_odds_v9_{date_str}"
        day_odds = cache.get(cache_key_date)

        if day_odds is None:
            print(f"AF: Caricamento per {date_str}...")
            f_map = {}
            try:
                f_r = requests.get(f"{FOOTBALL_API_BASE_URL}/fixtures", headers=headers,
                                   params={'date': date_str}, timeout=15)
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
                r_odds = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers,
                                      params={'date': date_str}, timeout=15)
                if r_odds.status_code == 200:
                    data = r_odds.json()
                    if not data.get('response') and data.get('errors'):
                        print(f"Errore AF: {data['errors']}")
                        day_odds = []
                        cache.set(cache_key_date, day_odds, expire=60)
                        continue
                    total_pages = data.get('paging', {}).get('total', 1)
                    for page in range(1, total_pages + 1):
                        if page > 1:
                            time.sleep(0.3)
                            resp = requests.get(f"{FOOTBALL_API_BASE_URL}/odds", headers=headers,
                                                params={'date': date_str, 'page': page}, timeout=15)
                            if resp.status_code == 200:
                                data = resp.json()
                            else:
                                break
                        for item in data.get('response', []):
                            fid = item['fixture']['id']
                            if fid in f_map:
                                norm = _fast_normalize_af(item, f_map[fid])
                                if norm:
                                    day_odds_dict[fid] = norm
            except Exception as e:
                print(f"Errore odds AF: {e}")

            day_odds = list(day_odds_dict.values())
            cache.set(cache_key_date, day_odds, expire=600 if day_odds else 60)

        try:
            target_id = int(league_id_str.strip())
            all_normalized.extend(m for m in day_odds if m['league_id'] == target_id)
        except Exception:
            pass

    return all_normalized


def _fast_normalize_af(item: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    if not item.get('bookmakers'):
        return None
    bookie = next((b for b in item['bookmakers'] if b['id'] == 8), None)
    if not bookie:
        bookie = next((b for b in item['bookmakers'] if b['id'] in [1, 2, 3]), item['bookmakers'][0])
    bets = bookie.get('bets') or bookie.get('markets')
    if not bets:
        return None

    NAME_MAP = {
        "Match Winner":      'h2h',
        "Goals Over/Under":  'totals',
        "Both Teams Score":  'btts',
        "Double Chance":     'double_chance',
        "Draw No Bet":       'draw_no_bet',
        "Exact Score":       'correct_score',
        "First Half Winner": 'h2h_1st_half',
    }
    markets_dict = {}
    for m in bets:
        mk = NAME_MAP.get(m['name'])
        if not mk or mk in markets_dict:
            continue
        outcomes = []
        for val in m['values']:
            ov = str(val['value'])
            on = (ov.replace('Home', meta['home'])
                    .replace('Away', meta['away'])
                    .replace('Draw', 'Pareggio'))
            if on == 'X':
                on = 'Pareggio'
            point = None
            if mk == 'totals':
                if "2.5" not in ov:
                    continue
                point = 2.5
                on = "Over 2.5" if "Over" in ov else "Under 2.5"
            if mk == 'btts':
                on = "Goal" if ov == "Yes" else "No Goal"
            outcomes.append({"name": on, "price": float(val['odd']), "point": point})
        if outcomes:
            if mk == 'btts':
                outcomes.sort(key=lambda o: 0 if o.get('name') == 'Goal' else 1)
            markets_dict[mk] = {"key": mk, "outcomes": outcomes}

    if not markets_dict:
        return None
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
    if _is_tennis_event(event):
        _simulate_tennis_markets(event)
    else:
        _simulate_markets(event)
    return event


# ─── BETSAPI2 ────────────────────────────────────────────────────────────────

def get_odds_betsapi2_rapidapi(api_key: str, sport_id: str = "1") -> List[Dict[str, Any]]:
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": "betsapi2.p.rapidapi.com"}
    cache_key = f"rapidapi_betsapi2_v10_{sport_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    all_normalized = []
    try:
        r_up = requests.get("https://betsapi2.p.rapidapi.com/v1/bet365/upcoming",
                            headers=headers, params={"sport_id": sport_id, "day": "today"}, timeout=15)
        if r_up.status_code == 200:
            matches = r_up.json().get('results', [])[:25]
            for match in matches:
                fid = match.get('id')
                if not fid:
                    continue
                r_odds = requests.get("https://betsapi2.p.rapidapi.com/v3/bet365/prematch",
                                      headers=headers, params={"FI": str(fid)}, timeout=15)
                if r_odds.status_code == 200:
                    res = r_odds.json().get('results', [])
                    if res:
                        norm = _normalize_betsapi2(res[0], match)
                        if norm:
                            all_normalized.append(norm)
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
    except Exception:
        pass

    def sp(cat):
        return raw.get(cat, {}).get('sp', {})

    main_sp   = sp('main')
    goals_sp  = sp('goals')
    halves_sp = sp('halves')
    markets_dict = {}

    # H2H
    ftr = main_sp.get('full_time_result', {})
    if ftr and ftr.get('odds'):
        outcomes = []
        for o in ftr['odds']:
            n = home if o['name'] == '1' else (away if o['name'] == '2' else 'Pareggio')
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes:
            markets_dict['h2h'] = {"key": "h2h", "outcomes": outcomes}

    # BTTS
    btts = main_sp.get('both_teams_to_score', {})
    if btts and btts.get('odds'):
        outcomes = [{"name": "Goal" if o['name'] == 'Yes' else "No Goal",
                     "price": float(o.get('odds', 0))} for o in btts['odds']]
        if outcomes:
            outcomes.sort(key=lambda o: 0 if o.get('name') == 'Goal' else 1)
            markets_dict['btts'] = {"key": "btts", "outcomes": outcomes}

    # TOTALS
    ou = goals_sp.get('goals_over_under', {}) or main_sp.get('goals_over_under', {})
    if ou and ou.get('odds'):
        outcomes = []
        for o in ou['odds']:
            pt = o.get('name')
            if pt != '2.5':
                continue
            hdr = o.get('header', '')
            outcomes.append({"name": f"{'Over' if 'Over' in hdr else 'Under'} 2.5",
                             "price": float(o.get('odds', 0)), "point": 2.5})
        if outcomes:
            markets_dict['totals'] = {"key": "totals", "outcomes": outcomes}

    # CORRECT SCORE
    cs = main_sp.get('correct_score', {})
    if cs and cs.get('odds'):
        outcomes = [{"name": o.get('name'), "price": float(o.get('odds', 0))} for o in cs['odds'][:16]]
        if outcomes:
            markets_dict['correct_score'] = {"key": "correct_score", "outcomes": outcomes}

    # 1° TEMPO
    h1r = halves_sp.get('half_time_result', {})
    if h1r and h1r.get('odds'):
        outcomes = []
        for o in h1r['odds']:
            n = home if o['name'] == '1' else (away if o['name'] == '2' else 'Pareggio')
            outcomes.append({"name": n, "price": float(o.get('odds', 0))})
        if outcomes:
            markets_dict['h2h_1st_half'] = {"key": "h2h_1st_half", "outcomes": outcomes}

    if not markets_dict:
        return None

    event = {
        "id": f"b365-{meta.get('id')}",
        "sport_title": meta.get('league', {}).get('name', 'Soccer'),
        "commence_time": ct,
        "home_team": home,
        "away_team": away,
        "bookmakers": [{"key": "bet365", "title": "Bet365", "markets": list(markets_dict.values())}]
    }
    _apply_margin_to_event(event)
    if _is_tennis_event(event):
        _simulate_tennis_markets(event)
    else:
        _simulate_markets(event)
    return event


# ─── COMPATIBILITÀ ───────────────────────────────────────────────────────────

def apply_overround(odds_data: List[Dict[str, Any]], overround_percent: float) -> List[Dict[str, Any]]:
    return odds_data

def get_sports(api_key: str):
    return []
