import asyncio
import logging
import random
import time
import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# --- METADATA CONFIGURATION ---

RARITY_INFO = {
    "Common": {"emoji": "⚪", "color": discord.Color.light_grey(), "value": 500_000},
    "Rare": {"emoji": "🟢", "color": discord.Color.green(), "value": 2_000_000},
    "Epic": {"emoji": "🔵", "color": discord.Color.blue(), "value": 10_000_000},
    "Legendary": {"emoji": "🟣", "color": discord.Color.purple(), "value": 30_000_000},
    "Mythic": {"emoji": "🟡", "color": discord.Color.gold(), "value": 100_000_000},
    "Exclusive": {"emoji": "🔴", "color": discord.Color.red(), "value": 500_000_000}
}

COLLECTIONS = {
    "Vietnam": [
        "Honda Wave Alpha", "Honda Dream II", "Honda Cub 81", "Honda Future",
        "Yamaha Sirius", "Yamaha Jupiter", "Honda Air Blade", "Honda Vision",
        "Yamaha Exciter 150", "Yamaha Exciter 155", "Honda Winner X",
        "Honda SH125i", "Honda SH350i", "Suzuki Raider", "Suzuki Satria"
    ],
    "JDM": [
        "Toyota AE86", "Toyota Supra MK4", "Mazda 3", "Nissan Skyline R34",
        "Nissan GTR R35", "Honda NSX", "Nissan Silvia S15", "Hyundai Elantra",
        "Mitsubishi Outlander"
    ],
    "Super Bike": [
        "Kawasaki ZX4R", "Kawasaki ZX6R", "Kawasaki H2", "Kawasaki H2R",
        "Suzuki Hayabusa", "Honda CBR650R", "BMW S1000RR", "Ducati Panigale V4",
        "Yamaha MT09", "Kawasaki Z900"
    ],
    "Hypercar": [
        "Ferrari LaFerrari", "Ferrari SF90 Stradale", "Lamborghini", "Aston Martin",
        "Chevrolet Corvette", "Bugatti Chiron", "Koenigsegg Jesko",
        "Tesla Model S", "Rolls-Royce Phantom", "Dodge Challenger"
    ]
}

CAR_RARITIES = {
    # Vietnam Collection
    "Honda Wave Alpha": "Common", "Honda Dream II": "Common", "Honda Cub 81": "Common", "Yamaha Sirius": "Common",
    "Honda Future": "Rare", "Yamaha Jupiter": "Rare", "Honda Vision": "Rare", "Honda Air Blade": "Rare",
    "Yamaha Exciter 150": "Epic", "Yamaha Exciter 155": "Epic", "Honda Winner X": "Epic", "Suzuki Raider": "Epic", "Suzuki Satria": "Epic",
    "Honda SH125i": "Legendary", "Honda SH350i": "Legendary",

    # JDM Collection
    "Toyota AE86": "Common",
    "Nissan Silvia S15": "Rare", "Hyundai Elantra": "Rare",
    "Mazda 3": "Epic", "Mitsubishi Outlander": "Epic",
    "Nissan Skyline R34": "Legendary", "Honda NSX": "Legendary",
    "Toyota Supra MK4": "Mythic", "Nissan GTR R35": "Mythic",

    # Super Bike Collection
    "Honda CBR650R": "Rare", "Kawasaki Z900": "Rare", "Yamaha MT09": "Rare",
    "Kawasaki ZX4R": "Epic", "Kawasaki ZX6R": "Epic",
    "Suzuki Hayabusa": "Legendary", "BMW S1000RR": "Legendary", "Ducati Panigale V4": "Legendary",
    "Kawasaki H2": "Mythic",
    "Kawasaki H2R": "Exclusive",

    # Hypercar Collection
    "Ferrari SF90 Stradale": "Epic", "Lamborghini": "Epic",
    "Chevrolet Corvette": "Legendary", "Aston Martin": "Legendary", "Dodge Challenger": "Legendary",
    "Ferrari LaFerrari": "Mythic", "Rolls-Royce Phantom": "Mythic", "Bugatti Chiron": "Mythic",
    "Koenigsegg Jesko": "Exclusive", "Tesla Model S": "Exclusive"
}

# Special editions for specific models
CAR_EDITIONS = {
    "Toyota Supra MK4": ["Stock", "Track Pack", "Midnight Edition", "Dragon Edition", "Sakura Edition"],
    "Nissan Skyline R34": ["Stock", "Track Pack", "Midnight Edition", "Dragon Edition", "Sakura Edition"],
    "Honda SH350i": ["Stock", "Sport Edition", "Classic Edition"],
    "Honda Dream II": ["Stock", "Kiểng Edition"],
    "Yamaha Exciter 150": ["Stock", "GP Edition", "Monster Energy Edition"],
    "Kawasaki H2R": ["Stock", "Carbon Edition"],
    "Ferrari LaFerrari": ["Stock", "Aperta Edition"]
}

