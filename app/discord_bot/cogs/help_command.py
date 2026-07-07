
import discord
from discord.ext import commands
from discord.ui import Select, View

from app.discord_bot.modules.helpers import ABS_PATH, make_embed


# ──────────────────────────────────────────────
#  Mapping cog → nhóm hiển thị
# ──────────────────────────────────────────────
COG_GROUP_MAPPING = {
    "Blackjack":     ("🎲", "Cờ Bạc"),
    "MultiBlackjack":("🎲", "Cờ Bạc"),
    "GamblingGames": ("🎲", "Cờ Bạc"),
    "Daga":          ("🎲", "Cờ Bạc"),
    "Roulette":      ("🎲", "Cờ Bạc"),
    "CoinFlip":      ("🎲", "Cờ Bạc"),
    "HorseRace":     ("🎲", "Cờ Bạc"),
    "Crash":         ("🎲", "Cờ Bạc"),
    "ScratchCard":   ("🎲", "Cờ Bạc"),
    "Bkb":           ("🎲", "Cờ Bạc"),
    "Baito":         ("🎲", "Cờ Bạc"),
    "Mines":         ("🎲", "Cờ Bạc"),
    "Plinko":        ("🎲", "Cờ Bạc"),
    "HighLow":       ("🎲", "Cờ Bạc"),
    "Tower":         ("🎲", "Cờ Bạc"),
    "General":       ("💼", "General"),
    "Simulator":     ("💼", "General"),
    "Slots":         ("📈", "Giao Dịch"),
    "AI":            ("🤖", "AI"),
    "Xe":            ("🏎️", "Đua Xe"),
}

GROUP_ORDER = ["💼 General", "🎲 Cờ Bạc", "📈 Giao Dịch", "🏎️ Đua Xe", "🤖 AI"]


def _build_groups(client: commands.Bot):
    """Gom các lệnh theo nhóm, trả về dict {group_label: [commands]}."""
    groups: dict[str, list[commands.Command]] = {}
    for cog in client.cogs.values():
        cog_cmds = [c for c in cog.get_commands() if not c.hidden]
        if not cog_cmds:
            continue
        emoji, name = COG_GROUP_MAPPING.get(cog.qualified_name, ("📦", cog.qualified_name))
        label = f"{emoji} {name}"
        groups.setdefault(label, []).extend(cog_cmds)
    return groups


def _group_embed(group_label: str, cmds: list[commands.Command], prefix: str) -> discord.Embed:
    """Tạo embed cho 1 nhóm lệnh."""
    sorted_cmds = sorted(cmds, key=lambda c: c.name)

    lines = []
    for cmd in sorted_cmds:
        brief = (cmd.brief or "Không có mô tả.").split("\n")[0].strip()
        aliases = ""
        if cmd.aliases:
            aliases = " `(" + ", ".join(cmd.aliases) + ")`"
        lines.append(f"> `{prefix}{cmd.name}`{aliases}\n> ╰ {brief}")

    description = "\n".join(lines) if lines else "_Không có lệnh nào._"

    embed = make_embed(
        title=f"{group_label}",
        description=description,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Tổng: {len(sorted_cmds)} lệnh  •  Dùng {prefix}help <lệnh> để xem chi tiết")
    return embed


def _home_embed(groups: dict, prefix: str) -> discord.Embed:
    """Trang chủ của help."""
    embed = make_embed(
        title="📖 Danh Sách Lệnh",
        description=(
            f"Prefix của bot là **`{prefix}`**\n"
            "Chọn một danh mục từ menu bên dưới để xem các lệnh.\n"
            f"Hoặc dùng `{prefix}help <tên_lệnh>` để xem chi tiết."
        ),
        color=discord.Color.blurple(),
    )

    # Hiện bảng tóm tắt theo thứ tự ưu tiên
    ordered = [(g, groups[g]) for g in GROUP_ORDER if g in groups]
    others  = [(g, groups[g]) for g in groups if g not in GROUP_ORDER]

    rows = []
    for label, cmds in ordered + others:
        rows.append(f"{label} — **{len(cmds)}** lệnh")

    embed.add_field(name="Các danh mục", value="\n".join(rows), inline=False)
    return embed


# ──────────────────────────────────────────────
#  Discord UI — Select Menu
# ──────────────────────────────────────────────
class CategorySelect(Select):
    def __init__(self, groups: dict, prefix: str):
        self.groups = groups
        self.prefix = prefix

        ordered = [g for g in GROUP_ORDER if g in groups]
        others  = [g for g in groups if g not in GROUP_ORDER]
        all_groups = ordered + others

        options = [
            discord.SelectOption(label="🏠 Trang chủ", value="__home__", description="Quay về danh sách danh mục")
        ]
        for label in all_groups:
            cmds = groups[label]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=label,
                    description=f"{len(cmds)} lệnh",
                )
            )

        super().__init__(
            placeholder="📂 Chọn một danh mục để xem lệnh…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        if chosen == "__home__":
            embed = _home_embed(self.groups, self.prefix)
        else:
            embed = _group_embed(chosen, self.groups[chosen], self.prefix)
        await interaction.response.edit_message(embed=embed)


class HelpView(View):
    def __init__(self, groups: dict, prefix: str):
        super().__init__(timeout=120)
        self.add_item(CategorySelect(groups, prefix))

    async def on_timeout(self):
        # Vô hiệu hoá select khi hết thời gian
        for item in self.children:
            item.disabled = True


# ──────────────────────────────────────────────
#  Cog
# ──────────────────────────────────────────────
class Help(commands.Cog, name="help"):
    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.command(
        brief="Liệt kê các lệnh và thông tin chi tiết.",
        usage="help [tên_lệnh]",
        hidden=True,
    )
    async def help(self, ctx: commands.Context, request: str | None = None):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        # ── Chi tiết 1 lệnh cụ thể ──
        if request:
            command = self.client.get_command(request)
            if command is None:
                await ctx.invoke(self.client.get_command("help"))
                return

            embed = make_embed(
                title=f"🔍 Chi tiết lệnh: `{prefix}{command.name}`",
                description=command.brief or "Không có mô tả.",
                color=discord.Color.gold(),
            )
            embed.add_field(name="📌 Cách dùng", value=f"`{prefix}{command.usage}`", inline=False)

            if command.aliases:
                aliases = "  ".join(f"`{prefix}{a}`" for a in command.aliases)
                embed.add_field(name="🔀 Bí danh", value=aliases, inline=False)

            if isinstance(command, commands.Group):
                subs = sorted(
                    [s for s in command.commands if not s.hidden],
                    key=lambda c: c.name,
                )
                if subs:
                    sub_text = "\n".join(
                        f"> `{prefix}{s.name}` — {s.brief or 'Không có mô tả.'}"
                        for s in subs
                    )
                    embed.add_field(name="📂 Lệnh con", value=sub_text, inline=False)

            embed.set_footer(text=f"Dùng {prefix}help để xem tất cả lệnh")
            await ctx.send(embed=embed)
            return

        # ── Trang chủ với Select Menu ──
        groups = _build_groups(self.client)
        embed  = _home_embed(groups, prefix)
        view   = HelpView(groups, prefix)

        await ctx.send(embed=embed, view=view)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def kill(self, ctx: commands.Context):
        await self.client.remove_cog("handlers")
        await self.client.close()


async def setup(client: commands.Bot):
    await client.add_cog(Help(client))
