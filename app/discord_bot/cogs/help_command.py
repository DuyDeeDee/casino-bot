import os

import discord
from discord.ext import commands

from app.discord_bot.modules.helpers import ABS_PATH, make_embed


class Help(commands.Cog, name="help"):
    def __init__(self, client: commands.Bot):
        self.client = client

    def _format_command(self, command: commands.Command) -> str:
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
        base_name = f"🔹 **{prefix}{command.name}**"
        aliases_str = ""
        if command.aliases:
            aliases = ", ".join(
                f"{prefix}{alias}" for alias in command.aliases
            )
            aliases_str = f" ({aliases})"
        brief = (command.brief or "Không có mô tả.").split('\n')[0].strip()
        return f"{base_name}{aliases_str} — {brief}"

    @commands.command(
        brief="Liệt kê các lệnh và thông tin chi tiết.",
        usage="help [tên_lệnh]",
        hidden=True,
    )
    async def help(self, ctx: commands.Context, request: str | None = None):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
        if not request:
            embed = make_embed(
                title="📖 DANH SÁCH LỆNH CASINO BOT 📖",
                description=f"Sử dụng `{prefix}help <tên_lệnh>` để xem chi tiết cách dùng và ví dụ.",
                color=discord.Color.blue(),
            )
            
            cog_group_mapping = {
                "Blackjack": "🎲 Cờ Bạc",
                "MultiBlackjack": "🎲 Cờ Bạc",
                "GamblingGames": "🎲 Cờ Bạc",
                "Daga": "🎲 Cờ Bạc",
                "Roulette": "🎲 Cờ Bạc",
                "CoinFlip": "🎲 Cờ Bạc",
                "HorseRace": "🎲 Cờ Bạc",
                "Crash": "🎲 Cờ Bạc",
                "ScratchCard": "🎲 Cờ Bạc",
                "Bkb": "🎲 Cờ Bạc",
                "Baito": "🎲 Cờ Bạc",
                "Mines": "🎲 Cờ Bạc",
                "Plinko": "🎲 Cờ Bạc",
                "HighLow": "🎲 Cờ Bạc",
                "General": "💼 General",
                "Simulator": "💼 General",
                "Slots": "📈 Giao dịch",
                "Tower": "🎲 Cờ Bạc",
                "AI": "🤖 AI",
                "Xe": "🏎️ Đua Xe",
            }
            
            groups = {}
            for cog in self.client.cogs.values():
                cog_commands = [command for command in cog.get_commands() if not command.hidden]
                if not cog_commands:
                    continue
                group_name = cog_group_mapping.get(cog.qualified_name, cog.qualified_name)
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].extend(cog_commands)

            group_order = ["💼 General", "🎲 Cờ Bạc", "📈 Giao dịch", "🏎️ Đua Xe", "🤖 AI"]

            
            # Show groups in a designated order
            for group_name in group_order:
                if group_name in groups:
                    commands_list = sorted(groups[group_name], key=lambda c: c.name)
                    commands_str = ", ".join(f"`{cmd.name}`" for cmd in commands_list)
                    embed.add_field(
                        name=group_name,
                        value=commands_str,
                        inline=False,
                    )
                    
            for group_name in groups:
                if group_name not in group_order:
                    commands_list = sorted(groups[group_name], key=lambda c: c.name)
                    commands_str = ", ".join(f"`{cmd.name}`" for cmd in commands_list)
                    embed.add_field(
                        name=group_name,
                        value=commands_str,
                        inline=False,
                    )

            fp = os.path.join(ABS_PATH, "modules/cards/aces.png")
            file = discord.File(fp, filename="aces.png")
            embed.set_thumbnail(url="attachment://aces.png")
        else:
            command = self.client.get_command(request)
            if command is None:
                await ctx.invoke(self.client.get_command("help"))
                return
            embed = make_embed(
                title=f"🔍 Chi tiết lệnh: {command.name}",
                description=command.brief,
                footer="* tùy chọn",
                color=discord.Color.gold(),
            )
            embed.add_field(
                name="Cách dùng:",
                value=f"`{prefix}{command.usage}`",
            )
            if command.aliases:
                aliases = ", ".join(
                    f"`{prefix}{alias}`"
                    for alias in command.aliases
                )
                embed.add_field(name="Bí danh:", value=aliases)
            
            if isinstance(command, commands.Group):
                subcommands_list = sorted([sub for sub in command.commands if not sub.hidden], key=lambda c: c.name)
                subcommands = "\n".join(f"🔹 **{sub.name}** — {sub.brief or 'Không có mô tả.'}" for sub in subcommands_list)
                if subcommands:
                    embed.add_field(name="Các lệnh con:", value=subcommands, inline=False)
                    
            file = None

        await ctx.send(file=file, embed=embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def kill(self, ctx: commands.Context):
        await self.client.remove_cog("handlers")
        await self.client.close()


async def setup(client: commands.Bot):
    await client.add_cog(Help(client))
