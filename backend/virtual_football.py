import asyncio
import random
import time
import math
import json
import traceback
from fastapi import APIRouter, Depends, HTTPException, Body
from backend.database import get_db

router = APIRouter()

# --- Configurazione Squadre Serie A ---
SERIE_A_TEAMS = [
    {"name": "Atalanta",   "offense": 82, "defense": 78},
    {"name": "Bologna",    "offense": 75, "defense": 76},
    {"name": "Cagliari",   "offense": 68, "defense": 65},
    {"name": "Como",       "offense": 67, "defense": 63},
    {"name": "Cremonese",  "offense": 66, "defense": 62},
    {"name": "Fiorentina", "offense": 78, "defense": 75},
    {"name": "Genoa",      "offense": 71, "defense": 70},
    {"name": "Hellas Verona","offense": 69, "defense": 68},
    {"name": "Inter",      "offense": 88, "defense": 85},
    {"name": "Juventus",   "offense": 85, "defense": 87},
    {"name": "Lazio",      "offense": 80, "defense": 77},
    {"name": "Lecce",      "offense": 69, "defense": 67},
    {"name": "Milan",      "offense": 86, "defense": 82},
    {"name": "Napoli",     "offense": 84, "defense": 81},
    {"name": "Parma",      "offense": 68, "defense": 65},
    {"name": "Pisa",       "offense": 65, "defense": 64},
    {"name": "Roma",       "offense": 81, "defense": 79},
    {"name": "Sassuolo",   "offense": 73, "defense": 68},
    {"name": "Torino",     "offense": 73, "defense": 76},
    {"name": "Udinese",    "offense": 70, "defense": 69},
]

# Variabili di stato globale del simulatore
class VirtualEngine:
    def __init__(self):
        self.phase = "BETTING"  # 'BETTING', 'LIVE', 'FINISHED'
        self.timer = 0
        self.current_season_id = None
        self.current_matchday = 1
        self.finished_matchday = 0  
        self.clock = "0'"       
        self.action_text = ""   

engine = VirtualEngine()

def check_is_psql(conn):
    return hasattr(conn, 'get_dsn_parameters')

def init_teams():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    cursor.execute("SELECT COUNT(*) FROM virtual_teams")
    count = cursor.fetchone()[0]
    if count == 0:
        print("[Virtual] Inizializzazione 20 squadre Serie A...")
        for t in SERIE_A_TEAMS:
            if psql:
                cursor.execute("INSERT INTO virtual_teams (name, offense, defense) VALUES (%s, %s, %s)", (t["name"], t["offense"], t["defense"]))
            else:
                cursor.execute("INSERT INTO virtual_teams (name, offense, defense) VALUES (?, ?, ?)", (t["name"], t["offense"], t["defense"]))
        conn.commit()
    conn.close()

