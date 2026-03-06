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

class VirtualEngine:
    def __init__(self):
        self.phase = "BETTING"
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
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    cursor.execute("SELECT COUNT(*) FROM virtual_teams")
    if cursor.fetchone()[0] == 0:
        for t in SERIE_A_TEAMS:
            q = "INSERT INTO virtual_teams (name, offense, defense) VALUES (%s, %s, %s)" if psql else "INSERT INTO virtual_teams (name, offense, defense) VALUES (?, ?, ?)"
            cursor.execute(q, (t["name"], t["offense"], t["defense"]))
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
        for m in cursor.fetchall():
            mid, h_id, a_id = (m[0], m[1], m[2]) if psql else (m["id"], m["home_team_id"], m["away_team_id"])
            h_g, a_g = (m[3], m[4]) if psql else (m["home_score"], m["away_score"])
            h_p, a_p = (3, 0) if h_g > a_g else ((1, 1) if h_g == a_g else (0, 3))
            
            h_w, h_d, h_l = (1, 0, 0) if h_p == 3 else ((0, 1, 0) if h_p == 1 else (0, 0, 1))
            a_w, a_d, a_l = (0, 0, 1) if h_p == 3 else ((0, 1, 0) if h_p == 1 else (1, 0, 0))

            def upd_st(tid, pts, w, d, l, gf, ga):
                par = (season_id, tid, pts, w, d, l, gf, ga)
                if psql:
                    cursor.execute("""
                        INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                        VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
                        ON CONFLICT(season_id, team_id) DO UPDATE SET
                        points = virtual_standings.points + EXCLUDED.points, played = virtual_standings.played + 1,
                        won = virtual_standings.won + EXCLUDED.won, drawn = virtual_standings.drawn + EXCLUDED.drawn,
                        lost = virtual_standings.lost + EXCLUDED.lost, goals_for = virtual_standings.goals_for + EXCLUDED.goals_for,
                        goals_against = virtual_standings.goals_against + EXCLUDED.goals_against
                    """, par)
                else:
                    cursor.execute("""
                        INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                        ON CONFLICT(season_id, team_id) DO UPDATE SET
                        points = points + excluded.points, played = played + 1,
                        won = won + excluded.won, drawn = drawn + excluded.drawn,
                        lost = lost + excluded.lost, goals_for = goals_for + excluded.goals_for,
                        goals_against = goals_against + excluded.goals_against
                    """, par)
            
            upd_st(h_id, h_p, h_w, h_d, h_l, h_g, a_g)
            upd_st(a_id, a_p, a_w, a_d, a_l, a_g, h_g)
            cursor.execute("UPDATE virtual_matches SET status = 'finished' WHERE id = %s" if psql else "UPDATE virtual_matches SET status = 'finished' WHERE id = ?", (mid,))
        
        conn.commit()
        resolve_virtual_bets(conn, season_id, matchday)
    except Exception as e:
        print(f"[Finalize Error] {e}")
    finally:
        conn.close()

