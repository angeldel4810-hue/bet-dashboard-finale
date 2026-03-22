"""
7 e Mezzo - Motore di Gioco
Mazzo italiano 40 carte. Banco si ferma a >= 5.0
Parita: push. 7½ naturale: paga 1:1.
"""
import random
from typing import Optional

# --- Mazzo Napoletano ---
SUITS = ['Denari', 'Coppe', 'Bastoni', 'Spade']
RANKS = ['A', '2', '3', '4', '5', '6', '7', 'F', 'C', 'R']
RANK_VALUES = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    'F': 0.5, 'C': 0.5, 'R': 0.5
}

def build_deck() -> list:
    deck = [{'rank': r, 'suit': s, 'value': RANK_VALUES[r], 'matta': False}
            for r in RANKS for s in SUITS]
    # Aggiungi la Matta (jolly)
    deck.append({'rank': '★', 'suit': '★', 'value': 0, 'matta': True})
    random.shuffle(deck)
    return deck

def calc_score(hand: list) -> float:
    """Calcola il punteggio. La Matta vale il valore ottimale per non sforare."""
    has_matta = any(c['matta'] for c in hand)
    base = sum(c['value'] for c in hand if not c['matta'])
    if not has_matta:
        return round(base, 1)
    # Matta: trova il valore migliore (max intero che non sfora 7.5)
    best = base  # matta = 0 (es. se gia a 7.5)
    for v in [7, 6, 5, 4, 3, 2, 1, 0.5]:
        if base + v <= 7.5:
            best = base + v
            break
    return round(best, 1)

def is_natural(hand: list) -> bool:
    """True se 7½ naturale: 2 carte che fanno esattamente 7.5"""
    return len(hand) == 2 and calc_score(hand) == 7.5

# --- Stato partite in memoria ---
games: dict = {}

def _new_game_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]

def deal(bet: float, user_id: int) -> dict:
    deck = build_deck()
    # 7 e Mezzo: 1 carta a testa iniziale
    player_hand = [deck.pop()]
    dealer_hand = [deck.pop()]

    game_id = _new_game_id()

    games[game_id] = {
        'deck': deck,
        'player_hand': player_hand,
        'dealer_hand': dealer_hand,
        'bet': bet,
        'user_id': user_id,
        'status': 'playing',
        'payout': 0,
    }

    return _sanitize(game_id)

def hit(game_id: str) -> dict:
    g = games.get(game_id)
    if not g or g['status'] != 'playing':
        return {'error': 'Partita non trovata o gia terminata'}

    card = g['deck'].pop()
    g['player_hand'].append(card)
    score = calc_score(g['player_hand'])

    if score > 7.5:
        g['status'] = 'bust'
        g['payout'] = 0

    return _sanitize(game_id)

def stand(game_id: str) -> dict:
    g = games.get(game_id)
    if not g or g['status'] != 'playing':
        return {'error': 'Partita non trovata o gia terminata'}

    # Banco pesca finche < 5.0 oppure ha la Matta
    dealer_has_matta = any(c['matta'] for c in g['dealer_hand'])
    while calc_score(g['dealer_hand']) < 5.0 and not dealer_has_matta:
        if not g['deck']:
            break
        g['dealer_hand'].append(g['deck'].pop())
        dealer_has_matta = any(c['matta'] for c in g['dealer_hand'])

    player_score = calc_score(g['player_hand'])
    dealer_score = calc_score(g['dealer_hand'])
    bet = g['bet']

    dealer_bust = dealer_score > 7.5

    if dealer_bust:
        g['status'] = 'win'
        g['payout'] = bet * 2
    elif player_score > dealer_score:
        g['status'] = 'win'
        g['payout'] = bet * 2
    elif player_score == dealer_score:
        # Parita: rimborso puntata
        g['status'] = 'push'
        g['payout'] = bet
    else:
        g['status'] = 'loss'
        g['payout'] = 0

    return _sanitize(game_id)

def _sanitize(game_id: str) -> dict:
    g = games[game_id]
    game_over = g['status'] not in ('playing',)
    
    # 7 e Mezzo: la prima carta del banco e sempre scoperta!
    dealer_hand_display = g['dealer_hand'] if game_over else [g['dealer_hand'][0]]
    dealer_score_display = calc_score(g['dealer_hand']) if game_over else calc_score([g['dealer_hand'][0]])

    return {
        'game_id': game_id,
        'player_hand': g['player_hand'],
        'dealer_hand': dealer_hand_display,
        'player_score': calc_score(g['player_hand']),
        'dealer_score': dealer_score_display,
        'status': g['status'],
        'payout': g['payout'],
        'bet': g['bet'],
    }
