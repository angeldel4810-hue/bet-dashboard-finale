"""
Baccarat - Punto Banco
Regole standard: mazzo 8 mazzi, terza carta automatica.
Puntate: Giocatore (1:1), Banco (1:1 - 5% commissione), Pareggio (8:1), Coppia Giocatore/Banco (11:1)
"""
import random
from typing import Dict, Any

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

def card_value(rank: str) -> int:
    if rank in ['10', 'J', 'Q', 'K']:
        return 0
    if rank == 'A':
        return 1
    return int(rank)

def build_deck(num_decks=8) -> list:
    deck = [{'rank': r, 'suit': s, 'value': card_value(r)}
            for _ in range(num_decks) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def hand_score(hand: list) -> int:
    return sum(c['value'] for c in hand) % 10

games: Dict[str, Dict[str, Any]] = {}

def _new_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]

def deal(bet_on: str, bet_amount: float, side_bets: dict, user_id: int) -> dict:
    """
    bet_on: 'player' | 'banker' | 'tie'
    side_bets: {'player_pair': float, 'banker_pair': float}
    """
    deck = build_deck()
    # Deal: player, banker, player, banker
    player = [deck.pop(), deck.pop()]
    banker = [deck.pop(), deck.pop()]

    game_id = _new_id()
    games[game_id] = {
        'game_id': game_id,
        'user_id': user_id,
        'deck': deck,
        'player': player,
        'banker': banker,
        'bet_on': bet_on,
        'bet_amount': bet_amount,
        'side_bets': side_bets,
        'status': 'dealing',
    }

    # Terza carta automatica (regole standard Punto Banco)
    _apply_third_card(games[game_id])

    return _resolve(games[game_id])

def _apply_third_card(g: dict):
    player = g['player']
    banker = g['banker']
    deck = g['deck']

    ps = hand_score(player)
    bs = hand_score(banker)

    # Natural (8 o 9) = nessuna terza carta
    if ps >= 8 or bs >= 8:
        return

    player_drew = False
    player_third = None

    # Giocatore pesca se score <= 5
    if ps <= 5:
        player_third = deck.pop()
        player.append(player_third)
        player_drew = True

    # Banco: regole terza carta
    bs = hand_score(banker)
    if not player_drew:
        if bs <= 5:
            banker.append(deck.pop())
    else:
        ptv = player_third['value']
        if bs <= 2:
            banker.append(deck.pop())
        elif bs == 3 and ptv != 8:
            banker.append(deck.pop())
        elif bs == 4 and ptv in [2, 3, 4, 5, 6, 7]:
            banker.append(deck.pop())
        elif bs == 5 and ptv in [4, 5, 6, 7]:
            banker.append(deck.pop())
        elif bs == 6 and ptv in [6, 7]:
            banker.append(deck.pop())

def _resolve(g: dict) -> dict:
    ps = hand_score(g['player'])
    bs = hand_score(g['banker'])

    if ps > bs:
        winner = 'player'
    elif bs > ps:
        winner = 'banker'
    else:
        winner = 'tie'

    # Calcola payout
    payout = 0.0
    bet_on = g['bet_on']
    amount = g['bet_amount']

    if bet_on == winner:
        if winner == 'player':
            payout = amount * 2          # 1:1
        elif winner == 'banker':
            payout = amount * 2 * 0.95   # 1:1 meno 5% commissione
        elif winner == 'tie':
            payout = amount * 9          # 8:1
    elif winner == 'tie' and bet_on in ['player', 'banker']:
        payout = amount  # push: rimborso puntata se tie e non hai puntato tie

    # Side bets
    side_payout = 0.0
    sb = g.get('side_bets', {})
    player_pair = len(g['player']) >= 2 and g['player'][0]['rank'] == g['player'][1]['rank']
    banker_pair = len(g['banker']) >= 2 and g['banker'][0]['rank'] == g['banker'][1]['rank']

    if sb.get('player_pair', 0) > 0 and player_pair:
        side_payout += sb['player_pair'] * 12  # 11:1
    if sb.get('banker_pair', 0) > 0 and banker_pair:
        side_payout += sb['banker_pair'] * 12  # 11:1

    total_payout = payout + side_payout

    g['status'] = 'finished'
    g['winner'] = winner
    g['payout'] = total_payout
    g['player_score'] = ps
    g['banker_score'] = bs
    g['player_pair'] = player_pair
    g['banker_pair'] = banker_pair

    # Cleanup memoria
    if g['game_id'] in games:
        del games[g['game_id']]

    return {
        'game_id': g['game_id'],
        'player': g['player'],
        'banker': g['banker'],
        'player_score': ps,
        'banker_score': bs,
        'winner': winner,
        'payout': total_payout,
        'player_pair': player_pair,
        'banker_pair': banker_pair,
        'bet_on': bet_on,
        'bet_amount': amount,
        'side_bets': sb,
        'status': 'finished',
    }