def resolve_virtual_bets(conn, season_id, matchday):
    cursor = conn.cursor(); psql = check_is_psql(conn)
    
    # Get Admin ID for transaction logging
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    adm_row = cursor.fetchone()
    admin_id = adm_row[0] if adm_row else 1 # Fallback to 1 if no admin
    
    cursor.execute("SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql else "SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?", (season_id, matchday))
    results = {}
    for r in cursor.fetchall():
        mid, hg, ag = (r[0], r[1], r[2]) if psql else (r["id"], r["home_score"], r["away_score"])
        es = set()
        r1x2 = "1" if hg > ag else ("X" if hg == ag else "2")
        es.add(r1x2)
        for t in [1.5, 2.5, 3.5, 4.5]:
            lbl = f"Over {t}" if (hg+ag) > t else f"Under {t}"
            es.add(lbl); es.add(f"{r1x2}+{lbl}")
        gg_val = "Goal" if (hg>0 and ag>0) else "No Goal"
        gg_c = "GG" if (hg>0 and ag>0) else "NG"
        es.add(gg_val); es.add(f"{r1x2}+{gg_c}")
        ex = f"{hg}-{ag}"
        # Support both formats
        es.add(f"Esatto {ex}")
        es.add(ex)
        if ex not in {"0-0","1-0","0-1","1-1","2-0","0-2","2-1","1-2","2-2","3-0","0-3","3-1","1-3","3-2","2-3"}:
            es.add("Esatto Altro")
            es.add("Altro")
        results[f"v_{mid}"] = es

    # Find affected bets
    cursor.execute("SELECT bs.bet_id, bs.event_id, bs.selection FROM bet_selections bs JOIN bets b ON bs.bet_id = b.id WHERE b.status = 'pending'")
    affected_bets = set()
    for bs in cursor.fetchall():
        bid, evid, sel = (bs[0], bs[1], bs[2]) if psql else (bs["bet_id"], bs["event_id"], bs["selection"])
        if evid in results:
            # Clean selection string (remove Esatto prefix if exists for simpler check)
            clean_sel = sel.replace("Esatto ", "")
            is_winner = sel in results[evid] or clean_sel in results[evid]
            st = 'won' if is_winner else 'lost'
            cursor.execute("UPDATE bet_selections SET status = %s WHERE bet_id = %s AND event_id = %s" if psql else "UPDATE bet_selections SET status = ? WHERE bet_id = ? AND event_id = ?", (st, bid, evid))
            affected_bets.add(bid)
    
    conn.commit()
    
    # Process payout for each affected bet
    for bid in affected_bets:
        cursor.execute("SELECT user_id, potential_win, status FROM bets WHERE id = %s" if psql else "SELECT user_id, potential_win, status FROM bets WHERE id = ?", (bid,))
        b_row = cursor.fetchone()
        if not b_row or b_row[2] != 'pending': continue
        
        uid, win = (b_row[0], b_row[1]) if psql else (b_row["user_id"], b_row["potential_win"])
        
        cursor.execute("SELECT status FROM bet_selections WHERE bet_id = %s" if psql else "SELECT status FROM bet_selections WHERE bet_id = ?", (bid,))
        stats = [s[0] if psql else s["status"] for s in cursor.fetchall()]
        
        if 'lost' in stats:
            cursor.execute("UPDATE bets SET status = 'lost' WHERE id = %s" if psql else "UPDATE bets SET status = 'lost' WHERE id = ?", (bid,))
        elif all(s == 'won' for s in stats):
            # Credit balance
            cursor.execute("SELECT balance FROM users WHERE id = %s" if psql else "SELECT balance FROM users WHERE id = ?", (uid,))
            u_row = cursor.fetchone()
            if not u_row: continue
            prev = float(u_row[0])
            nxt = prev + win
            
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if psql else "UPDATE users SET balance = ? WHERE id = ?", (nxt, uid))
            cursor.execute("UPDATE bets SET status = 'won' WHERE id = %s" if psql else "UPDATE bets SET status = 'won' WHERE id = ?", (bid,))
            
            # Log transaction
            t_sql = "INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (%s, 'credit', %s, %s, %s, %s, %s)" if psql else \
                    "INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (?, 'credit', ?, ?, ?, ?, ?)"
            cursor.execute(t_sql, (uid, win, prev, nxt, admin_id, f"Vincita Virtuale #{bid}"))
            print(f"[Virtual Payout] Pagato {win}€ a user {uid} (Bet #{bid})")
            
    conn.commit()

def generate_fixtures(season_id, conn):
    cursor = conn.cursor(); psql = check_is_psql(conn)
    cursor.execute("SELECT id FROM virtual_teams"); tids = [r[0] for r in cursor.fetchall()]
    if len(tids) < 2: return
    
    random.shuffle(tids)
    num_teams = len(tids)
    num_rounds = num_teams - 1 if num_teams % 2 == 0 else num_teams
    
    for r in range(1, 40): # Generate up to 38 matchdays
        # Simplified round robin for virtual
        random.shuffle(tids)
        for i in range(0, num_teams, 2):
            h, a = tids[i], tids[i+1]
            q = "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (%s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s, %s, %s, %s, %s)" if psql else \
                "INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status, odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact) VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            
            # Static mock odds for now to avoid generation issues
            cursor.execute(q, (season_id, r, h, a, 1.9, 3.2, 3.4, 1.8, 1.9, 1.7, 2.0, '{}', '{}'))
    conn.commit()