def get_or_create_season():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    # Cerchiamo solo l'ultima stagione ATTIVA
    cursor.execute("SELECT id, current_matchday FROM virtual_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    season = cursor.fetchone()
    if not season:
        print("[Virtual] Creazione nuova stagione...")
        if psql:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active') RETURNING id")
            season_id = cursor.fetchone()[0]
        else:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active')")
            season_id = cursor.lastrowid
        conn.commit()
        generate_fixtures(season_id, conn)
        engine.current_season_id = season_id
        engine.current_matchday = 1
    else:
        engine.current_season_id = season[0] if psql else season["id"]
        engine.current_matchday = season[1] if psql else season["current_matchday"]
    conn.close()

def mark_season_finished(season_id):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET status = 'finished' WHERE id = %s" if psql else "UPDATE virtual_seasons SET status = 'finished' WHERE id = ?"
    cursor.execute(q, (season_id,))
    conn.commit()
    conn.close()

def update_season_matchday(season_id, mday):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET current_matchday = %s WHERE id = %s" if psql else "UPDATE virtual_seasons SET current_matchday = ? WHERE id = ?"
    cursor.execute(q, (mday, season_id))
    conn.commit()
    conn.close()

def finalize_matchday(season_id, matchday):
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    print(f"[Virtual] Finalizzo giornata {matchday} della stagione {season_id}")
    
    if psql:
        cursor.execute("SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s", (season_id, matchday))
    else:
        cursor.execute("SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?", (season_id, matchday))
    matches = cursor.fetchall()
    
    for m in matches:
        m_id = m[0] if psql else m["id"]
        h_id = m[1] if psql else m["home_team_id"]
        a_id = m[2] if psql else m["away_team_id"]
        h_g = m[3] if psql else m["home_score"]
        a_g = m[4] if psql else m["away_score"]
        
        h_pts, a_pts = (3, 0) if h_g > a_g else ((1, 1) if h_g == a_g else (0, 3))
        h_w, h_d, h_l = (1, 0, 0) if h_g > a_g else ((0, 1, 0) if h_g == a_g else (0, 0, 1))
        a_w, a_d, a_l = (0, 0, 1) if h_g > a_g else ((0, 1, 0) if h_g == a_g else (1, 0, 0))
        
        def update_st(tid, pts, w, d, l, gf, ga):
            params = (season_id, tid, pts, w, d, l, gf, ga)
            if psql:
                cursor.execute("""
                    INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                    VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
                    ON CONFLICT(season_id, team_id) DO UPDATE SET
                    points = virtual_standings.points + EXCLUDED.points, played = virtual_standings.played + 1,
                    won = virtual_standings.won + EXCLUDED.won, drawn = virtual_standings.drawn + EXCLUDED.drawn,
                    lost = virtual_standings.lost + EXCLUDED.lost, goals_for = virtual_standings.goals_for + EXCLUDED.goals_for,
                    goals_against = virtual_standings.goals_against + EXCLUDED.goals_against
                """, params)
            else:
                cursor.execute("""
                    INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(season_id, team_id) DO UPDATE SET
                    points = virtual_standings.points + excluded.points, played = virtual_standings.played + 1,
                    won = virtual_standings.won + excluded.won, drawn = virtual_standings.drawn + excluded.drawn,
                    lost = virtual_standings.lost + excluded.lost, goals_for = virtual_standings.goals_for + excluded.goals_for,
                    goals_against = virtual_standings.goals_against + excluded.goals_against
                """, params)
        
        update_st(h_id, h_pts, h_w, h_d, h_l, h_g, a_g)
        update_st(a_id, a_pts, a_w, a_d, a_l, a_g, h_g)
        
        if psql: cursor.execute("UPDATE virtual_matches SET status = 'finished' WHERE id = %s", (m_id,))
        else: cursor.execute("UPDATE virtual_matches SET status = 'finished' WHERE id = ?", (m_id,))
            
    resolve_virtual_bets(conn, season_id, matchday)
    conn.commit()
    conn.close()

def resolve_virtual_bets(conn, season_id, matchday):
    try:
        cursor = conn.cursor()
        psql = check_is_psql(conn)
        print(f"[Virtual Resolve] Inizio resolv giornata {matchday} stagione {season_id}")
        
        if psql:
            cursor.execute("SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s", (season_id, matchday))
        else:
            cursor.execute("SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?", (season_id, matchday))
        
        match_results = {}
        for r in cursor.fetchall():
            m_id = r[0] if psql else r["id"]
            h_g = r[1] if psql else r["home_score"]
            a_g = r[2] if psql else r["away_score"]
            
            res = set()
            r1x2 = "1" if h_g > a_g else ("X" if h_g == a_g else "2")
            res.add(r1x2)
            for t in [1.5, 2.5, 3.5, 4.5]:
                label = f"Over {t}" if (h_g + a_g) > t else f"Under {t}"
                res.add(label)
                res.add(f"{r1x2}+{label}")
            
            gg_str = "Goal" if (h_g > 0 and a_g > 0) else "No Goal"
            gg_combo = "GG" if (h_g > 0 and a_g > 0) else "NG"
            res.add(gg_str)
            res.add(f"{r1x2}+{gg_combo}")
            
            exact_str = f"{h_g}-{a_g}"
            res.add(f"Esatto {exact_str}" if exact_str in {"0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"} else "Esatto Altro")
            match_results[f"v_{m_id}"] = res

        if not match_results: 
            print("[Virtual Resolve] Nessuna partita trovata.")
            return

        ph = ", ".join(["%s" if psql else "?" for _ in match_results.keys()])
        query = f"SELECT bs.bet_id, bs.event_id, bs.selection, b.user_id FROM bet_selections bs JOIN bets b ON bs.bet_id = b.id WHERE b.status = 'pending' AND bs.event_id IN ({ph})"
        cursor.execute(query, list(match_results.keys()))
        selections = cursor.fetchall()
        
        affected_bets = set()
        for s in selections:
            bid, evid, sel = (s[0], s[1], s[2]) if psql else (s["bet_id"], s["event_id"], s["selection"])
            is_won = sel in match_results.get(evid, set())
            new_st = 'won' if is_won else 'lost'
            if psql:
                cursor.execute("UPDATE bet_selections SET status = %s WHERE bet_id = %s AND event_id = %s", (new_st, bid, evid))
            else:
                cursor.execute("UPDATE bet_selections SET status = ? WHERE bet_id = ? AND event_id = ?", (new_st, bid, evid))
            affected_bets.add(bid)

        for bid in affected_bets:
            try:
                if psql: cursor.execute("SELECT status FROM bet_selections WHERE bet_id = %s", (bid,))
                else: cursor.execute("SELECT status FROM bet_selections WHERE bet_id = ?", (bid,))
                statuses = [r[0] if psql else r["status"] for r in cursor.fetchall()]
                
                if 'lost' in statuses:
                    if psql: cursor.execute("UPDATE bets SET status = 'lost' WHERE id = %s", (bid,))
                    else: cursor.execute("UPDATE bets SET status = 'lost' WHERE id = ?", (bid,))
                elif all(st == 'won' for st in statuses):
                    if psql: cursor.execute("SELECT user_id, potential_win FROM bets WHERE id = %s", (bid,))
                    else: cursor.execute("SELECT user_id, potential_win FROM bets WHERE id = ?", (bid,))
                    b_data = cursor.fetchone()
                    uid, win_amt = (b_data[0], b_data[1]) if psql else (b_data["user_id"], b_data["potential_win"])
                    
                    if psql: cursor.execute("SELECT balance FROM users WHERE id = %s", (uid,))
                    else: cursor.execute("SELECT balance FROM users WHERE id = ?", (uid,))
                    old_bal = float(cursor.fetchone()[0])
                    new_bal = old_bal + win_amt

                    if psql:
                        cursor.execute("UPDATE bets SET status = 'won' WHERE id = %s", (bid,))
                        cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_bal, uid))
                        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (%s, 'credit', %s, %s, %s, 0, %s)", 
                                       (uid, win_amt, old_bal, new_bal, f"Vincita Virtuale #{bid}"))
                    else:
                        cursor.execute("UPDATE bets SET status = 'won' WHERE id = ?", (bid,))
                        cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_bal, uid))
                        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (?, 'credit', ?, ?, ?, 0, ?)", 
                                       (uid, win_amt, old_bal, new_bal, f"Vincita Virtuale #{bid}"))
                    print(f"[Virtual Resolve] Pagato {win_amt}€ a user {uid} per schedina #{bid}")
            except Exception as e_bet:
                print(f"[Virtual Resolve Error] Bet #{bid}: {e_bet}")
    except Exception as e:
        print(f"[Virtual Resolve Error] {e}")

