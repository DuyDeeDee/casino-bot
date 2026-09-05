
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
    title_text = "🛡️ DANH SÁCH LỆNH QUẢN TRỊ SERVER 🛡️" if only_discord_perms else "👑 DANH SÁCH LỆNH OWNER / ADMIN 👑"

    for name, value in fields:
        # Giới hạn an toàn: <= 3500 ký tự và <= 10 field mỗi trang để hiển thị đẹp mắt và không vượt giới hạn Discord
        if cur is None or cur_len + len(name) + len(value) > 3500 or len(cur.fields) >= 10:
            page = len(embeds) + 1
            cur = make_embed(
                title=f"{title_text}" if page == 1 else f"{title_text} (Trang {page})",
                description=header_desc,
                color=discord.Color.from_rgb(255, 215, 0),
            )
            embeds.append(cur)
            cur_len = len(header_desc) + len(cur.title)
        cur.add_field(name=name, value=value, inline=False)
        cur_len += len(name) + len(value)

    if not embeds:
        cur = make_embed(
            title=title_text,
            description=header_desc + "\n\n_Không có lệnh nào._",
            color=discord.Color.from_rgb(255, 215, 0),
        )
        embeds.append(cur)

    total_pages = len(embeds)
    for idx, emb in enumerate(embeds, 1):
        if total_pages > 1:
            emb.title = f"{title_text} (Trang {idx}/{total_pages})"
        emb.set_footer(
            text=f"Trang {idx}/{total_pages} • Dùng {prefix}help <tên_lệnh> để xem chi tiết • Lệnh này ẩn với người chơi"
        )
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


class AdminHelpPaginationView(View):
    def __init__(self, embeds: list[discord.Embed], author_id: int):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.author_id = author_id
        self.current_page = 0
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self):
        self.first_btn.disabled = (self.current_page == 0)
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page == len(self.embeds) - 1)
        self.last_btn.disabled = (self.current_page == len(self.embeds) - 1)
        self.page_indicator.label = f"Trang {self.current_page + 1}/{len(self.embeds)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bạn không có quyền thao tác trên menu này.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="admin_help:first")
    async def first_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, custom_id="admin_help:prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Trang 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="admin_help:page")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, custom_id="admin_help:next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="admin_help:last")
    async def last_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.embeds) - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ──────────────────────────────────────────────
