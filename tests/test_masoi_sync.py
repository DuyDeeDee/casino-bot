"""Regression contracts between the engine, live views, DM and replay."""
import asyncio
import time
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from app.discord_bot.cogs import masoi
from app.discord_bot.modules.masoi_delivery import deliver_night
from app.discord_bot.modules.masoi_engine import (
    ActionKind, Faction, GamePhase, MasoiSettings, RankFaction, ReplayLog, Role,
)
from app.discord_bot.modules.masoi_presentation import new_deaths, select_badge, ui_lock
from app.discord_bot.modules.masoi_state import restore_game, snapshot_game
from tests.test_masoi_cog import interaction, make_cog
from tests.test_masoi_engine import make_game, submit


class ObjectiveSyncTests(unittest.TestCase):
    def pair(self, first, second):
        game = make_game(first, second, Role.CUPID, Role.VILLAGER, Role.VILLAGER)
        submit(game, 3, ActionKind.CUPID, 1, 2)
        game.resolve_night()
        return game

    def test_white_wolf_regular_wolf_lovers_end_and_rank_together(self):
        game = self.pair(Role.WHITE_WOLF, Role.WOLF)
        game.apply_deaths((3, 4, 5), "DAY_DEATH")
        self.assertEqual(game.check_win_condition(), Faction.LOVERS)
        self.assertEqual(game.get_rank_faction(1), RankFaction.SOLO)
        self.assertEqual(game.get_rank_faction(2), RankFaction.SOLO)
        self.assertEqual(game.calculate_rank_points(), {1: 30, 2: 30, 3: -15, 4: -15, 5: -15})

    def test_cross_objective_pair_blocks_premature_team_win(self):
        game = self.pair(Role.WOLF, Role.VILLAGER)
        game.players[3].is_alive = game.players[4].is_alive = False
        game.players[5].role = Role.WOLF
        self.assertIsNone(game.check_win_condition())
        self.assertIn("rank Solo", game.lover_goal_text(1))

    def test_paired_piper_cannot_win_without_partner_objective(self):
        game = self.pair(Role.PIPER, Role.VILLAGER)
        for p in game.get_alive_players():
            p.piper_charmed = True
        self.assertIsNone(game.check_win_condition())
        game.apply_deaths((3, 4, 5), "DAY_DEATH")
        self.assertEqual(game.check_win_condition(), Faction.LOVERS)
        self.assertTrue(game.did_player_win(2))

    def test_unpaired_piper_keeps_its_win_condition(self):
        game = self.pair(Role.WOLF, Role.VILLAGER)
        game.players[4].role = Role.PIPER
        for p in game.get_alive_players():
            p.piper_charmed = True
        self.assertEqual(game.check_win_condition(), Faction.PIPER)
        self.assertTrue(game.did_player_win(4))
        self.assertFalse(game.did_player_win(1))

    def test_same_team_pair_keeps_team_objective(self):
        game = self.pair(Role.VILLAGER, Role.VILLAGER)
        self.assertFalse(game.has_lovers_objective(1))
        self.assertEqual(game.get_rank_faction(1), RankFaction.VILLAGER)
        self.assertEqual(game.check_win_condition(), Faction.VILLAGER)

    def test_mixed_objective_survives_conversion_and_snapshot(self):
        game = self.pair(Role.WOLF, Role.CURSED)
        game.players[2].is_cursed_converted = True
        restored = restore_game(snapshot_game(game))
        self.assertTrue(restored.has_lovers_objective(1))
        self.assertEqual(restored.get_rank_faction(2), RankFaction.SOLO)
        self.assertEqual(restored.players[2].lover_objective, True)

    def test_tanner_execution_keeps_documented_instant_win(self):
        game = self.pair(Role.TANNER, Role.VILLAGER)
        game.phase = GamePhase.DAY_RESOLVE
        game.day_votes = {3: 1}
        game.resolve_day_vote()
        self.assertEqual(game.check_win_condition(), Faction.INDEPENDENT)
        self.assertTrue(game.did_player_win(1))
        self.assertFalse(game.did_player_win(2))

    def test_custom_tanner_switch_matches_preview_and_assignment(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 1
        game.settings.custom_special_roles = ["TANNER", "SEER"]
        game.settings.enable_tanner = False
        self.assertTrue(game.settings.tanner_enabled)
        self.assertIn(Role.TANNER, game.preview_roles())
        game.settings.cycle_tanner()
        self.assertFalse(game.settings.tanner_enabled)
        self.assertNotIn(Role.TANNER, game.preview_roles())
        game.settings.cycle_tanner()
        preview = Counter(game.preview_roles())
        game.assign_roles()
        self.assertEqual(Counter(p.role for p in game.players.values()), preview)

    def test_settings_copy_does_not_share_custom_roles(self):
        settings = MasoiSettings()
        settings.custom_special_roles = ["SEER"]
        copied = settings.copy()
        copied.custom_special_roles.append("TANNER")
        self.assertEqual(settings.custom_special_roles, ["SEER"])

    def test_seer_does_not_call_solo_a_villager(self):
        for role in (Role.SERIAL_KILLER, Role.TANNER, Role.PIPER):
            game = make_game(Role.SEER, role, Role.WOLF)
            submit(game, 1, ActionKind.SEER, 2)
            game.resolve_night()
            self.assertIn("KHÔNG THUỘC BẦY SÓI", game.night_seer_result)
            self.assertNotIn("DÂN LÀNG", game.night_seer_result)

    def test_death_batch_includes_hunter_and_lover_without_changing_result(self):
        game = make_game(Role.WOLF, Role.HUNTER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER)
        game.players[3].lover_id, game.players[4].lover_id = 4, 3
        before = set(game.players)
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        result = game.resolve_night()
        game.resolve_hunter_shot(2, 3)
        self.assertEqual(new_deaths(game, before), (2, 3, 4))
        self.assertEqual(result.deaths, (2,))
        self.assertIs(game.resolve_night(), result)


class LiveUISyncTests(unittest.IsolatedAsyncioTestCase):
    def badge_cog(self, game):
        cog = make_cog(game)
        badges = {1: "🔥"}
        eco = Mock()
        eco.get_masoi_custom_badge.side_effect = lambda uid: badges.get(uid, "")
        eco.is_masoi_vip.side_effect = lambda uid: uid == 1
        eco.set_masoi_custom_badge.side_effect = lambda uid, value: badges.__setitem__(uid, value)
        eco.remove_masoi_custom_badge.side_effect = lambda uid: badges.pop(uid, None)
        cog.get_economy.return_value = eco
        return cog, badges, eco

    async def test_vote_badge_preserves_existing_vip_marker(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        cog, _, _ = self.badge_cog(game)
        text = cog.build_vote_embed(game).description
        self.assertIn("• 🔥 <a:2336vipgif:1534596901834592286> **Player 1**", text)
        self.assertIn("• ⚖️ **Player 2**", text)

    async def test_text_badge_does_not_become_invalid_component_emoji(self):
        self.assertEqual(str(select_badge("My custom badge")), "⚖️")
        for emoji in ("🔥", "⏳", "🇻🇳", "👨‍👩‍👧‍👦", "1️⃣", "<a:badge:123456789012345678>"):
            self.assertEqual(str(select_badge(emoji)), emoji)
        self.assertEqual(str(select_badge("🔥⭐")), "⚖️")

    async def test_lobby_badge_refresh_is_preserved(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.LOBBY
        game.message_id = 123
        cog, _, _ = self.badge_cog(game)
        message = SimpleNamespace(edit=AsyncMock())
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
        cog.bot.get_channel = Mock(return_value=channel)
        await cog.refresh_player_badge_lobbies(1)
        self.assertIn("🔥", str(message.edit.call_args.kwargs["embed"].to_dict()))

    async def test_setting_and_removing_badge_refreshes_active_vote_and_menu(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        cog, _, eco = self.badge_cog(game)
        game.day_vote_view = masoi.DayVoteView(game, cog)
        game.day_vote_message = SimpleNamespace(edit=AsyncMock())
        cog.bot.is_owner = AsyncMock(return_value=False)
        cog.bot.emojis, cog.bot.guilds = [], []
        ctx = SimpleNamespace(author=SimpleNamespace(guild_permissions=SimpleNamespace(administrator=True, manage_guild=False)), send=AsyncMock(), prefix="!")
        member = SimpleNamespace(id=1, mention="<@1>", display_name="Player 1")
        await masoi.Masoi.setmasoibadge_cmd.callback(cog, ctx, member, badge="⭐")
        updated = game.day_vote_message.edit.call_args.kwargs
        self.assertIn("⭐", updated["embed"].description)
        self.assertEqual(str(updated["view"].children[0].options[1].emoji), "⭐")
        await masoi.Masoi.removemasoibadge_cmd.callback(cog, ctx, member)
        updated = game.day_vote_message.edit.call_args.kwargs
        self.assertNotIn("⭐", updated["embed"].description)
        self.assertEqual(str(updated["view"].children[0].options[1].emoji), "⚖️")
        eco.set_masoi_vip.assert_not_called()
        game.day_vote_view.stop()

    async def test_end_only_badge_refresh_does_not_leak_counts(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        game.settings.vote_display = "END_ONLY"
        game.day_votes = {1: 2}
        cog, _, _ = self.badge_cog(game)
        game.day_vote_view = masoi.DayVoteView(game, cog)
        game.day_vote_message = SimpleNamespace(edit=AsyncMock())
        await cog.refresh_player_badge_lobbies(1)
        text = game.day_vote_message.edit.call_args.kwargs["embed"].description
        self.assertIn("🔥", text)
        self.assertNotIn("(1 phiếu)", text)
        self.assertNotIn("█", text)
        game.day_vote_view.stop()

    async def test_queued_live_vote_edit_cannot_overwrite_final_phase(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        cog = make_cog(game)
        msg = SimpleNamespace(edit=AsyncMock())
        async with ui_lock(game, "vote"):
            task = asyncio.create_task(cog.update_vote_embed(game, msg))
            await asyncio.sleep(0)
            game.phase = GamePhase.DAY_RESOLVE
        await task
        msg.edit.assert_not_awaited()
        self.assertNotIn("menu bên dưới", cog.build_vote_embed(game, is_final=True).description)

    async def test_day_views_open_only_after_delivery(self):
        for cls, phase, duration in ((masoi.DayDiscussionView, GamePhase.DAY_DISCUSSION, 120), (masoi.DayVoteView, GamePhase.DAY_VOTE, 60)):
            game = make_game(Role.WOLF, Role.VILLAGER)
            game.phase = phase
            view = cls(game, make_cog(game), prepare=True)
            self.assertEqual(view.deadline, 0)
            event = interaction(1)
            event.data = {"values": ["white"]}
            if cls == masoi.DayVoteView:
                await view.vote_callback(event)
                self.assertFalse(game.day_votes)
            else:
                await view.early_vote_btn.callback(event)
                self.assertFalse(game.early_vote_requests)
            before = time.monotonic()
            view.open_actions()
            self.assertGreaterEqual(view.deadline, before + duration)
            view.stop()

    async def test_role_guide_uses_engine_text_and_discord_limits(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        view = masoi.LobbyView(game, make_cog(game))
        event = interaction(1)
        await view.roles_info_btn.callback(event)
        embeds = event.response.send_message.call_args.kwargs["embeds"]
        text = "\n".join(e.description for e in embeds)
        for role in Role:
            if role not in masoi.RETIRED_ROLES:
                self.assertIn(role.description, text)
        for retired in masoi.RETIRED_ROLES:
            self.assertNotIn(f"**{retired.value}**", text)
        self.assertLessEqual(sum(len(e) for e in embeds), 6000)
        self.assertTrue(all(len(e.description) <= 4096 for e in embeds))
        view.stop()

    async def test_full_lobby_badges_fit_field_limits(self):
        game = make_game(*([Role.VILLAGER] * 20))
        cog, badges, _ = self.badge_cog(game)
        for p in game.players.values():
            p.display_name = f"Player{p.user_id}-" + "x" * 24
            badges[p.user_id] = "<a:custom_badge:123456789012345678>"
        embed = cog.build_lobby_embed(game)
        self.assertTrue(all(len(f.value) <= 1024 for f in embed.fields))
        self.assertLessEqual(len(embed), 6000)
        text = "\n".join(f.value for f in embed.fields)
        self.assertTrue(all(p.display_name in text for p in game.players.values()))

    async def test_settings_show_effective_custom_tanner_and_actual_channel(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_special_roles = ["TANNER"]
        cog = make_cog(game)
        embed = cog.build_settings_embed(game)
        self.assertIn("Kẻ Ngốc (Tanner):** `Bật`", embed.description)
        self.assertIn("kênh chơi", embed.description)
        self.assertNotIn("thread", embed.description)
        view = masoi.SettingsView(game, cog, None)
        self.assertIn("Bật", view.btn_tanner.label)
        view.stop()

    async def test_tanner_toggle_also_refreshes_lobby_preview(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        cog = make_cog(game)
        cog.save_game_settings = Mock()
        message = SimpleNamespace(edit=AsyncMock())
        view = masoi.SettingsView(game, cog, message)
        await view.btn_tanner.callback(interaction(game.host_id))
        self.assertTrue(game.settings.tanner_enabled)
        fields = message.edit.call_args.kwargs["embed"].fields
        self.assertTrue(any(Role.TANNER.value in field.value for field in fields))
        view.stop()

    async def test_target_count_dm_and_controls_match_with_one_or_two_targets(self):
        for role, kind, cls in ((Role.INVESTIGATOR, ActionKind.INVESTIGATE, masoi.NightInvestigatorView),):
            for others in (2, 3):
                game = make_game(role, *([Role.VILLAGER] * others))
                game.prepare_night_delivery()
                cog = make_cog(game)
                user = SimpleNamespace(send=AsyncMock())
                cog.get_or_fetch_user.return_value = user
                await deliver_night(cog, game)
                kwargs = user.send.call_args.kwargs
                self.assertIsInstance(kwargs["view"], cls)
                self.assertIn("Chọn đúng 2 người", kwargs["embed"].description)
                self.assertEqual(kwargs["view"].select.min_values, game.required_target_count(kind))
                self.assertEqual(kwargs["view"].select.max_values, 2)
                game.stop_night_views()

    async def test_witch_inflight_wolf_edit_cannot_restore_save_over_poison(self):
        game = make_game(Role.WITCH, Role.WOLF, Role.VILLAGER)
        cog = make_cog(game)
        game.witch_view = masoi.NightWitchView(game, 1, None)
        entered, release = asyncio.Event(), asyncio.Event()
        shown = []
        async def edit(**kwargs):
            if isinstance(kwargs.get("view"), masoi.NightWitchView):
                entered.set()
                await release.wait()
            shown.append(kwargs.get("view"))
        message = SimpleNamespace(edit=edit, embeds=[discord.Embed()])
        game.witch_dm_message = message
        update = asyncio.create_task(cog.update_witch_dm(game))
        await asyncio.wait_for(entered.wait(), 1)
        event = interaction(1)
        event.message = message
        save_view = game.witch_view
        choice = asyncio.create_task(save_view.no_save_callback(event))
        await asyncio.sleep(0)
        event.response.defer.assert_awaited_once()
        release.set()
        await asyncio.wait_for(asyncio.gather(update, choice), 1)
        self.assertIsInstance(shown[-1], masoi.NightWitchPoisonView)
        self.assertIs(game.witch_view, shown[-1])
        self.assertFalse(shown[-1].is_finished())
        game.stop_night_views()

    async def test_witch_dm_uses_remaining_not_full_time(self):
        game = make_game(Role.WITCH, Role.WOLF, Role.VILLAGER)
        game.night_deadline = time.monotonic() + 5
        game.witch_view = masoi.NightWitchView(game, 1, None)
        game.witch_dm_message = interaction(1).message
        await make_cog(game).update_witch_dm(game)
        text = game.witch_dm_message.edit.call_args.kwargs["embed"].description
        self.assertIn("5 giây", text)
        self.assertNotIn("60 giây", text)
        game.stop_night_views()

    async def test_failed_witch_refresh_keeps_delivered_save_view_usable(self):
        game = make_game(Role.WITCH, Role.WOLF, Role.VILLAGER)
        previous = masoi.NightWitchView(game, 1, None)
        game.witch_view = previous
        game.witch_dm_message = SimpleNamespace(edit=AsyncMock(side_effect=RuntimeError("refresh unavailable")))
        with self.assertLogs(masoi.logger, level="WARNING"):
            await make_cog(game).update_witch_dm(game)
        self.assertIs(game.witch_view, previous)
        self.assertFalse(previous.is_finished())
        self.assertTrue(await previous.interaction_check(interaction(1)))
        game.stop_night_views()

    async def test_queued_witch_update_cannot_edit_a_new_night(self):
        game = make_game(Role.WITCH, Role.WOLF, Role.VILLAGER)
        game.witch_view = masoi.NightWitchView(game, 1, None)
        message = SimpleNamespace(edit=AsyncMock())
        game.witch_dm_message = message
        async with ui_lock(game, "witch"):
            task = asyncio.create_task(make_cog(game).update_witch_dm(game))
            await asyncio.sleep(0)
            game.start_night()
            game.witch_dm_message = message
            game.witch_view = masoi.NightWitchView(game, 1, None)
        await task
        message.edit.assert_not_awaited()
        game.stop_night_views()

    async def test_later_night_dm_keeps_couple_goal_visible(self):
        game = make_game(Role.WHITE_WOLF, Role.WOLF, Role.CUPID, Role.VILLAGER, Role.VILLAGER)
        submit(game, 3, ActionKind.CUPID, 1, 2)
        game.resolve_night()
        game.start_night()
        game.prepare_night_delivery()
        cog = make_cog(game)
        users = {uid: SimpleNamespace(send=AsyncMock()) for uid in game.players}
        cog.get_or_fetch_user.side_effect = lambda uid: users[uid]
        await deliver_night(cog, game)
        for uid in (1, 2):
            for call in users[uid].send.call_args_list:
                self.assertIn("2 người sống cuối cùng", call.kwargs["embed"].description)
                self.assertIn("rank Solo", call.kwargs["embed"].description)
        game.stop_night_views()

    async def test_concurrent_early_requests_end_on_current_majority(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        game.phase = GamePhase.DAY_DISCUSSION
        view = masoi.DayDiscussionView(game, make_cog(game))
        first, second = interaction(1), interaction(2)
        entered, release = asyncio.Event(), asyncio.Event()
        labels = []
        async def edit(**kwargs):
            if not entered.is_set():
                entered.set()
                await release.wait()
            labels.append(kwargs["view"].early_vote_btn.label)
        first.message.edit = edit
        second.message.edit = edit
        task1 = asyncio.create_task(view.early_vote_btn.callback(first))
        await asyncio.wait_for(entered.wait(), 1)
        task2 = asyncio.create_task(view.early_vote_btn.callback(second))
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(task1, task2), 1)
        self.assertIn("(2/3)", labels[-1])
        self.assertTrue(view.is_finished())
        first.response.defer.assert_awaited_once()
        second.response.defer.assert_awaited_once()

    async def test_witch_commit_dm_says_visit_did_not_block_potion(self):
        game = make_game(Role.WITCH, Role.HARLOT, Role.VILLAGER)
        submit(game, 1, ActionKind.WITCH_POISON, 3)
        submit(game, 2, ActionKind.HARLOT, 1)
        game.witch_dm_message = interaction(1).message
        game.resolve_night()
        await make_cog(game).close_witch_dm(game)
        kwargs = game.witch_dm_message.edit.call_args.kwargs
        self.assertIn("Đã dùng bình độc", kwargs["embed"].description)
        self.assertIsNone(kwargs["view"])
        self.assertTrue(game.players[1].witch_poison_used)

    async def test_result_dm_without_confirmation_field_still_gets_result(self):
        game = make_game(Role.SEER, Role.WOLF)
        message = SimpleNamespace(embeds=[discord.Embed()], edit=AsyncMock())
        await make_cog(game).update_night_result_dm(message, "Đã bị phong tỏa", "Tiên Tri")
        self.assertIn("Đã bị phong tỏa", message.edit.call_args.kwargs["embed"].fields[0].value)

    async def test_mayor_successor_is_announced_publicly_and_privately(self):
        game = make_game(Role.MAYOR, Role.SEER, Role.WOLF)
        game.players[1].is_alive = False
        game.mayor_id = 1
        cog = make_cog(game)
        new_user = SimpleNamespace(send=AsyncMock())
        async def send_mayor(**kwargs):
            view = kwargs["view"]
            view.selected_target_id = 2
            await view.confirm_callback(interaction(1))
        async def fetch(uid):
            return SimpleNamespace(send=send_mayor) if uid == 1 else new_user
        cog.get_or_fetch_user.side_effect = fetch
        channel = SimpleNamespace(send=AsyncMock())
        await cog.check_and_trigger_mayor_succession(game, channel)
        self.assertEqual(game.mayor_id, 2)
        self.assertEqual(game.players[2].role, Role.SEER)
        self.assertIn("Player 2", channel.send.call_args.kwargs["embed"].description)
        new_user.send.assert_awaited_once()
        self.assertIn("x2", cog.build_vote_embed(game).description)

    async def test_mayor_timeout_clears_vacant_office(self):
        game = make_game(Role.MAYOR, Role.WOLF)
        game.players[1].is_alive = False
        game.mayor_id = 1
        game.settings.night_time = 0
        channel = SimpleNamespace(send=AsyncMock())
        await make_cog(game).check_and_trigger_mayor_succession(game, channel)
        self.assertIsNone(game.mayor_id)
        self.assertIn("x1", channel.send.call_args.kwargs["embed"].description)

    async def test_replay_attacks_do_not_claim_protected_target_died(self):
        for event in ("SERIAL_KILLER_KILL", "WHITE_WOLF_BITE", "WITCH_SAVE", "GUARD_PROTECT"):
            log = ReplayLog(0, "night", event, target_name="Target")
            line = masoi.format_replay_story_line(log)
            self.assertNotIn("hạ gục", line)
            self.assertNotIn("hạ sát", line)
            self.assertNotIn("hồi sinh Target", line)
            self.assertNotIn("an toàn!", line)

    async def test_replay_draw_does_not_claim_victory(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.apply_deaths((1, 2), "NIGHT_DEATH")
        game.check_win_condition()
        view = masoi.ReplayView(game)
        text = "\n".join(p["content"] for p in view.pages)
        self.assertIn("VÁN HÒA", text)
        self.assertNotIn("đã giành thắng lợi", text)
        view.stop()

    async def test_girl_dm_and_committed_replay_use_same_target_result(self):
        game = make_game(Role.THE_GIRL, Role.WOLF, Role.VILLAGER)
        game.night_seed = 2
        submit(game, 1, ActionKind.GIRL)
        submit(game, 2, ActionKind.WOLF_VOTE, 3)
        result = game.resolve_night()
        self.assertIn("Player 3", game.girl_result)
        self.assertIn((1, ActionKind.GIRL.value, game.girl_result), result.outcomes)
        self.assertEqual(next(log.result for log in game.replay_logs if log.event_type == "GIRL_PEEK"), game.girl_result)

    async def test_morning_includes_real_hunter_and_lover_chain(self):
        await self.run_death_chain(day_execution=False)

    async def test_day_execution_includes_real_hunter_and_lover_chain(self):
        await self.run_death_chain(day_execution=True)

    async def run_death_chain(self, *, day_execution):
        game = make_game(Role.WOLF, Role.HUNTER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER)
        game.players[3].lover_id, game.players[4].lover_id = 4, 3
        game.settings.night_time = 0.02
        old_start = game.start_night
        def start():
            old_start()
            if not day_execution:
                submit(game, 1, ActionKind.WOLF_VOTE, 2)
        game.start_night = start
        cog = make_cog(game)
        cog.restore_channel_permissions = AsyncMock()
        cog.sync_channel_permissions = AsyncMock()
        cog.retire_snapshot = Mock()
        async def dm(**kwargs):
            view = kwargs["view"]
            if isinstance(view, masoi.NightHunterView):
                view.selected_target_id = 3
                await view.confirm_callback(interaction(2))
            return SimpleNamespace(edit=AsyncMock(), embeds=[kwargs["embed"]])
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=dm)
        public = []
        async def send(channel, **kwargs):
            embed, view = kwargs.get("embed"), kwargs.get("view")
            public.append(embed)
            if isinstance(view, masoi.DayDiscussionView):
                view.stop()
            if isinstance(view, masoi.DayVoteView):
                game.day_votes = {5: 2}
                view.stop()
            target_title = "Kết Quả Xử Tử" if day_execution else "Ban Ngày — Ngày"
            if target_title in embed.title:
                game.phase = GamePhase.GAME_END
            return SimpleNamespace(edit=AsyncMock(), delete=AsyncMock())
        with patch.object(masoi, "_safe_send", side_effect=send):
            await asyncio.wait_for(cog.game_loop(game, SimpleNamespace(channel=SimpleNamespace())), 2)
        target_title = "Kết Quả Xử Tử" if day_execution else "Ban Ngày — Ngày"
        text = next(e.description for e in public if target_title in e.title)
        for uid in (2, 3, 4):
            self.assertIn(f"Player {uid}", text)
            self.assertFalse(game.players[uid].is_alive)
        self.assertEqual(game._night_result.deaths, () if day_execution else (2,))
