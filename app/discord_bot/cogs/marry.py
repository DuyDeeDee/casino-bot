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


def render_couple_banner(proposer, target, ring_type: str, love_points: int, joint_wallet: int, married_days: int, proposer_ig: str = "", target_ig: str = "", relationship_status: str = "Vợ Chồng", married_at: int = 0) -> BytesIO:
    """Draws a beautiful custom profile banner for married couples using the template."""
    bg_path = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_marry.png"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
    else:
        # Fallback to plain pink background of same dimensions
        bg = Image.new("RGBA", (1672, 941), (252, 229, 237, 255))
        
    width, height = bg.size
    
    # Create overlay for transparent drawing
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Load fonts (Roboto or fallback)
    font_large = load_font("bold", 36)
    font_medium = load_font("bold", 26)
    font_regular = load_font("bold", 22)
    
    # 1. Load and process avatars (cropped circles of diameter 356, radius 178)
    p_avatar = get_avatar_img(proposer)
    t_avatar = get_avatar_img(target)
    
    p_circle = crop_circle(p_avatar, 356)
    t_circle = crop_circle(t_avatar, 356)
    
    # Paste avatars centered at (412, 530) and (1260, 530)
    overlay.paste(p_circle, (412 - 178, 530 - 178), mask=p_circle)
    overlay.paste(t_circle, (1260 - 178, 530 - 178), mask=t_circle)
    
    p_avatar.close()
    t_avatar.close()
    p_circle.close()
    t_circle.close()
    
    # 2. Draw display names inside nameplate boxes above avatars
    # Left name at (412, 310)
    draw.text((412, 310), proposer.display_name, fill=(255, 255, 255, 255), anchor="mm", font=font_large)
    # Right name at (1260, 310)
    draw.text((1260, 310), target.display_name, fill=(255, 255, 255, 255), anchor="mm", font=font_large)
    
    # 3. Draw Discord usernames in boxes below avatars
    # Left username at (412, 740)
    draw.text((412, 740), proposer.name, fill=(138, 43, 226, 255), anchor="mm", font=font_medium)
    # Right username at (1260, 740)
    draw.text((1260, 740), target.name, fill=(138, 43, 226, 255), anchor="mm", font=font_medium)
    
    # 4. Draw Custom Relationship Status centered above the heart
    draw.text((836, 450), relationship_status, fill=(138, 43, 226, 255), anchor="mm", font=font_medium)
    
    # 5. Draw stats centered below the heart
    date_str = "Chưa rõ"
    if married_at > 0:
        date_str = datetime.fromtimestamp(married_at).strftime("%d/%m/%Y")
    
    draw.text((836, 680), f"Ngày Kết Hôn : {date_str}", fill=(255, 255, 255, 255), anchor="mm", font=font_regular)
    draw.text((836, 720), f"Đã Kết Hôn : {married_days} ngày", fill=(255, 255, 255, 255), anchor="mm", font=font_regular)
    draw.text((836, 760), f"Điểm thân mật : {love_points:,}", fill=(255, 255, 255, 255), anchor="mm", font=font_regular)
    
    # 6. Load and paste Ring image at bottom left (centered at 306, 799)
    ring_file = RING_IMAGES.get(ring_type)
    if ring_file:
        ring_path = ABS_PATH.parent.parent / "pictures" / "Marry" / ring_file
        if ring_path.exists():
            try:
                ring_img = Image.open(ring_path).convert("RGBA")
                ring_img = ring_img.resize((120, 120), Image.Resampling.LANCZOS)
                overlay.paste(ring_img, (306 - 60, 799 - 60), mask=ring_img)
                ring_img.close()
            except Exception as e:
                logger.error(f"Failed to draw wedding ring image: {e}")
                
    # 7. Draw social boxes and Instagram handles at bottom middle
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
    
    draw.text((645, 820), left_ig_str, fill=(255, 255, 255, 255), anchor="mm", font=font_regular)
    draw.text((1015, 820), right_ig_str, fill=(255, 255, 255, 255), anchor="mm", font=font_regular)
    
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


