import asyncio
from io import BytesIO
import logging
import random
import time
from datetime import datetime
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageChops
import requests

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.profile_renderer import load_font
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# List of wedding rings mapping
RINGS = {
    "ring_grass": "Nhẫn Cỏ 🌾",
    "ring_quartz": "Nhẫn Thạch Anh Trắng 💍",
    "ring_aquamarine": "Nhẫn Sương Mai Aquamarine 💧",
    "ring_emerald": "Nhẫn Thanh Xuân Lục Bảo 🌿",
    "ring_amethyst": "Nhẫn Trăng Khuyết Amethyst 🌙",
    "ring_cupid": "Nhẫn Tình Yêu Cupid 💘",
    "ring_citrine": "Nhẫn Vương Miện Citrine 👑",
    "ring_ruby": "Nhẫn Hồng Ngọc Bách Hợp 🌹",
    "ring_sapphire": "Nhẫn Lam Ngọc Tinh Tú ✨",
    "ring_sunburst": "Nhẫn Nhật Quang Thái Dương ☀️",
    "ring_gothic": "Nhẫn Hắc Dạ Gothic 🖤",
    "ring_angel": "Nhẫn Cánh Thần Sapphire 👼",
    "ring_divine": "Nhẫn Hào Quang Vĩnh Cửu 🌌"
}

RING_IMAGES = {
    "ring_grass": "Nhẫn Cỏ.png",
    "ring_quartz": "Nhẫn Thạch Anh Trắng.png",
    "ring_aquamarine": "Nhẫn Sương Mai Aquamarine.png",
    "ring_emerald": "Nhẫn Thanh Xuân Lục Bảo.png",
    "ring_amethyst": "Nhẫn Trăng Khuyết Amethyst.png",
    "ring_cupid": "Nhẫn Tình Yêu Cupid.png",
    "ring_citrine": "Nhẫn Vương Miện Citrine.png",
    "ring_ruby": "Nhẫn Hồng Ngọc Bách Hợp.png",
    "ring_sapphire": "Nhẫn Lam Ngọc Tinh Tú.png",
    "ring_sunburst": "Nhẫn Nhật Quang Thái Dương.png",
    "ring_gothic": "Nhẫn Hắc Dạ.png",
    "ring_angel": "Nhẫn Cánh Thần Sapphire.png",
    "ring_divine": "Nhẫn Hào Quang Vĩnh Cửu.png"
}

# Sweet sayings for interactions
INTERACT_SAYINGS = {
    "Kiss": [
        "Chụt! Một nụ hôn nồng cháy gửi đến người thương ❤️",
        "Hôn nhẹ lên má cậu một cái nè, yêu ghê cơ 🥰",
        "Thương nhiều lắm mới trao nụ hôn ngọt ngào này đó 😘",
        "Nụ hôn ngọt ngào nhất thế gian này dành riêng cho cậu 💋",
        "Chụt! Mong rằng nụ hôn này làm cậu mỉm cười cả ngày hôm nay ✨"
    ],
    "Hug": [
        "Ôm một cái thật chặt để tiếp thêm năng lượng cho cậu nhé 🤗",
        "Ấm áp ghê, muốn ôm cậu mãi như thế này thôi 💖",
        "Nhận lấy chiếc ôm siêu to khổng lồ từ tớ nè! 🧸",
        "Bất cứ khi nào mệt mỏi, hãy nhớ luôn có một chiếc ôm đợi cậu 🌸",
        "Gửi trọn tình cảm vào cái ôm ấm áp này nhắn gửi tới cậu 💕"
    ],
    "Pat": [
        "Xoa đầu ngoan ngoan nè, thương thương lắm luôn á 👋",
        "Cậu đã làm tốt lắm rồi, xoa đầu khen thưởng cái nè 🥰",
        "Xoa xoa đầu, mong mọi muộn phiền của cậu đều tan biến nhé 💫",
        "Ngoan nào ngoan nào, có tớ ở đây rồi 🥺",
        "Nhìn cưng xỉu thế này chỉ muốn xoa đầu mãi thôi 😸"
    ],
    "Fuck": [
        "Một đêm nồng cháy và đầy yêu thương bên bạn đời của mình... 💕",
        "Ân ái mặn nồng, tình cảm đôi ta càng thêm thắt chặt gắn kết cấu 🥰",
        "Yêu thương đong đầy, những giây phút thăng hoa ngọt ngào bên nhau 💖",
        "Quấn quýt không rời, tình yêu phu thê nồng cháy thăng hoa đầy cảm xúc ✨"
    ]
}

def get_avatar_img(user) -> Image.Image:
    """Downloads user avatar or returns a fallback grey placeholder."""
    try:
        url = str(user.display_avatar.url)
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Failed to fetch avatar for {user.id}: {e}")
    return Image.new("RGBA", (150, 150), (120, 120, 120, 255))


def crop_circle(img: Image.Image, size: int = 120) -> Image.Image:
    """Crops an image into a circle with transparency."""
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    return output


