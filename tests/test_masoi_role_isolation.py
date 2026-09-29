"""CUSTOM role choices never leak from a VIP lobby to the next host."""
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.discord_bot.cogs import masoi
from app.discord_bot.modules.masoi_engine import GamePhase, MasoiSettings, Role
from tests.test_masoi_cog import interaction, make_cog
from tests.test_masoi_engine import make_game


class RolePreferenceIsolationTests(unittest.TestCase):
    def test_shared_save_keeps_general_settings_but_never_custom_roles(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 2
        game.settings.custom_special_roles = ["SEER", "GUARD"]
        game.settings.vote_display = "END_ONLY"
        game.settings.enable_rank = False
        cog = make_cog(game)
        cog.saved_settings = {}
        cog.save_settings_to_file = Mock()

        cog.save_game_settings(game)

        self.assertEqual(game.settings.role_setup_mode, "CUSTOM")
        self.assertEqual(game.settings.custom_wolf_count, 2)
        self.assertEqual(game.settings.custom_special_roles, ["SEER", "GUARD"])
        for key in ("1-2", "1"):
            saved = cog.saved_settings[key]
            self.assertEqual(saved.role_setup_mode, "AUTO")
            self.assertEqual(saved.custom_wolf_count, MasoiSettings().custom_wolf_count)
            self.assertEqual(saved.custom_special_roles, [])
            self.assertEqual(saved.vote_display, "END_ONLY")
            self.assertFalse(saved.enable_rank)
        for channel in (2, 3):
            next_room = cog.get_saved_settings(1, channel)
            self.assertEqual(next_room.role_setup_mode, "AUTO")
            self.assertEqual(next_room.custom_special_roles, [])
            self.assertEqual(Counter(make_preview(next_room)), Counter([Role.WOLF, Role.SEER, Role.GUARD, Role.MAYOR, Role.VILLAGER]))

    def test_legacy_shared_custom_data_is_sanitized_on_read(self):
        game = make_game(*([Role.VILLAGER] * 5))
        cog = make_cog(game)
        old = MasoiSettings.from_dict({
            "role_setup_mode": "CUSTOM", "custom_wolf_count": 4,
            "custom_special_roles": ["WOLF_SEER", "MAYOR"], "dead_can_chat": True,
        })
        cog.saved_settings = {"1-2": old, "1": old}
        for channel in (2, 9):
            new = cog.get_saved_settings(1, channel)
            self.assertEqual(new.role_setup_mode, "AUTO")
            self.assertEqual(new.custom_special_roles, [])
            self.assertEqual(new.custom_wolf_count, 2)
            self.assertTrue(new.dead_can_chat)
        self.assertEqual(old.role_setup_mode, "CUSTOM")  # Read has no side effect on old data.


def make_preview(settings):
    game = make_game(*([Role.VILLAGER] * 5))
    game.settings = settings
    return game.preview_roles()


class RoleGateTests(unittest.IsolatedAsyncioTestCase):
    def lobby(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 2
        game.settings.custom_special_roles = ["SEER"]
        cog = make_cog(game)
        cog.get_economy.return_value = SimpleNamespace(is_masoi_vip=Mock(return_value=False))
        message = SimpleNamespace(edit=AsyncMock(), channel=SimpleNamespace(send=AsyncMock()))
        return game, cog, message

    async def test_new_nonvip_room_from_legacy_custom_pref_uses_auto_roles(self):
        game, cog, _ = self.lobby()
        cog.active_games = {}
        cog.saved_settings = {"1-2": game.settings.copy()}
        cog._recovery_ready = True
        eco = Mock()
        eco.is_masoi_vip.return_value = False
        eco.get_entry.return_value = (1, 20_000)
        eco.get_masoi_custom_badge.return_value = ""
        cog.get_economy.return_value = eco
        ctx = SimpleNamespace(
            guild=SimpleNamespace(id=1), channel=SimpleNamespace(id=2),
            author=SimpleNamespace(id=99, display_name="Next host"), prefix="!",
            send=AsyncMock(return_value=SimpleNamespace(id=42)),
        )
        await masoi.Masoi.masoi_cmd.callback(cog, ctx)
        created = cog.active_games["1-2"]
        self.assertEqual(created.host_id, 99)
        self.assertEqual(created.settings.role_setup_mode, "AUTO")
        self.assertEqual(created.settings.custom_special_roles, [])
        self.assertEqual(Counter(created.preview_roles()), Counter([Role.WOLF, Role.SEER, Role.GUARD, Role.MAYOR, Role.VILLAGER]))
        eco.add_money.assert_called_once_with(99, -masoi.MASOI_CREATE_FEE)
        ctx.send.call_args.kwargs["view"].stop()

    async def test_start_rejects_custom_for_nonvip_without_assigning_or_locking_lobby(self):
        game, cog, message = self.lobby()
        game.assign_roles = Mock(wraps=game.assign_roles)
        cog.game_loop = AsyncMock()
        await cog.start_game(game, message)
        self.assertEqual(game.phase, GamePhase.LOBBY)
        self.assertEqual(game.settings.role_setup_mode, "CUSTOM")
        game.assign_roles.assert_not_called()
        cog.game_loop.assert_not_awaited()
        cog.get_or_fetch_user.assert_not_awaited()
        self.assertIn("CUSTOM", message.channel.send.call_args.args[0])
        restored_view = message.edit.call_args.kwargs["view"]
        self.assertIsInstance(restored_view, masoi.LobbyView)
        restored_view.stop()

    async def test_start_fails_closed_when_vip_database_unavailable(self):
        game, cog, message = self.lobby()
        cog.get_economy.return_value = None
        await cog.start_game(game, message)
        self.assertEqual(game.phase, GamePhase.LOBBY)
        self.assertIn("CUSTOM", message.channel.send.call_args.args[0])
        message.edit.call_args.kwargs["view"].stop()

    async def test_nonvip_host_can_leave_custom_but_cannot_enter_again(self):
        game, cog, message = self.lobby()
        cog.save_game_settings = Mock()
        cog.update_lobby_embed = AsyncMock()
        parent = masoi.SettingsView(game, cog, message)
        view = masoi.CustomRolesConfigView(game, cog, parent, message)
        try:
            await view.toggle_mode_callback(interaction(game.host_id))
            self.assertEqual(game.settings.role_setup_mode, "AUTO")
            cog.save_game_settings.assert_called_once_with(game)
            second = interaction(game.host_id)
            await view.toggle_mode_callback(second)
            self.assertEqual(game.settings.role_setup_mode, "AUTO")
            second.response.send_message.assert_awaited_once()
            self.assertEqual(cog.save_game_settings.call_count, 1)
        finally:
            view.stop()
            parent.stop()

    async def test_nonvip_cannot_select_wolves_even_if_old_custom_view_is_open(self):
        game, cog, message = self.lobby()
        parent = masoi.SettingsView(game, cog, message)
        view = masoi.CustomRolesConfigView(game, cog, parent, message)
        try:
            view.select_wolves._values = ["4"]
            event = interaction(game.host_id)
            await view.wolves_callback(event)
            self.assertEqual(game.settings.custom_wolf_count, 2)
            self.assertEqual(game.settings.role_setup_mode, "CUSTOM")
            event.response.send_message.assert_awaited_once()
        finally:
            view.stop()
            parent.stop()

    async def test_current_vip_can_still_start_their_valid_custom_room(self):
        game, cog, message = self.lobby()
        eco = SimpleNamespace(is_masoi_vip=Mock(return_value=True))
        cog.get_economy.return_value = eco
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock())
        cog.game_loop = AsyncMock()
        game.assign_roles = Mock(wraps=game.assign_roles)
        await cog.start_game(game, message)
        game.assign_roles.assert_called_once()
        eco.is_masoi_vip.assert_called_with(game.host_id)
        self.assertEqual(Counter(p.role for p in game.players.values()), Counter([Role.WOLF, Role.WOLF, Role.SEER, Role.VILLAGER, Role.VILLAGER]))
        cog.game_loop.assert_awaited_once()

    async def test_vip_expiring_during_dm_preflight_prevents_role_assignment(self):
        game, cog, message = self.lobby()
        eco = SimpleNamespace(is_masoi_vip=Mock(side_effect=[True, False]))
        cog.get_economy.return_value = eco
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock())
        game.assign_roles = Mock(wraps=game.assign_roles)
        cog.game_loop = AsyncMock()
        await cog.start_game(game, message)
        self.assertEqual(eco.is_masoi_vip.call_count, 2)
        self.assertEqual(game.phase, GamePhase.LOBBY)
        game.assign_roles.assert_not_called()
        cog.game_loop.assert_not_awaited()
        self.assertIn("CUSTOM", message.channel.send.call_args.args[0])
        message.edit.call_args.kwargs["view"].stop()

    async def test_auto_setup_does_not_require_vip_for_start(self):
        game, cog, message = self.lobby()
        game.settings.role_setup_mode = "AUTO"
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock())
        cog.game_loop = AsyncMock()
        await cog.start_game(game, message)
        cog.get_economy.return_value.is_masoi_vip.assert_not_called()
        cog.game_loop.assert_awaited_once()
