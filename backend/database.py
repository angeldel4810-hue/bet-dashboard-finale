import sqlite3
import os
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOG_AVAILABLE = True
except ImportError:
    PSYCOG_AVAILABLE = False
from bcrypt import hashpw, gensalt, checkpw

# Supabase URL (PostgreSQL)
SUPABASE_DB_URL = os.environ.get("DATABASE_URL")

# Path locale per fallback SQLite (se non c'è DATABASE_URL)
LOCAL_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "antigravity.db")

def get_db():
    if SUPABASE_DB_URL:
        # Usiamo Supabase (PostgreSQL)
        if not PSYCOG_AVAILABLE:
            raise ImportError("psycopg2 non è installato. Impossibile connettersi a PostgreSQL.")
        conn = psycopg2.connect(SUPABASE_DB_URL)
        return conn
    else:
        # Fallback locale (SQLite)
        if not os.path.exists(os.path.dirname(LOCAL_DB_PATH)):
            os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(LOCAL_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def is_postgres(conn):
    return SUPABASE_DB_URL is not None or hasattr(conn, 'get_dsn_parameters')

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    is_postgres = SUPABASE_DB_URL is not None
    
    # Sintassi per l'auto-incremento diversa tra SQLite e PostgreSQL
    serial_primary_key = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text_type = "TEXT"
    real_type = "DOUBLE PRECISION" if is_postgres else "REAL"
    timestamp_type = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    
    # Users table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS users (
        id {serial_primary_key},
        username {text_type} UNIQUE NOT NULL,
        password_hash {text_type} NOT NULL,
        role {text_type} DEFAULT 'user',
        balance {real_type} DEFAULT 0,
        status {text_type} DEFAULT 'active'
    )
    ''')
    
    # Settings table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS settings (
        key {text_type} PRIMARY KEY,
        value {text_type} NOT NULL
    )
    ''')

    # Manual Odds table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS manual_odds (
        id {serial_primary_key},
        sport_title {text_type} NOT NULL,
        home_team {text_type} NOT NULL,
        away_team {text_type} NOT NULL,
        commence_time {text_type} NOT NULL,
        price_home {real_type} NOT NULL,
        price_draw {real_type},
        price_away {real_type} NOT NULL,
        price_over {real_type},
        price_under {real_type},
        price_goal {real_type},
        price_nogoal {real_type}
    )
    ''')

    # Bets table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS bets (
        id {serial_primary_key},
        user_id INTEGER NOT NULL,
        amount {real_type} NOT NULL,
        total_odds {real_type} NOT NULL,
        potential_win {real_type} NOT NULL,
        status {text_type} DEFAULT 'pending',
        created_at {timestamp_type},
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Bet Selections
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS bet_selections (
        id {serial_primary_key},
        bet_id INTEGER NOT NULL,
        event_id {text_type} NOT NULL,
        market {text_type} NOT NULL,
        selection {text_type} NOT NULL,
        odds {real_type} NOT NULL,
        status {text_type} DEFAULT 'pending',
        home_team {text_type},
        away_team {text_type},
        FOREIGN KEY (bet_id) REFERENCES bets (id)
    )
    ''')
    
    # Check if admin exists
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_pass = "admin123"
        hashed = hashpw(admin_pass.encode('utf-8'), gensalt()).decode('utf-8')
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)" if is_postgres else "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                       ("admin", hashed, "admin"))
    
    # Initialize default settings
    default_settings = {
        "overround": "5",
        "active_sports": "soccer_italy_serie_a,soccer_italy_serie_b,soccer_italy_serie_c_girone_a,soccer_italy_serie_c_girone_b,soccer_italy_serie_c_girone_c,soccer_epl,soccer_efl_champ,soccer_spain_la_liga,soccer_germany_bundesliga,soccer_france_ligue_one,soccer_uefa_champs_league,soccer_uefa_europa_league,soccer_uefa_europa_conference_league,soccer_netherlands_eredivisie,soccer_portugal_primeira_liga,soccer_usa_mls,soccer_brazil_campeonato,soccer_argentina_primera_division,basketball_nba,basketball_euroleague,basketball_ncaab,tennis_atp_aus_open,tennis_wta_aus_open,tennis_atp_french_open,tennis_wta_french_open,tennis_atp_wimbledon,tennis_wta_wimbledon,tennis_atp_us_open,tennis_wta_us_open",
        "odds_source": "api",
        "api_provider": "the-odds-api",
        "apikey": "f85d90a7ce76ed13e4a81a93bb880665",
        "crash_house_edge": "3"
    }
    
    for key, value in default_settings.items():
        if is_postgres:
            cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, value))
        else:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        
    # Transactions table
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS transactions (
        id {serial_primary_key},
        user_id INTEGER NOT NULL,
        type {text_type} NOT NULL,
        amount {real_type} NOT NULL,
        balance_before {real_type} NOT NULL,
        balance_after {real_type} NOT NULL,
        admin_id INTEGER NOT NULL,
        reason {text_type},
        timestamp {timestamp_type},
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (admin_id) REFERENCES users (id)
    )
    ''')

    # Crash Game Rounds
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS crash_rounds (
        id {serial_primary_key},
        crash_point {real_type} NOT NULL,
        status {text_type} DEFAULT 'finished',
        created_at {timestamp_type}
    )
    ''')

    # Crash Game Bets
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS crash_bets (
        id {serial_primary_key},
        user_id INTEGER NOT NULL,
        round_id INTEGER,
        amount {real_type} NOT NULL,
        cashout_multiplier {real_type},
        payout {real_type} DEFAULT 0,
        status {text_type} DEFAULT 'pending',
        created_at {timestamp_type},
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (round_id) REFERENCES crash_rounds (id)
    )
    ''')
    # Virtual Football Schema
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS virtual_teams (
        id {serial_primary_key},
        name {text_type} UNIQUE NOT NULL,
        offense {real_type} NOT NULL,
        defense {real_type} NOT NULL,
        logo_url {text_type}
    )
    ''')

    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS virtual_seasons (
        id {serial_primary_key},
        current_matchday INTEGER DEFAULT 1,
        status {text_type} DEFAULT 'active',
        created_at {timestamp_type}
    )
    ''')

    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS virtual_matches (
        id {serial_primary_key},
        season_id INTEGER NOT NULL,
        matchday INTEGER NOT NULL,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        status {text_type} DEFAULT 'scheduled',
        home_score INTEGER DEFAULT 0,
        away_score INTEGER DEFAULT 0,
        current_minute INTEGER DEFAULT 0,
        odds_1 {real_type},
        odds_x {real_type},
        odds_2 {real_type},
        odds_over25 {real_type},
        odds_under25 {real_type},
        odds_gg {real_type},
        odds_ng {real_type},
        odds_combo {text_type} DEFAULT '{{}}',
        odds_exact {text_type} DEFAULT '{{}}',
        FOREIGN KEY (season_id) REFERENCES virtual_seasons (id),
        FOREIGN KEY (home_team_id) REFERENCES virtual_teams (id),
        FOREIGN KEY (away_team_id) REFERENCES virtual_teams (id)
    )
    ''')

    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS virtual_standings (
        id {serial_primary_key},
        season_id INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        points INTEGER DEFAULT 0,
        played INTEGER DEFAULT 0,
        won INTEGER DEFAULT 0,
        drawn INTEGER DEFAULT 0,
        lost INTEGER DEFAULT 0,
        goals_for INTEGER DEFAULT 0,
        goals_against INTEGER DEFAULT 0,
        FOREIGN KEY (season_id) REFERENCES virtual_seasons (id),
        FOREIGN KEY (team_id) REFERENCES virtual_teams (id),
        UNIQUE(season_id, team_id)
    )
    ''')

    # Add virtual house edge default if missing
    if is_postgres:
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ("virtual_house_edge", "15"))
        cursor.execute("ALTER TABLE virtual_matches ADD COLUMN IF NOT EXISTS odds_combo TEXT DEFAULT '{}'")
        cursor.execute("ALTER TABLE virtual_matches ADD COLUMN IF NOT EXISTS odds_exact TEXT DEFAULT '{}'")
    else:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("virtual_house_edge", "15"))
        try: cursor.execute("ALTER TABLE virtual_matches ADD COLUMN odds_combo TEXT DEFAULT '{}'")
        except: pass
        try: cursor.execute("ALTER TABLE virtual_matches ADD COLUMN odds_exact TEXT DEFAULT '{}'")
        except: pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
