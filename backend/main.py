import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List

from fastapi import FastAPI, Depends, HTTPException, Body, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from backend.auth import get_current_user, check_admin, get_password_hash, verify_password, create_access_token
from backend.database import get_db, init_db, check_is_psql
from backend.crash import crash_engine
from backend.blackjack import bj_engine
from backend.sette_mezzo import deal as sm_deal_func, hit as sm_hit_func, stand as sm_stand_func
from backend.baccarat import deal as baccarat_deal

is_postgres = os.environ.get("DATABASE_URL") is not None
app = FastAPI(title="Simus Bet Dashboard API")
odds_cache = {}
odds_lock = asyncio.Lock()

def _get_db_timestamp() -> float:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'odds_last_update'")
        row = cursor.fetchone()
        conn.close()
        if row:
            return float(row[0] if hasattr(row, '__getitem__') else row[0])
    except:
        pass
    return 0.0

def _set_db_timestamp(ts: float):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if is_postgres:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                          ('odds_last_update', str(ts), str(ts)))
        else:
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                          ('odds_last_update', str(ts)))
        conn.commit()
        conn.close()
    except:
        pass

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(crash_engine.start_loop())
    print("[Startup] Database OK")
    print("[Startup] Crash Engine started")

@app.post("/api/login")
async def login(username: str = Body(...), password: str = Body(...)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("SELECT id, password_hash, role FROM users WHERE username = %s", (username,))
    else:
        cursor.execute("SELECT id, password_hash, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not verify_password(password, row[1] if hasattr(row, '__getitem__') else row[1]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali non valide")
    
    user_id = row[0] if hasattr(row, '__getitem__') else row[0]
    role = row[2] if hasattr(row, '__getitem__') else row[2]
    
    access_token = create_access_token({"sub": username, "id": user_id, "role": role})
    return {"access_token": access_token, "token_type": "bearer", "role": role}

def save_casino_bet(conn, u_id: int, game_name: str, amount: float, payout: float):
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("INSERT INTO casino_bets (user_id, game, amount, payout, status) VALUES (%s, %s, %s, %s, 'completed')",
                      (u_id, game_name, amount, payout))
    else:
        cursor.execute("INSERT INTO casino_bets (user_id, game, amount, payout, status) VALUES (?, ?, ?, ?, 'completed')",
                      (u_id, game_name, amount, payout))
    conn.commit()

def fetch_all_settings(conn) -> Dict[str, str]:
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}

@app.get("/api/settings")
async def get_settings(user = Depends(get_current_user)):
    conn = get_db()
    settings = fetch_all_settings(conn)
    conn.close()
    return settings

@app.post("/api/settings")
async def update_settings(settings: Dict[str, str] = Body(...), admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    for key, value in settings.items():
        if is_postgres:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                          (key, value, value))
        else:
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/balance")
async def get_balance(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("SELECT balance FROM users WHERE id = %s", (user["id"],))
    else:
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user["id"],))
    row = cursor.fetchone()
    conn.close()
    balance = row[0] if row else 0
    return {"balance": balance}

@app.get("/api/users")
async def list_users(admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, balance, status FROM users")
    rows = cursor.fetchall()
    conn.close()
    users = []
    for row in rows:
        users.append({"id": row[0], "username": row[1], "role": row[2], "balance": row[3], "status": row[4]})
    return users

@app.post("/api/users")
async def create_user(data: dict, admin = Depends(check_admin)):
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username e password obbligatori")
    
    hashed = get_password_hash(password)
    conn = get_db()
    cursor = conn.cursor()
    try:
        if is_postgres:
            cursor.execute("INSERT INTO users (username, password_hash, role, balance) VALUES (%s, %s, %s, %s)",
                          (username, hashed, "user", 0))
        else:
            cursor.execute("INSERT INTO users (username, password_hash, role, balance) VALUES (?, ?, ?, ?)",
                          (username, hashed, "user", 0))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/users/{user_id}")
async def get_user_detail(user_id: int, admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("SELECT id, username, role, balance, status FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("SELECT id, username, role, balance, status FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return {"id": row[0], "username": row[1], "role": row[2], "balance": row[3], "status": row[4]}

@app.post("/api/users/{user_id}/status")
async def update_user_status(user_id: int, data: Dict[str, str] = Body(...), admin = Depends(check_admin)):
    status_val = data.get("status")
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status_val, user_id))
    else:
        cursor.execute("UPDATE users SET status = ? WHERE id = ?", (status_val, user_id))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/users/{user_id}/password")
async def update_user_password(user_id: int, data: Dict[str, str] = Body(...), admin = Depends(check_admin)):
    password = data.get("password")
    hashed = get_password_hash(password)
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user_id))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/admin/adjust-balance")
async def admin_adjust_balance(data: Dict[str, Any] = Body(...), admin = Depends(check_admin)):
    user_id = data.get("user_id")
    amount = float(data.get("amount", 0))
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    old_balance = row[0] if row else 0
    new_balance = old_balance + amount
    
    if is_postgres:
        cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id) VALUES (%s, %s, %s, %s, %s, %s)",
                      (user_id, "admin_adjustment", amount, old_balance, new_balance, admin["id"]))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, balance_before, balance_after, admin_id) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, "admin_adjustment", amount, old_balance, new_balance, admin["id"]))
    conn.commit()
    conn.close()
    return {"status": "success", "new_balance": new_balance}