BOX_DETAILS = {
    "1": {
        "name": "Garage Box",
        "price": 100_000,
        "rates": [("Common", 70), ("Rare", 25), ("Epic", 5)]
    },
    "2": {
        "name": "Premium Box",
        "price": 1_000_000,
        "rates": [("Rare", 50), ("Epic", 35), ("Legendary", 13), ("Mythic", 2)]
    },
    "3": {
        "name": "Luxury Box",
        "price": 10_000_000,
        "rates": [("Epic", 40), ("Legendary", 35), ("Mythic", 20), ("Exclusive", 5)]
    }
}

# Helper mapping for model quotes / descriptions
CAR_QUOTES = {
    "Honda Wave Alpha": "Chiến thần đường phố Việt Nam.",
    "Honda Dream II": "Giấc mơ của mọi thế hệ.",
    "Honda Cub 81": "Huyền thoại sống mãi với thời gian.",
    "Toyota Supra MK4": "Quái vật JDM với khối động cơ 2JZ huyền thoại.",
    "Nissan Skyline R34": "Biểu tượng bất tử của văn hóa JDM.",
    "Kawasaki H2R": "Tốc độ vượt trội, mãnh thú đường đua.",
    "Koenigsegg Jesko": "Tuyệt tác Hypercar phá vỡ mọi giới hạn vật lý.",
    "Lamborghini": "Mãnh thú cơ bắp mang dòng máu bò tót Ý.",
    "BMW S1000RR": "Cá mập chúa thống trị phân khúc Super Bike.",
    "Ferrari LaFerrari": "Tuyệt tác hybrid tối thượng của nhà ngựa chồm Ý.",
    "Mazda 3": "Mẫu xe sedan trẻ trung, hiện đại và vô cùng năng động.",
    "Mitsubishi Outlander": "Chiếc CUV gia đình mạnh mẽ, rộng rãi và an toàn.",
    "Hyundai Elantra": "Thiết kế trẻ trung, hiện đại và đầy phong cách.",
    "Aston Martin": "Vẻ đẹp lịch lãm quý tộc Anh Quốc kết hợp sức mạnh động cơ vượt trội.",
    "Chevrolet Corvette": "Chiến cơ cơ bắp Mỹ đầy uy lực và tốc độ.",
    "Dodge Challenger": "Biểu tượng cơ bắp Mỹ cổ điển đầy kiêu hãnh.",
    "Ferrari SF90 Stradale": "Tuyệt tác siêu xe hybrid thế hệ mới đầy đột phá.",
    "Rolls-Royce Phantom": "Biểu tượng tối cao của sự xa hoa và quyền lực.",
    "Tesla Model S": "Đại diện ưu tú cho kỷ nguyên xe điện tương lai."
}

def get_car_image_file(model: str) -> str | None:
    mapping = {
        "Aston Martin": "Aston-Martin-Car-PNG-Image-Background.png",
        "Lamborghini": "Black-Lamborghini-Transparent-Image.png",
        "Mazda 3": "Blue-Mazda-PNG-Free-Download.png",
        "Mitsubishi Outlander": "Blue-Mitsubishi-PNG-Transparent-Image.png",
        "Chevrolet Corvette": "Chevrolet-Corvette-PNG-Free-Download.png",
        "Dodge Challenger": "Dodge-Challenger-PNG-Image-Transparent.png",
        "Ferrari SF90 Stradale": "Ferrari-SF90-Stradale-PNG-Image-Background.png",
        "Honda Wave Alpha": "pngwing.com.png",
        "Hyundai Elantra": "Red-Hyundai-PNG-Image-Transparent.png",
        "Rolls-Royce Phantom": "Rolls-Royce-PNG-High-Quality-Image.png",
        "Tesla Model S": "Tesla-Model-S-PNG-Photo.png",
    }
    return mapping.get(model)

def roll_rarity(rates: list[tuple[str, int]]) -> str:
    total = sum(r[1] for r in rates)
    roll = random.random() * total
    current = 0.0
    for rarity, chance in rates:
        current += chance
        if roll <= current:
            return rarity
    return rates[-1][0]


