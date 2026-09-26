"""Durable checkpoints and startup recovery; intentionally no VIP/refund policy."""
from __future__ import annotations
import asyncio
import json
import logging
import discord
from app.discord_bot.modules.masoi_engine import Faction, GamePhase
from app.discord_bot.modules.masoi_rank import MasoiRankService
from app.discord_bot.modules.masoi_state import restore_game, snapshot_game

logger = logging.getLogger(__name__)


class MasoiRecoveryMixin:
    async def cog_load(self):
        self._persistence_enabled = True
        self._recovering_channels = set()
        self._recovery_ready = False
        economy = self.get_economy()
        if economy is None:
            raise RuntimeError("Ma Sói requires the economy database for recovery")
        for row in economy.get_masoi_sessions():
            self._recovering_channels.add(f"{row['guild_id']}-{row['channel_id']}")
        self._recovery_ready = True
        self._recovery_task = asyncio.create_task(self._recovery_worker(), name="masoi-recovery")

    async def cog_unload(self):
        task = getattr(self, "_recovery_task", None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for game in tuple(self.active_games.values()):
            try:
                self.checkpoint_game(game)
            except Exception:
                logger.exception("Could not checkpoint Ma Sói on unload")
            game.stop_night_views()
        # Snapshots remain for the next load. No refunds or rank losses here.
        for task in tuple(getattr(self, "_game_tasks", {}).values()):
            task.cancel()
        if getattr(self, "_game_tasks", None):
            await asyncio.gather(*self._game_tasks.values(), return_exceptions=True)

    def checkpoint_game(self, game):
        if not getattr(self, "_persistence_enabled", False):
            return
        economy = self.get_economy()
        if economy is None:
            raise RuntimeError("Cannot persist Ma Sói without database")
        economy.save_masoi_session(snapshot_game(game))

    def attach_checkpoint(self, game):
        game.checkpoint_hook = self.checkpoint_game
        self.checkpoint_game(game)

    def retire_snapshot(self, game):
        if not getattr(self, "_persistence_enabled", False):
            return
        economy = self.get_economy()
        if economy is None:
            return
        requires_rank = bool(game.winner_faction and game.winner_faction != Faction.DRAW and game.settings.enable_rank)
        key = f"{game.guild_id}-{game.channel_id}"
        announced = not game.winner_faction or getattr(game, "result_announced", False)
        if not game.channel_permission_snapshots and (not requires_rank or game.rank_settled) and announced:
            economy.finish_masoi_session(snapshot_game(game))
            self._recovering_channels.discard(key)
        else:
            self.checkpoint_game(game)
            self._recovering_channels.add(key)

    async def _recovery_worker(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.recover_pending_games()
            except Exception:
                logger.exception("Ma Sói recovery worker failed; retrying later")
            await asyncio.sleep(30)

    async def recover_pending_games(self):
        economy = self.get_economy()
        if economy is None:
            return
        for row in economy.get_masoi_sessions():
            key = f"{row['guild_id']}-{row['channel_id']}"
            if key in self.active_games:
                continue  # Never restore permissions while a live match owns the channel.
            self._recovering_channels.add(key)
            try:
                data = json.loads(row["state_json"])
                game = restore_game(data)
                if game.rank_match_id != row["match_id"] or (game.guild_id, game.channel_id) != (row["guild_id"], row["channel_id"]):
                    raise ValueError("Snapshot identity mismatch")
                if game.winner_faction and game.settings.enable_rank and game.winner_faction != Faction.DRAW:
                    # Completed-only replay; no active match is awarded or penalized.
                    MasoiRankService.settle(game, economy)
                game.phase = GamePhase.GAME_END
                game.recovering = True
                channel = self.bot.get_channel(game.channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(game.channel_id)
                    except discord.NotFound:
                        # The channel no longer exists; permission restoration is unnecessary.
                        game.channel_permission_snapshots.clear()
                        game.result_announced = True
                        self.retire_snapshot(game)
                        continue
                if not isinstance(channel, discord.TextChannel) or channel.guild.id != game.guild_id:
                    raise RuntimeError("Recovery channel unavailable or guild mismatched")
                # Keep an updated durable copy if restoration is only partially successful.
                game.checkpoint_hook = self.checkpoint_game
                await self.restore_channel_permissions(game, channel)
                if game.channel_permission_snapshots:
                    self.checkpoint_game(game)
                    continue
                if not data.get("recovery_notified") and not data.get("result_announced"):
                    text = ("🔄 Đã phục hồi ván Ma Sói hòa; không cộng/trừ rank."
                            if game.winner_faction == Faction.DRAW else
                            "🔄 Đã phục hồi kết quả Ma Sói đã chốt; rank được lưu đúng một lần."
                            if game.winner_faction else
                            "🔄 Ván Ma Sói trước đã bị gián đoạn do bot restart và được hủy an toàn. Quyền chat đã khôi phục; không cộng/trừ rank.")
                    await channel.send(text)
                    game.recovery_notified = True
                    game.result_announced = True
                    self.checkpoint_game(game)
                if game.message_id:
                    try:
                        old_message = await channel.fetch_message(game.message_id)
                        await old_message.edit(view=None)
                    except discord.NotFound:
                        pass
                self.retire_snapshot(game)
            except Exception:
                # Never delete a failed/corrupt snapshot or silently unlock its channel.
                logger.exception("Cannot recover Ma Sói match %s; snapshot retained", row["match_id"])