async def run_virtual_football_loop():
    init_teams(); get_or_create_season()
    while True:
        # 1. Phase BETTING
        engine.phase, engine.timer = "BETTING", 120
        while engine.timer > 0: 
            await asyncio.sleep(1)
            engine.timer -= 1
        
        # 2. Phase LIVE
        engine.phase, engine.timer = "LIVE", 30
        conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
        cursor.execute("SELECT id FROM virtual_matches WHERE season_id = %s AND matchday = %s" if psql else "SELECT id FROM virtual_matches WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        m_ids = [r[0] for r in cursor.fetchall()]
        
        for mid in m_ids:
            # Random score
            hg, ag = random.randint(0, 3), random.randint(0, 3)
            cursor.execute("UPDATE virtual_matches SET home_score=%s, away_score=%s, status='finished' WHERE id=%s" if psql else "UPDATE virtual_matches SET home_score=?, away_score=?, status='finished' WHERE id=?", (hg, ag, mid))
        conn.commit(); conn.close()
        
        # 3. Phase FINALIZING (Process standings and payouts)
        engine.phase = "FINALIZING"
        finalize_matchday(engine.current_season_id, engine.current_matchday)
        engine.finished_matchday = engine.current_matchday
        
        # 4. Advance Matchday and Save to DB
        if engine.current_matchday >= 38:
            mark_season_finished(engine.current_season_id)
            get_or_create_season() # Creates new season and sets engine.current_matchday = 1
        else:
            engine.current_matchday += 1
            update_season_matchday(engine.current_season_id, engine.current_matchday)
        
        # 5. Phase FINISHED (Display results)
        engine.phase, engine.timer = "FINISHED", 60
        while engine.timer > 0: 
            await asyncio.sleep(1)
            engine.timer -= 1

@router.get("/status")
async def get_virtual_status():
    return {
        "phase": engine.phase, 
        "timer": engine.timer, 
        "matchday": engine.current_matchday, 
        "finished_matchday": engine.finished_matchday
    }

@router.get("/matches")
async def get_virtual_matches():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "SELECT m.id, th.name, ta.name, m.odds_1, m.odds_x, m.odds_2 FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = %s AND m.matchday = %s" if psql else "SELECT m.id, th.name, ta.name, m.odds_1, m.odds_x, m.odds_2 FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = ? AND m.matchday = ?"
    cursor.execute(q, (engine.current_season_id, engine.current_matchday))
    rows = cursor.fetchall(); conn.close()
    return [{"id":r[0], "home_team":{"name":r[1]}, "away_team":{"name":r[2]}, "odds_1":r[3], "odds_x":r[4], "odds_2":r[5]} for r in rows]

@router.get("/live")
async def get_virtual_live():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    # If in FINISHED phase, show the results of the day that just ended
    day = engine.finished_matchday if engine.phase == 'FINISHED' else engine.current_matchday
    q = "SELECT th.name, ta.name, m.home_score, m.away_score FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = %s AND m.matchday = %s" if psql else "SELECT th.name, ta.name, m.home_score, m.away_score FROM virtual_matches m JOIN virtual_teams th ON m.home_team_id = th.id JOIN virtual_teams ta ON m.away_team_id = ta.id WHERE m.season_id = ? AND m.matchday = ?"
    cursor.execute(q, (engine.current_season_id, day))
    rows = cursor.fetchall(); conn.close()
    return [{"home_team":{"name":r[0]}, "away_team":{"name":r[1]}, "home_score":r[2], "away_score":r[3]} for r in rows]

@router.get("/standings")
async def get_virtual_standings():
    conn = get_db(); cursor = conn.cursor(); psql = check_is_psql(conn)
    q = "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against FROM virtual_standings s JOIN virtual_teams t ON s.team_id = t.id WHERE s.season_id = %s ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC" if psql else \
        "SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against FROM virtual_standings s JOIN virtual_teams t ON s.team_id = t.id WHERE s.season_id = ? ORDER BY s.points DESC"
    cursor.execute(q, (engine.current_season_id,))
    rows = cursor.fetchall(); conn.close()
    return [{"team_name":r[0], "logo":r[1], "points":r[2], "played":r[3], "won":r[4], "drawn":r[5], "lost":r[6], "gf":r[7], "ga":r[8]} if psql else \
            {"team_name":r["name"], "logo":r["logo_url"], "points":r["points"], "played":r["played"], "won":r["won"], "drawn":r["drawn"], "lost":r["lost"], "gf":r["goals_for"], "ga":r["goals_against"]} for r in rows]