class Marry(commands.Cog):
    """Cog for community Couple features and rewards."""
    def __init__(self, bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", Economy())

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
            
        # Check active marriages
        marriage_author = self.economy.get_marriage(ctx.author.id)
        if marriage_author:
            await ctx.send("❌ Bạn đang trong một cuộc hôn nhân! Hãy ly hôn (i?divorce) trước khi đi tìm bến đỗ mới.")
            return
            
        marriage_target = self.economy.get_marriage(target.id)
        if marriage_target:
            await ctx.send(f"❌ **{target.name}** đã kết hôn rồi! Đập chậu cướp hoa là hành vi trái đạo đức.")
            return
            
        # Check owned rings in inventory
        inventory = dict(self.economy.get_inventory(ctx.author.id))
        
        # Select best ring owned
        owned_rings = [k for k in RINGS.keys() if inventory.get(k, 0) > 0]
        if not owned_rings:
            await ctx.send("❌ **Bạn không sở hữu nhẫn cưới nào!** Hãy sử dụng `i?shop` để mua một chiếc nhẫn cầu hôn trước.")
            return
            
        # Prioritize divine > angel > gothic > sunburst > sapphire > ruby > citrine > cupid > amethyst > emerald > aquamarine > quartz
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
            "ring_quartz"
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
    async def couple_cmd(self, ctx: commands.Context):
        # Displays the couple profile banner
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send(f"❌ Bạn chưa kết hôn! Hãy sắm nhẫn cưới rồi cầu hôn ai đó bằng: `{config.bot.prefix}marry @user`")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
        # Get users objects
        spouse_id = user_two if ctx.author.id == user_one else user_one
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
        
        await ctx.send("⌛ **Đang kết xuất thông tin gia đình...**")
        
        # Get IG handles
        ig_handles = self.economy.get_marriage_ig(ctx.author.id)
        # Determine which IG belongs to author and which to spouse
        if ctx.author.id == user_one:
            author_ig, spouse_ig = ig_handles[0], ig_handles[1]
        else:
            author_ig, spouse_ig = ig_handles[1], ig_handles[0]
            
        # Get custom status
        rel_status = self.economy.get_marriage_status(ctx.author.id)
        
        buf = await asyncio.to_thread(
            render_couple_banner, 
            ctx.author, 
            spouse, 
            ring_type, 
            love_points, 
            joint_wallet, 
            married_days,
            author_ig,
            spouse_ig,
            rel_status,
            married_at
        )
        file = discord.File(fp=buf, filename="couple_profile.png")
        
        embed = make_embed(
            title="💖 TRANG CÁ NHÂN PHU THÊ 💖",
            color=discord.Color.magenta()
        )
        embed.set_image(url="attachment://couple_profile.png")
        await ctx.send(embed=embed, file=file)

    @couple_cmd.command(name="setig", aliases=["instagram", "ig"])
    async def couple_setig(self, ctx: commands.Context, ig_handle: str):
        """Đặt tài khoản Instagram của bạn để hiển thị trên profile cặp đôi."""
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể cài đặt tài khoản Instagram!")
            return
            
        # Clean handle (remove @ if present)
        clean_handle = ig_handle.strip().lstrip('@')
        if len(clean_handle) > 30:
            await ctx.send("❌ Tên tài khoản Instagram quá dài (tối đa 30 ký tự)!")
            return
            
        self.economy.update_marriage_ig(ctx.author.id, clean_handle)
        await ctx.send(f"✅ Đã cập nhật tài khoản Instagram của bạn thành: `ins / {clean_handle}`!")

    @couple_cmd.command(name="status", aliases=["setstatus", "trangthai"])
    async def couple_status(self, ctx: commands.Context, *, status_text: str):
        """Đặt trạng thái mối quan hệ của cặp đôi (ví dụ: situation ship, mãi bên nhau...)."""
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể đặt trạng thái mối quan hệ!")
            return
            
        clean_status = status_text.strip()
        if len(clean_status) > 20:
            await ctx.send("❌ Trạng thái mối quan hệ quá dài (tối đa 20 ký tự)!")
            return
            
        self.economy.update_marriage_status(ctx.author.id, clean_status)
        await ctx.send(f"✅ Đã cập nhật trạng thái mối quan hệ thành: `{clean_status}`!")

    @couple_cmd.command(name="deposit", aliases=["gop"])
    async def couple_deposit(self, ctx: commands.Context, amount: str):
        # Deposit to joint wallet
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể mở khóa và góp tiền vào quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
        # Parse amount
        # Handle 'all' capping at max
        from app.discord_bot.modules.betting import validate_money_bet
        try:
            money_val, _ = validate_money_bet(self.economy, ctx.author.id, amount)
        except Exception as e:
            await ctx.send(f"❌ **Lỗi tiền cược:** {e}")
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
    async def couple_withdraw(self, ctx: commands.Context, amount: str):
        # Withdraw from joint wallet
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể rút tiền từ quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
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
            
        # Perform withdrawal
        self.economy.update_joint_wallet(user_one, user_two, -money_val)
        self.economy.add_money(ctx.author.id, money_val)
        
        log_wallet_change(
            logger,
            event="couple_joint_withdraw",
            user_id=ctx.author.id,
            money_delta=money_val,
            joint_balance=joint_wallet - money_val,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🏦 RÚT TIỀN QUỸ CHUNG THÀNH CÔNG 🏦",
            description=(
                f"**{ctx.author.name}** đã rút thành công tiền từ quỹ phu thê:\n\n"
                f"💰 **Nhận lại ví:** `+{money_val:,} VND`\n"
                f"🏦 **Số dư quỹ chung còn lại:** `{joint_wallet - money_val:,} VND`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # Love points daily interaction commands
    async def process_interact(self, ctx: commands.Context, target: discord.Member, action: str, emoji: str):
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send(f"❌ Lệnh tương tác cặp đôi chỉ dành cho người đã kết hôn!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        if target.id != spouse_id:
            await ctx.send(f"❌ Bạn chỉ có thể tương tác thân mật cùng vợ/chồng của mình (<@{spouse_id}>)!")
            return
            
        # Try to add love points
        now = int(time.time())
        new_points, success = self.economy.add_love_points(user_one, user_two, 5, now)
        
        if success:
            pts_msg = " Bạn nhận được `+5 Điểm thân mật` (Giới hạn tối đa 20 điểm/ngày)."
        else:
            pts_msg = " (Hôm nay hai bạn đã đạt giới hạn tối đa 20 Điểm thân mật)."
            
        await ctx.send(
            f"{emoji} **{ctx.author.name}** đã trao một {action} nồng thắm cho bạn đời của mình **{target.name}**!{pts_msg}"
        )

    @commands.command(brief="Ôm bạn đời của mình.")
    async def hug(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái ôm ấm áp", "🤗")

    @commands.command(brief="Hôn bạn đời của mình.")
    async def kiss(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "nụ hôn nồng cháy", "💋")

    @commands.command(brief="Xoa đầu bạn đời của mình.")
    async def pat(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái xoa đầu ngọt ngào", "👋")

    @commands.command(
        brief="Hủy bỏ cuộc hôn nhân hiện tại (Ly hôn).",
        usage="divorce"
    )
    async def divorce(self, ctx: commands.Context):
        marriage = self.economy.get_marriage(ctx.author.id)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn thì ly hôn cái gì?")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
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
                f"1️⃣ **Ly hôn Đồng Thuận (Mutual):** Gõ `i?divorcemutual` (Cả hai cùng ký đơn, không mất phí, quỹ chung chia đôi).\n"
                f"2️⃣ **Ly hôn Đơn Phương (Unilateral):** Gõ `i?divorceforce` (Không cần bên kia đồng ý, án phí tòa án rất đắt: **{unilateral_cost:,} VND** (10% ví của bạn), 50% án phí sẽ đền bù cho bạn đời của bạn)."
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name="divorcemutual", aliases=["divorce_mutual", "divmutual"], hidden=True)
    async def divorce_mutual(self, ctx: commands.Context):
        marriage = self.economy.get_marriage(ctx.author.id)
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
    async def divorce_force(self, ctx: commands.Context):
        marriage = self.economy.get_marriage(ctx.author.id)
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
                f"**{ctx.author.name}** đã đơn phương ly hôn cùng bạn đời.\n\n"
                f"💸 **Án phí khấu trừ:** `-{unilateral_cost:,} VND` từ ví của bạn.\n"
                f"🎁 **Bồi thường tổn thất phu thê:** chuyển `+{compensation:,} VND` cho <@{spouse_id}>.\n"
                f"🏦 **Quỹ chung chia đôi:** Mỗi người nhận lại `+{split:,} VND`."
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Marry(bot))
