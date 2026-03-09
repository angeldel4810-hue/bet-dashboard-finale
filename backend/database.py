import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")

class PgRow:
    """Wrapper che permette accesso per indice E per nome colonna su psycopg2"""
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
    """Wrapper cursor psycopg2 che restituisce PgRow compatibili con sqlite3.Row"""
    def __init__(self, cursor):
        self._cur = cursor
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
        rows = self._cur.fetchall()
        return [PgRow(r, self._cur.description) for r in rows]
    def __getattr__(self, name): return getattr(self._cur, name)

class PgConnWrapper:
    """Wrapper connessione che usa PgCursorWrapper"""
    def __init__(self, conn):
        self._conn = conn
    def cursor(self): return PgCursorWrapper(self._conn.cursor())
    def commit(self): self._conn.commit()
    def rollback(self): self._conn.rollback()
    def close(self): self._conn.close()
    def get_dsn_parameters(self): return self._conn.get_dsn_parameters()
    def __getattr__(self, name): return getattr(self._conn, name)

def get_db():
    if DATABASE_URL:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        return PgConnWrapper(conn)
    else:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

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
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), type TEXT, amount REAL, balance_before REAL, balance_after REAL, admin_id INTEGER, reason TEXT, timestamp TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS manual_odds (id SERIAL PRIMARY KEY, sport_title TEXT, home_team TEXT, away_team TEXT, commence_time TEXT, price_home REAL, price_draw REAL, price_away REAL, price_over REAL, price_under REAL, price_goal REAL, price_nogoal REAL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS crash_bets (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), amount REAL, cashout_multiplier REAL, payout REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS crash_rounds (id SERIAL PRIMARY KEY, crash_point REAL, created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_teams (id SERIAL PRIMARY KEY, name TEXT UNIQUE, offense INTEGER DEFAULT 70, defense INTEGER DEFAULT 70, logo_url TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_seasons (id SERIAL PRIMARY KEY, status TEXT DEFAULT 'active', current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_matches (id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id), matchday INTEGER, home_team_id INTEGER REFERENCES virtual_teams(id), away_team_id INTEGER REFERENCES virtual_teams(id), home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0, status TEXT DEFAULT 'scheduled', current_minute INTEGER DEFAULT 0, odds_1 REAL, odds_x REAL, odds_2 REAL, odds_over25 REAL, odds_under25 REAL, odds_gg REAL, odds_ng REAL, odds_combo TEXT, odds_exact TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_standings (id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id), team_id INTEGER REFERENCES virtual_teams(id), points INTEGER DEFAULT 0, played INTEGER DEFAULT 0, won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0, goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0, UNIQUE(season_id, team_id))""")

        for k, v in [('overround','5'),('odds_source','manual'),('apikey',''),('api_provider','the-odds-api'),('active_sports',''),('crash_house_edge','3'),('virtual_house_edge','15'),('virtual_pay_mode','auto')]:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (k, v))

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
            CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, balance_before REAL, balance_after REAL, admin_id INTEGER, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS manual_odds (id INTEGER PRIMARY KEY AUTOINCREMENT, sport_title TEXT, home_team TEXT, away_team TEXT, commence_time TEXT, price_home REAL, price_draw REAL, price_away REAL, price_over REAL, price_under REAL, price_goal REAL, price_nogoal REAL);
            CREATE TABLE IF NOT EXISTS crash_bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, cashout_multiplier REAL, payout REAL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS crash_rounds (id INTEGER PRIMARY KEY AUTOINCREMENT, crash_point REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS virtual_teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, offense INTEGER DEFAULT 70, defense INTEGER DEFAULT 70, logo_url TEXT);
            CREATE TABLE IF NOT EXISTS virtual_seasons (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT DEFAULT 'active', current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS virtual_matches (id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER, matchday INTEGER, home_team_id INTEGER, away_team_id INTEGER, home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0, status TEXT DEFAULT 'scheduled', current_minute INTEGER DEFAULT 0, odds_1 REAL, odds_x REAL, odds_2 REAL, odds_over25 REAL, odds_under25 REAL, odds_gg REAL, odds_ng REAL, odds_combo TEXT, odds_exact TEXT);
            CREATE TABLE IF NOT EXISTS virtual_standings (id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER, team_id INTEGER, points INTEGER DEFAULT 0, played INTEGER DEFAULT 0, won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0, goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0, UNIQUE(season_id, team_id));
            INSERT OR IGNORE INTO settings (key, value) VALUES ('overround', '5');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('odds_source', 'manual');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('apikey', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('api_provider', 'the-odds-api');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('active_sports', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('crash_house_edge', '3');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('virtual_house_edge', '15');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('virtual_pay_mode', 'auto');
        """)
        import bcrypt as _bcrypt
        admin_hash = _bcrypt.hashpw('admin123'.encode(), _bcrypt.gensalt()).decode()
        cursor.execute("INSERT OR REPLACE INTO users (username, password_hash, role, balance, status) VALUES (?, ?, ?, ?, ?)", ('admin', admin_hash, 'admin', 1000.0, 'active'))

    conn.commit()
    print("[DB] Inizializzazione OK")
    conn.close()
