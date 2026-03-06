import os
import sqlite3
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect("simusbet.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'get_dsn_parameters')

    if is_postgres:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                balance NUMERIC(12,2) DEFAULT 0.0,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount NUMERIC(12,2) NOT NULL,
                total_odds NUMERIC(10,4) DEFAULT 1.0,
                potential_win NUMERIC(12,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bet_selections (
                id SERIAL PRIMARY KEY,
                bet_id INTEGER REFERENCES bets(id),
                event_id VARCHAR(255),
                market VARCHAR(100),
                selection VARCHAR(255),
                odds NUMERIC(10,4),
                home_team VARCHAR(100),
                away_team VARCHAR(100),
                status VARCHAR(20) DEFAULT 'pending'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                type VARCHAR(50),
                amount NUMERIC(12,2),
                balance_before NUMERIC(12,2),
                balance_after NUMERIC(12,2),
                admin_id INTEGER,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT
            )
        """)
        # Virtual football tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_teams (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                offense NUMERIC(5,2) DEFAULT 1.0,
                defense NUMERIC(5,2) DEFAULT 1.0,
                logo VARCHAR(10) DEFAULT '⚽'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_seasons (
                id SERIAL PRIMARY KEY,
                status VARCHAR(20) DEFAULT 'active',
                current_matchday INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_matches (
                id SERIAL PRIMARY KEY,
                season_id INTEGER REFERENCES virtual_seasons(id),
                matchday INTEGER,
                home_team_id INTEGER REFERENCES virtual_teams(id),
                away_team_id INTEGER REFERENCES virtual_teams(id),
                home_score INTEGER DEFAULT 0,
                away_score INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'scheduled',
                current_minute INTEGER DEFAULT 0,
                odd_1 NUMERIC(6,2) DEFAULT 2.0,
                odd_x NUMERIC(6,2) DEFAULT 3.0,
                odd_2 NUMERIC(6,2) DEFAULT 2.0,
                odd_gg NUMERIC(6,2) DEFAULT 1.8,
                odd_ng NUMERIC(6,2) DEFAULT 1.9,
                odd_over25 NUMERIC(6,2) DEFAULT 2.0,
                odd_under25 NUMERIC(6,2) DEFAULT 1.7,
                odd_over15 NUMERIC(6,2) DEFAULT 1.3,
                odd_under15 NUMERIC(6,2) DEFAULT 3.5
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_standings (
                id SERIAL PRIMARY KEY,
                season_id INTEGER REFERENCES virtual_seasons(id),
                team_id INTEGER REFERENCES virtual_teams(id),
                played INTEGER DEFAULT 0,
                won INTEGER DEFAULT 0,
                drawn INTEGER DEFAULT 0,
                lost INTEGER DEFAULT 0,
                goals_for INTEGER DEFAULT 0,
                goals_against INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                UNIQUE(season_id, team_id)
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                balance REAL DEFAULT 0.0,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                amount REAL NOT NULL,
                total_odds REAL DEFAULT 1.0,
                potential_win REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bet_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bet_id INTEGER REFERENCES bets(id),
                event_id TEXT,
                market TEXT,
                selection TEXT,
                odds REAL,
                home_team TEXT,
                away_team TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                type TEXT,
                amount REAL,
                balance_before REAL,
                balance_after REAL,
                admin_id INTEGER,
                reason TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                offense REAL DEFAULT 1.0,
                defense REAL DEFAULT 1.0,
                logo TEXT DEFAULT '⚽'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT DEFAULT 'active',
                current_matchday INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER REFERENCES virtual_seasons(id),
                matchday INTEGER,
                home_team_id INTEGER REFERENCES virtual_teams(id),
                away_team_id INTEGER REFERENCES virtual_teams(id),
                home_score INTEGER DEFAULT 0,
                away_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'scheduled',
                current_minute INTEGER DEFAULT 0,
                odd_1 REAL DEFAULT 2.0,
                odd_x REAL DEFAULT 3.0,
                odd_2 REAL DEFAULT 2.0,
                odd_gg REAL DEFAULT 1.8,
                odd_ng REAL DEFAULT 1.9,
                odd_over25 REAL DEFAULT 2.0,
                odd_under25 REAL DEFAULT 1.7,
                odd_over15 REAL DEFAULT 1.3,
                odd_under15 REAL DEFAULT 3.5
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS virtual_standings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER REFERENCES virtual_seasons(id),
                team_id INTEGER REFERENCES virtual_teams(id),
                played INTEGER DEFAULT 0,
                won INTEGER DEFAULT 0,
                drawn INTEGER DEFAULT 0,
                lost INTEGER DEFAULT 0,
                goals_for INTEGER DEFAULT 0,
                goals_against INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                UNIQUE(season_id, team_id)
            )
        """)

    # Impostazioni di default
    if is_postgres:
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('overround', '5')
            ON CONFLICT (key) DO NOTHING
        """)
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES ('virtual_house_edge', '5')
            ON CONFLICT (key) DO NOTHING
        """)
    else:
        cursor.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('overround', '5')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('virtual_house_edge', '5')
        """)

    conn.commit()
    conn.close()
    print("[DB] init_db completato.")
