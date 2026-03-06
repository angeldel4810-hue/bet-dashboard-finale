import asyncio
import random
import math
import json
import traceback
from fastapi import APIRouter, HTTPException
from backend.database import get_db

router = APIRouter()

# ---------------------------------------------------------------------------
# Squadre
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Stato motore in memoria
# ---------------------------------------------------------------------------
class VirtualEngine:
    def __init__(self):
        # Flusso: LIVE (30s) → FINISHED (120s) → BETTING (120s) → LIVE ...
        self.phase = "BETTING"
        self.timer = 120           # secondi rimanenti nella fase corrente
        self.current_season_id = None
        self.current_matchday = 1  # giornata su cui si scommette ADESSO
        self.finished_matchday = 0 # ultima giornata già completata
        self.clock = ""
        self.action_text = "⏳ Piazza le scommesse!"
        self.live_scores: dict = {}  # mid -> {"home": int, "away": int}

engine = VirtualEngine()

# ---------------------------------------------------------------------------
# Helpers DB
# ---------------------------------------------------------------------------
def _pg(conn):
    return hasattr(conn, 'get_dsn_parameters')

def _q(psql_q, sqlite_q, is_pg):
    return psql_q if is_pg else sqlite_q

def get_house_edge(conn) -> float:
    c = conn.cursor(); pg = _pg(conn)
    c.execute(_q("SELECT value FROM settings WHERE key=%s",
                 "SELECT value FROM settings WHERE key=?", pg), ("virtual_house_edge",))
    row = c.fetchone()
    if row:
        return float(row[0] if pg else row["value"])
    return 15.0

# ---------------------------------------------------------------------------
# Calcolo quote Poisson
# ---------------------------------------------------------------------------
def _poisson(lam, k):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def _poisson_sample(lam: float) -> int:
    L = math.exp(-max(0.01, lam))
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1

def compute_odds(h_off, h_def, a_off, a_def, margin):
    lam_h = max(0.25, (h_off / 100) * (1 - a_def / 150) * 2.8 + 0.1)
    lam_a = max(0.15, (a_off / 100) * (1 - h_def / 150) * 2.3)

    p1 = px = p2 = p_gg = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0, 4.5: 0.0}
    combo: dict = {}
    exact: dict = {}

    for hg in range(9):
        for ag in range(9):
            prob = _poisson(lam_h, hg) * _poisson(lam_a, ag)
            if prob < 1e-10:
                continue
            res = "1" if hg > ag else ("X" if hg == ag else "2")
            if hg > ag:    p1 += prob
            elif hg == ag: px += prob
            else:          p2 += prob

            total = hg + ag
            is_gg = hg > 0 and ag > 0
            if is_gg: p_gg += prob
            gg_lbl = "GG" if is_gg else "NG"

            for thr in [1.5, 2.5, 3.5, 4.5]:
                if total > thr: p_over[thr] += prob
                ou = f"Over {thr}" if total > thr else f"Under {thr}"
                combo[ou]               = combo.get(ou, 0)              + prob
                combo[f"{res}+{ou}"]    = combo.get(f"{res}+{ou}", 0)   + prob

            combo[f"{res}+{gg_lbl}"] = combo.get(f"{res}+{gg_lbl}", 0) + prob
            combo["GG"] = combo.get("GG", 0) + (prob if is_gg else 0)
            combo["NG"] = combo.get("NG", 0) + (prob if not is_gg else 0)
            exact[f"{hg}-{ag}"] = exact.get(f"{hg}-{ag}", 0) + prob

    tot = p1 + px + p2
    if tot > 0:
        p1 /= tot; px /= tot; p2 /= tot

    def odd(p):
        return round(max(1.02, min(150.0, (1.0 / max(p, 1e-6)) * margin)), 2)

    EXACT_SCORES = [
        "0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2",
        "2-2","3-0","0-3","3-1","1-3","3-2","2-3","3-3",
        "4-0","0-4","4-1","1-4"
    ]
    odds_exact = {s: odd(exact.get(s, 0)) for s in EXACT_SCORES}
    other_p = max(0.001, 1.0 - sum(exact.get(s, 0) for s in EXACT_SCORES))
    odds_exact["Altro"] = odd(other_p)

    return {
        "odds_1":       odd(p1),
        "odds_x":       odd(px),
        "odds_2":       odd(p2),
        "odds_over25":  odd(p_over[2.5]),
        "odds_under25": odd(1 - p_over[2.5]),
        "odds_gg":      odd(p_gg),
        "odds_ng":      odd(1 - p_gg),
        "odds_combo":   json.dumps({k: odd(v) for k, v in combo.items()}),
        "odds_exact":   json.dumps(odds_exact),
    }

