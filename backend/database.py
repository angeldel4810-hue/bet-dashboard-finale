import os
import sqlite3
import threading
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")

class PgRow:
    def __init__(self, row, description):
        self._data = list(row) if row else []
        self._keys = [d[0] for d in description] if description else []
        self._dict = dict(zip(self._keys, self._data))
    def __getitem__(self, key):
        if isinstance(key, int): return self._data[key]
        return self._dict[key]
    def __contains__(self, key): return key in self._dict
    def get(self, key, default=None): return self._dict.get(key, default)
    def keys(self): return self._keys
    def __bool__(self): return bool(self._data)

class PgCursorWrapper:
    def __init__(self, cursor): self._cur = cursor
    def execute(self, q, p=None):
        if p is None: self._cur.execute(q)
        else: self._cur.execute(q, p)
        return self
    def executemany(self, q, p): return self._cur.executemany(q, p)
    def fetchone(self):
        row = self._cur.fetchone()
        if row is None: return None
        return PgRow(row, self._cur.description)
    def fetchall(self):
        return [PgRow(r, self._cur.description) for r in self._cur.fetchall()]
    def __getattr__(self, name): return getattr(self._cur, name)

class PgConnWrapper:
    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool
        self._closed = False
    def cursor(self): return PgCursorWrapper(self._conn.cursor())
    def commit(self): self._conn.commit()
    def rollback(self):
        try: self._conn.rollback()
        except Exception: pass
    def close(self):
        if self._closed: return
        self._closed = True
        if self._pool:
            self._pool._putconn(self._conn)
        else:
            try: self._conn.close()
            except Exception: pass
    def get_dsn_parameters(self): return self._conn.get_dsn_parameters()
    def __enter__(self): return self
    def __exit__(self, exc_type, *_):
        if exc_type: self.rollback()
        self.close()
    def __getattr__(self, name): return getattr(self._conn, name)

class _PgPool:
    def __init__(self, dsn, maxconn=8):
        import psycopg2
        self._dsn = dsn
        self._max = maxconn
        self._lock = threading.Lock()
        self._free = []
        self._used = 0
        for _ in range(2):
            try: self._free.append(psycopg2.connect(dsn))
            except Exception as e: print(f"[Pool] warn: {e}")

    def _getconn(self):
        import psycopg2
        with self._lock:
            self._free = [c for c in self._free if not c.closed]
            if self._free:
                conn = self._free.pop()
                self._used += 1
                return conn
            if self._used < self._max:
                conn = psycopg2.connect(self._dsn)
                self._used += 1
                return conn
        return psycopg2.connect(self._dsn)

    def _putconn(self, conn):
        with self._lock:
            self._used = max(0, self._used - 1)
            try:
                if conn.closed: return
                if conn.status != 0: conn.rollback()
                if len(self._free) < self._max:
                    self._free.append(conn)
                    return
            except Exception: pass
            try: conn.close()
            except Exception: pass

_pool: _PgPool | None = None

def _get_pool():
    global _pool
    if _pool is None and DATABASE_URL:
        _pool = _PgPool(DATABASE_URL, maxconn=8)
    return _pool

def get_db():
    if DATABASE_URL:
        pool = _get_pool()
        conn = pool._getconn()
        return PgConnWrapper(conn, pool)
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

@contextmanager
def db_conn():
    conn = get_db()
    try:
        yield conn
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise
    finally:
        try: conn.close()
        except Exception: pass

