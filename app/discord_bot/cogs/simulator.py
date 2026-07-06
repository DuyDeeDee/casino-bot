import asyncio
import logging
import random
import time
from pathlib import Path
from uuid import uuid4
import discord
from discord.ext import commands, tasks

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.profile_renderer import render_profile_banner, render_showcase_image
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.cogs.xe import get_car_image_file
from app.discord_bot.cogs.daga import get_cock_image_file, RARITY_DISPLAY

logger = logging.getLogger(__name__)


LIQUIDITY_VOLUME = {
    "USDT": 1_000_000.0,
    "AGV": 50_000.0,
    "CASINO": 10_000.0,
    "ETH": 2_000.0,
    "BTC": 500.0,
    "SOL": 5_000.0,
    "DOGE": 500_000.0
}

DEFAULT_PRICES = {
    "USDT": 25_000,
    "AGV": 10_000,
    "CASINO": 100_000,
    "ETH": 500_000,
    "BTC": 1_000_000,
    "SOL": 80_000,
    "DOGE": 5_000
}

def get_limit_buy_cost(shares: float, target_price: int, symbol: str) -> int:
    liquidity = LIQUIDITY_VOLUME.get(symbol.upper(), 10000.0)
    slippage_pct = (shares / liquidity) * 0.01
    effective_target = int(target_price * (1 + slippage_pct))
    base_cost = int(shares * effective_target)
    fee = int(base_cost * 0.02)
    return base_cost + fee


def remove_vietnamese_accents(s: str) -> str:
    s = s.lower()
    replacements = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'đ': 'd',
        'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
    }
    for char, replacement in replacements.items():
        s = s.replace(char, replacement)
    return s


def get_custom_emoji_or_default(bot, title_text: str) -> str:
    if not title_text:
        return ""
    
    # Strip emojis to get clean name
    from app.discord_bot.modules.profile_renderer import strip_emoji
    clean_name = strip_emoji(title_text)
    if not clean_name:
        return title_text
        
    # Normalize to lowercase and remove accents/spaces
    no_accents = remove_vietnamese_accents(clean_name)
    normalized = "".join(c for c in no_accents if c.isalnum() or c == ' ').strip().lower().replace(" ", "_")
    normalized_no_underscore = normalized.replace("_", "")
    
    for emoji in bot.emojis:
        name_lower = emoji.name.lower()
        if name_lower in (normalized, normalized_no_underscore):
            return f"{emoji} {clean_name}"
            
    return title_text


def get_custom_emojis_for_user(bot, titles: list[str]) -> list[str]:
    custom_emojis = []
    from app.discord_bot.modules.profile_renderer import strip_emoji
    
    for title in titles:
        if not title:
            continue
        clean_name = strip_emoji(title)
        if not clean_name:
            continue
            
        no_accents = remove_vietnamese_accents(clean_name)
        normalized = "".join(c for c in no_accents if c.isalnum() or c == ' ').strip().lower().replace(" ", "_")
        normalized_no_underscore = normalized.replace("_", "")
        
        for emoji in bot.emojis:
            name_lower = emoji.name.lower()
            if name_lower in (normalized, normalized_no_underscore):
                custom_emojis.append(str(emoji))
                break
                
    return custom_emojis

# Business configs
BUSINESSES = {
    "iot": {
        "name": "Nhà Máy",
        "base_cost": 50_000_000,
        "base_revenue": 500_000, # per hour
        "currency": "money"
    },
    "gym": {
        "name": "Phòng Gym Thể hình 🏋️",
        "base_cost": 100_000_000,
        "base_revenue": 1_200_000, # per hour
        "currency": "money",
        "buff": "Sinh ra 1.2M VND/giờ + Tặng giáp sức khỏe tinh thần chống nản."
    },
    "gold_shop": {
        "name": "Chuỗi Tiệm Vàng <:32100goldbarsfortnite:1514192020921651251>",
        "base_cost": 10, # 10 Gold (credits)
        "base_revenue": 0.1 / 24, # 0.1 Gold per day (approx 0.00416 Gold per hour)
        "currency": "gold"
    }
}

# Shop items config
SHOP_ITEMS = {
    "bang_cap": {
        "name": "Bằng cấp công nghệ 🎓",
        "cost": 5,
        "currency": "gold",
        "description": "Mở khóa công việc Công nghệ trong lệnh $work để nhận dự án lớn."
    },
    "bang_kien_truc": {
        "name": "Bằng Kiến Trúc Sư 📐",
        "cost": 10,
        "currency": "gold",
        "description": "Mở khóa các dự án thiết kế công trình trong lệnh $work để nhận từ 1,800,000 VND đến 3,000,000 VND mỗi giờ."
    },
    "bang_phi_hanh": {
        "name": "Chứng Chỉ Phi Hành Gia 🚀",
        "cost": 15,
        "currency": "gold",
        "description": "Mở khóa nhiệm vụ thám hiểm vũ trụ trong lệnh $work để nhận từ 4,500,000 VND đến 8,000,000 VND mỗi giờ."
    },
    "bang_bac_si": {
        "name": "Bằng Bác Sĩ Chuyên Khoa 🩺",
        "cost": 35,
        "currency": "gold",
        "description": "Mở khóa công việc chăm sóc sức khỏe VIP trong lệnh $work để nhận từ 10,000,000 VND đến 20,000,000 VND mỗi giờ."
    },
    "the_tho_mo": {
        "name": "Nghề Khai Thác Vàng ⛏️",
        "cost": 30,
        "currency": "gold",
        "description": "Mở khóa lệnh $mine khai thác vàng tự động. Càng sở hữu nhiều vàng, tỷ lệ đào trúng càng khó."
    },
    "the_tho_san": {
        "name": "Chứng Chỉ Thợ Săn Kho Báu 🗺️",
        "cost": 500,
        "currency": "gold",
        "description": "Mở khóa thám hiểm hầm mộ cổ đại trong lệnh $work để tìm kiếm các kho báu giá trị (có thể sưu tầm hoặc bán bằng lệnh i?sellitem)."
    },
    "banner_aesthetic": {
        "name": "Banner Aesthetic Động ✨",
        "cost": 150,
        "currency": "gold",
        "description": "Hình nền động phong cách lofi hoàng hôn cực chất.",
        "is_banner": True,
        "filename": "aesthetic-banner.gif"
    },
    "banner_cyberpunk": {
        "name": "Banner Cyberpunk Neon 🌆",
        "cost": 600,
        "currency": "gold",
        "description": "Hình nền tĩnh thành phố tương lai neon lung linh.",
        "is_banner": True,
        "filename": "cyberpunk.png"
    },
    "banner_royal": {
        "name": "Banner Casino Hoàng Gia 👑",
        "cost": 1200,
        "currency": "gold",
        "description": "Hình nền tĩnh casino hoàng gia sang xịn mịn.",
        "is_banner": True,
        "filename": "royal.png"
    },
    "banner_lelouch": {
        "name": "Banner Lelouch Động 👁️",
        "cost": 200,
        "currency": "gold",
        "description": "Hình nền động Lelouch Geass cực kỳ ngầu.",
        "is_banner": True,
        "filename": "lelouch.gif"
    },
    "banner_anak": {
        "name": "Banner Anak Động 🌌",
        "cost": 250,
        "currency": "gold",
        "description": "Hình nền động Anak siêu ngầu.",
        "is_banner": True,
        "is_admin_only": True,
        "filename": "anak.gif"
    },
    "banner_hr": {
        "name": "Banner HR Động 💫",
        "cost": 250,
        "currency": "gold",
        "description": "Hình nền động HR cực đẹp.",
        "is_banner": True,
        "is_admin_only": True,
        "filename": "hr.gif"
    },
    "banner_hr2": {
        "name": "Banner HR 2 Động 💫",
        "cost": 250,
        "currency": "gold",
        "description": "Hình nền động HR 2 cực đẹp.",
        "is_banner": True,
        "is_admin_only": True,
        "filename": "hr2.gif"
    },
    "banner_sally": {
        "name": "Banner Sally Động 🍭",
        "cost": 250,
        "currency": "gold",
        "description": "Hình nền động Sally siêu dễ thương.",
        "is_banner": True,
        "is_admin_only": True,
        "filename": "sally.gif"
    },
    "banner_zee": {
        "name": "Banner Zee Đẹp Trai 😎",
        "cost": 250,
        "currency": "gold",
        "description": "Hình nền Zee tĩnh cực chất.",
        "is_banner": True,
        "is_admin_only": True,
        "filename": "zee.jpg"
    },
    "manager_contract": {
        "name": "Hợp đồng Quản lý 7 ngày 💼",
        "cost": 7,
        "currency": "gold",
        "description": "Sử dụng lệnh `i?use manager_contract` để thuê Quản lý tự thu hoạch doanh nghiệp mỗi 12h."
    },
    "insurance_contract": {
        "name": "Bảo hiểm Doanh nghiệp 7 ngày 🛡️",
        "cost": 7,
        "currency": "gold",
        "description": "Sử dụng lệnh `i?use insurance_contract` để phòng ngừa 100% rủi ro/gặp sự cố doanh nghiệp."
    },
    "bodyguard_contract": {
        "name": "Hợp đồng Vệ sĩ 7 ngày 💂",
        "cost": 10,
        "currency": "gold",
        "description": "Sử dụng lệnh `i?use bodyguard_contract` để thuê Vệ sĩ bảo vệ tài sản, giảm 80% tỷ lệ bị cướp."
    },
    "security_system": {
        "name": "Hệ thống Camera & Báo động 🚨",
        "cost": 50,
        "currency": "gold",
        "description": "Thiết bị bảo vệ doanh nghiệp vĩnh viễn. 30% cơ hội bắt giữ kẻ cướp, phạt tiền bồi thường cho bạn."
    },
    "ring_grass": {
        "name": "<:NhnC:1522871683495624764>Nhẫn Cỏ",
        "cost": 100000,
        "currency": "money",
        "description": "Nghèo thì mua cái này thôi."
    },
    "ring_quartz": {
        "name": "<:NhanThachAnhTrang:1521733831932121159>Nhẫn Thạch Anh Trắng",
        "cost": 2,
        "currency": "gold",
        "description": "Nhẫn bạc đơn giản đính thạch anh tinh khiết. Buff: +2% điểm thân mật."
    },
    "ring_aquamarine": {
        "name": "<:NhnSngMaiAquamarine:1521739939849441461>Nhẫn Sương Mai Aquamarine",
        "cost": 10,
        "currency": "gold",
        "description": "Dây xoắn mảnh đính Aquamarine lam nhạt. Buff: +3% điểm thân mật."
    },
    "ring_emerald": {
        "name": "<:NhnThanhXunLcBo:1521739876838543410>Nhẫn Thanh Xuân Lục Bảo",
        "cost": 15,
        "currency": "gold",
        "description": "Hình lá cây Peridot xanh tươi trẻ. Buff: +4% điểm thân mật, +2% lương làm việc."
    },
    "ring_amethyst": {
        "name": "<:NhnTrngKhuytAmethyst:1521739893947105361>Nhẫn Trăng Khuyết Amethyst",
        "cost": 20,
        "currency": "gold",
        "description": "Trăng khuyết ôm lấy thạch anh tím huyền bí. Buff: +5% điểm thân mật, +3% lương làm việc."
    },
    "ring_cupid": {
        "name": "<:NhnTnhYuCupid:1521739979691135027>Nhẫn Tình Yêu Cupid",
        "cost": 50,
        "currency": "gold",
        "description": "Vàng hồng đính thạch anh hồng Cupid ngọt ngào. Buff: +7% điểm thân mật, +5% lương làm việc."
    },
    "ring_citrine": {
        "name": "<:NhnVngMinCitrine:1521740000100876308>Nhẫn Vương Miện Citrine",
        "cost": 75,
        "currency": "gold",
        "description": "Vương miện vàng đính Citrine vàng rực rỡ. Buff: +9% điểm thân mật, +7% lương làm việc."
    },
    "ring_ruby": {
        "name": "<:NhnHngNgcBchHp:1521740055293591702>Nhẫn Hồng Ngọc Bách Hợp",
        "cost": 100,
        "currency": "gold",
        "description": "Ruby đỏ uốn lượn như cánh hoa hồng. Buff: +12% điểm thân mật, +10% lương, giảm 5% phí ly hôn."
    },
    "ring_sapphire": {
        "name": "<:NhnLamNgcTinhT:1521740040730968114>Nhẫn Lam Ngọc Tinh Tú",
        "cost": 150,
        "currency": "gold",
        "description": "Lam ngọc xanh đính kim cương nhỏ lấp lánh. Buff: +15% điểm thân mật, +12% lương, giảm 10% phí ly hôn."
    },
    "ring_sunburst": {
        "name": "<:NhnNhtQuangThiDng:1521740029473591306>Nhẫn Nhật Quang Thái Dương",
        "cost": 200,
        "currency": "gold",
        "description": "Hào quang mặt trời đính Opal lửa cam rực cháy. Buff: +20% điểm thân mật, +15% lương, +2% đào mỏ."
    },
    "ring_gothic": {
        "name": "<:NhnHcD:1521740067415134258>Nhẫn Hắc Dạ Gothic",
        "cost": 300,
        "currency": "gold",
        "description": "Vành kim loại đen đính đá Obsidian ma mị. Buff: +25% điểm thân mật, +20% lương, giảm 20% bị cướp."
    },
    "ring_angel": {
        "name": "<:NhnCnhThnSapphire:1521740094283841576>Nhẫn Cánh Thần Sapphire",
        "cost": 600,
        "currency": "gold",
        "description": "Cánh thiên thần bạc ôm Sapphire hoàng gia. Buff: +30% điểm thân mật, +25% lương, giảm 40% bị cướp."
    },
    "ring_divine": {
        "name": "<:NhnHoQuangVnhCu:1521740081935814797>Nhẫn Hào Quang Vĩnh Cửu",
        "cost": 2000,
        "currency": "gold",
        "description": "Cực phẩm cánh thiên thần vàng đính đá ngũ sắc. Buff: +50% thân mật, +40% lương, miễn nhiễm cướp vĩnh viễn, hoàn trả 3% cược Casino, pháo hoa toàn server."
    }
}

TREASURES = {
    # ── Rác thải (Trash) ──────────────────────────────────────────────────────────
    "t_lop_xe": {"name": "Lốp xe cũ hỏng 🛞", "value": 50_000, "rarity": "Rác thải"},
    "t_lon_bia": {"name": "Lon bia rỉ sét 🥫", "value": 100_000, "rarity": "Rác thải"},
    "t_giay_cu": {"name": "Chiếc giày cũ rách mất đế 🥾", "value": 70_000, "rarity": "Rác thải"},
    "t_mo_blet": {"name": "Mỏ lết rỉ sét gãy cán 🔧", "value": 120_000, "rarity": "Rác thải"},
    
    # ── Thường (Common) ────────────────────────────────────────────────────────────
    "t_dong_xu_co": {"name": "Đồng xu cổ thời Đinh 🪙", "value": 2_500_000, "rarity": "Thường"},
    "t_bat_gom": {"name": "Bát gốm Chu Đậu cổ 🏺", "value": 8_000_000, "rarity": "Thường"},
    "t_tranh_dong_ho": {"name": "Bức tranh Đông Hồ cổ 🖼️", "value": 4_000_000, "rarity": "Thường"},
    "t_tram_dong": {"name": "Trâm cài tóc bằng đồng thời Lý 🗡️", "value": 6_500_000, "rarity": "Thường"},
    
    # ── Hiếm (Rare) ────────────────────────────────────────────────────────────────
    "t_kiem_ri": {"name": "Thanh kiếm rỉ sét của nghĩa quân 🗡️", "value": 20_000_000, "rarity": "Hiếm"},
    "t_trong_dong": {"name": "Mảnh Trống đồng Đông Sơn 🥁", "value": 30_000_000, "rarity": "Hiếm"},
    "t_sach_da_thuoc": {"name": "Cuộn sách thư pháp bằng da thuộc 📜", "value": 15_000_000, "rarity": "Hiếm"},
    "t_hoa_tai_co": {"name": "Đôi hoa tai bạc chạm khắc cổ xưa 💍", "value": 25_000_000, "rarity": "Hiếm"},
    
    # ── Quý hiếm (Epic) ────────────────────────────────────────────────────────────
    "t_mat_na_vang": {"name": "Mặt nạ vàng bộ tộc Inca 🎭", "value": 60_000_000, "rarity": "Quý hiếm"},
    "t_ngoc_ti": {"name": "Ngọc tỷ triều đình phong kiến 玺", "value": 80_000_000, "rarity": "Quý hiếm"},
    "t_la_chan_sparta": {"name": "Lá chắn đồng của chiến binh Sparta 🛡️", "value": 110_000_000, "rarity": "Quý hiếm"},
    "t_nanh_ho_phach": {"name": "Nanh hổ phách hóa thạch nghìn năm 🦷", "value": 140_000_000, "rarity": "Quý hiếm"},
    
    # ── Huyền thoại (Legendary) ────────────────────────────────────────────────────
    "t_vuong_mien": {"name": "Vương miện đính ngọc Hoàng đế La Mã 👑", "value": 250_000_000, "rarity": "Huyền thoại"},
    "t_riu_ma_bac": {"name": "Rìu chiến Viking mạ bạc 🪓", "value": 350_000_000, "rarity": "Huyền thoại"},
    "t_kim_cuong_hope": {"name": "Viên kim cương xanh Hope huyền thoại 💎", "value": 500_000_000, "rarity": "Huyền thoại"},
    "t_la_thu_einstein": {"name": "Bức thư tay gốc của Einstein 📝", "value": 400_000_000, "rarity": "Huyền thoại"},
    
    # ── Thần thoại (Mythical) ──────────────────────────────────────────────────────
    "t_chen_thanh": {"name": "Chén Thánh truyền thuyết 🏆", "value": 1_000_000_000, "rarity": "Thần thoại"},
    "t_long_phuong_hoang": {"name": "Lông vũ rực cháy của Phượng Hoàng 🔥", "value": 1_300_000_000, "rarity": "Thần thoại"},
    "t_hop_pandora": {"name": "Chiếc hộp Pandora bí ẩn 🎁", "value": 1_800_000_000, "rarity": "Thần thoại"}
}

class ChestSelect(discord.ui.Select):
    def __init__(self, current_value: str):
        options = [
            discord.SelectOption(label="Banner Thường - 1M", value="banner_thuong", description="Triệu hồi nhân vật C -> SS", emoji="🔮"),
            discord.SelectOption(label="Banner Xịn - 5M", value="banner_xin", description="Triệu hồi nhân vật B -> SS (Bảo hiểm 50)", emoji="🔮"),
            
            discord.SelectOption(label="Garage Box Xe - 100k", value="box_garage", description="Mở xe Common -> Epic", emoji="🏎️"),
            discord.SelectOption(label="Premium Box Xe - 1M", value="box_premium", description="Mở xe Rare -> Mythic", emoji="🏎️"),
            discord.SelectOption(label="Luxury Box Xe - 10M", value="box_luxury", description="Mở xe Epic -> Exclusive", emoji="🏎️"),
        ]
        super().__init__(placeholder="Chọn loại Trứng / Rương cần mở...", min_values=1, max_values=1, options=options)
        for opt in self.options:
            opt.default = (opt.value == current_value)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_option = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == self.view.selected_option)
        embed = self.view.get_embed()
        await interaction.response.edit_message(embed=embed, view=self.view)


