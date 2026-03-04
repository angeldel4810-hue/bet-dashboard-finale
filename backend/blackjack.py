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

    def _is_blackjack(self, hand: List[Dict[str, Any]]) -> bool:
        return len(hand) == 2 and self._calculate_score(hand) == 21

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
            'status': 'playing',
            'insurance_active': False
        }
        
        player_bj = self._is_blackjack(player_hand)
        dealer_bj = self._is_blackjack(dealer_hand)
        
        # If dealer shows Ace, offer insurance, DO NOT resolve immediately unless insurance is handled
        # But for simplicity, we provide an 'insurance_available' flag to UI
        if dealer_hand[0]['rank'] == 'A':
            game_state['insurance_available'] = True
        else:
            game_state['insurance_available'] = False
            if player_bj and dealer_bj:
                game_state['status'] = 'push'
            elif player_bj:
                game_state['status'] = 'win_bj'
            elif dealer_bj:
                game_state['status'] = 'loss'
            
        self.games[game_id] = game_state
        return self._sanitize_game(game_state, show_dealer=(game_state['status'] != 'playing'))

    def insurance(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing' or not game.get('insurance_available'):
            return {"error": "Assicurazione non disponibile"}
        
        game['insurance_active'] = True
        game['insurance_available'] = False
        
        # Now resolve the dealer blackjack check since player chose insurance
        dealer_bj = self._is_blackjack(game['dealer_hand'])
        player_bj = self._is_blackjack(game['player_hand'])
        
        if dealer_bj:
            if player_bj:
                game['status'] = 'push'
            else:
                game['status'] = 'loss'
            return self._sanitize_game(game, show_dealer=True)
        else:
            # Dealer does not have BJ
            if player_bj:
                game['status'] = 'win_bj'
                return self._sanitize_game(game, show_dealer=True)
            else:
                # Game continues
                return self._sanitize_game(game)

    def skip_insurance(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing':
            return {"error": "Gioco non trovato o terminato"}
        
        game['insurance_available'] = False
        
        dealer_bj = self._is_blackjack(game['dealer_hand'])
        player_bj = self._is_blackjack(game['player_hand'])
        
        if dealer_bj:
            if player_bj:
                game['status'] = 'push'
            else:
                game['status'] = 'loss'
            return self._sanitize_game(game, show_dealer=True)
        else:
            if player_bj:
                game['status'] = 'win_bj'
                return self._sanitize_game(game, show_dealer=True)
            else:
                return self._sanitize_game(game)

    def split(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing':
            return {"error": "Gioco non trovato o terminato"}
        
        hand = game.get('player_hand')
        if not hand or len(hand) != 2:
            return {"error": "Non puoi splittare questa mano"}
        if hand[0]['value'] != hand[1]['value'] and hand[0]['rank'] != hand[1]['rank']:
            return {"error": "Le carte devono avere lo stesso valore per splittare"}
        if 'split_hands' in game:
            return {"error": "Hai già splittato in questa partita"}

        game['insurance_available'] = False
        game['split_hands'] = [
            [hand[0], game['deck'].pop()],
            [hand[1], game['deck'].pop()]
        ]
        game['active_split_index'] = 0
        game['player_hand'] = game['split_hands'][0]
        game['split_statuses'] = ['playing', 'playing']
        game['split_bets'] = [game['bet'], game['bet']] 
        game['bet'] = game['bet'] * 2
        
        return self._sanitize_game(game)

    def double_down(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing':
            return {"error": "Gioco non trovato o terminato"}
        
        hand = game.get('player_hand')
        if len(hand) != 2:
            return {"error": "Puoi raddoppiare solo con due carte"}
            
        game['insurance_available'] = False
        if 'split_hands' in game:
            game['split_bets'][game['active_split_index']] *= 2
        else:
            game['bet'] *= 2
            
        game['player_hand'].append(game['deck'].pop())
        score = self._calculate_score(game['player_hand'])
        
        if score > 21:
            if 'split_hands' in game:
                game['split_statuses'][game['active_split_index']] = 'bust'
                return self._next_split_hand(game)
            else:
                game['status'] = 'bust'
                if game_id in self.games: del self.games[game_id]
                return self._sanitize_game(game, show_dealer=True)
        else:
            return self.stand(game)

    def _next_split_hand(self, game: Dict[str, Any]) -> Dict[str, Any]:
        game['split_hands'][game['active_split_index']] = game['player_hand']
        idx = game['active_split_index'] + 1
        if idx < len(game['split_hands']):
            game['active_split_index'] = idx
            game['player_hand'] = game['split_hands'][idx]
            return self._sanitize_game(game)
        else:
            return self._evaluate_split_game(game)

    def _evaluate_split_game(self, game: Dict[str, Any]) -> Dict[str, Any]:
        if any(s not in ['bust', 'win_bj'] for s in game['split_statuses']):
            while self._calculate_score(game['dealer_hand']) < 17:
                game['dealer_hand'].append(game['deck'].pop())
        
        dealer_score = self._calculate_score(game['dealer_hand'])
        dealer_bj = self._is_blackjack(game['dealer_hand'])
        
        payout = 0
        for i, hand in enumerate(game['split_hands']):
            if game['split_statuses'][i] == 'bust':
                game['split_statuses'][i] = 'loss'
                continue
                
            player_score = self._calculate_score(hand)
            # In split, a blackjack is generally a 21 because you split, but let's just stick to scoring.
            if dealer_bj:
                game['split_statuses'][i] = 'loss'
            elif dealer_score > 21 or player_score > dealer_score:
                game['split_statuses'][i] = 'win'
                payout += game['split_bets'][i] * 2
            elif player_score < dealer_score:
                game['split_statuses'][i] = 'loss'
            else:
                game['split_statuses'][i] = 'push'
                payout += game['split_bets'][i]
                
        game['status'] = 'split_end'
        game['payout'] = payout
        if game.get('insurance_active') and dealer_bj:
            game['insurance_payout'] = sum(game['split_bets']) * 0.5 * 3
            game['payout'] += game['insurance_payout']

        if game.get('game_id') in self.games:
            del self.games[game['game_id']]
            
        return self._sanitize_game(game, show_dealer=True)

    def hit(self, game_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game or game['status'] != 'playing':
            return {"error": "Gioco non trovato o terminato"}
        
        game['insurance_available'] = False
        game['player_hand'].append(game['deck'].pop())
        score = self._calculate_score(game['player_hand'])
        
        if score > 21:
            if 'split_hands' in game:
                game['split_statuses'][game['active_split_index']] = 'bust'
                return self._next_split_hand(game)
            else:
                game['status'] = 'bust'
                if game_id in self.games: del self.games[game_id]
                return self._sanitize_game(game, show_dealer=True)
            
        return self._sanitize_game(game)

    def stand(self, game_state_or_id: Any) -> Dict[str, Any]:
        if isinstance(game_state_or_id, str):
            game = self.games.get(game_state_or_id)
            if not game or game['status'] != 'playing':
                return {"error": "Gioco non trovato o terminato"}
        else:
            game = game_state_or_id

        game['insurance_available'] = False

        if 'split_hands' in game:
            game['split_statuses'][game['active_split_index']] = 'stood'
            return self._next_split_hand(game)

        # Dealer logic
        while self._calculate_score(game['dealer_hand']) < 17:
            game['dealer_hand'].append(game['deck'].pop())
            
        player_score = self._calculate_score(game['player_hand'])
        dealer_score = self._calculate_score(game['dealer_hand'])
        dealer_bj = self._is_blackjack(game['dealer_hand'])
        player_bj = self._is_blackjack(game['player_hand'])
        
        if dealer_bj:
            if player_bj:
                game['status'] = 'push'
            else:
                game['status'] = 'loss'
        elif player_bj:
            game['status'] = 'win_bj'
        elif dealer_score > 21 or player_score > dealer_score:
            game['status'] = 'win'
        elif player_score < dealer_score:
            game['status'] = 'loss'
        else:
            game['status'] = 'push'
            
        if game.get('game_id') in self.games:
            del self.games[game['game_id']]
            
        return self._sanitize_game(game, show_dealer=True)

    def _sanitize_game(self, game: Dict[str, Any], show_dealer: bool = False) -> Dict[str, Any]:
        res = {
            'game_id': game['game_id'],
            'player_hand': game['player_hand'],
            'player_score': self._calculate_score(game['player_hand']),
            'dealer_hand': game['dealer_hand'] if show_dealer else [game['dealer_hand'][0], {'rank': '?', 'suit': '?', 'value': 0}],
            'dealer_score': self._calculate_score(game['dealer_hand']) if show_dealer else game['dealer_hand'][0]['value'],
            'status': game['status'],
            'bet': game['bet'],
            'insurance_available': game.get('insurance_available', False),
            'insurance_active': game.get('insurance_active', False),
            'is_split': False
        }
        if game.get('insurance_payout'):
            res['insurance_payout'] = game['insurance_payout']
        if 'split_hands' in game:
            res['is_split'] = True
            res['active_hand_num'] = game['active_split_index'] + 1
            res['split_hands'] = game['split_hands']
            res['split_statuses'] = game.get('split_statuses', [])
            if game['status'] == 'split_end':
                res['payout'] = game.get('payout', 0)
        return res

bj_engine = BlackjackEngine()