def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k)

def generate_fixtures(season_id, conn):
    cursor = conn.cursor()
    psql = check_is_psql(conn)
    cursor.execute("SELECT id, name, offense, defense FROM virtual_teams")
    teams = cursor.fetchall()
    team_dict = {t[0] if psql else t["id"]: {"name": t[1] if psql else t["name"], "offense": t[2] if psql else t["offense"], "defense": t[3] if psql else t["defense"]} for t in teams}
    team_ids = list(team_dict.keys())
    
    cursor.execute("SELECT value FROM settings WHERE key = 'virtual_house_edge'")
    row = cursor.fetchone()
    edge_pct = float(row[0] if row else 15.0)
    margin = 1.0 - (edge_pct / 100.0)

    if len(team_ids) != 20: return
    # IMPORTANTE: Mescola le squadre per ogni nuova stagione
    random.shuffle(team_ids)
    rounds = []
    temp_ids = list(team_ids)
    for r in range(19):
        matches = [(temp_ids[i], temp_ids[19-i]) for i in range(10)]
        temp_ids.insert(1, temp_ids.pop())
        rounds.append(matches)
        
    def get_odds(hid, aid):
        h, a = team_dict[hid], team_dict[aid]
        exph = max(0.5, (h["offense"] - a["defense"] + 50) / 100 * 1.5) + 0.3
        expa = max(0.4, (a["offense"] - h["defense"] + 50) / 100 * 1.5)
        p1, px, p2, po, pgg = 0, 0, 0, 0, 0
        for hg in range(6):
            for ag in range(6):
                prob = poisson_prob(exph, hg) * poisson_prob(expa, ag)
                if hg > ag: p1 += prob
                elif hg == ag: px += prob
                else: p2 += prob
                if hg + ag > 2.5: po += prob
                if hg > 0 and ag > 0: pgg += prob
        total = p1 + px + p2
        p1/=total; px/=total; p2/=total
        sq = lambda p: round(max(1.01, min(99.0, (1.0/p)*margin)), 2)
        return sq(p1), sq(px), sq(p2), sq(po), sq(1-po), sq(pgg), sq(1-pgg)

    def get_ext(hid, aid):
        h, a = team_dict[hid], team_dict[aid]
        exph = max(0.5, (h["offense"] - a["defense"] + 50) / 100 * 1.5) + 0.3
        expa = max(0.4, (a["offense"] - h["defense"] + 50) / 100 * 1.5)
        combo, exact = {}, {}
        for hg in range(6):
            for ag in range(6):
                prob = poisson_prob(exph, hg) * poisson_prob(expa, ag)
                r = "1" if hg > ag else ("X" if hg == ag else "2")
                is_gg = (hg > 0 and ag > 0)
                gg = "GG" if is_gg else "NG"
                for th in [1.5, 2.5, 3.5, 4.5]:
                    tk = f"Over {th}" if (hg+ag) > th else f"Under {th}"
                    combo[tk] = combo.get(tk, 0) + prob
                    combo[f"{r}+{tk}"] = combo.get(f"{r}+{tk}", 0) + prob
                combo[f"{r}+{gg}"] = combo.get(f"{r}+{gg}", 0) + prob
                exact[f"{hg}-{ag}"] = exact.get(f"{hg}-{ag}", 0) + prob
        sq = lambda p: round(max(1.01, min(99.0, (1.0/p)*margin)), 2) if p > 0.001 else None
        co = {k: sq(v) for k, v in combo.items() if sq(v)}
        known = ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"]
        eo = {s: sq(exact[s]) for s in known if s in exact}
        eo["Altro"] = sq(max(0.001, 1.0 - sum(exact[s] for s in known if s in exact)))
        return co, eo

    for r_num, matches in enumerate(rounds):
        mday, rday = r_num + 1, r_num + 20
        for h, a in matches:
            o1, ox, o2, oo, ou, ogg, ong = get_odds(h, a)
            o1r, oxr, o2r, oor, our, oggr, ongr = get_odds(a, h)
            c, e = get_ext(h, a)
            cr, er = get_ext(a, h)
            cj, ej, crj, erj = json.dumps(c), json.dumps(e), json.dumps(cr), json.dumps(er)
            q = "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (%s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s, %s, %s, %s, %s)" if psql else "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            cursor.execute(q, (season_id, mday, h, a, o1, ox, o2, oo, ou, ogg, ong, cj, ej))
            # Matchday rday (ritorno)
            cursor.execute(q, (season_id, rday, a, h, o1r, oxr, o2r, oor, our, oggr, ongr, crj, erj))
    conn.commit()

