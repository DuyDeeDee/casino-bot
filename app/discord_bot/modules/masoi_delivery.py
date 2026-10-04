"""Concurrent, bounded non-VIP night delivery before opening the shared action window."""
from __future__ import annotations

import asyncio
import logging
import discord
from app.discord_bot.modules.masoi_engine import ActionKind, GamePhase, NightEvent, Role
from app.discord_bot.modules import masoi_ui as ui

logger = logging.getLogger(__name__)


class NightDeliveryError(RuntimeError):
    pass


async def deliver_night(cog, game, *, timeout=15, concurrency=6):
    if game.phase != GamePhase.NIGHT_PREPARE:
        raise ValueError("Night delivery requires the preparation phase")
    jobs = []
    simple = {
        Role.GUARD: (ui.NightGuardView, "Chọn một người để chặn mọi đòn tấn công ban đêm; không chọn cùng người hai đêm liên tiếp."),
        Role.DOCTOR: (ui.NightDoctorView, "Chọn một người khác để cứu khỏi Sói cắn. Có thể chọn cùng người nhiều đêm không giới hạn."),
        Role.SEER: (ui.NightSeerView, "Chọn một người để soi phe."),
        Role.WOLF_SEER: (ui.NightWolfSeerView, "Chọn một người để soi chính xác vai trò."),
        Role.WOLF_GUARD: (ui.NightWolfGuardView, "Chọn một người khác để che chở khỏi kỹ năng giết của Dân và treo cổ trong ngày và đêm kế tiếp. Sau khi cứu thành công một lần, bạn mất kỹ năng này."),
        Role.STRONGMAN: (ui.NightStrongmanView, "Chọn một người khác để bảo vệ. Nếu bạn hoặc người đó bị tấn công, cả hai sống sót; bạn và kẻ tấn công biết role nhau. Bạn sẽ chết khi đêm sau bắt đầu."),
        Role.BIGMOUTH: (ui.NightBigmouthView, "Chọn người có role sẽ được tiết lộ khi bạn chết. Bạn có thể đổi lựa chọn vào các đêm sau."),
        Role.HARLOT: (ui.NightHarlotView, "Ghé thăm một người hoặc ở nhà. Vắng nhà tránh đòn tấn công, nhưng ghé Sói/Kẻ Phóng Hỏa hoặc người bị giết sẽ chết."),
        Role.INVESTIGATOR: (ui.NightInvestigatorView, "Chọn đúng 2 người để so họ cùng hay khác phe thật (Dân/Sói/Solo)."),
        Role.ARSONIST: (ui.NightArsonistView, f"Chọn đúng {game.required_target_count(ActionKind.ARSON_DOUSE)} người để tẩm xăng xuyên bảo vệ, hoặc chọn tối đa 4 người đang dính xăng để châm lửa."),
        Role.PHANTOM_WOLF: (ui.NightPhantomWolfView, "Chọn một người không thuộc bầy Sói để tạo ảo ảnh."),
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
        if player.role in simple and (player.role != Role.WOLF_GUARD or not player.wolf_guard_used):
            view_type, description = simple[player.role]
            queue(player, view_type(game, player.user_id), description)
        if player.role == Role.APPRENTICE_SEER and player.apprentice_promoted:
            queue(player, ui.NightSeerView(game, player.user_id), "Bạn đã kế thừa Tiên Tri. Chọn một người để soi phe.")
        if player.role == Role.CUPID and game.night_count == 1:
            queue(player, ui.NightCupidView(game, player.user_id), "Chọn đúng hai người để ghép đôi.")
        if player.role == Role.WITCH and game.active_night_event != NightEvent.SEAL_NIGHT:
            victim = game.resolve_wolf_target()
            view = ui.NightWitchView(game, player.user_id, victim)
            game.witch_view = view
            queue(player, view, "Bầy Sói chưa chốt mục tiêu; tin nhắn sẽ cập nhật khi Sói bỏ phiếu. Bình cứu chỉ bảo vệ một người.", witch=True)
        if player.role == Role.FORENSIC:
            has_previous_night_victim = any(
                not candidate.is_alive
                and candidate.last_death_night == game.night_count - 1
                and candidate.last_death_source in {"wolf", "white_wolf", "serial_killer", "arson"}
                for candidate in game.players.values()
            )
            if has_previous_night_victim:
                view = ui.NightForensicView(game, player.user_id)
                queue(player, view, "Chọn người bị giết đêm trước để nhận các nghi phạm có thể là hung thủ.")
        if player.role == Role.PRIEST and not player.holy_water_used:
            queue(player, ui.NightPriestView(game, player.user_id), "Vẩy nước thánh lên một người khác. Sói sẽ chết; nếu không phải Sói, bạn sẽ chết. Dùng một lần trong ván.")

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
