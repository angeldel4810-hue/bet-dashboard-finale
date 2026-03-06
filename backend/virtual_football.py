import asyncio
import random
import time
import math
import json
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
        self.finished_matchday = 0  # Giornata appena conclusa (usata nella fase FINISHED)
        self.clock = "0'"       # Minuto simulato corrente
        self.action_text = ""   # Testo azione corrente (es: "⚽ GOL - 15'")
        
engine = VirtualEngine()

def is_postgres(conn):
    return hasattr(conn, 'get_dsn_parameters')

def init_teams():
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    cursor.execute("SELECT COUNT(*) FROM virtual_teams")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("[Virtual Football] Inizializzazione 20 squadre Serie A...")
        for t in SERIE_A_TEAMS:
            if psql:
                cursor.execute("INSERT INTO virtual_teams (name, offense, defense) VALUES (%s, %s, %s)", (t["name"], t["offense"], t["defense"]))
            else:
                cursor.execute("INSERT INTO virtual_teams (name, offense, defense) VALUES (?, ?, ?)", (t["name"], t["offense"], t["defense"]))
        conn.commit()
    conn.close()

def get_or_create_season():
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    cursor.execute("SELECT id, current_matchday FROM virtual_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    season = cursor.fetchone()
    
    if not season:
        print("[Virtual Football] Creazione nuova stagione...")
        if psql:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active') RETURNING id")
            if hasattr(cursor, 'fetchone'):
               season_id = cursor.fetchone()[0]
            else:
               # fallback for some psycopg configs
               conn.commit()
               cursor.execute("SELECT id FROM virtual_seasons ORDER BY id DESC LIMIT 1")
               season_id = cursor.fetchone()[0]
        else:
            cursor.execute("INSERT INTO virtual_seasons (status) VALUES ('active')")
            season_id = cursor.lastrowid
        conn.commit()
        generate_fixtures(season_id, conn)
        engine.current_season_id = season_id
        engine.current_matchday = 1
    else:
        s_id = season[0] if psql else season["id"]
        c_m = season[1] if psql else season["current_matchday"]
        
        q = "SELECT COUNT(*) FROM virtual_matches WHERE season_id = %s" if psql else "SELECT COUNT(*) FROM virtual_matches WHERE season_id = ?"
        cursor.execute(q, (s_id,))
        count = cursor.fetchone()
        count_val = count[0] if isinstance(count, tuple) or (hasattr(count, 'keys') and 'COUNT(*)' not in count) else count.get('COUNT(*)', count[0])
        
        if count_val == 0:
            print(f"[Virtual Football] Trovata stagione " + str(s_id) + " orfana senza partite. Rigenero...")
            generate_fixtures(s_id, conn)
            engine.current_season_id = s_id
            engine.current_matchday = 1
            
            up_q = "UPDATE virtual_seasons SET current_matchday = 1 WHERE id = %s" if psql else "UPDATE virtual_seasons SET current_matchday = 1 WHERE id = ?"
            cursor.execute(up_q, (s_id,))
            conn.commit()
        else:
            engine.current_season_id = s_id
            engine.current_matchday = c_m
            
    conn.close()

def finalize_matchday(season_id, matchday):
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    # 1. Recupero match conclusi
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
        
        # 2. Aggiornamento Standings
        h_pts, a_pts = 0, 0
        h_w, h_d, h_l = 0, 0, 0
        a_w, a_d, a_l = 0, 0, 0
        
        if h_g > a_g:
            h_pts, h_w, a_l = 3, 1, 1
        elif h_g == a_g:
            h_pts, a_pts, h_d, a_d = 1, 1, 1, 1
        else:
            a_pts, a_w, h_l = 3, 1, 1
            
        def update_st(t_id, pts, w, d, l, gf, ga):
            if psql:
                cursor.execute("""
                INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
                ON CONFLICT(season_id, team_id) DO UPDATE SET
                points = virtual_standings.points + EXCLUDED.points,
                played = virtual_standings.played + 1,
                won = virtual_standings.won + EXCLUDED.won,
                drawn = virtual_standings.drawn + EXCLUDED.drawn,
                lost = virtual_standings.lost + EXCLUDED.lost,
                goals_for = virtual_standings.goals_for + EXCLUDED.goals_for,
                goals_against = virtual_standings.goals_against + EXCLUDED.goals_against
                """, (season_id, t_id, pts, w, d, l, gf, ga))
            else:
                cursor.execute("""
                INSERT INTO virtual_standings (season_id, team_id, points, played, won, drawn, lost, goals_for, goals_against)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(season_id, team_id) DO UPDATE SET
                points = virtual_standings.points + excluded.points,
                played = virtual_standings.played + 1,
                won = virtual_standings.won + excluded.won,
                drawn = virtual_standings.drawn + excluded.drawn,
                lost = virtual_standings.lost + excluded.lost,
                goals_for = virtual_standings.goals_for + excluded.goals_for,
                goals_against = virtual_standings.goals_against + excluded.goals_against
                """, (season_id, t_id, pts, w, d, l, gf, ga))
                
        update_st(h_id, h_pts, h_w, h_d, h_l, h_g, a_g)
        update_st(a_id, a_pts, a_w, a_d, a_l, a_g, h_g)
        
        if psql:
            cursor.execute("UPDATE virtual_matches SET status = 'finished' WHERE id = %s", (m_id,))
        else:
            cursor.execute("UPDATE virtual_matches SET status = 'finished' WHERE id = ?", (m_id,))
            
    # 3. Risoluzione automatica scommesse virtuali
    resolve_virtual_bets(conn, season_id, matchday)
    
    conn.commit()
    conn.close()

def resolve_virtual_bets(conn, season_id, matchday):
    try:
        from backend.database import is_postgres
        cursor = conn.cursor()
        psql = is_postgres(conn)
        
        # Recupera i risultati dei match della giornata
        if psql:
            cursor.execute("SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = %s AND matchday = %s", (season_id, matchday))
        else:
            cursor.execute("SELECT id, home_score, away_score FROM virtual_matches WHERE season_id = ? AND matchday = ?", (season_id, matchday))
        
        match_results = {}
        for r in cursor.fetchall():
            m_id = r[0] if psql else r["id"]
            h_g = r[1] if psql else r["home_score"]
            a_g = r[2] if psql else r["away_score"]
            
            # --- LOGICA CALCOLO RISULTATI ---
            results = set()
            # 1X2
            res_1x2 = "1" if h_g > a_g else ("X" if h_g == a_g else "2")
            results.add(res_1x2)
            
            # Over/Under e Combo associate
            for threshold in [1.5, 2.5, 3.5, 4.5]:
                if (h_g + a_g) > threshold:
                    results.add(f"Over {threshold}")
                    results.add(f"{res_1x2}+Over {threshold}")
                else:
                    results.add(f"Under {threshold}")
                    results.add(f"{res_1x2}+Under {threshold}")
            
            # GG/NG
            gg_str = "Goal" if (h_g > 0 and a_g > 0) else "No Goal"
            gg_combo = "GG" if (h_g > 0 and a_g > 0) else "NG"
            results.add(gg_str)
            
            # Combo 1X2 + GG/NG
            results.add(f"{res_1x2}+{gg_combo}")
            
            # Risultato Esatto
            known_exact_scores = {"0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"}
            exact_str = f"{h_g}-{a_g}"
            if exact_str in known_exact_scores:
                results.add(f"Esatto {exact_str}")
            else:
                results.add("Esatto Altro")
            # -------------------------------
            
            match_results[f"v_{m_id}"] = results

        if not match_results:
            print(f"[Virtual Resolve] Nessun match trovato per season {season_id} matchday {matchday}")
            return

        # Trova le selezioni in sospeso per questi eventi
        placeholders = ", ".join(["%s" if psql else "?" for _ in match_results.keys()])
        query = f"SELECT bs.bet_id, bs.event_id, bs.selection, b.user_id FROM bet_selections bs JOIN bets b ON bs.bet_id = b.id WHERE b.status = 'pending' AND bs.event_id IN ({placeholders})"
        cursor.execute(query, list(match_results.keys()))
        selections = cursor.fetchall()
        
        affected_bets = set()
        for s in selections:
            b_id = s[0] if psql else s["bet_id"]
            ev_id = s[1] if psql else s["event_id"]
            sel = s[2] if psql else s["selection"]
            
            is_won = sel in match_results.get(ev_id, set())
            new_status = 'won' if is_won else 'lost'
            
            if psql:
                cursor.execute("UPDATE bet_selections SET status = %s WHERE bet_id = %s AND event_id = %s", (new_status, b_id, ev_id))
            else:
                cursor.execute("UPDATE bet_selections SET status = ? WHERE bet_id = ? AND event_id = ?", (new_status, b_id, ev_id))
            affected_bets.add(b_id)

        # Verifica se le schedine sono tutte completate
        for b_id in affected_bets:
            try:
                if psql:
                    cursor.execute("SELECT status FROM bet_selections WHERE bet_id = %s", (b_id,))
                else:
                    cursor.execute("SELECT status FROM bet_selections WHERE bet_id = ?", (b_id,))
                
                all_sels = cursor.fetchall()
                statuses = [r[0] if psql else r["status"] for r in all_sels]
                
                if 'lost' in statuses:
                    # Schedina persa
                    if psql:
                        cursor.execute("UPDATE bets SET status = 'lost' WHERE id = %s", (b_id,))
                    else:
                        cursor.execute("UPDATE bets SET status = 'lost' WHERE id = ?", (b_id,))
                elif all(s == 'won' for s in statuses):
                    # Tutte vinte! Pagamento
                    if psql:
                        cursor.execute("SELECT user_id, potential_win FROM bets WHERE id = %s", (b_id,))
                    else:
                        cursor.execute("SELECT user_id, potential_win FROM bets WHERE id = ?", (b_id,))
                    b_data = cursor.fetchone()
                    u_id = b_data[0] if psql else b_data["user_id"]
                    win_amt = b_data[1] if psql else b_data["potential_win"]
                    if psql:
                        cursor.execute("UPDATE bets SET status = 'won' WHERE id = %s", (b_id,))
                        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (win_amt, u_id))
                        # Registro transazione
                        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (%s, 'credit', %s, (SELECT balance FROM users WHERE id = %s) - %s, (SELECT balance FROM users WHERE id = %s), 0, %s)", 
                                       (u_id, win_amt, u_id, win_amt, u_id, f"Vincita Virtuale Schedina #{b_id}"))
                    else:
                        cursor.execute("UPDATE bets SET status = 'won' WHERE id = ?", (b_id,))
                        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (win_amt, u_id))
                        # Registro transazione
                        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (?, 'credit', ?, (SELECT balance FROM users WHERE id = ?), (SELECT balance FROM users WHERE id = ?), 0, ?)", 
                                       (u_id, win_amt, u_id, u_id, f"Vincita Virtuale Schedina #{b_id}"))
                        cursor.execute("UPDATE transactions SET balance_before = balance_after - ? WHERE id = (SELECT last_insert_rowid())", (win_amt,))

            except Exception as e_bet:
                print(f"[Virtual Resolve] Errore risoluzione schedina {b_id}: {e_bet}")
    except Exception as e:
        print(f"[Virtual Resolve] Errore critico: {e}")