def check_is_psql(conn):
    return hasattr(conn, 'get_dsn_parameters')

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    if psql:
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT DEFAULT 'user', balance REAL DEFAULT 0, status TEXT DEFAULT 'active')""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bets (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), amount REAL NOT NULL, total_odds REAL NOT NULL, potential_win REAL NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bet_selections (id SERIAL PRIMARY KEY, bet_id INTEGER REFERENCES bets(id), event_id TEXT, market TEXT, selection TEXT, odds REAL, home_team TEXT, away_team TEXT, status TEXT DEFAULT 'pending')""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), type TEXT, amount NUMERIC, balance_before NUMERIC, balance_after NUMERIC, admin_id INTEGER DEFAULT NULL, reason TEXT, timestamp TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS manual_odds (id SERIAL PRIMARY KEY, sport_title TEXT, home_team TEXT, away_team TEXT, commence_time TEXT, price_home REAL, price_draw REAL, price_away REAL, price_over REAL, price_under REAL, price_goal REAL, price_nogoal REAL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS crash_bets (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), amount REAL, cashout_multiplier REAL, payout REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS crash_rounds (id SERIAL PRIMARY KEY, crash_point REAL, created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE, offense INTEGER DEFAULT 70, defense INTEGER DEFAULT 70, logo_url TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_seasons (id SERIAL PRIMARY KEY, status TEXT DEFAULT 'active', current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_matches (id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id), matchday INTEGER, home_team_id INTEGER REFERENCES virtual_teams(id), away_team_id INTEGER REFERENCES virtual_teams(id), home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0, status TEXT DEFAULT 'scheduled', current_minute INTEGER DEFAULT 0, odds_1 REAL, odds_x REAL, odds_2 REAL, odds_over25 REAL, odds_under25 REAL, odds_gg REAL, odds_ng REAL, odds_combo TEXT, odds_exact TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bonuses (id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT, min_deposit REAL DEFAULT 0, max_deposit REAL DEFAULT 0, bonus_percent INTEGER DEFAULT 0, bonus_fixed REAL DEFAULT 0, active BOOLEAN DEFAULT TRUE, assigned_to_user_id INTEGER DEFAULT NULL, created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_bonuses (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), bonus_id INTEGER REFERENCES bonuses(id), applied_amount REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS withdrawal_requests (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), username TEXT, amount REAL, iban TEXT, holder_name TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS deposit_requests (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), username TEXT, amount REAL, bonus_id INTEGER DEFAULT NULL, bonus_amount REAL DEFAULT 0, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_standings (id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id), team_id INTEGER REFERENCES virtual_teams(id), points INTEGER DEFAULT 0, played INTEGER DEFAULT 0, won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0, goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0, UNIQUE(season_id, team_id))""")

        # ── CRITICAL MIGRATIONS (fix retroattivo per DB esistenti su Render) ──
        # Rimuove foreign key su admin_id: causa errore perche 0/NULL non e in users
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_admin_id_fkey; EXCEPTION WHEN others THEN NULL; END $$""")
        # Rimuove NOT NULL e imposta DEFAULT NULL su admin_id
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions ALTER COLUMN admin_id DROP NOT NULL; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions ALTER COLUMN admin_id SET DEFAULT NULL; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions ALTER COLUMN amount TYPE NUMERIC USING amount::NUMERIC; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions ALTER COLUMN balance_before TYPE NUMERIC USING balance_before::NUMERIC; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE transactions ALTER COLUMN balance_after TYPE NUMERIC USING balance_after::NUMERIC; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE bonuses ADD COLUMN IF NOT EXISTS assigned_to_user_id INTEGER DEFAULT NULL; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE bonuses ADD COLUMN IF NOT EXISTS max_deposit REAL DEFAULT 0; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE deposit_requests ADD COLUMN IF NOT EXISTS bonus_id INTEGER DEFAULT NULL; EXCEPTION WHEN others THEN NULL; END $$""")
        cursor.execute("""DO $$ BEGIN ALTER TABLE deposit_requests ADD COLUMN IF NOT EXISTS bonus_amount REAL DEFAULT 0; EXCEPTION WHEN others THEN NULL; END $$""")

        for k, v in [('overround','5'),('odds_source','manual'),('apikey',''),('api_provider','the-odds-api'),('active_sports','soccer_serie_a,soccer_epl,soccer_uefa_champs_league,soccer_spain_la_liga,soccer_germany_bundesliga,soccer_france_ligue_one,soccer_italy_serie_b,soccer_usa_mls,soccer_brazil_campeonato,soccer_portugal_primeira_liga,soccer_netherlands_eredivisie,soccer_uefa_europa_league,soccer_turkey_super_league,soccer_argentina_primera_division,soccer_italy_serie_c,soccer_uefa_europa_conference_league,soccer_italy_coppa_italia'),('crash_house_edge','3'),('virtual_house_edge','15'),('virtual_pay_mode','auto')]:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (k, v))

        # Migration: aggiorna active_sports se mancano leghe importanti
        cursor.execute("SELECT value FROM settings WHERE key = 'active_sports'")
        row = cursor.fetchone()
        current_sports = (row[0] if row else '') or ''
        # Aggiorna se vuoto, invalido, o mancano leghe chiave
        needs_update = (
            not current_sports.strip()
            or not any(kw in current_sports.lower() for kw in ['soccer','football'])
            or 'soccer_serie_a' not in current_sports
            or 'soccer_epl' not in current_sports
            or 'soccer_italy_serie_c' not in current_sports
            or 'soccer_uefa_europa_conference_league' not in current_sports
        )
        if needs_update:
            new_val = 'soccer_serie_a,soccer_epl,soccer_uefa_champs_league,soccer_spain_la_liga,soccer_germany_bundesliga,soccer_france_ligue_one,soccer_italy_serie_b,soccer_usa_mls,soccer_brazil_campeonato,soccer_portugal_primeira_liga,soccer_netherlands_eredivisie,soccer_uefa_europa_league,soccer_turkey_super_league,soccer_argentina_primera_division,soccer_italy_serie_c,soccer_uefa_europa_conference_league,soccer_italy_coppa_italia'
            cursor.execute("UPDATE settings SET value = %s WHERE key = 'active_sports'", (new_val,))
            print(f"[DB] active_sports aggiornato")

        import bcrypt as _bcrypt
        admin_hash = _bcrypt.hashpw('admin123'.encode(), _bcrypt.gensalt()).decode()
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, balance, status)
            VALUES (%s, %s, 'admin', 1000.0, 'active')
            ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = 'admin',
                    status = 'active'
        """, ('admin', admin_hash))
        print("[DB] Utente admin OK")

    else:
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT DEFAULT 'user', balance REAL DEFAULT 0, status TEXT DEFAULT 'active');
            CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL NOT NULL, total_odds REAL NOT NULL, potential_win REAL NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS bet_selections (id INTEGER PRIMARY KEY AUTOINCREMENT, bet_id INTEGER, event_id TEXT, market TEXT, selection TEXT, odds REAL, home_team TEXT, away_team TEXT, status TEXT DEFAULT 'pending');
            CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, balance_before REAL, balance_after REAL, admin_id INTEGER DEFAULT 0, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS manual_odds (id INTEGER PRIMARY KEY AUTOINCREMENT, sport_title TEXT, home_team TEXT, away_team TEXT, commence_time TEXT, price_home REAL, price_draw REAL, price_away REAL, price_over REAL, price_under REAL, price_goal REAL, price_nogoal REAL);
            CREATE TABLE IF NOT EXISTS crash_bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, cashout_multiplier REAL, payout REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS crash_rounds (id INTEGER PRIMARY KEY AUTOINCREMENT, crash_point REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS virtual_teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, offense INTEGER DEFAULT 70, defense INTEGER DEFAULT 70, logo_url TEXT);
            CREATE TABLE IF NOT EXISTS virtual_seasons (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT DEFAULT 'active', current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS virtual_matches (id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER, matchday INTEGER, home_team_id INTEGER, away_team_id INTEGER, home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0, status TEXT DEFAULT 'scheduled', current_minute INTEGER DEFAULT 0, odds_1 REAL, odds_x REAL, odds_2 REAL, odds_over25 REAL, odds_under25 REAL, odds_gg REAL, odds_ng REAL, odds_combo TEXT, odds_exact TEXT);
            CREATE TABLE IF NOT EXISTS bonuses (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, min_deposit REAL DEFAULT 0, max_deposit REAL DEFAULT 0, bonus_percent INTEGER DEFAULT 0, bonus_fixed REAL DEFAULT 0, active INTEGER DEFAULT 1, assigned_to_user_id INTEGER DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS user_bonuses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bonus_id INTEGER, applied_amount REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS withdrawal_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, amount REAL, iban TEXT, holder_name TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS deposit_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, amount REAL, bonus_id INTEGER DEFAULT NULL, bonus_amount REAL DEFAULT 0, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS virtual_standings (id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER, team_id INTEGER, points INTEGER DEFAULT 0, played INTEGER DEFAULT 0, won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0, goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0, UNIQUE(season_id, team_id));
            INSERT OR IGNORE INTO settings (key, value) VALUES ('overround', '5');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('odds_source', 'manual');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('apikey', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('api_provider', 'the-odds-api');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('active_sports', 'soccer_serie_a,soccer_epl,soccer_uefa_champs_league,soccer_spain_la_liga,soccer_germany_bundesliga,soccer_france_ligue_one,soccer_italy_serie_b,soccer_usa_mls,soccer_brazil_campeonato,soccer_portugal_primeira_liga,soccer_netherlands_eredivisie,soccer_uefa_europa_league,soccer_turkey_super_league,soccer_argentina_primera_division,soccer_italy_serie_c,soccer_uefa_europa_conference_league,soccer_italy_coppa_italia');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('crash_house_edge', '3');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('virtual_house_edge', '15');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('virtual_pay_mode', 'auto');
        """)
        try:
            cursor.execute("ALTER TABLE deposit_requests ADD COLUMN bonus_id INTEGER")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE deposit_requests ADD COLUMN bonus_amount REAL DEFAULT 0")
        except Exception:
            pass

        import bcrypt as _bcrypt
        admin_hash = _bcrypt.hashpw('admin123'.encode(), _bcrypt.gensalt()).decode()
        cursor.execute("INSERT OR REPLACE INTO users (username, password_hash, role, balance, status) VALUES (?, ?, ?, ?, ?)", ('admin', admin_hash, 'admin', 1000.0, 'active'))

    conn.commit()
    print("[DB] Inizializzazione OK")
    conn.close()
