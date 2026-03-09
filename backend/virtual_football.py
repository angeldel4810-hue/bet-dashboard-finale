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
    {"name": "Atalanta",   "offense": 82, "defense": 78, "logo": "https://upload.wikimedia.org/wikipedia/en/6/66/AtalantaBC.svg"},
    {"name": "Bologna",    "offense": 75, "defense": 76, "logo": "https://upload.wikimedia.org/wikipedia/en/5/5b/Bologna_F.C._1909_logo.svg"},
    {"name": "Cagliari",   "offense": 68, "defense": 65, "logo": "https://upload.wikimedia.org/wikipedia/en/6/61/Cagliari_Calcio_1970_logo.svg"},
    {"name": "Como",       "offense": 67, "defense": 63, "logo": "https://upload.wikimedia.org/wikipedia/en/1/1e/Como_1907_logo.svg"},
    {"name": "Cremonese",  "offense": 66, "defense": 62, "logo": "https://upload.wikimedia.org/wikipedia/en/d/df/US_Cremonese_logo.svg"},
    {"name": "Fiorentina", "offense": 78, "defense": 75, "logo": "https://upload.wikimedia.org/wikipedia/en/b/ba/ACF_Fiorentina_2022_logo.svg"},
    {"name": "Genoa",      "offense": 71, "defense": 70, "logo": "https://upload.wikimedia.org/wikipedia/en/6/6c/Genoa_C.F.C._logo.svg"},
    {"name": "Hellas Verona","offense": 69, "defense": 68, "logo": "https://upload.wikimedia.org/wikipedia/en/9/92/Hellas_Verona_FC_logo_2020.svg"},
    {"name": "Inter",      "offense": 88, "defense": 85, "logo": "https://upload.wikimedia.org/wikipedia/commons/0/05/FC_Internazionale_Milano_2021.svg"},
    {"name": "Juventus",   "offense": 85, "defense": 87, "logo": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Juventus_FC_2017_icon_%28black%29.svg"},
    {"name": "Lazio",      "offense": 80, "defense": 77, "logo": "https://upload.wikimedia.org/wikipedia/en/c/ce/S.S._Lazio_badge.svg"},
    {"name": "Lecce",      "offense": 69, "defense": 67, "logo": "https://upload.wikimedia.org/wikipedia/en/3/36/U.S._Lecce_logo.svg"},
    {"name": "Milan",      "offense": 86, "defense": 82, "logo": "https://upload.wikimedia.org/wikipedia/commons/d/d0/Logo_of_AC_Milan.svg"},
    {"name": "Napoli",     "offense": 84, "defense": 81, "logo": "https://upload.wikimedia.org/wikipedia/commons/2/2d/SSC_Napoli_2021.svg"},
    {"name": "Parma",      "offense": 68, "defense": 65, "logo": "https://upload.wikimedia.org/wikipedia/en/d/d2/Parma_Calcio_1913_logo.svg"},
    {"name": "Pisa",       "offense": 65, "defense": 64, "logo": "https://upload.wikimedia.org/wikipedia/en/6/6c/A.C._Pisa_1909_logo.svg"},
    {"name": "Roma",       "offense": 81, "defense": 79, "logo": "https://upload.wikimedia.org/wikipedia/en/f/f7/AS_Roma_logo_%282017%29.svg"},
    {"name": "Sassuolo",   "offense": 73, "defense": 68, "logo": "https://upload.wikimedia.org/wikipedia/en/1/1c/US_Sassuolo_Calcio_logo.svg"},
    {"name": "Torino",     "offense": 73, "defense": 76, "logo": "https://upload.wikimedia.org/wikipedia/en/2/2e/Torino_FC_Logo.svg"},
    {"name": "Udinese",    "offense": 70, "defense": 69, "logo": "https://upload.wikimedia.org/wikipedia/en/c/ce/Udinese_Calcio_logo.svg"},
]

class VirtualEngine:
    def __init__(self):
        self.phase = "BETTING" # BETTING, LIVE, FINALIZING, FINISHED
        self.timer = 0
        self.current_season_id = None
        self.current_matchday = 1
        self.finished_matchday = 0  
        self.clock = "0'"       
        self.action_text = ""   

engine = VirtualEngine()

def check_is_psql(conn):
    return hasattr(conn, 'get_dsn_parameters')

def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k) if k >= 0 else 0

