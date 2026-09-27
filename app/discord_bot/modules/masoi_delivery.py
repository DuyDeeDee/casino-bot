"""Concurrent, bounded non-VIP night delivery before opening the shared action window."""
from __future__ import annotations

import asyncio
import logging
import discord
from app.discord_bot.modules.masoi_engine import ActionKind, GamePhase, Role
from app.discord_bot.modules import masoi_ui as ui

logger = logging.getLogger(__name__)


class NightDeliveryError(RuntimeError):
    pass


async def deliver_night(cog, game, *, timeout=15, concurrency=6):
    if game.phase != GamePhase.NIGHT_PREPARE:
        raise ValueError("Night delivery requires the preparation phase")
    jobs = []
    simple = {
        Role.GUARD: (ui.NightGuardView, "Chọn một người để bảo vệ; không chọn cùng người hai đêm liên tiếp."),
        Role.SEER: (ui.NightSeerView, "Chọn một người để soi phe."),
        Role.WOLF_SEER: (ui.NightWolfSeerView, "Chọn một người để soi chính xác vai trò."),
        Role.SERIAL_KILLER: (ui.NightSerialKillerView, "Chọn một nạn nhân. Mục tiêu gốc: sống sót duy nhất, trừ mục tiêu Tình Nhân dưới đây."),
        Role.HARLOT: (ui.NightHarlotView, "Chọn một người để phong tỏa toàn bộ hành động đêm."),
        Role.INVESTIGATOR: (ui.NightInvestigatorView, f"Chọn đúng {game.required_target_count(ActionKind.INVESTIGATE)} người để kiểm tra có Sói hay không."),
        Role.PHANTOM_WOLF: (ui.NightPhantomWolfView, "Chọn một người không thuộc bầy Sói để tạo ảo ảnh."),
        Role.THE_GIRL: (ui.NightGirlView, "Bạn có thể nhìn trộm; có 50% khả năng bị phát hiện, mỗi lần nhìn trộm."),
        Role.PIPER: (ui.NightPiperView, f"Chọn đúng {game.required_target_count(ActionKind.PIPER)} người để mê hoặc."),
    }

    def queue(player, view, description, *, witch=False):
        if player.lover_id is not None:
            description += "\n\n" + game.lover_goal_text(player.user_id)
        embed = discord.Embed(
            title=f"🌙 Đêm {game.night_count} — {player.role.emoji} {player.role.value}",
            description=description + "\n\n⏳ Đang gửi DM. Chỉ hành động sau thông báo mở đêm ở kênh chơi; mọi người có cùng thời gian.",
            color=discord.Color.gold(),
        )
        jobs.append((player.user_id, embed, view, witch))

    for player in game.get_alive_players():
        if player.is_wolf:
            queue(player, ui.NightWolfView(game, player.user_id), "Bỏ phiếu cắn một người không thuộc bầy Sói.")
        if player.role in simple:
            view_type, description = simple[player.role]
            queue(player, view_type(game, player.user_id), description)
        if player.role == Role.APPRENTICE_SEER and player.apprentice_promoted:
            queue(player, ui.NightSeerView(game, player.user_id), "Bạn đã kế thừa Tiên Tri. Chọn một người để soi phe.")
        if player.role == Role.CUPID and game.night_count == 1:
            queue(player, ui.NightCupidView(game, player.user_id), "Chọn đúng hai người để ghép đôi.")
        if player.role == Role.WHITE_WOLF and game.night_count % 2 == 0:
            if any(p.user_id != player.user_id for p in game.get_alive_wolves()):
                queue(player, ui.NightWhiteWolfView(game, player.user_id), "Bạn có thể bí mật cắn thêm một Sói khác hoặc bỏ qua.")
        if player.role == Role.WITCH:
            victim = game.resolve_wolf_target()
            view = ui.NightWitchView(game, player.user_id, victim)
            game.witch_view = view
            queue(player, view, "Bầy Sói chưa chốt mục tiêu; tin nhắn sẽ cập nhật khi Sói bỏ phiếu. Bình cứu chỉ bảo vệ một người.", witch=True)

    semaphore = asyncio.Semaphore(concurrency)
    async def send_job(job):
        uid, embed, view, witch = job
        async with semaphore:
            if game.phase == GamePhase.GAME_END:
                return uid
            try:
                async def fetch_and_send():
                    user = await cog.get_or_fetch_user(uid)
                    if not user:
                        raise NightDeliveryError("User unavailable")
                    return await user.send(embed=embed, view=view)
                message = await asyncio.wait_for(fetch_and_send(), timeout=timeout)
                if witch:
                    game.witch_dm_message = message
                return None
            except Exception as exc:
                logger.warning("Night DM delivery failed for %s: %s", uid, type(exc).__name__)
                return uid
    failures = {uid for uid in await asyncio.gather(*(send_job(job) for job in jobs)) if uid is not None}
    if failures:
        game.stop_night_views()
        names = ", ".join(game.players[uid].display_name for uid in sorted(failures))
        raise NightDeliveryError(f"Không gửi được DM hành động cho: {names}. Ván bị hủy, không tính rank.")
