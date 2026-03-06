import asyncio
import random
import math
import json
import traceback
from fastapi import APIRouter, Depends, HTTPException, Body
from backend.database import get_db

router = APIRouter()

# --- Configurazione Squadre Serie A Virtuale ---
SERIE_A_TEAMS = [
    {"name": "Atalanta",      "offense": 82, "defense": 78, "logo": "https://upload.wikimedia.org/wikipedia/en/6/66/AtalantaBC.svg"},
    {"name": "Bologna",       "offense": 75, "defense": 76, "logo": "https://upload.wikimedia.org/wikipedia/en/5/5b/Bologna_F.C._1909_logo.svg"},
    {"name": "Cagliari",      "offense": 68, "defense": 65, "logo": "https://upload.wikimedia.org/wikipedia/en/6/61/Cagliari_Calcio_1970_logo.svg"},
    {"name": "Como",          "offense": 67, "defense": 63, "logo": "https://upload.wikimedia.org/wikipedia/en/1/1e/Como_1907_logo.svg"},
    {"name": "Cremonese",     "offense": 66, "defense": 62, "logo": "https://upload.wikimedia.org/wikipedia/en/d/df/US_Cremonese_logo.svg"},
    {"name": "Fiorentina",    "offense": 78, "defense": 75, "logo": "https://upload.wikimedia.org/wikipedia/en/b/ba/ACF_Fiorentina_2022_logo.svg"},
    {"name": "Genoa",         "offense": 71, "defense": 70, "logo": "https://upload.wikimedia.org/wikipedia/en/6/6c/Genoa_C.F.C._logo.svg"},
    {"name": "Hellas Verona", "offense": 69, "defense": 68, "logo": "https://upload.wikimedia.org/wikipedia/en/9/92/Hellas_Verona_FC_logo_2020.svg"},
    {"name": "Inter",         "offense": 88, "defense": 85, "logo": "https://upload.wikimedia.org/wikipedia/commons/0/05/FC_Internazionale_Milano_2021.svg"},
    {"name": "Juventus",      "offense": 85, "defense": 87, "logo": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Juventus_FC_2017_icon_%28black%29.svg"},
    {"name": "Lazio",         "offense": 80, "defense": 77, "logo": "https://upload.wikimedia.org/wikipedia/en/c/ce/S.S._Lazio_badge.svg"},
    {"name": "Lecce",         "offense": 69, "defense": 67, "logo": "https://upload.wikimedia.org/wikipedia/en/3/36/U.S._Lecce_logo.svg"},
    {"name": "Milan",         "offense": 86, "defense": 82, "logo": "https://upload.wikimedia.org/wikipedia/commons/d/d0/Logo_of_AC_Milan.svg"},
    {"name": "Napoli",        "offense": 84, "defense": 81, "logo": "https://upload.wikimedia.org/wikipedia/commons/2/2d/SSC_Napoli_2021.svg"},
    {"name": "Parma",         "offense": 68, "defense": 65, "logo": "https://upload.wikimedia.org/wikipedia/en/d/d2/Parma_Calcio_1913_logo.svg"},
    {"name": "Pisa",          "offense": 65, "defense": 64, "logo": "https://upload.wikimedia.org/wikipedia/en/6/6c/A.C._Pisa_1909_logo.svg"},
    {"name": "Roma",          "offense": 81, "defense": 79, "logo": "https://upload.wikimedia.org/wikipedia/en/f/f7/AS_Roma_logo_%282017%29.svg"},
    {"name": "Sassuolo",      "offense": 73, "defense": 68, "logo": "https://upload.wikimedia.org/wikipedia/en/1/1c/US_Sassuolo_Calcio_logo.svg"},
    {"name": "Torino",        "offense": 73, "defense": 76, "logo": "https://upload.wikimedia.org/wikipedia/en/2/2e/Torino_FC_Logo.svg"},
    {"name": "Udinese",       "offense": 70, "defense": 69, "logo": "https://upload.wikimedia.org/wikipedia/en/c/ce/Udinese_Calcio_logo.svg"},
]

# ---- Motore stato in memoria ----
class VirtualEngine:
    def __init__(self):
        self.phase = "BETTING"   # BETTING, LIVE, FINISHED
        self.timer = 120
        self.current_season_id = None
        self.current_matchday = 1
        self.finished_matchday = 0
        self.clock = "0'"
        self.action_text = "⏳ Piazza le scommesse!"
        # Risultati parziali in memoria durante LIVE
        self.live_scores = {}  # match_id -> {"home": int, "away": int}

engine = VirtualEngine()

# ---- Utility ----
def check_is_psql(conn):
    return hasattr(conn, 'get_dsn_parameters')

def poisson_prob(lmbda, k):
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def get_house_edge(conn):
    """Legge virtual_house_edge dal DB. Default 15%."""
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    try:
        q = "SELECT value FROM settings WHERE key = %s" if psql else "SELECT value FROM settings WHERE key = ?"
        cursor.execute(q, ("virtual_house_edge",))
        row = cursor.fetchone()
        if row:
            return float(row[0] if psql else row["value"])
    except Exception:
        pass
    return 15.0

# ---- Calcolo Quote ----
def compute_odds_for_match(home_offense, home_defense, away_offense, away_defense, margin):
    """
    Calcola tutte le quote per una partita usando la distribuzione di Poisson.
    margin = 1.0 - (house_edge / 100)  → es. 0.85 per 15%
    """
    # Lambda attesi: casa e trasferta
    # Formula: forza attacco casa vs forza difesa ospiti, normalizzati su scala 0-100
    exp_home = max(0.3, (home_offense / 100.0) * (1.0 - away_defense / 150.0) * 2.8 + 0.15)
    exp_away = max(0.2, (away_offense / 100.0) * (1.0 - home_defense / 150.0) * 2.3)

    p1 = px = p2 = 0.0
    p_over = {1.5: 0, 2.5: 0, 3.5: 0, 4.5: 0}
    p_gg = 0.0
    combo = {}   # chiave -> probabilità
    exact = {}   # "hg-ag" -> probabilità

    GOAL_RANGE = 8  # calcola fino a 7 gol per squadra

    for hg in range(GOAL_RANGE):
        for ag in range(GOAL_RANGE):
            prob = poisson_prob(exp_home, hg) * poisson_prob(exp_away, ag)
            if prob < 1e-9:
                continue

            # 1X2
            if hg > ag:
                res = "1"; p1 += prob
            elif hg == ag:
                res = "X"; px += prob
            else:
                res = "2"; p2 += prob

            total = hg + ag

            # Over/Under soglie
            for thr in [1.5, 2.5, 3.5, 4.5]:
                if total > thr:
                    p_over[thr] += prob

            # Goal / No Goal
            is_gg = (hg > 0 and ag > 0)
            if is_gg:
                p_gg += prob

            gg_lbl = "GG" if is_gg else "NG"

            # Combo Over/Under + 1X2
            for thr in [1.5, 2.5, 3.5, 4.5]:
                ou_lbl = f"Over {thr}" if total > thr else f"Under {thr}"
                # Solo Over/Under senza 1X2
                combo[ou_lbl] = combo.get(ou_lbl, 0) + prob
                # Combo con 1X2
                k = f"{res}+{ou_lbl}"
                combo[k] = combo.get(k, 0) + prob

            # Combo GG/NG + 1X2
            combo[f"{res}+{gg_lbl}"] = combo.get(f"{res}+{gg_lbl}", 0) + prob
            combo["GG"] = combo.get("GG", 0) + (prob if is_gg else 0)
            combo["NG"] = combo.get("NG", 0) + (prob if not is_gg else 0)

            # Risultato esatto (limitato a scoreline comuni)
            score_key = f"{hg}-{ag}"
            exact[score_key] = exact.get(score_key, 0) + prob

    # Normalizza 1X2 (sicurezza numerica)
    tot_12 = p1 + px + p2
    if tot_12 > 0:
        p1 /= tot_12; px /= tot_12; p2 /= tot_12

    def to_odd(p):
        if p <= 0:
            return 99.0
        raw = (1.0 / p) * margin
        return round(max(1.02, min(150.0, raw)), 2)

    odds_1  = to_odd(p1)
    odds_x  = to_odd(px)
    odds_2  = to_odd(p2)

    odds_over  = {thr: to_odd(p_over[thr]) for thr in [1.5, 2.5, 3.5, 4.5]}
    odds_under = {thr: to_odd(1.0 - p_over[thr]) for thr in [1.5, 2.5, 3.5, 4.5]}
    odds_gg = to_odd(p_gg)
    odds_ng = to_odd(1.0 - p_gg)

    # Quote combo (incluse Over/Under per ogni soglia)
    odds_combo = {}
    for k, p in combo.items():
        odds_combo[k] = to_odd(p)

    # Quote risultato esatto
    EXACT_SCORES = [
        "0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2",
        "2-2","3-0","0-3","3-1","1-3","3-2","2-3","3-3",
        "4-0","0-4","4-1","1-4","4-2","2-4"
    ]
    odds_exact = {}
    shown_prob = 0.0
    for s in EXACT_SCORES:
        p = exact.get(s, 0.0)
        shown_prob += p
        odds_exact[s] = to_odd(p) if p > 0 else 99.0

    other_prob = max(0.001, 1.0 - shown_prob)
    odds_exact["Altro"] = to_odd(other_prob)

    return {
        "odds_1": odds_1,
        "odds_x": odds_x,
        "odds_2": odds_2,
        "odds_over15": odds_over[1.5],
        "odds_under15": odds_under[1.5],
        "odds_over25": odds_over[2.5],
        "odds_under25": odds_under[2.5],
        "odds_over35": odds_over[3.5],
        "odds_under35": odds_under[3.5],
        "odds_over45": odds_over[4.5],
        "odds_under45": odds_under[4.5],
        "odds_gg": odds_gg,
        "odds_ng": odds_ng,
        "odds_combo": json.dumps(odds_combo),
        "odds_exact": json.dumps(odds_exact),
    }

# ---- Simulazione risultato partita ----
def simulate_match(home_offense, home_defense, away_offense, away_defense):
    """Simula il risultato finale usando Poisson."""
    exp_home = max(0.3, (home_offense / 100.0) * (1.0 - away_defense / 150.0) * 2.8 + 0.15)
    exp_away = max(0.2, (away_offense / 100.0) * (1.0 - home_defense / 150.0) * 2.3)
    hg = min(random.randint(0, 99), _poisson_sample(exp_home))
    ag = min(random.randint(0, 99), _poisson_sample(exp_away))
    return hg, ag

def _poisson_sample(lmbda):
    """Campionamento da distribuzione di Poisson."""
    L = math.exp(-lmbda)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1

# ---- DB helpers ----
def init_teams():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    cursor.execute("SELECT COUNT(*) FROM virtual_teams")
    count = cursor.fetchone()[0]
    if count == 0:
        for t in SERIE_A_TEAMS:
            q = "INSERT INTO virtual_teams (name, offense, defense, logo_url) VALUES (%s, %s, %s, %s)" if psql \
                else "INSERT INTO virtual_teams (name, offense, defense, logo_url) VALUES (?, ?, ?, ?)"
            cursor.execute(q, (t["name"], t["offense"], t["defense"], t["logo"]))
        conn.commit()
    conn.close()

def get_or_create_season():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    cursor.execute("SELECT id, current_matchday FROM virtual_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        # Nuova stagione
        if psql:
            cursor.execute("INSERT INTO virtual_seasons (status, current_matchday) VALUES ('active', 1) RETURNING id")
            sid = cursor.fetchone()[0]
        else:
            cursor.execute("INSERT INTO virtual_seasons (status, current_matchday) VALUES ('active', 1)")
            sid = cursor.lastrowid
        conn.commit()
        generate_fixtures(sid, conn)
        conn.commit()
        engine.current_season_id = sid
        engine.current_matchday = 1
    else:
        engine.current_season_id = row[0] if psql else row["id"]
        engine.current_matchday = row[1] if psql else row["current_matchday"]

    conn.close()

def update_season_matchday(season_id, mday):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET current_matchday = %s WHERE id = %s" if psql \
        else "UPDATE virtual_seasons SET current_matchday = ? WHERE id = ?"
    cursor.execute(q, (mday, season_id))
    conn.commit()
    conn.close()

def mark_season_finished(season_id):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET status = 'finished' WHERE id = %s" if psql \
        else "UPDATE virtual_seasons SET status = 'finished' WHERE id = ?"
    cursor.execute(q, (season_id,))
    conn.commit()
    conn.close()

def generate_fixtures(season_id, conn):
    """
    Genera il calendario completo della stagione (38 giornate, 10 partite ciascuna).
    Algoritmo round-robin: andata (giornate 1-19) + ritorno (giornate 20-38).
    """
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    cursor.execute("SELECT id, name, offense, defense FROM virtual_teams")
    rows = cursor.fetchall()
    teams = {}
    for r in rows:
        if psql:
            teams[r[0]] = {"name": r[1], "o": r[2], "d": r[3]}
        else:
            teams[r["id"]] = {"name": r["name"], "o": r["offense"], "d": r["defense"]}

    tids = list(teams.keys())
    if len(tids) != 20:
        print(f"[WARNING] generate_fixtures: attese 20 squadre, trovate {len(tids)}")
        return

    house_edge = get_house_edge(conn)
    margin = 1.0 - (house_edge / 100.0)

    # Round-robin (algoritmo rotating)
    random.shuffle(tids)
    temp = list(tids)
    first_half_rounds = []
    for _ in range(19):
        pairs = [(temp[i], temp[19 - i]) for i in range(10)]
        first_half_rounds.append(pairs)
        # Ruota: il primo elemento è fisso, gli altri ruotano
        temp = [temp[0]] + [temp[-1]] + temp[1:-1]

    # Andata
    for r_num, pairs in enumerate(first_half_rounds):
        mday = r_num + 1
        for h_id, a_id in pairs:
            ht, at = teams[h_id], teams[a_id]
            o = compute_odds_for_match(ht["o"], ht["d"], at["o"], at["d"], margin)
            _insert_match(cursor, psql, season_id, mday, h_id, a_id, o)

    # Ritorno (stessa sequenza ma squadre invertite)
    for r_num, pairs in enumerate(first_half_rounds):
        mday = r_num + 20
        for h_id, a_id in pairs:
            # Ritorno: casa e trasferta invertiti
            ht, at = teams[a_id], teams[h_id]
            o = compute_odds_for_match(ht["o"], ht["d"], at["o"], at["d"], margin)
            _insert_match(cursor, psql, season_id, mday, a_id, h_id, o)

def _insert_match(cursor, psql, season_id, matchday, home_id, away_id, o):
    if psql:
        cursor.execute("""
            INSERT INTO virtual_matches
              (season_id, matchday, home_team_id, away_team_id, status,
               odds_1, odds_x, odds_2, odds_over25, odds_under25,
               odds_gg, odds_ng, odds_combo, odds_exact)
            VALUES (%s,%s,%s,%s,'scheduled',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (season_id, matchday, home_id, away_id,
              o["odds_1"], o["odds_x"], o["odds_2"],
              o["odds_over25"], o["odds_under25"],
              o["odds_gg"], o["odds_ng"],
              o["odds_combo"], o["odds_exact"]))
    else:
        cursor.execute("""
            INSERT INTO virtual_matches
              (season_id, matchday, home_team_id, away_team_id, status,
               odds_1, odds_x, odds_2, odds_over25, odds_under25,
               odds_gg, odds_ng, odds_combo, odds_exact)
            VALUES (?,?,?,?,'scheduled',?,?,?,?,?,?,?,?,?)
        """, (season_id, matchday, home_id, away_id,
              o["odds_1"], o["odds_x"], o["odds_2"],
              o["odds_over25"], o["odds_under25"],
              o["odds_gg"], o["odds_ng"],
              o["odds_combo"], o["odds_exact"]))

# ---- Finalizzazione giornata ----
def finalize_matchday(season_id, matchday):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    try:
        q = "SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql \
            else "SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?"
        cursor.execute(q, (season_id, matchday))
        matches = cursor.fetchall()

        for m in matches:
            if psql:
                mid, h_id, a_id, hg, ag = m[0], m[1], m[2], m[3], m[4]
            else:
                mid, h_id, a_id, hg, ag = m["id"], m["home_team_id"], m["away_team_id"], m["home_score"], m["away_score"]

            if hg > ag:
                h_pts, a_pts = 3, 0
                h_w, h_d, h_l = 1, 0, 0
                a_w, a_d, a_l = 0, 0, 1
            elif hg == ag:
                h_pts, a_pts = 1, 1
                h_w, h_d, h_l = 0, 1, 0
                a_w, a_d, a_l = 0, 1, 0
            else:
                h_pts, a_pts = 0, 3
                h_w, h_d, h_l = 0, 0, 1
                a_w, a_d, a_l = 1, 0, 0

            _upsert_standing(cursor, psql, season_id, h_id, h_pts, h_w, h_d, h_l, hg, ag)
            _upsert_standing(cursor, psql, season_id, a_id, a_pts, a_w, a_d, a_l, ag, hg)

            upd_q = "UPDATE virtual_matches SET status = 'finished' WHERE id = %s" if psql \
                else "UPDATE virtual_matches SET status = 'finished' WHERE id = ?"
            cursor.execute(upd_q, (mid,))

        conn.commit()
        resolve_virtual_bets(conn, season_id, matchday)
    except Exception:
        print(f"[Finalize Error] {traceback.format_exc()}")
    finally:
        conn.close()

def _upsert_standing(cursor, psql, season_id, team_id, pts, w, d, l, gf, ga):
    if psql:
        cursor.execute("""
            INSERT INTO virtual_standings
              (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
            VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s)
            ON CONFLICT(season_id, team_id) DO UPDATE SET
              points = virtual_standings.points + EXCLUDED.points,
              played = virtual_standings.played + 1,
              won    = virtual_standings.won + EXCLUDED.won,
              drawn  = virtual_standings.drawn + EXCLUDED.drawn,
              lost   = virtual_standings.lost + EXCLUDED.lost,
              goals_for     = virtual_standings.goals_for + EXCLUDED.goals_for,
              goals_against = virtual_standings.goals_against + EXCLUDED.goals_against
        """, (season_id, team_id, pts, w, d, l, gf, ga))
    else:
        cursor.execute("""
            INSERT INTO virtual_standings
              (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
            VALUES (?,?,?,1,?,?,?,?,?)
            ON CONFLICT(season_id, team_id) DO UPDATE SET
              points = points + excluded.points,
              played = played + 1,
              won    = won + excluded.won,
              drawn  = drawn + excluded.drawn,
              lost   = lost + excluded.lost,
              goals_for     = goals_for + excluded.goals_for,
              goals_against = goals_against + excluded.goals_against
        """, (season_id, team_id, pts, w, d, l, gf, ga))

# ---- Risoluzione scommesse virtuali ----
def resolve_virtual_bets(conn, season_id, matchday):
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    adm_row = cursor.fetchone()
    admin_id = adm_row[0] if adm_row else 1

    # Recupera risultati della giornata
    q = "SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql \
        else "SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?"
    cursor.execute(q, (season_id, matchday))

    results = {}  # event_id ("v_{match_id}") -> set di selezioni vincenti
    for r in cursor.fetchall():
        if psql:
            mid, hg, ag = r[0], r[1], r[2]
        else:
            mid, hg, ag = r["id"], r["home_score"], r["away_score"]

        event_id = f"v_{mid}"
        winning = set()

        # 1X2
        r1x2 = "1" if hg > ag else ("X" if hg == ag else "2")
        winning.add(r1x2)

        total = hg + ag

        # Over/Under per tutte le soglie
        for thr in [1.5, 2.5, 3.5, 4.5]:
            if total > thr:
                winning.add(f"Over {thr}")
            else:
                winning.add(f"Under {thr}")

        # GG/NG
        is_gg = hg > 0 and ag > 0
        winning.add("Goal" if is_gg else "No Goal")
        winning.add("GG" if is_gg else "NG")

        gg_lbl = "GG" if is_gg else "NG"
        ou_lbl = {thr: (f"Over {thr}" if total > thr else f"Under {thr}") for thr in [1.5, 2.5, 3.5, 4.5]}

        # Combo 1X2 + Over/Under
        for thr in [1.5, 2.5, 3.5, 4.5]:
            winning.add(f"{r1x2}+{ou_lbl[thr]}")

        # Combo 1X2 + GG/NG
        winning.add(f"{r1x2}+{gg_lbl}")

        # Risultato esatto
        score_str = f"{hg}-{ag}"
        winning.add(f"Esatto {score_str}")
        winning.add(score_str)

        KNOWN_SCORES = [
            "0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2","2-2",
            "3-0","0-3","3-1","1-3","3-2","2-3","3-3","4-0","0-4",
            "4-1","1-4","4-2","2-4"
        ]
        if score_str not in KNOWN_SCORES:
            winning.add("Esatto Altro")
            winning.add("Altro")

        results[event_id] = winning

    # Recupera tutte le selezioni pending su eventi virtuali di questa giornata
    event_ids = list(results.keys())
    if not event_ids:
        return

    cursor.execute("""
        SELECT bs.id, bs.bet_id, bs.event_id, bs.selection
        FROM bet_selections bs
        JOIN bets b ON bs.bet_id = b.id
        WHERE b.status = 'pending'
    """)
    all_sels = cursor.fetchall()

    affected_bets = set()
    for bs in all_sels:
        if psql:
            bs_id, bid, evid, sel = bs[0], bs[1], bs[2], bs[3]
        else:
            bs_id, bid, evid, sel = bs["id"], bs["bet_id"], bs["event_id"], bs["selection"]

        if evid not in results:
            continue

        is_winner = sel in results[evid]
        st = "won" if is_winner else "lost"
        upd_q = "UPDATE bet_selections SET status = %s WHERE id = %s" if psql \
            else "UPDATE bet_selections SET status = ? WHERE id = ?"
        cursor.execute(upd_q, (st, bs_id))
        affected_bets.add(bid)

    conn.commit()

    # Valuta le bet complete
    for bid in affected_bets:
        b_q = "SELECT user_id, potential_win, status FROM bets WHERE id = %s" if psql \
            else "SELECT user_id, potential_win, status FROM bets WHERE id = ?"
        cursor.execute(b_q, (bid,))
        b_row = cursor.fetchone()
        if not b_row:
            continue

        if psql:
            uid, win, b_status = b_row[0], b_row[1], b_row[2]
        else:
            uid, win, b_status = b_row["user_id"], b_row["potential_win"], b_row["status"]

        if b_status != "pending":
            continue

        s_q = "SELECT status FROM bet_selections WHERE bet_id = %s" if psql \
            else "SELECT status FROM bet_selections WHERE bet_id = ?"
        cursor.execute(s_q, (bid,))
        sel_statuses = [r[0] if psql else r["status"] for r in cursor.fetchall()]

        if "lost" in sel_statuses:
            cursor.execute(
                "UPDATE bets SET status = 'lost' WHERE id = %s" if psql else "UPDATE bets SET status = 'lost' WHERE id = ?",
                (bid,)
            )
        elif all(s == "won" for s in sel_statuses) and sel_statuses:
            # Paga la vincita
            bal_q = "SELECT balance FROM users WHERE id = %s" if psql else "SELECT balance FROM users WHERE id = ?"
            cursor.execute(bal_q, (uid,))
            u_row = cursor.fetchone()
            if not u_row:
                continue
            prev = float(u_row[0])
            nxt = prev + win
            cursor.execute(
                "UPDATE users SET balance = %s WHERE id = %s" if psql else "UPDATE users SET balance = ? WHERE id = ?",
                (nxt, uid)
            )
            cursor.execute(
                "UPDATE bets SET status = 'won' WHERE id = %s" if psql else "UPDATE bets SET status = 'won' WHERE id = ?",
                (bid,)
            )
            t_q = """INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason)
                     VALUES (%s,'credit',%s,%s,%s,%s,%s)""" if psql else \
                  """INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason)
                     VALUES (?,'credit',?,?,?,?,?)"""
            cursor.execute(t_q, (uid, win, prev, nxt, admin_id, f"Vincita Virtuale bet#{bid}"))
            print(f"[VirtualPayout] Paid €{win:.2f} to user {uid} for bet {bid}")
        # Se ci sono ancora selezioni pending (altri eventi non ancora risolti), non fare niente

    conn.commit()

# ---- Loop principale ----
async def run_virtual_football_loop():
    init_teams()
    get_or_create_season()

    while True:
        try:
            await _run_one_matchday()
        except Exception:
            print(f"[VirtualLoop Error] {traceback.format_exc()}")
            await asyncio.sleep(10)

async def _run_one_matchday():
    sid = engine.current_season_id
    mday = engine.current_matchday

    # ---- FASE BETTING ----
    engine.phase = "BETTING"
    engine.action_text = "⏳ Piazza le scommesse!"
    engine.timer = 120

    while engine.timer > 0:
        await asyncio.sleep(1)
        engine.timer -= 1

    # ---- CARICA PARTITE E TEAM STATS ----
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    cursor.execute(
        "SELECT m.id, m.home_team_id, m.away_team_id, ht.offense, ht.defense, at.offense, at.defense "
        "FROM virtual_matches m "
        "JOIN virtual_teams ht ON m.home_team_id = ht.id "
        "JOIN virtual_teams at ON m.away_team_id = at.id "
        "WHERE m.season_id = %s AND m.matchday = %s" if psql else
        "SELECT m.id, m.home_team_id, m.away_team_id, ht.offense, ht.defense, at.offense, at.defense "
        "FROM virtual_matches m "
        "JOIN virtual_teams ht ON m.home_team_id = ht.id "
        "JOIN virtual_teams at ON m.away_team_id = at.id "
        "WHERE m.season_id = ? AND m.matchday = ?",
        (sid, mday)
    )
    matches = cursor.fetchall()

    # Pre-calcola i risultati finali (simulazione)
    match_data = []
    for m in matches:
        if psql:
            mid, h_id, a_id, h_off, h_def, a_off, a_def = m[0], m[1], m[2], m[3], m[4], m[5], m[6]
        else:
            mid, h_id, a_id = m["id"], m["home_team_id"], m["away_team_id"]
            h_off, h_def, a_off, a_def = m["offense"], m["defense"], m[5], m[6]
        final_h, final_a = simulate_match(h_off, h_def, a_off, a_def)
        match_data.append({"id": mid, "final_h": final_h, "final_a": final_a})

    # Inizializza punteggi a 0
    if psql:
        cursor.execute(
            "UPDATE virtual_matches SET status='live', home_score=0, away_score=0, current_minute=0 "
            "WHERE season_id=%s AND matchday=%s", (sid, mday)
        )
    else:
        cursor.execute(
            "UPDATE virtual_matches SET status='live', home_score=0, away_score=0, current_minute=0 "
            "WHERE season_id=? AND matchday=?", (sid, mday)
        )
    conn.commit()
    conn.close()

    # Inizializza live_scores in memoria
    engine.live_scores = {m["id"]: {"home": 0, "away": 0} for m in match_data}

    # ---- FASE LIVE ----
    engine.phase = "LIVE"
    engine.clock = "0'"
    engine.action_text = "🏟️ Fischio d'inizio!"
    engine.timer = 90  # secondi simulati (ogni secondo = ~1 minuto di partita)

    MINUTES = [15, 30, 45, 60, 75, 90]
    SIM_SECONDS = 30  # durata totale simulazione in secondi reali
    minute_map = {
        round(SIM_SECONDS * (m / 90)): m for m in MINUTES
    }

    for sec in range(SIM_SECONDS, 0, -1):
        await asyncio.sleep(1)
        engine.timer = sec

        real_minute = MINUTES[max(0, len(MINUTES) - round(sec * len(MINUTES) / SIM_SECONDS) - 1)]
        engine.clock = f"{real_minute}'"

        # Distribuisci gol in modo progressivo
        # Ad ogni step simula se ci sono stati gol fino a questo momento
        progress = 1.0 - (sec / SIM_SECONDS)  # da 0 a 1 nel tempo
        next_progress = 1.0 - ((sec - 1) / SIM_SECONDS)

        conn = get_db()
        cursor = conn.cursor()
        psql = check_is_psql(conn)
        changed = False

        for m in match_data:
            mid = m["id"]
            current = engine.live_scores[mid]

            # Quanti gol il team ha segnato fino a "next_progress" del tempo
            total_h = m["final_h"]
            total_a = m["final_a"]

            # Distribuisce i gol uniformemente nel tempo
            expected_h_now = round(total_h * next_progress)
            expected_a_now = round(total_a * next_progress)

            new_h = max(current["home"], expected_h_now)
            new_a = max(current["away"], expected_a_now)

            if new_h != current["home"] or new_a != current["away"]:
                engine.live_scores[mid] = {"home": new_h, "away": new_a}
                upd_q = "UPDATE virtual_matches SET home_score=%s, away_score=%s, current_minute=%s WHERE id=%s" if psql \
                    else "UPDATE virtual_matches SET home_score=?, away_score=?, current_minute=? WHERE id=?"
                cursor.execute(upd_q, (new_h, new_a, real_minute, mid))
                changed = True

        if changed:
            conn.commit()

        # Aggiorna testo azione
        scorers = [f"{m['final_h']}-{m['final_a']}" for m in match_data if
                   round(m['final_h'] * next_progress) > round(m['final_h'] * progress) or
                   round(m['final_a'] * next_progress) > round(m['final_a'] * progress)]
        if scorers:
            engine.action_text = f"⚽ Gol! ({real_minute}')"
        else:
            engine.action_text = f"🏟️ In corso... {real_minute}'"

        conn.close()

    # ---- Scrivi punteggi finali ----
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    for m in match_data:
        upd_q = "UPDATE virtual_matches SET home_score=%s, away_score=%s, current_minute=90 WHERE id=%s" if psql \
            else "UPDATE virtual_matches SET home_score=?, away_score=?, current_minute=90 WHERE id=?"
        cursor.execute(upd_q, (m["final_h"], m["final_a"], m["id"]))
        engine.live_scores[m["id"]] = {"home": m["final_h"], "away": m["final_a"]}
    conn.commit()
    conn.close()

    engine.clock = "FIN"
    engine.action_text = f"🏁 Fischio Finale!"

    # ---- FINALIZZA E CLASSIFICA ----
    finalize_matchday(sid, mday)
    engine.finished_matchday = mday

    # ---- Avanza giornata ----
    if mday >= 38:
        mark_season_finished(sid)
        get_or_create_season()
    else:
        engine.current_matchday = mday + 1
        update_season_matchday(sid, mday + 1)

    # ---- FASE FINISHED (mostra risultati) ----
    engine.phase = "FINISHED"
    engine.timer = 30
    engine.action_text = f"🏆 Risultati Giornata {mday}"

    while engine.timer > 0:
        await asyncio.sleep(1)
        engine.timer -= 1

# ---- API Endpoints ----

@router.get("/status")
async def get_virtual_status():
    return {
        "phase": engine.phase,
        "timer": engine.timer,
        "matchday": engine.current_matchday,
        "finished_matchday": engine.finished_matchday,
        "clock": engine.clock,
        "action_text": engine.action_text,
    }

@router.get("/matches")
async def get_virtual_matches():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    q = (
        "SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, "
        "m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, "
        "m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, "
        "th.name AS home_name, th.logo_url AS home_logo, "
        "ta.name AS away_name, ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = %s AND m.matchday = %s"
        if psql else
        "SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, "
        "m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, "
        "m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, "
        "th.name AS home_name, th.logo_url AS home_logo, "
        "ta.name AS away_name, ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = ? AND m.matchday = ?"
    )
    cursor.execute(q, (engine.current_season_id, engine.current_matchday))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for m in rows:
        if psql:
            combo_raw = m[12] or "{}"
            exact_raw = m[13] or "{}"
            entry = {
                "id": m[0], "matchday": m[1], "status": m[2],
                "home_score": m[3], "away_score": m[4],
                "odds_1": m[5], "odds_x": m[6], "odds_2": m[7],
                "odds_over25": m[8], "odds_under25": m[9],
                "odds_gg": m[10], "odds_ng": m[11],
                "odds_combo": json.loads(combo_raw),
                "odds_exact": json.loads(exact_raw),
                "home_team": {"name": m[14], "logo": m[15]},
                "away_team": {"name": m[16], "logo": m[17]},
            }
        else:
            combo_raw = m["odds_combo"] or "{}"
            exact_raw = m["odds_exact"] or "{}"
            entry = {
                "id": m["id"], "matchday": m["matchday"], "status": m["status"],
                "home_score": m["home_score"], "away_score": m["away_score"],
                "odds_1": m["odds_1"], "odds_x": m["odds_x"], "odds_2": m["odds_2"],
                "odds_over25": m["odds_over25"], "odds_under25": m["odds_under25"],
                "odds_gg": m["odds_gg"], "odds_ng": m["odds_ng"],
                "odds_combo": json.loads(combo_raw),
                "odds_exact": json.loads(exact_raw),
                "home_team": {"name": m["home_name"], "logo": m["home_logo"]},
                "away_team": {"name": m["away_name"], "logo": m["away_logo"]},
            }
        result.append(entry)
    return result

@router.get("/live")
async def get_virtual_live():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    day = engine.finished_matchday if engine.phase == "FINISHED" else engine.current_matchday

    q = (
        "SELECT m.id, m.home_score, m.away_score, m.current_minute, "
        "th.name AS home_name, ta.name AS away_name "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = %s AND m.matchday = %s"
        if psql else
        "SELECT m.id, m.home_score, m.away_score, m.current_minute, "
        "th.name AS home_name, ta.name AS away_name "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = ? AND m.matchday = ?"
    )
    cursor.execute(q, (engine.current_season_id, day))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        if psql:
            mid = r[0]
            # Durante LIVE usa i punteggi in memoria per massima freschezza
            if engine.phase == "LIVE" and mid in engine.live_scores:
                hs = engine.live_scores[mid]["home"]
                as_ = engine.live_scores[mid]["away"]
            else:
                hs, as_ = r[1], r[2]
            result.append({
                "id": mid, "home_score": hs, "away_score": as_,
                "minute": r[3],
                "home_team": {"name": r[4]},
                "away_team": {"name": r[5]},
            })
        else:
            mid = r["id"]
            if engine.phase == "LIVE" and mid in engine.live_scores:
                hs = engine.live_scores[mid]["home"]
                as_ = engine.live_scores[mid]["away"]
            else:
                hs, as_ = r["home_score"], r["away_score"]
            result.append({
                "id": mid, "home_score": hs, "away_score": as_,
                "minute": r["current_minute"],
                "home_team": {"name": r["home_name"]},
                "away_team": {"name": r["away_name"]},
            })
    return result

@router.get("/standings")
async def get_virtual_standings():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    q = (
        "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, "
        "s.goals_for, s.goals_against "
        "FROM virtual_standings s "
        "JOIN virtual_teams t ON s.team_id = t.id "
        "WHERE s.season_id = %s "
        "ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC, s.goals_for DESC"
        if psql else
        "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, "
        "s.goals_for, s.goals_against "
        "FROM virtual_standings s "
        "JOIN virtual_teams t ON s.team_id = t.id "
        "WHERE s.season_id = ? "
        "ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC, s.goals_for DESC"
    )
    cursor.execute(q, (engine.current_season_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        if psql:
            gd = r[7] - r[8]
            result.append({
                "team_name": r[0], "logo": r[1],
                "points": r[2], "played": r[3],
                "won": r[4], "drawn": r[5], "lost": r[6],
                "gf": r[7], "ga": r[8], "gd": gd,
            })
        else:
            gd = r["goals_for"] - r["goals_against"]
            result.append({
                "team_name": r["name"], "logo": r["logo_url"],
                "points": r["points"], "played": r["played"],
                "won": r["won"], "drawn": r["drawn"], "lost": r["lost"],
                "gf": r["goals_for"], "ga": r["goals_against"], "gd": gd,
            })
    return result

@router.get("/history/{matchday}")
async def get_matchday_results(matchday: int):
    """Restituisce i risultati di una giornata già giocata."""
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    if matchday < 1 or matchday > 38:
        raise HTTPException(status_code=400, detail="Giornata non valida")

    q = (
        "SELECT m.id, m.home_score, m.away_score, m.status, "
        "th.name AS home_name, th.logo_url AS home_logo, "
        "ta.name AS away_name, ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = %s AND m.matchday = %s "
        "ORDER BY m.id"
        if psql else
        "SELECT m.id, m.home_score, m.away_score, m.status, "
        "th.name AS home_name, th.logo_url AS home_logo, "
        "ta.name AS away_name, ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id = th.id "
        "JOIN virtual_teams ta ON m.away_team_id = ta.id "
        "WHERE m.season_id = ? AND m.matchday = ? "
        "ORDER BY m.id"
    )
    cursor.execute(q, (engine.current_season_id, matchday))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0] if psql else r["id"],
            "home_score": r[1] if psql else r["home_score"],
            "away_score": r[2] if psql else r["away_score"],
            "status": r[3] if psql else r["status"],
            "home_team": {"name": r[4] if psql else r["home_name"], "logo": r[5] if psql else r["home_logo"]},
            "away_team": {"name": r[6] if psql else r["away_name"], "logo": r[7] if psql else r["away_logo"]},
        }
        for r in rows
    ]
