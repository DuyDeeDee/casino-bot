
import discord
from discord.ext import commands
from discord.ui import Select, View

from app.config import config
from app.discord_bot.modules.helpers import ABS_PATH, make_embed

# Các lệnh kiểm tra quyền admin ngay TRONG thân hàm (không bọc decorator) nên quét động
# theo metadata không thấy được — phải liệt kê tường minh tại đây.
EXTRA_ADMIN_COMMANDS = {"invest max"}


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
    "Hopy":          ("<:game:1531333922535768226>", "Fungame"),
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
    "TuTien":        ("<:tutien:1540738237021298849>", "Tu Tiên"),
    "TuTienCog":     ("<:tutien:1540738237021298849>", "Tu Tiên"),
}

GROUP_ORDER = [
    "<:gen:1531709110376988743> General",
    "<:tutien:1540738237021298849> Tu Tiên",
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


def _is_owner_command(cmd: commands.Command) -> bool:
    """Lệnh chỉ Owner/Admin bot dùng được — bị ẨN khỏi help thường (xem qua i?adhelp)."""
    if getattr(cmd, "hidden", False):
        return True
    brief = (cmd.brief or "").lower()
    name = cmd.name.lower()
    if brief.startswith("[admin]") or "[admin]" in brief or "admin" in name or "owner" in name:
        return True
    if cmd.qualified_name in EXTRA_ADMIN_COMMANDS:
        return True
    requires = getattr(cmd, "requires", None)
    if getattr(requires, "predicates", None):
        return True
    # @commands.is_owner() / check tùy chỉnh nằm ở cmd.checks. Riêng
    # @commands.has_permissions(...) có perms dict → là lệnh quyền Discord server,
    # vẫn HIỆN trong help thường (người chơi dùng sẽ bị báo thiếu quyền).
    checks = getattr(cmd, "checks", None)
    if checks and _perms_from_checks(cmd) is None:
        return True
    # Lệnh con kế thừa gate từ group cha (vd: giftcode create/delete/list)
    parent = getattr(cmd, "parent", None)
    while parent is not None:
        if _is_owner_command(parent):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _is_admin_command(cmd: commands.Command) -> bool:
    """Lệnh giới hạn quyền (owner bot HOẶC quyền Discord server) — dùng cho i?adhelp."""
    if _is_owner_command(cmd):
        return True
    requires = getattr(cmd, "requires", None)
    return _perms_from_checks(cmd) is not None or getattr(requires, "permissions", None) is not None


def _perms_from_checks(cmd: commands.Command) -> dict | None:
    """Lấy dict quyền từ @commands.has_permissions(...) nếu lệnh có (vd {'administrator': True})."""
    for check in getattr(cmd, "checks", None) or []:
        fn = getattr(check, "predicate", None) or check
        perms = getattr(fn, "perms", None)
        if isinstance(perms, dict):
            return perms
        # Một số bản discord.py giữ perms trong closure của predicate
        for cell in getattr(fn, "__closure__", None) or ():
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if isinstance(v, dict) and v and all(
                isinstance(k, str) and isinstance(b, bool) for k, b in v.items()
            ):
                return v
    return None


def _admin_perm_label(cmd: commands.Command) -> str | None:
    """Nhãn quyền Discord yêu cầu bởi @commands.has_permissions(...), nếu có."""
    perms = _perms_from_checks(cmd)
    if not perms:
        return None
    labels = []
    for viett, key in (
        ("Quản trị viên", "administrator"),
        ("Quản lý tin nhắn", "manage_messages"),
        ("Quản lý server", "manage_guild"),
        ("Quản lý kênh", "manage_channels"),
    ):
        if perms.get(key):
            labels.append(viett)
    return " + ".join(labels) if labels else "quyền đặc biệt"


def _iter_admin_commands(client: commands.Bot) -> list[commands.Command]:
    """Quét toàn bộ lệnh của bot (kể cả subcommand của group) lấy các lệnh admin/owner."""
    found: list[commands.Command] = []

    def walk(cmds):
        for c in cmds:
            # Bỏ qua lệnh help tổng (ẩn để không lọt vào nhóm lệnh, nhưng không phải lệnh admin)
            if c.qualified_name == "help":
                continue
            if _is_admin_command(c):
                found.append(c)
            if isinstance(c, commands.Group):
                walk(c.commands)

    for cog in client.cogs.values():
        walk(cog.get_commands())
    return sorted(found, key=lambda c: c.qualified_name)


def _clean_brief(cmd: commands.Command) -> str:
    """Brief hiển thị: bỏ tag [ADMIN] rỗng, ưu tiên docstring khi brief chỉ là tag."""
    raw = (cmd.brief or "").split("\n")[0].strip()
    if not raw or raw.upper().startswith("[ADMIN"):
        raw = (cmd.short_doc or "").split("\n")[0].strip()
    if raw[:6].upper() == "[ADMIN":
        raw = raw.split("]", 1)[-1].strip()
    return raw or "Không có mô tả."


def _admin_help_embeds(client: commands.Bot, prefix: str, only_discord_perms: bool) -> list[discord.Embed]:
    """Danh sách embed liệt kê toàn bộ lệnh admin/owner, quét động từ command tree.

    Giới hạn Discord: 1 field ≤ 1024 ký tự, 1 embed ≤ 6000 ký tự — nội dung được
    chunk thành nhiều field/embed thay vì cắt ngắn để không mất lệnh nào.
    """
    cmds = _iter_admin_commands(client)
    if only_discord_perms:
        # Quản trị server (không phải admin bot) chỉ thấy lệnh họ thực sự chạy được
        cmds = [c for c in cmds if _admin_perm_label(c)]

    groups: dict[str, list[commands.Command]] = {}
    for c in cmds:
        cog = c.cog
        cog_name = cog.qualified_name if cog else "Khác"
        emoji, name = COG_GROUP_MAPPING.get(cog_name, ("📦", cog_name))
        groups.setdefault(f"{emoji} {name}", []).append(c)

    ordered = [(g, groups[g]) for g in GROUP_ORDER if g in groups]
    others = [(g, groups[g]) for g in groups if g not in GROUP_ORDER]

    fields: list[tuple[str, str]] = []
    for label, group_cmds in ordered + others:
        lines = []
        for cmd in group_cmds:
            aliases = f" `({', '.join(cmd.aliases)})`" if cmd.aliases else ""
            perm = _admin_perm_label(cmd)
            perm_tag = f" 🔑 *[{perm}]*" if perm else ""
            usage = f"`{prefix}{cmd.usage}`" if cmd.usage else f"`{prefix}{cmd.qualified_name}`"
            lines.append(f"> {usage}{aliases}{perm_tag}\n> ╰ {_clean_brief(cmd)}")
        # Chunk các dòng thành field ≤ 1000 ký tự
        buf: list[str] = []
        blen = 0
        idx = 1
        for ln in lines:
            if blen + len(ln) + 1 > 1000 and buf:
                fields.append((label if idx == 1 else f"{label} ({idx})", "\n".join(buf)))
                buf, blen, idx = [], 0, idx + 1
            buf.append(ln)
            blen += len(ln) + 1
        if buf:
            fields.append((label if idx == 1 else f"{label} ({idx})", "\n".join(buf)))

    header_desc = (
        f"Prefix: **`{prefix}`** • Tổng: **{len(cmds)}** lệnh ẩn / giới hạn quyền\n"
        "🔍 Danh sách được quét tự động từ toàn bộ lệnh của bot — luôn cập nhật."
    )
    embeds: list[discord.Embed] = []
    cur: discord.Embed | None = None
    cur_len = 0
    for name, value in fields:
        if cur is None or cur_len + len(name) + len(value) > 5700 or len(cur.fields) >= 25:
            cur = make_embed(
                title="👑 DANH SÁCH LỆNH OWNER / ADMIN 👑",
                description=header_desc,
                color=discord.Color.from_rgb(255, 215, 0),
            )
            if embeds:
                cur.title = "👑 DANH SÁCH LỆNH OWNER / ADMIN 👑 (tiếp)"
            embeds.append(cur)
            cur_len = len(header_desc) + len(cur.title)
        cur.add_field(name=name, value=value, inline=False)
        cur_len += len(name) + len(value)

    for emb in embeds:
        emb.set_footer(text=f"Dùng {prefix}help <tên_lệnh> để xem chi tiết lệnh thường • Lệnh này ẩn với người chơi")
    return embeds


def _build_groups(client: commands.Bot):
    """Gom các lệnh theo nhóm, trả về dict {group_label: [commands]}."""
    groups: dict[str, list[commands.Command]] = {}
    for cog in client.cogs.values():
        cog_cmds = [c for c in cog.get_commands() if not _is_owner_command(c)]
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
                ("nhapmon", "Khởi tạo Linh Căn ngẫu nhiên & nhận 500 Linh Thạch"),
                ("profile", "Xem Thẻ PNG 18 thuộc tính nghệ thuật nhân vật"),
                ("ttinv", "Xem Túi Trữ Vật Tu Tiên (Hỗ trợ @user / ID / Đạo Hiệu)"),
                ("tutien-top", "Bảng Xếp Hạng Top Tu Vi, Gia Tài, Tháp, Boss Server"),
                ("tamcanh", "Kiểm tra tỷ lệ Đột Phá, Tâm Cảnh & Căn Cơ"),
                ("huongdan", "Xem cẩm nang hướng dẫn Tu Tiên 7 trang chi tiết"),
                ("phe-tu-vi", "Phế bỏ toàn bộ tu vi để tu luyện lại từ đầu"),
            ],
            "🧘 II. TU LUYỆN & ĐỘT PHÁ": [
                ("tuluyen", "Tu luyện chủ động tiêu 15 Tinh Lực nhận EXP Tu Vi"),
                ("nhapdinh", "Bế quan AFK tích lũy tài nguyên (1h - 24h)"),
                ("xuatquan", "Thu công xuất quan sớm & nhận quà tích lũy AFK"),
                ("nhapdinh-nhanh", "Bế quan nhanh 4h nhận ngay quà AFK (25 Tiên Ngọc)"),
                ("luyenthe", "Rèn luyện Thân Thể Tôi Thể -> Bất Diệt Thể"),
                ("dotpha", "Xung kích bình cảnh cảnh giới & nghênh đón Lôi Kiếp"),
            ],
            "⚔️ III. CHINH PHỤC HARDCORE PVE": [
                ("sanyeu", "Săn Yêu Quái (VIP 2+ dùng !san-yeu quet 10x)"),
                ("leothap", "Thử thách Tháp Thiên Cực 100 Tầng"),
                ("topthap", "Bảng Xếp Hạng Leo Tháp Top 10 Server"),
                ("bicanh", "Tổ đội 2-5 Tu Sĩ đánh Bí Cảnh Cổ Đại (-30 Tinh Lực)"),
                ("camdia", "Đột phá Mê Cung Sinh Tồn Roguelike 5 Phòng"),
                ("dietboss", "Xông vào trảm Thái Cổ Ma Vương (World Boss)"),
                ("cuuthuong", "Dùng Vạn Linh Đan cứu đạo hữu đoạn tuyệt kinh mạch"),
                ("giaidoc", "Tẩy trừ Độc Tố Thấu Cốt & Tâm Ma Ô Nhiễm"),
            ],
            "🔮 IV. GACHA & SHOP TIÊN CÁC": [
                ("quay-gacha", "Quay Gacha 3 Banner (Tụ Bảo Các, Tiên Các, Cải Mệnh)"),
                ("banner", "Xem danh sách vật phẩm & tỷ lệ rơi 3 Banner Gacha"),
                ("wishlist", "Cấu hình Wishlist định hướng 100% ra món UR mơ ước"),
                ("xienquach", "Bốc quẻ Khí Vận hàng ngày nhận vé quay & Tiên Ngọc"),
                ("linhbui-shop", "Đổi Linh Bụi lấy vật phẩm UR/SR tự chọn"),
                ("tiencac", "Xem danh mục Shop Tiên Các (Bảo hiểm, VIP, Thẻ Tháng)"),
                ("mua", "Mua vật phẩm Shop Tiên Các bằng Tiên Ngọc"),
                ("vip", "Xem Cấp VIP & Trạng thái Thẻ Tháng Đạo Tâm Tôn Giả"),
            ],
            "🥋 V. PVP TRANH PHONG & SÁT LỤC": [
                ("luandao", "Luận Đạo Đài 1v1 Ranked tính ELO & Danh Vọng"),
                ("bxh-pvp", "Bảng Xếp Hạng ELO & Danh Vọng Top 10 Server"),
                ("tang-kinh-cac", "Đổi Danh Vọng lấy Công Pháp, Thần Binh hiếm"),
                ("sinh-tu-dai", "Đặt cược Linh Thạch Quyết Chiến Sinh Tử"),
                ("cuop", "Đột nhập Động Phủ cướp Linh Thạch (+15 Nghiệp Lực)"),
                ("truy-na-ma-tu", "Treo Thưởng Lệnh Truy Nã trảm trừ Ma Đầu"),
                ("bang-truy-na", "Xem Bảng Lệnh Truy Nã Ma Đầu toàn server"),
                ("tram-ma", "Trảm Ma Đầu theo Lệnh Truy Nã nhận tiền thưởng"),
                ("mien-chien", "Kích hoạt Thất Nhật Miễn Chiến Phù (Khóa PK 7 ngày)"),
            ],
            "⚒️ VI. ĐẠO VỤ, DÙNG ĐỒ & LUYỆN KHÍ": [
                ("dao-vu", "Xem sổ Đạo Vụ Hàng Ngày (Tu Luyện, Săn Yêu, Luận Đạo)"),
                ("nhan-dao-vu", "Nhận nhanh thưởng Đạo Vụ đã xong (!nhan-dao-vu all)"),
                ("su-dung", "Dùng đan dược, phù lục từ Túi Trữ Vật (!su-dung <item>)"),
                ("dung-dan", "Dùng Cửu Chuyển Đan hồi 100% HP/Căn Cơ & xóa debuff"),
                ("luyen-dan", "Thiên Địa Đan Lò: Luyện chế Đan Dược, Phù Lục"),
                ("luyen-khi", "Thiên Công Lò: Rèn đúc Pháp Bảo, Thần Binh"),
                ("doi-cong-phap", "Trang bị / Thay đổi Công Pháp Chủ Tu từ Túi Đồ"),
                ("khai-dao", "Khai ngộ và hợp nhất Đạo Vực Vô Thượng"),
            ],
            "🏪 VII. SÀN ĐẤU GIÁ & ĐỘNG PHỦ": [
                ("cho-troi", "Xem vật phẩm đang bán trên Sàn Đấu Giá Vạn Bảo Các"),
                ("dang-ban", "Đăng bán đồ lên Sàn Đấu Giá với giá tự định"),
                ("mua-hang", "Mua vật phẩm từ Sàn Đấu Giá theo Mã Số Phiên"),
                ("huy-ban", "Hủy phiên đăng bán hoàn trả đồ về Túi Trữ Vật"),
                ("dong-phu", "Xem Động Phủ & nâng cấp Tụ Linh Trận (!dong-phu nangcap)"),
            ]
        }

        for cat_title, cmd_list in categories.items():
            cat_text = "\n".join([f"> `{prefix}{c_name}` — *{desc}*" for c_name, desc in cmd_list])
            if len(cat_text) > 1024:
                cat_text = cat_text[:1020] + "..."
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
    if len(description) > 4000:
        description = description[:3990] + "\n> *...và các lệnh khác...*"

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
        try:
            chosen = self.values[0]
            if chosen == "__home__":
                embed = _home_embed(self.groups, self.prefix)
            else:
                embed = _group_embed(chosen, self.groups.get(chosen, []), self.prefix)
            await interaction.response.edit_message(embed=embed)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi khi tải danh mục: {e}", ephemeral=True)
            except Exception:
                pass


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
            if command is None or _is_owner_command(command):
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
                    [s for s in command.commands if not _is_owner_command(s)],
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

    @commands.command(
        name="adhelp",
        hidden=True,
        aliases=["adminhelp", "ownerhelp"],
        brief="[ADMIN] Danh sách các lệnh chỉ dành cho Owner / Admin.",
        usage="adhelp",
    )
    async def adhelp(self, ctx: commands.Context):
        """[ADMIN] Danh sách các lệnh ẩn chỉ dành cho Owner / Admin (quét tự động)."""
        cfg_bot = getattr(config, "bot", None)
        owner_ids = set(getattr(cfg_bot, "owner_ids", None) or [])
        admin_ids = set(getattr(cfg_bot, "admin_ids", None) or [])
        try:
            is_app_owner = await self.client.is_owner(ctx.author)
        except Exception:
            is_app_owner = False
        is_bot_admin = ctx.author.id in owner_ids or ctx.author.id in admin_ids or is_app_owner
        is_guild_admin = bool(ctx.guild) and ctx.author.guild_permissions.administrator
        if not (is_bot_admin or is_guild_admin):
            return  # Không phản hồi gì hết, tàng hình hoàn toàn với người chơi thường

        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        embeds = _admin_help_embeds(self.client, prefix, only_discord_perms=not is_bot_admin)
        if not is_bot_admin:
            embeds[0].title = "🛡️ DANH SÁCH LỆNH QUẢN TRỊ SERVER 🛡️"
        await ctx.send(embeds=embeds)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def kill(self, ctx: commands.Context):
        await self.client.remove_cog("handlers")
        await self.client.close()


async def setup(client: commands.Bot):
    await client.add_cog(Help(client))