class OpenButton(discord.ui.Button):
    def __init__(self, label: str, quantity: int, style: discord.ButtonStyle, emoji: str):
        super().__init__(label=label, style=style, emoji=emoji)
        self.quantity = quantity

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.view.cog.process_chest_open(interaction, self.view, self.view.selected_option, self.quantity)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error in process_chest_open callback")
            try:
                await interaction.response.send_message(f"❌ **Lỗi:** `{str(e)}`", ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send(f"❌ **Lỗi:** `{str(e)}`", ephemeral=True)
                except Exception:
                    pass


class ChestOpenView(discord.ui.View):
    def __init__(self, cog, author: discord.User | discord.Member, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author = author
        self.selected_option = "banner_thuong"
        self.message = None
        self.add_item(ChestSelect(self.selected_option))
        self.add_item(OpenButton(label="Mở 1", quantity=1, style=discord.ButtonStyle.success, emoji="1️⃣"))
        self.add_item(OpenButton(label="Mở 3", quantity=3, style=discord.ButtonStyle.primary, emoji="3️⃣"))
        self.add_item(OpenButton(label="Mở 10", quantity=10, style=discord.ButtonStyle.danger, emoji="🔟"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Bảng điều khiển này không phải của bạn!", ephemeral=True)
            return False
            
        if not self.cog.economy.has_claimed_start(interaction.user.id):
            await interaction.response.send_message("❌ Bạn chưa nhận quà khởi nghiệp! Hãy gõ `i?khoinghiep` trước.", ephemeral=True)
            return False
            
        return True

    def get_embed(self) -> discord.Embed:
        details = {
            "banner_thuong": ("🔮 Banner Thường", 1_000_000, "Triệu hồi nhân vật. Tỷ lệ: C (60%), B (30%), A (9%), S (0.8%), SS (0.2%)."),
            "banner_xin": ("🔮 Banner Xịn", 5_000_000, "Triệu hồi nhân vật. Tỷ lệ: B (40%), A (45%), S (12%), SS (3%). Có bảo hiểm (pity) 50 lần."),

            "box_garage": ("🏎️ Garage Box Xe", 100_000, "Mở xe / siêu xe. Tỷ lệ: Common (70%), Rare (25%), Epic (5%)."),
            "box_premium": ("🏎️ Premium Box Xe", 1_000_000, "Mở xe / siêu xe. Tỷ lệ: Rare (50%), Epic (35%), Legendary (13%), Mythic (2%)."),
            "box_luxury": ("🏎️ Luxury Box Xe", 10_000_000, "Mở xe / siêu xe. Tỷ lệ: Epic (40%), Legendary (35%), Mythic (20%), Exclusive (5%)."),
        }
        name, price, desc = details[self.selected_option]
        
        embed = make_embed(
            title="🎁 CỬA HÀNG MỞ RƯƠNG NHANH 🎁",
            description=(
                f"### **{name}**\n"
                f"💵 **Giá mở 1 lần:** `{price:,} VND`\n"
                f"💵 **Giá mở 3 lần:** `{(price * 3):,} VND`\n"
                f"💵 **Giá mở 10 lần:** `{(price * 10):,} VND`\n\n"
                f"📝 **Mô tả:** *{desc}*\n\n"
                f"▼ Chọn loại rương trong menu và bấm nút tương ứng để mở."
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Casino Bot • Mở Rương")
        return embed

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class InteractionContext:
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.bot = interaction.client
        self.author = interaction.user
        self.channel = interaction.channel
        self.guild = interaction.guild
        self.command = None

    async def send(self, *args, **kwargs):
        if not self.interaction.response.is_done():
            return await self.interaction.response.send_message(*args, **kwargs)
        else:
            return await self.interaction.followup.send(*args, **kwargs)


class ControlPanelView(discord.ui.View):
    def __init__(self, cog, author: discord.Member, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.economy = cog.economy
        self.client = cog.client
        self.author = author
        self.current_tab = "overview"
        self.selected_stock = "CASINO"
        self.message = None
        self.setup_components()

    def setup_components(self):
        self.clear_items()
        
        # Add select menu
        self.add_item(AreaSelect())
        
        # Add stock select menu if on invest tab
        if self.current_tab == "invest":
            self.add_item(StockSelect(self.cog, is_panel=True))
            
        # Add buttons depending on tab
        if self.current_tab == "overview":
            self.add_item(DailyButton())
            self.add_item(WorkButton())
            self.add_item(CollectButton())
            self.add_item(InventoryButton())
            self.add_item(CloseButton())
        elif self.current_tab == "biz":
            self.add_item(CollectButton())
            self.add_item(BackButton())
        elif self.current_tab == "mine":
            self.add_item(MineButton())
            self.add_item(BackButton())
        elif self.current_tab == "daga":
            self.add_item(TrainButton())
            self.add_item(BackButton())
        else:
            self.add_item(BackButton())

    async def get_current_embed_and_file(self) -> tuple[discord.Embed, discord.File | None]:
        embed = await self.get_current_embed()
        file = None
        if self.current_tab == "daga":
            active_row = self.economy.get_active_cock(self.author.id)
            if active_row:
                from app.discord_bot.cogs.daga import Cock
                c = Cock(active_row)
                img_name = get_cock_image_file(c.name)
                if img_name:
                    if Path(img_name).is_absolute():
                        img_path = Path(img_name)
                    else:
                        img_path = ABS_PATH / "modules" / "daga" / img_name
                    
                    if img_path.exists():
                        file = discord.File(img_path, filename="character.png")
                        embed.set_image(url="attachment://character.png")
        elif self.current_tab == "invest":
            symbol = getattr(self, "selected_stock", "CASINO")
            file = self.cog.get_stock_chart_file(symbol)
            embed.set_image(url="attachment://chart.png")
        return embed, file

    async def update_interaction(self, interaction: discord.Interaction):
        embed, file = await self.get_current_embed_and_file()
        if file:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])

    async def update_message(self, message: discord.Message):
        embed, file = await self.get_current_embed_and_file()
        if file:
            await message.edit(embed=embed, view=self, attachments=[file])
        else:
            await message.edit(embed=embed, view=self, attachments=[])

    async def get_current_embed(self) -> discord.Embed:
        if self.current_tab == "overview":
            # Overview Embed
            profile = self.economy.get_entry(self.author.id)
            money = profile[1]
            gold = profile[2]
            gold_price = self.economy.get_gold_price()
            loan_amount, _ = self.economy.get_loan(self.author.id)
            net_worth = money + (gold * gold_price) - loan_amount
            
            # Fetch Rank Name
            from app.discord_bot.modules.profile_renderer import get_rank_info
            rank_name, _, _ = get_rank_info(net_worth)
            
            # Fetch Roulette Title
            from app.discord_bot.cogs.roulette import get_user_vip
            rl_stats = self.economy.get_roulette(self.author.id)
            rl_vip = get_user_vip(rl_stats)
            rl_title = rl_vip["title"]
            
            # Fetch Daga Title
            active_cock_row = self.economy.get_active_cock(self.author.id)
            if active_cock_row:
                from app.discord_bot.cogs.daga import Cock
                cock = Cock(active_cock_row)
                daga_title = cock.get_title()
            else:
                daga_title = "Chưa xuất trận 🌟"
            
            # Fetch Coin Flip Title
            from app.discord_bot.cogs.coinflip import get_user_vip as get_cf_vip
            cf_stats = self.economy.get_coinflip(self.author.id)
            cf_vip = get_cf_vip(cf_stats)
            cf_title = cf_vip["title"]
            
            # Fetch Businesses
            owned_bizs = []
            for biz_id, lvl in self.economy.get_businesses(self.author.id):
                if lvl > 0 and biz_id in BUSINESSES:
                    owned_bizs.append(f"{BUSINESSES[biz_id]['name']} (Cấp {lvl})")
            biz_str = ", ".join(owned_bizs) if owned_bizs else "Chưa sở hữu"
            
            # Fetch Job Info
            inventory = self.economy.get_inventory(self.author.id)
            has_degree = any(item == 'bang_cap' and qty > 0 for item, qty in inventory)
            has_mine_card = any(item == 'the_tho_mo' and qty > 0 for item, qty in inventory)
            has_hunter_card = any(item == 'the_tho_san' and qty > 0 for item, qty in inventory)
            has_architecture = any(item == 'bang_kien_truc' and qty > 0 for item, qty in inventory)
            has_astronaut = any(item == 'bang_phi_hanh' and qty > 0 for item, qty in inventory)
            has_doctor = any(item == 'bang_bac_si' and qty > 0 for item, qty in inventory)
            
            job_titles = []
            if has_degree:
                job_titles.append("Kỹ sư Công nghệ 💻")
            if has_mine_card:
                job_titles.append("Thợ mỏ VIP ⛏️")
            if has_hunter_card:
                job_titles.append("Thợ săn Kho báu 🗺️")
            if has_architecture:
                job_titles.append("Kiến trúc sư 📐")
            if has_astronaut:
                job_titles.append("Phi hành gia 🚀")
            if has_doctor:
                job_titles.append("Bác sĩ 🩺")
                
            if not job_titles:
                job_titles.append("Lao động tự do 💼")
            job_str = " & ".join(job_titles)

            from app.discord_bot.modules.profile_renderer import strip_emoji
            display_rank = strip_emoji(rank_name)
            display_rl = strip_emoji(rl_title) if rl_title else ""
            display_daga = strip_emoji(daga_title) if daga_title else ""
            display_cf = strip_emoji(cf_title) if cf_title else ""

            desc = (
                f"🎖️ **Danh hiệu:**\n"
                f"• {display_rank}\n"
                f"• {display_rl}\n"
                f"• {display_daga}\n"
                f"• {display_cf}\n\n"
                f"💰 **Số tiền:** `{money:,} VND`\n"
                f"<:32100goldbarsfortnite:1514192020921651251> **Số vàng:** `{gold:,} thỏi`\n"
                f"🏢 **Doanh nghiệp:** `{biz_str}`\n"
                f"💼 **Nghề nghiệp:** `{job_str}`\n\n"
                f"▼ Sử dụng Menu thả xuống bên dưới để thao tác"
            )
            
            embed = make_embed(
                title="----------- TỔNG QUAN -----------",
                description=desc,
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=self.author.display_avatar.url)
            embed.set_footer(text=f"🎰 Casino Bot • Bảng Điều Khiển")
            return embed
            
        elif self.current_tab == "biz":
            return self.cog.get_business_embed(self.author)
        elif self.current_tab == "invest":
            return self.cog.get_invest_embed(self.author, getattr(self, "selected_stock", "CASINO"))
        elif self.current_tab == "daga":
            return self.cog.get_daga_embed(self.author)
        elif self.current_tab == "xe":
            return self.cog.get_xe_embed(self.author)
        elif self.current_tab == "mine":
            # Mine view
            stats = self.economy.get_simulator_stats(self.author.id)
            last_mine = stats[1]
            now = int(time.time())
            cooldown = 5 * 3600
            
            if now - last_mine < cooldown:
                time_left = cooldown - (now - last_mine)
                hours = time_left // 3600
                minutes = (time_left % 3600) // 60
                mine_status = f"⏳ Đang hồi sức (Sẵn sàng sau **{hours}h {minutes}m**)"
            else:
                mine_status = "🟢 Sẵn sàng làm việc!"
                
            desc = (
                f"⛏️ **Khu khai thác mỏ hoàng gia**\n\n"
                f"• Trạng thái: {mine_status}\n"
                f"• Yêu cầu: **Thẻ thợ mỏ VIP**\n"
                f"• Cơ hội đào trúng quặng sắt (kiếm VND) và thỏi vàng lẻ!"
            )
            embed = make_embed(
                title="⛏️ KHU KHAI THÁC MỎ ⛏️",
                description=desc,
                color=discord.Color.dark_green()
            )
            return embed
            
        return make_embed(title="Bảng Điều Khiển")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Bảng điều khiển này không phải của bạn!", ephemeral=True)
            return False
            
        if not self.economy.has_claimed_start(interaction.user.id):
            await interaction.response.send_message("❌ Bạn chưa nhận quà khởi nghiệp! Hãy gõ `i?khoinghiep` trước.", ephemeral=True)
            return False
            
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

class StockSelect(discord.ui.Select):
    def __init__(self, cog, is_panel=False):
        self.cog = cog
        self.is_panel = is_panel
        options = [
            discord.SelectOption(label="USDT (Stablecoin)", value="USDT", emoji="💵"),
            discord.SelectOption(label="AGV (Antigravity Coin)", value="AGV", emoji="🌌"),
            discord.SelectOption(label="CASINO (Cổ phiếu Casino)", value="CASINO", emoji="👑"),
            discord.SelectOption(label="ETH (Ethereum)", value="ETH", emoji="🔷"),
            discord.SelectOption(label="BTC (Bitcoin)", value="BTC", emoji="🪙"),
            discord.SelectOption(label="SOL (Solana)", value="SOL", emoji="☀️"),
            discord.SelectOption(label="DOGE (Dogecoin)", value="DOGE", emoji="🐕"),
        ]
        # Highlight current stock
        symbol = getattr(cog, "selected_stock", "CASINO") if is_panel else "CASINO"
        for opt in options:
            opt.default = (opt.value == symbol)
            
        super().__init__(placeholder="Chọn cổ phiếu/crypto để xem biểu đồ...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        symbol = self.values[0]
        
        # Mark selected option as default
        for opt in self.options:
            opt.default = (opt.value == symbol)
            
        if self.is_panel:
            view.selected_stock = symbol
            await view.update_interaction(interaction)
        else:
            view.selected_symbol = symbol
            embed = view.cog.get_invest_embed(view.author, symbol)
            chart_file = view.cog.get_stock_chart_file(symbol)
            embed.set_image(url="attachment://chart.png")
            await interaction.response.edit_message(embed=embed, attachments=[chart_file], view=view)


class InvestLobbyView(discord.ui.View):
    def __init__(self, cog, author: discord.User | discord.Member, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author = author
        self.selected_symbol = "CASINO"
        self.message = None
        self.add_item(StockSelect(cog, is_panel=False))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Bảng điều khiển này không phải của bạn!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class AreaSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📊 Tổng Quan", description="Màn hình chính tổng quan tài sản", value="overview", emoji="📊"),
            discord.SelectOption(label="🏢 Doanh Nghiệp", description="Quản lý & thu hoạch doanh nghiệp", value="biz", emoji="🏢"),
            discord.SelectOption(label="📈 Chứng Khoán & Crypto", description="Thị trường đầu tư tài chính", value="invest", emoji="📈"),
            discord.SelectOption(label="⚔️ Đại Chiến Anime", description="Quản lý nhân vật Anime", value="daga", emoji="⚔️"),
            discord.SelectOption(label="🏎️ Gara Siêu Xe", description="Xem bộ sưu tập siêu xe cá nhân", value="xe", emoji="🏎️"),
            discord.SelectOption(label="⛏️ Khai Thác Mỏ", description="Đào mỏ quặng kiếm tiền và vàng", value="mine", emoji="⛏️"),
        ]
        super().__init__(placeholder="📁 Chọn khu vực quản lý...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_tab = self.values[0]
        view.setup_components()
        await view.update_interaction(interaction)

class DailyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Điểm Danh", style=discord.ButtonStyle.primary, emoji="🎁")

    async def callback(self, interaction: discord.Interaction):
        general_cog = interaction.client.get_cog("General")
        if not general_cog:
            await interaction.response.send_message("❌ Lỗi: Không tìm thấy module General.", ephemeral=True)
            return
        embed = await general_cog.process_daily(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        await self.view.update_message(interaction.message)

class WorkButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Làm Việc", style=discord.ButtonStyle.primary, emoji="💼")

    async def callback(self, interaction: discord.Interaction):
        general_cog = interaction.client.get_cog("General")
        if not general_cog:
            await interaction.response.send_message("❌ Lỗi: Không tìm thấy module General.", ephemeral=True)
            return
        embed = await general_cog.process_work(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        await self.view.update_message(interaction.message)

class InventoryButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Kho Đồ", style=discord.ButtonStyle.primary, emoji="📦")

    async def callback(self, interaction: discord.Interaction):
        embed = self.view.cog.get_inventory_embed(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Đóng Bảng Điều Khiển", style=discord.ButtonStyle.danger, emoji="❌")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="🔒 Bảng điều khiển đã đóng.", embed=None, view=None)

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Quay Lại", style=discord.ButtonStyle.secondary, emoji="🔙")

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_tab = "overview"
        view.setup_components()
        await view.update_interaction(interaction)

class CollectButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Thu Hoạch", style=discord.ButtonStyle.success, emoji="🌾")

    async def callback(self, interaction: discord.Interaction):
        embed = await self.view.cog.process_collect(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        await self.view.update_message(interaction.message)

class MineButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Đào Mỏ", style=discord.ButtonStyle.success, emoji="⛏️")

    async def callback(self, interaction: discord.Interaction):
        embed = await self.view.cog.process_mine(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.view.update_message(interaction.message)

class TrainButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Huấn Luyện", style=discord.ButtonStyle.success, emoji="💪")

    async def callback(self, interaction: discord.Interaction):
        daga_cog = interaction.client.get_cog("Daga")
        if not daga_cog:
            await interaction.response.send_message("❌ Lỗi: Không tìm thấy module Đại Chiến Anime.", ephemeral=True)
            return
        
        mock_ctx = InteractionContext(interaction)
        await daga_cog.daga_train(mock_ctx)
        
        try:
            await self.view.update_message(interaction.message)
        except Exception:
            pass


class ShopView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.category = "career"
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"shop_{self.category}":
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="🎓 Nghề Nghiệp", style=discord.ButtonStyle.primary, custom_id="shop_career")
    async def view_career(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.category = "career"
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="🔧 Công Cụ", style=discord.ButtonStyle.secondary, custom_id="shop_tools")
    async def view_tools(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.category = "tools"
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="💍 Nhẫn Cưới", style=discord.ButtonStyle.secondary, custom_id="shop_rings")
    async def view_rings(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.category = "rings"
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="🎨 Hình Nền", style=discord.ButtonStyle.secondary, custom_id="shop_banner")
    async def view_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.category = "banner"
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    def get_embed(self) -> discord.Embed:
        if self.category == "career":
            embed = make_embed(
                title="🎓 CỬA HÀNG NGHỀ NGHIỆP 🎓",
                description="Trang bị các bằng cấp và chứng chỉ để nâng cấp bản thân và mở khóa các công việc mới!",
                color=discord.Color.gold()
            )
            career_keys = ["bang_cap", "bang_kien_truc", "bang_phi_hanh", "bang_bac_si", "the_tho_mo", "the_tho_san"]
            for item_id in career_keys:
                if item_id in SHOP_ITEMS:
                    details = SHOP_ITEMS[item_id]
                    if not details.get("is_admin_only"):
                        cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
                        embed.add_field(
                            name=f"{details['name']} (ID: `{item_id}`)",
                            value=f"**Giá:** `{cost_str}`\n**Mô tả:** {details['description']}",
                            inline=False
                        )
        elif self.category == "tools":
            embed = make_embed(
                title="🔧 CỬA HÀNG CÔNG CỤ & HỢP ĐỒNG 🔧",
                description="Mua các thiết bị bảo vệ và bản đồ thám hiểm để tối ưu hóa tài sản doanh nghiệp của bạn!",
                color=discord.Color.blue()
            )
            tool_keys = [
                "manager_contract",
                "insurance_contract",
                "bodyguard_contract",
                "security_system"
            ]
            for item_id in tool_keys:
                if item_id in SHOP_ITEMS:
                    details = SHOP_ITEMS[item_id]
                    if not details.get("is_admin_only"):
                        cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
                        embed.add_field(
                            name=f"{details['name']} (ID: `{item_id}`)",
                            value=f"**Giá:** `{cost_str}`\n**Mô tả:** {details['description']}",
                            inline=False
                        )
        elif self.category == "rings":
            embed = make_embed(
                title="💍 CỬA HÀNG NHẪN CƯỚI 💍",
                description="Mua các loại nhẫn cầu hôn tuyệt đẹp để thề ước và nhận các đặc quyền gia đình!",
                color=discord.Color.magenta()
            )
            ring_keys = [
                "ring_grass",
                "ring_quartz",
                "ring_aquamarine",
                "ring_emerald",
                "ring_amethyst",
                "ring_cupid",
                "ring_citrine",
                "ring_ruby",
                "ring_sapphire",
                "ring_sunburst",
                "ring_gothic",
                "ring_angel",
                "ring_divine"
            ]
            for item_id in ring_keys:
                if item_id in SHOP_ITEMS:
                    details = SHOP_ITEMS[item_id]
                    if not details.get("is_admin_only"):
                        cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
                        embed.add_field(
                            name=f"{details['name']} (ID: `{item_id}`)",
                            value=f"**Giá:** `{cost_str}`\n**Mô tả:** {details['description']}",
                            inline=False
                        )
        else:
            embed = make_embed(
                title="🎨 CỬA HÀNG HÌNH NỀN & BANNER 🎨",
                description="Hãy trang hoàng trang cá nhân sành điệu của bạn bằng các hình nền / banner tuyệt đẹp!",
                color=discord.Color.purple()
            )
            for item_id, details in SHOP_ITEMS.items():
                if details.get("is_banner") and not details.get("is_admin_only"):
                    cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
                    embed.add_field(
                        name=f"{details['name']} (ID: `{item_id}`)",
                        value=f"**Giá:** `{cost_str}`\n**Mô tả:** {details['description']}",
                        inline=False
                    )
        
        embed.set_footer(text="Gõ i?buyitem <item_id> để mua đồ.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Bảng điều khiển này không phải của bạn!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class Simulator(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.update_stock_prices_task.start()

    def cog_unload(self) -> None:
        self.update_stock_prices_task.cancel()

    async def cog_before_invoke(self, ctx: commands.Context):
        self.economy.set_setting("last_invest_channel_id", str(ctx.channel.id))

    @commands.command(
        brief="Hiển thị bảng điều khiển quản lý tài sản.",
        usage="menu / panel / dashboard",
        aliases=["panel", "dashboard", "control", "cp", "bảng"]
    )
    async def menu(self, ctx: commands.Context):
        view = ControlPanelView(self, ctx.author)
        embed, file = await view.get_current_embed_and_file()
        if file:
            msg = await ctx.send(embed=embed, view=view, file=file)
        else:
            msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    def get_inventory_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        inventory = self.economy.get_inventory(user.id)
        if not inventory or sum(qty for _, qty in inventory) == 0:
            embed = make_embed(
                title=f"🎒 TÚI ĐỒ CỦA {user.name.upper()}",
                description="Túi đồ của bạn hiện đang trống rỗng.",
                color=discord.Color.blue()
            )
            return embed

        embed = make_embed(
            title=f"🎒 TÚI ĐỒ CỦA {user.name.upper()}",
            color=discord.Color.blue()
        )
        
        has_items = False
        for item_id, qty in inventory:
            if qty <= 0:
                continue
                
            if item_id in SHOP_ITEMS:
                item = SHOP_ITEMS[item_id]
                embed.add_field(
                    name=f"{item['name']}",
                    value=f"• Số lượng: **{qty}**\n• Chức năng: *{item['description']}*",
                    inline=False
                )
                has_items = True
            elif item_id in TREASURES:
                item = TREASURES[item_id]
                embed.add_field(
                    name=f"🏺 {item['name']} (ID: `{item_id}`)",
                    value=(
                        f"• Số lượng: **{qty}**\n"
                        f"• Độ hiếm: `{item['rarity']}`\n"
                        f"• Giá bán: `{item['value']:,} VND`\n"
                        f"• *Cổ vật/kho báu sưu tầm.*"
                    ),
                    inline=False
                )
                has_items = True
                
        if not has_items:
            embed.description = "Túi đồ của bạn hiện đang trống rỗng."
            
        return embed

    async def process_mine(self, user: discord.User | discord.Member, ctx: commands.Context | None = None) -> discord.Embed:
        user_id = user.id
        
        # Check Gold Miner Career (the_tho_mo)
        inventory = self.economy.get_inventory(user_id)
        has_card = any(item == 'the_tho_mo' and qty > 0 for item, qty in inventory)
        if not has_card:
            embed = make_embed(
                title="❌ CHƯA ĐĂNG KÝ NGHỀ KHAI THÁC VÀNG ❌",
                description="Yêu cầu phải sở hữu **Nghề khai thác vàng** để đào mỏ! Hãy gõ `i?shop` để đăng ký nghề nghiệp bằng VND trước.",
                color=discord.Color.red()
            )
            return embed

        # Check pickaxe upgrades
        upgrades = self.economy.get_upgrades(user_id)
        pickaxe_level = upgrades[3]
        
        pickaxe_names = {
            0: "Cuốc Gỗ 🪵",
            1: "Cuốc Sắt ⚙️",
            2: "Cuốc Vàng 🪙",
            3: "Cuốc Kim Cương 💎"
        }
        pickaxe_name = pickaxe_names.get(pickaxe_level, "Cuốc Gỗ 🪵")

        # Check cooldown
        stats = self.economy.get_simulator_stats(user_id)
        last_mine = stats[1]
        now = int(time.time())
        
        cooldown_hours = {0: 5, 1: 4, 2: 3, 3: 2}
        hours_cd = cooldown_hours.get(pickaxe_level, 5)
        cooldown = hours_cd * 3600
        
        if now - last_mine < cooldown:
            time_left = cooldown - (now - last_mine)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            
            embed = make_embed(
                title="⏳ BẠN ĐANG MỆT ⏳",
                description=f"Hãy nghỉ ngơi! Bằng việc sử dụng **{pickaxe_name}**, bạn có thể tiếp tục đào mỏ sau **{hours} giờ {minutes} phút**.",
                color=discord.Color.red()
            )
            return embed

        # Calculate user's current gold
        profile = self.economy.get_entry(user_id)
        current_gold_blocks = profile[2]
        fractional_gold = stats[3]
        total_gold = current_gold_blocks + fractional_gold

        # Success rate decreases as total_gold increases, but gets pickaxe bonus
        success_chance = max(5.0, min(80.0, 80.0 - total_gold * 0.5))
        pickaxe_bonuses = {0: 0.0, 1: 10.0, 2: 20.0, 3: 35.0}
        success_chance += pickaxe_bonuses.get(pickaxe_level, 0.0)
        success_chance = min(95.0, success_chance)

        roll = random.random() * 100
        dropped_gold = 0.0
        gold_message = ""
        success = False

        if roll < success_chance:
            success = True
            gold_ranges = {
                0: (0.01, 0.50),
                1: (0.10, 0.70),
                2: (0.20, 1.20),
                3: (0.50, 2.50)
            }
            min_g, max_g = gold_ranges.get(pickaxe_level, (0.01, 0.50))
            dropped_gold = round(random.uniform(min_g, max_g), 2)
            gold_message = f"\n✨ **ĐẶC BIỆT:** Bạn dùng **{pickaxe_name}** đào trúng mạch vàng và thu về **{dropped_gold}** Vàng!"

        # Base money reward from normal ores (always awarded)
        ore_money = random.randint(20_000, 100_000)
        self.economy.add_money(user_id, ore_money)
        
        # Process fractional gold reward if success
        total_gold_frac = stats[3] + dropped_gold
        int_gold = int(total_gold_frac)
        new_frac = round(total_gold_frac - int_gold, 4)
        
        if int_gold > 0:
            self.economy.add_credits(user_id, int_gold)
            gold_message += f" (Đã quy đổi cộng thêm `{int_gold}` thỏi vàng vào két sắt)"

        # Save stats
        self.economy.set_simulator_stats(user_id, last_mine=now, fractional_gold=new_frac)
        
        log_wallet_change(
            logger,
            event="mine_ore",
            user_id=user_id,
            money_delta=ore_money,
            credits_delta=int_gold,
            ctx=ctx,
            dropped_gold_frac=dropped_gold,
            success_chance=success_chance,
            success=success
        )

        chance_text = f"🎯 **Tỷ lệ trúng vàng của bạn:** `{success_chance:.2f}%` *(Độ khó tăng dần theo số vàng hiện có: {total_gold:.2f} Vàng)*"

        if success:
            desc = (
                f"Bạn đã vác cuốc vào hầm mỏ khai thác vàng...\n\n"
                f"💰 **Bán quặng thường:** `+{ore_money:,} VND`"
                f"{gold_message}\n"
                f"💳 **Vàng lẻ đang tích lũy:** `{new_frac} Vàng` (Đủ `1.0` sẽ tự đổi ra thỏi)\n"
                f"{chance_text}"
            )
            color = discord.Color.gold()
        else:
            desc = (
                f"Bạn đã vác cuốc vào hầm mỏ khai thác vàng...\n\n"
                f"💰 **Bán quặng thường:** `+{ore_money:,} VND`\n"
                f"💨 Không tìm thấy vàng trong ca làm việc này. Hãy kiên trì!\n"
                f"{chance_text}"
            )
            color = discord.Color.dark_green()

        embed = make_embed(
            title="⛏️ KHAI THÁC VÀNG TỰ NHIÊN ⛏️",
            description=desc,
            color=color
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        return embed

    def get_business_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        user_id = user.id
        owned = dict(self.economy.get_businesses(user_id))
        
        embed = make_embed(
            title="🏢 DANH SÁCH DOANH NGHIỆP CỦA BẠN 🏢",
            description="Sở hữu doanh nghiệp để nhận thu nhập thụ động mỗi giờ (Cần gõ `i?collect` hoặc bấm nút Thu Hoạch).",
            color=discord.Color.teal()
        )
        
        stats = self.economy.get_simulator_stats(user_id)
        last_collect = stats[0]
        now = int(time.time())
        
        for biz_id, details in BUSINESSES.items():
            lvl = owned.get(biz_id, 0)
            
            if lvl > 0:
                current_revenue = details['base_revenue'] * lvl
                if details['currency'] == "money":
                    rev_str = f"{current_revenue:,} VND/giờ"
                else:
                    rev_str = f"{current_revenue * 24:.2f} Vàng/ngày"
                status = f"🟢 Đang hoạt động (Cấp {lvl}{' - Tối đa' if lvl >= 10 else ''})\n📈 Doanh thu hiện tại: `{rev_str}`"
            else:
                status = "🔴 Chưa sở hữu"
                
            if lvl >= 10:
                cost_str = "Đã đạt cấp tối đa"
                next_rev_str = "`Đã đạt cấp tối đa`"
            else:
                cost = int(details['base_cost'] * (1.5 ** lvl))
                cost_str = f"{cost:,} VND" if details['currency'] == "money" else f"{cost} thỏi vàng"
                next_lvl_revenue = details['base_revenue'] * (lvl + 1)
                if details['currency'] == "money":
                    next_rev_str = f"`{next_lvl_revenue:,} VND/giờ`"
                else:
                    next_rev_str = f"`{next_lvl_revenue * 24:.2f} Vàng/ngày`"
                
            buff_desc = f"\n🌟 **Đặc quyền:** {details['buff']}" if 'buff' in details else ""
            
            embed.add_field(
                name=f"{details['name']}",
                value=(
                    f"• Trạng thái: {status}\n"
                    f"• Chi phí mua/nâng cấp: `{cost_str}`\n"
                    f"• Doanh thu cấp tiếp theo: {next_rev_str}"
                    f"{buff_desc}"
                ),
                inline=False
            )
            
        if last_collect > 0:
            elapsed = (now - last_collect) // 60
            embed.set_footer(text=f"Đã tích lũy doanh thu trong {elapsed} phút qua. Gõ i?collect để nhận.")
        else:
            embed.set_footer(text="Gõ i?biz buy <id> hoặc i?biz upgrade <id> để mua/nâng cấp.")
            
        return embed

    async def process_collect(self, user: discord.User | discord.Member, ctx: commands.Context | None = None) -> discord.Embed:
        user_id = user.id
        owned = dict(self.economy.get_businesses(user_id))
        
        if not owned or sum(lvl for lvl in owned.values()) == 0:
            embed = make_embed(
                title="❌ CHƯA CÓ DOANH NGHIỆP ❌",
                description="Bạn chưa sở hữu doanh nghiệp nào! Hãy dùng `i?biz` để mua.",
                color=discord.Color.red()
            )
            return embed

        stats = self.economy.get_simulator_stats(user_id)
        last_collect = stats[0]
        now = int(time.time())
        
        if last_collect == 0:
            self.economy.set_simulator_stats(user_id, last_collect=now)
            embed = make_embed(
                title="⏱️ BẮT ĐẦU TÍNH DOANH THU ⏱️",
                description="Đã bắt đầu tính doanh thu cho doanh nghiệp của bạn từ bây giờ.",
                color=discord.Color.blue()
            )
            return embed

        elapsed_sec = now - last_collect
        if elapsed_sec < 60:
            embed = make_embed(
                title="⏳ DOANH THU QUÁ NHỎ ⏳",
                description="Hãy đợi ít nhất 1 phút để tích lũy doanh thu.",
                color=discord.Color.red()
            )
            return embed
            
        hours = elapsed_sec / 3600.0
        hours = min(24.0, hours)
        
        earned_money = 0
        earned_gold_frac = 0.0
        
        for biz_id, lvl in owned.items():
            if lvl <= 0:
                continue
            biz = BUSINESSES[biz_id]
            revenue = biz['base_revenue'] * lvl
            
            if biz['currency'] == "money":
                earned_money += int(hours * revenue)
            else:
                earned_gold_frac += hours * revenue

        # Check active marriage multiplier
        marriage_multiplier = self.economy.get_marriage_multiplier(user_id)
        marriage_info = ""
        if marriage_multiplier > 1.0:
            earned_money = int(earned_money * marriage_multiplier)
            earned_gold_frac = earned_gold_frac * marriage_multiplier
            bonus_pct = int((marriage_multiplier - 1.0) * 100)
            marriage_info = f"\n💖 *Đã cộng thêm **{bonus_pct}%** từ Thệ ước Hôn nhân!*"

        total_gold_frac = stats[3] + earned_gold_frac
        int_gold = int(total_gold_frac)
        new_frac = round(total_gold_frac - int_gold, 4)
        
        # Check upgrades
        upgrades = self.economy.get_upgrades(user_id)
        insurance_active = upgrades[1] > now
        
        # Operational Risk & Insurance Check (10% chance)
        accident_triggered = False
        accident_msg = ""
        
        if earned_money > 100_000 and random.random() < 0.10:
            accident_triggered = True
            accident_type = random.choice(["fire", "fine"])
            if accident_type == "fire":
                loss_amount = int(earned_money * 0.15)
                accident_msg = f"⚠️ **SỰ CỐ VẬN HÀNH:** Thiết bị sản xuất bị chập điện gây cháy, tổn thất **-{loss_amount:,} VND** (15% doanh thu)!"
                if insurance_active:
                    accident_msg += "\n🛡️ **BẢO HIỂM CHI TRẢ:** Nhờ có **Bảo hiểm Doanh nghiệp** còn hiệu lực, bạn được đền bù toàn bộ tổn thất!"
                else:
                    earned_money -= loss_amount
            else:
                fine_amount = min(earned_money, 5_000_000)
                accident_msg = f"⚠️ **SỰ CỐ VẬN HÀNH:** Cơ quan chức năng tiến hành thanh tra đột xuất doanh nghiệp, phạt hành chính **-{fine_amount:,} VND**!"
                if insurance_active:
                    accident_msg += "\n🛡️ **BẢO HIỂM CHI TRẢ:** Nhờ có **Bảo hiểm Doanh nghiệp** còn hiệu lực, bảo hiểm đã thanh toán toàn bộ tiền phạt!"
                else:
                    earned_money -= fine_amount

        if earned_money == 0 and int_gold == 0:
            embed = make_embed(
                title="⏳ DOANH THU QUÁ NHỎ ⏳",
                description=f"Doanh thu tích lũy hiện tại quá ít. Hãy đợi thêm (Đã trôi qua {elapsed_sec // 60} phút).",
                color=discord.Color.red()
            )
            return embed

        if earned_money != 0:
            self.economy.add_money(user_id, earned_money)
        if int_gold > 0:
            self.economy.add_credits(user_id, int_gold)

        self.economy.set_simulator_stats(user_id, last_collect=now, fractional_gold=new_frac)
        
        log_wallet_change(
            logger,
            event="collect_passive_income",
            user_id=user_id,
            money_delta=earned_money,
            credits_delta=int_gold,
            ctx=ctx,
            elapsed_sec=elapsed_sec
        )

        gold_str = f"\n<:32100goldbarsfortnite:1514192020921651251> **Vàng nhận:** `+{int_gold} thỏi vàng`" if int_gold > 0 else ""
        accident_embed_str = f"\n\n{accident_msg}" if accident_triggered else ""
        
        embed = make_embed(
            title="🏢 BÁO CÁO DOANH THU DOANH NGHIỆP 🏢",
            description=(
                f"Sau **{elapsed_sec // 60} phút** làm việc chăm chỉ, các doanh nghiệp của bạn đã báo cáo thu hoạch:\n\n"
                f"💰 **VND nhận:** `+{earned_money:,} VND`"
                f"{gold_str}\n"
                f"💳 **Vàng lẻ tích lũy thêm:** `+{earned_gold_frac:.4f} Vàng` (Số dư dư: `{new_frac} Vàng`)"
                f"{marriage_info}"
                f"{accident_embed_str}"
            ),
            color=discord.Color.red() if (accident_triggered and not insurance_active) else discord.Color.green()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        return embed

    def get_invest_embed(self, user: discord.User | discord.Member, symbol: str | None = None) -> discord.Embed:
        if symbol is None:
            symbol = "CASINO"
            
        prices = self.economy.get_stock_prices()
        target_row = None
        for row in prices:
            if row[0] == symbol:
                target_row = row
                break
                
        if not target_row:
            symbol = "CASINO"
            for row in prices:
                if row[0] == symbol:
                    target_row = row
                    break
                    
        if not target_row and prices:
            target_row = prices[0]
            symbol = target_row[0]
            
        import json
        active_news = None
        news_data = self.economy.get_setting("active_news")
        if news_data:
            try:
                active_news = json.loads(news_data)
            except Exception:
                pass
                
        news_str = ""
        if active_news:
            news_str = f"\n\n🔥 **TIN TỨC THỊ TRƯỜNG:**\n> {active_news['title']}\n> *(Hiệu lực còn {active_news['duration']} phiên)*"
            
        embed = make_embed(
            title=f"📈 CHI TIẾT GIAO DỊCH: {symbol} 📈",
            description=f"Tỷ giá biến động tự động mỗi 5 phút một lần. Đầu tư bằng tiền mặt VND.{news_str}",
            color=discord.Color.blue()
        )
        
        user_portfolio = dict(self.economy.get_portfolio(user.id))
        
        if target_row:
            sym, price, prev, change = target_row
            trend_str = "📈 TĂNG" if change > 0 else "📉 GIẢM" if change < 0 else "↔️ ỔN ĐỊNH"
            owned_shares = user_portfolio.get(sym, 0.0)
            value = int(owned_shares * price)
            
            embed.add_field(
                name=f"{sym} ({trend_str})",
                value=(
                    f"💵 **Giá hiện tại:** `{price:,} VND` / cổ\n"
                    f"📊 **Biến động:** `{change:+.2f}%`\n"
                    f"🎒 **Bạn đang sở hữu:** `{owned_shares:.2f}` cổ (`{value:,} VND`)"
                ),
                inline=False
            )
            
        embed.set_footer(text="Gõ i?invest buy <ticker> <số lượng> hoặc i?invest sell <ticker> <số lượng>")
        return embed

    def get_daga_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        active_row = self.economy.get_active_cock(user.id)
        if not active_row:
            embed = make_embed(
                title="⚔️ ĐẠI CHIẾN ANIME ⚔️",
                description="⚠️ **Bạn chưa chọn nhân vật chính xuất trận.**\n\nHãy gõ `i?anime list` để xem các nhân vật bạn đang sở hữu và gõ `i?anime active <ID>` để đặt nhân vật xuất trận!",
                color=discord.Color.gold()
            )
            return embed

        from app.discord_bot.cogs.daga import Cock
        c = Cock(active_row)
        
        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }
        
        display_rarity = RARITY_DISPLAY.get(c.rarity, c.rarity)
        desc = (
            f"⚔️ **Nhân vật:** `{c.name}`\n"
            f"⭐ **Độ hiếm:** {rarity_emojis.get(c.rarity, '')} `{display_rarity}`\n"
            f"📈 **Cấp độ:** `{c.level}` (EXP: `{c.exp}/{c.level * 100}`)\n"
            f"❤️ **HP:** `{c.hp}` | ⚔️ **ATK:** `{c.atk}` | 🛡️ **DEF:** `{c.df}`\n"
            f"⚡ **SPD:** `{c.spd}` | 🍀 **LUK:** `{c.luk}`\n"
            f"⚔️ **Số trận thắng:** `{c.wins}` | 🛡️ **Số trận thua:** `{c.losses}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{c.streak}` ngày"
        )
        
        embed = make_embed(
            title=f"⚔️ NHÂN VẬT ĐANG XUẤT TRẬN CỦA {user.name.upper()} ⚔️",
            description=desc,
            color=discord.Color.gold()
        )
        return embed

    def get_xe_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        cars = self.economy.get_user_cars(user.id)
        fav_car = self.economy.get_favorite_car(user.id)
        
        desc = ""
        if fav_car:
            desc += f"🏎️ **Siêu xe yêu thích:** {fav_car[2]} ({fav_car[3]}) - Phiên bản: `{fav_car[5]}` (Serial: `#{fav_car[4]:04d}`)\n\n"
        
        if not cars:
            desc += "🎒 **Bạn chưa sở hữu siêu xe nào!**\nHãy gõ `i?xe` để xem hướng dẫn và tham gia đua xe / đấu giá để có siêu xe nhé!"
        else:
            desc += "**Danh sách xe bạn sở hữu:**\n"
            for car in cars:
                fav_marker = " ⭐" if car[7] else ""
                desc += f"• **{car[2]}** ({car[3]}) - Phiên bản: `{car[5]}` (Serial: `#{car[4]:04d}`){fav_marker}\n"
                
        embed = make_embed(
            title=f"🏎️ GARA SIÊU XE CỦA {user.name.upper()} 🏎️",
            description=desc,
            color=discord.Color.dark_red()
        )
        return embed

    def cog_unload(self) -> None:
        self.update_stock_prices_task.cancel()

    @tasks.loop(minutes=5)
    async def update_stock_prices_task(self):
        """Fluctuates the virtual stock/crypto prices every 5 minutes."""
        try:
            import json
            now = int(time.time())
            
            # --- 1. Market News Event System ---
            active_news = None
            news_data = self.economy.get_setting("active_news")
            if news_data:
                try:
                    active_news = json.loads(news_data)
                except Exception:
                    pass
            
            if active_news:
                active_news['duration'] -= 1
                if active_news['duration'] <= 0:
                    active_news = None
                    self.economy.set_setting("active_news", "")
                else:
                    self.economy.set_setting("active_news", json.dumps(active_news))
            
            # Roll for new news every 30 minutes (6 ticks)
            news_ticks_str = self.economy.get_setting("news_ticks") or "0"
            news_ticks = int(news_ticks_str) + 1
            if news_ticks >= 6:
                news_ticks = 0
                if not active_news and random.random() < 0.35:
                    templates = [
                        {"title": "📰 TIN TỐT: Quốc gia lớn hợp pháp hóa BTC làm phương thức thanh toán, dòng tiền đổ vào ồ ạt!", "symbol": "BTC", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Sàn giao dịch tiền điện tử lớn bị hack, BTC giảm sâu toàn hệ thống!", "symbol": "BTC", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: Tập đoàn CASINO báo cáo lợi nhuận quý kỷ lục, giá cổ tức tăng mạnh!", "symbol": "CASINO", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Siết chặt quy định kiểm tra cá cược trực tuyến, cổ phiếu CASINO bị bán tháo!", "symbol": "CASINO", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: AGV giới thiệu mô hình AI thế hệ mới dẫn đầu thế giới công nghệ!", "symbol": "AGV", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: AGV đối mặt với vụ kiện độc quyền dữ liệu lớn tại thị trường châu Âu!", "symbol": "AGV", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: Đồng USD tăng giá mạnh mẽ kéo theo sự tăng trưởng nhẹ của USDT!", "symbol": "USDT", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Cục dự trữ Liên Bang phát hành stablecoin đối thủ khiến USDT bị rút nhẹ!", "symbol": "USDT", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: Bản cập nhật nâng cấp Ethereum 2.5 hoàn tất, phí gas giảm sâu!", "symbol": "ETH", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Phát hiện lỗ hổng smart contract trên mạng lưới Ethereum, giá sụt giảm!", "symbol": "ETH", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: Quỹ đầu tư mạo hiểm công bố đầu tư 10 tỷ USD vào hệ sinh thái Solana!", "symbol": "SOL", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Mạng lưới Solana bị nghẽn giao dịch liên tục trong 24 giờ!", "symbol": "SOL", "direction": "down", "duration": 6},
                        {"title": "📰 TIN TỐT: Tỷ phú công nghệ đăng ảnh chú chó Shiba Inu làm đại diện, DOGE bay cao!", "symbol": "DOGE", "direction": "up", "duration": 6},
                        {"title": "📰 TIN XẤU: Cộng đồng chốt lời meme coin khiến DOGE sụt giảm nghiêm trọng!", "symbol": "DOGE", "direction": "down", "duration": 6}
                    ]
                    active_news = random.choice(templates)
                    self.economy.set_setting("active_news", json.dumps(active_news))
            self.economy.set_setting("news_ticks", str(news_ticks))
            
            # --- 2. Fluctuate Stock Prices ---
            prices = self.economy.get_stock_prices()
            news_symbol = active_news.get("symbol") if active_news else None
            news_dir = active_news.get("direction") if active_news else None
            
            # Configs: (min_price, max_price, base_fluctuation_range_tuple, news_up_range_tuple, news_down_range_tuple)
            stock_configs = {
                "USDT": (24_500, 25_500, (-0.01, 0.01), (0.005, 0.015), (-0.015, -0.005)),
                "AGV": (1_000, 100_000, (-0.03, 0.03), (0.04, 0.10), (-0.10, -0.04)),
                "CASINO": (10_000, 1_000_000, (-0.08, 0.08), (0.08, 0.20), (-0.20, -0.08)),
                "ETH": (50_000, 5_000_000, (-0.10, 0.10), (0.10, 0.22), (-0.22, -0.10)),
                "BTC": (100_000, 10_000_000, (-0.15, 0.15), (0.12, 0.28), (-0.28, -0.12)),
                "SOL": (8_000, 800_000, (-0.18, 0.18), (0.15, 0.35), (-0.35, -0.15)),
                "DOGE": (100, 50_000, (-0.30, 0.35), (0.30, 0.60), (-0.60, -0.30))
            }
            
            bankrupted_symbols = []
            for symbol, current_price, _, _ in prices:
                if symbol not in stock_configs:
                    continue
                    
                min_p, max_p, base_range, up_range, down_range = stock_configs[symbol]
                
                # Check bankruptcy chance or countdown (Option D)
                is_bankruptcy = False
                countdown_str = self.economy.get_setting(f"scheduled_bankruptcy_{symbol}")
                if countdown_str:
                    try:
                        countdown = int(countdown_str)
                    except ValueError:
                        countdown = 0
                    
                    if countdown == 2:
                        # Decrement to 1
                        self.economy.set_setting(f"scheduled_bankruptcy_{symbol}", "1")
                        # Send warning to channel without pings (countdown = 1)
                        try:
                            channel_id_str = self.economy.get_setting("last_invest_channel_id")
                            if channel_id_str:
                                channel_id = int(channel_id_str)
                                channel = self.client.get_channel(channel_id)
                                if channel is None:
                                    channel = await self.client.fetch_channel(channel_id)
                                if channel:
                                    embed = make_embed(
                                        title=f"⚠️ CẢNH BÁO PHÁ SẢN KHẨN CẤP: {symbol} (Còn 1 phiên) ⚠️",
                                        description=(
                                            f"Mã đầu tư `{symbol}` đang gặp biến động cực kỳ tiêu cực và có nguy cơ cao sẽ **phá sản** ở phiên tiếp theo!\n\n"
                                            f"💡 Toàn bộ cổ đông nắm giữ hãy chủ động xử lý tài sản trước khi mã này bị thanh lý cưỡng chế."
                                        ),
                                        color=discord.Color.gold()
                                    )
                                    await channel.send(embed=embed)
                        except Exception as warn_err:
                            logger.error(f"Error sending countdown=1 bankruptcy warning: {warn_err}")
                    elif countdown == 1:
                        # Time to crash!
                        is_bankruptcy = True
                else:
                    # Roll normal bankruptcy chance
                    is_bankruptcy_rolled = False
                    if news_symbol == symbol and news_dir == "down":
                        if random.random() < 0.05: # 5% chance under bad news
                            is_bankruptcy_rolled = True
                    elif random.random() < 0.005: # 0.5% chance normally
                        is_bankruptcy_rolled = True
                        
                    if is_bankruptcy_rolled:
                        # Schedule bankruptcy: set to 2 sessions
                        self.economy.set_setting(f"scheduled_bankruptcy_{symbol}", "2")
                        # Send warning (countdown = 2) with user pings
                        try:
                            holders = self.economy.get_stock_holders(symbol)
                            holder_ids = [user_id for user_id, shares in holders if shares > 0]
                            if holder_ids:
                                mentions = " ".join([f"<@{uid}>" for uid in holder_ids])
                                channel_id_str = self.economy.get_setting("last_invest_channel_id")
                                if channel_id_str:
                                    channel_id = int(channel_id_str)
                                    channel = self.client.get_channel(channel_id)
                                    if channel is None:
                                        channel = await self.client.fetch_channel(channel_id)
                                    if channel:
                                        embed = make_embed(
                                            title=f"🚨 CẢNH BÁO PHÁ SẢN: {symbol} (Còn 2 phiên) 🚨",
                                            description=(
                                                f"Hội đồng quản trị `{symbol}` báo cáo tình hình tài chính cực kỳ nguy kịch. Mã này dự kiến sẽ **phá sản** sau 2 phiên nữa!\n\n"
                                                f"🚨 **Các cổ đông nắm giữ:** {mentions}\n"
                                                f"💡 Vui lòng đưa ra quyết định đầu tư phù hợp."
                                            ),
                                            color=discord.Color.orange()
                                        )
                                        await channel.send(content=mentions, embed=embed)
                        except Exception as warn_err:
                            logger.error(f"Error sending countdown=2 bankruptcy warning: {warn_err}")
                    
                if is_bankruptcy:
                    bankrupted_symbols.append(symbol)
                    bankruptcy_price = int(min_p * 0.1)
                    
                    # Update stock price to crashed price in DB
                    self.economy.update_stock_price(symbol, bankruptcy_price, current_price, -90.0)
                    logger.warning(f"🚨 CRITICAL: Stock {symbol} went bankrupt! Price crashed to {bankruptcy_price} VND.")
                    
                    # Refund active limit orders for this bankrupt stock
                    try:
                        all_orders = self.economy.get_all_active_limit_orders()
                        for order_id, user_id, ord_sym, order_type, target_price, shares, _ in all_orders:
                            if ord_sym == symbol:
                                if order_type == "BUY":
                                    refund_money = get_limit_buy_cost(shares, target_price, symbol)
                                    self.economy.add_money(user_id, refund_money)
                                else: # SELL
                                    # Refund locked shares back to their portfolio
                                    portfolio = dict(self.economy.get_portfolio(user_id))
                                    curr_shares = portfolio.get(symbol, 0.0)
                                    self.economy.set_portfolio_shares(user_id, symbol, curr_shares + shares)
                                self.economy.remove_limit_order(order_id)
                    except Exception as err:
                        logger.error(f"Error handling limit orders for bankrupt stock {symbol}: {err}")
                        
                    # Liquidate all outstanding shares for this stock held by users
                    try:
                        holders = self.economy.get_stock_holders(symbol)
                        liquidated_users = []
                        for user_id, shares in holders:
                            if shares <= 0:
                                continue
                            
                            liquidation_value = int(shares * bankruptcy_price)
                            fee = int(liquidation_value * 0.05)
                            payout = liquidation_value - fee
                            
                            # Add payout to user and set shares to 0
                            self.economy.add_money(user_id, payout)
                            self.economy.set_portfolio_shares(user_id, symbol, 0.0)
                            liquidated_users.append((user_id, shares, payout))
                            
                        # Send public/channel announcement instead of DM
                        channel_id_str = self.economy.get_setting("last_invest_channel_id")
                        if channel_id_str:
                            try:
                                channel_id = int(channel_id_str)
                                channel = self.client.get_channel(channel_id)
                                if channel is None:
                                    channel = await self.client.fetch_channel(channel_id)
                                if channel:
                                    desc_lines = [
                                        f"Mã đầu tư `{symbol}` đã chính thức phá sản sau thời gian cảnh báo!\n\n",
                                        f"💥 **Giá thanh lý tài sản:** `{bankruptcy_price:,} VND` / cổ\n",
                                        f"💡 Toàn bộ cổ phiếu `{symbol}` của các cổ đông đã bị cưỡng chế tự động bán để thu hồi tài sản:\n\n"
                                    ]
                                    for user_id, shares, payout in liquidated_users:
                                        desc_lines.append(f"• <@{user_id}>: Nhận lại `+{payout:,} VND` (cho `{shares:.2f} {symbol}`, phí thanh lý 5%)\n")
                                    
                                    if not liquidated_users:
                                        desc_lines.append("• Không có cổ đông nào đang nắm giữ mã này.")
                                        
                                    embed = make_embed(
                                        title=f"🚨 BÁO CÁO PHÁ SẢN & THANH LÝ CƯỠNG CHẾ: {symbol} 🚨",
                                        description="".join(desc_lines),
                                        color=discord.Color.red()
                                    )
                                    await channel.send(embed=embed)
                            except Exception as chan_err:
                                logger.error(f"Error sending bankruptcy announcement: {chan_err}")
                    except Exception as err:
                        logger.error(f"Error liquidating portfolio for bankrupt stock {symbol}: {err}")
                        
                    # Immediately restructure/reset the stock price to its default starting price
                    restructured_price = DEFAULT_PRICES.get(symbol, min_p * 2)
                    self.economy.update_stock_price(symbol, restructured_price, bankruptcy_price, 0.0)
                    logger.info(f"Restructured {symbol}. Price reset to {restructured_price} VND.")
                    
                    # Clear scheduled bankruptcy setting
                    self.economy.set_setting(f"scheduled_bankruptcy_{symbol}", "")
                    continue
                
                # Normal fluctuation
                if news_symbol == symbol and news_dir == "up":
                    change = random.uniform(*up_range)
                elif news_symbol == symbol and news_dir == "down":
                    change = random.uniform(*down_range)
                else:
                    change = random.uniform(*base_range)
                    
                new_price = int(current_price * (1 + change))
                new_price = max(min_p, min(max_p, new_price))
                
                change_percent = ((new_price - current_price) / current_price) * 100
                self.economy.update_stock_price(symbol, new_price, current_price, change_percent)
            logger.info("Stock/crypto prices updated.")

            # --- 3. Limit Orders Execution ---
            try:
                active_orders = self.economy.get_all_active_limit_orders()
                current_prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
                
                for order_id, user_id, symbol, order_type, target_price, shares, created_at in active_orders:
                    curr_price = current_prices.get(symbol)
                    if not curr_price:
                        continue
                        
                    trigger = False
                    if order_type == "BUY" and curr_price <= target_price:
                        trigger = True
                    elif order_type == "SELL" and curr_price >= target_price:
                        trigger = True
                        
                    if trigger:
                        if order_type == "BUY":
                            portfolio = dict(self.economy.get_portfolio(user_id))
                            curr_shares = portfolio.get(symbol, 0.0)
                            
                            # Check max holding limit (Option B)
                            limit_str = self.economy.get_setting(f"max_holding_{symbol}")
                            limit_exceeded = False
                            if limit_str:
                                try:
                                    limit_val = float(limit_str)
                                    if curr_shares + shares > limit_val:
                                        limit_exceeded = True
                                except ValueError:
                                    pass
                                    
                            if limit_exceeded:
                                # Refund locked funds and cancel order
                                locked_funds = get_limit_buy_cost(shares, target_price, symbol)
                                self.economy.add_money(user_id, locked_funds)
                                self.economy.remove_limit_order(order_id)
                                
                                user = self.client.get_user(user_id)
                                if user is None:
                                    try: user = await self.client.fetch_user(user_id)
                                    except Exception: pass
                                if user:
                                    embed = make_embed(
                                        title="🔔 LỆNH TỰ ĐỘNG BỊ HỦY (VƯỢT GIỚI HẠN) 🔔",
                                        description=(
                                            f"Lệnh mua tự động (Limit Buy) của bạn đã bị hủy do số lượng nắm giữ vượt quá giới hạn của server!\n\n"
                                            f"📈 **Mã:** `{symbol}`\n"
                                            f"📊 **Số lượng lệnh:** `{shares:.2f}`\n"
                                            f"🎒 **Số lượng hiện có:** `{curr_shares:.2f}`\n"
                                            f"🚫 **Giới hạn tối đa:** `{limit_val:,}`\n\n"
                                            f"💰 Đã hoàn trả `+{locked_funds:,} VND` vào tài khoản."
                                        ),
                                        color=discord.Color.orange()
                                    )
                                    try: await user.send(embed=embed)
                                    except Exception: pass
                                continue

                            # Target price cost including target slippage and fee was locked
                            locked_funds = get_limit_buy_cost(shares, target_price, symbol)
                            
                            # Slippage & buy fee
                            liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
                            slippage_pct = (shares / liquidity) * 0.01
                            effective_curr_price = int(curr_price * (1 + slippage_pct))
                            actual_cost_base = int(shares * effective_curr_price)
                            buy_fee = int(actual_cost_base * 0.02)
                            actual_cost = actual_cost_base + buy_fee
                            
                            refund = locked_funds - actual_cost
                            self.economy.add_money(user_id, refund)
                            self.economy.set_portfolio_shares(user_id, symbol, curr_shares + shares)
                            
                            self.economy.remove_limit_order(order_id)
                            
                            user = self.client.get_user(user_id)
                            if user is None:
                                try: user = await self.client.fetch_user(user_id)
                                except Exception: pass
                            if user:
                                refund_str = f" và được hoàn trả `+{refund:,} VND` chênh lệch" if refund > 0 else f" và khấu trừ thêm `{abs(refund):,} VND` chênh lệch" if refund < 0 else ""
                                embed = make_embed(
                                    title="🔔 LỆNH MUA TỰ ĐỘNG KHỚP 🔔",
                                    description=(
                                        f"Lệnh mua tự động (Limit Order) của bạn đã khớp thành công!\n\n"
                                        f"📈 **Mã:** `{symbol}`\n"
                                        f"📊 **Số lượng:** `{shares:.2f}`\n"
                                        f"💵 **Giá thị trường:** `{curr_price:,} VND`\n"
                                        f"⚡ **Trượt giá:** `+{slippage_pct*100:.3f}%` (Giá khớp: `{effective_curr_price:,} VND`)\n"
                                        f"🏷️ **Phí mua (2%):** `{buy_fee:,} VND`\n"
                                        f"💰 Đã nhận `+{shares:.2f} {symbol}` vào tài khoản{refund_str}."
                                    ),
                                    color=discord.Color.green()
                                )
                                try: await user.send(embed=embed)
                                except Exception: pass
                        else:  # SELL
                            # Slippage & sell fee
                            liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
                            slippage_pct = (shares / liquidity) * 0.01
                            effective_curr_price = int(curr_price * (1 - slippage_pct))
                            effective_curr_price = max(int(curr_price * 0.1), effective_curr_price)
                            
                            base_payout = int(shares * effective_curr_price)
                            sell_fee = int(base_payout * 0.05)
                            payout = base_payout - sell_fee
                            
                            self.economy.add_money(user_id, payout)
                            self.economy.remove_limit_order(order_id)
                            
                            user = self.client.get_user(user_id)
                            if user is None:
                                try: user = await self.client.fetch_user(user_id)
                                except Exception: pass
                            if user:
                                embed = make_embed(
                                    title="🔔 LỆNH BÁN TỰ ĐỘNG KHỚP 🔔",
                                    description=(
                                        f"Lệnh bán tự động (Limit Order) của bạn đã khớp thành công!\n\n"
                                        f"📈 **Mã:** `{symbol}`\n"
                                        f"📊 **Số lượng:** `{shares:.2f}`\n"
                                        f"💵 **Giá thị trường:** `{curr_price:,} VND`\n"
                                        f"⚡ **Trượt giá:** `-{slippage_pct*100:.3f}%` (Giá khớp: `{effective_curr_price:,} VND`)\n"
                                        f"🏷️ **Phí bán (5%):** `{sell_fee:,} VND`\n"
                                        f"💰 Nhận về ví: `+{payout:,} VND`."
                                    ),
                                    color=discord.Color.green()
                                )
                                try: await user.send(embed=embed)
                                except Exception: pass
            except Exception as ex:
                logger.error(f"Error executing limit orders: {ex}")

            # --- 4. Manager Automatic Business Collect ---
            try:
                active_managers = self.economy.get_all_active_managers()
                for user_id, last_collect, manager_expiry in active_managers:
                    if now - last_collect >= 12 * 3600:
                        user = self.client.get_user(user_id)
                        if user is None:
                            try: user = await self.client.fetch_user(user_id)
                            except Exception: pass
                        if user:
                            embed = await self.process_collect(user)
                            # Customize title and description for auto-collect
                            embed.title = "💼 BÁO CÁO THU HOẠCH TỰ ĐỘNG CỦA QUẢN LÝ 💼"
                            embed.description = f"Quản lý của bạn đã tự động thu hoạch doanh nghiệp:\n\n{embed.description}"
                            try: await user.send(embed=embed)
                            except Exception: pass
            except Exception as ex:
                logger.error(f"Error in manager auto-collect: {ex}")

        except Exception as e:
            logger.error(f"Error updating stock prices: {e}")

    @commands.command(
        brief="Hiển thị profile sành điệu dạng banner của bạn.",
        usage="profile / pf",
        aliases=["pf"]
    )
    async def profile(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        if target.bot:
            await ctx.send("❌ Không thể xem profile của bot.")
            return

        async with ctx.typing():
            try:
                # Fetch data
                user_id = target.id
                profile_entry = self.economy.get_entry(user_id)
                money = profile_entry[1]
                gold = profile_entry[2]
                
                gold_price = self.economy.get_gold_price()
                loan_amount, _ = self.economy.get_loan(user_id)
                
                businesses = self.economy.get_businesses(user_id)
                biz_count = sum(lvl for biz, lvl in businesses)
                
                inventory = self.economy.get_inventory(user_id)
                inv_count = sum(qty for item, qty in inventory)
                
                # Fetch Rank Name
                from app.discord_bot.modules.profile_renderer import get_rank_info
                net_worth = money + (gold * gold_price) - loan_amount
                rank_name, _, _ = get_rank_info(net_worth)
                
                # Fetch Roulette Title
                from app.discord_bot.cogs.roulette import get_user_vip
                rl_stats = self.economy.get_roulette(user_id)
                rl_vip = get_user_vip(rl_stats)
                rl_title = rl_vip["title"]
                
                # Fetch Daga Title
                active_cock_row = self.economy.get_active_cock(user_id)
                if active_cock_row:
                    from app.discord_bot.cogs.daga import Cock
                    cock = Cock(active_cock_row)
                    daga_title = cock.get_title()
                else:
                    daga_title = "Chưa xuất trận 🌟"

                # Fetch Coin Flip Title
                from app.discord_bot.cogs.coinflip import get_user_vip as get_cf_vip
                cf_stats = self.economy.get_coinflip(user_id)
                cf_vip = get_cf_vip(cf_stats)
                cf_title = cf_vip["title"]

                # Render banner
                marriages = self.economy.get_marriages(user_id)
                if marriages:
                    from app.discord_bot.cogs.marry import render_couple_banner
                    marriage = marriages[0]
                    user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
                    
                    spouse_id = user_two if user_id == user_one else user_one
                    spouse = self.client.get_user(spouse_id)
                    if not spouse:
                        try:
                            spouse = await self.client.fetch_user(spouse_id)
                        except Exception:
                            pass
                    if not spouse:
                        class FallbackUser:
                            def __init__(self, uid):
                                self.id = uid
                                self.display_name = f"User_ID:{uid}"
                                self.display_avatar = self
                                self.url = "https://example.com/avatar.png"
                        spouse = FallbackUser(spouse_id)
                        
                    married_days = max(1, (int(time.time()) - married_at) // 86400)
                    ig_handles = self.economy.get_marriage_ig(user_one, user_two)
                    if user_id == user_one:
                        author_ig, spouse_ig = ig_handles[0], ig_handles[1]
                    else:
                        author_ig, spouse_ig = ig_handles[1], ig_handles[0]
                        
                    rel_status = self.economy.get_marriage_status(user_one, user_two)
                    saying = self.economy.get_marriage_saying(user_one, user_two)
                    
                    img_buffer = await asyncio.to_thread(
                        render_couple_banner,
                        target,
                        spouse,
                        ring_type,
                        love_points,
                        joint_wallet,
                        married_days,
                        author_ig,
                        spouse_ig,
                        rel_status,
                        married_at,
                        saying
                    )
                else:
                    equipped = self.economy.get_equipped_banner(user_id)
                    banner_path = None
                    if equipped and equipped in SHOP_ITEMS:
                        filename = SHOP_ITEMS[equipped].get("filename")
                        if filename:
                            banner_path = Path("pictures/banners") / filename
                    
                    avatar_url = target.display_avatar.with_format("png").url
                    img_buffer = await render_profile_banner(
                        username=target.name,
                        avatar_url=avatar_url,
                        money=money,
                        gold=gold,
                        gold_price=gold_price,
                        loan_amount=loan_amount,
                        biz_count=biz_count,
                        inv_count=inv_count,
                        banner_path=banner_path,
                        rl_title=rl_title,
                        daga_title=daga_title,
                        cf_title=cf_title
                    )
                
                is_gif = getattr(img_buffer, "is_gif", False)
                ext = "gif" if is_gif else "png"
                filename = f"profile-{user_id}-{uuid4().hex[:6]}.{ext}"
                file = discord.File(fp=img_buffer, filename=filename)
                
                # Render Showcase side-by-side companion image if exists
                active_cock = self.economy.get_active_cock(user_id)
                fav_car = self.economy.get_favorite_car(user_id)
                
                cock_info = None
                if active_cock:
                    cock_info = {
                        "name": active_cock[2],
                        "rarity": active_cock[3],
                        "level": active_cock[4],
                        "wins": active_cock[15],
                        "losses": active_cock[16],
                        "streak": active_cock[17],
                        "image_filename": get_cock_image_file(active_cock[2])
                    }
                    
                car_info = None
                if fav_car:
                    car_info = {
                        "model": fav_car[2],
                        "rarity": fav_car[3],
                        "serial": fav_car[4],
                        "edition": fav_car[5],
                        "collection": fav_car[6],
                        "image_filename": get_car_image_file(fav_car[2])
                    }
                    
                showcase_buffer = await render_showcase_image(cock_info, car_info)
                showcase_file = None
                showcase_embed = None
                
                if showcase_buffer:
                    showcase_filename = f"showcase-{user_id}-{uuid4().hex[:6]}.png"
                    showcase_file = discord.File(fp=showcase_buffer, filename=showcase_filename)
                    showcase_embed = make_embed(
                        title="🐓 BẠN ĐỒNG HÀNH & SIÊU XE TRƯNG BÀY 🏎️",
                        color=discord.Color.purple()
                    )
                    showcase_embed.set_image(url=f"attachment://{showcase_filename}")

                # Build embed with stats text below
                showcase_treasure_id = self.economy.get_showcase_treasure(user_id)
                showcase_treasure_text = "Chưa trưng bày"
                if showcase_treasure_id and showcase_treasure_id in TREASURES:
                    showcase_treasure_text = f"{TREASURES[showcase_treasure_id]['name']} (ID: `{showcase_treasure_id}`)"

                from app.discord_bot.modules.profile_renderer import strip_emoji
                display_rank = strip_emoji(rank_name)
                display_rl = strip_emoji(rl_title) if rl_title else ""
                display_daga = strip_emoji(daga_title) if daga_title else ""
                display_cf = strip_emoji(cf_title) if cf_title else ""

                desc = (
                    f"🎖️ **Danh hiệu:**\n"
                    f"• {display_rank}\n"
                    f"• {display_rl}\n"
                    f"• {display_daga}\n"
                    f"• {display_cf}\n\n"
                    f"💵 **Tài khoản:** `{money:,} VND`\n"
                    f"<:32100goldbarsfortnite:1514192020921651251> **Két sắt:** `{gold} Vàng` *(Tỷ giá Vàng: {gold_price:,} VND)*\n"
                    f"🏢 **Doanh nghiệp:** `{biz_count} Cơ sở`\n"
                    f"🎒 **Túi đồ:** `{inv_count} Vật phẩm`\n"
                    f"🏺 **Cổ vật trưng bày:** {showcase_treasure_text}\n"
                )
                if loan_amount > 0:
                    desc += f"🚨 **Khoản nợ hiện tại:** `-{loan_amount:,} VND`\n"
                    
                embed = make_embed(
                    title=f"💳 PROFILE CỦA {target.name.upper()}",
                    description=desc,
                    color=discord.Color.purple()
                )
                embed.set_image(url=f"attachment://{filename}")
                
                files = [file]
                embeds = [embed]
                if showcase_file and showcase_embed:
                    files.append(showcase_file)
                    embeds.append(showcase_embed)
                    
                await ctx.send(files=files, embeds=embeds)
                
                img_buffer.close()
                if showcase_buffer:
                    showcase_buffer.close()
            except Exception as e:
                logger.error(f"Failed to generate profile: {e}", exc_info=True)
                await ctx.send(f"❌ Có lỗi xảy ra khi tạo profile: {e}")

    @commands.command(
        brief="Trang bị hình nền profile từ kho đồ của bạn.",
        usage="setbanner / sb [banner_id / reset]",
        aliases=["sb"]
    )
    async def setbanner(self, ctx: commands.Context, banner_id: str | None = None):
        user_id = ctx.author.id
        
        # If no arguments, show their owned banners
        if not banner_id:
            inventory = self.economy.get_inventory(user_id)
            owned_banners = []
            
            equipped = self.economy.get_equipped_banner(user_id)
            
            for item_id, qty in inventory:
                if qty > 0 and item_id in SHOP_ITEMS and SHOP_ITEMS[item_id].get("is_banner"):
                    owned_banners.append((item_id, SHOP_ITEMS[item_id]["name"]))
                    
            if not owned_banners:
                await ctx.send(
                    "🎒 **Bạn chưa sở hữu banner nào!**\n"
                    "Hãy gõ `i?shop` để mua banner từ cửa hàng, sau đó gõ `i?setbanner <ID>` để trang bị."
                )
                return
                
            desc_lines = [
                "Sử dụng lệnh `i?setbanner <ID>` để trang bị hình nền cho profile của bạn.",
                "Để gỡ bỏ banner, gõ `i?setbanner reset`.\n",
                "**Danh sách banner bạn sở hữu:**"
            ]
            
            for bid, name in owned_banners:
                status = " 🟢 *[Đang trang bị]*" if bid == equipped else ""
                desc_lines.append(f"• ID: `{bid}` — **{name}**{status}")
                
            embed = make_embed(
                title=f"🎨 KHO BANNER CỦA {ctx.author.name.upper()}",
                description="\n".join(desc_lines),
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        # Handle reset
        if banner_id.lower() in ["reset", "default", "none"]:
            self.economy.set_equipped_banner(user_id, None)
            await ctx.send("✅ Đã đặt lại hình nền mặc định cho profile của bạn.")
            return

        # Handle equip
        if banner_id not in SHOP_ITEMS or not SHOP_ITEMS[banner_id].get("is_banner"):
            await ctx.send("❌ **Lỗi:** ID banner không tồn tại! Gõ `i?setbanner` (không kèm ID) để xem các banner bạn sở hữu.")
            return

        # Check ownership
        inventory = self.economy.get_inventory(user_id)
        has_banner = any(item == banner_id and qty > 0 for item, qty in inventory)
        if not has_banner:
            await ctx.send(f"❌ **Lỗi:** Bạn chưa sở hữu banner này! Hãy mua nó trong cửa hàng bằng lệnh `i?buyitem {banner_id}`.")
            return

        # Equip
        self.economy.set_equipped_banner(user_id, banner_id)
        await ctx.send(f"✅ Đã trang bị banner **{SHOP_ITEMS[banner_id]['name']}** cho profile của bạn!")

    @commands.command(
        brief="Xem cửa hàng bán bằng cấp và công cụ bổ trợ.",
        usage="shop"
    )
    async def shop(self, ctx: commands.Context):
        view = ShopView(ctx.author)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(
        brief="Mua một vật phẩm từ cửa hàng bằng ID.",
        usage="buyitem <item_id>"
    )
    async def buyitem(self, ctx: commands.Context, item_id: str):
        if item_id not in SHOP_ITEMS:
            await ctx.send(f"❌ Vật phẩm ID `{item_id}` không tồn tại. Gõ `i?shop` để xem danh sách.")
            return

        user_id = ctx.author.id
        item = SHOP_ITEMS[item_id]
        
        # Check if item is admin-only and user is not owner
        if item.get("is_admin_only") and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ **Lỗi:** Vật phẩm này chỉ dành cho Admin!")
            return
            
        # Check if it is a banner and they already own it
        if item.get("is_banner"):
            inventory = self.economy.get_inventory(user_id)
            if any(inv_item == item_id and qty > 0 for inv_item, qty in inventory):
                await ctx.send(f"❌ Bạn đã sở hữu banner này rồi! Không thể mua thêm.")
                return
        
        # Check current balance
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        gold = profile[2]
        
        if item['currency'] == "money":
            if money < item['cost']:
                await ctx.send(f"❌ Bạn không đủ tiền mặt! Cần `{item['cost']:,} VND` nhưng bạn chỉ có `{money:,} VND`.")
                return
            # Deduct VND
            self.economy.add_money(user_id, -item['cost'])
            log_wallet_change(logger, event="buy_shop_item", user_id=user_id, money_delta=-item['cost'], item_id=item_id, ctx=ctx)
        else:
            if gold < item['cost']:
                await ctx.send(f"❌ Bạn không đủ Vàng! Cần `{item['cost']}` thỏi vàng nhưng bạn chỉ có `{gold}` thỏi vàng.")
                return
            # Deduct gold
            self.economy.add_credits(user_id, -item['cost'])
            log_wallet_change(logger, event="buy_shop_item", user_id=user_id, credits_delta=-item['cost'], item_id=item_id, ctx=ctx)

        # Add item to inventory
        self.economy.add_inventory_item(user_id, item_id, 1)
        
        embed = make_embed(
            title="🎁 MUA HÀNG THÀNH CÔNG 🎁",
            description=f"Chúc mừng bạn đã sở hữu **{item['name']}**!\nĐã trừ thành công chi phí mua hàng.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


    @commands.command(
        brief="Sử dụng hợp đồng gia hạn (quản lý, bảo hiểm, vệ sĩ) từ túi đồ.",
        usage="use <item_id>",
        aliases=["sudung"]
    )
    async def use(self, ctx: commands.Context, item_id: str):
        item_id = item_id.lower().strip()
        valid_contracts = {
            "manager_contract": ("manager_expiry", "Hợp đồng Quản lý 7 ngày 💼", "quản lý doanh nghiệp tự động"),
            "insurance_contract": ("insurance_expiry", "Bảo hiểm Doanh nghiệp 7 ngày 🛡️", "phòng ngừa rủi ro doanh nghiệp"),
            "bodyguard_contract": ("bodyguard_expiry", "Hợp đồng Vệ sĩ 7 ngày 💂", "bảo vệ tài sản giảm tỷ lệ bị cướp")
        }
        
        if item_id not in valid_contracts:
            await ctx.send("❌ Vật phẩm này không thể kích hoạt/sử dụng bằng lệnh này. Các hợp đồng hợp lệ: `manager_contract`, `insurance_contract`, `bodyguard_contract`.")
            return
            
        user_id = ctx.author.id
        inventory = self.economy.get_inventory(user_id)
        owned_qty = next((qty for iid, qty in inventory if iid == item_id), 0)
        
        if owned_qty <= 0:
            await ctx.send(f"❌ Bạn không sở hữu **{SHOP_ITEMS[item_id]['name']}** trong túi đồ! Hãy dùng `i?buyitem {item_id}` để mua trước.")
            return
            
        # Deduct 1 item from inventory
        self.economy.add_inventory_item(user_id, item_id, -1)
        
        # Calculate new expiry
        now = int(time.time())
        upgrades = self.economy.get_upgrades(user_id)
        
        db_field, name, desc = valid_contracts[item_id]
        
        current_exp = 0
        if db_field == "manager_expiry":
            current_exp = upgrades[0]
        elif db_field == "insurance_expiry":
            current_exp = upgrades[1]
        elif db_field == "bodyguard_expiry":
            current_exp = upgrades[2]
            
        base_time = max(now, current_exp)
        new_expiry = base_time + 7 * 24 * 3600
        
        # Save to db
        kwargs = {db_field: new_expiry}
        self.economy.set_upgrades(user_id, **kwargs)
        
        from datetime import datetime
        expiry_date = datetime.fromtimestamp(new_expiry).strftime("%d/%m/%Y %H:%M:%S")
        
        embed = make_embed(
            title="⚡ KÍCH HOẠT HỢP ĐỒNG THÀNH CÔNG ⚡",
            description=(
                f"Bạn đã kích hoạt thành công **{name}**!\n\n"
                f"🔹 **Chức năng:** {desc}\n"
                f"⏳ **Hết hạn lúc:** `{expiry_date}`\n"
                f"🎒 **Số lượng còn lại trong túi:** `{owned_qty - 1}`"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Xem các vật phẩm bạn đang sở hữu trong túi đồ.",
        usage="inventory / inv",
        aliases=["inv"]
    )
    async def inventory(self, ctx: commands.Context):
        embed = self.get_inventory_embed(ctx.author)
        await ctx.send(embed=embed)


    @commands.command(
        brief="Bán cổ vật/kho báu thợ săn hoặc bằng cấp đã mua.",
        usage="sellitem <item_id> [số lượng]"
    )
    async def sellitem(self, ctx: commands.Context, item_id: str, quantity: int = 1):
        if quantity <= 0:
            await ctx.send("❌ **Lỗi:** Số lượng bán phải lớn hơn 0.")
            return

        user_id = ctx.author.id

        if item_id in SHOP_ITEMS:
            item = SHOP_ITEMS[item_id]
            if item.get("is_banner"):
                await ctx.send("❌ **Lỗi:** Không thể bán hình nền/banner profile!")
                return
            
            # Check ownership
            inventory = self.economy.get_inventory(user_id)
            owned_qty = next((qty for iid, qty in inventory if iid == item_id), 0)
            
            if owned_qty < quantity:
                await ctx.send(f"❌ **Lỗi:** Bạn không sở hữu đủ vật phẩm này! Bạn chỉ có **{owned_qty}** cái.")
                return

            # Deduct from inventory
            new_qty = self.economy.add_inventory_item(user_id, item_id, -quantity)
            
            # Calculate 75% refund
            refund_value = int(item["cost"] * 0.75) * quantity
            currency = item.get("currency", "money")
            
            if currency == "money":
                self.economy.add_money(user_id, refund_value)
                log_wallet_change(
                    logger,
                    event="sell_degree",
                    user_id=user_id,
                    money_delta=refund_value,
                    item_id=item_id,
                    quantity=quantity,
                    ctx=ctx
                )
                currency_name = "VND"
                balance_msg = f"💳 **Số dư VND hiện tại:** `{self.economy.get_entry(user_id)[1]:,} VND`"
            else: # gold
                self.economy.add_credits(user_id, refund_value)
                log_wallet_change(
                    logger,
                    event="sell_degree",
                    user_id=user_id,
                    credits_delta=refund_value,
                    item_id=item_id,
                    quantity=quantity,
                    ctx=ctx
                )
                currency_name = "thỏi vàng"
                balance_msg = f"<:32100goldbarsfortnite:1514192020921651251> **Số dư Vàng hiện tại:** `{self.economy.get_entry(user_id)[2]:,} thỏi vàng`"
                
            embed = make_embed(
                title="💰 BÁN BẰNG CẤP THÀNH CÔNG 💰",
                description=(
                    f"Bạn đã bán thành công **{quantity}x {item['name']}**!\n\n"
                    f"💵 **Giá bán lại mỗi chiếc (75%):** `{int(item['cost'] * 0.75):,} {currency_name}`\n"
                    f"💰 **Tổng tiền nhận lại:** `+{refund_value:,} {currency_name}`\n"
                    f"{balance_msg}"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        elif item_id in TREASURES:
            treasure = TREASURES[item_id]
            
            # Check ownership
            inventory = self.economy.get_inventory(user_id)
            owned_qty = next((qty for iid, qty in inventory if iid == item_id), 0)
            
            if owned_qty < quantity:
                await ctx.send(f"❌ **Lỗi:** Bạn không sở hữu đủ vật phẩm này! Bạn chỉ có **{owned_qty}** cái.")
                return

            # Deduct from inventory
            new_qty = self.economy.add_inventory_item(user_id, item_id, -quantity)
            
            # Clear showcase if item no longer owned
            if new_qty <= 0:
                showcase_id = self.economy.get_showcase_treasure(user_id)
                if showcase_id == item_id:
                    self.economy.set_showcase_treasure(user_id, None)
            
            # Add money
            total_value = treasure["value"] * quantity
            self.economy.add_money(user_id, total_value)
            
            log_wallet_change(
                logger,
                event="sell_treasure",
                user_id=user_id,
                money_delta=total_value,
                item_id=item_id,
                quantity=quantity,
                ctx=ctx
            )
            
            embed = make_embed(
                title="💰 BÁN CỔ VẬT THÀNH CÔNG 💰",
                description=(
                    f"Bạn đã bán **{quantity}x {treasure['name']}** cho bảo tàng thành phố!\n\n"
                    f"💵 **Giá bán mỗi chiếc:** `{treasure['value']:,} VND`\n"
                    f"💰 **Tổng tiền nhận:** `+{total_value:,} VND`\n"
                    f"💳 **Số dư VND hiện tại:** `{self.economy.get_entry(user_id)[1]:,} VND`"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        else:
            await ctx.send("❌ **Lỗi:** Vật phẩm này không thể bán hoặc không tồn tại! Chỉ có thể bán các cổ vật thợ săn đào được hoặc bằng cấp nghề nghiệp.")
            return

    @commands.command(
        brief="Triệu hồi nhân vật, mở hòm trang bị hoặc rương xe gacha.",
        usage="moruong",
        aliases=["mởruong", "open"]
    )
    async def moruong(self, ctx: commands.Context):
        view = ChestOpenView(self, ctx.author)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def process_chest_open(self, interaction: discord.Interaction, view: discord.ui.View, selected_option: str, quantity: int):
        user_id = interaction.user.id
        
        details = {
            "banner_thuong": ("🔮 Banner Thường", 1_000_000, "banner", "thuong"),
            "banner_xin": ("🔮 Banner Xịn", 5_000_000, "banner", "xin"),
            
            "box_garage": ("🏎️ Garage Box Xe", 100_000, "box", "1"),
            "box_premium": ("🏎️ Premium Box Xe", 1_000_000, "box", "2"),
            "box_luxury": ("🏎️ Luxury Box Xe", 10_000_000, "box", "3"),
        }
        
        name, price_per_one, item_type, tier_id = details[selected_option]
        total_price = price_per_one * quantity
        
        # Check money
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        if money < total_price:
            await interaction.response.send_message(
                f"❌ **Lỗi:** Bạn không đủ tiền! Cần `{total_price:,} VND` nhưng bạn chỉ có `{money:,} VND`.",
                ephemeral=True
            )
            return

        # Defer interaction first to acknowledge and allow editing with files
        await interaction.response.defer()

        # Deduct money
        self.economy.add_money(user_id, -total_price)
        log_wallet_change(logger, event="open_chest_menu", user_id=user_id, money_delta=-total_price, chest_type=selected_option, quantity=quantity)

        # Show opening animation
        anim_embed = make_embed(
            title="📦 ĐANG MỞ RƯƠNG... 📦",
            description=f"⏳ **{interaction.user.display_name}** đang mở **{quantity}x {name}** với tổng giá **{total_price:,} VNĐ**...\nHãy chờ xem bạn nhận được gì nhé! 🍀",
            color=discord.Color.gold()
        )
        
        gif_path = ABS_PATH / "modules" / "daga" / "open_chest.gif"
        if item_type == "banner":
            gif_path = ABS_PATH / "modules" / "daga" / "mo_trung.gif"

        file_gif = None
        if gif_path.exists():
            file_gif = discord.File(gif_path, filename=gif_path.name)
            anim_embed.set_image(url=f"attachment://{gif_path.name}")
        
        if file_gif:
            await interaction.message.edit(content=None, embed=anim_embed, view=None, attachments=[file_gif])
        else:
            await interaction.message.edit(content=None, embed=anim_embed, view=None, attachments=[])
        
        await asyncio.sleep(3)

        results = []
        if item_type == "banner":
            from app.discord_bot.cogs.daga import BREEDS, STAT_RANGES, get_cock_image_file
            rarity_emojis = {
                "Thường": "<:698204c:1515422780370190377>",
                "Hiếm": "<:759990b:1515423304620703905>",
                "Quý": "<:780661a:1515423318587609224>",
                "Sử Thi": "<:429893s:1515423348014715091>",
                "Huyền Thoại": "<:915638ss:1515423361310785536>",
                "Thần Kê": "<:886814sss:1515423524167225415>",
                "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
            }
            
            pity = self.economy.get_pity_golden(user_id)
            final_pity = pity

            for _ in range(quantity):
                # Roll secret SSS first
                r_secret = random.random() * 100
                is_secret_sss = False
                if tier_id == "thuong" and r_secret < 0.02:
                    is_secret_sss = True
                elif tier_id == "xin" and r_secret < 0.1:
                    is_secret_sss = True

                rarity = "Thường"
                is_reset_pity = False

                if is_secret_sss:
                    rarity = "Thần Kê"
                    if tier_id == "xin":
                        final_pity += 1
                else:
                    r = random.random() * 100
                    if tier_id == "thuong":
                        if r < 60.0:
                            rarity = "Thường"
                        elif r < 90.0:
                            rarity = "Hiếm"
                        elif r < 99.0:
                            rarity = "Quý"
                        elif r < 99.8:
                            rarity = "Sử Thi"
                        else:
                            rarity = "Huyền Thoại"
                    elif tier_id == "xin":
                        if final_pity >= 49:
                            rarity = "Huyền Thoại"
                            is_reset_pity = True
                        else:
                            if r < 40.0:
                                rarity = "Hiếm"
                            elif r < 85.0:
                                rarity = "Quý"
                            elif r < 97.0:
                                rarity = "Sử Thi"
                            else:
                                rarity = "Huyền Thoại"
                                is_reset_pity = True

                        if is_reset_pity:
                            final_pity = 0
                        else:
                            final_pity += 1

                breed = random.choice(BREEDS[rarity])
                ranges = STAT_RANGES[rarity]
                hp = random.randint(*ranges["hp"])
                atk = random.randint(*ranges["atk"])
                df = random.randint(*ranges["df"])
                spd = random.randint(*ranges["spd"])
                luk = random.randint(*ranges["luk"])
                
                cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
                    user_id, breed, rarity, hp, atk, df, spd, luk
                )
                results.append({
                    "id": cock_id,
                    "breed": breed,
                    "rarity": rarity,
                    "hp": final_stats["hp"],
                    "atk": final_stats["atk"],
                    "df": final_stats["df"],
                    "spd": final_stats["spd"],
                    "luk": final_stats["luk"],
                    "is_duplicate": is_duplicate,
                    "is_upgraded": is_upgraded,
                    "old_stars": old_stars,
                    "new_stars": new_stars,
                    "new_shards": new_shards
                })

            if tier_id == "xin":
                self.economy.set_pity_golden(user_id, final_pity)

            from app.discord_bot.cogs.daga import RARITY_DISPLAY
            # Build result message
            if quantity == 1:
                res = results[0]
                pity_str = f"\n🛡️ **Số lần tích bảo hiểm (Pity SS):** `{final_pity}/50`" if tier_id == "xin" else ""
                display_rarity = RARITY_DISPLAY.get(res['rarity'], res['rarity'])
                if res.get("is_duplicate"):
                    needed = res["new_stars"] + 1
                    if res["new_shards"] >= needed:
                        tip_msg = f"*(🎉 Đã tích đủ mảnh trùng! Hãy gõ `i?anime dotpha` để tiến hành đột phá!)*"
                    else:
                        tip_msg = f"*(Nhận thêm `{needed - res['new_shards']}` bản trùng nữa để lên {res['new_stars'] + 1} Sao)*"
                    desc = (
                        f"🔄 **BẠN NHẬN TRÙNG NHÂN VẬT!** (Tích luỹ mảnh)\n\n"
                        f"⚔️ **Nhân vật:** `{res['breed']}`\n"
                        f"⭐ **Độ hiếm:** {rarity_emojis[res['rarity']]} `{display_rarity}`\n"
                        f"📊 **Tiến trình đột phá:** `[ {res['new_shards']} / {needed} ]` mảnh trùng\n"
                        f"{tip_msg}"
                        f"{pity_str}"
                    )
                else:
                    desc = (
                        f"⚔️ **Nhân vật:** `{res['breed']}`\n"
                        f"⭐ **Độ hiếm:** {rarity_emojis[res['rarity']]} `{display_rarity}`\n"
                        f"❤️ **Máu (HP):** `{res['hp']}`\n"
                        f"⚔️ **Sát thương (ATK):** `{res['atk']}`\n"
                        f"🛡️ **Phòng thủ (DEF):** `{res['df']}`\n"
                        f"⚡ **Tốc độ (SPD):** `{res['spd']}`\n"
                        f"🍀 **May mắn (LUK):** `{res['luk']}`"
                        f"{pity_str}"
                    )
                embed = make_embed(
                    title="🔮 TRIỆU HỒI THÀNH CÔNG 🔮",
                    description=desc,
                    color=discord.Color.green(),
                )
                img_name = get_cock_image_file(res['breed'])
                file_img = None
                if img_name:
                    file_img = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
                    embed.set_thumbnail(url=f"attachment://{img_name}")
                
                if file_img:
                    await interaction.message.edit(embed=embed, view=view, attachments=[file_img])
                else:
                    await interaction.message.edit(embed=embed, view=view, attachments=[])
            else:
                list_str = ""
                for res in results:
                    emoji = rarity_emojis[res['rarity']]
                    display_rarity = RARITY_DISPLAY.get(res['rarity'], res['rarity'])
                    if res.get("is_duplicate"):
                        needed = res["new_stars"] + 1
                        if res["new_shards"] >= needed:
                            list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}` (Trùng - Đủ mảnh đột phá! 💥)\n"
                        else:
                            list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}` (Trùng - Mảnh: `{res['new_shards']}/{needed}`)\n"
                    else:
                        list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}`\n"
                
                pity_str = f"\n🛡️ **Bảo hiểm hiện tại (Pity SS):** `{final_pity}/50`" if tier_id == "xin" else ""
                embed = make_embed(
                    title=f"🔮 KẾT QUẢ TRIỆU HỒI {quantity} LƯỢT 🔮",
                    description=f"Chúc mừng bạn đã sở hữu thêm các nhân vật mới:\n\n{list_str}{pity_str}",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.message.edit(embed=embed, view=view, attachments=[])

        elif item_type == "box":
            from app.discord_bot.cogs.xe import BOX_DETAILS, CAR_RARITIES, CAR_EDITIONS, COLLECTIONS, RARITY_INFO, get_car_image_file, roll_rarity, CAR_QUOTES
            rarity_emojis = {
                "Common": "⚪", "Rare": "🟢", "Epic": "🔵", "Legendary": "🟣", "Mythic": "🟡", "Exclusive": "🔴"
            }
            
            box = BOX_DETAILS[tier_id]
            for _ in range(quantity):
                rarity = roll_rarity(box["rates"])
                
                models = [name for name, r_name in CAR_RARITIES.items() if r_name == rarity]
                model = random.choice(models)
                
                edition = "Stock"
                if model in CAR_EDITIONS:
                    if random.random() < 0.30:
                        edition = random.choice(CAR_EDITIONS[model][1:])
                
                col_name = "Other"
                for c_name, c_models in COLLECTIONS.items():
                    if model in c_models:
                        col_name = c_name
                        break
                
                serial = random.randint(1, 9999)
                self.economy.add_user_car(user_id, model, rarity, serial, edition, col_name)
                
                results.append({
                    "model": model,
                    "rarity": rarity,
                    "edition": edition,
                    "emoji": rarity_emojis[rarity]
                })

            if quantity == 1:
                res = results[0]
                desc = (
                    f"🏎️ **Xe:** **{res['model']}**\n"
                    f"⭐ **Độ hiếm:** {res['emoji']} `{res['rarity']}`\n"
                    f"✨ **Phiên bản:** `{res['edition']}`\n\n"
                    f"*\"{CAR_QUOTES.get(res['model'], 'Một chiếc xe tuyệt vời!')}\"*\n\n"
                    f"Đã được chuyển vào Garage của bạn (`i?xe garage`)!"
                )
                embed = make_embed(
                    title="🏎️ MỞ BOX XE THÀNH CÔNG 🏎️",
                    description=desc,
                    color=discord.Color.green(),
                )
                img_name = get_car_image_file(res['model'])
                file_img = None
                if img_name:
                    file_img = discord.File(ABS_PATH / "modules" / "duaxe" / img_name, filename=img_name)
                    embed.set_thumbnail(url=f"attachment://{img_name}")
                
                if file_img:
                    await interaction.message.edit(embed=embed, view=view, attachments=[file_img])
                else:
                    await interaction.message.edit(embed=embed, view=view, attachments=[])
            else:
                list_str = ""
                for res in results:
                    list_str += f"• {res['emoji']} **{res['model']}** ({res['rarity']}) - `{res['edition']}`\n"
                
                embed = make_embed(
                    title=f"🏎️ KẾT QUẢ MỞ {quantity} BOX XE 🏎️",
                    description=f"Chúc mừng bạn đã nhận được các xe sau:\n\n{list_str}",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.message.edit(embed=embed, view=view, attachments=[])

    @commands.command(
        brief="Xem và nâng cấp cuốc đào mỏ của bạn.",
        usage="pickaxe [upgrade]",
        aliases=["cuoc"]
    )
    async def pickaxe(self, ctx: commands.Context, action: str = None):
        user_id = ctx.author.id
        upgrades = self.economy.get_upgrades(user_id)
        pickaxe_level = upgrades[3]
        
        pickaxe_names = {
            0: ("Cuốc Gỗ 🪵", 5, 0),
            1: ("Cuốc Sắt ⚙️", 4, 10),
            2: ("Cuốc Vàng 🪙", 3, 20),
            3: ("Cuốc Kim Cương 💎", 2, 35)
        }
        
        curr_name, curr_cd, curr_bonus = pickaxe_names[pickaxe_level]
        
        upgrade_costs = {
            0: (10_000_000, "Cuốc Sắt ⚙️"),
            1: (30_000_000, "Cuốc Vàng 🪙"),
            2: (100_000_000, "Cuốc Kim Cương 💎")
        }
        
        if action and action.lower() in ["upgrade", "up", "nangcap"]:
            if pickaxe_level >= 3:
                await ctx.send("❌ Bạn đã đạt cấp độ cuốc tối đa (**Cuốc Kim Cương 💎**)!")
                return
                
            cost, next_name = upgrade_costs[pickaxe_level]
            profile = self.economy.get_entry(user_id)
            money = profile[1]
            
            if money < cost:
                await ctx.send(f"❌ Bạn không đủ tiền mặt! Nâng cấp lên **{next_name}** cần `{cost:,} VND` nhưng bạn chỉ có `{money:,} VND`.")
                return
                
            # Deduct money
            self.economy.add_money(user_id, -cost)
            self.economy.set_upgrades(user_id, pickaxe_level=pickaxe_level + 1)
            
            embed = make_embed(
                title="🔨 NÂNG CẤP CUỐC THÀNH CÔNG 🔨",
                description=(
                    f"Bạn đã nâng cấp thành công lên **{next_name}**!\n\n"
                    f"💸 **Chi phí:** `-{cost:,} VND`\n"
                    f"⏱️ **Thời gian chờ đào mỏ:** Giảm còn `{pickaxe_names[pickaxe_level + 1][1]} giờ`!\n"
                    f"✨ **Tỷ lệ đào trúng vàng:** Tăng thêm `+{pickaxe_names[pickaxe_level + 1][2]}%`!"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return
            
        # Show current pickaxe info
        embed = make_embed(
            title="⛏️ THÔNG TIN CUỐC ĐÀO MỎ ⛏️",
            description=(
                f"Bạn đang sở hữu: **{curr_name}**\n"
                f"⏱️ **Thời gian hồi:** `{curr_cd} giờ`\n"
                f"✨ **Tỷ lệ đào trúng vàng bổ sung:** `+{curr_bonus}%`"
            ),
            color=discord.Color.blue()
        )
        
        if pickaxe_level < 3:
            cost, next_name = upgrade_costs[pickaxe_level]
            embed.description += f"\n\n🛠️ **Nâng cấp tiếp theo:** **{next_name}**\n💵 **Chi phí nâng cấp:** `{cost:,} VND`\n💡 *Gõ lệnh `i?pickaxe upgrade` để nâng cấp.*"
        else:
            embed.description += "\n\n🎉 Bạn đã sở hữu cuốc huyền thoại mạnh nhất!"
            
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Đào mỏ khai thác khoáng sản (Yêu cầu Thẻ thợ mỏ VIP). Cooldown 5 tiếng.",
        usage="mine"
    )
    async def mine(self, ctx: commands.Context):
        embed = await self.process_mine(ctx.author, ctx)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Sử dụng Bản đồ Kho báu để thám hiểm hầm mộ cổ đại nhận cổ vật giá trị cao.",
        usage="explore <normal / rare / legend>",
        aliases=["thamhiem"]
    )
    async def explore(self, ctx: commands.Context, map_type: str):
        map_type = map_type.lower().strip()
        map_item_id = f"map_{map_type}"
        
        if map_item_id not in SHOP_ITEMS:
            await ctx.send("❌ Cấp độ bản đồ không hợp lệ! Vui lòng chọn: `normal` (thường), `rare` (hiếm), `legend` (huyền thoại).")
            return
            
        user_id = ctx.author.id
        inventory = self.economy.get_inventory(user_id)
        owned_qty = next((qty for iid, qty in inventory if iid == map_item_id), 0)
        
        if owned_qty <= 0:
            await ctx.send(f"❌ Bạn không sở hữu **{SHOP_ITEMS[map_item_id]['name']}**! Hãy dùng `i?buyitem {map_item_id}` để mua trong shop trước.")
            return
            
        # Deduct 1 map from inventory
        self.economy.add_inventory_item(user_id, map_item_id, -1)
        
        # Roll rarity based on map type
        r = random.random()
        if map_type == "normal":
            if r < 0.50: rarity = "Thường"
            elif r < 0.90: rarity = "Hiếm"
            elif r < 0.999: rarity = "Quý hiếm"
            else: rarity = "Huyền thoại"
        elif map_type == "rare":
            if r < 0.45: rarity = "Hiếm"
            elif r < 0.95: rarity = "Quý hiếm"
            elif r < 0.999: rarity = "Huyền thoại"
            else: rarity = "Thần thoại"
        else: # legend
            if r < 0.85: rarity = "Quý hiếm"
            elif r < 0.995: rarity = "Huyền thoại"
            else: rarity = "Thần thoại"
            
        # Select treasure
        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == rarity]
        chosen_id = random.choice(rarity_pool)
        treasure = TREASURES[chosen_id]
        
        # Add to inventory
        self.economy.add_inventory_item(user_id, chosen_id, 1)
        
        log_wallet_change(
            logger,
            event="map_exploration_success",
            user_id=user_id,
            item_id=chosen_id,
            quantity=1,
            ctx=ctx
        )
        
        map_name = SHOP_ITEMS[map_item_id]["name"]
        embed = make_embed(
            title="🏴‍☠️ CUỘC THÁM HIỂM KHO BÁU BẮT ĐẦU 🏴‍☠️",
            description=(
                f"Bạn đã sử dụng **{map_name}** để thâm nhập vào khu hầm mộ cổ đại bí ẩn...\n\n"
                f"🏺 **Phát hiện cổ vật:** {treasure['name']} (ID: `{chosen_id}`)\n"
                f"✨ **Độ hiếm:** `{treasure['rarity']}`\n"
                f"💰 **Giá trị ước tính:** `{treasure['value']:,} VND`\n\n"
                f"💡 *Bạn có thể trưng bày lên trang cá nhân hoặc dùng `i?sellitem {chosen_id}` để bán.*"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.group(
        brief="Hệ thống quản lý tài sản và kinh doanh thụ động.",
        usage="business / biz [mua/nangcap/id]",
        aliases=["biz"],
        invoke_without_command=True
    )
    async def business(self, ctx: commands.Context):
        embed = self.get_business_embed(ctx.author)
        await ctx.send(embed=embed)

    @business.command(name="buy", aliases=["mua", "upgrade", "up", "nangcap"])
    async def biz_buy(self, ctx: commands.Context, biz_id: str):
        if biz_id not in BUSINESSES:
            await ctx.send(f"❌ Doanh nghiệp ID `{biz_id}` không tồn tại. Các ID hợp lệ: `iot`, `gym`, `gold_shop`.")
            return

        user_id = ctx.author.id
        biz = BUSINESSES[biz_id]
        
        owned = dict(self.economy.get_businesses(user_id))
        current_lvl = owned.get(biz_id, 0)
        
        if current_lvl >= 10:
            await ctx.send(f"❌ Doanh nghiệp **{biz['name']}** của bạn đã đạt cấp độ tối đa (Cấp 10)!")
            return
            
        # Calculate cost
        cost = int(biz['base_cost'] * (1.5 ** current_lvl))
        
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        gold = profile[2]
        
        if biz['currency'] == "money":
            if money < cost:
                await ctx.send(f"❌ Bạn không đủ VND! Chi phí nâng cấp cấp {current_lvl + 1} là `{cost:,} VND`.")
                return
            self.economy.add_money(user_id, -cost)
            log_wallet_change(logger, event="buy_business", user_id=user_id, money_delta=-cost, biz_id=biz_id, ctx=ctx)
        else:
            if gold < cost:
                await ctx.send(f"❌ Bạn không đủ Vàng! Chi phí nâng cấp cấp {current_lvl + 1} là `{cost}` thỏi vàng.")
                return
            self.economy.add_credits(user_id, -cost)
            log_wallet_change(logger, event="buy_business", user_id=user_id, credits_delta=-cost, biz_id=biz_id, ctx=ctx)

        # Set level
        new_lvl = current_lvl + 1
        self.economy.set_business_level(user_id, biz_id, new_lvl)
        
        # If buying the first business ever, initialize last_collect
        stats = self.economy.get_simulator_stats(user_id)
        if stats[0] == 0:
            self.economy.set_simulator_stats(user_id, last_collect=int(time.time()))

        embed = make_embed(
            title="🏢 GIAO DỊCH DOANH NGHIỆP THÀNH CÔNG 🏢",
            description=f"Bạn đã nâng cấp thành công **{biz['name']}** lên **Cấp {new_lvl}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Thu hoạch doanh thu thụ động từ các doanh nghiệp của bạn.",
        usage="collect / thuhoach",
        aliases=["thuhoach"]
    )
    async def collect(self, ctx: commands.Context):
        embed = await self.process_collect(ctx.author, ctx)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Cướp tiền VND từ ví của người khác. Có tỷ lệ thất bại bị phạt tiền.",
        usage="rob @user"
    )
    async def rob(self, ctx: commands.Context, target: discord.Member):
        if target.bot:
            await ctx.send("❌ Không thể cướp tiền của bot!")
            return
        if target.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể tự cướp tiền của chính mình!")
            return
            
        # Check if target is admin or owner
        if target.id in config.bot.owner_ids or target.id in config.bot.admin_ids:
            await ctx.send("❌ **Đòi cướp tiền của bố, có cái quần què!!!**")
            return
            
        user_id = ctx.author.id
        now = int(time.time())
        cooldown = 2 * 3600 # 2 hours
        
        # Check robber cooldown
        stats = self.economy.get_simulator_stats(user_id)
        last_rob = stats[2]
        
        if now - last_rob < cooldown:
            time_left = cooldown - (now - last_rob)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            await ctx.send(f"⏳ **Cảnh sát đang tuần tra:** Bạn cần lẩn trốn thêm **{hours} giờ {minutes} phút** trước khi đi cướp tiếp.")
            return

        # Check target money
        target_profile = self.economy.get_entry(target.id)
        target_money = target_profile[1]
        
        if target_money < 50_000:
            await ctx.send(f"❌ **Mục tiêu quá nghèo:** {target.name} chỉ có `{target_money:,} VND` trong ví. Hãy để họ yên!")
            return

        # 40% success rate
        robber_profile = self.economy.get_entry(user_id)
        robber_money = robber_profile[1]
        
        # Check security alarm system (30% trigger chance)
        target_inventory = self.economy.get_inventory(target.id)
        has_security = any(item == 'security_system' and qty > 0 for item, qty in target_inventory)
        
        if has_security and random.random() < 0.30:
            # Alarm triggered! Robber is arrested and fined 10% of their cash (min 1M, max 10M)
            fine = max(1_000_000, min(10_000_000, int(robber_money * 0.10)))
            fine = min(robber_money, fine)
            fine = max(0, fine)
            
            if fine > 0:
                self.economy.add_money(user_id, -fine)
                self.economy.add_money(target.id, fine)
                
            self.economy.set_simulator_stats(user_id, last_rob=now)
            log_wallet_change(logger, event="rob_caught_by_security", user_id=user_id, money_delta=-fine, victim_id=target.id, ctx=ctx)
            
            embed = make_embed(
                title="🚨 CHUÔNG BÁO ĐỘNG KÍCH HOẠT: CƯỚP THẤT BẠI 🚨",
                description=(
                    f"Bạn vừa đột nhập vào thuộc tính của **{target.mention}** nhưng **Hệ thống Camera & Chuông báo động 🚨** của họ đã reo inh ỏi!\n\n"
                    f"👮 Cảnh sát lập tức có mặt bắt giữ bạn tại hiện trường!\n"
                    f"💸 **Bạn phải nộp phạt đền bù cho gia chủ:** `-{fine:,} VND`"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        # Check bodyguard active contract (reduces success rate from 40% to 8%)
        target_upgrades = self.economy.get_upgrades(target.id)
        bodyguard_active = target_upgrades[2] > now
        success_rate = 0.08 if bodyguard_active else 0.40

        if random.random() < success_rate:
            # Success: steal a random 1% to 5% of target's money
            steal_pct = random.uniform(0.01, 0.05)
            steal_amount = int(target_money * steal_pct)
            if target_money > 0:
                steal_amount = max(1, min(target_money, steal_amount))
            else:
                steal_amount = 0
            
            self.economy.add_money(target.id, -steal_amount)
            self.economy.add_money(user_id, steal_amount)
            self.economy.set_simulator_stats(user_id, last_rob=now)
            
            log_wallet_change(logger, event="rob_success", user_id=user_id, money_delta=steal_amount, victim_id=target.id, ctx=ctx)
            log_wallet_change(logger, event="rob_victim", user_id=target.id, money_delta=-steal_amount, actor_id=user_id, ctx=ctx)
            
            embed = make_embed(
                title="🥷 VỤ CƯỚP THÀNH CÔNG 🥷",
                description=(
                    f"Bạn đã áp sát **{target.mention}** và giật phăng ví tiền mặt thành công!\n\n"
                    f"💰 **Số tiền cướp được:** `+{steal_amount:,} VND`\n"
                    f"🛡️ *Mẹo: Hãy đổi VND sang Vàng gấp để tránh bị người khác cướp lại!*"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            # Failure: get caught and fined a random 1% to 5% of robber money
            fine_pct = random.uniform(0.01, 0.05)
            fine = int(robber_money * fine_pct)
            if robber_money > 0:
                fine = max(1, min(robber_money, fine))
            else:
                fine = 0
            
            if fine > 0:
                self.economy.add_money(user_id, -fine)
                self.economy.add_money(target.id, fine)
                
            self.economy.set_simulator_stats(user_id, last_rob=now)
            log_wallet_change(logger, event="rob_failed", user_id=user_id, money_delta=-fine, victim_id=target.id, ctx=ctx)
            
            fail_msg = f"Bạn đã bị cảnh sát tóm gọn hoặc bị **{target.name}** phản kháng dữ dội!"
            if bodyguard_active:
                fail_msg = f"**Vệ sĩ chuyên nghiệp 🛡️** bảo vệ **{target.name}** đã lập tức ngăn cản và đá bay bạn đi chỗ khác!"

            embed = make_embed(
                title="🚨 VỤ CƯỚP THẤT BẠI 🚨",
                description=(
                    f"{fail_msg}\n\n"
                    f"💸 **Bồi thường thiệt hại cho nạn nhân:** `-{fine:,} VND`"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.group(
        brief="Đầu tư cổ phiếu & tiền điện tử biến động.",
        usage="invest [list/buy/sell]",
        invoke_without_command=True
    )
    async def invest(self, ctx: commands.Context):
        view = InvestLobbyView(self, ctx.author)
        embed = self.get_invest_embed(ctx.author, view.selected_symbol)
        chart_file = self.get_stock_chart_file(view.selected_symbol)
        embed.set_image(url="attachment://chart.png")
        msg = await ctx.send(embed=embed, file=chart_file, view=view)
        view.message = msg

    @invest.command(name="buy", aliases=["mua"])
    async def invest_buy(self, ctx: commands.Context, symbol: str, shares: float):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `USDT`, `AGV`, `CASINO`, `ETH`, `BTC`, `SOL`, `DOGE`.")
            return
            
        if shares <= 0:
            await ctx.send("❌ Số lượng cổ phiếu mua phải lớn hơn 0.")
            return

        user_id = ctx.author.id
        price = prices[symbol]
        
        # Calculate slippage (Option C)
        liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
        slippage_pct = (shares / liquidity) * 0.01
        effective_price = int(price * (1 + slippage_pct))
        
        base_cost = int(shares * effective_price)
        # Calculate buy fee (2%)
        fee = int(base_cost * 0.02)
        total_cost = base_cost + fee
        
        # Check wallet money
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        
        if money < total_cost:
            await ctx.send(
                f"❌ Bạn không đủ tiền mặt!\n"
                f"• Mua `{shares:.2f}` {symbol} cần tổng cộng `{total_cost:,} VND` (gồm {slippage_pct*100:.3f}% trượt giá & 2% phí mua).\n"
                f"• Số dư ví hiện tại: `{money:,} VND`."
            )
            return
            
        portfolio = dict(self.economy.get_portfolio(user_id))
        current_shares = portfolio.get(symbol, 0.0)
        
        # Check max holding limit (Option B)
        limit_str = self.economy.get_setting(f"max_holding_{symbol}")
        if limit_str:
            try:
                limit_val = float(limit_str)
                if current_shares + shares > limit_val:
                    await ctx.send(
                        f"❌ **Lỗi:** Giao dịch bị từ chối do vượt quá giới hạn sở hữu tối đa của server!\n"
                        f"• Giới hạn sở hữu `{symbol}`: `{limit_val:,}` cổ\n"
                        f"• Bạn đang có: `{current_shares:.2f}` cổ\n"
                        f"• Có thể mua thêm tối đa: `{max(0.0, limit_val - current_shares):.2f}` cổ."
                    )
                    return
            except ValueError:
                pass

        # Process transaction
        self.economy.add_money(user_id, -total_cost)
        self.economy.set_portfolio_shares(user_id, symbol, current_shares + shares)
        
        log_wallet_change(
            logger,
            event="invest_buy_shares",
            user_id=user_id,
            money_delta=-total_cost,
            symbol=symbol,
            shares_bought=shares,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🟢 ĐẦU TƯ THÀNH CÔNG 🟢",
            description=(
                f"Bạn đã khớp lệnh mua thành công **{shares:.2f} {symbol}**!\n\n"
                f"💵 **Giá thị trường:** `{price:,} VND`\n"
                f"📊 **Trượt giá:** `+{slippage_pct*100:.3f}%` (Giá thực nhận: `{effective_price:,} VND`)\n"
                f"🏷️ **Phí mua (2%):** `{fee:,} VND`\n"
                f"💸 **Tổng chi phí:** `-{total_cost:,} VND`\n\n"
                f"🎒 **Số dư cổ phiếu hiện tại:** `{current_shares + shares:.2f} {symbol}`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invest.command(name="sell", aliases=["ban"])
    async def invest_sell(self, ctx: commands.Context, symbol: str, shares: float):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `USDT`, `AGV`, `CASINO`, `ETH`, `BTC`, `SOL`, `DOGE`.")
            return
            
        if shares <= 0:
            await ctx.send("❌ Số lượng cổ phiếu bán phải lớn hơn 0.")
            return

        user_id = ctx.author.id
        portfolio = dict(self.economy.get_portfolio(user_id))
        current_shares = portfolio.get(symbol, 0.0)
        
        if current_shares < shares:
            await ctx.send(f"❌ Bạn không đủ cổ phiếu để bán! Bạn chỉ có `{current_shares:.2f} {symbol}`.")
            return
            
        # Process transaction
        price = prices[symbol]
        
        # Calculate slippage (Option C)
        liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
        slippage_pct = (shares / liquidity) * 0.01
        effective_price = int(price * (1 - slippage_pct))
        effective_price = max(int(price * 0.1), effective_price) # Không trượt quá 90%
        
        base_payout = int(shares * effective_price)
        # Calculate sell fee (5%)
        fee = int(base_payout * 0.05)
        total_payout = base_payout - fee
        
        self.economy.set_portfolio_shares(user_id, symbol, current_shares - shares)
        self.economy.add_money(user_id, total_payout)
        
        log_wallet_change(
            logger,
            event="invest_sell_shares",
            user_id=user_id,
            money_delta=total_payout,
            symbol=symbol,
            shares_sold=shares,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🔴 BÁN ĐẦU TƯ THÀNH CÔNG 🔴",
            description=(
                f"Bạn đã bán thành công **{shares:.2f} {symbol}**!\n\n"
                f"💵 **Giá thị trường:** `{price:,} VND`\n"
                f"📊 **Trượt giá:** `-{slippage_pct*100:.3f}%` (Giá thực nhận: `{effective_price:,} VND`)\n"
                f"🏷️ **Phí bán (5%):** `{fee:,} VND`\n"
                f"💰 **Thực nhận về ví:** `+{total_payout:,} VND`\n\n"
                f"🎒 **Số dư cổ phiếu còn lại:** `{current_shares - shares:.2f} {symbol}`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invest.group(name="limit", brief="Quản lý lệnh mua/bán tự động (Limit Orders).", invoke_without_command=True)
    async def invest_limit(self, ctx: commands.Context):
        await ctx.send("❌ Vui lòng sử dụng các lệnh: `i?invest limit buy`, `i?invest limit sell`, `i?invest limit list`, `i?invest limit cancel`.")

    @invest_limit.command(name="buy", aliases=["mua"])
    async def invest_limit_buy(self, ctx: commands.Context, symbol: str, shares: float, target_price: int):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `USDT`, `AGV`, `CASINO`, `ETH`, `BTC`, `SOL`, `DOGE`.")
            return
            
        if shares <= 0 or target_price <= 0:
            await ctx.send("❌ Số lượng cổ phiếu và giá mục tiêu phải lớn hơn 0.")
            return
            
        user_id = ctx.author.id
        total_cost = get_limit_buy_cost(shares, target_price, symbol)
        
        # Check wallet money
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        
        if money < total_cost:
            liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
            slippage_pct = (shares / liquidity) * 0.01
            await ctx.send(
                f"❌ Bạn không đủ VND để đặt lệnh mua này!\n"
                f"• Cần tạm khóa: `{total_cost:,} VND` (bao gồm 2% phí mua & {slippage_pct*100:.3f}% trượt giá ước tính ở target price).\n"
                f"• Bạn chỉ có: `{money:,} VND`."
            )
            return
            
        portfolio = dict(self.economy.get_portfolio(user_id))
        current_shares = portfolio.get(symbol, 0.0)
        
        # Check max holding limit (Option B)
        limit_str = self.economy.get_setting(f"max_holding_{symbol}")
        if limit_str:
            try:
                limit_val = float(limit_str)
                if current_shares + shares > limit_val:
                    await ctx.send(
                        f"❌ **Lỗi:** Lệnh mua tự động bị từ chối do tổng số lượng sở hữu sau khi mua sẽ vượt quá giới hạn của server!\n"
                        f"• Giới hạn sở hữu `{symbol}`: `{limit_val:,}` cổ\n"
                        f"• Bạn đang có: `{current_shares:.2f}` cổ\n"
                        f"• Số lượng mua dự kiến: `{shares:.2f}` cổ."
                    )
                    return
            except ValueError:
                pass

        # Lock VND
        self.economy.add_money(user_id, -total_cost)
        order_id = self.economy.add_limit_order(user_id, symbol, "BUY", target_price, shares)
        
        liquidity = LIQUIDITY_VOLUME.get(symbol, 10000.0)
        slippage_pct = (shares / liquidity) * 0.01
        embed = make_embed(
            title="🟢 ĐẶT LỆNH MUA TỰ ĐỘNG THÀNH CÔNG 🟢",
            description=(
                f"Đã đặt thành công lệnh mua tự động (Limit Buy) **#{order_id}**!\n\n"
                f"📈 **Mã:** `{symbol}`\n"
                f"📊 **Số lượng:** `{shares:.2f}`\n"
                f"💵 **Giá mục tiêu:** `<= {target_price:,} VND` / cổ\n"
                f"🔒 **Tiền mặt bị khóa:** `-{total_cost:,} VND` (Đã gồm 2% phí & {slippage_pct*100:.3f}% trượt giá. Sẽ hoàn lại chênh lệch khi khớp lệnh hoặc trả lại khi hủy lệnh)\n"
                f"💡 *Lệnh sẽ tự động khớp khi giá thị trường giảm về dưới hoặc bằng giá mục tiêu.*"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invest_limit.command(name="sell", aliases=["ban"])
    async def invest_limit_sell(self, ctx: commands.Context, symbol: str, shares: float, target_price: int):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `USDT`, `AGV`, `CASINO`, `ETH`, `BTC`, `SOL`, `DOGE`.")
            return
            
        if shares <= 0 or target_price <= 0:
            await ctx.send("❌ Số lượng cổ phiếu và giá mục tiêu phải lớn hơn 0.")
            return
            
        user_id = ctx.author.id
        portfolio = dict(self.economy.get_portfolio(user_id))
        curr_shares = portfolio.get(symbol, 0.0)
        
        if curr_shares < shares:
            await ctx.send(f"❌ Bạn không đủ cổ phiếu để đặt lệnh bán! Bạn chỉ có `{curr_shares:.2f} {symbol}`.")
            return
            
        # Lock shares
        self.economy.set_portfolio_shares(user_id, symbol, curr_shares - shares)
        order_id = self.economy.add_limit_order(user_id, symbol, "SELL", target_price, shares)
        
        embed = make_embed(
            title="🔴 ĐẶT LỆNH BÁN TỰ ĐỘNG THÀNH CÔNG 🔴",
            description=(
                f"Đã đặt thành công lệnh bán tự động (Limit Sell) **#{order_id}**!\n\n"
                f"📈 **Mã:** `{symbol}`\n"
                f"📊 **Số lượng:** `{shares:.2f}`\n"
                f"💵 **Giá mục tiêu:** `>= {target_price:,} VND` / cổ\n"
                f"🔒 **Cổ phiếu bị khóa:** `-{shares:.2f} {symbol}` (Sẽ hoàn trả lại nếu hủy lệnh)\n"
                f"💡 *Lệnh sẽ tự động khớp khi giá thị trường tăng lên bằng hoặc cao hơn giá mục tiêu.*"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invest_limit.command(name="list", aliases=["danhsach"])
    async def invest_limit_list(self, ctx: commands.Context):
        user_id = ctx.author.id
        orders = self.economy.get_limit_orders(user_id)
        
        if not orders:
            embed = make_embed(
                title="📋 DANH SÁCH LỆNH TỰ ĐỘNG 📋",
                description="Bạn hiện không có lệnh giới hạn (Limit Order) nào đang hoạt động.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
            
        embed = make_embed(
            title="📋 DANH SÁCH LỆNH TỰ ĐỘNG 📋",
            color=discord.Color.blue()
        )
        
        for oid, symbol, otype, target, shares, created in orders:
            type_str = "🟢 MUA" if otype == "BUY" else "🔴 BÁN"
            lock_asset = f"{get_limit_buy_cost(shares, target, symbol):,} VND" if otype == "BUY" else f"{shares:.2f} {symbol}"
            embed.add_field(
                name=f"Lệnh #{oid} | {type_str} {symbol}",
                value=(
                    f"• Số lượng: **{shares:.2f}**\n"
                    f"• Giá mục tiêu: **{target:,} VND**\n"
                    f"• Đang khóa: `{lock_asset}`"
                ),
                inline=False
            )
        await ctx.send(embed=embed)

    @invest_limit.command(name="cancel", aliases=["huy"])
    async def invest_limit_cancel(self, ctx: commands.Context, order_id: int):
        user_id = ctx.author.id
        order = self.economy.get_limit_order(order_id)
        
        if not order:
            await ctx.send(f"❌ Lệnh tự động **#{order_id}** không tồn tại.")
            return
            
        if order[1] != user_id:
            await ctx.send("❌ Bạn không thể hủy lệnh của người khác!")
            return
            
        _, _, symbol, order_type, target_price, shares, _ = order
        
        # Refund locked asset
        if order_type == "BUY":
            refund_money = get_limit_buy_cost(shares, target_price, symbol)
            self.economy.add_money(user_id, refund_money)
            refund_msg = f"Đã hoàn lại `+{refund_money:,} VND` vào ví của bạn."
        else: # SELL
            portfolio = dict(self.economy.get_portfolio(user_id))
            curr_shares = portfolio.get(symbol, 0.0)
            self.economy.set_portfolio_shares(user_id, symbol, curr_shares + shares)
            refund_msg = f"Đã trả lại `+{shares:.2f} {symbol}` vào kho của bạn."
            
        self.economy.remove_limit_order(order_id)
        
        embed = make_embed(
            title="❌ HỦY LỆNH TỰ ĐỘNG THÀNH CÔNG ❌",
            description=f"Đã hủy thành công lệnh giới hạn **#{order_id}**!\n{refund_msg}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @invest.command(name="max", brief="Xem hoặc cấu hình giới hạn sở hữu tối đa của các mã.")
    async def invest_max(self, ctx: commands.Context, symbol: str = None, amount: str = None):
        if not symbol:
            prices = self.economy.get_stock_prices()
            desc = ""
            for sym, _, _, _ in prices:
                limit_str = self.economy.get_setting(f"max_holding_{sym}")
                limit_val = f"`{float(limit_str):,}` cổ" if limit_str else "**Vô hạn**"
                desc += f"• **{sym}**: {limit_val}\n"
                
            embed = make_embed(
                title="⚙️ GIỚI HẠN SỞ HỮU TỐI ĐA CỦA CÁC MÃ ⚙️",
                description=f"Dưới đây là giới hạn số lượng nắm giữ tối đa hiện tại của từng mã đầu tư:\n\n{desc}\n💡 *Quản trị viên có thể thay đổi bằng lệnh: `i?invest max <ticker> <số lượng>`*",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `USDT`, `AGV`, `CASINO`, `ETH`, `BTC`, `SOL`, `DOGE`.")
            return
            
        # Check permissions: bot owner or guild administrator
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        is_owner = ctx.author.id in config.bot.owner_ids or await ctx.bot.is_owner(ctx.author)
        if not (is_admin or is_owner):
            await ctx.send("❌ **Lỗi:** Chỉ có quản trị viên hoặc chủ sở hữu bot mới có quyền cấu hình giới hạn này.")
            return
            
        if amount is None or amount.lower() in ["reset", "none", "unlimited", "vô hạn"]:
            self.economy.set_setting(f"max_holding_{symbol}", "")
            await ctx.send(f"✅ Đã đặt lại giới hạn sở hữu mã `{symbol}` thành **Vô hạn**.")
            return
            
        try:
            val = float(amount)
            if val <= 0:
                self.economy.set_setting(f"max_holding_{symbol}", "")
                await ctx.send(f"✅ Đã đặt lại giới hạn sở hữu mã `{symbol}` thành **Vô hạn**.")
                return
        except ValueError:
            await ctx.send("❌ Số lượng giới hạn không hợp lệ. Vui lòng nhập số dương hoặc `reset`.")
            return
            
        self.economy.set_setting(f"max_holding_{symbol}", str(val))
        
        embed = make_embed(
            title="⚙️ CẤU HÌNH GIỚI HẠN ĐẦU TƯ ⚙️",
            description=(
                f"Đã cập nhật giới hạn sở hữu tối đa thành công!\n\n"
                f"📈 **Mã:** `{symbol}`\n"
                f"🔒 **Giới hạn tối đa mỗi người:** `{val:,}` cổ phiếu\n\n"
                f"💡 *Người chơi sẽ không thể mua thêm nếu số lượng nắm giữ hiện tại + số lượng mua vượt quá mức này.*"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.command(
        brief="Trưng bày cổ vật/kho báu lên trang cá nhân của bạn.",
        usage="trungbay [item_id hoặc 'huy']",
        aliases=["showcase"]
    )
    async def trungbay(self, ctx: commands.Context, item_id: str = None):
        user_id = ctx.author.id
        
        if not item_id:
            # Show current showcased treasure
            current = self.economy.get_showcase_treasure(user_id)
            if not current or current not in TREASURES:
                await ctx.send("🏺 Hiện tại bạn **chưa trưng bày** cổ vật nào. Dùng lệnh `i?trungbay <item_id>` để chọn vật phẩm trưng bày.")
            else:
                treasure = TREASURES[current]
                await ctx.send(f"🏺 Cổ vật đang trưng bày của bạn: **{treasure['name']}** (ID: `{current}`).\nDùng lệnh `i?trungbay huy` để hủy trưng bày.")
            return

        if item_id.lower() in ["huy", "remove", "cancel", "clear"]:
            self.economy.set_showcase_treasure(user_id, None)
            await ctx.send("✅ Đã hủy trưng bày cổ vật trên trang cá nhân.")
            return

        if item_id not in TREASURES:
            await ctx.send("❌ **Lỗi:** Vật phẩm này không phải là cổ vật hợp lệ để trưng bày! Ví dụ: `t_bat_gom`.")
            return

        # Check ownership
        inventory = self.economy.get_inventory(user_id)
        owned_qty = next((qty for iid, qty in inventory if iid == item_id), 0)
        
        if owned_qty <= 0:
            await ctx.send(f"❌ **Lỗi:** Bạn không sở hữu cổ vật này trong túi đồ để trưng bày!")
            return

        # Set showcase
        self.economy.set_showcase_treasure(user_id, item_id)
        treasure = TREASURES[item_id]
        
        embed = make_embed(
            title="🏺 TRƯNG BÀY CỔ VẬT THÀNH CÔNG 🏺",
            description=(
                f"Bạn đã chọn trưng bày **{treasure['name']}** lên trang cá nhân!\n\n"
                f"✨ **Độ hiếm:** `{treasure['rarity']}`\n"
                f"💰 **Giá trị cổ vật:** `{treasure['value']:,} VND`\n\n"
                f"👉 Cổ vật này sẽ được hiển thị khi người khác gõ lệnh `i?profile` của bạn."
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="[ADMIN] Xem cửa hàng banner độc quyền dành cho Admin.",
        usage="adminshop",
        hidden=True
    )
    @commands.is_owner()
    async def adminshop(self, ctx: commands.Context):
        embed = make_embed(
            title="👑 CỬA HÀNG BANNER ĐỘC QUYỀN (ADMIN ONLY) 👑",
            description="Danh sách các banner đặc biệt dành riêng cho admin. Dùng lệnh give/set banner cho người khác.",
            color=discord.Color.red()
        )
        for item_id, details in SHOP_ITEMS.items():
            if details.get("is_banner") and details.get("is_admin_only"):
                cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
                embed.add_field(
                    name=f"🖼️ {details['name']} (ID: `{item_id}`)",
                    value=f"💵 **Giá tham khảo:** `{cost_str}`\n📝 **Mô tả:** {details['description']}\n📁 **Tên file:** `{details['filename']}`",
                    inline=False
                )
        embed.set_footer(text="Sử dụng i?givebanner <member> <banner_id> hoặc i?setbannerother <member> <banner_id>")
        await ctx.send(embed=embed)

    @commands.command(
        name="givebanner",
        brief="[ADMIN] Tặng banner cho người chơi khác.",
        usage="givebanner <member> <banner_id>",
        hidden=True
    )
    @commands.is_owner()
    async def give_banner(self, ctx: commands.Context, member: discord.Member, banner_id: str):
        if banner_id not in SHOP_ITEMS or not SHOP_ITEMS[banner_id].get("is_banner"):
            await ctx.send("❌ **Lỗi:** ID banner không tồn tại hoặc không phải là banner!")
            return

        # Add to user inventory
        self.economy.add_inventory_item(member.id, banner_id, 1)
        
        embed = make_embed(
            title="🎁 TẶNG BANNER THÀNH CÔNG 🎁",
            description=f"Admin đã tặng banner **{SHOP_ITEMS[banner_id]['name']}** cho **{member.mention}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        name="setbannerother",
        aliases=["sbo", "setbannerfor", "sbf"],
        brief="[ADMIN] Trang bị banner trực tiếp cho người chơi khác.",
        usage="setbannerother <member> <banner_id / reset>",
        hidden=True
    )
    @commands.is_owner()
    async def set_banner_other(self, ctx: commands.Context, member: discord.Member, banner_id: str):
        if banner_id.lower() in ["reset", "default", "none"]:
            self.economy.set_equipped_banner(member.id, None)
            await ctx.send(f"✅ Đã đặt lại hình nền mặc định cho profile của **{member.display_name}**.")
            return

        if banner_id not in SHOP_ITEMS or not SHOP_ITEMS[banner_id].get("is_banner"):
            await ctx.send("❌ **Lỗi:** ID banner không tồn tại hoặc không phải là banner!")
            return

        # Add banner to their inventory if they don't already own it
        inventory = self.economy.get_inventory(member.id)
        has_banner = any(item == banner_id and qty > 0 for item, qty in inventory)
        if not has_banner:
            self.economy.add_inventory_item(member.id, banner_id, 1)

        # Equip
        self.economy.set_equipped_banner(member.id, banner_id)
        
        embed = make_embed(
            title="🎨 TRANG BỊ BANNER THÀNH CÔNG 🎨",
            description=f"Đã trang bị banner **{SHOP_ITEMS[banner_id]['name']}** cho profile của **{member.mention}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        name="setbetlimit",
        brief="Đặt giới hạn cược tối thiểu và tối đa cho các trò chơi cờ bạc (Chỉ Admin/Owner).",
        usage="setbetlimit [min] [max]",
        aliases=["betlimit", "setlimit"]
    )
    async def setbetlimit(self, ctx: commands.Context, min_bet: str = None, max_bet: str = None):
        # Check permissions
        if ctx.author.id not in config.bot.owner_ids and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ **Lỗi:** Chỉ có Admin/Owner mới có quyền sử dụng lệnh này!")
            return
            
        if min_bet is None and max_bet is None:
            # Display current configuration
            global_min = self.economy.get_setting("global_min_bet")
            global_max = self.economy.get_setting("global_max_bet")
            
            min_str = f"{int(global_min):,} VND" if global_min else "Không giới hạn"
            max_str = f"{int(global_max):,} VND" if global_max else "Không giới hạn"
            
            embed = make_embed(
                title="⚙️ GIỚI HẠN CƯỢC CỜ BẠC HIỆN TẠI ⚙️",
                description=(
                    f"💰 **Giới hạn cược tối thiểu (Min):** `{min_str}`\n"
                    f"💰 **Giới hạn cược tối đa (Max):** `{max_str}`\n\n"
                    f"💡 *Sử dụng cú pháp sau để cấu hình:* `i?setbetlimit <min> <max>`\n"
                    f"💡 *Để xóa giới hạn, ví dụ:* `i?setbetlimit clear clear` hoặc `i?setbetlimit 0 0`"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        # Helper to parse amount
        def parse_limit_val(val_str: str) -> int | None | str:
            val_str = val_str.lower().strip()
            if val_str in ["clear", "reset", "none", "0", "null", "không", "khong"]:
                return None
            multiplier = 1
            if val_str.endswith("k"):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith("m"):
                multiplier = 1000000
                val_str = val_str[:-1]
            try:
                # Remove commas
                val_str = val_str.replace(",", "")
                return int(float(val_str) * multiplier)
            except ValueError:
                return "invalid"

        min_val = parse_limit_val(min_bet)
        max_val = None
        if max_bet is not None:
            max_val = parse_limit_val(max_bet)
            
        if min_val == "invalid" or max_val == "invalid":
            await ctx.send("❌ **Lỗi:** Số tiền giới hạn không hợp lệ. Ví dụ hợp lệ: `10k`, `500k`, `1m` hoặc `clear`.")
            return

        if min_val is not None and max_val is not None and min_val > max_val:
            await ctx.send("❌ **Lỗi:** Giới hạn cược tối thiểu không được phép lớn hơn giới hạn tối đa!")
            return

        # Save to database
        self.economy.set_setting("global_min_bet", str(min_val) if min_val is not None else "")
        self.economy.set_setting("global_max_bet", str(max_val) if max_val is not None else "")

        min_str = f"{min_val:,} VND" if min_val is not None else "Không giới hạn"
        max_str = f"{max_val:,} VND" if max_val is not None else "Không giới hạn"

        embed = make_embed(
            title="⚙️ CẬP NHẬT GIỚI HẠN CƯỢC THÀNH CÔNG ⚙️",
            description=(
                f"Đã cập nhật giới hạn cược thành công cho toàn bộ các trò chơi!\n\n"
                f"💰 **Giới hạn cược tối thiểu (Min):** `{min_str}`\n"
                f"💰 **Giới hạn cược tối đa (Max):** `{max_str}`"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    def get_stock_chart_file(self, symbol: str) -> discord.File:
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        current_price = prices.get(symbol, 1000)
        
        history_rows = self.economy.get_stock_price_history(symbol, limit=15)
        history = [row[0] for row in history_rows]
        
        # Fallback if history is insufficient (generate fake walk backwards)
        if len(history) < 15:
            import random
            prices_list = [current_price]
            # Generate backwards
            for _ in range(15 - len(history)):
                change = random.uniform(-0.05, 0.05)
                prev_price = int(prices_list[-1] / (1 + change))
                prices_list.append(prev_price)
            history = list(reversed(prices_list))
            
        from app.discord_bot.modules.chart_renderer import draw_candlestick_chart
        buf = draw_candlestick_chart(symbol, history, current_price)
        return discord.File(buf, filename="chart.png")

async def setup(client: commands.Bot):
    await client.add_cog(Simulator(client))
