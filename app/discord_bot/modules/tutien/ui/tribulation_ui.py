"""
Interactive Discord Views for Real-Time Lôi Kiếp & Heart Demon Mini-Games.
"""

import asyncio
import time
import discord
from typing import Callable, Optional
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.engines.tribulation import (
    calculate_tribulation_damage,
    HEART_DEMON_QUESTIONS
)


class TribulationWaveView(discord.ui.View):
    """
    Real-time interactive button View for Lôi Kiếp (10s response time per wave).
    """
    def __init__(self, player: CultivatorProfile, wave: int, total_waves: int, damage: int):
        super().__init__(timeout=10.0)
        self.player = player
        self.wave = wave
        self.total_waves = total_waves
        self.damage = damage
        self.chosen_action: Optional[str] = None
        self.interaction: Optional[discord.Interaction] = None

    @discord.ui.button(label="🛡️ Dùng Pháp Bảo", style=discord.ButtonStyle.primary)
    async def use_shield(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.user_id:
            await interaction.response.send_message("❌ Bạn không phải là người đang độ kiếp!", ephemeral=True)
            return
        self.chosen_action = "SHIELD"
        self.interaction = interaction
        self.stop()

    @discord.ui.button(label="💊 Uống Kháng Lôi Đan", style=discord.ButtonStyle.success)
    async def use_pill(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.user_id:
            await interaction.response.send_message("❌ Bạn không phải là người đang độ kiếp!", ephemeral=True)
            return
        self.chosen_action = "PILL"
        self.interaction = interaction
        self.stop()

    @discord.ui.button(label="⚔️ Vận Công Nghênh ĐÓN", style=discord.ButtonStyle.danger)
    async def face_head_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.user_id:
            await interaction.response.send_message("❌ Bạn không phải là người đang độ kiếp!", ephemeral=True)
            return
        self.chosen_action = "FACE"
        self.interaction = interaction
        self.stop()


class HeartDemonQuizView(discord.ui.View):
    """
    Heart Demon quiz choice View (8s timer).
    """
    def __init__(self, player: CultivatorProfile, question_data: dict):
        super().__init__(timeout=8.0)
        self.player = player
        self.question_data = question_data
        self.selected_idx: Optional[int] = None
        self.interaction: Optional[discord.Interaction] = None

        # Add buttons for choices
        for idx, option in enumerate(question_data["options"]):
            btn = discord.ui.Button(
                label=option["label"][:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"quiz_opt_{idx}"
            )
            btn.callback = self.create_callback(idx)
            self.add_item(btn)

    def create_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.user_id:
                await interaction.response.send_message("❌ Tâm Ma này không thuộc về bạn!", ephemeral=True)
                return
            self.selected_idx = idx
            self.interaction = interaction
            self.stop()
        return callback