def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k)

def generate_fixtures(season_id, conn):
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    cursor.execute("SELECT id, name, offense, defense FROM virtual_teams")
    teams = cursor.fetchall()
    team_dict = {}
    team_ids = []
    
    for t in teams:
        if psql:
            team_dict[t[0]] = {"name": t[1], "offense": t[2], "defense": t[3]}
            team_ids.append(t[0])
        else:
            team_dict[t["id"]] = {"name": t["name"], "offense": t["offense"], "defense": t["defense"]}
            team_ids.append(t["id"])
            
    # Get house edge
    cursor.execute("SELECT value FROM settings WHERE key = 'virtual_house_edge'")
    row = cursor.fetchone()
    edge_pct = 15.0
    if row:
        try:
            val = row[0] if isinstance(row, tuple) or (hasattr(row, 'keys') and 'value' not in row) else row.get('value', row[0])
            edge_pct = float(val)
        except Exception:
            try:
                edge_pct = float(row[0])
            except:
                pass
    
    margin_multiplier = 1.0 - (edge_pct / 100.0)

    if len(team_ids) != 20: return
    
    random.shuffle(team_ids)
    rounds = []
    
    for r in range(19):
        matches = []
        for i in range(10):
            matches.append((team_ids[i], team_ids[19-i]))
        team_ids.insert(1, team_ids.pop())
        rounds.append(matches)
        
    def calc_odds(home_id, away_id):
        home = team_dict[home_id]
        away = team_dict[away_id]
        
        # Expected Goals
        exp_home = max(0.5, (home["offense"] - away["defense"] + 50) / 100 * 1.5) + 0.3 # home advantage
        exp_away = max(0.4, (away["offense"] - home["defense"] + 50) / 100 * 1.5)
        
        # Calculate 1X2 Probabilities max 5 goals
        p_1, p_x, p_2 = 0, 0, 0
        p_over = 0
        p_gg = 0
        for h_g in range(6):
            for a_g in range(6):
                prob = poisson_prob(exp_home, h_g) * poisson_prob(exp_away, a_g)
                if h_g > a_g: p_1 += prob
                elif h_g == a_g: p_x += prob
                else: p_2 += prob
                
                if h_g + a_g > 2.5: p_over += prob
                if h_g > 0 and a_g > 0: p_gg += prob
                
        # Normalize to 1.0
        total_1x2 = p_1 + p_x + p_2
        p_1 /= total_1x2; p_x /= total_1x2; p_2 /= total_1x2
        
        # Create quote with margin
        def safe_quote(p):
            if p <= 0: return 99.0
            q = (1.0 / p) * margin_multiplier
            return round(max(1.01, min(99.0, q)), 2)
            
        return (
            safe_quote(p_1), safe_quote(p_x), safe_quote(p_2),
            safe_quote(p_over), safe_quote(1 - p_over),
            safe_quote(p_gg), safe_quote(1 - p_gg)
        )

    def calc_extended(home_id, away_id):
        """Calcola combo odds e risultati esatti usando Poisson."""
        home = team_dict[home_id]
        away = team_dict[away_id]
        exp_home = max(0.5, (home["offense"] - away["defense"] + 50) / 100 * 1.5) + 0.3
        exp_away = max(0.4, (away["offense"] - home["defense"] + 50) / 100 * 1.5)
        
        combo = {}
        exact = {}
        
        for h_g in range(6):
            for a_g in range(6):
                prob = poisson_prob(exp_home, h_g) * poisson_prob(exp_away, a_g)
                res = "1" if h_g > a_g else ("X" if h_g == a_g else "2")
                is_gg = (h_g > 0 and a_g > 0)
                gg_str = "GG" if is_gg else "NG"
                
                # Over/Under e relative Combo (1.5, 2.5, 3.5, 4.5)
                for thr in [1.5, 2.5, 3.5, 4.5]:
                    thr_key = f"Over {thr}" if (h_g + a_g) > thr else f"Under {thr}"
                    combo[thr_key] = combo.get(thr_key, 0) + prob
                    
                    # Combo 1X2 + Over/Under
                    combo_key_ou = f"{res}+{thr_key}"
                    combo[combo_key_ou] = combo.get(combo_key_ou, 0) + prob
                
                # Combo 1X2 + GG/NG
                combo_key_gg = f"{res}+{gg_str}"
                combo[combo_key_gg] = combo.get(combo_key_gg, 0) + prob
                
                # Risultati esatti (solo i più plausibili fino a 3-3)
                exact_key = f"{h_g}-{a_g}"
                exact[exact_key] = exact.get(exact_key, 0) + prob
        
        # Converti probabilità in quote con margine
        def sq(p):
            if p <= 0.001: return None
            return round(max(1.01, min(99.0, (1.0/p) * margin_multiplier)), 2)
        
        combo_odds = {k: sq(v) for k, v in combo.items() if sq(v) is not None}
        
        known_exact_scores = ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3"]
        exact_odds = {}
        prob_known = 0
        for score in known_exact_scores:
            if score in exact:
                exact_odds[score] = sq(exact[score])
                prob_known += exact[score]
                
        # "Altro" è la probabilità rimanente
        prob_altro = max(0.001, 1.0 - prob_known)
        exact_odds["Altro"] = sq(prob_altro)
        
        return combo_odds, exact_odds

    for round_num, matches in enumerate(rounds):
        matchday = round_num + 1
        return_matchday = matchday + 19
        
        for home, away in matches:
            o1, ox, o2, o_over, o_under, o_gg, o_ng = calc_odds(home, away)
            o1_r, ox_r, o2_r, o_over_r, o_under_r, o_gg_r, o_ng_r = calc_odds(away, home)
            combo, exact = calc_extended(home, away)
            combo_r, exact_r = calc_extended(away, home)
            combo_json = json.dumps(combo)
            exact_json = json.dumps(exact)
            combo_r_json = json.dumps(combo_r)
            exact_r_json = json.dumps(exact_r)
            
            if psql:
                cursor.execute("""
                INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status,
                odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact)
                VALUES (%s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (season_id, matchday, home, away, o1, ox, o2, o_over, o_under, o_gg, o_ng, combo_json, exact_json))
                
                cursor.execute("""
                INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status,
                odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact)
                VALUES (%s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (season_id, return_matchday, away, home, o1_r, ox_r, o2_r, o_over_r, o_under_r, o_gg_r, o_ng_r, combo_r_json, exact_r_json))
            else:
                cursor.execute("""
                INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status,
                odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact)
                VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (season_id, matchday, home, away, o1, ox, o2, o_over, o_under, o_gg, o_ng, combo_json, exact_json))
                
                cursor.execute("""
                INSERT INTO virtual_matches (season_id, matchday, home_team_id, away_team_id, status,
                odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_gg, odds_ng, odds_combo, odds_exact)
                VALUES (?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (season_id, return_matchday, away, home, o1_r, ox_r, o2_r, o_over_r, o_under_r, o_gg_r, o_ng_r, combo_r_json, exact_r_json))
                
    conn.commit()


async def run_virtual_football_loop():
    print("[Virtual Football] Avvio ciclo asincrono...")
    try:
        init_teams()
        get_or_create_season()
    except Exception as e:
        import traceback
        err_msg = str(e) + " " + traceback.format_exc().replace('\n', ' ')
        engine.action_text = f"CRASH: {err_msg[:400]}"
        print("[CRITICAL] Virtual Football Loop Crashed:", traceback.format_exc())
        return
    
    BETTING_SECONDS = 120  # 2 minuti per scommettere
    LIVE_SECONDS = 30      # 30 secondi per la partita live
    FINISHED_SECONDS = 120 # 2 minuti di schermata risultati finale
    
    while True:
        # ---- FASE BETTING ----
        engine.phase = "BETTING"
        engine.timer = BETTING_SECONDS
        engine.clock = ""
        engine.action_text = "⏳ Scommetti prima del fischio!"
        
        while engine.timer > 0:
            await asyncio.sleep(1)
            engine.timer -= 1
            
        # ---- FASE LIVE ----
        engine.phase = "LIVE"
        engine.timer = LIVE_SECONDS
        engine.clock = "0'"
        engine.action_text = "🏟️ Partita iniziata! 0'"
        
        conn = get_db()
        cursor = conn.cursor()
        psql = is_postgres(conn)
        
        if psql:
            cursor.execute("UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = %s AND matchday = %s", (engine.current_season_id, engine.current_matchday))
        else:
            cursor.execute("UPDATE virtual_matches SET status = 'live', current_minute = 0, home_score = 0, away_score = 0 WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        conn.commit()
        
        cursor.execute("SELECT id, offense, defense FROM virtual_teams")
        t_rows = cursor.fetchall()
        t_rats = {}
        for tr in t_rows:
            if psql:
                t_rats[tr[0]] = {"o": tr[1], "d": tr[2]}
            else:
                t_rats[tr["id"]] = {"o": tr["offense"], "d": tr["defense"]}
                
        if psql:
            cursor.execute("SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = %s AND matchday = %s", (engine.current_season_id, engine.current_matchday))
        else:
            cursor.execute("SELECT id, home_team_id, away_team_id FROM virtual_matches WHERE season_id = ? AND matchday = ?", (engine.current_season_id, engine.current_matchday))
        active_matches = cursor.fetchall()
        conn.close()
        
        # Azioni a timer decrescente: {secondi_rimasti: (minuto_testo, azione_testo)}
        action_moments = {
            25: ("15'", "⚽ Primo quarto - 15'"),
            20: ("30'", "⚡ Metà primo tempo - 30'"),
            15: ("45'", "🔔 Fine primo tempo - 45'"),
            10: ("60'", "🔄 Inizio secondo tempo - 60'"),
             5: ("75'", "🔥 Finale incandescente - 75'"),
             2: ("90'", "⏱️ Ultimi minuti - 90'"),
        }
        
        while engine.timer > 0:
            await asyncio.sleep(1)
            engine.timer -= 1
            
            if engine.timer in action_moments:
                clock_str, action_str = action_moments[engine.timer]
                engine.clock = clock_str
                engine.action_text = action_str
                sim_minute = int(clock_str.replace("'", ""))
                
                conn = get_db()
                cursor = conn.cursor()
                
                for am in active_matches:
                    m_id = am[0] if psql else am["id"]
                    h_id = am[1] if psql else am["home_team_id"]
                    a_id = am[2] if psql else am["away_team_id"]
                    
                    exp_home = max(0.5, (t_rats[h_id]["o"] - t_rats[a_id]["d"] + 50) / 100 * 1.5) + 0.3
                    exp_away = max(0.4, (t_rats[a_id]["o"] - t_rats[h_id]["d"] + 50) / 100 * 1.5)
                    h_prob = exp_home / 6.0
                    a_prob = exp_away / 6.0
                    
                    h_goal = 1 if random.random() < h_prob else 0
                    a_goal = 1 if random.random() < a_prob else 0
                    
                    if psql:
                        cursor.execute("UPDATE virtual_matches SET home_score = home_score + %s, away_score = away_score + %s, current_minute = %s WHERE id = %s", (h_goal, a_goal, sim_minute, m_id))
                    else:
                        cursor.execute("UPDATE virtual_matches SET home_score = home_score + ?, away_score = away_score + ?, current_minute = ? WHERE id = ?", (h_goal, a_goal, sim_minute, m_id))
                
                conn.commit()
                conn.close()
        
        # ---- PAYOUT AUTOMATICO ----
        finished_matchday = engine.current_matchday
        print(f"[Virtual Football] Giornata {finished_matchday} terminata. Pagamento scommesse...")
        engine.action_text = "💰 Calcolo vincite..."
        finalize_matchday(engine.current_season_id, finished_matchday)
        
        # ---- AVANZA GIORNATA (prima di FINISHED, cosi si puo' scommettere) ----
        engine.current_matchday += 1
        if engine.current_matchday > 38:
            print("[Virtual Football] Fine Stagione! Nuova stagione...")
            engine.current_matchday = 1
            get_or_create_season()
        else:
            conn = get_db()
            cursor = conn.cursor()
            psql = is_postgres(conn)
            if psql:
                cursor.execute("UPDATE virtual_seasons SET current_matchday = %s WHERE id = %s", (engine.current_matchday, engine.current_season_id))
            else:
                cursor.execute("UPDATE virtual_seasons SET current_matchday = ? WHERE id = ?", (engine.current_matchday, engine.current_season_id))
            conn.commit()
            conn.close()
        
        # ---- FASE FINISHED (tabellone giornata conclusa, betting aperto sulla prossima) ----
        engine.finished_matchday = finished_matchday  # Salva la giornata conclusa per la UI
        engine.phase = "FINISHED"
        engine.timer = FINISHED_SECONDS
        engine.clock = "FIN"
        engine.action_text = f"🏆 Risultati Giornata {finished_matchday} - Prossima: Giornata {engine.current_matchday}"
        print(f"[Virtual Football] Risultati per {FINISHED_SECONDS}s. Giornata {engine.current_matchday} gia' aperta.")
        
        while engine.timer > 0:
            await asyncio.sleep(1)
            engine.timer -= 1

# API Endpoints per il frontend
@router.get("/status")
async def get_virtual_status():
    return {
        "phase": engine.phase,
        "timer": engine.timer,
        "matchday": engine.current_matchday,
        "season_id": engine.current_season_id,
        "clock": engine.clock,
        "action_text": engine.action_text
    }

@router.get("/live")
async def get_virtual_live():
    """Partite per il tabellone live/risultati. Durante FINISHED mostra la giornata conclusa."""
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    # Durante FINISHED mostriamo i risultati della giornata appena conclusa
    display_matchday = engine.finished_matchday if (engine.phase == 'FINISHED' and engine.finished_matchday) else engine.current_matchday
    
    if psql:
        cursor.execute("""
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute,
               th.name as home_name, ta.name as away_name
        FROM virtual_matches m
        JOIN virtual_teams th ON m.home_team_id = th.id
        JOIN virtual_teams ta ON m.away_team_id = ta.id
        WHERE m.season_id = %s AND m.matchday = %s
        """, (engine.current_season_id, display_matchday))
    else:
        cursor.execute("""
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute,
               th.name as home_name, ta.name as away_name
        FROM virtual_matches m
        JOIN virtual_teams th ON m.home_team_id = th.id
        JOIN virtual_teams ta ON m.away_team_id = ta.id
        WHERE m.season_id = ? AND m.matchday = ?
        """, (engine.current_season_id, display_matchday))
    
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for m in rows:
        if psql:
            res.append({"id": m[0], "home_score": m[3], "away_score": m[4],
                        "home_team": {"name": m[6]}, "away_team": {"name": m[7]}})
        else:
            res.append({"id": m["id"], "home_score": m["home_score"], "away_score": m["away_score"],
                        "home_team": {"name": m["home_name"]}, "away_team": {"name": m["away_name"]}})
    return res

@router.get("/matches")
async def get_virtual_matches():
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    # /matches serve SEMPRE la giornata corrente per le scommesse
    
    if psql:
        cursor.execute("""
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute,
               m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, m.odds_gg, m.odds_ng,
               m.odds_combo, m.odds_exact,
               th.name as home_name, th.logo_url as home_logo, 
               ta.name as away_name, ta.logo_url as away_logo
        FROM virtual_matches m
        JOIN virtual_teams th ON m.home_team_id = th.id
        JOIN virtual_teams ta ON m.away_team_id = ta.id
        WHERE m.season_id = %s AND m.matchday = %s
        """, (engine.current_season_id, engine.current_matchday))
    else:
        cursor.execute("""
        SELECT m.id, m.matchday, m.status, m.home_score, m.away_score, m.current_minute,
               m.odds_1, m.odds_x, m.odds_2, m.odds_over25, m.odds_under25, m.odds_gg, m.odds_ng,
               m.odds_combo, m.odds_exact,
               th.name as home_name, th.logo_url as home_logo, 
               ta.name as away_name, ta.logo_url as away_logo
        FROM virtual_matches m
        JOIN virtual_teams th ON m.home_team_id = th.id
        JOIN virtual_teams ta ON m.away_team_id = ta.id
        WHERE m.season_id = ? AND m.matchday = ?
        """, (engine.current_season_id, engine.current_matchday))
        
    matches = cursor.fetchall()
    conn.close()
    
    res = []
    for m in matches:
        if psql:
            res.append({
                "id": m[0], "matchday": m[1], "status": m[2], "home_score": m[3], "away_score": m[4], "current_minute": m[5],
                "odds_1": m[6], "odds_x": m[7], "odds_2": m[8], "odds_over25": m[9], "odds_under25": m[10], "odds_gg": m[11], "odds_ng": m[12],
                "odds_combo": json.loads(m[13] or '{}'),
                "odds_exact": json.loads(m[14] or '{}'),
                "home_team": {"name": m[15], "logo": m[16]},
                "away_team": {"name": m[17], "logo": m[18]}
            })
        else:
            res.append({
                "id": m["id"], "matchday": m["matchday"], "status": m["status"], "home_score": m["home_score"], "away_score": m["away_score"], "current_minute": m["current_minute"],
                "odds_1": m["odds_1"], "odds_x": m["odds_x"], "odds_2": m["odds_2"], "odds_over25": m["odds_over25"], "odds_under25": m["odds_under25"], "odds_gg": m["odds_gg"], "odds_ng": m["odds_ng"],
                "odds_combo": json.loads(m["odds_combo"] or '{}'),
                "odds_exact": json.loads(m["odds_exact"] or '{}'),
                "home_team": {"name": m["home_name"], "logo": m["home_logo"]},
                "away_team": {"name": m["away_name"], "logo": m["away_logo"]}
            })
    return res

@router.get("/standings")
async def get_virtual_standings():
    from backend.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    psql = is_postgres(conn)
    
    if psql:
        cursor.execute("""
        SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against
        FROM virtual_standings s
        JOIN virtual_teams t ON s.team_id = t.id
        WHERE s.season_id = %s
        ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC, s.goals_for DESC
        """, (engine.current_season_id,))
    else:
        cursor.execute("""
        SELECT t.name, t.logo_url, s.points, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against
        FROM virtual_standings s
        JOIN virtual_teams t ON s.team_id = t.id
        WHERE s.season_id = ?
        ORDER BY s.points DESC, (s.goals_for - s.goals_against) DESC, s.goals_for DESC
        """, (engine.current_season_id,))
        
    rows = cursor.fetchall()
    conn.close()
    
    standings = []
    for r in rows:
        if psql:
            standings.append({
                "team_name": r[0], "logo": r[1],
                "points": r[2], "played": r[3], "won": r[4], "drawn": r[5], "lost": r[6], "gf": r[7], "ga": r[8],
                "gd": r[7] - r[8]
            })
        else:
            standings.append({
                "team_name": r["name"], "logo": r["logo_url"],
                "points": r["points"], "played": r["played"], "won": r["won"], "drawn": r["drawn"], "lost": r["lost"], "gf": r["goals_for"], "ga": r["goals_against"],
                "gd": r["goals_for"] - r["goals_against"]
            })
    return standings
