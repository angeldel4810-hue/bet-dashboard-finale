import requests
import math
import os
import time
from typing import Dict, List, Any
from datetime import datetime, timedelta, timezone

try:
    from diskcache import Cache
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
    cache = Cache(cache_dir)
except:
    cache = {}

HOUSE_EDGE = 1.07

def apply_overround(odds_data: List[Dict[str, Any]], overround_percent: float) -> List[Dict[str, Any]]:
    return odds_data

def get_sports(api_key: str):
    return []

def get_odds_from_cache() -> List[Dict[str, Any]]:
    try:
        if isinstance(cache, dict):
            return cache.get("all_odds_cache", [])
        else:
            return cache.get("all_odds_cache", [])
    except:
        return []

def fetch_all_active_sports(api_key: str) -> List[Dict[str, Any]]:
    if not api_key:
        return []
    
    return []