def init_teams():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    # Aggiorniamo sempre i loghi se mancano o se le squadre esistono già
    for t in SERIE_A_TEAMS:
        q_check = "SELECT id FROM virtual_teams WHERE name = %s" if psql else "SELECT id FROM virtual_teams WHERE name = ?"
        cursor.execute(q_check, (t["name"],))
        row = cursor.fetchone()
        if row:
            q_up = "UPDATE virtual_teams SET offense=%s, defense=%s, logo_url=%s WHERE id=%s" if psql else "UPDATE virtual_teams SET offense=?, defense=?, logo_url=? WHERE id=?"
            cursor.execute(q_up, (t["offense"], t["defense"], t["logo"], row[0]))
        else:
            q_in = "INSERT INTO virtual_teams (name, offense, defense, logo_url) VALUES (%s, %s, %s, %s)" if psql else "INSERT INTO virtual_teams (name, offense, defense, logo_url) VALUES (?, ?, ?, ?)"
            cursor.execute(q_in, (t["name"], t["offense"], t["defense"], t["logo"]))
    conn.commit()
    conn.close()

def get_or_create_season():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    cursor.execute("SELECT id, current_matchday FROM virtual_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        if psql:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active') RETURNING id")
            sid = cursor.fetchone()[0]
        else:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active')")
            sid = cursor.lastrowid
        conn.commit()
        generate_fixtures(sid, conn)
        engine.current_season_id, engine.current_matchday = sid, 1
    else:
        engine.current_season_id = row[0] if psql else row["id"]
        engine.current_matchday = row[1] if psql else row["current_matchday"]
    conn.close()

def update_season_matchday(season_id, mday):
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET current_matchday = %s WHERE id = %s" if psql else "UPDATE virtual_seasons SET current_matchday = ? WHERE id = ?"
    cursor.execute(q, (mday, season_id))
    conn.commit(); conn.close()

def mark_season_finished(season_id):
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "UPDATE virtual_seasons SET status = 'finished' WHERE id = %s" if psql else "UPDATE virtual_seasons SET status = 'finished' WHERE id = ?"
    cursor.execute(q, (season_id,))
    conn.commit(); conn.close()

def finalize_matchday(season_id, matchday):
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    try:
        q = "SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql else "SELECT id, home_team_id, away_team_id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?"
        cursor.execute(q, (season_id, matchday))
        matches = cursor.fetchall()
        for m in matches:
            mid, h_id, a_id = (m[0], m[1], m[2]) if psql else (m["id"], m["home_team_id"], m["away_team_id"])
            h_g, a_g = (m[3], m[4]) if psql else (m["home_score"], m["away_score"])
            h_p = (3, 0) if h_g > a_g else ((1, 1) if h_g == a_g else (0, 3))
            h_p, a_p = h_p[0], h_p[1]
            h_w, h_d, h_l = (1,0,0) if h_p==3 else ((0,1,0) if h_p==1 else (0,0,1))
            a_w, a_d, a_l = (0,0,1) if h_p==3 else ((0,1,0) if h_p==1 else (1,0,0))

            def upd_st(tid, pts, w, d, l, gf, ga):
                par = (season_id, tid, pts, w, d, l, gf, ga)
                if psql:
                    cursor.execute("""
                        INSERT INTO virtual_standings (season_id,team_id,points,played,won,drawn,lost,goals_for,goals_against)
                        VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s)
                        ON CONFLICT(season_id,team_id) DO UPDATE SET
                        points=virtual_standings.points+EXCLUDED.points, played=virtual_standings.played+1,
                        won=virtual_standings.won+EXCLUDED.won, drawn=virtual_standings.drawn+EXCLUDED.drawn,
                        lost=virtual_standings.lost+EXCLUDED.lost, goals_for=virtual_standings.goals_for+EXCLUDED.goals_for,
                        goals_against=virtual_standings.goals_against+EXCLUDED.goals_against
                    """, par)
                else:
                    cursor.execute("""
                        INSERT INTO virtual_standings (season_id,team_id,points,played,won,drawn,lost,goals_for,goals_against)
                        VALUES (?,?,?,1,?,?,?,?,?)
                        ON CONFLICT(season_id,team_id) DO UPDATE SET
                        points=points+excluded.points, played=played+1,
                        won=won+excluded.won, drawn=drawn+excluded.drawn,
                        lost=lost+excluded.lost, goals_for=goals_for+excluded.goals_for,
                        goals_against=goals_against+excluded.goals_against
                    """, par)
            upd_st(h_id, h_p, h_w, h_d, h_l, h_g, a_g)
            upd_st(a_id, a_p, a_w, a_d, a_l, a_g, h_g)
            cursor.execute("UPDATE virtual_matches SET status='finished' WHERE id=%s" if psql else "UPDATE virtual_matches SET status='finished' WHERE id=?", (mid,))
        conn.commit()
    except Exception as e:
        print(f"[Finalize Error] {traceback.format_exc()}")
       resolve_virtual_bets(season_id, matchday)
        except: pass
    finally:
        conn.close()

    # Connessione NUOVA separata - evita lock PostgreSQL
   def resolve_virtual_bets(season_id, matchday):
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)


