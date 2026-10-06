import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.discord_bot.modules import economy as economy_module
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.masoi_engine import Faction, RankFaction, Role
from app.discord_bot.cogs.masoi import Masoi, RankboardView
from tests.test_masoi_engine import make_game
from tests.test_masoi_cog import make_cog, interaction


class RankRulesTests(unittest.TestCase):
    def test_team_win_and_loss_have_opposite_signs(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.SEER)
        game.winner_faction = Faction.WEREWOLF
        self.assertEqual(game.calculate_rank_points(), {1: 20, 2: -15, 3: -15})
        game.winner_faction = Faction.VILLAGER
        self.assertEqual(game.calculate_rank_points(), {1: -15, 2: 20, 3: 20})

    def test_loss_stays_negative_despite_survival_and_skill_metrics(self):
        game = make_game(Role.GUARD, Role.WOLF)
        game.players[1].guard_saved_count = 100
        game.players[1].seer_found_wolf = True
        game.players[1].witch_useful_use_count = 100
        game.winner_faction = Faction.WEREWOLF
        self.assertEqual(game.calculate_rank_points()[1], -15)

    def test_bonus_only_on_win_and_capped(self):
        game = make_game(Role.GUARD, Role.WOLF)
        game.winner_faction = Faction.VILLAGER
        game.players[1].guard_saved_count = 1
        self.assertEqual(game.calculate_rank_points()[1], 25)
        game.players[1].guard_saved_count = 100
        self.assertEqual(game.calculate_rank_points()[1], 30)

    def test_dead_teammate_still_wins_without_survival_bias(self):
        game = make_game(Role.WOLF, Role.WOLF, Role.VILLAGER)
        game.players[2].is_alive = False
        game.winner_faction = Faction.WEREWOLF
        self.assertEqual(game.calculate_rank_points()[1], game.calculate_rank_points()[2])

    def test_no_winner_or_rank_disabled_means_zero(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        self.assertEqual(game.calculate_rank_points(), {1: 0, 2: 0})
        game.winner_faction = Faction.WEREWOLF
        game.settings.enable_rank = False
        self.assertEqual(game.calculate_rank_points(), {1: 0, 2: 0})

    def test_solo_role_classification_and_wins(self):
        for role, winner in ((Role.TANNER, Faction.INDEPENDENT), (Role.PIPER, Faction.PIPER),
                             (Role.SERIAL_KILLER, Faction.SERIAL_KILLER), (Role.WHITE_WOLF, Faction.WHITE_WOLF)):
            with self.subTest(role=role):
                game = make_game(role, Role.VILLAGER)
                game.winner_faction = winner
                game.tanner_winner_id = 1
                self.assertEqual(game.get_rank_faction(1), RankFaction.SOLO)
                self.assertEqual(game.calculate_rank_points(), {1: 30, 2: -15})

    def test_white_wolf_does_not_win_just_because_wolf_team_wins(self):
        game = make_game(Role.WHITE_WOLF, Role.WOLF, Role.VILLAGER)
        game.winner_faction = Faction.WEREWOLF
        self.assertFalse(game.did_player_win(1))
        self.assertEqual(game.calculate_rank_points()[1], -15)

    def test_converted_cursed_rank_follows_new_faction(self):
        game = make_game(Role.CURSED, Role.WOLF)
        self.assertEqual(game.get_rank_faction(1), RankFaction.VILLAGER)
        game.players[1].is_cursed_converted = True
        self.assertEqual(game.get_rank_faction(1), RankFaction.WOLF)
        game.winner_faction = Faction.WEREWOLF
        self.assertEqual(game.calculate_rank_points()[1], 20)

    def test_cross_faction_lovers_rank_as_solo_even_when_dead(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.CUPID)
        game.players[1].lover_id, game.players[2].lover_id = 2, 1
        for uid in (1, 2):
            self.assertEqual(game.get_rank_faction(uid), RankFaction.SOLO)
        game.players[3].is_alive = False
        game.winner_faction = Faction.LOVERS
        self.assertEqual(game.calculate_rank_points(), {1: 30, 2: 30, 3: -15})
        game.players[1].is_alive = game.players[2].is_alive = False
        game.players[3].is_alive = True
        game.winner_faction = Faction.VILLAGER
        self.assertEqual(game.get_rank_faction(2), RankFaction.SOLO)
        self.assertFalse(game.did_player_win(2))

    def test_same_faction_lovers_keep_team_rank(self):
        game = make_game(Role.GUARD, Role.VILLAGER)
        game.players[1].lover_id, game.players[2].lover_id = 2, 1
        self.assertEqual(game.get_rank_faction(1), RankFaction.VILLAGER)

    def test_lycan_rank_is_village_not_wolf(self):
        game = make_game(Role.LYCAN)
        self.assertEqual(game.get_rank_faction(1), RankFaction.VILLAGER)


class RankDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rank.db"
        # An existing empty DB avoids copying the user's legacy database during open().
        sqlite3.connect(self.path).close()
        self.path_patch = patch.object(economy_module, "DATABASE_PATH", self.path)
        self.path_patch.start()
        self.eco = Economy()

    def tearDown(self):
        self.eco.conn.close()
        self.path_patch.stop()
        self.temp.cleanup()

    def test_three_independent_signed_ranks_and_stats(self):
        self.eco.add_masoi_points(1, 20, True, "WOLF")
        self.eco.add_masoi_points(1, -15, False, "SOLO")
        self.eco.add_masoi_points(1, -15, False, "VILLAGER")
        for faction, points in (("WOLF", 20), ("SOLO", -15), ("VILLAGER", -15)):
            stats = self.eco.get_masoi_rank_stats(1, faction)
            self.assertEqual(stats["points"], points)
            self.assertEqual(stats["plays"], 1)
            self.assertEqual(stats["wins"] + stats["losses"], stats["plays"])
        self.assertEqual(self.eco.get_masoi_stats(1)["points"], -10)

    def test_loss_from_zero_is_not_clamped(self):
        self.eco.add_masoi_points(1, -15, False, "WOLF")
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["points"], -15)

    def test_leaderboard_filters_faction_and_keeps_negative_scores(self):
        self.eco.add_masoi_points(1, -15, False, "WOLF")
        self.eco.add_masoi_points(2, 20, True, "WOLF")
        self.eco.add_masoi_points(3, 30, True, "SOLO")
        self.assertEqual([r[0] for r in self.eco.get_masoi_leaderboard(faction="WOLF")], [2, 1])
        self.assertEqual([r[0] for r in self.eco.get_masoi_leaderboard(faction="SOLO")], [3])
        self.assertEqual(self.eco.get_masoi_leaderboard(faction="VILLAGER"), [])

    def test_results_accumulate_after_multiple_matches(self):
        self.eco.settle_masoi_match("one", [(1, 20, True, "VILLAGER")])
        self.eco.settle_masoi_match("two", [(1, -15, False, "VILLAGER")])
        stats = self.eco.get_masoi_rank_stats(1, "VILLAGER")
        self.assertEqual((stats["points"], stats["plays"], stats["wins"], stats["losses"]), (5, 2, 1, 1))

    def test_match_settled_once(self):
        results = [(1, 20, True, "WOLF"), (2, -15, False, "VILLAGER")]
        self.assertTrue(self.eco.settle_masoi_match("one", results))
        self.assertFalse(self.eco.settle_masoi_match("one", results))
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["plays"], 1)
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 1)

    def test_batch_failure_rolls_back_every_player_and_can_retry(self):
        original = self.eco._write_masoi_result
        def fail_on_second(*result):
            if result[0] == 2:
                raise RuntimeError("database failure")
            original(*result)
        results = [(1, 20, True, "WOLF"), (2, -15, False, "VILLAGER")]
        with patch.object(self.eco, "_write_masoi_result", side_effect=fail_on_second):
            with self.assertRaises(RuntimeError):
                self.eco.settle_masoi_match("retry", results)
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["plays"], 0)
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)
        self.assertTrue(self.eco.settle_masoi_match("retry", results))

    def test_invalid_sign_faction_and_duplicates_rejected(self):
        for delta, won, faction in ((15, False, "WOLF"), (-15, True, "WOLF"), (0, False, "WOLF"), (20, True, "BAD")):
            with self.subTest(delta=delta, won=won, faction=faction), self.assertRaises(ValueError):
                self.eco.add_masoi_points(1, delta, won, faction)
        with self.assertRaises(ValueError):
            self.eco.settle_masoi_match("duplicate", [(1, 20, True, "WOLF"), (1, 20, True, "WOLF")])
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)

    def test_add_masoi_rank_points_admin_single_and_all_factions(self):
        # Adding to single faction
        res = self.eco.add_masoi_rank_points_admin(1, 50, "WOLF")
        self.assertEqual(res["points_delta"], 50)
        self.assertEqual(res["factions"]["WOLF"]["points"], 50)
        self.assertEqual(res["factions"]["WOLF"]["plays"], 1)
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["points"], 50)
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "SOLO")["points"], 0)
        self.assertEqual(self.eco.get_masoi_stats(1)["points"], 50)

        # Adding to ALL factions (default)
        self.eco.add_masoi_rank_points_admin(2, 30, "ALL")
        self.assertEqual(self.eco.get_masoi_rank_stats(2, "WOLF")["points"], 30)
        self.assertEqual(self.eco.get_masoi_rank_stats(2, "SOLO")["points"], 30)
        self.assertEqual(self.eco.get_masoi_rank_stats(2, "VILLAGER")["points"], 30)
        self.assertEqual(self.eco.get_masoi_stats(2)["points"], 30)

        # Subtracting points
        self.eco.add_masoi_rank_points_admin(1, -20, "WOLF")
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["points"], 30)

        # Invalid parameters
        with self.assertRaises(ValueError):
            self.eco.add_masoi_rank_points_admin(-1, 50)
        with self.assertRaises(ValueError):
            self.eco.add_masoi_rank_points_admin(1, 0)
        with self.assertRaises(ValueError):
            self.eco.add_masoi_rank_points_admin(1, 50, "INVALID_FACTION")

    def test_upgrade_preserves_legacy_points_and_badge_without_guessing_factions(self):
        self.eco.cur.execute("INSERT INTO user_masoi_stats(user_id, points, plays, wins, custom_badge) VALUES(1, 999, 10, 8, 'VIP')")
        self.eco.cur.execute("DROP TABLE user_masoi_faction_stats")
        self.eco.cur.execute("DROP TABLE masoi_rank_matches")
        self.eco.cur.execute("UPDATE schema_version SET version=53")
        self.eco.conn.commit()
        self.eco.conn.close()
        self.eco = Economy()
        self.assertEqual(self.eco.get_masoi_stats(1)["points"], 999)
        self.eco.cur.execute("SELECT custom_badge FROM user_masoi_stats WHERE user_id=1")
        self.assertEqual(self.eco.cur.fetchone()[0], "VIP")
        for faction in ("WOLF", "SOLO", "VILLAGER"):
            self.assertEqual(self.eco.get_masoi_rank_stats(1, faction)["points"], 0)
            self.assertEqual(self.eco.get_masoi_leaderboard(faction=faction), [])
        self.eco.cur.execute("SELECT version FROM schema_version")
        self.assertEqual(self.eco.cur.fetchone()[0], economy_module.SCHEMA_VERSION)


