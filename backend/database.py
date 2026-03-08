import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def get_db():
    if DATABASE_URL and PSYCOPG2_AVAILABLE:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def check_is_psql(conn):
    if not PSYCOPG2_AVAILABLE:
        return False
    return isinstance(conn, psycopg2.extensions.connection)


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    psql = check_is_psql(conn)

    if psql:
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            balance REAL DEFAULT 0, role TEXT DEFAULT 'user', status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id),
            amount REAL NOT NULL, potential_win REAL NOT NULL, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bet_selections (
            id SERIAL PRIMARY KEY, bet_id INTEGER REFERENCES bets(id),
            event_id TEXT, market TEXT, selection TEXT, odds REAL,
            home_team TEXT, away_team TEXT, status TEXT DEFAULT 'pending')""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id),
            type TEXT, amount REAL, balance_before REAL, balance_after REAL,
            admin_id INTEGER, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_teams (
            id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            offense REAL DEFAULT 1.0, defense REAL DEFAULT 1.0)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_seasons (
            id SERIAL PRIMARY KEY, status TEXT DEFAULT 'active',
            current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_matches (
            id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id),
            matchday INTEGER, home_team_id INTEGER REFERENCES virtual_teams(id),
            away_team_id INTEGER REFERENCES virtual_teams(id),
            home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'scheduled', odds_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_standings (
            id SERIAL PRIMARY KEY, season_id INTEGER REFERENCES virtual_seasons(id),
            team_id INTEGER REFERENCES virtual_teams(id),
            points INTEGER DEFAULT 0, played INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0,
            goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0,
            UNIQUE(season_id, team_id))""")
        for key, val in [('overround','0'),('crash_house_edge','8'),('virtual_house_edge','8'),('odds_source','the_odds_api'),('virtual_pay_mode','auto')]:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))
    else:
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            balance REAL DEFAULT 0, role TEXT DEFAULT 'user', status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
            amount REAL NOT NULL, potential_win REAL NOT NULL, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS bet_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bet_id INTEGER REFERENCES bets(id),
            event_id TEXT, market TEXT, selection TEXT, odds REAL,
            home_team TEXT, away_team TEXT, status TEXT DEFAULT 'pending')""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
            type TEXT, amount REAL, balance_before REAL, balance_after REAL,
            admin_id INTEGER, reason TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            offense REAL DEFAULT 1.0, defense REAL DEFAULT 1.0)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT DEFAULT 'active',
            current_matchday INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER REFERENCES virtual_seasons(id),
            matchday INTEGER, home_team_id INTEGER REFERENCES virtual_teams(id),
            away_team_id INTEGER REFERENCES virtual_teams(id),
            home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'scheduled', odds_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS virtual_standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER REFERENCES virtual_seasons(id),
            team_id INTEGER REFERENCES virtual_teams(id),
            points INTEGER DEFAULT 0, played INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0, drawn INTEGER DEFAULT 0, lost INTEGER DEFAULT 0,
            goals_for INTEGER DEFAULT 0, goals_against INTEGER DEFAULT 0,
            UNIQUE(season_id, team_id))""")
        for key, val in [('overround','0'),('crash_house_edge','8'),('virtual_house_edge','8'),('odds_source','the_odds_api'),('virtual_pay_mode','auto')]:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()
    print("[DB] Inizializzazione completata")