def resolve_virtual_bets(season_id, matchday):
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    try:
        # Controlla modalita pagamento
        cursor.execute("SELECT value FROM settings WHERE key='virtual_pay_mode'")
        row = cursor.fetchone()
        pay_mode = (row[0] if psql else row["value"]) if row else 'auto'
        if pay_mode != 'auto':
            print(f"[Virtual Bets] Modalita manuale - skip giornata {matchday}")
            return

        cursor.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
        adm = cursor.fetchone()
        admin_id = (adm[0] if psql else adm["id"]) if adm else 1

        cursor.execute(
            "SELECT id,home_score,away_score FROM virtual_matches WHERE season_id=%s AND matchday=%s AND status='finished'" if psql
            else "SELECT id,home_score,away_score FROM virtual_matches WHERE season_id=? AND matchday=? AND status='finished'",
            (season_id, matchday))
        results = {}
        for r in cursor.fetchall():
            mid,hg,ag = (r[0],r[1],r[2]) if psql else (r["id"],r["home_score"],r["away_score"])
            es = set()
            r1x2 = "1" if hg>ag else ("X" if hg==ag else "2")
            es.add(r1x2)
            tg = hg+ag
            for t in [1.5,2.5,3.5,4.5]:
                lbl = f"Over {t}" if tg>t else f"Under {t}"
                es.add(lbl); es.add(f"{r1x2}+{lbl}")
            gg_val = "Goal" if (hg>0 and ag>0) else "No Goal"
            gg_c = "GG" if (hg>0 and ag>0) else "NG"
            es.add(gg_val); es.add(f"{r1x2}+{gg_c}")
            ex = f"{hg}-{ag}"
            es.add(f"Esatto {ex}"); es.add(ex)
            if ex not in {"0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2","2-2","3-0","0-3","3-1","1-3","3-2","2-3"}:
                es.add("Esatto Altro"); es.add("Altro")
            results[f"v_{mid}"] = es

        if not results:
            print(f"[Virtual Bets] Nessuna partita finished per giornata {matchday}")
            return

        print(f"[Virtual Bets] Giornata {matchday} - partite: {list(results.keys())}")
        event_ids = list(results.keys())
        ph = ",".join(["%s"]*len(event_ids)) if psql else ",".join(["?"]*len(event_ids))
        cursor.execute(f"SELECT DISTINCT b.id,b.user_id,b.potential_win FROM bets b JOIN bet_selections bs ON b.id=bs.bet_id WHERE b.status='pending' AND bs.event_id IN ({ph})", event_ids)
        pending = cursor.fetchall()
        print(f"[Virtual Bets] Scommesse pending: {len(pending)}")

        for b in pending:
            bid,uid,win = (b[0],b[1],b[2]) if psql else (b["id"],b["user_id"],b["potential_win"])
            cursor.execute("SELECT event_id,selection,status FROM bet_selections WHERE bet_id=%s" if psql else "SELECT event_id,selection,status FROM bet_selections WHERE bet_id=?", (bid,))
            sels = cursor.fetchall()
            all_resolved = True
            is_won = True
            for s in sels:
                evid = s[0] if psql else s["event_id"]
                sel  = s[1] if psql else s["selection"]
                cst  = s[2] if psql else s["status"]
                if evid in results:
                    sw = (sel in results[evid] or sel.replace("Esatto ","") in results[evid])
                    cursor.execute("UPDATE bet_selections SET status=%s WHERE bet_id=%s AND event_id=%s" if psql else "UPDATE bet_selections SET status=? WHERE bet_id=? AND event_id=?", ('won' if sw else 'lost', bid, evid))
                    if not sw: is_won = False
                else:
                    if cst=='pending': all_resolved = False
                    if cst=='lost': is_won = False

            if not is_won:
                cursor.execute("UPDATE bets SET status='lost' WHERE id=%s" if psql else "UPDATE bets SET status='lost' WHERE id=?", (bid,))
                print(f"[Virtual Bets] #{bid} PERSA")
            elif all_resolved:
                cursor.execute("SELECT balance FROM users WHERE id=%s" if psql else "SELECT balance FROM users WHERE id=?", (uid,))