class RankUITests(unittest.IsolatedAsyncioTestCase):
    async def test_end_summary_signed_and_uses_personal_faction(self):
        game = make_game(Role.WHITE_WOLF, Role.CURSED, Role.VILLAGER)
        game.players[2].is_cursed_converted = True
        game.winner_faction = Faction.WEREWOLF
        cog = make_cog(game)
        eco = Mock()
        cog.get_economy.return_value = eco
        cog.restore_channel_permissions = AsyncMock()
        channel = SimpleNamespace(send=AsyncMock())
        await cog.end_game(game, SimpleNamespace(channel=channel))
        eco.settle_masoi_match.assert_called_once_with(game.rank_match_id, [(1, -15, False, "SOLO"), (2, 20, True, "WOLF"), (3, -15, False, "VILLAGER")])
        description = channel.send.call_args.kwargs["embed"].description
        self.assertIn("-15 pts", description)
        self.assertIn("+20 pts", description)
        self.assertNotIn("+-", description)

    async def test_cancelled_or_unranked_games_do_not_settle(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        cog = make_cog(game)
        eco = Mock()
        cog.get_economy.return_value = eco
        cog.restore_channel_permissions = AsyncMock()
        channel = SimpleNamespace(send=AsyncMock())
        await cog.end_game(game, SimpleNamespace(channel=channel))
        eco.settle_masoi_match.assert_not_called()
        channel.send.assert_not_awaited()
        game.winner_faction = Faction.WEREWOLF
        game.settings.enable_rank = False
        await cog.end_game(game, SimpleNamespace(channel=channel))
        eco.settle_masoi_match.assert_not_called()

    async def test_summary_and_buttons_use_correct_boards(self):
        game = make_game(Role.WOLF)
        cog = make_cog(game)
        eco = Mock()
        eco.get_masoi_leaderboard.side_effect = lambda **kwargs: [(1, -15, 1, 0)] if kwargs["faction"] == "SOLO" else []
        cog.get_economy.return_value = eco
        embed = cog.build_rankboard_embed()
        self.assertEqual(len(embed.fields), 3)
        self.assertIn("-15 pts", embed.fields[1].value)
        view = RankboardView(cog)
        event = interaction(1)
        await view.solo_btn.callback(event)
        selected = event.response.edit_message.call_args.kwargs["embed"]
        self.assertIn("Solo", selected.title)
        self.assertIn("-15 pts", selected.description)
        view.stop()

    async def test_rank_command_accepts_alias_and_rejects_unknown_faction(self):
        cog = make_cog(make_game(Role.WOLF))
        cog.build_rankboard_embed = Mock(return_value=None)
        ctx = SimpleNamespace(send=AsyncMock())
        await Masoi.masoirank_cmd.callback(cog, ctx, "sói")
        cog.build_rankboard_embed.assert_called_once_with(RankFaction.WOLF)
        ctx.send.call_args.kwargs["view"].stop()
        await Masoi.masoirank_cmd.callback(cog, ctx, "invalid")
        self.assertIn("Chọn bảng rank", ctx.send.call_args.args[0])

    async def test_addmasoirank_command_permissions_and_execution(self):
        cog = make_cog(make_game(Role.WOLF))
        cog.bot = SimpleNamespace(get_user=Mock(return_value=None), fetch_user=AsyncMock(return_value=None), is_owner=AsyncMock(return_value=False))
        eco = Mock()
        eco.add_masoi_rank_points_admin.return_value = {
            "user_id": 123456,
            "points_delta": 50,
            "factions": {"WOLF": {"points": 50, "plays": 1, "wins": 0, "losses": 0}},
            "total_points": 50,
        }
        cog.get_economy.return_value = eco

        # Unauthorized user
        unauth_ctx = SimpleNamespace(
            author=SimpleNamespace(id=99999, guild_permissions=SimpleNamespace(administrator=False, manage_guild=False)),
            send=AsyncMock(),
            prefix="!",
        )
        await Masoi.addmasoirank_cmd.callback(cog, unauth_ctx, "<@123456>", "50", "soi")
        unauth_ctx.send.assert_called_once()
        self.assertIn("Chỉ có Admin hoặc Owner", unauth_ctx.send.call_args.args[0])
        eco.add_masoi_rank_points_admin.assert_not_called()

        # Authorized server admin user
        admin_ctx = SimpleNamespace(
            author=SimpleNamespace(id=88888, guild_permissions=SimpleNamespace(administrator=True, manage_guild=True)),
            send=AsyncMock(),
            prefix="!",
        )
        await Masoi.addmasoirank_cmd.callback(cog, admin_ctx, "<@123456>", "50", "soi")
        eco.add_masoi_rank_points_admin.assert_called_once_with(123456, 50, "WOLF")
        self.assertIn("embed", admin_ctx.send.call_args.kwargs)
        embed = admin_ctx.send.call_args.kwargs["embed"]
        self.assertIn("CỘNG ĐIỂM RANK MA SÓI THÀNH CÔNG", embed.title)