def render_marriage_certificate(proposer, target, ring_id: str) -> BytesIO:
    """Draws a beautiful romantic marriage certificate."""
    # 800 x 500
    bg = Image.new("RGBA", (800, 500), (255, 240, 245, 255)) # LavenderBlush
    draw = ImageDraw.Draw(bg)
    
    # Ornate double border
    draw.rectangle((15, 15, 785, 485), outline=(183, 110, 121, 255), width=3) # Rose gold
    draw.rectangle((22, 22, 778, 478), outline=(183, 110, 121, 100), width=1)
    
    # Header Font & Texts
    font_header = load_font("bold", 38)
    font_title = load_font("bold", 22)
    font_sub = load_font("regular", 16)
    font_names = load_font("bold", 18)
    
    # Title Header
    draw.text((400, 60), "GIẤY CHỨNG NHẬN KẾT HÔN", fill=(128, 0, 32, 255), anchor="mm", font=font_header) # Burgundy
    draw.text((400, 110), "Đã chính thức thề nguyện gắn kết đồng hành bên nhau", fill=(80, 80, 80, 255), anchor="mm", font=font_sub)
    
    # Load avatars
    prop_avatar = get_avatar_img(proposer)
    tar_avatar = get_avatar_img(target)
    
    prop_circle = crop_circle(prop_avatar, 130)
    tar_circle = crop_circle(tar_avatar, 130)
    
    # Paste avatars
    bg.paste(prop_circle, (135, 175), mask=prop_circle)
    bg.paste(tar_circle, (535, 175), mask=tar_circle)
    
    # Gold borders around avatars
    draw.ellipse((133, 173, 267, 307), outline=(255, 215, 0, 255), width=4)
    draw.ellipse((533, 173, 667, 307), outline=(255, 215, 0, 255), width=4)
    
    # Names centered under avatars
    draw.text((200, 335), proposer.display_name, fill=(128, 0, 32, 255), anchor="mm", font=font_names)
    draw.text((600, 335), target.display_name, fill=(128, 0, 32, 255), anchor="mm", font=font_names)
    
    # Center overlapping wedding rings
    draw.ellipse((365, 220, 415, 270), outline=(255, 215, 0, 255), width=4)
    draw.ellipse((385, 220, 435, 270), outline=(255, 215, 0, 255), width=4)
    # Red heart outline in middle intersection
    draw.text((400, 245), "❤️", fill=(255, 0, 0, 255), anchor="mm", font=font_title)
    
    # Ring and Date description
    ring_name = RINGS.get(ring_id, "Nhẫn Cưới")
    date_str = datetime.now().strftime("Ngày %d tháng %m năm %Y")
    
    draw.text((400, 400), f"Vật chứng hôn nhân: {ring_name}", fill=(50, 50, 50, 255), anchor="mm", font=font_title)
    draw.text((400, 435), f"Chứng chỉ kết hôn lập tại sảnh Casino vào {date_str}", fill=(120, 120, 120, 255), anchor="mm", font=font_sub)
    
    # Output to BytesIO
    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    bg.close()
    return buf