conn.commit()
    conn.close()                nxt = prev + float(win)
                cursor.execute("UPDATE users SET balance=%s WHERE id=%s" if psql else "UPDATE users SET balance=? WHERE id=?", (nxt,uid))
                cursor.execute("UPDATE bets SET status='won' WHERE id=%s" if psql else "UPDATE bets SET status='won' WHERE id=?", (bid,))
                cursor.execute(
                    "INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,admin_id,reason) VALUES(%s,'credit',%s,%s,%s,%s,%s)" if psql
                    else "INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,admin_id,reason) VALUES(?,'credit',?,?,?,?,?)",
                    (uid,float(win),prev,nxt,admin_id,f"Vincita Virtuale #{bid}"))
                print(f"[Virtual Bets] #{bid} VINTA - {win}euro a utente {uid}")
            else:
                print(f"[Virtual Bets] #{bid} pending (selezioni su giornate future)")

        conn.commit()
        print(f"[Virtual Bets] Giornata {matchday} OK")
    except Exception as e:
        print(f"[Virtual Bets Error] {traceback.format_exc()}")
        try: conn.rollback()
        except: pass
    finally:
        conn.close()


def generate_fixtures(season_id, conn):
    cursor = conn.cursor(); psql = check_is_psql(conn)
    cursor.execute("SELECT id, name, offense, defense FROM virtual_teams")
    teams = {r[0] if psql else r["id"]: {"name":r[1] if psql else r["name"], "o":r[2] if psql else r["offense"], "d":r[3] if psql else r["defense"]} for r in cursor.fetchall()}
    tids = list(teams.keys())
    if len(tids) != 20: 
        print(f"[Virtual Fixtures] Error: Expected 20 teams, found {len(tids)}")
        return
    
    cursor.execute("SELECT value FROM settings WHERE key = 'virtual_house_edge'")
    edge_row = cursor.fetchone()
    edge = float(edge_row[0] if edge_row else 15.0)
    margin = 1.0 - (edge / 100.0)

    # Round Robin
    random.shuffle(tids)
    rounds = []
    temp = list(tids)
    for r in range(19):
        matches = [(temp[i], temp[19-i]) for i in range(10)]
        rounds.append(matches)
        temp.insert(1, temp.pop())

    for r_num, matches in enumerate(rounds):
        mday, rday = r_num + 1, r_num + 20
        for h, a in matches:
            def get_o(hid, aid):
                ht, at = teams[hid], teams[aid]
                exph = max(0.5, (ht["o"] - at["d"] + 50) / 100 * 1.5) + 0.3
                expa = max(0.4, (at["o"] - ht["d"] + 50) / 100 * 1.5)
                p1, px, p2, po, pgg = 0, 0, 0, 0, 0
                combo, exact = {}, {}
                for hg in range(7):
                    for ag in range(7):
                        prob = poisson_prob(exph, hg) * poisson_prob(expa, ag)
                        res = "1" if hg > ag else ("X" if hg == ag else "2")
                        if hg > ag: p1 += prob
                        elif hg == ag: px += prob
                        else: p2 += prob
                        if hg + ag > 2.5: po += prob
                        if hg > 0 and ag > 0: pgg += prob
                        is_gg = (hg > 0 and ag > 0); gg = "GG" if is_gg else "NG"
                        for th in [1.5, 2.5, 3.5, 4.5]:
                            tk = f"Over {th}" if (hg+ag) > th else f"Under {th}"
                            combo[f"{res}+{tk}"] = combo.get(f"{res}+{tk}", 0) + prob
                        combo[f"{res}+{gg}"] = combo.get(f"{res}+{gg}", 0) + prob
                        exact[f"{hg}-{ag}"] = exact.get(f"{hg}-{ag}", 0) + prob
                total = p1 + px + p2; p1/=total; px/=total; p2/=total
                sq = lambda p: round(max(1.05, min(99.0, (1.0/max(0.001,p))*margin)), 2)
                co = {k: sq(v) for k, v in combo.items()}
                ex_list = ["0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2","2-2","3-0","0-3","3-1","1-3","3-2","2-3"]
                eo = {s: sq(exact.get(s, 0.001)) for s in ex_list}
                # Gestione "Altro"
                eo["Altro"] = sq(max(0.01, 1.0 - sum(exact.get(s, 0) for s in ex_list)))
                return sq(p1), sq(px), sq(p2), sq(po), sq(1-po), sq(pgg), sq(1-pgg), json.dumps(co), json.dumps(eo)
            
            o_h = get_o(h, a)
            q_in = "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (%s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s, %s, %s, %s, %s)" if psql else "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            cursor.execute(q_in, (season_id, mday, h, a, o_h[0], o_h[1], o_h[2], o_h[3], o_h[4], o_h[5], o_h[6], o_h[7], o_h[8]))
            o_r = get_o(a, h)
            cursor.execute(q_in, (season_id, rday, a, h, o_r[0], o_r[1], o_r[2], o_r[3], o_r[4], o_r[5], o_r[6], o_r[7], o_r[8]))
    conn.commit()

