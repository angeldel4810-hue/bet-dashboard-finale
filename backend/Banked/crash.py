import asyncio
import random
import time
import math
from typing import List, Dict, Any
from backend.database import get_db
import json

class CrashEngine:
    def __init__(self):
        self.current_multiplier = 1.0
        self.status = "waiting"          # waiting, running, crashed
        self.bets: List[Dict[str, Any]] = []
        self.history: List[float] = []
        self.crash_point = 0.0
        self.round_id = 0
        self.start_time = 0.0
        self.clients = set()
        self._wait_end = 0.0             # timestamp fine attesa
        self._last_broadcast_mult = 0.0  # ultimo moltiplicatore broadcastato

    async def start_loop(self):
        while True:
            try:
                await self._run_round()
            except Exception as e:
                print(f"[Crash] Errore round: {e}")
                await asyncio.sleep(3)

    async def _run_round(self):
        # ── 1. WAITING (10s) ──────────────────────────────────────────
        self.status = "waiting"
        self.current_multiplier = 1.0
        self.crash_point = self._generate_crash_point()
        self.bets = []
        self._wait_end = time.monotonic() + 10.0

        # Invece di sleep(1) x 10, aspettiamo con sleep(0.25) e
        # broadcastiamo solo quando il countdown cambia di 1 secondo
        last_countdown = -1
        while True:
            remaining = self._wait_end - time.monotonic()
            if remaining <= 0:
                break
            countdown = max(1, math.ceil(remaining))
            if countdown != last_countdown:
                last_countdown = countdown
                await self.broadcast({"type": "waiting", "time": countdown})
            # Sleep breve per non bloccare l'event loop
            await asyncio.sleep(0.25)

        # ── 2. RUNNING ────────────────────────────────────────────────
        self.status = "running"
        self.start_time = time.monotonic()
        self._last_broadcast_mult = 0.0
        print(f"[Crash] Round partito. Crash point: {self.crash_point}")

        while self.status == "running":
            elapsed = time.monotonic() - self.start_time
            mult = round(1.06 ** (elapsed * 2), 2)

            if mult >= self.crash_point:
                self.status = "crashed"
                self.current_multiplier = self.crash_point
                break

            self.current_multiplier = mult

            # Broadcast SOLO se il moltiplicatore e cambiato di almeno 0.01
            if abs(mult - self._last_broadcast_mult) >= 0.01:
                self._last_broadcast_mult = mult
                await self.broadcast({"type": "running", "multiplier": mult})

            # Sleep adattivo: piu lento quando il mult cresce lentamente
            # (all'inizio ~150ms, poi si riduce per apparire piu fluido)
            sleep_ms = max(0.08, 0.15 - elapsed * 0.002)
            await asyncio.sleep(sleep_ms)

        # ── 3. CRASHED ────────────────────────────────────────────────
        print(f"[Crash] CRASH a {self.current_multiplier}x")
        self.history.append(self.current_multiplier)
        if len(self.history) > 20:
            self.history.pop(0)

        self._save_round()

        await self.broadcast({
            "type": "crashed",
            "multiplier": self.current_multiplier,
            "history": self.history
        })

        # Pausa post-crash: sleep lungo invece di loop
        await asyncio.sleep(5)

    def _generate_crash_point(self) -> float:
        house_edge = 0.03
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'crash_house_edge'")
            res = cursor.fetchone()
            if res:
                house_edge = float(res['value'] if hasattr(res, '__getitem__') else res[0]) / 100
            conn.close()
        except Exception:
            pass
        r = random.random()
        if r < house_edge:
            return 1.0
        return round((1 - house_edge) / (1 - r), 2)

    # Alias per compatibilita con codice esistente in main.py
    def generate_crash_point(self) -> float:
        return self._generate_crash_point()

    async def broadcast(self, data: dict):
        if not self.clients:
            return
        message = json.dumps(data)
        dead = set()
        for client in self.clients:
            try:
                await client.send_text(message)
            except Exception:
                dead.add(client)
        self.clients -= dead

    def _save_round(self):
        try:
            conn = get_db()
            cursor = conn.cursor()
            is_pg = hasattr(conn, 'get_dsn_parameters')
            q = "INSERT INTO crash_rounds (crash_point) VALUES (%s)" if is_pg \
                else "INSERT INTO crash_rounds (crash_point) VALUES (?)"
            cursor.execute(q, (self.current_multiplier,))

            # Marca come 'lost' tutte le puntate ancora pending (non hanno fatto cashout)
            lose_q = "UPDATE crash_bets SET status = 'lost', payout = 0 WHERE status = 'pending'" 
            cursor.execute(lose_q)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Crash] Errore salvataggio round: {e}")

    # Alias per compatibilita
    def save_round_to_db(self):
        self._save_round()


crash_engine = CrashEngine()