#  Hệ Thống Lệnh Quản Trị Server (Server Admin Help)
# ──────────────────────────────────────────────
SERVER_ADMIN_SECTIONS = {
    "channel": {
        "title": "🛡️ Quản Lý Kênh & Phân Quyền Bot",
        "short": "Kênh & Phân Quyền",
        "emoji": "🛡️",
        "desc": "Cấu hình chặn / cho phép bot hoạt động tại các kênh văn bản trong server.",
        "commands": [
            {
                "name": "camkenh <#kênh>",
                "aliases": ["setcamkenh", "blockchannel"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Bật / Tắt cấm dùng các lệnh giải trí, cờ bạc của Bot tại kênh chỉ định (lệnh Function vẫn dùng được).",
                "example": "camkenh #chat-chung",
            },
            {
                "name": "gocamkenh <#kênh>",
                "aliases": ["unblockchannel"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Gỡ cấm dùng Bot tại kênh chỉ định để bot hoạt động bình thường.",
                "example": "gocamkenh #chat-chung",
            },
            {
                "name": "setkenhchoiduoc <#kênh>",
                "aliases": ["allowchannel", "setallowedchannel"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Thêm hoặc bớt kênh vào danh sách kênh được phép chơi (dùng để điều hướng người chơi).",
                "example": "setkenhchoiduoc #casino-games",
            },
            {
                "name": "danhsachkenhcam",
                "aliases": ["listcamkenh", "blockedchannels"],
                "perm": "Thành viên / Admin",
                "desc": "Xem danh sách tất cả các kênh đang bị cấm sử dụng Bot trong server.",
                "example": "danhsachkenhcam",
            },
        ],
    },
    "jail": {
        "title": "⚖️ Nhà Tù & Kỷ Luật Thành Viên",
        "short": "Nhà Tù & Kỷ Luật",
        "emoji": "⚖️",
        "desc": "Hệ thống tống giam người chơi vi phạm, bắt buộc thực hiện lắc đít cải tạo để ra tù.",
        "commands": [
            {
                "name": "setkenhtu <#kênh>",
                "aliases": ["setjailchannel"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Thiết lập Kênh Nhà Tù của server (nơi tù nhân phải vào thực hiện lắc đít cải tạo).",
                "example": "setkenhtu #nha-tu",
            },
            {
                "name": "setvaitrotu <@Role>",
                "aliases": ["setjailrole"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Thiết lập Role Tù Nhân (tự động gán cho người bị tống giam để hạn chế quyền chat ngoài tù).",
                "example": "setvaitrotu @Tù Nhân",
            },
            {
                "name": "phattu <@user> [số_lần] [lý_do]",
                "aliases": ["jail", "tonggiam"],
                "perm": "Quản lý tin nhắn (Manage Messages)",
                "desc": "Tống giam người chơi vi phạm. Người chơi phải gõ `lacdit` đủ số lần chỉ định mới được tha bổng (mặc định: 100 lần).",
                "example": "phattu @User 200 Spam link cấm",
            },
            {
                "name": "anxatu <@user>",
                "aliases": ["unjail", "thabong"],
                "perm": "Admin / Owner Bot",
                "desc": "Tha bổng / Ân xá cho tù nhân trước thời hạn (Chỉ Admin và Owner bot mới dùng được).",
                "example": "anxatu @User",
            },
        ],
    },
    "giveaway": {
        "title": "🎉 Quản Trị Giveaway Chuyên Nghiệp",
        "short": "Giveaway Studio",
        "emoji": "🎉",
        "desc": "Hệ thống tổ chức và quản lý phát quà / Giveaways tự động chuyên sâu.",
        "commands": [
            {
                "name": "ga <thời_gian> <số_win> <quà> [flags]",
                "aliases": ["giveaway"],
                "perm": "Quản lý Server / Host",
                "desc": "Tạo giveaway với đầy đủ cờ tùy biến: `--banner <link>`, `--color <màu>`, `--thumb <host/server>`, `--role <@Role>`, `--bonus <@Role> <vé>`, `--bonus-prize <@Role> <quà_thêm>`, `--ping <role/all>`, `--desc <ghi_chú>`, `--channel <#kênh>`.",
                "example": "ga 1h 1 100k Xu --banner https://... --role @VIP --bonus-prize @Booster \"+50k\"",
            },
            {
                "name": "ga edit [id_tin_nhắn]",
                "aliases": ["sua", "chinhsua", "custom", "studio"],
                "perm": "Quản lý Server / Host",
                "desc": "Mở Bảng điều khiển tương tác (Mimu-style Studio) với nút bấm riêng tư để sửa Live Preview hoặc cấu hình Mẫu Giveaway Mặc Định.",
                "example": "ga edit",
            },
            {
                "name": "ga setbonus <id> @Role <quà_thêm>",
                "aliases": [],
                "perm": "Quản lý Server / Host",
                "desc": "Thiết lập phần thưởng thêm cho Role chỉ định nếu thành viên có role đó trúng giải.",
                "example": "ga setbonus 123456789 @Booster +1 Thẻ Tháng",
            },
            {
                "name": "ga delbonus <id> @Role",
                "aliases": [],
                "perm": "Quản lý Server / Host",
                "desc": "Xóa phần thưởng thêm của Role trong Giveaway chỉ định.",
                "example": "ga delbonus 123456789 @Booster",
            },
            {
                "name": "ga listbonus <id>",
                "aliases": [],
                "perm": "Quản lý Server / Host",
                "desc": "Xem danh sách các role nhận quà bonus thêm của giveaway.",
                "example": "ga listbonus 123456789",
            },
            {
                "name": "ga ketthuc <id>",
                "aliases": ["end", "gstop"],
                "perm": "Quản lý Server / Host",
                "desc": "Kết thúc sớm giveaway và tiến hành quay số chốt người thắng ngay lập tức.",
                "example": "ga ketthuc 123456789",
            },
            {
                "name": "ga quaylai <id> [số_lượng]",
                "aliases": ["reroll"],
                "perm": "Quản lý Server / Host",
                "desc": "Quay lại kết quả (Reroll) để chọn người chiến thắng mới.",
                "example": "ga quaylai 123456789 1",
            },
            {
                "name": "ga huy <id>",
                "aliases": ["cancel", "gdelete"],
                "perm": "Quản lý Server / Host",
                "desc": "Hủy bỏ giveaway đang chạy.",
                "example": "ga huy 123456789",
            },
            {
                "name": "ga check <id> [@user]",
                "aliases": [],
                "perm": "Quản lý Server / Host",
                "desc": "Tổng kết quà gốc + các bonus role người đó trúng được ra tin nhắn riêng (không sửa embed).",
                "example": "ga check 123456789 @Winner",
            },
        ],
    },
    "events": {
        "title": "🧩 Sự Kiện Mini-Game & Quản Lý Phòng Chơi",
        "short": "Mini-Games & Events",
        "emoji": "🧩",
        "desc": "Quản lý sự kiện Boss Server, phòng chơi Ma Sói, bài UNO và thời sự server.",
        "commands": [
            {
                "name": "giaimaboss start [jackpot]",
                "aliases": [],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Bắt đầu sự kiện Boss Server Giải Mã Mật Mã 6 số với hũ Jackpot khởi điểm (VD: `100k`, `1m`).",
                "example": "giaimaboss start 500k",
            },
            {
                "name": "giaimaboss stop",
                "aliases": [],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Dừng và hủy bỏ sự kiện Boss Server Giải Mã hiện tại.",
                "example": "giaimaboss stop",
            },
            {
                "name": "stopmasoi",
                "aliases": ["endmasoi", "cancelmasoi", "masoiend"],
                "perm": "Host / Quản trị viên",
                "desc": "Hủy / Kết thúc khẩn cấp ván Ma Sói đang diễn ra hoặc phòng chờ ở kênh hiện tại.",
                "example": "stopmasoi",
            },
            {
                "name": "uno stop",
                "aliases": ["cancel", "forceclose"],
                "perm": "Host / Quản trị viên",
                "desc": "Dừng ván bài UNO đang chơi tại kênh và hoàn trả 100% tiền cọc cho mọi người chơi.",
                "example": "uno stop",
            },
            {
                "name": "setmasoivip @user <số_ngày>",
                "aliases": ["setvipmasoi", "addmasoivip"],
                "perm": "Quản lý Server / Quản trị viên",
                "desc": "Cấp quyền VIP Ma Sói cho thành viên (thêm lời trăn trối, hiệu ứng danh vọng).",
                "example": "setmasoivip @User 30",
            },
            {
                "name": "removemasoivip @user",
                "aliases": ["delmasoivip", "huyvipmasoi"],
                "perm": "Quản lý Server / Quản trị viên",
                "desc": "Hủy gói VIP Ma Sói của thành viên.",
                "example": "removemasoivip @User",
            },
            {
                "name": "setmasoibadge @user <emoji/id>",
                "aliases": ["setbadge", "sethuyhieu"],
                "perm": "Quản lý Server / Quản trị viên",
                "desc": "Cài đặt huy hiệu / icon hiển thị đặc biệt cạnh tên người chơi trong game Ma Sói.",
                "example": "setmasoibadge @User 🔥",
            },
            {
                "name": "removemasoibadge @user",
                "aliases": ["delbadge", "huyhuyhieu"],
                "perm": "Quản lý Server / Quản trị viên",
                "desc": "Xóa huy hiệu tự chọn trong Ma Sói của người chơi.",
                "example": "removemasoibadge @User",
            },
            {
                "name": "masoiviplist",
                "aliases": ["listvipmasoi"],
                "perm": "Quản lý Server / Quản trị viên",
                "desc": "Xem danh sách tất cả các tài khoản VIP Ma Sói đang hoạt động.",
                "example": "masoiviplist",
            },
            {
                "name": "event",
                "aliases": [],
                "perm": "Admin / Owner",
                "desc": "Xem trạng thái các sự kiện server thời vụ (Giờ Vàng x2 lương/đào quặng, Bão Tuyết, Flash Sale, Boss Cướp Phố).",
                "example": "event",
            },
        ],
    },
    "economy": {
        "title": "💍 Quản Trị Hôn Nhân & Giới Hạn Kinh Tế",
        "short": "Hôn Nhân & Kinh Tế",
        "emoji": "💍",
        "desc": "Quản trị quan hệ hôn nhân và thiết lập giới hạn sở hữu đầu tư cho server.",
        "commands": [
            {
                "name": "admindel_marry <@user/ID>",
                "aliases": ["admin_divorce", "xoahonnhan"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Buộc ly hôn / Xóa hôn nhân của một người dùng bất kỳ trong server mà không mất phí.",
                "example": "admindel_marry @User",
            },
            {
                "name": "invest max <mã> <số_lượng>",
                "aliases": [],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Đặt giới hạn sở hữu cổ phiếu / coin tối đa của từng mã (`BTC`, `ETH`, `USDT`, `AGV`, `SOL`, `DOGE`, `CASINO`) hoặc `reset` để mở vô hạn.",
                "example": "invest max BTC 50",
            },
            {
                "name": "setlevel <@user/ID> <cấp 0-50> [xp]",
                "aliases": ["setcap", "setcapdo", "setmemberlevel", "setchatlevel"],
                "perm": "Quản trị viên (Administrator)",
                "desc": "Cài đặt cấp độ chat (0-50) và hạn mức cho/nhận tiền, vàng của một thành viên trong server.",
                "example": "setlevel @Member 20",
            },
            {
                "name": "invest max",
                "aliases": [],
                "perm": "Quản trị viên / Mọi người",
                "desc": "Xem danh sách các giới hạn sở hữu tối đa hiện tại của từng mã đầu tư.",
                "example": "invest max",
            },
        ],
    },
}


def _can_use_server_help(ctx: commands.Context) -> bool:
    """Kiểm tra quyền sử dụng lệnh shelp (Quản trị viên, Quản lý Server, Quản lý Tin nhắn hoặc Bot Owner)."""
    if not ctx.guild:
        return True
    cfg_bot = getattr(config, "bot", None)
    owner_ids = set(getattr(cfg_bot, "owner_ids", None) or [])
    admin_ids = set(getattr(cfg_bot, "admin_ids", None) or [])
    if ctx.author.id in owner_ids or ctx.author.id in admin_ids:
        return True
    perms = ctx.author.guild_permissions
    return perms.administrator or perms.manage_guild or perms.manage_messages or perms.manage_channels


def _server_admin_home_embed(prefix: str) -> discord.Embed:
    """Tạo Embed Trang Chủ cho Lệnh Help Quản Trị Server."""
    total_cmds = sum(len(sec["commands"]) for sec in SERVER_ADMIN_SECTIONS.values())
    embed = make_embed(
        title="🛡️ TRUNG TÂM LỆNH QUẢN TRỊ SERVER (SERVER ADMIN HELP) 🛡️",
        description=(
            f"Prefix của bot: **`{prefix}`** • Tổng cộng: **{total_cmds} lệnh quản trị server**\n\n"
            "Chào mừng Quản trị viên! Đây là bảng điều khiển lệnh quản trị độc quyền giúp bạn cấu hình kênh, kỷ luật nhà tù, tổ chức giveaway, quản lý mini-game và kinh tế server.\n\n"
            "👉 **Cách xem lệnh:** Sử dụng **Menu chọn bên dưới** hoặc bấm các **Nút chức năng** để duyệt từng danh mục.\n"
            f"👉 **Tra cứu nhanh:** Gõ `{prefix}shelp <tên_lệnh>` (Ví dụ: `{prefix}shelp ga`, `{prefix}shelp phattu`)."
        ),
        color=discord.Color.gold(),
    )

    for key, sec in SERVER_ADMIN_SECTIONS.items():
        cmd_names = [f"`{prefix}{c['name'].split()[0]}`" for c in sec["commands"]]
        sample_text = " • ".join(cmd_names[:4])
        if len(cmd_names) > 4:
            sample_text += f" *(+{len(cmd_names) - 4} lệnh khác)*"
        embed.add_field(
            name=f"{sec['title']} ({len(sec['commands'])} lệnh)",
            value=f"{sec['desc']}\n> 📌 Lệnh tiêu biểu: {sample_text}",
            inline=False,
        )

    embed.set_footer(text=f"Dành riêng cho Quản trị viên Server • Prefix: {prefix}")
    return embed


def _server_admin_section_embed(section_key: str, prefix: str) -> discord.Embed:
    """Tạo Embed hiển thị chi tiết các lệnh trong 1 danh mục quản trị."""
    sec = SERVER_ADMIN_SECTIONS.get(section_key)
    if not sec:
        return _server_admin_home_embed(prefix)

    embed = make_embed(
        title=f"{sec['title']}",
        description=(
            f"{sec['desc']}\n"
            f"Prefix: **`{prefix}`** • Tổng: **{len(sec['commands'])}** lệnh trong danh mục này\n"
            "────────────────────────────────────────────"
        ),
        color=discord.Color.gold(),
    )

    for cmd in sec["commands"]:
        aliases_str = f" `({', '.join(cmd['aliases'])})`" if cmd["aliases"] else ""
        embed.add_field(
            name=f"> `{prefix}{cmd['name']}`{aliases_str}",
            value=(
                f"🔑 *Yêu cầu:* **{cmd['perm']}**\n"
                f"📝 *Chi tiết:* {cmd['desc']}\n"
                f"💡 *Ví dụ:* `{prefix}{cmd['example']}`"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Dùng {prefix}shelp <tên_lệnh> để xem chi tiết • Trang quản trị Server")
    return embed


def _find_server_admin_command(query: str) -> tuple[dict, str] | None:
    """Tìm kiếm lệnh quản trị server theo tên hoặc alias."""
    clean_q = query.strip().lower()
    for p in ["i?", "!", "$", "?", "/"]:
        if clean_q.startswith(p):
            clean_q = clean_q[len(p):].strip()
            break

    for sec_key, sec in SERVER_ADMIN_SECTIONS.items():
        for cmd in sec["commands"]:
            cmd_root = cmd["name"].split()[0].lower()
            if clean_q == cmd_root:
                return cmd, sec["title"]
            if any(clean_q == a.lower() for a in cmd["aliases"]):
                return cmd, sec["title"]
            full_name = cmd["name"].split("<")[0].split("[")[0].strip().lower()
            if clean_q == full_name or clean_q == full_name.replace(" ", ""):
                return cmd, sec["title"]
    return None


def _server_admin_detail_embed(cmd_data: dict, section_title: str, prefix: str) -> discord.Embed:
    """Tạo Embed tra cứu chi tiết 1 lệnh quản trị."""
    embed = make_embed(
        title=f"🔍 Chi Tiết Lệnh Quản Trị: `{prefix}{cmd_data['name'].split()[0]}`",
        description=f"Danh mục: **{section_title}**\n──────────────────────────────",
        color=discord.Color.gold(),
    )
    embed.add_field(name="📌 Cú pháp sử dụng", value=f"`{prefix}{cmd_data['name']}`", inline=False)
    embed.add_field(name="🔑 Quyền hạn yêu cầu", value=f"**{cmd_data['perm']}**", inline=False)

    aliases_str = "  ".join(f"`{prefix}{a}`" for a in cmd_data["aliases"]) if cmd_data["aliases"] else "Không có"
    embed.add_field(name="🔀 Bí danh (Aliases)", value=aliases_str, inline=False)
    embed.add_field(name="📝 Mô tả chức năng", value=cmd_data["desc"], inline=False)
    embed.add_field(name="💡 Ví dụ mẫu", value=f"`{prefix}{cmd_data['example']}`", inline=False)
    embed.set_footer(text=f"Dùng {prefix}shelp để xem toàn bộ danh mục quản trị")
    return embed


class ServerAdminCategorySelect(Select):
    def __init__(self, prefix: str):
        self.prefix = prefix
        options = [
            discord.SelectOption(
                label="Trang Chủ Quản Trị",
                value="__home__",
                emoji="🏠",
                description="Bảng tổng quan trung tâm quản trị server",
            )
        ]
        for key, sec in SERVER_ADMIN_SECTIONS.items():
            options.append(
                discord.SelectOption(
                    label=sec["short"],
                    value=key,
                    emoji=sec["emoji"],
                    description=f"{len(sec['commands'])} lệnh • {sec['title'][:35]}",
                )
            )

        super().__init__(
            placeholder="🛡️ Chọn danh mục quản trị cần xem…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            chosen = self.values[0]
            if chosen == "__home__":
                embed = _server_admin_home_embed(self.prefix)
            else:
                embed = _server_admin_section_embed(chosen, self.prefix)
            await interaction.response.edit_message(embed=embed)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi khi tải danh mục: {e}", ephemeral=True)
            except Exception:
                pass


class ServerAdminHelpView(View):
    def __init__(self, prefix: str, author_id: int):
        super().__init__(timeout=180)
        self.prefix = prefix
        self.author_id = author_id
        self.message: discord.Message | None = None
        self.add_item(ServerAdminCategorySelect(prefix))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Menu này chỉ dành cho người vừa gọi lệnh.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Trang Chủ", emoji="🏠", style=discord.ButtonStyle.secondary, row=1)
    async def btn_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_home_embed(self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Kênh & Quyền", emoji="🛡️", style=discord.ButtonStyle.primary, row=1)
    async def btn_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_section_embed("channel", self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Nhà Tù", emoji="⚖️", style=discord.ButtonStyle.primary, row=1)
    async def btn_jail(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_section_embed("jail", self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Giveaway", emoji="🎉", style=discord.ButtonStyle.primary, row=1)
    async def btn_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_section_embed("giveaway", self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Mini-Game", emoji="🧩", style=discord.ButtonStyle.success, row=2)
    async def btn_events(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_section_embed("events", self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hôn Nhân & Kinh Tế", emoji="💍", style=discord.ButtonStyle.success, row=2)
    async def btn_economy(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _server_admin_section_embed("economy", self.prefix)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


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
        name="shelp",
        aliases=["serverhelp", "adminhelp", "serveradmin", "sadmin", "guildhelp", "modhelp", "hdadmin"],
        brief="[ADMIN] Trung tâm hướng dẫn lệnh quản trị server dành riêng cho Admin.",
        usage="shelp [tên_lệnh]",
    )
    async def shelp(self, ctx: commands.Context, request: str | None = None):
        """Lệnh help chuyên biệt dành riêng cho Quản trị viên Server."""
        if not _can_use_server_help(ctx):
            await ctx.send(
                "❌ **Bạn không có quyền sử dụng lệnh này!** Lệnh `shelp` dành riêng cho Quản trị viên / Quản lý Server.",
                delete_after=10,
            )
            return

        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        # ── Tra cứu 1 lệnh cụ thể ──
        if request:
            found = _find_server_admin_command(request)
            if found:
                cmd_data, sec_title = found
                embed = _server_admin_detail_embed(cmd_data, sec_title, prefix)
                await ctx.send(embed=embed)
                return

            # Nếu không tìm thấy trong danh mục server admin, thử tìm lệnh bot chung
            bot_cmd = self.client.get_command(request)
            if bot_cmd and not _is_owner_command(bot_cmd):
                await ctx.invoke(self.client.get_command("help"), request=request)
                return

            await ctx.send(
                f"❌ Không tìm thấy lệnh quản trị nào có tên hoặc bí danh là `{request}`. Dùng `{prefix}shelp` để xem danh sách.",
                delete_after=10,
            )
            return

        # ── Trang chủ Server Admin Help Dashboard ──
        embed = _server_admin_home_embed(prefix)
        view = ServerAdminHelpView(prefix=prefix, author_id=ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(
        name="adhelp",
        hidden=True,
        aliases=["ownerhelp", "devhelp"],
        brief="[ADMIN] Danh sách các lệnh chỉ dành cho Owner / Admin Bot.",
        usage="adhelp",
    )
    async def adhelp(self, ctx: commands.Context):
        """[ADMIN] Danh sách các lệnh ẩn chỉ dành cho Owner / Admin Bot (quét tự động)."""
        cfg_bot = getattr(config, "bot", None)
        owner_ids = set(getattr(cfg_bot, "owner_ids", None) or [])
        admin_ids = set(getattr(cfg_bot, "admin_ids", None) or [])
        try:
            is_app_owner = await self.client.is_owner(ctx.author)
        except Exception:
            is_app_owner = False
        is_bot_admin = ctx.author.id in owner_ids or ctx.author.id in admin_ids or is_app_owner
        is_guild_admin = bool(ctx.guild) and (
            ctx.author.guild_permissions.administrator
            or ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.manage_messages
        )

        if not (is_bot_admin or is_guild_admin):
            return  # Không phản hồi gì hết, tàng hình hoàn toàn với người chơi thường

        # Nếu là Quản trị viên Server (nhưng không phải Bot Owner) -> Điều hướng trực tiếp sang shelp chuyên nghiệp
        if is_guild_admin and not is_bot_admin:
            await ctx.invoke(self.client.get_command("shelp"))
            return

        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        embeds = _admin_help_embeds(self.client, prefix, only_discord_perms=not is_bot_admin)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            view = AdminHelpPaginationView(embeds, author_id=ctx.author.id)
            view.message = await ctx.send(embed=embeds[0], view=view)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def kill(self, ctx: commands.Context):
        await self.client.remove_cog("handlers")
        await self.client.close()


async def setup(client: commands.Bot):
    await client.add_cog(Help(client))