async def run_virtual_football_loop():
    print("[Virtual] Loop Avviato.")
    try:
        init_teams()
        get_or_create_season()
    except Exception as e:
        print(f"[Virtual CRITICAL] Init Error: {e}")
        return

    while True:
        # --- BETTING ---
        engine.phase, engine.timer, engine.clock, engine.action_text = "BETTING", 120, "", "⏳ Piazza le scommesse!"
        while engine.timer > 0: 
            await asyncio.sleep(1)
            engine.timer -= 1
        
        # --- LIVE ---
        engine.phase, engine.timer, engine.clock, engine.action_text = "LIVE", 30, "0'", "🏟️ Fischio d'inizio!"
        conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
        cursor.execute("UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = %s AND matchday = %s" if psql else "UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        conn.commit()
        
        cursor.execute("SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql else "SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        matches = cursor.fetchall()
        
        # Simulazione minuti 15, 30, 45, 60, 75, 90
        intervals = {25: "15'", 20: "30'", 15: "45'", 10: "60'", 5: "75'", 2: "90'"}
        for sim in range(30, 0, -1):
            await asyncio.sleep(1); engine.timer = sim
            if sim in intervals:
                engine.clock = intervals[sim]
                engine.action_text = f"⚽ Azione pericolosa ({engine.clock})"
                for m in matches:
                    mid = m[0] if psql else m["id"]
                    hg = 1 if random.random() < 0.18 else 0
                    ag = 1 if random.random() < 0.15 else 0
                    cursor.execute("UPDATE virtual_matches SET home_score=home_score+%s, away_score=away_score+%s, current_minute=%s WHERE id=%s" if psql else "UPDATE virtual_matches SET home_score=home_score+?, away_score=away_score+?, current_minute=? WHERE id=?", (hg, ag, int(engine.clock.replace("'","")), mid))
                conn.commit()
        conn.close()
        
        # --- FINALIZING ---
        engine.phase = "FINALIZING"
        finalize_matchday(engine.current_season_id, engine.current_matchday)
        engine.finished_matchday = engine.current_matchday
        
        if engine.current_matchday >= 38:
            mark_season_finished(engine.current_season_id)
            get_or_create_season() # Nuova stagione, mday=1
        else:
            engine.current_matchday += 1
            update_season_matchday(engine.current_season_id, engine.current_matchday)
        
        # --- FINISHED ---
        engine.phase, engine.timer, engine.clock, engine.action_text = "FINISHED", 120, "FIN", f"🏆 Risultati giornata {engine.finished_matchday}"
        while engine.timer > 0: 
            await asyncio.sleep(1)
            engine.timer -= 1

@router.get("/status")
async def get_virtual_status():
    return {
        "phase": engine.phase, 
        "timer": engine.timer, 
        "matchday": engine.current_matchday, 
        "finished_matchday": engine.finished_matchday, 
        "clock": engine.clock, 
        "action_text": engine.action_text
    }

@router.get("/matches")
async def get_virtual_matches():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = """
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, 
               m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, 
               m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, 
               th.name, th.logo_url, ta.name, ta.logo_url 
        FROM virtual_matches m 
        JOIN virtual_teams th ON m.home_team_id = th.id 
        JOIN virtual_teams ta ON m.away_team_id = ta.id 
        WHERE m.season_id = %s AND m.matchday = %s
    """ if psql else """
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, 
               m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, 
               m.odds_gg, m.odds_ng, m.odds_combo, m.odds_exact, 
               th.name, th.logo_url, ta.name, ta.logo_url 
        FROM virtual_matches m 
        JOIN virtual_teams th ON m.home_team_id = th.id 
        JOIN virtual_teams ta ON m.away_team_id = ta.id 
        WHERE m.season_id = ? AND m.matchday = ?
    """
    cursor.execute(q, (engine.current_season_id, engine.current_matchday))
    rows = cursor.fetchall(); conn.close()
    res = []
    for m in rows:
        if psql:
            res.append({
                "id":m[0], "matchday":m[1], "status":m[2], "home_score":m[3], "away_score":m[4],
                "odds_1":m[5], "odds_x":m[6], "odds_2":m[7], "odds_over25":m[8], "odds_under25":m[9],
                "odds_gg":m[10], "odds_ng":m[11],
                "odds_combo":json.loads(m[12] or '{}'),
                "odds_exact":json.loads(m[13] or '{}'),
                "home_team":{"name":m[14], "logo":m[15]},
                "away_team":{"name":m[16], "logo":m[17]}
            })
        else:
            res.append({
                "id":m["id"], "matchday":m["matchday"], "status":m["status"], "home_score":m["home_score"], "away_score":m["away_score"],
                "odds_1":m["odds_1"], "odds_x":m["odds_x"], "odds_2":m["odds_2"], "odds_over25":m["odds_over25"], "odds_under25":m["odds_under25"],
                "odds_gg":m["odds_gg"], "odds_ng":m["odds_ng"],
                "odds_combo":json.loads(m["odds_combo"] or '{}'),
                "odds_exact":json.loads(m["odds_exact"] or '{}'),
                "home_team":{"name":m["name"], "logo":m["logo_url"]},
                "away_team":{"name":m["name:1"], "logo":m["logo_url:1"]}
            })
    return res

@router.get("/live")
async def get_virtual_live():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    day = engine.finished_matchday if engine.phase == 'FINISHED' else engine.current_matchday
    q = """
        SELECT m.id, m.home_score, m.away_score, th.name, ta.name 
        FROM virtual_matches m 
        JOIN virtual_teams th ON m.home_team_id = th.id 
        JOIN virtual_teams ta ON m.away_team_id = ta.id 
        WHERE m.season_id = %s AND m.matchday = %s
    """ if psql else """
        SELECT m.id, m.home_score, m.away_score, th.name, ta.name 
        FROM virtual_matches m 
        JOIN virtual_teams th ON m.home_team_id = th.id 
        JOIN virtual_teams ta ON m.away_team_id = ta.id 
        WHERE m.season_id = ? AND m.matchday = ?
    """
    cursor.execute(q, (engine.current_season_id, day))
    rows = cursor.fetchall(); conn.close()
    return [{"id":r[0], "home_score":r[1], "away_score":r[2], "home_team":{"name":r[3]}, "away_team":{"name":r[4]}} if psql else {"id":r["id"], "home_score":r["home_score"], "away_score":r["away_score"], "home_team":{"name":r["name"]}, "away_team":{"name":r["name:1"]}} for r in rows]

@router.get("/standings")
async def get_virtual_standings():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = """
        SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against 
        FROM virtual_standings s 
        JOIN virtual_teams t ON s.team_id = t.id 
        WHERE s.season_id = %s 
        ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC
    """ if psql else """
        SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against 
        FROM virtual_standings s 
        JOIN virtual_teams t ON s.team_id = t.id 
        WHERE s.season_id = ? 
        ORDER BY s.points DESC, (goals_for - goals_against) DESC
    """
    cursor.execute(q, (engine.current_season_id,))
    rows = cursor.fetchall(); conn.close()
    return [{"team_name":r[0], "logo":r[1], "points":r[2], "played":r[3], "won":r[4], "drawn":r[5], "lost":r[6], "gf":r[7], "ga":r[8]} if psql else {"team_name":r["name"], "logo":r["logo_url"], "points":r["points"], "played":r["played"], "won":r["won"], "drawn":r["drawn"], "lost":r["lost"], "gf":r["goals_for"], "ga":r["goals_against"]} for r in rows]
