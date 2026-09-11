import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.discord_bot.cogs.hopy import HopyAnswerModal
from app.discord_bot.modules.hopy_engine import GamePhase, HopyGame


def make_question_game(player_count: int = 2) -> HopyGame:
    game = HopyGame(channel_id=123, host_id=1, host_name="Player 1")
    for user_id in range(2, player_count + 1):
        game.add_player(user_id, f"Player {user_id}")
    game.current_round = 1
    game.total_rounds = 3
    game.current_question = {
        "id": "test_question",
        "question": "Test?",
        "synonyms": {},
    }
    game.phase = GamePhase.QUESTION
    return game


class TestHopyMatching(unittest.TestCase):
    def test_answers_sharing_one_word_receive_points(self):
        game = make_question_game(player_count=4)
        game.submit_answer(1, "Trà sữa")
        game.submit_answer(2, "trà đá")
        game.submit_answer(3, "đá xay")
        game.submit_answer(4, "cà phê")

        evaluation = game.evaluate_round()

        # Player 2 khớp trực tiếp với hai người; player 1 và 3 chỉ khớp một người.
        self.assertEqual(game.players[1].round_scores[1], 10)
        self.assertEqual(game.players[2].round_scores[1], 12)
        self.assertEqual(game.players[3].round_scores[1], 10)
        self.assertEqual(game.players[4].round_scores[1], 0)
        self.assertEqual({s["player"].user_id for s in evaluation.solos}, {4})
        self.assertEqual(set(evaluation.matched_groups[0]["shared_words"]), {"trà", "đá"})

    def test_synonym_exact_match_keeps_dai_hop_y_bonus(self):
        game = make_question_game()
        game.current_question["synonyms"] = {"trà sữa": ["tra sua"]}
        game.submit_answer(1, "trà sữa")
        game.submit_answer(2, "tra sua")

        evaluation = game.evaluate_round()

        self.assertTrue(evaluation.is_dai_hop_y)
        self.assertEqual(game.players[1].score, 30)
        self.assertEqual(game.players[2].score, 30)

    def test_evaluate_round_is_idempotent(self):
        game = make_question_game()
        game.submit_answer(1, "giống nhau")
        game.submit_answer(2, "giống nhau")
        # Game loop chuyển sang REVEALING trước khi gọi evaluate_round.
        game.phase = GamePhase.REVEALING

        first = game.evaluate_round()
        score_after_first = game.players[1].score
        second = game.evaluate_round()

        self.assertIs(first, second)
        self.assertEqual(game.players[1].score, score_after_first)

    def test_no_answers_is_not_reported_as_all_solos(self):
        game = make_question_game()

        evaluation = game.evaluate_round()

        self.assertEqual(len(evaluation.no_answers), 2)
        self.assertFalse(evaluation.is_all_solos)


class TestHopyStaleModal(unittest.IsolatedAsyncioTestCase):
    async def test_modal_from_previous_round_is_rejected(self):
        game = make_question_game()
        cog = SimpleNamespace()
        cog.is_current_game = lambda candidate: candidate is game
        cog.refresh_question_embed = AsyncMock()

        modal = HopyAnswerModal(cog, game, user_id=1)
        modal.answer_input._value = "đáp án vòng cũ"

        game.current_round = 2
        game.current_question = {
            "id": "next_question",
            "question": "Next?",
            "synonyms": {},
        }
        game.round_raw_answers.clear()

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=1),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        await modal.on_submit(interaction)

        self.assertNotIn(1, game.round_raw_answers)
        interaction.response.send_message.assert_awaited_once()
        cog.refresh_question_embed.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