async def run_virtual_football_loop():
    print("[Virtual] Loop Avviato.")
    try:
        init_teams()
        get_or_create_season()
    except Exception:
        print("[CRITICAL] Loop INIT Error:", traceback.format_exc()); return
    
    while True:
        # 1. FASE BETTING
        engine.phase, engine.timer, engine.clock, engine.action_text = "BETTING", 120, "", "⏳ Piazza le scommesse!"
        while engine.timer > 0: await asyncio.sleep(1); engine.timer -= 1
        
        # 2. FASE LIVE
        engine.phase, engine.timer, engine.clock, engine.action_text = "LIVE", 30, "0'", "🏟️ Fischio d'inizio!"
        conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
        q_up = "UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = %s AND matchday = %s" if psql else "UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = ? AND matchday = ?"
        cursor.execute(q_up, (engine.current_season_id, engine.current_matchday))
        conn.commit()
        
        cursor.execute("SELECT id, offense, defense FROM virtual_teams")
        t_rats = {r[0] if psql else r["id"]: {"o": r[1] if psql else r["offense"], "d": r[2] if psql else r["defense"]} for r in cursor.fetchall()}
        cursor.execute("SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql else "SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        matches = cursor.fetchall()
        
        for sec in range(30, 0, -1):
            await asyncio.sleep(1); engine.timer = sec
            if sec in (25, 20, 15, 10, 5, 2):
                min_str = {25:"15'", 20:"30'", 15:"45'", 10:"60'", 5:"75'", 2:"90'"}[sec]
                engine.clock, engine.action_text = min_str, f"⚽ Azione {min_str}"
                for m in matches:
                    mid, hid, aid = (m[0], m[1], m[2]) if psql else (m["id"], m["home_team_id"], m["away_team_id"])
                    hg = 1 if random.random() < (t_rats[hid]["o"]-t_rats[aid]["d"]+50)/600 else 0
                    ag = 1 if random.random() < (t_rats[aid]["o"]-t_rats[hid]["d"]+50)/600 else 0
                    q_g = "UPDATE virtual_matches SET home_score = home_score + %s, away_score = away_score + %s, current_minute = %s WHERE id = %s" if psql else "UPDATE virtual_matches SET home_score = home_score + ?, away_score = away_score + ?, current_minute = ? WHERE id = ?"
                    cursor.execute(q_g, (hg, ag, int(min_str.replace("'","")), mid))
                conn.commit()
        conn.close()
        
        # 3. FINALIZZAZIONE E PAGAMENTO
        finalize_matchday(engine.current_season_id, engine.current_matchday)
        engine.finished_matchday = engine.current_matchday
        
        # 4. AVANZAMENTO GIORNATA / RESET STAGIONE
        if engine.current_matchday >= 38:
            print(f"[Virtual] Fine Stagione {engine.current_season_id}. Reset Classifica...")
            mark_season_finished(engine.current_season_id)
            engine.current_matchday = 1
            get_or_create_season() # Creerà una nuova stagione 'active'
        else:
            engine.current_matchday += 1
            update_season_matchday(engine.current_season_id, engine.current_matchday)

        # 5. FASE FINISHED
        engine.phase, engine.timer, engine.clock, engine.action_text = "FINISHED", 120, "FIN", f"🏆 Risultati giornata {engine.finished_matchday}"
        while engine.timer > 0: await asyncio.sleep(1); engine.timer -= 1

@router.get("/status")
async def get_virtual_status():
    return {
        "phase": engine.phase, 
        "timer": engine.timer, 
        "matchday": engine.current_matchday, 
        "finished_matchday": engine.finished_matchday, # Importante per la UI
        "season_id": engine.current_season_id, 
        "clock": engine.clock, 
        "action_text": engine.action_text
    }

@router.get("/live")
async def get_virtual_live():
    from backend.database import get_db
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    # Se siamo in fase FINISHED mostriamo i risultati della giornata appena conclusa
    # Altrimenti mostriamo quella corrente (per i live update)
    if engine.phase == 'FINISHED':
        day = engine.finished_matchday
        # Se siamo appena passati alla stagione nuova, dobbiamo usare l'ID precedente?
        # No, se day=38 e engine.current_matchday=1, cercheremo i matchday 38.
        # Se matchday 38 era della stagione precedente, dobbiamo trovarlo.
        # Per semplicità, cerchiamo l'ultimo stagione finita se siamo a day=38 e current=1.
        sid = engine.current_season_id
        if day == 38 and engine.current_matchday == 1:
            q_prev = "SELECT id FROM virtual_seasons WHERE status = 'finished' ORDER BY id DESC LIMIT 1"
            cursor.execute(q_prev)
            p_row = cursor.fetchone()
            if p_row: sid = p_row[0]
    else:
        day = engine.current_matchday
        sid = engine.current_season_id

    q = "SELECT m.id, m.home_score, m.away_score, th.name, ta.name FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = %s AND m.matchday = %s" if psql else "SELECT m.id, m.home_score, m.away_score, th.name, ta.name FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = ? AND m.matchday = ?"
    cursor.execute(q, (sid, day))
    rows = cursor.fetchall()
    conn.close()
    return [{"id":r[0], "home_score":r[1], "away_score":r[2], "home_team":{"name":r[3]}, "away_team":{"name":r[4]}} if psql else {"id":r["id"], "home_score":r["home_score"], "away_score":r["away_score"], "home_team":{"name":r["name"]}, "away_team":{"name":r["name:1"]}} for r in rows]

@router.get("/matches")
async def get_virtual_matches():
    from backend.database import get_db
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute, m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, th.name, th.logo_url, ta.name, ta.logo_url FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = %s AND m.matchday = %s" if psql else "SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute, m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, th.name, th.logo_url, ta.name, ta.logo_url FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = ? AND m.matchday = ?"
    cursor.execute(q, (engine.current_season_id, engine.current_matchday))
    rows = cursor.fetchall(); conn.close()
    res = []
    for m in rows:
        if psql:
            res.append({"id":m[0], "matchday":m[1], "status":m[2], "home_score":m[3], "away_score":m[4], "odds_1":m[6], "odds_combo":json.loads(m[13] or '{}'), "odds_exact":json.loads(m[14] or '{}'), "home_team":{"name":m[15], "logo":m[16]}, "away_team":{"name":m[17], "logo":m[18]}, "odds_x":m[7], "odds_2":m[8], "odds_over25":m[9], "odds_under25":m[10], "odds_gg":m[11], "odds_ng":m[12]})
        else:
            res.append({"id":m["id"], "matchday":m["matchday"], "status":m["status"], "home_score":m["home_score"], "away_score":m["away_score"], "odds_1":m["odds_1"], "odds_combo":json.loads(m["odds_combo"] or '{}'), "odds_exact":json.loads(m["odds_exact"] or '{}'), "home_team":{"name":m["name"], "logo":m["logo_url"]}, "away_team":{"name":m["name:1"], "logo":m["logo_url:1"]}, "odds_x":m["odds_x"], "odds_2":m["odds_2"], "odds_over25":m["odds_over25"], "odds_under25":m["odds_under25"], "odds_gg":m["odds_gg"], "odds_ng":m["odds_ng"]})
    return res

@router.get("/standings")
async def get_virtual_standings():
    from backend.database import get_db
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against FROM virtual_standings s JOIN virtual_teams t ON s.team_id = t.id WHERE s.season_id = %s ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC" if psql else "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against FROM virtual_standings s JOIN virtual_teams t ON s.team_id = t.id WHERE s.season_id = ? ORDER BY s.points DESC"
    cursor.execute(q, (engine.current_season_id,))
    rows = cursor.fetchall(); conn.close()
    return [{"team_name":r[0], "logo":r[1], "points":r[2], "played":r[3], "won":r[4], "drawn":r[5], "lost":r[6], "gf":r[7], "ga":r[8], "gd":r[7]-r[8]} if psql else {"team_name":r["name"], "logo":r["logo_url"], "points":r["points"], "played":r["played"], "won":r["won"], "drawn":r["drawn"], "lost":r["lost"], "gf":r["goals_for"], "ga":r["goals_against"], "gd":r["goals_for"]-r["goals_against"]} for r in rows]
