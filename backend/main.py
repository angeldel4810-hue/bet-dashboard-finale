# ──────────────────────────────────────────────────────────────
# AGGIUNGI QUESTI ENDPOINT DOPO I TUOI ENDPOINT ESISTENTI
# ──────────────────────────────────────────────────────────────

@app.get("/api/odds-status")
async def odds_status_detailed(user = Depends(get_current_user)):
    """Mostra stato del cache e quote disponibili"""
    try:
        cached_odds = odds_cache.get("all_odds_cache", [])
        sports_count = len(set(o["sport_key"] for o in cached_odds))
        
        return {
            "cached_matches": len(cached_odds),
            "sports": sports_count,
            "cache_available": bool(cached_odds),
            "last_update": "Non disponibile - Usa il DB",
            "remaining_api_calls": "Controlla The-Odds-API dashboard"
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/force-odds-refresh")
async def force_odds_refresh_all(admin = Depends(check_admin)):
    """ADMIN: Forza aggiornamento di tutte le quote (usa API call!)"""
    try:
        from backend.odds_api import fetch_all_active_sports, apply_overround
        from backend.database import get_db
        
        api_key = os.environ.get("ODDS_API_KEY")
        if not api_key:
            return {"error": "API Key non configurata"}
        
        # Fetch tutte le quote
        all_odds = fetch_all_active_sports(api_key)
        
        # Applica margine
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'overround'")
        row = cursor.fetchone()
        overround = float(row[0] if row else 5) / 100
        
        all_odds = apply_overround(all_odds, overround)
        
        # Salva nel DB (opzionale)
        cursor.execute("DELETE FROM manual_odds")  # Pulisci vecchie quote
        
        for odd in all_odds[:500]:  # Limita a 500 per performance
            try:
                params = (
                    odd.get("sport_title"),
                    odd.get("home_team"),
                    odd.get("away_team"),
                    odd.get("commence_time"),
                    odd.get("markets", {}).get("1x2", {}).get("home"),
                    odd.get("markets", {}).get("1x2", {}).get("draw"),
                    odd.get("markets", {}).get("1x2", {}).get("away"),
                )
                if hasattr(conn, 'get_dsn_parameters'):
                    cursor.execute("""
                        INSERT INTO manual_odds 
                        (sport_title, home_team, away_team, commence_time, price_home, price_draw, price_away)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, params)
                else:
                    cursor.execute("""
                        INSERT INTO manual_odds 
                        (sport_title, home_team, away_team, commence_time, price_home, price_draw, price_away)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, params)
            except Exception as e:
                print(f"[DB] Errore salvataggio: {e}")
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "matches_updated": len(all_odds),
            "message": f"Aggiornate {len(all_odds)} partite"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/fetch-odds-smart")
async def fetch_odds_smart(user = Depends(get_current_user)):
    """Fetch quote intelligente: usa cache, altrimenti API"""
    try:
        from backend.odds_api import get_odds_from_cache
        
        odds = get_odds_from_cache()
        
        if not odds:
            return {
                "message": "Nessuna quota in cache. Contatta l'admin per aggiornare.",
                "odds": []
            }
        
        return {
            "count": len(odds),
            "odds": odds[:100]  # Limita a 100 per response
        }
    except Exception as e:
        return {"error": str(e)}
