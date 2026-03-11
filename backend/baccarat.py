"""Baccarat Punto Banco - puntate multiple su player/banker/tie + coppie"""
import random

SUITS = ['♠','♥','♦','♣']
RANKS = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']
RED_SUITS = {'♥','♦'}
BLACK_SUITS = {'♠','♣'}

def card_value(rank):
    if rank in ['10','J','Q','K']: return 0
    if rank == 'A': return 1
    return int(rank)

def build_deck(n=8):
    deck = [{'rank':r,'suit':s,'value':card_value(r)} for _ in range(n) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def score(hand):
    return sum(c['value'] for c in hand) % 10

def pair_type(c1, c2):
    """
    Ritorna il tipo di coppia tra le prime 2 carte:
    'none'     - rank diverso (non è coppia)
    'mixed'    - stesso rank, colori diversi (es. ♠ e ♥) → 6:1
    'same_color' - stesso rank, stesso colore ma seme diverso (es. ♠ e ♣) → 12:1
    'perfect'  - stesso rank, stesso seme identico → 24:1
    """
    if c1['rank'] != c2['rank']:
        return 'none'
    if c1['suit'] == c2['suit']:
        return 'perfect'
    c1_red = c1['suit'] in RED_SUITS
    c2_red = c2['suit'] in RED_SUITS
    if c1_red == c2_red:
        return 'same_color'   # stesso colore, seme diverso
    return 'mixed'            # colori diversi

PAIR_MULTIPLIER = {
    'none':       0,
    'mixed':      7,    # paga 6:1  → restituisce 7x (puntata + vincita)
    'same_color': 13,   # paga 12:1 → restituisce 13x
    'perfect':    25,   # paga 24:1 → restituisce 25x
}

PAIR_LABEL = {
    'none':       None,
    'mixed':      'Coppia Mista (6:1)',
    'same_color': 'Coppia Colore (12:1)',
    'perfect':    'Coppia Identica (24:1)',
}

def apply_third_card(player, banker, deck):
    ps, bs = score(player), score(banker)
    if ps >= 8 or bs >= 8:
        return
    player_drew = False
    third = None
    if ps <= 5:
        third = deck.pop()
        player.append(third)
        player_drew = True
    bs = score(banker)
    if not player_drew:
        if bs <= 5: banker.append(deck.pop())
    else:
        tv = third['value']
        if   bs <= 2: banker.append(deck.pop())
        elif bs == 3 and tv != 8: banker.append(deck.pop())
        elif bs == 4 and tv in [2,3,4,5,6,7]: banker.append(deck.pop())
        elif bs == 5 and tv in [4,5,6,7]: banker.append(deck.pop())
        elif bs == 6 and tv in [6,7]: banker.append(deck.pop())

def deal(bets: dict, user_id: int) -> dict:
    """
    bets = { player: float, banker: float, tie: float,
             player_pair: float, banker_pair: float }
    """
    deck = build_deck()
    player = [deck.pop(), deck.pop()]
    banker = [deck.pop(), deck.pop()]
    apply_third_card(player, banker, deck)

    ps = score(player)
    bs = score(banker)
    winner = 'player' if ps > bs else ('banker' if bs > ps else 'tie')

    pp_type = pair_type(player[0], player[1])
    bp_type = pair_type(banker[0], banker[1])
    player_pair = pp_type != 'none'
    banker_pair = bp_type != 'none'

    bp  = bets.get('player', 0)
    bb  = bets.get('banker', 0)
    bt  = bets.get('tie', 0)
    bpp = bets.get('player_pair', 0)
    bbp = bets.get('banker_pair', 0)
    total = bp + bb + bt + bpp + bbp

    payout = 0.0

    if winner == 'player':
        payout += bp * 2
    elif winner == 'banker':
        payout += bb * 2 * 0.95
    else:  # tie
        payout += bt * 9
        payout += bp  # push
        payout += bb  # push

    if bpp > 0 and player_pair:
        payout += bpp * PAIR_MULTIPLIER[pp_type]
    if bbp > 0 and banker_pair:
        payout += bbp * PAIR_MULTIPLIER[bp_type]

    profit = payout - total

    return {
        'player': player, 'banker': banker,
        'player_score': ps, 'banker_score': bs,
        'winner': winner,
        'player_pair': player_pair,
        'player_pair_type': pp_type,
        'player_pair_label': PAIR_LABEL[pp_type],
        'banker_pair': banker_pair,
        'banker_pair_type': bp_type,
        'banker_pair_label': PAIR_LABEL[bp_type],
        'payout': round(payout, 2),
        'profit': round(profit, 2),
        'total_bet': round(total, 2),
    }
