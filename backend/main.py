from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from typing import List, Dict, Any
from .database import get_db, init_db
from .auth import create_access_token, verify_password, get_current_user, check_admin, get_password_hash
from .odds_api import get_odds_the_odds_api, get_odds_api_football, apply_overround, get_sports, get_odds_betsapi2_rapidapi
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
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        # Se è l'admin di default e non c'è nel DB, verificalo comunque per sicurezza
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if user['status'] == 'blocked':
        raise HTTPException(status_code=403, detail="Account bloccato. Contatta l'amministratore.")
    
    access_token = create_access_token(data={"sub": user['username'], "role": user['role']})
    return {"access_token": access_token, "token_type": "bearer", "role": user['role']}

# --- Settings & Odds ---

@app.get("/api/settings")
async def get_settings(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    sett = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return sett

@app.post("/api/settings", dependencies=[Depends(check_admin)])
async def update_settings(settings: Dict[str, str] = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    for key, value in settings.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    return {"message": "Settings updated"}

@app.get("/api/odds")
async def fetch_odds(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM settings WHERE key = 'odds_source'")
    source = cursor.fetchone()['value']
    
    cursor.execute("SELECT value FROM settings WHERE key = 'overround'")
    overround = float(cursor.fetchone()['value'])
    
    cursor.execute("SELECT value FROM settings WHERE key = 'apikey'")
    api_key_res = cursor.fetchone()
    api_key = api_key_res['value'].strip() if api_key_res else ""
    
    if source == 'manual':
        cursor.execute("SELECT * FROM manual_odds")
        odds = [dict(row) for row in cursor.fetchall()]
        conn.close()
        formatted = []
        for o in odds:
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
            formatted.append({
                "id": o['id'],
                "sport_title": o['sport_title'],
                "home_team": o['home_team'],
                "away_team": o['away_team'],
                "commence_time": o['commence_time'],
                "bookmakers": [{"key": "manual", "title": "Manuale", "markets": markets}]
            })
        return formatted

    # API Mode
    cursor.execute("SELECT value FROM settings WHERE key = 'active_sports'")
    active_sports_res = cursor.fetchone()
    sports_str = active_sports_res['value'] if active_sports_res else ""
    
    cursor.execute("SELECT value FROM settings WHERE key = 'api_provider'")
    api_provider_res = cursor.fetchone()
    api_provider = api_provider_res['value'] if api_provider_res else "the-odds-api"
    
    conn.close()

    all_odds = []
    seen_ids = set()
    sports_list = sports_str.split(',')
    now = datetime.now(timezone.utc)

    import asyncio
    
    async def fetch_sport_odds(sport_name):
        try:
            if api_provider == 'api-football':
                # Use to_thread because requests is blocking
                return await asyncio.to_thread(get_odds_api_football, api_key, sport_name)
            elif api_provider == 'betsapi2_rapidapi':
                return await asyncio.to_thread(get_odds_betsapi2_rapidapi, api_key, sport_name)
            else:
                return await asyncio.to_thread(get_odds_the_odds_api, api_key, sport_name)
        except Exception as e:
            print(f"Error fetching {sport_name}: {e}")
            return []

    # Fetch all sports in parallel
    results = await asyncio.gather(*(fetch_sport_odds(s) for s in sports_list))
    
    for odds_chunk in results:
        if not odds_chunk: continue
        try:
            # SPOSTATO: NON applichiamo apply_overround a tutto indiscriminatamente perché 
            # uccide le quote basse (come Doppia Chance 1.20 -> 1.00 -> sparisce dal sito)
            for event in odds_chunk:
                event_id = event['id']
                if event_id in seen_ids: continue
                ts = event.get('commence_time', '').replace('Z', '+00:00')
                if not ts: continue
                event_time = datetime.fromisoformat(ts)
                
                # Applichiamo l'overround solo se necessario e con cautela
                if overround > 0:
                    for bookmaker in event.get('bookmakers', []):
                        for market in bookmaker.get('markets', []):
                            m_key = market.get('key')
                            # Esentiamo la Doppia Chance e Draw No Bet dall'overround 
                            # perché hanno già margini bassi e rischiano di sparire (quota 1.00)
                            if m_key in ['double_chance', 'draw_no_bet']:
                                continue
                                
                            for outcome in market.get('outcomes', []):
                                if isinstance(outcome.get('price'), (int, float)):
                                    # Applichiamo l'overround ma garantiamo una quota minima di 1.05
                                    new_price = round(outcome['price'] / (1 + overround/100), 2)
                                    outcome['price'] = max(new_price, 1.05)
                
                if event_time > now:
                    all_odds.append(event)
                    seen_ids.add(event_id)
        except Exception as e:
            print(f"Error processing odds chunk: {e}")
    
    print(f"Total Matches Loaded Parallel ({api_provider}): {len(all_odds)}")
    return all_odds

# --- Manual Odds CRUD (Admin) ---

@app.post("/api/admin/manual-odds", dependencies=[Depends(check_admin)])
async def add_manual_odd(data: Dict[str, Any] = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO manual_odds (sport_title, home_team, away_team, commence_time, 
                                price_home, price_draw, price_away, 
                                price_over, price_under, price_goal, price_nogoal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['sport_title'], data['home_team'], data['away_team'], data['commence_time'], 
          data['price_home'], data.get('price_draw'), data['price_away'],
          data.get('price_over'), data.get('price_under'), data.get('price_goal'), data.get('price_nogoal')))
    conn.commit()
    conn.close()
    return {"message": "Scommessa aggiunta"}

@app.delete("/api/admin/manual-odds/{odd_id}", dependencies=[Depends(check_admin)])
async def delete_manual_odd(odd_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM manual_odds WHERE id = ?", (odd_id,))
    conn.commit()
    conn.close()
    return {"message": "Scommessa eliminata"}

# --- User Management & Balance ---

@app.get("/api/user/balance")
async def get_balance(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (user['username'],))
    res = cursor.fetchone()
    conn.close()
    return {"balance": res['balance'] if res else 0}

@app.get("/api/admin/users", dependencies=[Depends(check_admin)])
async def list_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, balance, status FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

@app.post("/api/admin/users", dependencies=[Depends(check_admin)])
async def create_new_user(data: Dict[str, Any] = Body(...)):
    username = data['username']
    password = data['password']
    role = data.get('role', 'user')
    conn = get_db()
    cursor = conn.cursor()
    hashed = get_password_hash(password)
    try:
        cursor.execute("INSERT INTO users (username, password_hash, role, balance) VALUES (?, ?, ?, 0)", 
                       (username, hashed, role))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail="Utente già esistente o errore dati")
    conn.close()
    return {"message": "Utente creato con successo"}

@app.delete("/api/admin/users/{user_id}", dependencies=[Depends(check_admin)])
async def delete_system_user(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND username != 'admin'", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "Utente eliminato"}

@app.post("/api/admin/balance", dependencies=[Depends(check_admin)])
async def adjust_user_balance(data: Dict[str, Any] = Body(...), admin: dict = Depends(check_admin)):
    user_id = data['user_id']
    amount = float(data['amount'])
    conn = get_db()
    cursor = conn.cursor()
    # Get balance before
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    balance_before = cursor.fetchone()['balance']
    # Update balance
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    # Get balance after
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    balance_after = cursor.fetchone()['balance']
    # Log transaction
    cursor.execute("SELECT id FROM users WHERE username = ?", (admin['username'],))
    admin_id = cursor.fetchone()['id']
    cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, 'admin_adjustment', amount, balance_before, balance_after, admin_id, data.get('reason', 'Balance adjustment')))
    conn.commit()
    conn.close()
    return {"message": "Saldo aggiornato"}

# --- Betting System ---

@app.post("/api/bets")
async def place_bet_handler(data: Dict[str, Any] = Body(...), user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, balance, status FROM users WHERE username = ?", (user['username'],))
    db_user = cursor.fetchone()
    
    if db_user['status'] == 'blocked':
        conn.close()
        raise HTTPException(status_code=403, detail="Account bloccato. Impossibile scommettere.")
        
    amount = float(data['amount'])
    if db_user['balance'] < amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Saldo insufficiente!")
    
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, db_user['id']))
    cursor.execute("INSERT INTO bets (user_id, amount, total_odds, potential_win) VALUES (?, ?, ?, ?)", 
                   (db_user['id'], amount, data['total_odds'], data['potential_win']))
    bet_id = cursor.lastrowid
    for sel in data['selections']:
        cursor.execute("INSERT INTO bet_selections (bet_id, event_id, market, selection, odds, home_team, away_team) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                       (bet_id, sel['event_id'], sel['market'], sel['selection'], sel['odds'], sel['home_team'], sel['away_team']))
    conn.commit()
    conn.close()
    return {"message": "Scommessa piazzata!", "bet_id": bet_id}

@app.get("/api/admin/all-bets", dependencies=[Depends(check_admin)])
async def get_all_bets_admin():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT b.*, u.username FROM bets b JOIN users u ON b.user_id = u.id ORDER BY b.created_at DESC")
    bets_list = [dict(row) for row in cursor.fetchall()]
    for bet in bets_list:
        cursor.execute("SELECT * FROM bet_selections WHERE bet_id = ?", (bet['id'],))
        bet['selections'] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bets_list

@app.post("/api/admin/resolve-bet", dependencies=[Depends(check_admin)])
async def resolve_bet_admin(data: Dict[str, Any] = Body(...), admin: dict = Depends(check_admin)):
    bet_id = data['bet_id']
    status = data['status']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, potential_win, user_id, amount FROM bets WHERE id = ?", (bet_id,))
    bet = cursor.fetchone()
    
    if not bet:
        conn.close()
        return {"error": "Scommessa non trovata"}
    
    # Se la scommessa era già stata risolta (admin force resolve overrides previous ones for flexibility, except cancelled)
    # Per semplicità, permettiamo ad admin di forzare sempre lo status, facendo il ricalcolo del saldo
    
    current_status = bet['status']
    user_id = bet['user_id']
    amount = bet['amount']
    potential_win = bet['potential_win']
    
    if current_status == status:
        conn.close()
        return {"error": f"Scommessa già in stato {status}"}

    cursor.execute("SELECT id FROM users WHERE username = ?", (admin['username'],))
    admin_id = cursor.fetchone()['id']

    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    user_current_balance = cursor.fetchone()['balance']
    
    # 1. Revert previous state if it was already processed
    balance_change = 0
    if current_status == 'won':
        balance_change -= potential_win
    elif current_status == 'cancelled':
        # Se era cancellata, i soldi erano stati ridati. Ora li togliamo di nuovo
        balance_change -= amount
        
    # 2. Apply new state
    log_type = ''
    reason = ''
    if status == 'won':
        balance_change += potential_win
        log_type = 'win'
        reason = f"Forced win per scommessa #{bet_id}"
    elif status == 'lost':
        log_type = 'admin_adjustment'
        reason = f"Forced loss per scommessa #{bet_id}"
    elif status == 'cancelled':
        balance_change += amount
        log_type = 'refund'
        reason = f"Annullata scommessa #{bet_id}"

    # Eseguiamo gli aggiornamenti
    cursor.execute("UPDATE bets SET status = ? WHERE id = ?", (status, bet_id))
    
    if balance_change != 0:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (balance_change, user_id))
        
        # Log transaction only if balance changes
        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, log_type, balance_change, user_current_balance, user_current_balance + balance_change, admin_id, reason))

    conn.commit()
    conn.close()
    return {"message": f"Scommessa segnata come {status}"}

