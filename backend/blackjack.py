import random
from typing import List, Dict, Any, Optional

class BlackjackEngine:
    def __init__(self):
        self.suits = ['♠', '♥', '♦', '♣']
        self.ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.games: Dict[str, Dict[str, Any]] = {}

    def _create_deck(self) -> List[Dict[str, Any]]:
        deck = []
        for suit in self.suits:
            for rank in self.ranks:
                value = 0
                if rank in ['J', 'Q', 'K']:
                    value = 10
                elif rank == 'A':
                    value = 11
                else:
                    value = int(rank)
                deck.append({'suit': suit, 'rank': rank, 'value': value})
        random.shuffle(deck)
        return deck

    def _calculate_score(self, hand: List[Dict[str, Any]]) -> int:
        score = sum(card['value'] for card in hand)
        aces = sum(1 for card in hand if card['rank'] == 'A')
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def start_game(self, user_id: int, bet: float) -> Dict[str, Any]:
        deck = self._create_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        
        game_id = f"bj_{user_id}_{random.randint(1000, 9999)}"
        game_state = {
            'game_id': game_id,
            'user_id': user_id,
            'bet': bet,
            'deck': deck,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'status': 'playing'
        }
        
        # Check for immediate Blackjack
        player_score = self._calculate_score(player_hand)
        if player_score == 21:
            return self.stand(game_state)
            
        self.games[game_id] = game_state
        return self._sanitize_game(game_state)

    def hit(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing':
            return {"error": "Gioco non trovato o terminato"}
        
        game['player_hand'].append(game['deck'].pop())
        score = self._calculate_score(game['player_hand'])
        
        if score > 21:
            game['status'] = 'bust'
            del self.games[game_id]
            return self._sanitize_game(game, show_dealer=True)
            
        return self._sanitize_game(game)

    def stand(self, game_state_or_id: Any) -> Dict[str, Any]:
        if isinstance(game_state_or_id, str):
            game = self.games.get(game_state_or_id)
            if not game or game['status'] != 'playing':
                return {"error": "Gioco non trovato o terminato"}
        else:
            game = game_state_or_id

        # Dealer logic
        while self._calculate_score(game['dealer_hand']) < 17:
            game['dealer_hand'].append(game['deck'].pop())
            
        player_score = self._calculate_score(game['player_hand'])
        dealer_score = self._calculate_score(game['dealer_hand'])
        
        if dealer_score > 21 or player_score > dealer_score:
            game['status'] = 'win'
        elif player_score < dealer_score:
            game['status'] = 'loss'
        else:
            game['status'] = 'push'
            
        if game.get('game_id') in self.games:
            del self.games[game['game_id']]
            
        return self._sanitize_game(game, show_dealer=True)

    def _sanitize_game(self, game: Dict[str, Any], show_dealer: bool = False) -> Dict[str, Any]:
        return {
            'game_id': game['game_id'],
            'player_hand': game['player_hand'],
            'player_score': self._calculate_score(game['player_hand']),
            'dealer_hand': game['dealer_hand'] if show_dealer else [game['dealer_hand'][0], {'rank': '?', 'suit': '?', 'value': 0}],
            'dealer_score': self._calculate_score(game['dealer_hand']) if show_dealer else game['dealer_hand'][0]['value'],
            'status': game['status'],
            'bet': game['bet']
        }

bj_engine = BlackjackEngine()
