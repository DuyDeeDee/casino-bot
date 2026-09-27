"""Non-VIP game orchestration separated from command and settings handlers."""
from __future__ import annotations
import asyncio
import logging
import time
import discord
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.masoi_engine import Faction, GamePhase, MasoiGame, Role
from app.discord_bot.modules.masoi_delivery import deliver_night, NightDeliveryError
from app.discord_bot.modules.masoi_rank import MasoiRankService
from app.discord_bot.modules.masoi_presentation import ui_lock, new_deaths
from app.discord_bot.modules.masoi_ui import (
    NightHunterView, MayorSuccessionView, DayDiscussionView, DayVoteView, GameEndView,
)
logger = logging.getLogger("app.discord_bot.cogs.masoi")


async def _safe_send(*args, **kwargs):
    # Keep the cog facade patchable for existing callers/tests.
    from app.discord_bot.cogs.masoi import _safe_send as send
    return await send(*args, **kwargs)


def LobbyView(game, cog):
    from app.discord_bot.cogs.masoi import LobbyView as view
    return view(game, cog)


class MasoiFlowMixin:
    async def check_and_trigger_hunter(self, game: MasoiGame, channel: discord.TextChannel):
        """Kiểm tra và kích hoạt lượt bắn kéo theo của Thợ Săn khi bị loại (hỗ trợ bắn dây chuyền)."""
        while True:
            pending_hunters = [
                p for p in game.players.values()
                if p.role == Role.HUNTER and not p.is_alive and not getattr(p, "hunter_shot_used", False)
            ]
            if not pending_hunters:
                break

            for p in pending_hunters:
                h_user = await self.get_or_fetch_user(p.user_id)
                view = NightHunterView(game, p.user_id)
                hunter_shot_target_id = None
                if not h_user:
                    view.stop()
                    raise NightDeliveryError(f"Không gửi được lượt bắn cho Thợ Săn {p.display_name}; ván không tính rank.")

                if h_user:
                    embed_hunter = discord.Embed(
                        title="🏹 Lượt của Thợ Săn — Kéo theo 1 người",
                        description=f"Bạn đã bị loại! Hãy chọn 1 người để kéo theo chết cùng. Còn **{game.settings.night_time} giây** để quyết định.",
                        color=discord.Color(0xE0A638)
                    )
                    try:
                        await asyncio.wait_for(h_user.send(embed=embed_hunter, view=view), timeout=15)
                        view.deadline = time.monotonic() + game.settings.night_time
                        elapsed = 0
                        while elapsed < game.settings.night_time:
                            if view.is_finished() or game.phase == GamePhase.GAME_END:
                                break
                            await asyncio.sleep(1)
                            elapsed += 1
                        if view.is_finished():
                            hunter_shot_target_id = view.confirmed_target_id
                    except Exception as exc:
                        view.stop()
                        raise NightDeliveryError(f"Lỗi DM lượt Thợ Săn {p.display_name}; ván không tính rank.") from exc

                view.stop()
                p.hunter_shot_used = True
                # Thông báo kết quả ra channel chính
                if hunter_shot_target_id:
                    shot_p = game.players.get(hunter_shot_target_id)
                    if shot_p:
                        role_str = f" *({shot_p.role.emoji} {shot_p.role.value})*" if game.settings.reveal_roles_on_death else ""
                        embed_announce = discord.Embed(
                            title="🏹 Thợ Săn Kéo Theo!",
                            description=(
                                f"🏹 {self.player_label(p)} dùng phát bắn cuối cùng kéo theo "
                                + f"{self.player_label(shot_p)}{role_str} cùng ra đi!"
                            ),
                            color=discord.Color(0xE0A638)
                        )
                        await _safe_send(channel, embed=embed_announce)
                else:
                    embed_announce = discord.Embed(
                        title="🏹 Thợ Săn",
                        description=f"🏹 {self.player_label(p)} đã không dùng phát bắn cuối cùng.",
                        color=discord.Color(0xE0A638)
                    )
                    await _safe_send(channel, embed=embed_announce)


    async def check_and_trigger_mayor_succession(self, game: MasoiGame, channel: discord.TextChannel):
        """Kiểm tra nếu Thị Trưởng vừa qua đời -> Gửi DM cho Thị Trưởng chọn người kế nhiệm."""
        if game.mayor_id:
            mayor_p = game.players.get(game.mayor_id)
            if mayor_p and not mayor_p.is_alive and not getattr(mayor_p, "mayor_passed_succession", False):
                mayor_p.mayor_passed_succession = True
                m_user = await self.get_or_fetch_user(mayor_p.user_id)
                if not m_user:
                    raise NightDeliveryError(f"Không gửi được lượt kế nhiệm cho {mayor_p.display_name}; ván không tính rank.")
                if m_user:
                    embed_mayor = discord.Embed(
                        title="🎩 Thị Trưởng Qua Đời — Truyền Ngôi Kế Nhiệm",
                        description=f"Bạn đã qua đời! Hãy chọn 1 người chơi còn sống để trao lại chiếc mũ **Thị Trưởng (Vote x2)**. Còn **{game.settings.night_time} giây** để quyết định.",
                        color=discord.Color.gold()
                    )
                    view = MayorSuccessionView(game, mayor_p.user_id)
                    try:
                        await asyncio.wait_for(m_user.send(embed=embed_mayor, view=view), timeout=15)
                        view.deadline = time.monotonic() + game.settings.night_time
                        elapsed = 0
                        while elapsed < game.settings.night_time:
                            if view.is_finished() or game.phase == GamePhase.GAME_END:
                                break
                            await asyncio.sleep(1)
                            elapsed += 1
                    except Exception as exc:
                        raise NightDeliveryError(f"Lỗi DM lượt kế nhiệm của {mayor_p.display_name}; ván không tính rank.") from exc
                    finally:
                        view.stop()
                    if game.phase == GamePhase.GAME_END:
                        return
                    successor = game.players.get(game.mayor_id)
                    if successor and successor.is_alive and successor.user_id != mayor_p.user_id:
                        await _safe_send(channel, embed=discord.Embed(
                            title="🎩 Thị Trưởng Kế Nhiệm",
                            description=f"{self.player_label(successor)} đã nhận chức Thị Trưởng. Phiếu bầu từ nay tính **x2**, vai trò gốc không thay đổi.",
                            color=discord.Color.gold(),
                        ))
                        new_user = await self.get_or_fetch_user(successor.user_id)
                        if new_user:
                            try:
                                await asyncio.wait_for(new_user.send("🎩 Bạn là Thị Trưởng kế nhiệm! Phiếu bầu ban ngày tính x2; vai trò và kỹ năng gốc giữ nguyên."), timeout=15)
                            except Exception:
                                logger.warning("Không gửi được DM thông báo kế nhiệm cho %s", successor.user_id)
                    else:
                        game.mayor_id = None
                        game.record_log("MAYOR_VACANT", actor_id=mayor_p.user_id, result="Không có người kế nhiệm; mọi phiếu còn lại tính x1.")
                        await _safe_send(channel, embed=discord.Embed(title="🎩 Chức Thị Trưởng Đang Trống", description="Không chọn được người kế nhiệm. Mọi phiếu bầu còn lại tính x1.", color=discord.Color.gold()))


    async def start_game(self, game: MasoiGame, message: discord.Message):
        if game.phase != GamePhase.LOBBY:
            return
        setup_errors = game.validate_role_setup()
        if setup_errors:
            game.phase = GamePhase.LOBBY
            await message.edit(view=LobbyView(game, self))
            await message.channel.send(
                "❌ **Cấu hình vai trò không hợp lệ:**\n• " + "\n• ".join(setup_errors)
                + "\nHãy chỉnh cài đặt rồi thử bắt đầu lại."
            )
            return

        # Lock the lobby across awaited preflight calls.
        game.phase = GamePhase.ROLE_ASSIGN
        dm_failures = []
        for player in tuple(game.players.values()):
            if game.phase == GamePhase.GAME_END:
                return
            user = await self.get_or_fetch_user(player.user_id)
            if not user:
                dm_failures.append(player.display_name)
                continue
            try:
                await asyncio.wait_for(user.send("🔔 Ván Ma Sói sắp bắt đầu. Tin nhắn này xác nhận bot có thể gửi DM hành động cho bạn."), timeout=15)
            except (discord.Forbidden, asyncio.TimeoutError):
                dm_failures.append(player.display_name)
            except discord.HTTPException as e:
                logger.warning("Không thể kiểm tra DM cho user %s: %s", player.user_id, e)
                dm_failures.append(player.display_name)

        if game.phase == GamePhase.GAME_END:
            return
        if dm_failures:
            game.phase = GamePhase.LOBBY
            await message.edit(view=LobbyView(game, self))
            await message.channel.send(
                "❌ Chưa thể bắt đầu vì bot không gửi được DM tới: **"
                + ", ".join(dm_failures)
                + "**. Họ cần mở DM từ thành viên server rồi Host có thể thử lại."
            )
            return

        game.phase = GamePhase.ROLE_ASSIGN
        game.cog = self
        try:
            self.attach_checkpoint(game)
            game.assign_roles()
            game.checkpoint()
        except Exception:
            game.phase = GamePhase.GAME_END
            self.active_games.pop(f"{game.guild_id}-{game.channel_id}", None)
            logger.exception("Không thể lưu trạng thái Ma Sói trước khi phân vai")
            await message.channel.send("❌ Không thể lưu trạng thái ván. Ván đã hủy, không tính rank.")
            return

        # DM vai trò riêng cho từng người
        role_dm_failures = []
        for p in game.players.values():
            if game.phase == GamePhase.GAME_END:
                return
            user = await self.get_or_fetch_user(p.user_id)
            if user:
                extra_info = ""
                if p.is_wolf:
                    wolves = [other.display_name for other in game.players.values() if other.is_wolf and other.user_id != p.user_id]
                    if wolves:
                        extra_info = f" · Đồng đội Sói: {', '.join(wolves)}"
                    else:
                        extra_info = " · Bạn là Sói duy nhất ván này"

                faction_name = p.role.faction.value.replace(" 🐺", "").replace(" 👥", "").replace(" 🃏", "").replace(" 💘", "")

                dm_text = (
                    f"> {p.role.emoji} **Vai trò của bạn: {p.role.value}**\n"
                    f"> {faction_name} · {p.role.description}{extra_info}"
                )
                try:
                    await asyncio.wait_for(user.send(dm_text), timeout=15)
                except Exception:
                    role_dm_failures.append(p.display_name)
                    logger.warning("Không thể DM riêng cho user %s", p.user_id)
            else:
                role_dm_failures.append(p.display_name)

        if role_dm_failures:
            game.phase = GamePhase.GAME_END
            self.active_games.pop(f"{game.guild_id}-{game.channel_id}", None)
            self.retire_snapshot(game)
            await message.channel.send("❌ Không gửi được vai trò tới: " + ", ".join(role_dm_failures) + ". Ván đã hủy, không tính rank.")
            return
        if game.phase == GamePhase.GAME_END:
            return
        # Chạy vòng lặp game
        await self.game_loop(game, message)

    async def game_loop(self, game: MasoiGame, message: discord.Message):
        key = f"{game.guild_id}-{game.channel_id}"
        divider = "──────────────────────────────────────"

        try:
            while game.phase != GamePhase.GAME_END:
                # Guard: Kiểm tra xem game có bị force-stop từ bên ngoài không
                if self.active_games.get(key) is not game:
                    logger.info("Game %s đã bị dừng từ bên ngoài, thoát game_loop.", key)
                    return

                # ── BƯỚC 1: ĐÊM ──
                game.start_night()
                game.prepare_night_delivery()

                await deliver_night(self, game)
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                embed_night = discord.Embed(
                    title=f"<a:moon:1533444241596874792> Ban Đêm — Đêm {game.night_count}",
                    description=(
                        f"Màn đêm đã buông xuống làng...\n"
                        f"Bot đã gửi tin nhắn riêng (DM) tới các vai trò ban đêm để hành động!\n\n"
                        f"{divider}\n⏱️ **Thời gian đêm:** `{game.settings.night_time}s`"
                    ),
                    color=discord.Color(0xE0A638)
                )
                night_msg = await _safe_send(message.channel, embed=embed_night)
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break
                game.open_night_actions()

                # Chờ hết thời gian ban đêm
                while time.monotonic() < game.night_deadline:
                    if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(min(1, max(0, game.night_deadline - time.monotonic())))

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                game.lock_night()
                try:
                    await night_msg.delete()
                except Exception:
                    pass

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # 1.5 Tính toán đêm
                game.phase = GamePhase.NIGHT_RESOLVE
                alive_before_night = {p.user_id for p in game.get_alive_players()}
                game.resolve_night()
                await self.close_witch_dm(game)
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break
                await self.check_and_trigger_hunter(game, message.channel)
                await self.check_and_trigger_mayor_succession(game, message.channel)
                night_deaths = new_deaths(game, alive_before_night)
                game.night_deaths = list(night_deaths)

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # Thông báo DM cho Kẻ Bị Nguyền vừa biến thành Sói đêm này
                for p in game.players.values():
                    if (
                        p.is_alive
                        and p.role == Role.CURSED
                        and p.is_cursed_converted
                        and not p.cursed_notified
                    ):
                        p.cursed_notified = True
                        cursed_user = await self.get_or_fetch_user(p.user_id)
                        if cursed_user:
                            wolf_teammates = [
                                w.display_name
                                for w in game.get_alive_wolves()
                                if w.user_id != p.user_id
                            ]
                            teammates_str = (
                                ", ".join(f"**{n}**" for n in wolf_teammates)
                                if wolf_teammates else "*Bạn là Sói duy nhất còn sống!*"
                            )
                            try:
                                await cursed_user.send(
                                    f"🌕🐺 **Bạn đã bị Nguyền và biến thành SÓI!**\n"
                                    f"> Bầy Sói đã cắn bạn đêm qua \u2014 từ đêm sau bạn là **SÓI** rồi!\n"
                                    f"> 👥 Đồng đội Sói: {teammates_str}"
                                )
                            except Exception:
                                pass

                if game.girl_result:
                    await self.update_night_result_dm(game.girl_dm_message, game.girl_result, "👧 Kết quả Cô Bé")

                await self.update_night_result_dm(game.night_cupid_dm_message, game.night_cupid_result, "💘 Kết quả Thần Tình Yêu")
                if game.night_cupid_result and game.night_cupid_targets and game.night_cupid_result.startswith("💘"):
                    couple = [game.players.get(uid) for uid in game.night_cupid_targets]
                    if all(couple):
                        for target, partner in ((couple[0], couple[1]), (couple[1], couple[0])):
                            user = await self.get_or_fetch_user(target.user_id)
                            if user:
                                try:
                                    await user.send(
                                        "> 💘 **BẠN ĐÃ ĐƯỢC THẦN TÌNH YÊU GHÉP ĐÔI!**\n"
                                        f"> Bạn và **{partner.display_name}** hiện là **CẶP ĐÔI TÌNH NHÂN**.\n"
                                        "> ⚠️ *Nếu 1 trong 2 người chết, người kia cũng sẽ chết theo!*\n"
                                        f"> {game.lover_goal_text(target.user_id)}"
                                    )
                                except Exception:
                                    pass

                # Cập nhật DM cho Tiên Tri Tập Sự vừa kế thừa vị trí
                for app_p in game.players.values():
                    if app_p.is_alive and app_p.role == Role.APPRENTICE_SEER and app_p.apprentice_promoted and not getattr(app_p, "apprentice_notified", False):
                        app_p.apprentice_notified = True
                        app_user = await self.get_or_fetch_user(app_p.user_id)
                        if app_user:
                            try:
                                await app_user.send(
                                    "🔮✨ **Tiên Tri chính đã qua đời!** Bạn đã chính thức kế thừa vị trí **Tiên Tri mới** của làng!\n"
                                    "> Từ đêm tiếp theo, bạn có thể sử dụng kỹ năng soi phe."
                                )
                            except Exception:
                                pass

                # Tiết lộ thông tin điều tra chỉ sau khi roleblock đã được phân giải.
                await self.update_night_result_dm(game.seer_dm_message, game.night_seer_result, "🔮 Kết quả Tiên Tri")
                await self.update_night_result_dm(
                    game.night_investigator_dm_message,
                    game.night_investigator_result,
                    "👁️ Kết quả Thám Tử",
                )
                await self.update_night_result_dm(
                    game.night_wolf_seer_dm_message,
                    game.night_wolf_seer_result,
                    "🐺🔮 Kết quả Sói Tiên Tri",
                )

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # ── BƯỚC 2: CÔNG BỐ BAN NGÀY ──
                game.phase = GamePhase.DAY_ANNOUNCE
                game.start_day()
                await self.sync_channel_permissions(game, message.channel)

                if night_deaths:
                    death_names = []
                    quotes = []
                    eco = self.get_economy()
                    for uid in night_deaths:
                        p = game.players[uid]
                        if game.settings.reveal_roles_on_death:
                            death_names.append(f"<:die:1533444731000848415> {self.player_label(p)} *({p.role.emoji} {p.role.value})*")
                        else:
                            death_names.append(f"<:die:1533444731000848415> **{p.display_name}**")

                        if eco:
                            vip_info = eco.get_masoi_vip_info(p.user_id)
                            if vip_info["is_vip"] and vip_info["last_words"]:
                                quotes.append(f"💬 *Lời trăn trối của <a:2336vipgif:1534596901834592286> **{p.display_name}**: \"{vip_info['last_words']}\"*")

                    quote_str = ("\n\n" + "\n".join(quotes)) if quotes else ""
                    day_msg_text = "Đêm qua trôi qua đầy đau thương... Các nạn nhân đã ra đi:\n" + "\n".join(death_names) + quote_str
                else:
                    day_msg_text = "<a:yay:1533444499827851505> Đêm qua trôi qua thật bình yên, không có ai qua đời!"

                embed_announce = discord.Embed(
                    title=f"<a:yay:1533444499827851505> Ban Ngày — Ngày {game.day_count}",
                    description=f"{day_msg_text}\n\n{divider}\n💬 Mọi người hãy cùng trao đổi và thảo luận tại kênh này!",
                    color=discord.Color(0xE0A638)
                )
                await _safe_send(message.channel, embed=embed_announce)

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # Kiểm tra thắng ngay sau đêm
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

                # ── BƯỚC 3: THẢO LUẬN BAN NGÀY ──
                game.phase = GamePhase.DAY_DISCUSSION
                disc_limit = game.settings.discussion_time
                disc_embed = discord.Embed(
                    title=f"💬 Ban Ngày — Thảo Luận (Ngày {game.day_count})",
                    description=f"<a:time:1533445134522384536> **Thời gian thảo luận:** `{disc_limit} giây`.\n"
                                f"Bấm **Yêu cầu bỏ phiếu sớm** nếu muốn dồn phiếu ngay!\n\n"
                                f"{divider}\n💬 Mọi người hãy trao đổi ý kiến để tìm ra bầy Sói!",
                    color=discord.Color(0xE0A638)
                )
                disc_view = DayDiscussionView(game, self, prepare=True)
                game.discussion_view = disc_view
                disc_msg = await _safe_send(message.channel, embed=disc_embed, view=disc_view)

                game.discussion_view = disc_view
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    disc_view.stop()
                    break
                disc_view.open_actions()
                # One monotonic deadline, opened only after delivery.
                while time.monotonic() < disc_view.deadline:
                    if disc_view.is_finished() or self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(min(1, max(0, disc_view.deadline - time.monotonic())))

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                try:
                    await disc_msg.delete()
                except Exception:
                    pass

                disc_view.stop()
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # ── BƯỚC 4: BỎ PHIẾU TREO CỔ ──
                game.phase = GamePhase.DAY_VOTE
                vote_embed = self.build_vote_embed(game, is_final=False)
                vote_view = DayVoteView(game, self, prepare=True)
                game.day_vote_view = vote_view
                vote_msg = await _safe_send(message.channel, embed=vote_embed, view=vote_view)

                game.day_vote_message = vote_msg
                game.day_vote_view = vote_view
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    vote_view.stop()
                    break
                vote_view.open_actions()

                # Chờ đủ phiếu hoặc tới đúng deadline đã mở sau khi gửi.
                while time.monotonic() < vote_view.deadline:
                    if vote_view.is_finished() or len(game.day_votes) >= len(game.get_alive_players()) or self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(min(1, max(0, vote_view.deadline - time.monotonic())))

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # ── BƯỚC 5: XỬ LÝ BỎ PHIẾU ──
                # Close synchronously before awaiting the lock: queued live edits cannot reopen.
                game.phase = GamePhase.DAY_RESOLVE
                vote_view.stop()
                async with ui_lock(game, "vote"):
                    try:
                        await vote_msg.edit(embed=self.build_vote_embed(game, is_final=True), view=None)
                    except Exception:
                        pass
                game.day_vote_message = None
                game.day_vote_view = None
                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break
                alive_before_vote = {p.user_id for p in game.get_alive_players()}
                executed_id = game.resolve_day_vote()
                last_log = game.replay_logs[-1] if game.replay_logs else None
                if game.winner_faction != Faction.INDEPENDENT:
                    await self.check_and_trigger_hunter(game, message.channel)
                    await self.check_and_trigger_mayor_succession(game, message.channel)
                await self.sync_channel_permissions(game, message.channel)

                if executed_id:
                    p = game.players[executed_id]
                    if p.role == Role.SCAPEGOAT and any(log.event_type == "SCAPEGOAT_EXECUTED" and log.day == game.day_count and log.target_id == executed_id for log in game.replay_logs):
                        if game.settings.reveal_roles_on_death:
                            exec_text = f"🐐 **Do phiếu bầu bị HÒA, Dê Tế Thần {self.player_badge(p.user_id)} {p.display_name}** tự động bị gánh tội và đưa lên giàn treo cổ! *(Vai trò: **{p.role.emoji} {p.role.value}**)*"
                        else:
                            exec_text = f"🐐 **Do phiếu bầu bị HÒA, Dê Tế Thần {p.display_name}** tự động bị gánh tội và đưa lên giàn treo cổ!"
                    else:
                        if game.settings.reveal_roles_on_death:
                            exec_text = f"<a:huyay:1533445376563089448> {self.player_label(p)} đã bị dân làng xử tử trên giàn treo cổ! *(Vai trò: **{p.role.emoji} {p.role.value}**)*"
                        else:
                            exec_text = f"<a:huyay:1533445376563089448> {self.player_label(p)} đã bị dân làng xử tử trên giàn treo cổ!"

                    eco = self.get_economy()
                    if eco:
                        vip_info = eco.get_masoi_vip_info(p.user_id)
                        if vip_info["is_vip"] and vip_info["last_words"]:
                            exec_text += f"\n\n💬 *Lời trăn trối của <a:2336vipgif:1534596901834592286> **{p.display_name}**: \"{vip_info['last_words']}\"*"
                else:
                    last_log = game.replay_logs[-1] if game.replay_logs else None
                    if last_log and last_log.event_type == "VOTE_RESULT":
                        exec_text = f"<a:huyay:1533445376563089448> Lượt bỏ phiếu kết thúc: **{last_log.result}**."
                    else:
                        exec_text = "<a:huyay:1533445376563089448> Lượt bỏ phiếu kết thúc, không ai bị xử tử."

                additional_deaths = [uid for uid in new_deaths(game, alive_before_vote) if uid != executed_id]
                if additional_deaths:
                    names = [self.player_label(game.players[uid]) + (f" ({game.players[uid].role.emoji} {game.players[uid].role.value})" if game.settings.reveal_roles_on_death else "") for uid in additional_deaths]
                    exec_text += "\n\n💀 Những người qua đời theo dây chuyền:\n" + "\n".join(names)

                embed_exec = discord.Embed(
                    title="<a:huyay:1533445376563089448> Kết Quả Xử Tử",
                    description=f"{exec_text}\n\n{divider}",
                    color=discord.Color(0xE0A638)
                )
                await _safe_send(message.channel, embed=embed_exec)

                if self.active_games.get(key) is not game or game.phase == GamePhase.GAME_END:
                    break

                # Kiểm tra thắng sau bỏ phiếu
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

            # A forced stop also ends the loop, but must not settle ranks as a completed match.
            if game.winner_faction and self.active_games.get(key) is game:
                await self.end_game(game, message)

        except NightDeliveryError as exc:
            # Transport failure is not a player's choice or a ranked loss.
            game.winner_faction = None
            game.phase = GamePhase.GAME_END
            game.checkpoint()
            try:
                await message.channel.send(f"❌ {exc}")
            except Exception:
                logger.warning("Không thể gửi thông báo hủy ván vì lỗi DM")
        except asyncio.CancelledError:
            # Game bị cancel chủ động (thường do force_stop_game)
            logger.info("Game loop %s bị cancel.", key)
        except discord.HTTPException as e:
            logger.error("Discord API error trong game loop %s: %s", key, e, exc_info=True)
            try:
                embed_err = make_embed(
                    title="<a:luuy:1533429265293508888> ĐÃ XẢY RA LỖI KẾT NỐI",
                    description=(
                        f"Ván Ma Sói gặp sự cố kết nối với Discord và đã bị hủy!\n"
                        f"*(Lỗi: {e.status} — {e.text})*\n\n"
                        f"Dùng `!masoi` để tạo ván mới."
                    ),
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed_err)
            except Exception:
                pass
        except Exception as e:
            logger.exception("Lỗi không xác định trong game loop (Guild %s, Channel %s):", game.guild_id, game.channel_id)
            try:
                embed_err = make_embed(
                    title="<a:luuy:1533429265293508888> ĐÃ XẢY RA LỖI HỆ THỐNG",
                    description=(
                        f"Ván Ma Sói gặp sự cố không mong muốn và đã bị hủy!\n"
                        f"`Chi tiết lỗi: {type(e).__name__}: {e}`\n\n"
                        f"Dùng `!masoi` để tạo ván mới."
                    ),
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed_err)
            except Exception:
                pass
        finally:
            game.phase = GamePhase.GAME_END
            game.stop_night_views()
            for view in (getattr(game, "discussion_view", None), getattr(game, "day_vote_view", None)):
                if view:
                    view.stop()
            game.day_vote_message = None
            game.day_vote_view = None
            try:
                await self.restore_channel_permissions(game, message.channel)
            except Exception:
                logger.exception("Không thể khôi phục đầy đủ permission của game %s", key)
            try:
                self.retire_snapshot(game)
            except Exception:
                logger.exception("Snapshot Ma Sói còn pending để phục hồi ở lần sau")
                if hasattr(self, "_recovering_channels"):
                    self._recovering_channels.add(key)
            # Luôn dọn sạch active_games để kênh không bị lock
            if self.active_games.get(key) is game:
                del self.active_games[key]
                logger.info("Đã dọn sạch active_games cho key %s.", key)

    async def end_game(self, game: MasoiGame, message: discord.Message):
        if not game.winner_faction:
            return
        game.phase = GamePhase.GAME_END
        game.end_time = time.time()

        # Cộng điểm rank
        rank_pts = game.calculate_rank_points()
        eco = self.get_economy()
        game.checkpoint()
        MasoiRankService.settle(game, eco)
        game.checkpoint()

        # Tổng kết vai trò
        role_lines = []
        for p in game.players.values():
            status = "<a:key:1526234974150459593> Sống" if p.is_alive else "<:die:1533444731000848415> Chết"
            pts_str = f" ({game.get_rank_faction(p.user_id).label}: {rank_pts.get(p.user_id, 0):+d} pts)" if game.settings.enable_rank else ""
            result = "Hòa" if game.winner_faction == Faction.DRAW else "Thắng" if game.did_player_win(p.user_id) else "Thua"
            role_lines.append(f"• {self.player_label(p)} — {p.role.emoji} **{p.role.value}** [{status} · {result}]{pts_str}")

        winner_str = game.winner_faction.value if game.winner_faction else "Không có"

        outcome_text = "Ván đấu hòa; không cộng/trừ rank." if game.winner_faction == Faction.DRAW else f"**{winner_str} đã giành chiến thắng!**"
        end_embed = make_embed(
            title=f"<a:w1:1526231439425667093> VÁN BÀN CỜ MA SÓI KẾT THÚC <a:w1:1526231439425667093> {winner_str}",
            description=(
                f"<a:w1:1526231439425667093> {outcome_text}<a:w1:1526231439425667093>\n\n"
                f"**Vai trò tất cả người chơi:**\n" + "\n".join(role_lines) + "\n\n"
                f" **Tổng thời gian ván:** {game.night_count} Đêm, {game.day_count} Ngày"
            ),
            color=discord.Color.green(),
        )

        end_view = GameEndView(game, self)
        await message.channel.send(embed=end_embed, view=end_view)
        game.result_announced = True
        game.checkpoint()
        await self.restore_channel_permissions(game, message.channel)
