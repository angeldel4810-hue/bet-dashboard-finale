"""Baccarat Punto Banco - puntate multiple su player/banker/tie + coppie"""
import random

SUITS = ['♠','♥','♦','♣']
RANKS = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']

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

    player_pair = player[0]['rank'] == player[1]['rank']
    banker_pair = banker[0]['rank'] == banker[1]['rank']

    payout = 0.0
    bp = bets.get('player', 0)
    bb = bets.get('banker', 0)
    bt = bets.get('tie', 0)
    bpp = bets.get('player_pair', 0)
    bbp = bets.get('banker_pair', 0)
    total = bp + bb + bt + bpp + bbp

    if winner == 'player':
        payout += bp * 2
    elif winner == 'banker':
        payout += bb * 2 * 0.95
    else:  # tie
        payout += bt * 9
        payout += bp   # push rimborso
        payout += bb   # push rimborso

    if player_pair and bpp > 0: payout += bpp * 12
    if banker_pair and bbp > 0: payout += bbp * 12

    profit = payout - total

    return {
        'player': player, 'banker': banker,
        'player_score': ps, 'banker_score': bs,
        'winner': winner,
        'player_pair': player_pair, 'banker_pair': banker_pair,
        'payout': round(payout, 2),
        'profit': round(profit, 2),
        'total_bet': round(total, 2),
    }
