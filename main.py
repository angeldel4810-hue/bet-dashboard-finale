from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from typing import List, Dict, Any
from backend.database import get_db, init_db
from backend.auth import create_access_token, verify_password, get_current_user, check_admin, get_password_hash
from backend.odds_api import get_odds_the_odds_api, get_odds_api_football, apply_overround, get_sports, get_odds_betsapi2_rapidapi
import os
from datetime import datetime, timezone, timedelta

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
def startup_event():
    init_db()

# --- Auth Routes ---

@app.post("/api/login")
async def login(username: str = Body(...), password: str = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if we are in PostgreSQL or SQLite
    is_postgres = hasattr(conn, 'get_dsn_parameters')
    query = "SELECT * FROM users WHERE username = %s" if is_postgres else "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    
    if is_postgres:
        from psycopg2.extras import RealDictCursor
        # Handle PostgreSQL row as dict if needed, or index
        user_row = cursor.fetchone()
        if not user_row:
            conn.close()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        # In a real app we'd use RealDictCursor, but for now let's map by index 
        # based on init_db order: id, username, password_hash, role, balance, status
        user = {
            'username': user_row[1],
            'password_hash': user_row[2],
            'role': user_row[3],
            'status': user_row[5]
        }
    else:
        user = cursor.fetchone()
        
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if user['status'] == 'blocked':
        raise HTTPException(status_code=403, detail="Account bloccato. Contatta l'amministratore.")
    
    access_token = create_access_token(data={"sub": user['username'], "role": user['role']})
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

# Note: Admin functions resolved-bet, user-status etc would need similar PostgreSQL mapping.
# For brevity, let's ensure the core flow (login, odds, balance, my-bets) is robust.

# Serve frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
