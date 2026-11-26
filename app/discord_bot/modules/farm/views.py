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
    def __init__(self, user_id, pages, *, start=0, rate_pages=False):
        super().__init__(timeout=60 if rate_pages else 300)
        self.user_id = user_id
        self.pages = pages
        self.index = max(0, min(start, len(pages) - 1))
        self.rate_pages = rate_pages
        if rate_pages:
            self.previous.emoji = self.next.emoji = None
            self.previous.label = "◀ Trước"
            self.next.label = "Sau ▶"
        self._update_buttons()
        self.message = None

    @property
    def current(self):
        return self.pages[self.index]

    def _update_buttons(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1

    async def interaction_check(self, interaction):
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("Chỉ người mở menu mới có thể đổi trang.", ephemeral=True)
        return False

    async def on_timeout(self):
        if self.message:
            try:
                if self.rate_pages:
                    self.previous.disabled = self.next.disabled = True
                    await self.message.edit(view=self)
                else:
                    await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def turn(self, interaction, offset):
        self.index = max(0, min(self.index + offset, len(self.pages) - 1))
        self._update_buttons()
        await interaction.response.edit_message(embed=self.current, view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        await self.turn(interaction, -1)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        await self.turn(interaction, 1)
