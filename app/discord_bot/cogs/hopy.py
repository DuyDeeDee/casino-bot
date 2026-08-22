# coding: utf-8
"""
Cog cho Party Minigame: HỢP Ý (Tâm Đầu Ý Hợp) - Mind Meld.
Tương tác 100% qua Buttons, Modals và Select Menus trên 1 Embed edit-in-place duy nhất.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.hopy_engine import (
    GamePhase,
    HopyGame,
    HopyPlayer,
    RoundEvaluation,
)

logger = logging.getLogger(__name__)

GOLD_COLOR = discord.Color(0xC8A84B)
QUESTION_TIMEOUT = 30  # Giây đếm ngược mỗi câu hỏi
INTERIM_DELAY = 7       # Giây chờ trước khi tự động qua vòng mới


# ==============================================================================
#  MODALS
# ==============================================================================

class HopyAnswerModal(discord.ui.Modal, title="💡 Câu Trả Lời Hợp Ý"):
    def __init__(self, cog: "Hopy", game: HopyGame, user_id: int):
        super().__init__()
        self.cog = cog
        self.game = game
        self.user_id = user_id

        prev_answer = self.game.round_raw_answers.get(user_id, "")
        self.answer_input = discord.ui.TextInput(
            label="Nhập 1 từ hoặc cụm từ ngắn:",
            placeholder="VD: Cà phê, Mùa hè, Chó cưng, Bánh mì...",
            min_length=1,
            max_length=35,
            required=True,
            default=prev_answer if prev_answer else None,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.game.phase != GamePhase.QUESTION:
            await interaction.response.send_message(
                "❌ Vòng này đã kết thúc thời gian nộp bài!", ephemeral=True
            )
            return

        user_ans = self.answer_input.value.strip()
        if not user_ans:
            await interaction.response.send_message(
                "❌ Câu trả lời không được để trống!", ephemeral=True
            )
            return

        success = self.game.submit_answer(interaction.user.id, user_ans)
        if not success:
            await interaction.response.send_message(
                "❌ Bạn không nằm trong danh sách người chơi của phòng này!", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Đã ghi nhận câu trả lời: **{user_ans}**!\n"
            "💡 Bạn có thể bấm nút nộp lại bất cứ lúc nào trước khi hết giờ nếu muốn đổi ý.",
            ephemeral=True
        )

        # Cập nhật số người đã trả lời trên Embed chính
        await self.cog.refresh_question_embed(self.game)


# ==============================================================================
#  VIEWS
# ==============================================================================

class DifficultySelect(discord.ui.Select):
    def __init__(self, current_diff: str = "mix"):
        options = [
            discord.SelectOption(
                label="Dễ (Đáp án dễ hội tụ)",
                value="easy",
                emoji="🟢",
                description="Màu sắc, đồ ăn, thú cưng, ngày lễ...",
                default=(current_diff == "easy")
            ),
            discord.SelectOption(
                label="Khó (Đáp án phân tán)",
                value="hard",
                emoji="🔴",
                description="Ước mơ, nỗi sợ, thói quen, nghề nghiệp...",
                default=(current_diff == "hard")
            ),
            discord.SelectOption(
                label="Hỗn Hợp (Mix ngẫu nhiên)",
                value="mix",
                emoji="🎲",
                description="Trộn đều tất cả chủ đề",
                default=(current_diff == "mix")
            ),
        ]
        super().__init__(placeholder="⚙️ Chọn độ khó...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HopyLobbyView = self.view
        if interaction.user.id != view.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới được đổi độ khó!", ephemeral=True)
            return

        view.game.set_difficulty(self.values[0])
        for opt in self.options:
            opt.default = (opt.value == self.values[0])

        await interaction.response.defer()
        await view.cog.refresh_lobby_embed(view.game)


class RoundsSelect(discord.ui.Select):
    def __init__(self, current_rounds: int = 5):
        options = [
            discord.SelectOption(
                label="3 Vòng (Nhanh gọn)",
                value="3",
                emoji="⚡",
                description="Thời gian chơi ~2-3 phút",
                default=(current_rounds == 3)
            ),
            discord.SelectOption(
                label="5 Vòng (Tiêu chuẩn)",
                value="5",
                emoji="🎯",
                description="Thời gian chơi ~5 phút",
                default=(current_rounds == 5)
            ),
            discord.SelectOption(
                label="7 Vòng (Đại chiến)",
                value="7",
                emoji="🏆",
                description="Thời gian chơi ~7-8 phút",
                default=(current_rounds == 7)
            ),
        ]
        super().__init__(placeholder="🎯 Chọn số vòng đấu...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HopyLobbyView = self.view
        if interaction.user.id != view.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới được đổi số vòng!", ephemeral=True)
            return

        view.game.set_rounds(int(self.values[0]))
        for opt in self.options:
            opt.default = (opt.value == self.values[0])

        await interaction.response.defer()
        await view.cog.refresh_lobby_embed(view.game)


class HopyLobbyView(discord.ui.View):
    def __init__(self, cog: "Hopy", game: HopyGame):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.game = game

        self.add_item(DifficultySelect(game.difficulty))
        self.add_item(RoundsSelect(game.total_rounds))

    @discord.ui.button(label="Tham Gia", style=discord.ButtonStyle.success, emoji="🟢", row=2)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id in self.game.players and self.game.players[user.id].active:
            await interaction.response.send_message("❌ Bạn đã ở trong phòng rồi!", ephemeral=True)
            return

        if len(self.game.active_players) >= self.game.MAX_PLAYERS:
            await interaction.response.send_message("❌ Phòng chơi đã đạt số người tối đa (8 người)!", ephemeral=True)
            return

        self.game.add_player(user.id, user.display_name)
        await interaction.response.send_message("✅ Bạn đã tham gia phòng **HỢP Ý**!", ephemeral=True)
        await self.cog.refresh_lobby_embed(self.game)

    @discord.ui.button(label="Rời Phòng", style=discord.ButtonStyle.secondary, emoji="🚪", row=2)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id not in self.game.players:
            await interaction.response.send_message("❌ Bạn chưa tham gia phòng này!", ephemeral=True)
            return

        self.game.remove_player(user.id)
        await interaction.response.send_message("🚪 Bạn đã rời khỏi phòng chờ.", ephemeral=True)

        if not self.game.players:
            # Không còn ai trong phòng -> Hủy phòng
            self.stop()
            self.cog.active_games.pop(self.game.channel_id, None)
            embed = make_embed(
                title="✨ PHÒNG HỢP Ý ĐÃ ĐÓNG",
                description="Phòng chơi đã tự động đóng vì không còn ai trong phòng.",
                color=discord.Color.dark_grey()
            )
            try:
                channel = self.cog.client.get_channel(self.game.channel_id)
                if channel and self.game.message_id:
                    msg = await channel.fetch_message(self.game.message_id)
                    await msg.edit(embed=embed, view=None)
            except Exception:
                pass
            return

        await self.cog.refresh_lobby_embed(self.game)

    @discord.ui.button(label="Bắt Đầu", style=discord.ButtonStyle.primary, emoji="🚀", row=2)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới có quyền bắt đầu ván đấu!", ephemeral=True)
            return

        if self.game.player_count < self.game.MIN_PLAYERS:
            await interaction.response.send_message(
                f"❌ Cần ít nhất **{self.game.MIN_PLAYERS} người chơi** để bắt đầu!",
                ephemeral=True
            )
            return

        self.stop()
        await interaction.response.defer()
        asyncio.create_task(self.cog.start_game_session(self.game))

    @discord.ui.button(label="Hủy Phòng", style=discord.ButtonStyle.danger, emoji="❌", row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới có quyền hủy phòng!", ephemeral=True)
            return

        self.stop()
        self.cog.active_games.pop(self.game.channel_id, None)
        await interaction.response.defer()
        embed = make_embed(
            title="✨ PHÒNG HỢP Ý ĐÃ HỦY",
            description=f"Chủ phòng **{interaction.user.display_name}** đã hủy phòng chờ.",
            color=discord.Color.red()
        )
        try:
            channel = self.cog.client.get_channel(self.game.channel_id)
            if channel and self.game.message_id:
                msg = await channel.fetch_message(self.game.message_id)
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass


class HopyQuestionView(discord.ui.View):
    def __init__(self, cog: "Hopy", game: HopyGame):
        super().__init__(timeout=QUESTION_TIMEOUT + 5)
        self.cog = cog
        self.game = game

    @discord.ui.button(label="✍️ Trả Lời / Đổi Đáp Án", style=discord.ButtonStyle.primary)
    async def answer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players or not self.game.players[interaction.user.id].active:
            await interaction.response.send_message("❌ Bạn không tham gia ván chơi này!", ephemeral=True)
            return

        if self.game.phase != GamePhase.QUESTION:
            await interaction.response.send_message("❌ Vòng này đã kết thúc nhận đáp án!", ephemeral=True)
            return

        modal = HopyAnswerModal(self.cog, self.game, interaction.user.id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="⏩ Chốt Giờ Sớm", style=discord.ButtonStyle.secondary)
    async def early_reveal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới có quyền chốt giờ sớm!", ephemeral=True)
            return

        ans_count, total, _ = self.game.get_answered_status()
        if ans_count < 2:
            await interaction.response.send_message("❌ Cần ít nhất 2 người trả lời trước khi chốt sớm!", ephemeral=True)
            return

        await interaction.response.send_message("⏩ Chủ phòng đã kích hoạt chốt giờ sớm!", ephemeral=True)
        # Đánh dấu cờ force reveal
        self.cog.force_reveal_flags[self.game.channel_id] = True


class HopyNextRoundView(discord.ui.View):
    def __init__(self, cog: "Hopy", game: HopyGame):
        super().__init__(timeout=INTERIM_DELAY + 2)
        self.cog = cog
        self.game = game

    @discord.ui.button(label="⏩ Vòng Tiếp Theo", style=discord.ButtonStyle.success)
    async def next_round_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới có quyền chuyển vòng ngay!", ephemeral=True)
            return

        await interaction.response.defer()
        self.cog.skip_wait_flags[self.game.channel_id] = True


class HopyGameEndView(discord.ui.View):
    def __init__(self, cog: "Hopy", game: HopyGame):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.game = game

    @discord.ui.button(label="🔄 Chơi Ván Mới", style=discord.ButtonStyle.primary, emoji="🎉")
    async def new_game_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id in self.cog.active_games:
            await interaction.response.send_message("❌ Kênh này đang có một phòng chơi khác đang hoạt động!", ephemeral=True)
            return

        # Vô hiệu hóa nút trên màn hình cũ để tránh bấm nhiều lần
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # Tạo phòng mới với host là người bấm nút
        new_game = HopyGame(
            channel_id=interaction.channel.id,
            host_id=interaction.user.id,
            host_name=interaction.user.display_name
        )
        self.cog.active_games[interaction.channel.id] = new_game

        view = HopyLobbyView(self.cog, new_game)
        embed = self.cog.build_lobby_embed(new_game)
        msg = await interaction.channel.send(embed=embed, view=view)
        new_game.message_id = msg.id
        asyncio.create_task(self.cog._lobby_timeout_watcher(new_game, 180))
        await interaction.response.send_message("✅ Đã mở phòng HỢP Ý mới!", ephemeral=True)


# ==============================================================================
#  COG CLASS
# ==============================================================================

class Hopy(commands.Cog, name="Hopy"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.active_games: Dict[int, HopyGame] = {}
        self.force_reveal_flags: Dict[int, bool] = {}
        self.skip_wait_flags: Dict[int, bool] = {}

    # --------------------------------------------------------------------------
    #  COMMANDS
    # --------------------------------------------------------------------------

    @commands.group(
        name="hopy",
        aliases=["tamdauyhop", "mindmeld", "hop-y"],
        invoke_without_command=True,
        brief="✨ Party minigame Tâm Đầu Ý Hợp",
    )
    async def hopy_cmd(self, ctx: commands.Context):
        """Khởi tạo phòng chơi HỢP Ý (Tâm Đầu Ý Hợp)"""
        if ctx.channel.id in self.active_games:
            await ctx.send("❌ Kênh này hiện đã có một phòng HỢP Ý đang hoạt động!", delete_after=6)
            return

        game = HopyGame(
            channel_id=ctx.channel.id,
            host_id=ctx.author.id,
            host_name=ctx.author.display_name
        )
        self.active_games[ctx.channel.id] = game

        view = HopyLobbyView(self, game)
        embed = self.build_lobby_embed(game)
        msg = await ctx.send(embed=embed, view=view)
        game.message_id = msg.id

        # Tự động dọn phòng nếu sau 3 phút không bắt đầu
        asyncio.create_task(self._lobby_timeout_watcher(game, 180))

    async def _lobby_timeout_watcher(self, game: HopyGame, timeout_seconds: int):
        await asyncio.sleep(timeout_seconds)
        if game.phase == GamePhase.LOBBY and self.active_games.get(game.channel_id) == game:
            self.active_games.pop(game.channel_id, None)
            try:
                channel = self.client.get_channel(game.channel_id)
                if channel and game.message_id:
                    msg = await channel.fetch_message(game.message_id)
                    embed = make_embed(
                        title="✨ PHÒNG HỢP Ý HẾT HẠN",
                        description="Phòng chờ đã tự động hủy do quá thời gian chờ bắt đầu.",
                        color=discord.Color.dark_grey()
                    )
                    await msg.edit(embed=embed, view=None)
            except Exception:
                pass

    # --------------------------------------------------------------------------
    #  EMBED BUILDERS
    # --------------------------------------------------------------------------

    def build_lobby_embed(self, game: HopyGame) -> discord.Embed:
        diff_labels = {
            "easy": "🟢 Dễ (Dễ trùng ý)",
            "hard": "🔴 Khó (Thử thách phân tán)",
            "mix": "🎲 Hỗn Hợp (Ngẫu nhiên)"
        }
        diff_text = diff_labels.get(game.difficulty, "🎲 Hỗn Hợp")

        players_list = []
        for i, p in enumerate(game.active_players, 1):
            is_host = " 👑 *(Chủ phòng)*" if p.user_id == game.host_id else ""
            players_list.append(f"`{i}.` **{p.display_name}**{is_host}")

        players_text = "\n".join(players_list) if players_list else "*Chưa có người tham gia*"

        desc = (
            "🎯 **Thể loại:** Party Minigame đoán ý đồng đội\n"
            "💬 **Luật chơi:** Mỗi vòng, bot đưa ra 1 câu hỏi mở. Mọi người bí mật nhập 1 từ trả lời.\n"
            "🔥 **Khớp ý:** Càng nhiều người có cùng suy nghĩ, điểm nhận được càng cao!\n"
            "🌟 **Đại Hợp Ý:** Nếu 100% cả phòng cùng 1 đáp án -> Nhận siêu bonus +20đ!\n\n"
            "──────────────────────────────\n"
            f"👑 **Chủ phòng:** <@{game.host_id}>\n"
            f"⚙️ **Cài đặt:** `{game.total_rounds} Vòng` • `{diff_text}`\n"
            f"👥 **Người tham gia ({len(game.active_players)}/{game.MAX_PLAYERS}):** *(Tối thiểu {game.MIN_PLAYERS} người)*\n"
            f"{players_text}\n"
            "──────────────────────────────\n"
            "👉 *Bấm **🟢 Tham Gia** để vào phòng. Chủ phòng có thể chỉnh độ khó & số vòng bên dưới.*"
        )

        embed = make_embed(
            title="✨ PHÒNG CHỜ: HỢP Ý (TÂM ĐẦU Ý HỢP)",
            description=desc,
            color=GOLD_COLOR
        )
        embed.set_footer(text="🎰 Casino Bot • Party Minigame Hợp Ý")
        return embed

    def build_progress_bar(self, remaining: int, total: int = QUESTION_TIMEOUT) -> str:
        blocks = 10
        filled = max(0, min(blocks, int((remaining / total) * blocks)))
        unfilled = blocks - filled
        return f"`[{'█' * filled}{'░' * unfilled}]` **{remaining}s**"

    def build_question_embed(self, game: HopyGame, remaining_seconds: int) -> discord.Embed:
        q_data = game.current_question or {}
        cat = q_data.get("category", "Đời Sống")
        q_text = q_data.get("question", "...")

        ans_count, total_count, _ = game.get_answered_status()
        time_bar = self.build_progress_bar(remaining_seconds, QUESTION_TIMEOUT)

        status_lines = []
        for p in game.active_players:
            if p.user_id in game.round_raw_answers:
                status_lines.append(f"🟢 **{p.display_name}** *(Đã nộp bài)*")
            else:
                status_lines.append(f"⏳ {p.display_name} *(Đang suy nghĩ...)*")

        desc = (
            f"📌 **Chủ đề:** `{cat}`\n"
            f"❓ **CÂU HỎI:**\n"
            f"### {q_text}\n\n"
            f"⏱️ **Thời gian còn lại:** {time_bar}\n"
            f"📝 **Tiến độ:** `{ans_count}/{total_count}` người đã nộp\n"
            "──────────────────────────────\n"
            f"{chr(10).join(status_lines)}\n"
            "──────────────────────────────\n"
            "👉 *Bấm nút **✍️ Trả Lời** bên dưới để mở ô nhập từ khóa ngắn gọn!*"
        )

        embed = make_embed(
            title=f"🎯 VÒNG {game.current_round}/{game.total_rounds}: CÙNG SUY NGHĨ NÀO!",
            description=desc,
            color=GOLD_COLOR
        )
        embed.set_footer(text="🤫 Câu trả lời của bạn hoàn toàn bảo mật cho đến khi reveal!")
        return embed

    def build_revealing_embed(self, game: HopyGame) -> discord.Embed:
        desc = (
            "⏳ **Hết thời gian nộp bài!**\n\n"
            "🔄 *Hệ thống đang quét và đồng bộ suy nghĩ của tất cả người chơi trong phòng...*\n"
            "✨ *Liệu ai sẽ tâm đầu ý hợp với ai? Cùng chờ xem!*"
        )
        embed = make_embed(
            title=f"🔍 VÒNG {game.current_round}/{game.total_rounds}: ĐANG KHỚP Ý...",
            description=desc,
            color=discord.Color.purple()
        )
        embed.set_footer(text="🎲 Khoảnh khắc kịch tính...")
        return embed

    def build_reveal_embed(self, game: HopyGame, eval_res: RoundEvaluation) -> discord.Embed:
        q_data = game.current_question or {}
        q_text = q_data.get("question", "...")

        sections = []

        # Hiệu ứng đặc biệt nếu Đại Hợp Ý
        if eval_res.is_dai_hop_y:
            sections.append(
                "🌟🌟🌟 **ĐẠI HỢP Ý! TOÀN BỘ PHÒNG ĐỒNG LÒNG** 🌟🌟🌟\n"
                "*Không thể tin được! 100% người chơi cùng chung một suy nghĩ! (+20đ Bonus)*\n"
            )

        # Các nhóm trùng
        if eval_res.matched_groups:
            sections.append("🔥 **CÁC CẶP / NHÓM TRÙNG Ý:**")
            for grp in eval_res.matched_groups:
                word = grp["display_word"]
                pts = grp["points_each"]
                names = ", ".join([f"**{p.display_name}**" for p in grp["players"]])
                sections.append(f"• Từ khóa `[{word}]` *(+{pts}đ)*: {names}")
            sections.append("")

        # Những người lẻ loi
        if eval_res.solos:
            sections.append("💭 **LẺ LOI KHÔNG TRÙNG AI (0đ):**")
            for solo in eval_res.solos:
                p = solo["player"]
                raw = solo["raw_answer"]
                sections.append(f"• **{p.display_name}**: \"{raw}\"")
            sections.append("")

        # Không trả lời
        if eval_res.no_answers:
            sections.append("⏳ **KHÔNG KỊP TRẢ LỜI (0đ):**")
            no_names = ", ".join([f"{p.display_name}" for p in eval_res.no_answers])
            sections.append(f"• {no_names}")
            sections.append("")

        # Trường hợp cả phòng không ai trùng ai
        if eval_res.is_all_solos:
            sections.append("😅 *Cả phòng mỗi người một phách, chẳng ai hợp ý nhau cả!*\n")

        # Bảng điểm tạm thời
        board = game.get_leaderboard()
        leaderboard_lines = []
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
        for idx, p in enumerate(board):
            medal = medals[idx] if idx < len(medals) else "🔹"
            round_gain = p.round_scores.get(game.current_round, 0)
            gain_str = f"*(+{round_gain}đ)*" if round_gain > 0 else "*(+0đ)*"
            leaderboard_lines.append(f"{medal} **{p.display_name}**: `{p.score}đ` {gain_str}")

        desc = (
            f"❓ **Câu hỏi:** *{q_text}*\n"
            "──────────────────────────────\n"
            f"{chr(10).join(sections)}"
            "──────────────────────────────\n"
            "🏆 **BẢNG ĐIỂM HIỆN TẠI:**\n"
            f"{chr(10).join(leaderboard_lines)}\n"
        )

        embed = make_embed(
            title=f"🎉 KẾT QUẢ VÒNG {game.current_round}/{game.total_rounds}",
            description=desc,
            color=GOLD_COLOR
        )
        embed.set_footer(text=f"⏩ Tự động chuyển vòng tiếp theo sau {INTERIM_DELAY}s hoặc chủ phòng bấm chuyển ngay.")
        return embed

    def build_game_over_embed(self, game: HopyGame) -> discord.Embed:
        board = game.get_leaderboard()
        mvp = game.get_mvp()

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
        ranking_lines = []
        for idx, p in enumerate(board):
            medal = medals[idx] if idx < len(medals) else "🔹"
            ranking_lines.append(
                f"{medal} **{p.display_name}** — **{p.score} điểm** *(Trùng ý {p.match_count} lần)*"
            )

        mvp_text = f"👑 **MVP TÂM ĐẦU Ý HỢP:** <@{mvp.user_id}> ({mvp.match_count} lần bắt sóng thành công!)" if mvp else ""

        desc = (
            f"🎊 Trận đấu **HỢP Ý** đã chính thức khép lại sau **{game.total_rounds} vòng** đầy kịch tính!\n\n"
            f"{mvp_text}\n"
            "──────────────────────────────\n"
            "🏆 **BẢNG XẾP HẠNG CHUNG CUỘC:**\n"
            f"{chr(10).join(ranking_lines)}\n"
            "──────────────────────────────\n"
            "💖 Cảm ơn mọi người đã tham gia! Bấm **🔄 Chơi Ván Mới** để mở phòng chơi tiếp!"
        )

        embed = make_embed(
            title="👑 BẢNG TỔNG KẾT: HỢP Ý (TÂM ĐẦU Ý HỢP)",
            description=desc,
            color=GOLD_COLOR
        )
        embed.set_footer(text="🎰 Casino Bot • Party Minigame Hợp Ý")
        return embed

    # --------------------------------------------------------------------------
    #  REFRESH / FLOW HELPERS
    # --------------------------------------------------------------------------

    async def refresh_lobby_embed(self, game: HopyGame):
        channel = self.client.get_channel(game.channel_id)
        if not channel or not game.message_id:
            return
        try:
            msg = await channel.fetch_message(game.message_id)
            embed = self.build_lobby_embed(game)
            view = HopyLobbyView(self, game)
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logger.warning(f"Hopy: Lỗi khi refresh lobby embed: {e}")

    async def refresh_question_embed(self, game: HopyGame):
        """Cập nhật số người đã trả lời khi có người vừa nộp qua modal"""
        if game.phase != GamePhase.QUESTION:
            return
        channel = self.client.get_channel(game.channel_id)
        if not channel or not game.message_id:
            return
        try:
            msg = await channel.fetch_message(game.message_id)
            embed = self.build_question_embed(game, getattr(game, "_current_timer_remaining", QUESTION_TIMEOUT))
            await msg.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Hopy: Lỗi khi refresh question embed: {e}")

    # --------------------------------------------------------------------------
    #  GAME LOOP
    # --------------------------------------------------------------------------

    async def start_game_session(self, game: HopyGame):
        """Bắt đầu chuỗi các vòng chơi với xử lý ngoại lệ an toàn"""
        channel = self.client.get_channel(game.channel_id)
        if not channel or not game.message_id:
            self.active_games.pop(game.channel_id, None)
            return

        try:
            game.prepare_game()
            self.force_reveal_flags[game.channel_id] = False
            self.skip_wait_flags[game.channel_id] = False

            while not game.is_game_over():
                # Kiểm tra số người chơi còn lại
                if len(game.active_players) < game.MIN_PLAYERS:
                    embed = make_embed(
                        title="⚠️ TRẬN ĐẤU KẾT THÚC SỚM",
                        description=f"Trận đấu đã dừng lại do số người chơi trong phòng ít hơn {game.MIN_PLAYERS} người.",
                        color=discord.Color.orange()
                    )
                    try:
                        msg = await channel.fetch_message(game.message_id)
                        await msg.edit(embed=embed, view=None)
                    except Exception:
                        pass
                    return

                # 1. Bắt đầu vòng mới
                game.start_next_round()
                self.force_reveal_flags[game.channel_id] = False
                self.skip_wait_flags[game.channel_id] = False

                view = HopyQuestionView(self, game)
                try:
                    msg = await channel.fetch_message(game.message_id)
                    embed = self.build_question_embed(game, QUESTION_TIMEOUT)
                    await msg.edit(embed=embed, view=view)
                except Exception as e:
                    logger.warning(f"Hopy: Không thể gửi câu hỏi vòng {game.current_round}: {e}")
                    return

                # 2. Vòng lặp đếm ngược thời gian
                remaining = QUESTION_TIMEOUT
                while remaining > 0:
                    game._current_timer_remaining = remaining
                    await asyncio.sleep(2)
                    remaining -= 2

                    # Kiểm tra nếu tất cả đã nộp hoặc chủ phòng chốt sớm
                    if game.have_all_answered() or self.force_reveal_flags.get(game.channel_id):
                        break

                    # Cập nhật progress bar trên embed mỗi 4s để tránh rate limit
                    if remaining % 4 == 0 and game.phase == GamePhase.QUESTION:
                        try:
                            embed = self.build_question_embed(game, remaining)
                            await msg.edit(embed=embed)
                        except Exception:
                            pass

                # 3. Trạng thái Đang Khớp Ý (Suspense delay 1.5s)
                game.phase = GamePhase.REVEALING
                revealing_embed = self.build_revealing_embed(game)
                try:
                    await msg.edit(embed=revealing_embed, view=None)
                except Exception:
                    pass
                await asyncio.sleep(1.5)

                # 4. Reveal & Tính điểm
                eval_res = game.evaluate_round()
                reveal_embed = self.build_reveal_embed(game, eval_res)
                next_view = HopyNextRoundView(self, game)
                try:
                    await msg.edit(embed=reveal_embed, view=next_view)
                except Exception:
                    pass

                # 5. Chờ trước khi qua vòng tiếp theo (cho phép host bấm nút skip)
                wait_time = INTERIM_DELAY
                while wait_time > 0:
                    if self.skip_wait_flags.get(game.channel_id):
                        break
                    await asyncio.sleep(1)
                    wait_time -= 1

            # 6. Tổng kết trận đấu (Game Over)
            game.phase = GamePhase.GAME_OVER
            game_over_embed = self.build_game_over_embed(game)
            end_view = HopyGameEndView(self, game)
            try:
                msg = await channel.fetch_message(game.message_id)
                await msg.edit(embed=game_over_embed, view=end_view)
            except Exception as e:
                logger.warning(f"Hopy: Lỗi khi hiển thị màn hình kết thúc: {e}")

        except Exception as e:
            logger.exception(f"Hopy: Lỗi ngoại lệ trong start_game_session: {e}")
        finally:
            # Luôn dọn dẹp state để không bao giờ bị kẹt phòng
            self.active_games.pop(game.channel_id, None)
            self.force_reveal_flags.pop(game.channel_id, None)
            self.skip_wait_flags.pop(game.channel_id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Hopy(bot))