def simulate_score(h_off, h_def, a_off, a_def):
    lam_h = max(0.25, (h_off / 100) * (1 - a_def / 150) * 2.8 + 0.1)
    lam_a = max(0.15, (a_off / 100) * (1 - h_def / 150) * 2.3)
    return _poisson_sample(lam_h), _poisson_sample(lam_a)

# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------
def init_teams():
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    for t in SERIE_A_TEAMS:
        c.execute(_q("SELECT id FROM virtual_teams WHERE name=%s",
                     "SELECT id FROM virtual_teams WHERE name=?", pg), (t["name"],))
        row = c.fetchone()
        if row:
            tid = row[0]
            c.execute(_q("UPDATE virtual_teams SET offense=%s,defense=%s,logo_url=%s WHERE id=%s",
                         "UPDATE virtual_teams SET offense=?,defense=?,logo_url=? WHERE id=?", pg),
                      (t["offense"], t["defense"], t["logo"], tid))
        else:
            c.execute(_q("INSERT INTO virtual_teams(name,offense,defense,logo_url) VALUES(%s,%s,%s,%s)",
                         "INSERT INTO virtual_teams(name,offense,defense,logo_url) VALUES(?,?,?,?)", pg),
                      (t["name"], t["offense"], t["defense"], t["logo"]))
    conn.commit(); conn.close()

