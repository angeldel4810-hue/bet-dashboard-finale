“”“Baccarat Punto Banco - puntate multiple su player/banker/tie + coppie”””
import random

SUITS = [‘♠’,‘♥’,‘♦’,‘♣’]
RANKS = [‘A’,‘2’,‘3’,‘4’,‘5’,‘6’,‘7’,‘8’,‘9’,‘10’,‘J’,‘Q’,‘K’]

# Colori per seme

SUIT_COLORS = {
‘♠’: ‘black’,
‘♣’: ‘black’,
‘♥’: ‘red’,
‘♦’: ‘red’,
}

def card_value(rank):
if rank in [‘10’,‘J’,‘Q’,‘K’]: return 0
if rank == ‘A’: return 1
return int(rank)

def build_deck(n=8):
deck = [{‘rank’:r,‘suit’:s,‘value’:card_value(r)} for _ in range(n) for s in SUITS for r in RANKS]
random.shuffle(deck)
return deck

def score(hand):
return sum(c[‘value’] for c in hand) % 10

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
tv = third[‘value’]
if   bs <= 2: banker.append(deck.pop())
elif bs == 3 and tv != 8: banker.append(deck.pop())
elif bs == 4 and tv in [2,3,4,5,6,7]: banker.append(deck.pop())
elif bs == 5 and tv in [4,5,6,7]: banker.append(deck.pop())
elif bs == 6 and tv in [6,7]: banker.append(deck.pop())

def classify_pair(c1, c2):
“””
Classifica il tipo di coppia e ritorna il moltiplicatore:
- Coppia identica (stesso rank E stesso seme): 24:1
- Coppia stesso colore ma seme diverso: 12:1
- Coppia colore diverso: 6:1
- Non e coppia: None
“””
if c1[‘rank’] != c2[‘rank’]:
return None  # Non e una coppia

```
if c1['suit'] == c2['suit']:
    return 24  # Coppia identica (stesso seme)

color1 = SUIT_COLORS[c1['suit']]
color2 = SUIT_COLORS[c2['suit']]

if color1 == color2:
    return 12  # Stesso colore, seme diverso
else:
    return 6   # Colore diverso
```

def deal(bets: dict, user_id: int) -> dict:
“””
bets = { player: float, banker: float, tie: float,
player_pair: float, banker_pair: float }
“””
deck = build_deck()
player = [deck.pop(), deck.pop()]
banker = [deck.pop(), deck.pop()]
apply_third_card(player, banker, deck)

```
ps = score(player)
bs = score(banker)
winner = 'player' if ps > bs else ('banker' if bs > ps else 'tie')

# Classifica le coppie con moltiplicatore variabile
player_pair_mult = classify_pair(player[0], player[1])
banker_pair_mult = classify_pair(banker[0], banker[1])
player_pair = player_pair_mult is not None
banker_pair = banker_pair_mult is not None

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

# Pagamento coppie con moltiplicatore variabile
if player_pair and bpp > 0:
    payout += bpp * player_pair_mult
if banker_pair and bbp > 0:
    payout += bbp * banker_pair_mult

profit = payout - total

return {
    'player': player, 'banker': banker,
    'player_score': ps, 'banker_score': bs,
    'winner': winner,
    'player_pair': player_pair,
    'banker_pair': banker_pair,
    'player_pair_mult': player_pair_mult,
    'banker_pair_mult': banker_pair_mult,
    'payout': round(payout, 2),
    'profit': round(profit, 2),
    'total_bet': round(total, 2),
}
```