@app.get("/api/bets")
async def list_all_bets(admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, amount, status FROM bets ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    bets = [{"id": r[0], "user_id": r[1], "amount": r[2], "status": r[3]} for r in rows]
    return bets

@app.get("/api/mybets")
async def get_my_bets_history(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("SELECT id, amount, status, created_at FROM bets WHERE user_id = %s ORDER BY id DESC LIMIT 50", (user["id"],))
    else:
        cursor.execute("SELECT id, amount, status, created_at FROM bets WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user["id"],))
    rows = cursor.fetchall()
    conn.close()
    bets = [{"id": r[0], "amount": r[1], "status": r[2], "date": str(r[3])} for r in rows]
    return bets

@app.post("/api/place-bet")
async def place_bet(data: dict, current_user = Depends(get_current_user)):
    return {"status": "success"}

@app.websocket("/ws/crash")
async def websocket_crash(websocket: WebSocket):
    await websocket.accept()
    crash_engine.clients.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await asyncio.sleep(0.1)
    except:
        crash_engine.clients.discard(websocket)

@app.post("/api/crash/bet")
async def place_crash_bet(amount: float = Body(..., embed=True), user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("INSERT INTO crash_bets (user_id, amount, status) VALUES (%s, %s, 'pending')", (user["id"], amount))
    else:
        cursor.execute("INSERT INTO crash_bets (user_id, amount, status) VALUES (?, ?, 'pending')", (user["id"], amount))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/crash/cashout")
async def crash_cashout(bet_id: int = Body(..., embed=True), user = Depends(get_current_user)):
    return {"status": "success"}

@app.post("/api/sm/deal")
async def sm_deal(data: dict, current_user = Depends(get_current_user)):
    bet = float(data.get("bet", 0))
    result = sm_deal_func(bet, current_user["id"])
    return result

@app.post("/api/sm/hit")
async def sm_hit(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = sm_hit_func(game_id)
    return result

@app.post("/api/sm/stand")
async def sm_stand(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = sm_stand_func(game_id)
    return result

@app.post("/api/bj/deal")
async def bj_deal(data: dict, current_user = Depends(get_current_user)):
    bet = float(data.get("bet", 0))
    result = bj_engine.start_game(current_user["id"], bet)
    return result

@app.post("/api/bj/hit")
async def bj_hit(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.hit(game_id)
    return result

@app.post("/api/bj/stand")
async def bj_stand(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.stand(game_id)
    return result

@app.post("/api/bj/split")
async def bj_split(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.split(game_id)
    return result

@app.post("/api/bj/double")
async def bj_double(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.double_down(game_id)
    return result

@app.post("/api/bj/insurance")
async def bj_insurance(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.insurance(game_id)
    return result

@app.post("/api/bj/skip-insurance")
async def bj_skip_insurance(data: dict, current_user = Depends(get_current_user)):
    game_id = data.get("game_id")
    result = bj_engine.skip_insurance(game_id)
    return result

@app.post("/api/baccarat/play")
async def play_baccarat(bets: Dict[str, float] = Body(...), user = Depends(get_current_user)):
    result = baccarat_deal(bets, user["id"])
    return result

@app.get("/api/bonuses")
async def get_bonuses(user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, bonus_percent FROM bonuses WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    bonuses = [{"id": r[0], "title": r[1], "description": r[2], "percent": r[3]} for r in rows]
    return bonuses

@app.post("/api/apply-bonus")
async def apply_bonus(data: dict, user = Depends(get_current_user)):
    return {"status": "success"}

@app.get("/api/admin/bonuses")
async def admin_get_bonuses(admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, bonus_percent, status FROM bonuses")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "percent": r[2], "status": r[3]} for r in rows]

@app.post("/api/admin/bonuses")
async def admin_create_bonus(data: dict = Body(...), admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("INSERT INTO bonuses (title, description, bonus_percent, status) VALUES (%s, %s, %s, 'active')",
                      (data.get("title"), data.get("description"), data.get("percent")))
    else:
        cursor.execute("INSERT INTO bonuses (title, description, bonus_percent, status) VALUES (?, ?, ?, 'active')",
                      (data.get("title"), data.get("description"), data.get("percent")))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/admin/bonuses/{bid}")
async def admin_delete_bonus(bid: int, admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("DELETE FROM bonuses WHERE id = %s", (bid,))
    else:
        cursor.execute("DELETE FROM bonuses WHERE id = ?", (bid,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/withdrawal")
async def request_withdrawal(data: dict, user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("INSERT INTO withdrawal_requests (user_id, username, amount, iban, holder_name, status) VALUES (%s, %s, %s, %s, %s, 'pending')",
                      (user["id"], user["username"], data.get("amount"), data.get("iban"), data.get("holder")))
    else:
        cursor.execute("INSERT INTO withdrawal_requests (user_id, username, amount, iban, holder_name, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                      (user["id"], user["username"], data.get("amount"), data.get("iban"), data.get("holder")))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/deposit")
async def request_deposit(data: dict = Body(...), user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres:
        cursor.execute("INSERT INTO deposit_requests (user_id, username, amount, status) VALUES (%s, %s, %s, 'pending')",
                      (user["id"], user["username"], data.get("amount")))
    else:
        cursor.execute("INSERT INTO deposit_requests (user_id, username, amount, status) VALUES (?, ?, ?, 'pending')",
                      (user["id"], user["username"], data.get("amount")))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/admin/deposits")
async def list_deposits(admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, username, amount, status FROM deposit_requests")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "username": r[2], "amount": r[3], "status": r[4]} for r in rows]

@app.post("/api/admin/deposits/{did}")
async def resolve_deposit(did: int, data: dict = Body(...), admin = Depends(check_admin)):
    return {"status": "success"}

@app.get("/api/admin/withdrawals")
async def list_withdrawals(admin = Depends(check_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, username, amount, status FROM withdrawal_requests")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "username": r[2], "amount": r[3], "status": r[4]} for r in rows]

@app.post("/api/admin/withdrawals/{wid}")
async def resolve_withdrawal(wid: int, data: dict = Body(...), admin = Depends(check_admin)):
    return {"status": "success"}

frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
