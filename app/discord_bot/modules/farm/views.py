"""Discord controls shared by the Ilis Farm menus."""

import discord


class FarmChoices(discord.ui.View):
    def __init__(self, user_id, options, choose, *, timeout):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.choose = choose
        self.message = None
        self.used = False
        for key, label, style, disabled in options:
            button = discord.ui.Button(label=label, style=style, disabled=disabled)

            async def callback(interaction, value=key):
                if self.used:
                    await interaction.response.send_message("Lựa chọn này đã được xử lý.", ephemeral=True)
                    return
                self.used = True
                self.stop()
                await interaction.response.defer()
                await self.choose(interaction, value)

            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction):
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("Chỉ người mở menu mới có thể chọn.", ephemeral=True)
        return False

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class FarmPages(discord.ui.View):
    def __init__(self, user_id, pages):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.pages = pages
        self.index = 0
        self.previous.disabled = True
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("Chỉ người mở menu mới có thể đổi trang.", ephemeral=True)
        return False

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def turn(self, interaction, offset):
        self.index = max(0, min(self.index + offset, len(self.pages) - 1))
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        await self.turn(interaction, -1)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        await self.turn(interaction, 1)
