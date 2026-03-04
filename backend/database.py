import sqlite3
import os
from bcrypt import hashpw, gensalt, checkpw

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "antigravity.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        balance REAL DEFAULT 0,
        status TEXT DEFAULT 'active'
    )
    ''')
    
    # Settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')

    # Manual Odds table - expanded for more markets
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS manual_odds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport_title TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        commence_time TEXT NOT NULL,
        price_home REAL NOT NULL,
        price_draw REAL,
        price_away REAL NOT NULL,
        price_over REAL,
        price_under REAL,
        price_goal REAL,
        price_nogoal REAL
    )
    ''')

    # Bets table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        total_odds REAL NOT NULL,
        potential_win REAL NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, won, lost
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # Bet Selections (for multiples)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bet_selections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bet_id INTEGER NOT NULL,
        event_id TEXT NOT NULL,
        market TEXT NOT NULL, -- h2h, totals, btts
        selection TEXT NOT NULL, -- 1, X, 2, Over, Under, Goal, NoGoal
        odds REAL NOT NULL,
        home_team TEXT,
        away_team TEXT,
        FOREIGN KEY (bet_id) REFERENCES bets (id)
    )
    ''')
    
    # Check if admin exists, if not create default
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_pass = "admin123" # User should change this
        hashed = hashpw(admin_pass.encode('utf-8'), gensalt()).decode('utf-8')
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                       ("admin", hashed, "admin"))
    
    # Initialize default settings
    default_settings = {
        "overround": "5",
        "active_sports": "soccer_italy_serie_a,soccer_italy_serie_b,soccer_italy_serie_c_girone_a,soccer_italy_serie_c_girone_b,soccer_italy_serie_c_girone_c,soccer_epl,soccer_efl_champ,soccer_spain_la_liga,soccer_germany_bundesliga,soccer_france_ligue_one,soccer_uefa_champs_league,soccer_uefa_europa_league,soccer_uefa_europa_conference_league,soccer_netherlands_eredivisie,soccer_portugal_primeira_liga,soccer_usa_mls,soccer_brazil_campeonato,soccer_argentina_primera_division,basketball_nba,basketball_euroleague,basketball_ncaab,tennis_atp_aus_open,tennis_wta_aus_open,tennis_atp_french_open,tennis_wta_french_open,tennis_atp_wimbledon,tennis_wta_wimbledon,tennis_atp_us_open,tennis_wta_us_open",
        "odds_source": "api",
        "api_provider": "the-odds-api",
        "apikey": "f85d90a7ce76ed13e4a81a93bb880665"
    }
    
    for key, value in default_settings.items():
        # Usiamo INSERT OR IGNORE per non sovrascrivere le impostazioni salvate dall'utente (amministratore)
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        
    # Create Transactions table for audit logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL, -- credit, debit, refund, win, admin_adjustment, bet_deletion
        amount REAL NOT NULL,
        balance_before REAL NOT NULL,
        balance_after REAL NOT NULL,
        admin_id INTEGER NOT NULL,
        reason TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (admin_id) REFERENCES users (id)
    )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