def get_or_create_season():
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    c.execute("SELECT id,current_matchday FROM virtual_seasons WHERE status='active' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if not row:
        if pg:
            c.execute("INSERT INTO virtual_seasons(status,current_matchday) VALUES('active',1) RETURNING id")
            sid = c.fetchone()[0]
        else:
            c.execute("INSERT INTO virtual_seasons(status,current_matchday) VALUES('active',1)")
            sid = c.lastrowid
        conn.commit()
        generate_fixtures(sid, conn)
        conn.commit()
        engine.current_season_id = sid
        engine.current_matchday  = 1
    else:
        engine.current_season_id = row[0] if pg else row["id"]
        engine.current_matchday  = row[1] if pg else row["current_matchday"]
    conn.close()

def generate_fixtures(season_id, conn):
    c = conn.cursor(); pg = _pg(conn)
    c.execute("SELECT id,offense,defense FROM virtual_teams")
    rows = c.fetchall()
    teams = {(r[0] if pg else r["id"]): (r[1] if pg else r["offense"], r[2] if pg else r["defense"])
             for r in rows}
    tids = list(teams.keys())
    if len(tids) != 20:
        print(f"[Fixtures] Errore: {len(tids)} squadre (attese 20)")
        return

    margin = 1.0 - get_house_edge(conn) / 100.0
    random.shuffle(tids)
    temp = list(tids)
    first_rounds = []
    for _ in range(19):
        first_rounds.append([(temp[i], temp[19 - i]) for i in range(10)])
        temp = [temp[0]] + [temp[-1]] + temp[1:-1]

    def ins(mday, h, a):
        ho, hd = teams[h]; ao, ad = teams[a]
        o = compute_odds(ho, hd, ao, ad, margin)
        c.execute(_q(
            "INSERT INTO virtual_matches(season_id,matchday,home_team_id,away_team_id,status,"
            "odds_1,odds_x,odds_2,odds_over25,odds_under25,odds_gg,odds_ng,odds_combo,odds_exact)"
            " VALUES(%s,%s,%s,%s,'scheduled',%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            "INSERT INTO virtual_matches(season_id,matchday,home_team_id,away_team_id,status,"
            "odds_1,odds_x,odds_2,odds_over25,odds_under25,odds_gg,odds_ng,odds_combo,odds_exact)"
            " VALUES(?,?,?,?,'scheduled',?,?,?,?,?,?,?,?,?)", pg),
            (season_id, mday, h, a,
             o["odds_1"], o["odds_x"], o["odds_2"],
             o["odds_over25"], o["odds_under25"],
             o["odds_gg"], o["odds_ng"],
             o["odds_combo"], o["odds_exact"]))

    for i, pairs in enumerate(first_rounds):
        for h, a in pairs:
            ins(i + 1,  h, a)
            ins(i + 20, a, h)

# ---------------------------------------------------------------------------
# Finalizzazione: classifica + pagamento scommesse
# ---------------------------------------------------------------------------
def finalize_matchday(season_id, matchday):
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    try:
        c.execute(_q(
            "SELECT id,home_team_id,away_team_id,home_score,away_score FROM virtual_matches WHERE season_id=%s AND matchday=%s",
            "SELECT id,home_team_id,away_team_id,home_score,away_score FROM virtual_matches WHERE season_id=? AND matchday=?", pg),
            (season_id, matchday))
        matches = c.fetchall()

        for m in matches:
            mid, hid, aid = (m[0],m[1],m[2]) if pg else (m["id"],m["home_team_id"],m["away_team_id"])
            hg,  ag       = (m[3],m[4])       if pg else (m["home_score"],m["away_score"])

            if   hg > ag: hp,ap=3,0; hw,hd_,hl=1,0,0; aw,ad_,al=0,0,1
            elif hg==ag:  hp,ap=1,1; hw,hd_,hl=0,1,0; aw,ad_,al=0,1,0
            else:         hp,ap=0,3; hw,hd_,hl=0,0,1; aw,ad_,al=1,0,0

            for tid,pts,w,d,l,gf,ga in [(hid,hp,hw,hd_,hl,hg,ag),(aid,ap,aw,ad_,al,ag,hg)]:
                if pg:
                    c.execute("""
                        INSERT INTO virtual_standings(season_id,team_id,points,played,won,drawn,lost,goals_for,goals_against)
                        VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s)
                        ON CONFLICT(season_id,team_id) DO UPDATE SET
                          points=virtual_standings.points+EXCLUDED.points, played=virtual_standings.played+1,
                          won=virtual_standings.won+EXCLUDED.won, drawn=virtual_standings.drawn+EXCLUDED.drawn,
                          lost=virtual_standings.lost+EXCLUDED.lost,
                          goals_for=virtual_standings.goals_for+EXCLUDED.goals_for,
                          goals_against=virtual_standings.goals_against+EXCLUDED.goals_against
                    """, (season_id,tid,pts,w,d,l,gf,ga))
                else:
                    c.execute("""
                        INSERT INTO virtual_standings(season_id,team_id,points,played,won,drawn,lost,goals_for,goals_against)
                        VALUES(?,?,?,1,?,?,?,?,?)
                        ON CONFLICT(season_id,team_id) DO UPDATE SET
                          points=points+excluded.points, played=played+1,
                          won=won+excluded.won, drawn=drawn+excluded.drawn,
                          lost=lost+excluded.lost,
                          goals_for=goals_for+excluded.goals_for,
                          goals_against=goals_against+excluded.goals_against
                    """, (season_id,tid,pts,w,d,l,gf,ga))

            c.execute(_q("UPDATE virtual_matches SET status='finished' WHERE id=%s",
                         "UPDATE virtual_matches SET status='finished' WHERE id=?", pg), (mid,))

        conn.commit()
        _resolve_bets(conn, season_id, matchday)

    except Exception:
        print(f"[Finalize Error]\n{traceback.format_exc()}")
    finally:
        conn.close()

def _resolve_bets(conn, season_id, matchday):
    c = conn.cursor(); pg = _pg(conn)

    c.execute(_q(
        "SELECT id,home_score,away_score FROM virtual_matches WHERE season_id=%s AND matchday=%s",
        "SELECT id,home_score,away_score FROM virtual_matches WHERE season_id=? AND matchday=?", pg),
        (season_id, matchday))

    # Costruisce selezioni vincenti per ogni evento della giornata
    winning: dict = {}
    for r in c.fetchall():
        mid = r[0] if pg else r["id"]
        hg  = r[1] if pg else r["home_score"]
        ag  = r[2] if pg else r["away_score"]
        evid = f"v_{mid}"
        w = set()
        res = "1" if hg > ag else ("X" if hg == ag else "2")
        w.add(res)
        total = hg + ag
        is_gg = hg > 0 and ag > 0
        w.add("Goal" if is_gg else "No Goal")
        w.add("GG"   if is_gg else "NG")
        gg_lbl = "GG" if is_gg else "NG"
        w.add(f"{res}+{gg_lbl}")
        for thr in [1.5, 2.5, 3.5, 4.5]:
            ou = f"Over {thr}" if total > thr else f"Under {thr}"
            w.add(ou); w.add(f"{res}+{ou}")
        sc = f"{hg}-{ag}"
        w.add(sc); w.add(f"Esatto {sc}")
        KNOWN = {"0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2","2-2",
                 "3-0","0-3","3-1","1-3","3-2","2-3","3-3","4-0","0-4","4-1","1-4"}
        if sc not in KNOWN:
            w.add("Altro"); w.add("Esatto Altro")
        winning[evid] = w

    if not winning:
        return

    c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    adm = c.fetchone()
    admin_id = (adm[0] if pg else adm["id"]) if adm else 1

    # Trova bet pending che coinvolgono questa giornata
    c.execute("SELECT DISTINCT b.id,b.user_id,b.potential_win "
              "FROM bets b JOIN bet_selections bs ON b.id=bs.bet_id "
              "WHERE b.status='pending'")
    pending = c.fetchall()

    for b in pending:
        bid,uid,pot = (b[0],b[1],b[2]) if pg else (b["id"],b["user_id"],b["potential_win"])

        c.execute(_q("SELECT id,event_id,selection,status FROM bet_selections WHERE bet_id=%s",
                     "SELECT id,event_id,selection,status FROM bet_selections WHERE bet_id=?", pg), (bid,))
        sels = c.fetchall()

        # Aggiorna selezioni che appartengono a questa giornata
        touched = False
        for s in sels:
            sid_,evid,sel,ssel_st = (s[0],s[1],s[2],s[3]) if pg else \
                                    (s["id"],s["event_id"],s["selection"],s["status"])
            if evid in winning and ssel_st == "pending":
                new_st = "won" if sel in winning[evid] else "lost"
                c.execute(_q("UPDATE bet_selections SET status=%s WHERE id=%s",
                             "UPDATE bet_selections SET status=? WHERE id=?", pg), (new_st, sid_))
                touched = True

        if not touched:
            continue
        conn.commit()

        # Rileggi stati
        c.execute(_q("SELECT status FROM bet_selections WHERE bet_id=%s",
                     "SELECT status FROM bet_selections WHERE bet_id=?", pg), (bid,))
        statuses = [r[0] if pg else r["status"] for r in c.fetchall()]

        if "lost" in statuses:
            c.execute(_q("UPDATE bets SET status='lost' WHERE id=%s",
                         "UPDATE bets SET status='lost' WHERE id=?", pg), (bid,))
        elif "pending" not in statuses and all(s == "won" for s in statuses):
            c.execute(_q("SELECT balance FROM users WHERE id=%s",
                         "SELECT balance FROM users WHERE id=?", pg), (uid,))
            prev = float(c.fetchone()[0])
            nxt  = prev + pot
            c.execute(_q("UPDATE users SET balance=%s WHERE id=%s",
                         "UPDATE users SET balance=? WHERE id=?", pg), (nxt, uid))
            c.execute(_q("UPDATE bets SET status='won' WHERE id=%s",
                         "UPDATE bets SET status='won' WHERE id=?", pg), (bid,))
            c.execute(_q(
                "INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,admin_id,reason)"
                " VALUES(%s,'credit',%s,%s,%s,%s,%s)",
                "INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,admin_id,reason)"
                " VALUES(?,'credit',?,?,?,?,?)", pg),
                (uid, pot, prev, nxt, admin_id, f"Vincita Virtuale bet#{bid}"))
            print(f"[VirtualPay] bet#{bid} → user#{uid} +€{pot:.2f}")

    conn.commit()

# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------
async def run_virtual_football_loop():
    print("[Virtual] Avvio loop...")
    try:
        init_teams()
        get_or_create_season()
    except Exception:
        print(f"[Virtual CRITICAL]\n{traceback.format_exc()}")
        return

    while True:
        try:
            await _run_one_cycle()
        except Exception:
            print(f"[Virtual Loop Error]\n{traceback.format_exc()}")
            await asyncio.sleep(5)

async def _run_one_cycle():
    sid  = engine.current_season_id
    mday = engine.current_matchday

    # ------------------------------------------------------------------ LIVE
    # Carica dati squadre e pre-calcola risultati finali
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    c.execute(_q(
        "SELECT m.id,ht.offense,ht.defense,at.offense,at.defense "
        "FROM virtual_matches m "
        "JOIN virtual_teams ht ON m.home_team_id=ht.id "
        "JOIN virtual_teams at ON m.away_team_id=at.id "
        "WHERE m.season_id=%s AND m.matchday=%s",
        "SELECT m.id,ht.offense,ht.defense,at.offense,at.defense "
        "FROM virtual_matches m "
        "JOIN virtual_teams ht ON m.home_team_id=ht.id "
        "JOIN virtual_teams at ON m.away_team_id=at.id "
        "WHERE m.season_id=? AND m.matchday=?", pg), (sid, mday))
    rows = c.fetchall()
    finals = {}
    for r in rows:
        mid = r[0] if pg else r["id"]
        ho,hd = (r[1],r[2]) if pg else (r["offense"],r["defense"])
        ao,ad = (r[3],r[4]) if pg else (r[3],r[4])
        finals[mid] = simulate_score(ho, hd, ao, ad)

    # Reset punteggi
    c.execute(_q(
        "UPDATE virtual_matches SET status='live',home_score=0,away_score=0,current_minute=0 WHERE season_id=%s AND matchday=%s",
        "UPDATE virtual_matches SET status='live',home_score=0,away_score=0,current_minute=0 WHERE season_id=? AND matchday=?", pg),
        (sid, mday))
    conn.commit(); conn.close()

    engine.live_scores = {mid: {"home":0,"away":0} for mid in finals}
    engine.phase       = "LIVE"
    engine.clock       = "0'"
    engine.action_text = "🏟️ Fischio d'inizio!"
    engine.timer       = 30

    SIM_SECS = 30
    for sec in range(SIM_SECS):
        await asyncio.sleep(1)
        engine.timer = SIM_SECS - sec
        progress = (sec + 1) / SIM_SECS
        game_min  = round(90 * progress)
        engine.clock = f"{game_min}'"

        conn = get_db(); c = conn.cursor(); pg = _pg(conn)
        gol_nel_secondo = False
        for mid, (fh, fa) in finals.items():
            new_h = round(fh * progress)
            new_a = round(fa * progress)
            old   = engine.live_scores[mid]
            if new_h != old["home"] or new_a != old["away"]:
                engine.live_scores[mid] = {"home": new_h, "away": new_a}
                c.execute(_q(
                    "UPDATE virtual_matches SET home_score=%s,away_score=%s,current_minute=%s WHERE id=%s",
                    "UPDATE virtual_matches SET home_score=?,away_score=?,current_minute=? WHERE id=?", pg),
                    (new_h, new_a, game_min, mid))
                gol_nel_secondo = True
        conn.commit(); conn.close()

        if gol_nel_secondo:
            engine.action_text = f"⚽ Gol! ({game_min}')"
        elif not engine.action_text.startswith("🏟"):
            engine.action_text = f"🏟️ In corso... {game_min}'"

    # Scrivi punteggi finali definitivi
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    for mid, (fh, fa) in finals.items():
        c.execute(_q(
            "UPDATE virtual_matches SET home_score=%s,away_score=%s,current_minute=90 WHERE id=%s",
            "UPDATE virtual_matches SET home_score=?,away_score=?,current_minute=90 WHERE id=?", pg),
            (fh, fa, mid))
        engine.live_scores[mid] = {"home": fh, "away": fa}
    conn.commit(); conn.close()

    engine.clock       = "90'"
    engine.action_text = "🏁 Fischio Finale!"
    engine.timer       = 0

    # ------------------------------------------------------------ FINALIZE
    # Aggiorna classifica e paga le scommesse in automatico
    finalize_matchday(sid, mday)
    engine.finished_matchday = mday

    # Avanza matchday in memoria e su DB
    if mday >= 38:
        conn = get_db(); c = conn.cursor(); pg = _pg(conn)
        c.execute(_q("UPDATE virtual_seasons SET status='finished' WHERE id=%s",
                     "UPDATE virtual_seasons SET status='finished' WHERE id=?", pg), (sid,))
        conn.commit(); conn.close()
        get_or_create_season()
    else:
        engine.current_matchday = mday + 1
        conn = get_db(); c = conn.cursor(); pg = _pg(conn)
        c.execute(_q("UPDATE virtual_seasons SET current_matchday=%s WHERE id=%s",
                     "UPDATE virtual_seasons SET current_matchday=? WHERE id=?", pg),
                  (engine.current_matchday, sid))
        conn.commit(); conn.close()

    # ------------------------------------------------------------ FINISHED
    # 2 minuti: scoreboard visibile + scommesse aperte sulla PROSSIMA giornata
    engine.phase       = "FINISHED"
    engine.timer       = 120
    engine.clock       = "FIN"
    engine.action_text = f"🏆 Risultati Giornata {mday}"

    while engine.timer > 0:
        await asyncio.sleep(1)
        engine.timer -= 1

    # ------------------------------------------------------------ BETTING
    # 2 minuti: scoreboard nascosto, solo scommesse
    engine.phase       = "BETTING"
    engine.timer       = 120
    engine.clock       = ""
    engine.action_text = "⏳ Piazza le scommesse!"

    while engine.timer > 0:
        await asyncio.sleep(1)
        engine.timer -= 1

    # poi torna a LIVE (il while nel loop principale)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_virtual_status():
    return {
        "phase":             engine.phase,
        "timer":             engine.timer,
        "matchday":          engine.current_matchday,    # giornata su cui scommettere
        "finished_matchday": engine.finished_matchday,   # ultima giornata completata
        "clock":             engine.clock,
        "action_text":       engine.action_text,
    }

@router.get("/matches")
async def get_virtual_matches():
    """Quote per la giornata corrente (quella su cui si può scommettere)."""
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    c.execute(_q(
        "SELECT m.id,m.matchday,m.status,m.home_score,m.away_score,"
        "m.odds_1,m.odds_x,m.odds_2,m.odds_over25,m.odds_under25,"
        "m.odds_gg,m.odds_ng,m.odds_combo,m.odds_exact,"
        "th.name,th.logo_url,ta.name,ta.logo_url "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=%s AND m.matchday=%s",
        "SELECT m.id,m.matchday,m.status,m.home_score,m.away_score,"
        "m.odds_1,m.odds_x,m.odds_2,m.odds_over25,m.odds_under25,"
        "m.odds_gg,m.odds_ng,m.odds_combo,m.odds_exact,"
        "th.name AS home_name,th.logo_url AS home_logo,"
        "ta.name AS away_name,ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=? AND m.matchday=?", pg),
        (engine.current_season_id, engine.current_matchday))
    rows = c.fetchall(); conn.close()

    res = []
    for m in rows:
        if pg:
            res.append({
                "id":m[0],"matchday":m[1],"status":m[2],"home_score":m[3],"away_score":m[4],
                "odds_1":m[5],"odds_x":m[6],"odds_2":m[7],"odds_over25":m[8],"odds_under25":m[9],
                "odds_gg":m[10],"odds_ng":m[11],
                "odds_combo":json.loads(m[12] or "{}"),
                "odds_exact": json.loads(m[13] or "{}"),
                "home_team":{"name":m[14],"logo":m[15]},
                "away_team":{"name":m[16],"logo":m[17]},
            })
        else:
            res.append({
                "id":m["id"],"matchday":m["matchday"],"status":m["status"],
                "home_score":m["home_score"],"away_score":m["away_score"],
                "odds_1":m["odds_1"],"odds_x":m["odds_x"],"odds_2":m["odds_2"],
                "odds_over25":m["odds_over25"],"odds_under25":m["odds_under25"],
                "odds_gg":m["odds_gg"],"odds_ng":m["odds_ng"],
                "odds_combo":json.loads(m["odds_combo"] or "{}"),
                "odds_exact": json.loads(m["odds_exact"]  or "{}"),
                "home_team":{"name":m["home_name"],"logo":m["home_logo"]},
                "away_team":{"name":m["away_name"],"logo":m["away_logo"]},
            })
    return res

@router.get("/live")
async def get_virtual_live():
    """Punteggi della giornata in corso (LIVE) o appena finita (FINISHED)."""
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)

    # Durante FINISHED mostriamo la giornata appena completata
    show_day = (engine.finished_matchday
                if engine.phase == "FINISHED" and engine.finished_matchday > 0
                else engine.current_matchday)

    c.execute(_q(
        "SELECT m.id,m.home_score,m.away_score,m.current_minute,th.name,ta.name "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=%s AND m.matchday=%s",
        "SELECT m.id,m.home_score,m.away_score,m.current_minute,"
        "th.name AS home_name,ta.name AS away_name "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=? AND m.matchday=?", pg),
        (engine.current_season_id, show_day))
    rows = c.fetchall(); conn.close()

    res = []
    for r in rows:
        mid = r[0] if pg else r["id"]
        if engine.phase == "LIVE" and mid in engine.live_scores:
            hs = engine.live_scores[mid]["home"]
            as_ = engine.live_scores[mid]["away"]
        else:
            hs  = r[1] if pg else r["home_score"]
            as_ = r[2] if pg else r["away_score"]
        res.append({
            "id": mid, "home_score": hs, "away_score": as_,
            "minute": r[3] if pg else r["current_minute"],
            "home_team": {"name": r[4] if pg else r["home_name"]},
            "away_team": {"name": r[5] if pg else r["away_name"]},
        })
    return res

@router.get("/standings")
async def get_virtual_standings():
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    c.execute(_q(
        "SELECT t.name,t.logo_url,s.points,s.played,s.won,s.drawn,s.lost,s.goals_for,s.goals_against "
        "FROM virtual_standings s JOIN virtual_teams t ON s.team_id=t.id "
        "WHERE s.season_id=%s "
        "ORDER BY s.points DESC,(s.goals_for-s.goals_against) DESC,s.goals_for DESC",
        "SELECT t.name,t.logo_url,s.points,s.played,s.won,s.drawn,s.lost,s.goals_for,s.goals_against "
        "FROM virtual_standings s JOIN virtual_teams t ON s.team_id=t.id "
        "WHERE s.season_id=? "
        "ORDER BY s.points DESC,(s.goals_for-s.goals_against) DESC,s.goals_for DESC", pg),
        (engine.current_season_id,))
    rows = c.fetchall(); conn.close()

    res = []
    for r in rows:
        if pg:
            gf,ga = r[7],r[8]
            res.append({"team_name":r[0],"logo":r[1],"points":r[2],"played":r[3],
                        "won":r[4],"drawn":r[5],"lost":r[6],"gf":gf,"ga":ga,"gd":gf-ga})
        else:
            gf,ga = r["goals_for"],r["goals_against"]
            res.append({"team_name":r["name"],"logo":r["logo_url"],"points":r["points"],"played":r["played"],
                        "won":r["won"],"drawn":r["drawn"],"lost":r["lost"],"gf":gf,"ga":ga,"gd":gf-ga})
    return res

@router.get("/history/{matchday}")
async def get_matchday_history(matchday: int):
    """Risultati di una giornata già disputata."""
    if matchday < 1 or matchday > 38:
        raise HTTPException(status_code=400, detail="Giornata non valida")
    conn = get_db(); c = conn.cursor(); pg = _pg(conn)
    c.execute(_q(
        "SELECT m.id,m.home_score,m.away_score,m.status,th.name,th.logo_url,ta.name,ta.logo_url "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=%s AND m.matchday=%s ORDER BY m.id",
        "SELECT m.id,m.home_score,m.away_score,m.status,"
        "th.name AS home_name,th.logo_url AS home_logo,"
        "ta.name AS away_name,ta.logo_url AS away_logo "
        "FROM virtual_matches m "
        "JOIN virtual_teams th ON m.home_team_id=th.id "
        "JOIN virtual_teams ta ON m.away_team_id=ta.id "
        "WHERE m.season_id=? AND m.matchday=? ORDER BY m.id", pg),
        (engine.current_season_id, matchday))
    rows = c.fetchall(); conn.close()
    return [{
        "id":         r[0] if pg else r["id"],
        "home_score": r[1] if pg else r["home_score"],
        "away_score": r[2] if pg else r["away_score"],
        "status":     r[3] if pg else r["status"],
        "home_team":  {"name": r[4] if pg else r["home_name"], "logo": r[5] if pg else r["home_logo"]},
        "away_team":  {"name": r[6] if pg else r["away_name"], "logo": r[7] if pg else r["away_logo"]},
    } for r in rows]