class XeRateView(discord.ui.View):
    def __init__(self, author: discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.current_page = 0
        self.message = None

    def get_embeds(self):
        # Page 0: Box Rates
        embed0 = make_embed(
            title="📦 TỶ LỆ HÒM XE GACHA 📦",
            description=(
                "### 📦 TỶ LỆ CÁC LOẠI HÒM XE\n\n"
                "- **📦 Garage Box (100.000 VNĐ):**\n"
                "  - ⚪ Common: **70%** | 🟢 Rare: **25%** | 🔵 Epic: **5%**\n\n"
                "- **📦 Premium Box (1.000.000 VNĐ):**\n"
                "  - 🟢 Rare: **50%** | 🔵 Epic: **35%** | 🟣 Legendary: **13%** | 🟡 Mythic: **2%**\n\n"
                "- **📦 Luxury Box (10.000.000 VNĐ):**\n"
                "  - 🔵 Epic: **40%** | 🟣 Legendary: **35%** | 🟡 Mythic: **20%** | 🔴 Exclusive: **5%**"
            ),
            color=discord.Color.red()
        )
        embed0.set_footer(text="Trang 1/5 • Tỷ lệ Hòm xe")

        # Page 1: Vietnam
        embed1 = make_embed(
            title="🇻🇳 BỘ VIỆT NAM (Vietnam Collection) 🇻🇳",
            description=(
                "- ⚪ **Common:** Honda Wave Alpha, Honda Dream II, Honda Cub 81, Yamaha Sirius\n"
                "- 🟢 **Rare:** Honda Future, Yamaha Jupiter, Honda Vision, Honda Air Blade\n"
                "- 🔵 **Epic:** Yamaha Exciter 150, Yamaha Exciter 155, Honda Winner X, Suzuki Raider, Suzuki Satria\n"
                "- 🟣 **Legendary:** Honda SH125i, Honda SH350i"
            ),
            color=discord.Color.red()
        )
        embed1.set_footer(text="Trang 2/5 • Bộ sưu tập Việt Nam")

        # Page 2: JDM
        embed2 = make_embed(
            title="🇯🇵 BỘ JDM (JDM Collection) 🇯🇵",
            description=(
                "- ⚪ **Common:** Toyota AE86\n"
                "- 🟢 **Rare:** Nissan Silvia S15, Hyundai Elantra\n"
                "- 🔵 **Epic:** Mazda 3, Mitsubishi Outlander\n"
                "- 🟣 **Legendary:** Nissan Skyline R34, Honda NSX\n"
                "- 🟡 **Mythic:** Toyota Supra MK4, Nissan GTR R35"
            ),
            color=discord.Color.blue()
        )
        embed2.set_footer(text="Trang 3/5 • Bộ sưu tập JDM")

        # Page 3: Super Bike
        embed3 = make_embed(
            title="🏍️ BỘ SUPER BIKE (Super Bike Collection) 🏍️",
            description=(
                "- 🟢 **Rare:** Honda CBR650R, Kawasaki Z900, Yamaha MT09\n"
                "- 🔵 **Epic:** Kawasaki ZX4R, Kawasaki ZX6R\n"
                "- 🟣 **Legendary:** Suzuki Hayabusa, BMW S1000RR, Ducati Panigale V4\n"
                "- 🟡 **Mythic:** Kawasaki H2\n"
                "- 🔴 **Exclusive:** Kawasaki H2R"
            ),
            color=discord.Color.green()
        )
        embed3.set_footer(text="Trang 4/5 • Bộ sưu tập Super Bike")

        # Page 4: Hypercar
        embed4 = make_embed(
            title="🏎️ BỘ HYPERCAR (Hypercar Collection) 🏎️",
            description=(
                "- 🔵 **Epic:** Ferrari SF90 Stradale, Lamborghini\n"
                "- 🟣 **Legendary:** Chevrolet Corvette, Aston Martin, Dodge Challenger\n"
                "- 🟡 **Mythic:** Ferrari LaFerrari, Rolls-Royce Phantom, Bugatti Chiron\n"
                "- 🔴 **Exclusive:** Koenigsegg Jesko, Tesla Model S"
            ),
            color=discord.Color.purple()
        )
        embed4.set_footer(text="Trang 5/5 • Bộ sưu tập Hypercar")

        return [embed0, embed1, embed2, embed3, embed4]

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"page_{self.current_page}":
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Tỷ Lệ 📦", style=discord.ButtonStyle.primary, custom_id="page_0")
    async def page_rates(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[0], view=self)

    @discord.ui.button(label="Việt Nam 🇻🇳", style=discord.ButtonStyle.secondary, custom_id="page_1")
    async def page_vietnam(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[1], view=self)

    @discord.ui.button(label="JDM 🇯🇵", style=discord.ButtonStyle.secondary, custom_id="page_2")
    async def page_jdm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 2
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[2], view=self)

    @discord.ui.button(label="Super Bike 🏍️", style=discord.ButtonStyle.secondary, custom_id="page_3")
    async def page_bike(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 3
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[3], view=self)

    @discord.ui.button(label="Hypercar 🏎️", style=discord.ButtonStyle.secondary, custom_id="page_4")
    async def page_hyper(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 4
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[4], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Lệnh này không phải của bạn!", ephemeral=True)
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


class Xe(commands.Cog, name="Xe"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())

    def _get_estimated_value(self, car) -> int:
        # car row: [id, user_id, model, rarity, serial, edition, collection, is_favorite]
        rarity = car[3]
        base_val = RARITY_INFO.get(rarity, {}).get("value", 500_000)
        
        # Serial bonus: beautiful serials have multipliers
        serial = car[4]
        serial_str = f"{serial:04d}"
        multiplier = 1.0
        
        if serial == 1:
            multiplier = 5.0  # #0001 gets 5x value
        elif len(set(serial_str)) == 1:
            multiplier = 3.0  # Tứ quý like #8888, #9999
        elif serial < 10:
            multiplier = 2.5  # Single digits #0002 - #0009
        elif serial_str in ["1337", "0007", "0042", "0079", "0888", "9999"]:
            multiplier = 2.0  # Special numbers
            
        # Edition bonus
        edition = car[5]
        edition_mult = 1.0
        if edition != "Stock":
            edition_mult = 1.5
            
        return int(base_val * multiplier * edition_mult)

    def _check_achievements(self, user_id: int, cars: list) -> list[str]:
        achieved = []
        if not cars:
            return achieved
            
        total_cars = len(cars)
        if total_cars >= 10:
            achieved.append("🏆 **Sở hữu 10 xe:** Bộ sưu tập khởi đầu thành công!")
        if total_cars >= 50:
            achieved.append("🏆 **Sở hữu 50 xe:** Gã khổng lồ của giới chơi xe!")
        if total_cars >= 100:
            achieved.append("🏆 **Sở hữu 100 xe:** Ông trùm Garage thế giới!")
            
        rarities = [c[3] for c in cars]
        if "Legendary" in rarities:
            achieved.append("🏆 **Chiếc Legendary đầu tiên:** Bắt đầu có giá trị thật sự!")
        if "Mythic" in rarities:
            achieved.append("🏆 **Chiếc Mythic đầu tiên:** Kho báu tối thượng!")
        if "Exclusive" in rarities:
            achieved.append("🏆 **Chiếc Exclusive đầu tiên:** Giới hạn của sự đẳng cấp!")
            
        # Collection completions
        models_owned = {c[2] for c in cars}
        for col_name, col_models in COLLECTIONS.items():
            if all(m in models_owned for m in col_models):
                achieved.append(f"🏆 **Hoàn thành bộ sưu tập {col_name}:** Bằng chứng của nhà sưu tập đích thực!")
                
        # Serial #0001
        serials = [c[4] for c in cars]
        if 1 in serials:
            achieved.append("🏆 **Sở hữu xe Serial #0001:** Chiếc xe đầu tiên của dòng sản phẩm!")
            
        return achieved

    @commands.group(
        name="xe",
        brief="Hệ thống sưu tập xe, mở hòm và giao dịch.",
        usage="xe [subcommand]",
        aliases=["car"],
        invoke_without_command=True,
    )
    async def xe_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            # Default behavior: Show player's garage (aliases to garage)
            await self.xe_garage(ctx)

    @xe_group.command(name="help", brief="Xem hướng dẫn sử dụng tính năng Xe.")
    async def xe_help(self, ctx: commands.Context):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
            
        desc = (
            "🏎️ **HỆ THỐNG GARAGE XE - COLLECT & FLEX** 🏎️\n\n"
            f"📦 **Gacha & Hòm:**\n"
            f"🔹 `{prefix}xe shop` — Xem cửa hàng hòm xe.\n"
            f"🔹 `{prefix}xe box <ID>` — Mua và mở hòm xe gacha.\n"
            f"🔹 `{prefix}xe rate` — Xem tỷ lệ mở hòm xe gacha và danh mục xe.\n\n"
            f"🏠 **Garage & Cá nhân:**\n"
            f"🔹 `{prefix}xe garage` (hoặc `{prefix}garage`) — Xem garage cá nhân.\n"
            f"🔹 `{prefix}xe favorite <ID_xe>` (hoặc `{prefix}favorite`) — Đặt xe yêu thích trưng bày.\n"
            f"🔹 `{prefix}xe card <ID_xe>` — Xem thẻ xe chi tiết dạng sưu tập.\n"
            f"🔹 `{prefix}xe collection` (hoặc `{prefix}xe coll`) — Xem tiến trình hoàn thành các bộ sưu tập.\n"
            f"🔹 `{prefix}xe achievements` (hoặc `{prefix}xe ach`) — Xem danh sách thành tựu đã đạt được.\n\n"
            f"🛒 **Chợ xe (Market):**\n"
            f"🔹 `{prefix}xe market` (hoặc `{prefix}market`) — Xem danh sách xe đang rao bán.\n"
            f"🔹 `{prefix}xe market sell <ID_xe> <giá>` — Đăng bán xe của bạn lên chợ.\n"
            f"🔹 `{prefix}xe market buy <ID_tin>` — Mua xe từ chợ giao dịch.\n"
            f"🔹 `{prefix}xe market cancel <ID_tin>` — Hủy bài đăng bán xe của bạn.\n"
        )
        embed = make_embed(
            title="🎮 HỆ THỐNG XE - HƯỚNG DẪN 🎮",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @xe_group.command(name="rate", brief="Xem tỷ lệ mở hòm xe gacha và danh mục xe theo độ hiếm.")
    async def xe_rate(self, ctx: commands.Context):
        view = XeRateView(ctx.author)
        embeds = view.get_embeds()
        msg = await ctx.send(embed=embeds[0], view=view)
        view.message = msg

    @xe_group.command(name="garage", brief="Xem garage xe cá nhân của bạn.", aliases=["list"])
    async def xe_garage(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        cars = self.economy.get_user_cars(target.id)
        
        if not cars:
            embed = make_embed(
                title=f"🏠 GARAGE CỦA {target.display_name.upper()} 🏠",
                description="Garage hiện tại đang trống. Hãy vào `{prefix}xe shop` để mua hòm đầu tiên!",
                color=discord.Color.dark_grey()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            await ctx.send(embed=embed)
            return
            
        total_cars = len(cars)
        rarity_counts = {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0, "Mythic": 0, "Exclusive": 0}
        total_val = 0
        
        for c in cars:
            rarity_counts[c[3]] = rarity_counts.get(c[3], 0) + 1
            total_val += self._get_estimated_value(c)
            
        fav_car = self.economy.get_favorite_car(target.id)
        fav_str = "Chưa thiết lập"
        if fav_car:
            fav_str = f"{RARITY_INFO[fav_car[3]]['emoji']} **{fav_car[2]}** ({fav_car[5]}) - Serial #{fav_car[4]:04d}"
            
        car_list_str = ""
        for c in cars[:15]:  # Show up to first 15 cars
            car_id, _, model, rarity, serial, edition, _, _ = c
            r_emoji = RARITY_INFO[rarity]["emoji"]
            car_list_str += f"• `[ID: {car_id}]` {r_emoji} **{model}** ({edition}) - Serial `#{serial:04d}`\n"
            
        if len(cars) > 15:
            car_list_str += f"*... và {len(cars) - 15} chiếc xe khác.*"
            
        desc = (
            f"**Tổng xe:** `{total_cars}` chiếc\n\n"
            f"⚪ Common: `{rarity_counts['Common']}` chiếc\n"
            f"🟢 Rare: `{rarity_counts['Rare']}` chiếc\n"
            f"🔵 Epic: `{rarity_counts['Epic']}` chiếc\n"
            f"🟣 Legendary: `{rarity_counts['Legendary']}` chiếc\n"
            f"🟡 Mythic: `{rarity_counts['Mythic']}` chiếc\n"
            f"🔴 Exclusive: `{rarity_counts['Exclusive']}` chiếc\n\n"
            f"⭐ **Xe yêu thích:**\n{fav_str}\n\n"
            f"💰 **Giá trị Garage (Ước tính):**\n**{total_val:,} VNĐ**\n\n"
            f"🚗 **DANH SÁCH XE CỦA BẠN:**\n{car_list_str}"
        )
        
        embed = make_embed(
            title=f"🏠 GARAGE CỦA {target.display_name.upper()} 🏠",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @xe_group.command(name="shop", brief="Xem các loại hòm xe có sẵn.")
    async def xe_shop(self, ctx: commands.Context):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
            
        desc = (
            "📦 **CỬA HÀNG HÒM XE GACHA**\n"
            f"🛒 Mua hòm bằng lệnh: `{prefix}xe box <ID>`\n\n"
            "📦 **[1] Garage Box:** `100.000 VNĐ`\n"
            "  - ⚪ Common (70%) | 🟢 Rare (25%) | 🔵 Epic (5%)\n\n"
            "📦 **[2] Premium Box:** `1.000.000 VNĐ`\n"
            "  - 🟢 Rare (50%) | 🔵 Epic (35%) | 🟣 Legendary (13%) | 🟡 Mythic (2%)\n\n"
            "📦 **[3] Luxury Box:** `10.000.000 VNĐ`\n"
            "  - 🔵 Epic (40%) | 🟣 Legendary (35%) | 🟡 Mythic (20%) | 🔴 Exclusive (5%)\n"
        )
        embed = make_embed(
            title="📦 GARAGE BOX SHOP 📦",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @xe_group.command(name="box", brief="Mua và mở hòm xe bằng ID.")
    async def buy_box(self, ctx: commands.Context, box_id: str):
        box_id = box_id.strip()
        if box_id not in BOX_DETAILS:
            await ctx.send("❌ **Lỗi:** ID hòm không hợp lệ! Hãy chọn ID `1` (Garage Box), `2` (Premium Box), hoặc `3` (Luxury Box).")
            return
            
        box = BOX_DETAILS[box_id]
        price = box["price"]
        
        try:
            validate_money_bet(self.economy, ctx.author.id, price)
        except Exception as exc:
            await ctx.send(str(exc))
            return
            
        # Deduct money
        self.economy.add_money(ctx.author.id, -price)
        
        # 1. Roll rarity
        rarity = roll_rarity(box["rates"])
        
        # 2. Get models of that rarity
        models = [name for name, r in CAR_RARITIES.items() if r == rarity]
        if not models:
            # Fallback to any model if rarity filter fails
            models = list(CAR_RARITIES.keys())
            
        model = random.choice(models)
        
        # 3. Roll edition
        edition = "Stock"
        if model in CAR_EDITIONS:
            # 70% Stock, 30% split among special editions
            if random.random() < 0.30:
                edition = random.choice(CAR_EDITIONS[model][1:])
                
        # 4. Roll collection name
        col_name = "Other"
        for c_name, c_models in COLLECTIONS.items():
            if model in c_models:
                col_name = c_name
                break
                
        # 5. Roll serial number
        serial = random.randint(1, 9999)
        
        # Write to database
        car_id = self.economy.add_user_car(ctx.author.id, model, rarity, serial, edition, col_name)
        
        log_wallet_change(
            logger,
            event="buy_car_box",
            user_id=ctx.author.id,
            money_delta=-price,
            box_id=box_id,
            car_id=car_id,
            model=model,
            rarity=rarity
        )
        
        # Send opening animation first
        anim_embed = make_embed(
            title="📦 ĐANG MỞ HÒM XE... 📦",
            description=f"⏳ **{ctx.author.display_name}** đang mở **{box['name']}** với giá **{price:,} VNĐ**...",
            color=discord.Color.gold()
        )
        gif_path = ABS_PATH / "modules" / "daga" / "open_chest.gif"
        
        if gif_path.exists():
            file_gif = discord.File(gif_path, filename="open_chest.gif")
            anim_embed.set_image(url="attachment://open_chest.gif")
            msg = await ctx.send(embed=anim_embed, file=file_gif)
        else:
            msg = await ctx.send(embed=anim_embed)
            
        await asyncio.sleep(3)
        
        # Final card layout response
        est_val = self._get_estimated_value((car_id, ctx.author.id, model, rarity, serial, edition, col_name, 0))
        r_emoji = RARITY_INFO[rarity]["emoji"]
        
        desc = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏎️ **{model}**\n"
            f"{r_emoji} `{rarity}`\n"
            f"📁 **Collection:** {col_name}\n"
            f"🔢 **Edition:** {edition}\n"
            f"🔢 **Serial:** #{serial:04d}\n"
            f"👤 **Owner:** {ctx.author.display_name}\n"
            f"💰 **Estimated Value:** {est_val:,} VNĐ\n\n"
            f"*{CAR_QUOTES.get(model, 'Tuyệt tác của tốc độ và thiết kế.')}*\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        embed = make_embed(
            title="🏎️ XE MỚI ĐÃ VỀ GARAGE 🏎️",
            description=desc,
            color=RARITY_INFO[rarity]["color"]
        )
        
        img_filename = get_car_image_file(model)
        img_path = ABS_PATH / "modules" / "duaxe" / img_filename if img_filename else None
        
        if img_path and img_path.exists():
            file_car = discord.File(img_path, filename=img_filename)
            embed.set_image(url=f"attachment://{img_filename}")
            await msg.edit(embed=embed, attachments=[file_car])
        else:
            await msg.edit(embed=embed, attachments=[])

    @xe_group.command(name="favorite", brief="Chọn chiếc xe trưng bày của bạn.", aliases=["fav"])
    async def xe_favorite(self, ctx: commands.Context, car_id: int):
        car = self.economy.get_user_car(car_id)
        if not car:
            await ctx.send(f"❌ **Lỗi:** Không tìm thấy xe với ID `{car_id}`.")
            return
            
        if car[1] != ctx.author.id:
            await ctx.send("❌ **Lỗi:** Chiếc xe này không thuộc quyền sở hữu của bạn!")
            return
            
        self.economy.set_favorite_car(ctx.author.id, car_id)
        await ctx.send(f"✅ Đã đặt xe **{car[2]}** (Serial #{car[4]:04d}) làm xe yêu thích trưng bày của bạn!")

    @xe_group.command(name="card", brief="Xem thẻ chi tiết của xe.")
    async def xe_card(self, ctx: commands.Context, car_id: int):
        car = self.economy.get_user_car(car_id)
        if not car:
            await ctx.send(f"❌ **Lỗi:** Không tìm thấy xe với ID `{car_id}`.")
            return
            
        owner = self.client.get_user(car[1])
        owner_name = owner.name if owner else f"User {car[1]}"
        
        rarity = car[3]
        r_emoji = RARITY_INFO[rarity]["emoji"]
        est_val = self._get_estimated_value(car)
        
        desc = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏎️ **{car[2]}**\n"
            f"{r_emoji} `{rarity}`\n"
            f"📁 **Collection:** {car[6]}\n"
            f"🔢 **Edition:** {car[5]}\n"
            f"🔢 **Serial:** #{car[4]:04d}\n"
            f"👤 **Owner:** {owner_name}\n"
            f"💰 **Estimated Value:** {est_val:,} VNĐ\n\n"
            f"*{CAR_QUOTES.get(car[2], 'Tuyệt tác của tốc độ và thiết kế.')}*\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        embed = make_embed(
            title=f"🏎️ THẺ SƯU TẬP XE (ID: {car_id}) 🏎️",
            description=desc,
            color=RARITY_INFO[rarity]["color"]
        )
        
        img_filename = get_car_image_file(car[2])
        img_path = ABS_PATH / "modules" / "duaxe" / img_filename if img_filename else None
        
        if img_path and img_path.exists():
            file_car = discord.File(img_path, filename=img_filename)
            embed.set_image(url=f"attachment://{img_filename}")
            await ctx.send(embed=embed, file=file_car)
        else:
            await ctx.send(embed=embed)

    @xe_group.command(name="collection", brief="Xem tiến độ bộ sưu tập xe.", aliases=["coll"])
    async def xe_collection(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        cars = self.economy.get_user_cars(target.id)
        models_owned = {c[2] for c in cars}
        
        desc = ""
        for col_name, col_models in COLLECTIONS.items():
            owned_count = sum(1 for m in col_models if m in models_owned)
            pct = int((owned_count / len(col_models)) * 100)
            status_emoji = "✅" if owned_count == len(col_models) else "📁"
            
            desc += f"{status_emoji} **{col_name} Collection:** `{owned_count}/{len(col_models)}` xe ({pct}%)\n"
            for m in col_models[:5]: # Show preview of first 5
                marker = "🟢" if m in models_owned else "🔴"
                desc += f"  {marker} {m}\n"
            if len(col_models) > 5:
                desc += f"  *... và {len(col_models)-5} mẫu xe khác.*\n\n"
                
        embed = make_embed(
            title=f"🏆 BỘ SƯU TẬP CỦA {target.display_name.upper()} 🏆",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @xe_group.command(name="achievements", brief="Xem các thành tựu thu thập xe.", aliases=["ach"])
    async def xe_achievements(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        cars = self.economy.get_user_cars(target.id)
        
        achieved = self._check_achievements(target.id, cars)
        
        all_achievements = [
            "🏆 **Sở hữu 10 xe**",
            "🏆 **Sở hữu 50 xe**",
            "🏆 **Sở hữu 100 xe**",
            "🏆 **Có chiếc Legendary đầu tiên**",
            "🏆 **Có chiếc Mythic đầu tiên**",
            "🏆 **Có chiếc Exclusive đầu tiên**",
            "🏆 **Hoàn thành bộ sưu tập Vietnam**",
            "🏆 **Hoàn thành bộ sưu tập JDM**",
            "🏆 **Hoàn thành bộ sưu tập Super Bike**",
            "🏆 **Hoàn thành bộ sưu tập Hypercar**",
            "🏆 **Sở hữu xe Serial #0001**"
        ]
        
        desc = "**THÀNH TỰU ĐÃ ĐẠT ĐƯỢC:**\n"
        if achieved:
            desc += "\n".join(achieved)
        else:
            desc += "*Chưa đạt thành tựu nào. Hãy tiếp tục sưu tầm!*"
            
        desc += "\n\n**DANH SÁCH THÀNH TỰU:**\n"
        models_owned = {c[2] for c in cars}
        serials = [c[4] for c in cars]
        rarities = [c[3] for c in cars]
        
        checks = [
            len(cars) >= 10,
            len(cars) >= 50,
            len(cars) >= 100,
            "Legendary" in rarities,
            "Mythic" in rarities,
            "Exclusive" in rarities,
            all(m in models_owned for m in COLLECTIONS["Vietnam"]),
            all(m in models_owned for m in COLLECTIONS["JDM"]),
            all(m in models_owned for m in COLLECTIONS["Super Bike"]),
            all(m in models_owned for m in COLLECTIONS["Hypercar"]),
            1 in serials
        ]
        
        for name, checked in zip(all_achievements, checks):
            marker = "✅" if checked else "❌"
            desc += f"{marker} {name}\n"
            
        embed = make_embed(
            title=f"🏅 THÀNH TỰU GARAGE CỦA {target.display_name.upper()} 🏅",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # --- MARKET SUBCOMMANDS ---

    @xe_group.group(
        name="market",
        brief="Hệ thống chợ giao dịch, mua bán xe giữa người chơi.",
        aliases=["chợ"],
        invoke_without_command=True
    )
    async def market_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self.market_list(ctx)

    @market_group.command(name="list", brief="Xem danh sách xe đang đăng bán.")
    async def market_list(self, ctx: commands.Context):
        listings = self.economy.get_market_listings()
        if not listings:
            await ctx.send("🛍️ Chợ giao dịch hiện tại đang trống. Dùng lệnh `i?xe market sell` để rao bán chiếc xe của bạn!")
            return
            
        desc = ""
        for lst in listings[:15]: # Show top 15 listings
            lst_id, car_id, seller_id, price, _ = lst
            car = self.economy.get_user_car(car_id)
            if not car:
                continue
                
            seller = self.client.get_user(seller_id)
            seller_name = seller.name if seller else f"User {seller_id}"
            
            r_emoji = RARITY_INFO[car[3]]["emoji"]
            desc += (
                f"`[ID Lst: {lst_id}]` {r_emoji} **{car[2]}** ({car[5]}) - Serial `#{car[4]:04d}`\n"
                f"  └ Người bán: `{seller_name}` | Giá: **{price:,} VNĐ**\n"
            )
            
        embed = make_embed(
            title="🛍️ CHỢ XE GIAO DỊCH DISCORD 🛍️",
            description=desc,
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @market_group.command(name="sell", brief="Đăng bán xe của bạn lên chợ.")
    async def market_sell(self, ctx: commands.Context, car_id: int, price: int):
        if price <= 0:
            await ctx.send("❌ **Lỗi:** Giá bán phải lớn hơn 0 VNĐ.")
            return
            
        car = self.economy.get_user_car(car_id)
        if not car:
            await ctx.send(f"❌ **Lỗi:** Không tìm thấy xe với ID `{car_id}`.")
            return
            
        if car[1] != ctx.author.id:
            await ctx.send("❌ **Lỗi:** Bạn không thể đăng bán chiếc xe không phải của mình!")
            return
            
        # Check if already listed
        existing = self.economy.get_market_listing_by_car(car_id)
        if existing:
            await ctx.send("❌ **Lỗi:** Chiếc xe này đã được rao bán trên chợ rồi!")
            return
            
        lst_id = self.economy.add_market_listing(car_id, ctx.author.id, price)
        await ctx.send(f"✅ Đăng bán thành công chiếc **{car[2]}** (Serial #{car[4]:04d}) với giá **{price:,} VNĐ** lên chợ! (Mã tin đăng: `[ID Lst: {lst_id}]`)")

    @market_group.command(name="buy", brief="Mua xe từ chợ xe.")
    async def market_buy(self, ctx: commands.Context, listing_id: int):
        listing = self.economy.get_market_listing(listing_id)
        if not listing:
            await ctx.send(f"❌ **Lỗi:** Không tìm thấy tin đăng bán xe với ID `{listing_id}`.")
            return
            
        lst_id, car_id, seller_id, price, _ = listing
        
        if seller_id == ctx.author.id:
            await ctx.send("❌ **Lỗi:** Bạn không thể mua chiếc xe của chính bản thân đăng bán!")
            return
            
        try:
            validate_money_bet(self.economy, ctx.author.id, price)
        except Exception as exc:
            await ctx.send(str(exc))
            return
            
        car = self.economy.get_user_car(car_id)
        if not car:
            await ctx.send("❌ **Lỗi:** Chiếc xe này không còn tồn tại.")
            self.economy.delete_market_listing(listing_id)
            return
            
        # Execute Transaction
        self.economy.add_money(ctx.author.id, -price)
        self.economy.add_money(seller_id, price)
        self.economy.transfer_user_car(car_id, ctx.author.id)
        self.economy.delete_market_listing(listing_id)
        
        log_wallet_change(
            logger,
            event="market_buy_car_buyer",
            user_id=ctx.author.id,
            money_delta=-price,
            car_id=car_id,
            seller_id=seller_id,
            listing_id=listing_id
        )
        log_wallet_change(
            logger,
            event="market_buy_car_seller",
            user_id=seller_id,
            money_delta=price,
            car_id=car_id,
            buyer_id=ctx.author.id,
            listing_id=listing_id
        )
        
        await ctx.send(f"🎉 Chúc mừng **{ctx.author.display_name}** đã mua thành công xe **{car[2]}** (Serial #{car[4]:04d}) từ chợ giao dịch với giá **{price:,} VNĐ**!")

    @market_group.command(name="cancel", brief="Hủy tin đăng bán xe của bạn.")
    async def market_cancel(self, ctx: commands.Context, listing_id: int):
        listing = self.economy.get_market_listing(listing_id)
        if not listing:
            await ctx.send(f"❌ **Lỗi:** Không tìm thấy tin đăng bán xe với ID `{listing_id}`.")
            return
            
        lst_id, car_id, seller_id, _, _ = listing
        
        if seller_id != ctx.author.id:
            await ctx.send("❌ **Lỗi:** Bạn không có quyền hủy tin đăng bán của người khác!")
            return
            
        self.economy.delete_market_listing(listing_id)
        await ctx.send("✅ Đã gỡ bỏ bài đăng bán xe của bạn khỏi chợ giao dịch thành công!")

# Standalone command aliases for root-level direct invocation
@commands.command(name="garage")
async def top_level_garage(ctx: commands.Context, member: discord.Member | None = None):
    cog = ctx.bot.get_cog("Xe")
    if cog:
        await cog.xe_garage(ctx, member)

@commands.command(name="favorite")
async def top_level_favorite(ctx: commands.Context, car_id: int):
    cog = ctx.bot.get_cog("Xe")
    if cog:
        await cog.xe_favorite(ctx, car_id)

@commands.command(name="market")
async def top_level_market(ctx: commands.Context, *args):
    cog = ctx.bot.get_cog("Xe")
    if cog:
        # Default delegate
        if args and args[0] == "sell":
            if len(args) >= 3:
                try:
                    await cog.market_sell(ctx, int(args[1]), int(args[2]))
                except ValueError:
                    await ctx.send("❌ **Lỗi:** Vui lòng nhập đúng định dạng ID xe và giá bán.")
            else:
                await ctx.send("❌ **Lỗi:** Thiếu đối số. Hãy dùng `i?market sell <ID_xe> <giá>`.")
        elif args and args[0] == "buy":
            if len(args) >= 2:
                try:
                    await cog.market_buy(ctx, int(args[1]))
                except ValueError:
                    await ctx.send("❌ **Lỗi:** Vui lòng nhập đúng định dạng ID tin đăng.")
            else:
                await ctx.send("❌ **Lỗi:** Thiếu đối số. Hãy dùng `i?market buy <ID_tin>`.")
        elif args and args[0] == "cancel":
            if len(args) >= 2:
                try:
                    await cog.market_cancel(ctx, int(args[1]))
                except ValueError:
                    await ctx.send("❌ **Lỗi:** Vui lòng nhập đúng định dạng ID tin đăng.")
            else:
                await ctx.send("❌ **Lỗi:** Thiếu đối số. Hãy dùng `i?market cancel <ID_tin>`.")
        else:
            await cog.market_list(ctx)


async def setup(client: commands.Bot):
    cog = Xe(client)
    await client.add_cog(cog)
    client.add_command(top_level_garage)
    client.add_command(top_level_favorite)
    client.add_command(top_level_market)
