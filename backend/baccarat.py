"""
Baccarat - Punto Banco
Puntate separate su Giocatore, Banco, Pareggio + Coppia Giocatore/Banco
"""
import random
from typing import Dict, Any

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

def card_value(rank: str) -> int:
    if rank in ['10', 'J', 'Q', 'K']: return 0
    if rank == 'A': return 1
    return int(rank)

def build_deck(num_decks=8) -> list:
    deck = [{'rank': r, 'suit': s, 'value': card_value(r)}
            for _ in range(num_decks) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def hand_score(hand: list) -> int:
    return sum(c['value'] for c in hand) % 10

def _apply_third_card(player, banker, deck):
    ps = hand_score(player)
    bs = hand_score(banker)
    if ps >= 8 or bs >= 8:
        return
    player_drew = False
    player_third = None
    if ps <= 5:
        player_third = deck.pop()
        player.append(player_third)
        player_drew = True
    bs = hand_score(banker)
    if not player_drew:
        if bs <= 5:
            banker.append(deck.pop())
    else:
        ptv = player_third['value']
        if bs <= 2: banker.append(deck.pop())
        elif bs == 3 and ptv != 8: banker.append(deck.pop())
        elif bs == 4 and ptv in [2,3,4,5,6,7]: banker.append(deck.pop())
        elif bs == 5 and ptv in [4,5,6,7]: banker.append(deck.pop())
        elif bs == 6 and ptv in [6,7]: banker.append(deck.pop())

def deal(bets: dict, user_id: int) -> dict:
    """
    bets = {
      'player': float,
      'banker': float,
      'tie': float,
      'player_pair': float,
      'banker_pair': float
    }
    """
    deck = build_deck()
    player = [deck.pop(), deck.pop()]
    banker = [deck.pop(), deck.pop()]
    _apply_third_card(player, banker, deck)

    ps = hand_score(player)
    bs = hand_score(banker)

    if ps > bs: winner = 'player'
    elif bs > ps: winner = 'banker'
    else: winner = 'tie'

    payout = 0.0

    # Puntata Giocatore 1:1
    if bets.get('player', 0) > 0:
        if winner == 'player':
            payout += bets['player'] * 2
        elif winner == 'tie':
            payout += bets['player']  # push

    # Puntata Banco 0.95:1
    if bets.get('banker', 0) > 0:
        if winner == 'banker':
            payout += bets['banker'] * 2 * 0.95
        elif winner == 'tie':
            payout += bets['banker']  # push

    # Puntata Pareggio 8:1
    if bets.get('tie', 0) > 0:
        if winner == 'tie':
            payout += bets['tie'] * 9

    # Side bets coppie 11:1
    player_pair = player[0]['rank'] == player[1]['rank']
    banker_pair = banker[0]['rank'] == banker[1]['rank']
    if bets.get('player_pair', 0) > 0 and player_pair:
        payout += bets['player_pair'] * 12
    if bets.get('banker_pair', 0) > 0 and banker_pair:
        payout += bets['banker_pair'] * 12

    return {
        'player': player,
        'banker': banker,
        'player_score': ps,
        'banker_score': bs,
        'winner': winner,
        'payout': round(payout, 2),
        'player_pair': player_pair,
        'banker_pair': banker_pair,
        'bets': bets,
    }
