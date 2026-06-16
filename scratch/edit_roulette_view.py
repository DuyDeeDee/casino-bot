import os

filepath = "app/discord_bot/cogs/roulette.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Locate RouletteLobbyView's async def on_timeout
old_timeout_start = "    async def on_timeout(self):"
idx_start = content.find(old_timeout_start)
if idx_start == -1:
    print("Error: Could not find on_timeout start!")
    exit(1)

# Locate the end of view_stats just before class Roulette
old_view_stats_end = """        await interaction.response.send_message(embed=embed, ephemeral=True)"""
idx_end = content.find(old_view_stats_end, idx_start)
if idx_end == -1:
    print("Error: Could not find view_stats end!")
    exit(1)

# Include the length of old_view_stats_end
idx_end += len(old_view_stats_end)

new_block = """    async def on_timeout(self):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if lobby:
            if self.channel_id in self.roulette_cog.active_lobbies:
                del self.roulette_cog.active_lobbies[self.channel_id]
            try:
                embed = discord.Embed(title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰", description="⏱️ Bàn quay đã tự động đóng do hết thời gian chờ.", color=discord.Color.red())
                await lobby["message"].edit(embed=embed, view=None)
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Cược Đơn Giản", style=discord.ButtonStyle.primary, emoji="🔴")
    async def bet_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        view = RouletteSimpleBetView(interaction.user.id, self.roulette_cog)
        await interaction.response.send_message(
            "Chọn cửa cược Màu / Chẵn Lẻ / Thấp Cao từ menu bên dưới:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Cược Nhóm (Cột/Tá)", style=discord.ButtonStyle.primary, emoji="🏛")
    async def bet_group(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        view = RouletteGroupBetView(interaction.user.id, self.roulette_cog)
        await interaction.response.send_message(
            "Chọn cửa cược Cột / Tá từ menu bên dưới:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Cược Số", style=discord.ButtonStyle.success, emoji="🔢")
    async def bet_numbers(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        modal = RouletteNumberBetModal(self.roulette_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Thống Kê & Rank", style=discord.ButtonStyle.secondary, emoji="📊")
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = self.roulette_cog.economy.get_roulette(interaction.user.id)
        lucky_number = get_daily_lucky_number(interaction.user.id)
        vip = get_user_vip(stats)
        
        # calculate win rate
        plays = stats["plays"]
        win_rate = (stats["wins"] / plays * 100) if plays > 0 else 0
        
        # most hit number
        num_stats = stats.get("number_stats", {})
        if num_stats:
            most_lucky_num = max(num_stats, key=num_stats.get)
            hit_count = num_stats[most_lucky_num]
            most_lucky_str = f"Số **{most_lucky_num}** ({hit_count} lần trúng)"
        else:
            most_lucky_str = "Chưa có"

        ach_list = stats.get("achievements", [])
        ach_str = "\\n".join(f"🏆 {ach}" for ach in ach_list) if ach_list else "*Chưa có*"
        
        desc = (
            f"**CẤP BẬC VIP:** {vip['emoji']} **{vip['title']}**\\n"
            f"💰 Hạn mức cược tối đa: Không giới hạn\\n"
            f"🍀 Số may mắn hôm nay: **{lucky_number}** (Thưởng x40 khi cược trúng)\\n"
            f"⚡ Chip May Mắn hiện có: **{stats['chips']}/10** (Thưởng thêm `+{stats['chips'] * 0.5}%`)\\n\\n"
            f"📊 **BẢNG THỐNG KÊ CHI TIẾT:**\\n"
            f"• Đã chơi: `{plays}` ván\\n"
            f"• Thắng: `{stats['wins']}` | Thua: `{stats['losses']}`\\n"
            f"• Tỉ lệ thắng: `{win_rate:.1f}%`\\n"
            f"• Chuỗi thắng hiện tại: `{stats['streak']}` ván\\n"
            f"• Chuỗi thắng dài nhất: `{stats['max_streak']}` ván\\n"
            f"• Tổng lãi ròng: `{(stats['profit']):+,} VNĐ`\\n"
            f"• Số may mắn nhất: {most_lucky_str}\\n\\n"
            f"🏆 **THÀNH TỰU ĐÃ ĐẠT ({len(ach_list)}/7):**\\n"
            f"{ach_str}"
        )
        
        embed = make_embed(
            title=f"📊 THỐNG KÊ ROULETTE - {interaction.user.display_name} 📊",
            description=desc,
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)"""

new_content = content[:idx_start] + new_block + content[idx_end:]

# Verify compilation
try:
    compile(new_content, filepath, "exec")
    print("Compilation check: OK")
except Exception as e:
    print("Compilation error:", e)
    exit(1)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_content)
print("File written successfully!")
