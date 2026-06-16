import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Reroute database path for unit testing
import app.discord_bot.modules.economy as economy_mod
economy_mod.DATABASE_PATH = economy_mod.Path("data/test_economy.db")

from app.discord_bot.modules.card import Card
from app.discord_bot.cogs.xidach import Deck, PlayerHandView

class TestXiDachRules(unittest.TestCase):
    def test_calculate_score(self):
        # Normal cards
        hand1 = [Card("hearts", 5), Card("spades", 10)]
        self.assertEqual(Deck.calculate_score(hand1), 15)

        # Face cards (J, Q, K = 10)
        hand2 = [Card("diamonds", 11), Card("clubs", 12)] # J, Q
        self.assertEqual(Deck.calculate_score(hand2), 20)

        # Ace adjustments (A = 11, then falls back to 1 to avoid bust)
        hand3 = [Card("hearts", 14), Card("spades", 5)] # Ace + 5
        self.assertEqual(Deck.calculate_score(hand3), 16)

        hand4 = [Card("hearts", 14), Card("spades", 10), Card("clubs", 5)] # Ace + 10 + 5 = 26 -> 16
        self.assertEqual(Deck.calculate_score(hand4), 16)

        hand5 = [Card("hearts", 14), Card("spades", 14)] # 2 Aces
        self.assertEqual(Deck.calculate_score(hand5), 12) # 11 + 11 = 22 -> 12

    def test_hand_ranks(self):
        # normal points
        hand1 = [Card("hearts", 5), Card("spades", 10)]
        rank1, score1, label1 = Deck.get_hand_rank(hand1)
        self.assertEqual(rank1, 15)
        self.assertEqual(label1, "15 điểm")

        # Xi Bang (2 Aces)
        hand2 = [Card("hearts", 14), Card("spades", 14)]
        rank2, score2, label2 = Deck.get_hand_rank(hand2)
        self.assertEqual(rank2, 300)
        self.assertEqual(label2, "Xì Bàng")

        # Xi Dach (2 cards, score 21)
        hand3 = [Card("hearts", 14), Card("spades", 10)]
        rank3, score3, label3 = Deck.get_hand_rank(hand3)
        self.assertEqual(rank3, 100)
        self.assertEqual(label3, "Xì Dách")

        # Bust (score > 21)
        hand4 = [Card("hearts", 10), Card("spades", 10), Card("clubs", 5)]
        rank4, score4, label4 = Deck.get_hand_rank(hand4)
        self.assertEqual(rank4, 0)
        self.assertEqual(label4, "Quắc")

        # Ngu Linh (5 cards, score <= 21)
        hand5 = [Card("hearts", 2), Card("spades", 3), Card("clubs", 4), Card("diamonds", 5), Card("hearts", 6)] # sum = 20
        rank5, score5, label5 = Deck.get_hand_rank(hand5)
        self.assertEqual(rank5, 201)
        self.assertEqual(label5, "Ngũ Linh")

    def test_stand_restriction(self):
        # Test that clicking Stand button under 16 points is rejected
        mock_player = MagicMock()
        mock_deck = MagicMock()
        mock_session = MagicMock()
        mock_session.player_done = AsyncMock()

        # Under 16 points (score 15)
        hand1 = [Card("hearts", 5), Card("spades", 10)]
        view1 = PlayerHandView(mock_player, hand1, mock_deck, mock_session)
        
        mock_interaction1 = AsyncMock()
        mock_button1 = MagicMock()

        # Execute stand_button
        import asyncio
        asyncio.run(view1.stand_button.callback(mock_interaction1))

        # Should send ephemeral warning and NOT finish
        mock_interaction1.response.send_message.assert_called_once_with(
            "❌ Bạn chưa đủ 16 điểm (điểm dằn tối thiểu) để dằn bài! Vui lòng rút thêm.",
            ephemeral=True
        )
        self.assertFalse(mock_session.player_done.called)

        # Equal to or over 16 points (score 16)
        hand2 = [Card("hearts", 6), Card("spades", 10)]
        view2 = PlayerHandView(mock_player, hand2, mock_deck, mock_session)
        
        mock_interaction2 = AsyncMock()
        mock_button2 = MagicMock()

        asyncio.run(view2.stand_button.callback(mock_interaction2))

        # Should proceed to save and edit message, and notify session player is done
        mock_interaction2.response.edit_message.assert_called_once()
        mock_session.player_done.assert_called_once_with(mock_player, hand2, 16, "stand")

if __name__ == "__main__":
    unittest.main()
