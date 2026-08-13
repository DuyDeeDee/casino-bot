
import discord
from discord.ext import commands
from discord.ui import Select, View

from app.discord_bot.modules.helpers import ABS_PATH, make_embed


# ──────────────────────────────────────────────
#  Mapping cog → nhóm hiển thị
# ──────────────────────────────────────────────
COG_GROUP_MAPPING = {
    "Blackjack":     ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "MultiBlackjack":("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "GamblingGames": ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Roulette":      ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "CoinFlip":      ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "HorseRace":     ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Crash":         ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "ScratchCard":   ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Bkb":           ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Baito":         ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Mines":         ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Plinko":        ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "HighLow":       ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "Tower":         ("<:cobac:1531333888931135518>", "Cờ Bạc"),
    "General":       ("<:gen:1531709110376988743>", "General"),
    "Simulator":     ("<:gen:1531709110376988743>", "General"),
    "Slots":         ("<:trade:1531333907868291132>", "Giao Dịch"),
    "Xe":            ("<:trade:1531333907868291132>", "Giao Dịch"),
    "AI":            ("<:AI:1531709092362457292>", "AI"),
    "AIHelper":      ("<:AI:1531709092362457292>", "AI"),
    # Fungame
    "UNO":           ("<:game:1531333922535768226>", "Fungame"),
    "GiaiMa":        ("<:game:1531333922535768226>", "Fungame"),
    "Masoi":         ("<:game:1531333922535768226>", "Fungame"),
    # Function
    "afk":           ("<:function:1531341821257716025>", "Function"),
    "Afk":           ("<:function:1531341821257716025>", "Function"),
    "Giveaway":      ("<:function:1531341821257716025>", "Function"),
    "Jail":          ("<:function:1531341821257716025>", "Function"),
    "ChannelControl":("<:function:1531341821257716025>", "Function"),
    # Lixi & Marry
    "Lixi":          ("<:lixi:1531333938164007032>", "Lixi"),
    "Marry":         ("<:marry:1531333950234955799>", "Marry"),
    # Tu Tiên
    "TuTien":        ("☯️", "Tu Tiên"),
    "TuTienCog":     ("☯️", "Tu Tiên"),
}

GROUP_ORDER = [
    "<:gen:1531709110376988743> General",
    "☯️ Tu Tiên",
    "<:cobac:1531333888931135518> Cờ Bạc",
    "<:trade:1531333907868291132> Giao Dịch",
    "<:AI:1531709092362457292> AI",
    "<:game:1531333922535768226> Fungame",
    "<:function:1531341821257716025> Function",
    "<:lixi:1531333938164007032> Lixi",
    "<:marry:1531333950234955799> Marry",
]


def _parse_label_and_emoji(raw_label: str):
    """Tách emoji (custom hoặc unicode) và label sạch cho SelectOption."""
    import re
    match = re.match(r"^(<a?:\w+:\d+>)\s*(.*)$", raw_label)
    if match:
        emoji_str, clean_title = match.groups()
        try:
            emoji = discord.PartialEmoji.from_str(emoji_str)
        except Exception:
            emoji = None
        return clean_title.strip(), emoji

    parts = raw_label.split(" ", 1)
    if len(parts) == 2:
        return parts[1].strip(), parts[0].strip()

    return raw_label, None


def _is_admin_command(cmd: commands.Command) -> bool:
    """Kiểm tra xem lệnh có phải là lệnh admin/owner hay không."""
    if cmd.hidden:
        return True
    brief = (cmd.brief or "").lower()
    name = cmd.name.lower()
    if brief.startswith("[admin]") or "[admin]" in brief or "admin" in name or "owner" in name:
        return True
    return False


def _build_groups(client: commands.Bot):
    """Gom các lệnh theo nhóm, trả về dict {group_label: [commands]}."""
    groups: dict[str, list[commands.Command]] = {}
    for cog in client.cogs.values():
        cog_cmds = [c for c in cog.get_commands() if not _is_admin_command(c)]
        if not cog_cmds:
            continue
        emoji, name = COG_GROUP_MAPPING.get(cog.qualified_name, ("📦", cog.qualified_name))
        label = f"{emoji} {name}"
        groups.setdefault(label, []).extend(cog_cmds)
    return groups


def _group_embed(group_label: str, cmds: list[commands.Command], prefix: str) -> discord.Embed:
    """Tạo embed cho 1 nhóm lệnh."""
    if "Tu Tiên" in group_label or "TuTien" in group_label:
        embed = discord.Embed(
            title="☯️ HỆ THỐNG TU TIÊN: «ĐẠI ĐẠO TRANH PHONG»",
            description=f"Prefix hiện tại của bot: **`{prefix}`**\nDưới đây là danh sách toàn bộ các lệnh Tu Tiên được phân loại theo mục:",
            color=discord.Color.purple()
        )

        categories = {
            "👤 I. NHÂN VẬT & TÂN THỦ": [
                ("nhapmon", ["taonhanvat", "nhap-mon"], "Nhập môn Tu Tiên, quay Linh Căn ngẫu nhiên (Phàm Phẩm -> Hỗn Độn) & nhận 500 Linh Thạch."),
                ("tutien-profile", ["profile", "tt", "hoso-tutien"], "Xem Thẻ Hình Ảnh PNG 18 thuộc tính nghệ thuật nhân vật."),
                ("tamcanh", ["can-co", "tam-canh"], "Kiểm tra tỷ lệ Đột Phá, trạng thái Tâm Cảnh & độ vững chắc Căn Cơ."),
                ("tutien-huongdan", ["huongdan", "tutienhelp"], "Xem cẩm nang hướng dẫn Tu Tiên 7 bước chi tiết."),
                ("phe-tu-vi", ["phetuvi"], "Phế bỏ toàn bộ tu vi hiện tại để tu luyện lại từ Luyện Khí Tầng 1."),
            ],
            "🧘 II. TU LUYỆN & ĐỘT PHÁ": [
                ("tu-luyen", ["tuluyen", "train"], "Tu luyện chủ động (tiêu 15 Tinh Lực, tích lũy EXP Tu Vi)."),
                ("nhap-dinh", ["nhapdinh", "bequan"], "Bế quan AFK tích lũy tài nguyên (1h, 4h, 8h, 12h, 16h, 24h)."),
                ("xuat-quan", ["xuatquan", "xuatdinh"], "Thu công xuất quan sớm & nhận quà AFK tích lũy."),
                ("luyen-the", ["luyenthe"], "Rèn luyện Thân Thể tiêu hao Linh Thạch để đột phá Tôi Thể -> Bất Diệt Thể."),
                ("dot-pha", ["dotpha", "breakthrough"], "Xung kích bình cảnh & nghênh đón Lôi Kiếp thời gian thực."),
            ],
            "⚔️ III. CHINH PHỤC HARDCORE PVE": [
                ("san-yeu", ["sanyeu", "hunt"], "Săn Yêu Quái lượt (Có 15% quái Biến Dị 3x stats, VIP 2+ gõ !san-yeu quet 10x)."),
                ("leo-thap", ["leothap", "thap"], "Thử thách Tháp Thiên Cực 100 Tầng (Mỗi 10 tầng gặp Ảo Ảnh Bản Thân)."),
                ("top-thap", ["topthap"], "Xem Bảng Xếp Hạng Leo Tháp Thiên Cực Top 10 toàn Server."),
                ("bi-canh", ["bicanh"], "Tổ đội 3-5 Tu Sĩ (Tank, DPS, Healer) đánh Bí Cảnh Cổ Đại."),
                ("bi-canh-cam-dia", ["camdia", "roguelike"], "Đột phá Mê Cung Sinh Tồn Roguelike Thái Cổ Cấm Địa (5 Phòng)."),
                ("diet-boss", ["boss-server"], "Xông vào trảm Thái Cổ Ma Vương Giáng Lâm (World Boss Server)."),
                ("cuu-thuong", ["cuuthuong", "rescue"], "Dùng Vạn Linh Đan hoặc Tiên Ngọc cứu đạo hữu bị Kinh Mạch Đoạn Tuyệt."),
                ("giai-doc", ["giaidoc", "cleanse"], "Tẩy trừ hiệu ứng Độc Tố Thấu Cốt & Tâm Ma Ô Nhiễm."),
            ],
            "🔮 IV. GACHA & SHOP TIÊN CÁC": [
                ("quay-gacha", ["gacha", "quaygacha"], "Quay Gacha 3 Đại Banners Tiên Các, Cải Mệnh Đài nhận bảo vật UR/SR."),
                ("wishlist", ["dinh-huong"], "Cấu hình Định Hướng Đạo Vận (Ưu tiên UR 100% khi lệch rate)."),
                ("xienquach", ["bocque", "quere"], "Bốc quẻ Khí Vận hàng ngày nhận Linh Duyên Phù & Tiên Ngọc."),
                ("linhbui-shop", ["doilinhbui"], "Xem & Đổi Linh Bụi Tiên Các lấy vật phẩm UR/SR tự chọn."),
                ("tiencac", ["tiencac-shop"], "Xem danh mục Shop Tiên Các (Bảo hiểm độ kiếp, Bùa cứu thương, VIP)."),
                ("mua", ["muatiencac"], "Mua vật phẩm từ Shop Tiên Các bằng Tiên Ngọc."),
                ("vip", ["the-thang"], "Xem Cấp VIP & Trạng thái Thẻ Tháng Đạo Tâm Tôn Giả."),
            ],
            "🗡️ V. TƯƠNG TÁC TU SĨ": [
                ("cuop", ["cuop-dong-phu"], "Đột nhập Động Phủ tu sĩ khác cướp Linh Thạch (Cooldown 12h)."),
            ]
        }

        for cat_title, cmd_list in categories.items():
            cat_text = ""
            for c_name, aliases, desc in cmd_list:
                alias_str = f" `({', '.join(aliases)})`" if aliases else ""
                cat_text += f"> `{prefix}{c_name}`{alias_str}\n> ╰ *{desc}*\n"
            embed.add_field(name=cat_title, value=cat_text, inline=False)

        embed.set_footer(text=f"Dùng {prefix}help <tên_lệnh> để xem chi tiết  •  Prefix: {prefix}")
        return embed

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
            discord.SelectOption(label="Trang chủ", value="__home__", emoji="🏠", description="Quay về danh sách danh mục")
        ]
        for label in all_groups:
            cmds = groups[label]
            clean_label, emoji = _parse_label_and_emoji(label)
            options.append(
                discord.SelectOption(
                    label=clean_label,
                    value=label,
                    emoji=emoji,
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
            if command is None or _is_admin_command(command):
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
                    [s for s in command.commands if not _is_admin_command(s)],
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