def render_couple_banner(proposer, target, ring_type: str, love_points: int, joint_wallet: int, married_days: int, proposer_ig: str = "", target_ig: str = "", relationship_status: str = "Vợ Chồng", married_at: int = 0, saying: str = "") -> BytesIO:
    """Draws a beautiful custom profile banner for married couples using the template."""
    bg_path = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_marry2.png"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
    else:
        bg_fallback = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_marry.png"
        if bg_fallback.exists():
            bg = Image.open(bg_fallback).convert("RGBA")
        else:
            # Fallback to plain pink background of same dimensions
            bg = Image.new("RGBA", (1672, 941), (252, 229, 237, 255))
        
    width, height = bg.size
    
    # Create overlay for transparent drawing
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Load fonts — vogueeb.ttf for display, Roboto for small stat text
    _font_dir = ABS_PATH.parent.parent / "data" / "fonts"
    _font_path = _font_dir / "vogueeb.ttf"

    def _vogue(size: int) -> ImageFont.FreeTypeFont:
        """Load vogueeb.ttf, fallback to Roboto Bold if missing."""
        try:
            return ImageFont.truetype(str(_font_path), size)
        except Exception:
            return load_font("bold", size)

    def _roboto(size: int) -> ImageFont.FreeTypeFont:
        return load_font("bold", size)

    font_large   = _vogue(30)   # display names (decreased from 56 to 30)
    font_medium  = _vogue(48)   # status text "Vợ Chồng" (increased to 48 and pulled higher)
    font_stats   = _vogue(22)   # stats inside heart (decreased from 36 to 22)
    font_username = _vogue(30)  # usernames below avatar (decreased from 42 to 30)
    font_regular = _roboto(22)  # IG text in bottom box (decreased from 28 to 22)
    
    # ── Calibrated coordinates from template scan ──────────────────
    # Left  avatar slot center: (412, 412), radius ~174
    # Right avatar slot center: (1243, 412), radius ~177
    # Avatar diameter reduced to 260 to fit neatly inside the frame slot
    LEFT_CX,  LEFT_CY  = 412,  412
    RIGHT_CX, RIGHT_CY = 1243, 412
    AVATAR_DIAM = 260

    # 1. Load and process avatars
    p_avatar = get_avatar_img(proposer)
    t_avatar = get_avatar_img(target)

    p_circle = crop_circle(p_avatar, AVATAR_DIAM)
    t_circle = crop_circle(t_avatar, AVATAR_DIAM)

    overlay.paste(p_circle, (LEFT_CX  - AVATAR_DIAM // 2, LEFT_CY  - AVATAR_DIAM // 2), mask=p_circle)
    overlay.paste(t_circle, (RIGHT_CX - AVATAR_DIAM // 2, RIGHT_CY - AVATAR_DIAM // 2), mask=t_circle)

    p_avatar.close(); t_avatar.close()
    p_circle.close(); t_circle.close()

    PASTEL_PINK   = (235, 110, 145, 255)  # pastel pink replaces PURPLE
    LIGHT_PINK    = (255, 150, 180, 255)  # light pink replaces LIGHT_PURPLE
    BORDER_PINK   = (255, 182, 193, 255)  # border pink replaces PASTEL_PURPLE

    # Draw pastel pink border around avatars: "Avatar được bọc bởi một lớp viền màu hồng pátel"
    draw.ellipse((LEFT_CX - 130, LEFT_CY - 130, LEFT_CX + 130, LEFT_CY + 130), outline=BORDER_PINK, width=6)
    draw.ellipse((RIGHT_CX - 130, RIGHT_CY - 130, RIGHT_CX + 130, RIGHT_CY + 130), outline=BORDER_PINK, width=6)

    # 2. Display names inside white nameplate box above avatar
    draw.text((LEFT_CX,  205), proposer.display_name, fill=LIGHT_PINK, anchor="mm", font=font_large)
    draw.text((RIGHT_CX, 205), target.display_name,   fill=LIGHT_PINK, anchor="mm", font=font_large)

    # 3. Discord usernames inside the card below the avatar (Y = 600, inside the frame): "kéo username lên trên như ảnh"
    draw.text((LEFT_CX,  600), proposer.name, fill=PASTEL_PINK, anchor="mm", font=font_username)
    draw.text((RIGHT_CX, 600), target.name,   fill=PASTEL_PINK, anchor="mm", font=font_username)

    # 4. Relationship status high above the big heart: "Kéo chữ vợ chồng lên cao hơn nữa đi" (moved to Y = 180)
    draw.text((836, 180), relationship_status, fill=PASTEL_PINK, anchor="mm", font=font_medium)

    # 5. Stats inside the big heart: "thông tin như ngày kết hôn,... thì cung đổi sang font Selly Calligraphy và đặt ở giữa trái tim"
    date_str = "Chưa rõ"
    if married_at > 0:
        date_str = datetime.fromtimestamp(married_at).strftime("%d/%m/%Y")

    draw.text((836, 420), f"Ngày Kết Hôn : {date_str}",      fill=PASTEL_PINK, anchor="mm", font=font_stats)
    draw.text((836, 465), f"Đã Kết Hôn : {married_days} ngày", fill=PASTEL_PINK, anchor="mm", font=font_stats)
    draw.text((836, 510), f"Điểm thân mật : {love_points:,}",  fill=PASTEL_PINK, anchor="mm", font=font_stats)
    
    # 6. Load and paste Ring image centered exactly at the bottom-right heart: "fix lại hình chiếc nhẫn sao cho nó nằm ở giữa cái trái tim ở góc dưới"
    ring_file = RING_IMAGES.get(ring_type)
    if ring_file:
        ring_path = ABS_PATH.parent.parent / "pictures" / "Marry" / ring_file
        if ring_path.exists():
            try:
                ring_img = Image.open(ring_path).convert("RGBA")
                ring_img = ring_img.resize((130, 130), Image.Resampling.LANCZOS)
                overlay.paste(ring_img, (1475 - 65, 825 - 65), mask=ring_img)
                ring_img.close()
            except Exception as e:
                logger.error(f"Failed to draw wedding ring image: {e}")
                
    # 7. Instagram handles inside the bottom rectangular box: "tên ins thì nằm ở trong hình chữ nhật ở dưới cơ mà"
    if not bg_path.exists():
        # Box 1: Left IG
        draw.rounded_rectangle(
            [480, 780, 810, 860],
            radius=15,
            fill=(255, 255, 255, 120),
            outline=(255, 255, 255, 255),
            width=3
        )
        # Box 2: Right IG
        draw.rounded_rectangle(
            [850, 780, 1180, 860],
            radius=15,
            fill=(255, 255, 255, 120),
            outline=(255, 255, 255, 255),
            width=3
        )
    
    left_ig_str = f"ins / {proposer_ig}" if proposer_ig else "ins / chưa đặt"
    right_ig_str = f"ins / {target_ig}" if target_ig else "ins / chưa đặt"
    
    # Draw Instagram handles in bottom box corners (X = 350, 1320, Y = 810)
    draw.text((300,  810), left_ig_str,  fill=LIGHT_PINK, anchor="lm", font=font_regular)
    draw.text((1200, 810), right_ig_str, fill=LIGHT_PINK, anchor="rm", font=font_regular)
    
    # Draw custom saying centered in the middle of the bottom box at Y = 845
    if saying:
        font_saying = _vogue(24)
        draw.text((836, 845), saying, fill=PASTEL_PINK, anchor="mm", font=font_saying)
        
    # Draw joint wallet balance centered near the bottom of the box at Y = 880
    joint_wallet_str = f"Quỹ chung: {joint_wallet:,} VND"
    draw.text((836, 880), joint_wallet_str, fill=PASTEL_PINK, anchor="mm", font=font_regular)
    
    # Composite overlay on background
    bg.paste(overlay, (0, 0), mask=overlay)
    overlay.close()
    
    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    bg.close()
    return buf


class MarriageView(discord.ui.View):
    """View with Accept/Decline buttons for proposal flows."""
    def __init__(self, proposer: discord.User | discord.Member, target: discord.User | discord.Member, ring_id: str, economy: Economy):
        super().__init__(timeout=60.0)
        self.proposer = proposer
        self.target = target
        self.ring_id = ring_id
        self.economy = economy
        self.accepted = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Nút bấm này dành cho người được cầu hôn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="marry_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        self.stop()
        
        # Verify proposer still has the ring
        inventory = dict(self.economy.get_inventory(self.proposer.id))
        if inventory.get(self.ring_id, 0) <= 0:
            await interaction.response.send_message("❌ Người cầu hôn không còn sở hữu nhẫn cưới này để kết hôn!", ephemeral=True)
            return
            
        # Consume ring & execute marriage
        self.economy.add_inventory_item(self.proposer.id, self.ring_id, -1)
        self.economy.create_marriage(self.proposer.id, self.target.id, self.ring_id)
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Render and send certificate
        await interaction.channel.send("💘 **Đang lập giấy đăng ký kết hôn...**")
        buf = await asyncio.to_thread(render_marriage_certificate, self.proposer, self.target, self.ring_id)
        file = discord.File(fp=buf, filename="marriage_certificate.png")
        
        embed = make_embed(
            title="💖 CHÚC MỪNG HẠN PHÚC GIA ĐÌNH MỚI 💖",
            description=f"Chúc mừng **{self.proposer.mention}** và **{self.target.mention}** đã thề ước kết duyên vợ chồng thành công!",
            color=discord.Color.magenta()
        )
        embed.set_image(url="attachment://marriage_certificate.png")
        
        # Global divine alert
        if self.ring_id == "ring_divine":
            broadcast = (
                "🎇🎆✨ **THÔNG BÁO TOÀN SEVER** ✨🎆🎇\n"
                f"🎉💎 **CHÚC MỪNG HẠN PHÚC GIA ĐÌNH MỚI!** **{self.proposer.mention}** đã kết hôn cùng "
                f"**{self.target.mention}** bằng **Nhẫn Hào Quang Vĩnh Cửu** lấp lánh thần thánh sang trọng nhất! Trăm năm hạnh phúc! 💖🥂"
            )
            await interaction.channel.send(broadcast)
            
        await interaction.channel.send(embed=embed, file=file)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="marry_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = False
        self.stop()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"💔 **{self.target.mention}** đã từ chối lời cầu hôn của **{self.proposer.mention}**.")


class DivorceView(discord.ui.View):
    """View with Accept/Decline buttons for mutual divorce flows."""
    def __init__(self, initiator: discord.User | discord.Member, spouse: discord.User | discord.Member, economy: Economy):
        super().__init__(timeout=60.0)
        self.initiator = initiator
        self.spouse = spouse
        self.economy = economy
        self.confirmed = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.spouse.id:
            await interaction.response.send_message("❌ Chỉ người bạn đời mới có thể bấm xác nhận ly hôn đồng thuận!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="divorce_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Get marriage details to split joint wallet
        marriage = self.economy.get_marriage(self.initiator.id)
        if marriage:
            user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
            split = joint_wallet // 2
            
            # Delete marriage and return wallet cash
            self.economy.delete_marriage(user_one, user_two)
            if split > 0:
                self.economy.add_money(user_one, split)
                self.economy.add_money(user_two, split)
                
            desc = (
                f"💔 Hai bạn đã chính thức đường ai nấy đi.\n"
                f"🏦 **Quỹ chung chia đôi:** Mỗi người nhận lại `+{split:,} VND` vào tài khoản ví."
            )
        else:
            desc = "❌ Không tìm thấy thông tin hôn nhân để chia tài sản."
            
        embed = make_embed(
            title="💔 LY HÔN ĐỒNG THUẬN THÀNH CÔNG 💔",
            description=desc,
            color=discord.Color.red()
        )
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="divorce_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"❌ **{self.spouse.mention}** đã từ chối ký đơn ly hôn đồng thuận. Hãy dùng tùy chọn ly hôn đơn phương!")


class CoupleWithdrawView(discord.ui.View):
    """View with Accept/Decline buttons for couple joint wallet withdraw flows."""
    def __init__(self, proposer: discord.User | discord.Member, spouse: discord.User | discord.Member, amount: int, economy: Economy, ctx: commands.Context):
        super().__init__(timeout=60.0)
        self.proposer = proposer
        self.spouse = spouse
        self.amount = amount
        self.economy = economy
        self.ctx = ctx
        self.confirmed = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.spouse.id:
            await interaction.response.send_message("❌ Chỉ người bạn đời mới có thể xác nhận rút tiền!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="withdraw_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Double check marriage and wallet balance
        marriages = self.economy.get_marriages(self.proposer.id)
        marriage = None
        for m in marriages:
            m_user_one, m_user_two, *_ = m
            if self.spouse.id in (m_user_one, m_user_two):
                marriage = m
                break
                
        if not marriage:
            await interaction.channel.send("❌ Thất bại: Hôn nhân này không còn tồn tại!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if joint_wallet < self.amount:
            await interaction.channel.send(f"❌ Thất bại: Quỹ chung hiện tại không đủ để rút (Chỉ còn `{joint_wallet:,} VND`!)")
            return
            
        # Perform withdrawal
        self.economy.update_joint_wallet(user_one, user_two, -self.amount)
        self.economy.add_money(self.proposer.id, self.amount)
        
        log_wallet_change(
            logger,
            event="couple_joint_withdraw",
            user_id=self.proposer.id,
            money_delta=self.amount,
            joint_balance=joint_wallet - self.amount,
            ctx=self.ctx
        )
        
        embed = make_embed(
            title="🏦 RÚT TIỀN QUỸ CHUNG THÀNH CÔNG 🏦",
            description=(
                f"**{self.spouse.name}** đã đồng ý cho **{self.proposer.name}** rút tiền từ quỹ phu thê:\n\n"
                f"💰 **Nhận lại ví:** `+{self.amount:,} VND`\n"
                f"🏦 **Số dư quỹ chung còn lại:** `{joint_wallet - self.amount:,} VND`"
            ),
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="withdraw_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"❌ **{self.spouse.mention}** đã từ chối yêu cầu rút tiền phu thê của **{self.proposer.mention}**.")


class Marry(commands.Cog):
    """Cog for community Couple features and rewards."""
    def __init__(self, bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", Economy())

    async def is_admin_user(self, user) -> bool:
        if user.id in config.bot.owner_ids or user.id in config.bot.admin_ids:
            return True
        if user.id in self.bot.owner_ids:
            return True
        try:
            return await self.bot.is_owner(user)
        except Exception:
            return False

    def _resolve_marriage_and_args(self, user_id: int, args: list[str]) -> tuple[tuple | None, list[str]]:
        marriages = self.economy.get_marriages(user_id)
        if not marriages:
            return None, args
            
        if args and args[0].isdigit():
            idx = int(args[0])
            if 1 <= idx <= len(marriages):
                return marriages[idx - 1], args[1:]
                
        return marriages[0], args

    @commands.command(
        brief="Cầu hôn một người chơi khác trong server.",
        usage="marry @user"
    )
    async def marry(self, ctx: commands.Context, target: discord.Member):
        if target.bot:
            await ctx.send("❌ Bạn không thể kết hôn cùng bot!")
            return
            
        if target.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể kết hôn với chính bản thân mình!")
            return
            
        # Check active marriages limit
        author_marriages = self.economy.get_marriages(ctx.author.id)
        author_limit = 5 if await self.is_admin_user(ctx.author) else 1
        if len(author_marriages) >= author_limit:
            if author_limit == 1:
                await ctx.send("❌ Bạn đang trong một cuộc hôn nhân! Hãy ly hôn (i?divorce) trước khi đi tìm bến đỗ mới.")
            else:
                await ctx.send(f"❌ Bạn đã đạt giới hạn kết hôn tối đa là {author_limit} người cùng lúc!")
            return
            
        target_marriages = self.economy.get_marriages(target.id)
        target_limit = 5 if await self.is_admin_user(target) else 1
        if len(target_marriages) >= target_limit:
            if target_limit == 1:
                await ctx.send(f"❌ **{target.name}** đã kết hôn rồi! Đập chậu cướp hoa là hành vi trái đạo đức.")
            else:
                await ctx.send(f"❌ **{target.name}** đã đạt giới hạn kết hôn tối đa là {target_limit} người cùng lúc!")
            return

            
        # Check owned rings in inventory
        inventory = dict(self.economy.get_inventory(ctx.author.id))
        
        # Select best ring owned
        owned_rings = [k for k in RINGS.keys() if inventory.get(k, 0) > 0]
        if not owned_rings:
            await ctx.send("❌ **Bạn không sở hữu nhẫn cưới nào!** Hãy sử dụng `i?shop` để mua một chiếc nhẫn cầu hôn trước.")
            return
            
        # Prioritize divine > angel > gothic > sunburst > sapphire > ruby > citrine > cupid > amethyst > emerald > aquamarine > quartz > grass
        ring_priority = [
            "ring_divine",
            "ring_angel",
            "ring_gothic",
            "ring_sunburst",
            "ring_sapphire",
            "ring_ruby",
            "ring_citrine",
            "ring_cupid",
            "ring_amethyst",
            "ring_emerald",
            "ring_aquamarine",
            "ring_quartz",
            "ring_grass"
        ]
        ring_id = next(r for r in ring_priority if r in owned_rings)
        ring_name = RINGS[ring_id]
        
        view = MarriageView(ctx.author, target, ring_id, self.economy)
        embed = make_embed(
            title="💞 LỜI CẦU HÔN LÃNG MẠN 💞",
            description=(
                f"💍 **{ctx.author.mention}** đang quỳ xuống trao chiếc **{ring_name}** cầu hôn bạn đời **{target.mention}**!\n\n"
                f"*Bạn có đồng ý kết duyên trăm năm, đồng cam cộng khổ cùng họ không?*"
            ),
            color=discord.Color.magenta()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.group(name="couple", brief="Quản lý thông tin gia đình cặp đôi.", invoke_without_command=True)
    async def couple_cmd(self, ctx: commands.Context, index_or_user: str = None, index: int = None):
        # Displays the couple profile banner
        # Parse arguments
        target_user = ctx.author
        target_index = 1
        
        if index_or_user is not None:
            # Check if index_or_user is a number
            try:
                target_index = int(index_or_user)
            except ValueError:
                # Try parsing as user/member
                try:
                    target_user = await commands.MemberConverter().convert(ctx, index_or_user)
                except commands.BadArgument:
                    await ctx.send("❌ Người dùng không hợp lệ!")
                    return
                # If index is also provided
                if index is not None:
                    target_index = index
                    
        if target_index < 1:
            await ctx.send("❌ Chỉ số cặp đôi phải lớn hơn hoặc bằng 1!")
            return
            
        marriages = self.economy.get_marriages(target_user.id)
        if not marriages:
            if target_user.id == ctx.author.id:
                await ctx.send(f"❌ Bạn chưa kết hôn! Hãy sắm nhẫn cưới rồi cầu hôn ai đó bằng: `{config.bot.prefix}marry @user`")
            else:
                await ctx.send(f"❌ **{target_user.name}** chưa kết hôn!")
            return
            
        if target_index > len(marriages):
            if len(marriages) == 1:
                await ctx.send(f"❌ **{target_user.display_name}** chỉ có 1 cuộc hôn nhân!")
            else:
                await ctx.send(f"❌ **{target_user.display_name}** chỉ có {len(marriages)} cuộc hôn nhân! (Hãy nhập chỉ số từ 1 đến {len(marriages)})")
            return
            
        marriage = marriages[target_index - 1]
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
        # Get spouse object
        spouse_id = user_two if target_user.id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        if not spouse:
            # Fallback mock user if missing
            class FallbackUser:
                def __init__(self, uid):
                    self.id = uid
                    self.display_name = f"User_ID:{uid}"
                    self.display_avatar = self
                    self.url = "https://example.com/avatar.png"
            spouse = FallbackUser(spouse_id)
            
        married_days = max(1, (int(time.time()) - married_at) // 86400)
        
        loading_msg = await ctx.send("⌛ **Đang kết xuất thông tin gia đình...**")
        
        # Get IG handles
        ig_handles = self.economy.get_marriage_ig(user_one, user_two)
        # Determine which IG belongs to target_user and which to spouse
        if target_user.id == user_one:
            author_ig, spouse_ig = ig_handles[0], ig_handles[1]
        else:
            author_ig, spouse_ig = ig_handles[1], ig_handles[0]
            
        # Get custom status
        rel_status = self.economy.get_marriage_status(user_one, user_two)
        
        # Get custom saying
        saying = self.economy.get_marriage_saying(user_one, user_two)
        
        buf = await asyncio.to_thread(
            render_couple_banner, 
            target_user, 
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
        file = discord.File(fp=buf, filename="couple_profile.png")
        await ctx.send(file=file)
        
        try:
            await loading_msg.delete()
        except Exception:
            pass

    @couple_cmd.command(name="setig", aliases=["instagram", "ig"])
    async def couple_setig(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt tài khoản Instagram của bạn để hiển thị trên profile cặp đôi."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp tài khoản Instagram!")
            return
            
        ig_handle = remaining_args[0]
        # Clean handle (remove @ if present)
        clean_handle = ig_handle.strip().lstrip('@')
        if len(clean_handle) > 30:
            await ctx.send("❌ Tên tài khoản Instagram quá dài (tối đa 30 ký tự)!")
            return
            
        user_one, user_two = marriage[0], marriage[1]
        self.economy.update_marriage_ig(user_one, user_two, ctx.author.id, clean_handle)
        await ctx.send(f"✅ Đã cập nhật tài khoản Instagram của bạn thành: `ins / {clean_handle}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="status", aliases=["setstatus", "trangthai"])
    async def couple_status(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt trạng thái mối quan hệ của cặp đôi (ví dụ: situation ship, mãi bên nhau...)."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp trạng thái quan hệ!")
            return
            
        status_text = " ".join(remaining_args)
        clean_status = status_text.strip()
        if len(clean_status) > 20:
            await ctx.send("❌ Trạng thái mối quan hệ quá dài (tối đa 20 ký tự)!")
            return
            
        user_one, user_two = marriage[0], marriage[1]
        self.economy.update_marriage_status(user_one, user_two, clean_status)
        await ctx.send(f"✅ Đã cập nhật trạng thái mối quan hệ thành: `{clean_status}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="setsaying", aliases=["saying", "quote", "setquote", "slogan"])
    async def couple_setsaying(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt câu nói/slogan cho cặp đôi hiển thị ở khung dưới banner."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp câu nói!")
            return
            
        saying_text = " ".join(remaining_args)
        clean_saying = saying_text.strip()
        user_one, user_two = marriage[0], marriage[1]
        if clean_saying.lower() in ("xoa", "clear", "none"):
            self.economy.update_marriage_saying(user_one, user_two, "")
            await ctx.send("✅ Đã xóa câu nói của cặp đôi cho cuộc hôn nhân này!")
            return
            
        if len(clean_saying) > 100:
            await ctx.send("❌ Câu nói quá dài (tối đa 100 ký tự)!")
            return
            
        self.economy.update_marriage_saying(user_one, user_two, clean_saying)
        await ctx.send(f"✅ Đã cập nhật câu nói thành: `{clean_saying}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="deposit", aliases=["gop"])
    async def couple_deposit(self, ctx: commands.Context, *, args_str: str = ""):
        # Deposit to joint wallet
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể mở khóa và góp tiền vào quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if not remaining_args:
            await ctx.send("❌ Vui lòng nhập số tiền muốn góp!")
            return
            
        amount = remaining_args[0]
        # Get user cash balance
        profile_entry = self.economy.get_entry(ctx.author.id)
        user_cash = profile_entry[1]

        # Parse deposit amount
        if amount.lower() in ["all", "tất tay"]:
            money_val = user_cash
        else:
            try:
                # Custom parse multiplier like 100k, 1m
                val_str = amount.lower().replace("k", "000").replace("m", "000000").replace(",", "").replace(".", "")
                money_val = int(val_str)
            except Exception:
                await ctx.send("❌ Số tiền nhập vào không hợp lệ!")
                return
                
        if money_val <= 0:
            await ctx.send("❌ Số tiền góp phải lớn hơn 0.")
            return
            
        if user_cash < money_val:
            await ctx.send(f"❌ Bạn không đủ tiền! Bạn chỉ có `{user_cash:,} VND`.")
            return
            
        # Deduct cash
        self.economy.add_money(ctx.author.id, -money_val)
        new_joint = self.economy.update_joint_wallet(user_one, user_two, money_val)
        
        log_wallet_change(
            logger,
            event="couple_joint_deposit",
            user_id=ctx.author.id,
            money_delta=-money_val,
            joint_balance=new_joint,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🏦 GÓP TIỀN QUỸ CHUNG THÀNH CÔNG 🏦",
            description=(
                f"**{ctx.author.name}** đã góp thành công vào quỹ gia đình:\n\n"
                f"💸 **Tiền góp:** `-{money_val:,} VND`\n"
                f"🏦 **Số dư quỹ chung mới:** `{new_joint:,} VND`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @couple_cmd.command(name="withdraw", aliases=["rut"])
    async def couple_withdraw(self, ctx: commands.Context, *, args_str: str = ""):
        # Withdraw from joint wallet
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể rút tiền từ quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if not remaining_args:
            await ctx.send("❌ Vui lòng nhập số tiền muốn rút!")
            return
            
        amount = remaining_args[0]
        # Parse withdraw amount
        if amount.lower() == "all" or amount.lower() == "tất tay":
            money_val = joint_wallet
        else:
            try:
                # Custom parse multiplier like 100k, 1m
                val_str = amount.lower().replace("k", "000").replace("m", "000000").replace(",", "").replace(".", "")
                money_val = int(val_str)
            except Exception:
                await ctx.send("❌ Số tiền nhập vào không hợp lệ!")
                return
                
        if money_val <= 0:
            await ctx.send("❌ Số tiền rút phải lớn hơn 0.")
            return
            
        if joint_wallet < money_val:
            await ctx.send(f"❌ Quỹ chung không đủ tiền! Quỹ chỉ có `{joint_wallet:,} VND`.")
            return
            
        # Get spouse object
        spouse_id = user_two if ctx.author.id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try:
                spouse = await self.bot.fetch_user(spouse_id)
            except Exception:
                pass
            
        if not spouse:
            await ctx.send("❌ Không thể tìm thấy thông tin bạn đời để yêu cầu đồng ý!")
            return
            
        view = CoupleWithdrawView(ctx.author, spouse, money_val, self.economy, ctx)
        embed = make_embed(
            title="🏦 YÊU CẦU RÚT TIỀN QUỸ PHU THÊ 🏦",
            description=(
                f"💍 **{ctx.author.mention}** muốn rút **`{money_val:,} VND`** từ quỹ chung.\n\n"
                f"🔔 Bạn đời **{spouse.mention}** vui lòng xác nhận đồng ý hoặc từ chối yêu cầu này!"
            ),
            color=discord.Color.magenta()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


    async def process_interact(self, ctx: commands.Context, target: discord.Member, action: str, emoji: str, action_type: str):
        marriages = self.economy.get_marriages(ctx.author.id)
        if not marriages:
            await ctx.send(f"❌ Lệnh tương tác cặp đôi chỉ dành cho người đã kết hôn!")
            return
            
        # Find active marriage matching this target spouse
        active_marriage = None
        for m in marriages:
            m_user_one, m_user_two, *_ = m
            m_spouse_id = m_user_two if ctx.author.id == m_user_one else m_user_one
            if target.id == m_spouse_id:
                active_marriage = m
                break
                
        if not active_marriage:
            # Adultery (target is not one of active spouses)
            deduct_pts = 10
            
            # Deduct points from all marriages
            last_new_pts = 0
            for m in marriages:
                m_user_one, m_user_two, *_ = m
                last_new_pts = self.economy.deduct_love_points(m_user_one, m_user_two, deduct_pts)
                
            spouse_mentions = []
            for m in marriages:
                m_user_one, m_user_two, *_ = m
                m_spouse_id = m_user_two if ctx.author.id == m_user_one else m_user_one
                spouse_mentions.append(f"<@{m_spouse_id}>")
            spouse_list_str = " hoặc ".join(spouse_mentions)
            
            embed = make_embed(
                title="💔 PHÁT HIỆN NGOẠI TÌNH 💔",
                description=(
                    f"⚠️ **{ctx.author.mention}** đã tương tác thân mật ({action}) với **{target.mention}** "
                    f"trong khi đã kết hôn cùng {spouse_list_str}!\n\n"
                    f"💔 **Hành vi ngoại tình bị phát hiện!**\n"
                    f"📉 Toàn bộ gia đình của bạn bị phạt trừ `-{deduct_pts}` Điểm thân mật.\n"
                    f"💞 **Điểm thân mật hiện tại (couple gần nhất):** `{last_new_pts}` điểm."
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today = active_marriage

            
        # Try to add love points
        now = int(time.time())
        points_to_add = 10 if action_type == "Fuck" else 5
        old_love_points = love_points
        new_points, success = self.economy.add_love_points(user_one, user_two, points_to_add, now)
        added_points = new_points - old_love_points
        
        if success and added_points > 0:
            pts_msg = f" Bạn nhận được `+{added_points} Điểm thân mật` (Giới hạn tối đa 20 điểm/ngày)."
        else:
            pts_msg = " (Hôm nay hai bạn đã đạt giới hạn tối đa 20 Điểm thân mật)."
            
        embed_desc = f"{emoji} **{ctx.author.name}** đã trao một {action} nồng thắm cho bạn đời của mình **{target.name}**!{pts_msg}"
        sayings = INTERACT_SAYINGS.get(action_type, [])
        if sayings:
            saying = random.choice(sayings)
            embed_desc += f"\n\n*\" {saying} \"*"
            
        embed = make_embed(
            description=embed_desc,
            color=discord.Color.magenta()
        )
        
        gif_dir = ABS_PATH.parent.parent / "pictures" / "Marry" / action_type
        file = None
        if gif_dir.exists() and gif_dir.is_dir():
            gifs = list(gif_dir.glob("*.gif"))
            if gifs:
                chosen_gif = random.choice(gifs)
                file = discord.File(str(chosen_gif), filename="interact.gif")
                embed.set_image(url="attachment://interact.gif")
                
        if file:
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)

    @commands.command(brief="Ôm bạn đời của mình.")
    async def hug(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái ôm ấm áp", "🤗", "Hug")

    @commands.command(brief="Hôn bạn đời của mình.")
    async def kiss(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "nụ hôn nồng cháy", "💋", "Kiss")

    @commands.command(brief="Xoa đầu bạn đời của mình.")
    async def pat(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái xoa đầu ngọt ngào", "👋", "Pat")

    @commands.command(brief="Ân ái nồng cháy với bạn đời của mình.")
    async def fuck(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cuộc ân ái nồng cháy", "🔞", "Fuck")

    @commands.command(
        brief="Hủy bỏ cuộc hôn nhân hiện tại (Ly hôn).",
        usage="divorce [chỉ_số]"
    )
    async def divorce(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn thì ly hôn cái gì?")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        # Find index of this marriage
        marriages = self.economy.get_marriages(ctx.author.id)
        idx = marriages.index(marriage) + 1
        
        # Give two options
        # We check author cash for Unilateral divorce
        author_profile = self.economy.get_entry(ctx.author.id)
        cash = author_profile[1]
        
        unilateral_cost = max(10_000_000, int(cash * 0.10))
        
        embed = make_embed(
            title="💔 ĐƠN LY HÔN (DIVORCE MENU) 💔",
            description=(
                f"Bạn đang yêu cầu chấm dứt hôn nhân cùng <@{spouse_id}>.\n\n"
                f"Hãy chọn một trong hai phương án giải quyết dưới đây:\n"
                f"1️⃣ **Ly hôn Đồng Thuận (Mutual):** Gõ `i?divorcemutual {idx}` (Cả hai cùng ký đơn, không mất phí, quỹ chung chia đôi).\n"
                f"2️⃣ **Ly hôn Đơn Phương (Unilateral):** Gõ `i?divorceforce {idx}` (Không cần bên kia đồng ý, án phí tòa án rất đắt: **{unilateral_cost:,} VND** (10% ví của bạn), 50% án phí sẽ đền bù cho bạn đời của bạn)."
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name="divorcemutual", aliases=["divorce_mutual", "divmutual"], hidden=True)
    async def divorce_mutual(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            return
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        view = DivorceView(ctx.author, spouse, self.economy)
        embed = make_embed(
            title="📜 ĐƠN LY HÔN ĐỒNG THUẬN 📜",
            description=f"**{ctx.author.mention}** đề xuất ly hôn đồng thuận. Mời **{spouse.mention}** bấm nút ký đơn để xác nhận giải tán gia đình.",
            color=discord.Color.red()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="divorceforce", aliases=["divorce_force", "divforce"], hidden=True)
    async def divorce_force(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            return
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        author_profile = self.economy.get_entry(ctx.author.id)
        cash = author_profile[1]
        
        unilateral_cost = max(10_000_000, int(cash * 0.10))
        if cash < unilateral_cost:
            await ctx.send(f"❌ Bạn không đủ tiền mặt trong ví để trả án phí ly hôn đơn phương! Cần `{unilateral_cost:,} VND` nhưng bạn chỉ có `{cash:,} VND`.")
            return
            
        # Execute force divorce
        split = joint_wallet // 2
        self.economy.delete_marriage(user_one, user_two)
        
        # Apply economic penalty
        self.economy.add_money(ctx.author.id, -unilateral_cost)
        # 50% of the penalty is compensated to the spouse
        compensation = unilateral_cost // 2
        self.economy.add_money(spouse_id, compensation)
        
        # Split joint wallet
        if split > 0:
            self.economy.add_money(user_one, split)
            self.economy.add_money(user_two, split)
            
        log_wallet_change(
            logger,
            event="couple_divorce_force",
            user_id=ctx.author.id,
            money_delta=-unilateral_cost,
            spouse_id=spouse_id,
            compensation=compensation,
            split=split,
            ctx=ctx
        )
        
        embed = make_embed(
            title="💔 LY HÔN ĐƠN PHƯƠNG THÀNH CÔNG 💔",
            description=(
                f"**{ctx.author.mention}** đã đơn phương ly hôn cùng bạn đời.\n\n"
                f"💸 **Án phí khấu trừ:** `-{unilateral_cost:,} VND` từ ví của bạn.\n"
                f"🎁 **Bồi thường tổn thất phu thê:** chuyển `+{compensation:,} VND` cho <@{spouse_id}>.\n"
                f"🏦 **Quỹ chung chia đôi:** Mỗi người nhận lại `+{split:,} VND`."
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)


    # ── ADMIN COMMANDS ──────────────────────────────────────────────────────────

    @commands.command(
        name="admindel_marry",
        aliases=["admin_divorce", "xoahonnhan"],
        brief="[ADMIN] Xoá hôn nhân của một người dùng bất kỳ.",
        usage="admindel_marry @user",
        hidden=True
    )
    async def admin_delete_marriage(self, ctx: commands.Context, target: str):
        """
        [ADMIN] Xoá toàn bộ hôn nhân của người dùng được chỉ định (bằng ID hoặc ping) mà không mất phí.
        Lệnh này dành cho Admin của server hoặc Chủ bot. Không có bồi thường và không có thông báo cho đương sự.
        """
        is_owner = ctx.author.id in config.bot.owner_ids or await ctx.bot.is_owner(ctx.author)
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        if not (is_owner or is_admin):
            await ctx.send("❌ **Lỗi:** Lệnh này chỉ dành cho Admin của server hoặc Chủ bot!")
            return

        # Parse ID from ping or get raw ID
        target_clean = target.strip("<@!>")
        try:
            target_id = int(target_clean)
        except ValueError:
            await ctx.send("❌ **Lỗi:** Định dạng ID hoặc tag người dùng không hợp lệ!")
            return

        marriage = self.economy.get_marriage(target_id)
        if not marriage:
            await ctx.send(
                embed=make_embed(
                    title="❌ Không tìm thấy hôn nhân",
                    description=f"Người dùng có ID **{target_id}** hiện không có hôn nhân nào trong hệ thống.",
                    color=discord.Color.red()
                )
            )
            return

        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage

        # Resolve spouse
        spouse_id = user_two if target_id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        spouse_name = spouse.name if spouse else f"ID:{spouse_id}"

        ring_name = RINGS.get(ring_type, ring_type)
        days = max(1, (int(time.time()) - married_at) // 86400)

        # Delete marriage record
        self.economy.delete_marriage(user_one, user_two)

        logger.warning(
            f"[ADMIN] {ctx.author} deleted marriage between "
            f"user_one={user_one} and user_two={user_two} "
            f"(ring={ring_type}, days={days}, joint_wallet={joint_wallet})"
        )

        embed = make_embed(
            title="🗑️ HÔN NHÂN ĐÃ BỊ XOÁ (ADMIN)",
            description=(
                f"Đã xoá thành công hôn nhân của cặp đôi:\n\n"
                f"👤 **Người 1:** <@{user_one}> (ID: `{user_one}`)\n"
                f"👤 **Người 2:** <@{user_two}> (ID: `{user_two}`)\n"
                f"💍 **Nhẫn:** {ring_name}\n"
                f"📅 **Thời gian kết hôn:** {days:,} ngày\n"
                f"🏦 **Quỹ chung bị xoá:** {joint_wallet:,} VND *(không hoàn trả)*\n\n"
                f"⚠️ *Cặp đôi sẽ không nhận được thông báo tự động.*"
            ),
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Thực hiện bởi Admin: {ctx.author} | {ctx.author.id}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Marry(bot))
