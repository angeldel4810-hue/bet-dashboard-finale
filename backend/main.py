from fastapi import FastAPI, Depends, HTTPException, status, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from typing import List, Dict, Any
from backend.database import get_db, init_db
from backend.auth import create_access_token, verify_password, get_current_user, check_admin, get_password_hash
from backend.odds_api import get_odds_the_odds_api, get_odds_api_football, apply_overround, get_sports, get_odds_betsapi2_rapidapi
import os
import asyncio
from datetime import datetime, timezone, timedelta
from backend.crash import crash_engine
from backend.blackjack import bj_engine
import backend.sette_mezzo as sm
from backend.virtual_football import router as virtual_router, run_virtual_football_loop

is_postgres = os.environ.get("DATABASE_URL") is not None

app = FastAPI(title="Simus Bet Dashboard API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    # Avvia il loop del Crash Game in background
    asyncio.create_task(crash_engine.start_loop())
    # Avvia il loop del Calcio Virtuale in background
    asyncio.create_task(run_virtual_football_loop())

# --- Auth Routes ---

@app.post("/api/login")
async def login(username: str = Body(...), password: str = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if we are in PostgreSQL or SQLite
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    query = "SELECT * FROM users WHERE username = %s" if is_postgres else "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if is_postgres:
        user = {
            'id': user_row[0],
            'username': user_row[1],
            'password_hash': user_row[2],
            'role': user_row[3],
            'status': user_row[5]
        }
    else:
        user = dict(user_row)
        
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if user['status'] == 'blocked':
        raise HTTPException(status_code=403, detail="Account bloccato. Contatta l'amministratore.")
    
    access_token = create_access_token(data={"sub": user['username'], "role": user['role'], "id": user['id']})
    return {"access_token": access_token, "token_type": "bearer", "role": user['role']}

# Helper to fetch settings (used frequently)
def fetch_all_settings(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    if is_postgres:
        return {row[0]: row[1] for row in rows}
    return {row['key']: row['value'] for row in rows}

@app.get("/api/settings")
async def get_settings(user = Depends(get_current_user)):
    conn = get_db()
    sett = fetch_all_settings(conn)
    conn.close()
    return sett

@app.post("/api/settings", dependencies=[Depends(check_admin)])
async def update_settings(settings: Dict[str, str] = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    for key, value in settings.items():
        if is_postgres:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
        else:
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    return {"message": "Settings updated"}

@app.get("/api/odds")
async def fetch_odds(user = Depends(get_current_user)):
    conn = get_db()
    sett = fetch_all_settings(conn)
    
    source = sett.get('odds_source', 'api')
    overround = float(sett.get('overround', '5'))
    api_key = sett.get('apikey', '').strip()
    api_provider = sett.get('api_provider', 'the-odds-api')
    sports_str = sett.get('active_sports', '')
    
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')

    if source == 'manual':
        cursor.execute("SELECT * FROM manual_odds")
        rows = cursor.fetchall()
        conn.close()
        
        odds_list = []
        for r in rows:
            # Map index-based if postgres
            if is_postgres:
                o = {
                    'id': r[0], 'sport_title': r[1], 'home_team': r[2], 'away_team': r[3],
                    'commence_time': r[4], 'price_home': r[5], 'price_draw': r[6], 'price_away': r[7],
                    'price_over': r[8], 'price_under': r[9], 'price_goal': r[10], 'price_nogoal': r[11]
                }
            else:
                o = dict(r)
                
            markets = []
            h2h_outcomes = [
                {"name": o['home_team'], "price": round(o['price_home'] / (1 + overround/100), 2)},
                {"name": "Pareggio", "price": round(o['price_draw'] / (1 + overround/100), 2)} if o['price_draw'] else None,
                {"name": o['away_team'], "price": round(o['price_away'] / (1 + overround/100), 2)}
            ]
            markets.append({"key": "h2h", "outcomes": [x for x in h2h_outcomes if x]})
            if o['price_over'] and o['price_under']:
                markets.append({"key": "totals", "outcomes": [
                    {"name": "Over 2.5", "price": round(o['price_over'] / (1 + overround/100), 2)},
                    {"name": "Under 2.5", "price": round(o['price_under'] / (1 + overround/100), 2)}
                ]})
            if o['price_goal'] and o['price_nogoal']:
                 markets.append({"key": "btts", "outcomes": [
                    {"name": "Goal", "price": round(o['price_goal'] / (1 + overround/100), 2)},
                    {"name": "No Goal", "price": round(o['price_nogoal'] / (1 + overround/100), 2)}
                ]})
            odds_list.append({
                "id": o['id'],
                "sport_title": o['sport_title'],
                "home_team": o['home_team'],
                "away_team": o['away_team'],
                "commence_time": o['commence_time'],
                "bookmakers": [{"key": "manual", "title": "Manuale", "markets": markets}]
            })
        return odds_list

    conn.close()
    # API Mode follows...
    all_odds = []
    seen_ids = set()
    sports_list = sports_str.split(',') if sports_str else []
    now = datetime.now(timezone.utc)

    import asyncio
    
    async def fetch_sport_odds(sport_name):
        try:
            if api_provider == 'api-football':
                return await asyncio.to_thread(get_odds_api_football, api_key, sport_name)
            elif api_provider == 'betsapi2_rapidapi':
                return await asyncio.to_thread(get_odds_betsapi2_rapidapi, api_key, sport_name)
            else:
                return await asyncio.to_thread(get_odds_the_odds_api, api_key, sport_name)
        except Exception as e:
            print(f"Error fetching {sport_name}: {e}")
            return []

    results = await asyncio.gather(*(fetch_sport_odds(s) for s in sports_list))
    
    for odds_chunk in results:
        if not odds_chunk: continue
        for event in odds_chunk:
            event_id = event['id']
            if event_id in seen_ids: continue
            ts = event.get('commence_time', '').replace('Z', '+00:00')
            if not ts: continue
            try:
                event_time = datetime.fromisoformat(ts)
                if overround > 0:
                    for bookmaker in event.get('bookmakers', []):
                        for market in bookmaker.get('markets', []):
                            m_key = market.get('key')
                            if m_key in ['double_chance', 'draw_no_bet']: continue
                            for outcome in market.get('outcomes', []):
                                if isinstance(outcome.get('price'), (int, float)):
                                    new_price = round(outcome['price'] / (1 + overround/100), 2)
                                    outcome['price'] = max(new_price, 1.05)
                if event_time > now:
                    all_odds.append(event)
                    seen_ids.add(event_id)
            except: continue
    return all_odds

@app.post("/api/admin/manual-odds", dependencies=[Depends(check_admin)])
async def add_manual_odd(data: Dict[str, Any] = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    query = """
        INSERT INTO manual_odds (sport_title, home_team, away_team, commence_time, 
                                price_home, price_draw, price_away, 
                                price_over, price_under, price_goal, price_nogoal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """ if is_postgres else """
        INSERT INTO manual_odds (sport_title, home_team, away_team, commence_time, 
                                price_home, price_draw, price_away, 
                                price_over, price_under, price_goal, price_nogoal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor.execute(query, (data['sport_title'], data['home_team'], data['away_team'], data['commence_time'], 
          data['price_home'], data.get('price_draw'), data['price_away'],
          data.get('price_over'), data.get('price_under'), data.get('price_goal'), data.get('price_nogoal')))
    conn.commit()
    conn.close()
    return {"message": "Scommessa aggiunta"}

@app.get("/api/user/balance")
async def get_balance(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    query = "SELECT balance FROM users WHERE username = %s" if is_postgres else "SELECT balance FROM users WHERE username = ?"
    cursor.execute(query, (user['username'],))
    row = cursor.fetchone()
    conn.close()
    return {"balance": row[0] if is_postgres and row else (row['balance'] if row else 0)}

@app.get("/api/admin/users", dependencies=[Depends(check_admin)])
async def list_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, balance, status FROM users")
    rows = cursor.fetchall()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    if is_postgres:
        users = [{"id": r[0], "username": r[1], "role": r[2], "balance": r[3], "status": r[4]} for r in rows]
    else:
        users = [dict(row) for row in rows]
    conn.close()
    return users

@app.post("/api/admin/users", dependencies=[Depends(check_admin)])
async def create_user(data: dict):
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")
    balance = float(data.get("balance", 0))

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username e password obbligatori")

    hashed = get_password_hash(password)

    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')

    try:
        if is_postgres:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, balance, status) VALUES (%s, %s, %s, %s, %s)",
                (username, hashed, role, balance, 'active')
            )
        else:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, balance, status) VALUES (?, ?, ?, ?, ?)",
                (username, hashed, role, balance, 'active')
            )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Errore: username già esistente o dati non validi")

    conn.close()
    return {"message": f"Utente '{username}' creato con successo"}

@app.get("/api/admin/users/{user_id}/detail", dependencies=[Depends(check_admin)])
async def get_user_detail(user_id: int):
    try:
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')

        cursor.execute(
            "SELECT id, username, role, balance, status FROM users WHERE id = %s" if is_postgres
            else "SELECT id, username, role, balance, status FROM users WHERE id = ?",
            (user_id,)
        )
        u = cursor.fetchone()
        if not u:
            conn.close()
            raise HTTPException(status_code=404, detail="Utente non trovato")

        user_data = {
            "id": u["id"], "username": u["username"], "role": u["role"],
            "balance": float(u["balance"]), "status": u["status"],
            "created_at": datetime.now().isoformat()
        }

        cursor.execute(
            "SELECT id, user_id, amount, total_odds, potential_win, status, created_at FROM bets WHERE user_id = %s ORDER BY created_at DESC" if is_postgres
            else "SELECT id, user_id, amount, total_odds, potential_win, status, created_at FROM bets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        bets = []
        for r in cursor.fetchall():
            bet = {
                "id": r["id"], "amount": float(r["amount"]),
                "total_odds": float(r["total_odds"]), "potential_win": float(r["potential_win"]),
                "status": r["status"], "created_at": str(r["created_at"])
            }
            cursor.execute(
                "SELECT id, event_id, market, selection, odds, home_team, away_team, status FROM bet_selections WHERE bet_id = %s" if is_postgres
                else "SELECT id, event_id, market, selection, odds, home_team, away_team, status FROM bet_selections WHERE bet_id = ?",
                (bet["id"],)
            )
            sels = []
            for s in cursor.fetchall():
                sel = {
                    "id": s["id"], "event_id": s["event_id"], "market": s["market"],
                    "selection": s["selection"], "odds": float(s["odds"] or 0),
                    "home_team": s["home_team"], "away_team": s["away_team"],
                    "status": s["status"] or "pending"
                }
                if str(sel["event_id"] or "").startswith("v_"):
                    mid = str(sel["event_id"]).replace("v_", "")
                    try:
                        cursor.execute(
                            "SELECT home_score, away_score, status FROM virtual_matches WHERE id = %s" if is_postgres
                            else "SELECT home_score, away_score, status FROM virtual_matches WHERE id = ?",
                            (mid,)
                        )
                        m = cursor.fetchone()
                        if m:
                            if m["status"] == "finished":
                                sel["match_result"] = f"{m['home_score']}-{m['away_score']}"
                            elif m["status"] == "playing":
                                sel["match_result"] = "In corso"
                            else:
                                sel["match_result"] = "In attesa"
                    except Exception:
                        pass
                sels.append(sel)
            bet["selections"] = sels
            bets.append(bet)

        user_data["bets"] = bets

        try:
            cursor.execute(
                "SELECT id, type, amount, balance_before, balance_after, reason, timestamp FROM transactions WHERE user_id = %s ORDER BY timestamp DESC" if is_postgres
                else "SELECT id, type, amount, balance_before, balance_after, reason, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,)
            )
            user_data["transactions"] = [{
                "id": t["id"], "type": t["type"],
                "amount": float(t["amount"] or 0),
                "balance_before": float(t["balance_before"] or 0),
                "balance_after": float(t["balance_after"] or 0),
                "reason": t["reason"], "timestamp": str(t["timestamp"])
            } for t in cursor.fetchall()]
        except Exception as tx_err:
            print(f"Transactions error: {tx_err}")
            user_data["transactions"] = []

        conn.close()
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/users/{user_id}/status", dependencies=[Depends(check_admin)])
async def update_user_status(user_id: int, data: Dict[str, str] = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    status = data.get('status')
    cursor.execute("UPDATE users SET status = %s WHERE id = %s" if is_postgres else "UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    conn.commit()
    conn.close()
    return {"message": "Stato aggiornato"}

@app.post("/api/admin/users/{user_id}/password", dependencies=[Depends(check_admin)])
async def update_user_password(user_id: int, data: Dict[str, str] = Body(...)):
    new_pass = data.get('password')
    if not new_pass or len(new_pass) < 4:
        raise HTTPException(status_code=400, detail="Password troppo corta")
    
    hashed = get_password_hash(new_pass)
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s" if is_postgres else "UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()
    return {"message": "Password aggiornata"}

@app.post("/api/admin/balance", dependencies=[Depends(check_admin)])
async def admin_adjust_balance(data: Dict[str, Any] = Body(...), admin = Depends(get_current_user)):
    user_id = data.get('user_id')
    amount = float(data.get('amount', 0))
    reason = data.get('reason', 'Manuale')
    mode = data.get('mode', 'adjust') # adjust or set

    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')

    # Get admin ID
    cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (admin['username'],))
    admin_id = cursor.fetchone()[0]

    # Get current user balance
    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    old_balance = u_row[0]
    new_balance = (old_balance + amount) if mode == 'adjust' else amount

    # Update balance
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
    
    # Log transaction
    t_query = """INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s)""" if is_postgres else \
                 """INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) 
                 VALUES (?, ?, ?, ?, ?, ?, ? )"""
    cursor.execute(t_query, (user_id, 'admin_adjustment', new_balance - old_balance, old_balance, new_balance, admin_id, reason))

    conn.commit()
    conn.close()
    return {"new_balance": new_balance}

@app.get("/api/admin/bets", dependencies=[Depends(check_admin)])
async def list_all_bets():
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    cursor.execute("SELECT bets.*, users.username FROM bets JOIN users ON bets.user_id = users.id ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    bets_list = []
    for r in rows:
        if is_postgres:
            bet = {"id": r[0], "user_id": r[1], "amount": r[2], "total_odds": r[3], "potential_win": r[4], "status": r[5], "created_at": r[6], "username": r[7]}
        else:
            bet = dict(r)
            
        cursor.execute("SELECT * FROM bet_selections WHERE bet_id = %s" if is_postgres else "SELECT * FROM bet_selections WHERE bet_id = ?", (bet['id'],))
        s_rows = cursor.fetchall()
        if is_postgres:
            bet['selections'] = [{"id": s[0], "bet_id": s[1], "event_id": s[2], "market": s[3], "selection": s[4], "odds": s[5], "home_team": s[6], "away_team": s[7]} for s in s_rows]
        else:
            bet['selections'] = [dict(sr) for sr in s_rows]
        bets_list.append(bet)
        
    conn.close()
    return bets_list

@app.get("/api/my-bets")
async def get_my_bets_history(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    u_query = "SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?"
    cursor.execute(u_query, (user['username'],))
    u_id = cursor.fetchone()[0]
    
    b_query = "SELECT * FROM bets WHERE user_id = %s ORDER BY created_at DESC" if is_postgres else "SELECT * FROM bets WHERE user_id = ? ORDER BY created_at DESC"
    cursor.execute(b_query, (u_id,))
    rows = cursor.fetchall()
    
    bets_list = []
    for r in rows:
        if is_postgres:
            bet = {"id": r[0], "user_id": r[1], "amount": r[2], "total_odds": r[3], "potential_win": r[4], "status": r[5], "created_at": r[6]}
        else:
            bet = dict(r)
            
        s_query = "SELECT * FROM bet_selections WHERE bet_id = %s" if is_postgres else "SELECT * FROM bet_selections WHERE bet_id = ?"
        cursor.execute(s_query, (bet['id'],))
        s_rows = cursor.fetchall()
        if is_postgres:
            bet['selections'] = [{"id": s[0], "bet_id": s[1], "event_id": s[2], "market": s[3], "selection": s[4], "odds": s[5], "home_team": s[6], "away_team": s[7]} for s in s_rows]
        else:
            bet['selections'] = [dict(sr) for sr in s_rows]
        bets_list.append(bet)
        
    conn.close()
    return bets_list

@app.post("/api/bets")
async def place_bet(data: dict, current_user = Depends(get_current_user)):
    amount = float(data.get("amount", 0))
    total_odds = float(data.get("total_odds", 0))
    potential_win = float(data.get("potential_win", 0))
    selections = data.get("selections", [])

    if amount <= 0 or not selections:
        raise HTTPException(status_code=400, detail="Dati scommessa non validi")

    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')

    # Get user id and balance
    u_query = "SELECT id, balance FROM users WHERE username = %s" if is_postgres else "SELECT id, balance FROM users WHERE username = ?"
    cursor.execute(u_query, (current_user['username'],))
    u_row = cursor.fetchone()
    u_id, balance = u_row[0], u_row[1]

    if balance < amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Saldo insufficiente")

    # Deduct balance
    upd = "UPDATE users SET balance = balance - %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance - ? WHERE id = ?"
    cursor.execute(upd, (amount, u_id))

    # Insert bet
    if is_postgres:
        cursor.execute(
            "INSERT INTO bets (user_id, amount, total_odds, potential_win, status) VALUES (%s, %s, %s, %s, 'pending') RETURNING id",
            (u_id, amount, total_odds, potential_win)
        )
        bet_id = cursor.fetchone()[0]
    else:
        cursor.execute(
            "INSERT INTO bets (user_id, amount, total_odds, potential_win, status) VALUES (?, ?, ?, ?, 'pending')",
            (u_id, amount, total_odds, potential_win)
        )
        bet_id = cursor.lastrowid

    # Check if we are mixing real and virtual bets
    if selections:
        first_is_virtual = str(selections[0].get('event_id', '')).startswith('v_')
        for s in selections:
            is_virtual = str(s.get('event_id', '')).startswith('v_')
            if is_virtual != first_is_virtual:
                conn.close()
                raise HTTPException(status_code=400, detail="Non è possibile combinare scommesse reali e virtuali")

    # Insert selections
    for s in selections:
        if is_postgres:
            cursor.execute(
                "INSERT INTO bet_selections (bet_id, event_id, market, selection, odds, home_team, away_team) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (bet_id, s.get('event_id'), s.get('market'), s.get('selection'), s.get('odds'), s.get('home_team'), s.get('away_team'))
            )
        else:
            cursor.execute(
                "INSERT INTO bet_selections (bet_id, event_id, market, selection, odds, home_team, away_team) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (bet_id, s.get('event_id'), s.get('market'), s.get('selection'), s.get('odds'), s.get('home_team'), s.get('away_team'))
            )

    conn.commit()
    conn.close()
    return {"message": f"Scommessa piazzata con successo! Vincita potenziale: €{potential_win:.2f}", "bet_id": bet_id}

# --- Crash Game WebSocket ---
@app.websocket("/ws/crash")
async def websocket_crash(websocket: WebSocket):
    await websocket.accept()
    crash_engine.clients.add(websocket)
    try:
        # Invia stato iniziale
        await websocket.send_json({
            "type": "init",
            "status": crash_engine.status,
            "multiplier": crash_engine.current_multiplier,
            "history": crash_engine.history
        })
        while True:
            await websocket.receive_text() # keep-alive
    except WebSocketDisconnect:
        if websocket in crash_engine.clients:
            crash_engine.clients.remove(websocket)

@app.post("/api/crash/bet")
async def place_crash_bet(amount: float = Body(..., embed=True), user = Depends(get_current_user)):
    if amount < 0.20:
        raise HTTPException(status_code=400, detail="Scommessa minima €0.20")
    if crash_engine.status != "waiting":
        raise HTTPException(status_code=400, detail="Round già iniziato o in corso")
    
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    # Check balance
    b_query = "SELECT id, balance FROM users WHERE username = %s" if is_postgres else "SELECT id, balance FROM users WHERE username = ?"
    cursor.execute(b_query, (user['username'],))
    u_row = cursor.fetchone()
    u_id, balance = u_row[0], u_row[1]
    
    if balance < amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Saldo insufficiente")
    
    # Detract balance
    u_update = "UPDATE users SET balance = balance - %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance - ? WHERE id = ?"
    cursor.execute(u_update, (amount, u_id))
    
    # Save bet
    bet_query = "INSERT INTO crash_bets (user_id, amount, status) VALUES (%s, %s, 'pending') RETURNING id" if is_postgres else "INSERT INTO crash_bets (user_id, amount, status) VALUES (?, ?, 'pending')"
    cursor.execute(bet_query, (u_id, amount))
    bet_id = cursor.fetchone()[0] if is_postgres else cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    # Aggiungi alla lista scommesse attive del motore (per semplicità in memoria)
    crash_engine.bets.append({"id": bet_id, "user_id": u_id, "username": user['username'], "amount": amount})
    
    return {"bet_id": bet_id, "new_balance": balance - amount}

@app.post("/api/crash/cashout")
async def crash_cashout(bet_id: int = Body(..., embed=True), user = Depends(get_current_user)):
    if crash_engine.status != "running":
        raise HTTPException(status_code=400, detail="Il gioco non è in esecuzione")
    
    # Cerca la scommessa tra quelle attive
    active_bet = next((b for b in crash_engine.bets if b['id'] == bet_id and b['username'] == user['username']), None)
    if not active_bet:
        raise HTTPException(status_code=404, detail="Scommessa non trovata o già incassata")
    
    multiplier = crash_engine.current_multiplier
    payout = active_bet['amount'] * multiplier
    
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    # Update bet
    bet_update = "UPDATE crash_bets SET cashout_multiplier = %s, payout = %s, status = 'won' WHERE id = %s" if is_postgres else "UPDATE crash_bets SET cashout_multiplier = ?, payout = ?, status = 'won' WHERE id = ?"
    cursor.execute(bet_update, (multiplier, payout, bet_id))
    
    # Update balance
    u_update = "UPDATE users SET balance = balance + %s WHERE username = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE username = ?"
    cursor.execute(u_update, (payout, user['username']))
    
    conn.commit()
    conn.close()
    
    # Rimuovi scommessa dalle attive
    crash_engine.bets = [b for b in crash_engine.bets if b['id'] != bet_id]
    
    return {"message": "Cashout effettuato!", "payout": payout, "multiplier": multiplier}

# Admin Resolve Bet
@app.post("/api/admin/resolve-bet", dependencies=[Depends(check_admin)])
async def resolve_bet(data: Dict[str, Any] = Body(...)):
    bet_id = data.get('bet_id')
    status = data.get('status') # 'won' or 'lost'
    
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    cursor.execute("SELECT user_id, amount, potential_win, status FROM bets WHERE id = %s" if is_postgres else "SELECT user_id, amount, potential_win, status FROM bets WHERE id = ?", (bet_id,))
    bet = cursor.fetchone()
    if not bet:
        conn.close()
        raise HTTPException(status_code=404, detail="Scommessa non trovata")
    
    if is_postgres:
        b_user_id, b_amount, b_win, b_status = bet[0], bet[1], bet[2], bet[3]
    else:
        b_user_id, b_amount, b_win, b_status = bet['user_id'], bet['amount'], bet['potential_win'], bet['status']

    if b_status != 'pending':
        conn.close()
        raise HTTPException(status_code=400, detail="Scommessa già risolta")

    # Update bet status
    cursor.execute("UPDATE bets SET status = %s WHERE id = %s" if is_postgres else "UPDATE bets SET status = ? WHERE id = ?", (status, bet_id))
    
    if status == 'won':
        # Credit user
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (b_win, b_user_id))
    
    conn.commit()
    conn.close()
    return {"message": "Scommessa risolta", "status": status}


# --- Sette e Mezzo Endpoints ---

@app.post("/api/sette-mezzo/deal")
async def sm_deal(data: dict, current_user = Depends(get_current_user)):
    bet = float(data.get("bet", 0))
    if bet < 0.20: return JSONResponse({"error": "Scommessa minima €0.20"}, status_code=400)
    
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    u_id = current_user.get("id")
    if not u_id:
        cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
        u_id = cursor.fetchone()[0]

    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (u_id,))
    user_db = cursor.fetchone()
    balance = float(user_db["balance"])
    
    if balance < bet:
        conn.close()
        return JSONResponse({"error": "Saldo insufficiente"}, status_code=400)
    
    # Deduct bet
    new_balance = balance - bet
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, u_id))
    conn.commit()
    conn.close()
    
    result = sm.deal(bet, u_id)
    
    # Se la partita finisce subito a causa di un 7 e mezzo naturale o push
    if result["status"] in ["win_natural", "push"]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (result["payout"], u_id))
        conn.commit()
        conn.close()
        
    return result

@app.post("/api/sette-mezzo/hit")
async def sm_hit(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = sm.hit(game_id)
    return result

@app.post("/api/sette-mezzo/stand")
async def sm_stand(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = sm.stand(game_id)
    
    if result["status"] in ["win", "push"]:
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')
        
        u_id = current_user.get("id")
        if not u_id:
            cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
            u_id = cursor.fetchone()[0]
            
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (result["payout"], u_id))
        conn.commit()
        conn.close()
        
    return result

# --- Blackjack Endpoints ---
@app.post("/api/blackjack/deal")
async def bj_deal(data: dict, current_user = Depends(get_current_user)):
    bet = float(data.get("bet", 0))
    if bet < 0.20: return JSONResponse({"error": "Scommessa minima €0.20"}, status_code=400)
    
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    # Get user ID if missing from token
    u_id = current_user.get("id")
    if not u_id:
        cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
        u_id = cursor.fetchone()[0]

    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (u_id,))
    user_db = cursor.fetchone()
    balance = float(user_db["balance"])
    
    if balance < bet:
        conn.close()
        return JSONResponse({"error": "Saldo insufficiente"}, status_code=400)
    
    # Deduct bet
    new_balance = balance - bet
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, u_id))
    conn.commit()
    conn.close()
    
    result = bj_engine.start_game(u_id, bet)
    
    # If game ended immediately (e.g. win_bj or push from dealer)
    if result["status"] in ["win_bj", "win", "push"] and not result.get('insurance_available'):
        payout = bet * 2.5 if result["status"] == "win_bj" else (bet * 2 if result["status"] == "win" else bet)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        conn.close()
        
    return result

@app.post("/api/blackjack/hit")
async def bj_hit(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.hit(game_id)
    if result["status"] == "split_end" and result.get("payout", 0) > 0:
        payout = result["payout"]
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')
        
        u_id = current_user.get("id")
        if not u_id:
            cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
            u_id = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        conn.close()
    return result

@app.post("/api/blackjack/stand")
async def bj_stand(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.stand(game_id)
    
    if result["status"] in ["win", "push"]:
        payout = result["bet"] * 2 if result["status"] == "win" else result["bet"]
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')
        
        u_id = current_user.get("id")
        if not u_id:
            cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
            u_id = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        conn.close()
        
    elif result["status"] == "split_end" and result.get("payout", 0) > 0:
        payout = result["payout"]
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')
        
        u_id = current_user.get("id")
        if not u_id:
            cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
            u_id = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        conn.close()

    return result

@app.post("/api/blackjack/split")
async def bj_split(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    game = bj_engine.games.get(game_id)
    if not game:
        return JSONResponse({"error": "Gioco non trovato"}, status_code=400)
    
    bet = game['bet']
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    u_id = current_user.get("id")
    if not u_id:
        cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
        u_id = cursor.fetchone()[0]

    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (u_id,))
    user_db = cursor.fetchone()
    balance = float(user_db["balance"])
    
    if balance < bet:
        conn.close()
        return JSONResponse({"error": "Saldo insufficiente per splittare"}, status_code=400)
    
    new_balance = balance - bet
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, u_id))
    conn.commit()
    conn.close()
    
    result = bj_engine.split(game_id)
    return result

@app.post("/api/blackjack/double")
async def bj_double(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    game = bj_engine.games.get(game_id)
    if not game:
        return JSONResponse({"error": "Gioco non trovato"}, status_code=400)
    
    if 'split_hands' in game:
        bet = game['split_bets'][game['active_split_index']]
    else:
        bet = game['bet']
        
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    u_id = current_user.get("id")
    if not u_id:
        cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
        u_id = cursor.fetchone()[0]

    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (u_id,))
    user_db = cursor.fetchone()
    balance = float(user_db["balance"])
    
    if balance < bet:
        conn.close()
        return JSONResponse({"error": "Saldo insufficiente per raddoppiare"}, status_code=400)
    
    new_balance = balance - bet
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, u_id))
    conn.commit()
    
    result = bj_engine.double_down(game_id)
    if "error" in result:
        # refund the bet we just subtracted
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (bet, u_id))
        conn.commit()
        conn.close()
        return JSONResponse(result, status_code=400)

    if result.get("status") in ["win", "push"]:
        payout = result["bet"] * 2 if result["status"] == "win" else result["bet"]
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
    elif result.get("status") == "split_end" and result.get("payout", 0) > 0:
        payout = result["payout"]
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        
    conn.close()
    return result

@app.post("/api/blackjack/insurance")
async def bj_insurance(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    game = bj_engine.games.get(game_id)
    if not game:
        return JSONResponse({"error": "Gioco non trovato"}, status_code=400)
    
    ins_bet = game['bet'] / 2.0
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    
    u_id = current_user.get("id")
    if not u_id:
        cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
        u_id = cursor.fetchone()[0]

    cursor.execute("SELECT balance FROM users WHERE id = %s" if is_postgres else "SELECT balance FROM users WHERE id = ?", (u_id,))
    user_db = cursor.fetchone()
    balance = float(user_db["balance"])
    
    if balance < ins_bet:
        conn.close()
        return JSONResponse({"error": "Saldo insufficiente per assicurazione"}, status_code=400)
    
    new_balance = balance - ins_bet
    cursor.execute("UPDATE users SET balance = %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = ? WHERE id = ?", (new_balance, u_id))
    conn.commit()
    
    result = bj_engine.insurance(game_id)
    if result.get("insurance_payout"):
        payout = result["insurance_payout"]
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        
    if result["status"] in ["win", "push", "win_bj"]:
        payout = result["bet"] * 2.5 if result["status"] == "win_bj" else (result["bet"] * 2 if result["status"] == "win" else result["bet"])
        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        
    conn.close()
    return result

@app.post("/api/blackjack/skip_insurance")
async def bj_skip_insurance(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.skip_insurance(game_id)
    
    if result["status"] in ["win", "push", "win_bj"]:
        payout = result["bet"] * 2.5 if result["status"] == "win_bj" else (result["bet"] * 2 if result["status"] == "win" else result["bet"])
        conn = get_db()
        cursor = conn.cursor()
        is_postgres = hasattr(conn, 'get_dsn_parameters')
        
        u_id = current_user.get("id")
        if not u_id:
            cursor.execute("SELECT id FROM users WHERE username = %s" if is_postgres else "SELECT id FROM users WHERE username = ?", (current_user["username"],))
            u_id = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s" if is_postgres else "UPDATE users SET balance = balance + ? WHERE id = ?", (payout, u_id))
        conn.commit()
        conn.close()
        
    return result

# VIRTUAL FOOTBALL ROUTER
app.include_router(virtual_router, prefix="/api/virtual", tags=["Virtual Football"])

# Serve frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