# --- New Admin User Detail & Status ---

@app.get("/api/admin/users/{user_id}/detail", dependencies=[Depends(check_admin)])
async def get_user_detail(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    # User info
    cursor.execute("SELECT id, username, balance, status, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user_dict = dict(user)
    
    # Bets history
    cursor.execute("SELECT * FROM bets WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    bets = [dict(row) for row in cursor.fetchall()]
    for bet in bets:
        cursor.execute("SELECT * FROM bet_selections WHERE bet_id = ?", (bet['id'],))
        bet['selections'] = [dict(row) for row in cursor.fetchall()]
    user_dict['bets'] = bets
        
    # Transactions history
    cursor.execute("SELECT t.*, a.username as admin_username FROM transactions t LEFT JOIN users a ON t.admin_id = a.id WHERE t.user_id = ? ORDER BY t.timestamp DESC", (user_id,))
    transactions = [dict(row) for row in cursor.fetchall()]
    user_dict['transactions'] = transactions

    conn.close()
    return user_dict

@app.post("/api/admin/users/{user_id}/status", dependencies=[Depends(check_admin)])
async def update_user_status(user_id: int, data: Dict[str, Any] = Body(...)):
    new_status = data['status']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE id = ? AND username != 'admin'", (new_status, user_id))
    conn.commit()
    conn.close()
    return {"message": f"Stato aggiornato a {new_status}"}

@app.post("/api/admin/users/{user_id}/password", dependencies=[Depends(check_admin)])
async def change_user_password(user_id: int, data: Dict[str, Any] = Body(...)):
    new_password = data['password']
    conn = get_db()
    cursor = conn.cursor()
    hashed = get_password_hash(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()
    return {"message": "Password modificata con successo"}

@app.get("/api/my-bets")
async def get_my_bets_history(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (user['username'],))
    u_id = cursor.fetchone()['id']
    cursor.execute("SELECT * FROM bets WHERE user_id = ? ORDER BY created_at DESC", (u_id,))
    my_bets = [dict(row) for row in cursor.fetchall()]
    for bet in my_bets:
        cursor.execute("SELECT * FROM bet_selections WHERE bet_id = ?", (bet['id'],))
        bet['selections'] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return my_bets

@app.get("/api/sports", dependencies=[Depends(check_admin)])
async def list_available_sports_handler():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'apikey'")
    api_key_res = cursor.fetchone()
    api_key = api_key_res['value'].strip() if api_key_res else ""
    conn.close()
    return get_sports(api_key)

# Serve frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
