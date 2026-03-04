import asyncio
import random
import time
from typing import List, Dict, Any
from backend.database import get_db
import json

class CrashEngine:
    def __init__(self):
        self.current_multiplier = 1.0
        self.status = "waiting" # waiting, running, crashed
        self.bets: List[Dict[str, Any]] = []
        self.history: List[float] = []
        self.crash_point = 0.0
        self.round_id = 0
        self.start_time = 0
        self.clients = set()

    async def start_loop(self):
        while True:
            # 1. Periodo di attesa (Puntate aperte)
            self.status = "waiting"
            self.current_multiplier = 1.0
            self.crash_point = self.generate_crash_point()
            print(f"Nuovo round Crash in preparazione. Crash point previsto: {self.crash_point}")
            
            # Reset scommesse per il nuovo round
            self.bets = []
            
            # Aspetta 10 secondi per le puntate
            for i in range(10, 0, -1):
                await self.broadcast({"type": "waiting", "time": i})
                await asyncio.sleep(1)

            # 2. Inizio Round
            self.status = "running"
            self.start_time = time.time()
            print("Round Crash partito!")

            while self.status == "running":
                elapsed = time.time() - self.start_time
                # Formula per la crescita del moltiplicatore (esponenziale)
                # 1.06^t è una crescita classica
                self.current_multiplier = round(1.06 ** (elapsed * 2), 2)

                if self.current_multiplier >= self.crash_point:
                    self.status = "crashed"
                    self.current_multiplier = self.crash_point
                    break
                
                await self.broadcast({
                    "type": "running", 
                    "multiplier": self.current_multiplier
                })
                # Aggiornamento ogni 100ms per fluidità
                await asyncio.sleep(0.1)

            # 3. Crash e Salvataggio
            print(f"CRASH a {self.current_multiplier}!")
            self.history.append(self.current_multiplier)
            if len(self.history) > 20: self.history.pop(0)
            
            # Qui andrebbe il salvataggio su DB del round
            self.save_round_to_db()

            await self.broadcast({
                "type": "crashed", 
                "multiplier": self.current_multiplier,
                "history": self.history
            })
            
            # Pausa dopo il crash
            await asyncio.sleep(5)

    def generate_crash_point(self) -> float:
        # Recupera house edge dinamico dal DB
        house_edge = 0.03 # Default fallback 3%
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'crash_house_edge'")
            res = cursor.fetchone()
            if res:
                # Valore nel DB è in percentuale (es. "3" -> 0.03)
                house_edge = float(res[0] if isinstance(res, tuple) else res['value']) / 100
            conn.close()
        except:
            pass

        r = random.random()
        if r < house_edge: return 1.0 # Crash immediato
        return round((1 - house_edge) / (1 - r), 2)

    async def broadcast(self, data: dict):
        if not self.clients: return
        message = json.dumps(data)
        # Invio a tutti i client WebSocket connessi
        to_remove = []
        for client in self.clients:
            try:
                await client.send_text(message)
            except:
                to_remove.append(client)
        for client in to_remove:
            self.clients.remove(client)

    def save_round_to_db(self):
        try:
            conn = get_db()
            cursor = conn.cursor()
            is_postgres = hasattr(conn, 'get_dsn_parameters')
            query = "INSERT INTO crash_rounds (crash_point) VALUES (%s)" if is_postgres else "INSERT INTO crash_rounds (crash_point) VALUES (?)"
            cursor.execute(query, (self.current_multiplier,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Errore salvataggio round: {e}")

# Istanza globale del motore
crash_engine = CrashEngine()
