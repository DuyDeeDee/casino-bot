import logging
import urllib.request
import os
import aiohttp
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.config import config

logger = logging.getLogger(__name__)

def get_font_path(font_type: str) -> Path:
    """Gets local path to Roboto font, downloading it if not present."""
    font_dir = Path(config.storage.data_dir) / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"Roboto-{font_type.capitalize()}.ttf"
    font_path = font_dir / filename
    
    if not font_path.exists():
        mapped_name = "Regular" if font_type.lower() == "regular" else "Bold"
        url = f"https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-{mapped_name}.ttf"
        try:
            logger.info(f"Downloading premium font from {url} to {font_path}...")
            urllib.request.urlretrieve(url, str(font_path))
        except Exception as e:
            logger.error(f"Failed to download font: {e}")
            
    return font_path

def load_font(font_type: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempts to load Outfit, falls back to system fonts, and finally default PIL font."""
    font_path = get_font_path(font_type)
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    fallbacks = []
    if os.name == 'nt':  # Windows
        if font_type == 'bold':
            fallbacks.extend(["arialbd.ttf", "segoeuib.ttf"])
        else:
            fallbacks.extend(["arial.ttf", "segoeui.ttf"])
    else:  # Linux/Mac
        fallbacks.extend([
            "DejaVuSans-Bold.ttf" if font_type == 'bold' else "DejaVuSans.ttf",
            "LiberationSans-Bold.ttf" if font_type == 'bold' else "LiberationSans-Regular.ttf",
            "FreeSansBold.ttf" if font_type == 'bold' else "FreeSans.ttf"
        ])
        
    for f in fallbacks:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            try:
                if os.name == 'nt':
                    p = Path("C:/Windows/Fonts") / f
                else:
                    p = Path("/usr/share/fonts/truetype") / f
                if p.exists():
                    return ImageFont.truetype(str(p), size)
            except Exception:
                pass
                
    return ImageFont.load_default()

async def fetch_avatar(url: str) -> bytes | None:
    """Asynchronously fetches the user's avatar image bytes."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.error(f"Failed to fetch avatar: {e}")
    return None

def format_money_short(val: int) -> str:
    """Formats large money values into short forms like 1.5M, 2.3B."""
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f}B VND"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M VND"
    return f"{val:,} VND"

def get_rank_info(net_worth: int) -> tuple[str, tuple[int, int, int], tuple[int, int, int]]:
    """Returns (rank_name, fill_color, text_color)."""
    if net_worth < 1_000_000:
        return "Con Nợ Quốc Dân", (139, 0, 0), (255, 255, 255) # Dark Red
    elif net_worth < 10_000_000:
        return "Dân Chơi Mới Nổi", (70, 130, 180), (255, 255, 255) # Steel Blue
    elif net_worth < 50_000_000:
        return "Thần Bài Bình Dân", (46, 139, 87), (255, 255, 255) # Sea Green
    elif net_worth < 200_000_000:
        return "Đại Gia Thành Phố", (218, 165, 32), (0, 0, 0) # Goldenrod
    elif net_worth < 1_000_000_000:
        return "Triệu Phú Sòng Bài", (186, 85, 211), (255, 255, 255) # Medium Orchid
    else:
        return "Tỷ Phú Đô La", (255, 69, 0), (255, 255, 255) # Red-Orange

def strip_emoji(text: str | None) -> str:
    """Removes emojis and special characters from title string for clean PIL rendering."""
    if not text:
        return ""
    return "".join(c for c in text if ord(c) < 0x2000 or 0x20A0 <= ord(c) <= 0x20CF).strip()

def draw_profile_content(
    img: Image.Image,
    draw: ImageDraw.Draw,
    avatar_img: Image.Image | None,
    username: str,
    money: int,
    gold: int,
    gold_price: int,
    loan_amount: int,
    biz_count: int,
    inv_count: int,
    rl_title: str | None = None,
    daga_title: str | None = None,
    cf_title: str | None = None
) -> None:
    width, height = img.size
    
    # Create a transparent overlay image for drawing everything to blend properly
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    
    # 1. Draw glowing outline border
    overlay_draw.rounded_rectangle([6, 6, width - 6, height - 6], radius=16, outline=(255, 215, 0, 80), width=3)
    
    # 2. Draw Avatar
    avatar_size = 180
    avatar_x, avatar_y = 40, 70
    
    if avatar_img:
        # Make circle mask
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
        
        # Paste avatar circular
        avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        avatar_circle.paste(avatar_img, (0, 0), mask=mask)
        overlay.paste(avatar_circle, (avatar_x, avatar_y), mask=avatar_circle)
        avatar_circle.close()
        mask.close()
    else:
        # Fallback placeholder circle
        overlay_draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=(100, 100, 100, 255))
        
    # Avatar gold border
    overlay_draw.ellipse([avatar_x - 3, avatar_y - 3, avatar_x + avatar_size + 3, avatar_y + avatar_size + 3], outline=(255, 215, 0, 180), width=4)
    
    # 3. Load Fonts
    font_title = load_font("bold", 34)
    font_badge = load_font("bold", 17)
    font_widget_title = load_font("regular", 11)
    font_widget_val = load_font("bold", 15)

    # Draw Username under the avatar, centered horizontally at x = 130
    username_font = font_title
    try:
        username_w = username_font.getlength(username)
    except AttributeError:
        username_w = len(username) * 20
        
    if username_w > 200:
        username_font = load_font("bold", 24)
        try:
            username_w = username_font.getlength(username)
        except AttributeError:
            username_w = len(username) * 14
            
    username_x = 130 - int(username_w // 2)
    username_y = 265
    overlay_draw.text((username_x, username_y), username, font=username_font, fill=(255, 255, 255, 255))
    
    # 5. Gather Badges
    raw_badges = []
    
    # Wealth Badge
    net_worth = money + (gold * gold_price) - loan_amount
    rank_name, badge_bg, badge_fg = get_rank_info(net_worth)
    raw_badges.append((rank_name, badge_bg, badge_fg))
    
    # Roulette Title Badge
    if rl_title:
        clean_rl = strip_emoji(rl_title)
        if clean_rl:
            if "Huyền Thoại" in clean_rl:
                rl_bg = (75, 0, 130)  # Indigo
            elif "Vua" in clean_rl:
                rl_bg = (25, 25, 112)  # Midnight Blue
            elif "Cao Thủ" in clean_rl:
                rl_bg = (184, 134, 11)  # Dark Goldenrod
            elif "Con Cưng" in clean_rl:
                rl_bg = (112, 128, 144)  # Slate Gray
            else:
                rl_bg = (160, 82, 45)  # Sienna
            raw_badges.append((clean_rl, rl_bg, (255, 255, 255)))
            
    # Daga Title Badge
    if daga_title:
        clean_daga = strip_emoji(daga_title)
        if clean_daga and clean_daga not in ["Chưa xuất trận", "Người mới"]:
            if "Huyền Thoại" in clean_daga:
                dg_bg = (148, 0, 211)  # Dark Violet
            elif "Đại Sư Kê" in clean_daga:
                dg_bg = (218, 165, 32)  # Goldenrod
            elif "Sư Kê" in clean_daga:
                dg_bg = (178, 34, 34)  # Firebrick
            elif "Chiến Kê" in clean_daga:
                dg_bg = (255, 140, 0)  # Dark Orange
            elif "Tân Binh" in clean_daga:
                dg_bg = (46, 139, 87)  # Sea Green
            else:
                dg_bg = (105, 105, 105)  # Dim Gray
            raw_badges.append((clean_daga, dg_bg, (255, 255, 255)))
            
    # Coin Flip Title Badge
    if cf_title:
        clean_cf = strip_emoji(cf_title)
        if clean_cf:
            if "Vua" in clean_cf:
                cf_bg = (25, 25, 112)  # Midnight Blue
            elif "Cao Thủ" in clean_cf:
                cf_bg = (184, 134, 11)  # Dark Goldenrod
            elif "Thần May" in clean_cf:
                cf_bg = (46, 139, 87)  # Sea Green
            else:
                cf_bg = (160, 82, 45)  # Sienna
            raw_badges.append((clean_cf, cf_bg, (255, 255, 255)))

    # Loan Warning Badge
    if loan_amount > 0:
        loan_text = f"Nợ: -{format_money_short(loan_amount)}"
        raw_badges.append((loan_text, (139, 0, 0), (255, 255, 255)))

    # Resolve image or text format for each badge
    badges = []
    badge_dir = Path("pictures/danh hiệu")
    
    for text, bg_color, fg_color in raw_badges:
        badge_path = None
        if badge_dir.exists():
            filenames_to_try = [f"{text}.png", f"{text.lower()}.png", f"{text.strip().lower()}.png"]
            for fname in filenames_to_try:
                p = badge_dir / fname
                if p.exists():
                    badge_path = p
                    break
                    
        if badge_path:
            try:
                with Image.open(badge_path) as b_img:
                    # Auto-crop transparent boundaries
                    bbox = b_img.getbbox()
                    if bbox:
                        b_img = b_img.crop(bbox)
                    w, h = b_img.size
                    # Scale to a prominent height
                    scaled_h = 180
                    scaled_w = int(w * (scaled_h / h)) if h > 0 else scaled_h
                    
                    # Cap width to fit within center area of the right side (max 460px)
                    max_w = 460
                    if scaled_w > max_w:
                        scaled_h = int(scaled_h * (max_w / scaled_w))
                        scaled_w = max_w
                        
                badges.append({
                    "text": text,
                    "bg_color": bg_color,
                    "fg_color": fg_color,
                    "path": badge_path,
                    "width": scaled_w,
                    "height": scaled_h,
                    "is_image": True
                })
            except Exception as e:
                logger.error(f"Error loading badge image {badge_path}: {e}")
                badge_path = None
                
        if not badge_path:
            try:
                text_w = font_badge.getlength(text)
            except AttributeError:
                text_w = len(text) * 10
            badge_w = int(text_w + 24)
            badges.append({
                "text": text,
                "bg_color": bg_color,
                "fg_color": fg_color,
                "path": None,
                "width": badge_w,
                "height": 32,
                "is_image": False
            })

    # Separate top image-based badges from bottom text-based badges
    top_image_badges = [b for b in badges if b["is_image"]]
    bottom_badges = [b for b in badges if not b["is_image"]]
    
    # We display at the center of the right area (from x = 260 to x = 760, center x = 510, center y = 200)
    center_x = 510
    center_y = 200
    
    if top_image_badges:
        # Draw top image badges centered in the right portion
        total_w = sum(b["width"] for b in top_image_badges) + 10 * (len(top_image_badges) - 1)
        current_x = center_x - total_w // 2
        for b in top_image_badges:
            badge_w = b["width"]
            badge_h = b["height"]
            badge_y = center_y - badge_h // 2
            try:
                with Image.open(b["path"]) as badge_img:
                    # Auto-crop transparent boundaries to avoid small size due to margins
                    bbox = badge_img.getbbox()
                    if bbox:
                        badge_img = badge_img.crop(bbox)
                    resized_badge = badge_img.convert("RGBA").resize((badge_w, badge_h), Image.Resampling.LANCZOS)
                    overlay.paste(resized_badge, (current_x, badge_y), mask=resized_badge)
                    resized_badge.close()
            except Exception as e:
                logger.error(f"Error rendering centered image badge {b['path']}: {e}")
            current_x += badge_w + 10
    else:
        # Fallback: Draw bottom text badges centered in the right portion
        badge_rows = []
        current_row = []
        current_row_width = 0
        max_badges_width = 460  # max width allowed
        spacing = 10
        
        for b in bottom_badges:
            badge_w = b["width"]
            if current_row_width + badge_w > max_badges_width:
                if current_row:
                    badge_rows.append((current_row, current_row_width - spacing))
                current_row = [b]
                current_row_width = badge_w + spacing
            else:
                current_row.append(b)
                current_row_width += badge_w + spacing
                
        if current_row:
            badge_rows.append((current_row, current_row_width - spacing))
            
        # Compute total height of fallback rows
        badge_row_gap = 8
        total_rows_h = 0
        num_rows = len(badge_rows)
        if num_rows > 0:
            for i, (row, row_w) in enumerate(badge_rows):
                row_h = max(b["height"] for b in row)
                total_rows_h += row_h
                if i < num_rows - 1:
                    total_rows_h += badge_row_gap
                    
        # Draw fallback rows centered
        current_y = center_y - total_rows_h // 2
        for row, row_w in badge_rows:
            row_h = max(b["height"] for b in row)
            current_x = center_x - row_w // 2
            for b in row:
                badge_w = b["width"]
                badge_h = b["height"]
                offset_y = current_y + (row_h - badge_h) // 2
                
                overlay_draw.rounded_rectangle(
                    [current_x, offset_y, current_x + badge_w, offset_y + badge_h],
                    radius=8,
                    fill=b["bg_color"]
                )
                overlay_draw.text((current_x + 12, offset_y + 5), b["text"], font=font_badge, fill=b["fg_color"])
                current_x += badge_w + spacing
            current_y += row_h + badge_row_gap

    # Paste transparent overlay onto the base image
    img.paste(overlay, (0, 0), mask=overlay)
    overlay.close()



async def render_profile_banner(
    username: str,
    avatar_url: str,
    money: int,
    gold: int,
    gold_price: int,
    loan_amount: int,
    biz_count: int,
    inv_count: int,
    banner_path: Path | None = None,
    rl_title: str | None = None,
    daga_title: str | None = None,
    cf_title: str | None = None
) -> BytesIO:
    """Renders a beautiful profile banner card (static or dynamic GIF) and returns it as a BytesIO buffer."""
    width = 800
    height = 400  # Locked standard banner height
    
    # 1. Resolve custom background if exists
    is_gif = False
    
    if banner_path and banner_path.exists():
        is_gif = (banner_path.suffix.lower() == ".gif")
    else:
        banner_path = None
                
    # Fetch avatar bytes once
    avatar_bytes = await fetch_avatar(avatar_url)
    avatar_img = None
    if avatar_bytes:
        try:
            avatar_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((180, 180), Image.Resampling.LANCZOS)
        except Exception as e:
            logger.error(f"Failed to prepare avatar image: {e}")
            avatar_img = None

    # Case A: Animated GIF Background
    if banner_path and is_gif:
        try:
            with Image.open(banner_path) as gif:
                frames = []
                num_frames = min(gif.n_frames, 100) # Safe limit to prevent CPU/memory exhaustion (increased to 100 to support full animations like sally.gif)
                
                # Fetch duration from original gif or set default
                duration = gif.info.get('duration', 100)
                
                for frame_idx in range(num_frames):
                    gif.seek(frame_idx)
                    # Create RGBA copy of current frame and resize
                    frame = gif.copy().convert("RGBA")
                    frame = frame.resize((width, height), Image.Resampling.BILINEAR)
                    frame_draw = ImageDraw.Draw(frame)
                    
                    # Draw profile overlay details
                    draw_profile_content(
                        img=frame,
                        draw=frame_draw,
                        avatar_img=avatar_img,
                        username=username,
                        money=money,
                        gold=gold,
                        gold_price=gold_price,
                        loan_amount=loan_amount,
                        biz_count=biz_count,
                        inv_count=inv_count,
                        rl_title=rl_title,
                        daga_title=daga_title,
                        cf_title=cf_title
                    )
                    frames.append(frame)
                    
                if avatar_img:
                    avatar_img.close()
                    
                output = BytesIO()
                # Save frames as animated GIF
                frames[0].save(
                    output,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    loop=0,
                    duration=duration,
                    disposal=2 # Restore to background to prevent ghosting
                )
                output.seek(0)
                output.is_gif = True
                return output
        except Exception as e:
            logger.error(f"Error rendering animated profile GIF: {e}", exc_info=True)
            # Fall through to default static if rendering GIF fails

    # Case B: Static Custom Background (PNG/JPG)
    if banner_path:
        try:
            img = Image.open(banner_path).convert("RGBA")
            img = img.resize((width, height), Image.Resampling.BILINEAR)
            draw = ImageDraw.Draw(img)
            
            draw_profile_content(
                img=img,
                draw=draw,
                avatar_img=avatar_img,
                username=username,
                money=money,
                gold=gold,
                gold_price=gold_price,
                loan_amount=loan_amount,
                biz_count=biz_count,
                inv_count=inv_count,
                rl_title=rl_title,
                daga_title=daga_title,
                cf_title=cf_title
            )
            
            if avatar_img:
                avatar_img.close()
                
            output = BytesIO()
            img.save(output, format="PNG")
            output.seek(0)
            output.is_gif = False
            img.close()
            return output
        except Exception as e:
            logger.error(f"Error rendering static profile banner: {e}", exc_info=True)
            # Fall through to default static gradient if loading custom static fails

    # Case C: Fallback Default Gradient Background
    gradient = Image.new("RGBA", (1, 2))
    gradient.putpixel((0, 0), (26, 11, 46, 255))
    gradient.putpixel((0, 1), (11, 4, 16, 255))
    img = gradient.resize((width, height), Image.Resampling.BILINEAR)
    
    draw = ImageDraw.Draw(img)
    
    draw_profile_content(
        img=img,
        draw=draw,
        avatar_img=avatar_img,
        username=username,
        money=money,
        gold=gold,
        gold_price=gold_price,
        loan_amount=loan_amount,
        biz_count=biz_count,
        inv_count=inv_count,
        rl_title=rl_title,
        daga_title=daga_title,
        cf_title=cf_title
    )
    
    if avatar_img:
        avatar_img.close()
        
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    output.is_gif = False
    img.close()
    return output


async def render_showcase_image(
    cock_info: dict | None,
    car_info: dict | None
) -> BytesIO | None:
    if not cock_info and not car_info:
        return None

    def resize_contain(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
        original_w, original_h = image.size
        aspect_ratio = original_w / original_h

        if original_w / max_w > original_h / max_h:
            new_w = max_w
            new_h = max(1, int(max_w / aspect_ratio))
        else:
            new_h = max_h
            new_w = max(1, int(max_h * aspect_ratio))

        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    width, height = 800, 240
    # Create background image with dark gradient
    gradient = Image.new("RGBA", (1, 2))
    gradient.putpixel((0, 0), (20, 10, 35, 255))
    gradient.putpixel((0, 1), (8, 4, 12, 255))
    img = gradient.resize((width, height), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(img)

    # Draw outline border
    draw.rounded_rectangle([6, 6, width - 6, height - 6], radius=16, outline=(255, 255, 255, 30), width=2)

    font_bold = load_font("bold", 16)
    font_regular = load_font("regular", 12)
    font_header = load_font("bold", 18)

    panel_y = 25
    panel_h = 190
    panel_w = 360

    from app.discord_bot.modules.helpers import ABS_PATH

    # Panel 1: Cock
    if cock_info and car_info:
        cock_x = 30
    elif cock_info:
        cock_x = (width - panel_w) // 2
    else:
        cock_x = None

    if cock_info and cock_x is not None:
        # Draw Cock Panel Frosted Glass Box
        draw.rounded_rectangle(
            [cock_x, panel_y, cock_x + panel_w, panel_y + panel_h],
            radius=12,
            fill=(255, 255, 255, 10),
            outline=(255, 255, 255, 20),
            width=1
        )
        rarity_colors = {
            "Thường": (120, 120, 120, 255),       # C (Grey)
            "Hiếm": (46, 204, 113, 255),         # B (Green)
            "Quý": (52, 152, 219, 255),          # A (Blue)
            "Sử Thi": (155, 89, 182, 255),       # S (Purple)
            "Huyền Thoại": (241, 196, 15, 255),   # SS (Gold)
            "Thần Kê": (231, 76, 60, 255),       # SSS (Red)
            "Exclusive": (230, 126, 34, 255)     # Exclusive (Orange)
        }
        rarity_display = {
            "Thường": "C",
            "Hiếm": "B",
            "Quý": "A",
            "Sử Thi": "S",
            "Huyền Thoại": "SS",
            "Thần Kê": "SSS",
            "Exclusive": "Exclusive"
        }
        rarity = cock_info.get("rarity", "Thường")
        accent_color = rarity_colors.get(rarity, (120, 120, 120, 255))
        draw.rounded_rectangle(
            [cock_x, panel_y, cock_x + 5, panel_y + panel_h],
            radius=12,
            fill=accent_color
        )

        # Draw cock image
        img_file = cock_info.get("image_filename")
        cock_img = None
        if img_file:
            if Path(img_file).is_absolute():
                path = Path(img_file)
            else:
                path = ABS_PATH / "modules" / "daga" / img_file
            if path.exists():
                try:
                    cock_img = Image.open(path).convert("RGBA")
                    cock_img = resize_contain(cock_img, 130, 150)
                except Exception as e:
                    logger.error(f"Failed to load cock image: {e}")
        
        if cock_img:
            new_w, new_h = cock_img.size
            paste_x = cock_x + 85 - (new_w // 2)
            paste_y = panel_y + 95 - (new_h // 2)
            img.paste(cock_img, (paste_x, paste_y), mask=cock_img)
            cock_img.close()
        else:
            draw.ellipse([cock_x + 20, panel_y + 30, cock_x + 150, panel_y + 160], fill=(100, 100, 100, 255))

        name = cock_info.get("name", "Nhân vật")
        level = cock_info.get("level", 1)
        wins = cock_info.get("wins", 0)
        losses = cock_info.get("losses", 0)
        streak = cock_info.get("streak", 0)

        draw.text((cock_x + 165, panel_y + 25), name, font=font_header, fill=(255, 255, 255, 255))
        
        display_rarity = rarity_display.get(rarity, rarity)
        draw.text((cock_x + 165, panel_y + 55), f"Độ hiếm: {display_rarity}", font=font_bold, fill=accent_color)
        draw.text((cock_x + 165, panel_y + 80), f"Cấp độ: {level}", font=font_regular, fill=(200, 200, 200, 255))
        draw.text((cock_x + 165, panel_y + 110), f"Thắng: {wins} | Thua: {losses}", font=font_regular, fill=(200, 200, 200, 255))
        draw.text((cock_x + 165, panel_y + 135), f"Chuỗi thắng: {streak}", font=font_regular, fill=(200, 200, 200, 255))

    # Panel 2: Car
    if cock_info and car_info:
        car_x = 410
    elif car_info:
        car_x = (width - panel_w) // 2
    else:
        car_x = None

    if car_info and car_x is not None:
        # Draw Car Panel Frosted Glass Box
        draw.rounded_rectangle(
            [car_x, panel_y, car_x + panel_w, panel_y + panel_h],
            radius=12,
            fill=(255, 255, 255, 10),
            outline=(255, 255, 255, 20),
            width=1
        )
        rarity_colors = {
            "Common": (120, 120, 120, 255),
            "Rare": (46, 204, 113, 255),
            "Epic": (52, 152, 219, 255),
            "Legendary": (155, 89, 182, 255),
            "Mythic": (241, 196, 15, 255),
            "Exclusive": (231, 76, 60, 255)
        }
        rarity = car_info.get("rarity", "Common")
        accent_color = rarity_colors.get(rarity, (120, 120, 120, 255))
        draw.rounded_rectangle(
            [car_x, panel_y, car_x + 5, panel_y + panel_h],
            radius=12,
            fill=accent_color
        )

        # Draw car image
        img_file = car_info.get("image_filename")
        car_img = None
        if img_file:
            path = ABS_PATH / "modules" / "duaxe" / img_file
            if path.exists():
                try:
                    car_img = Image.open(path).convert("RGBA")
                    car_img = resize_contain(car_img, 150, 110)
                except Exception as e:
                    logger.error(f"Failed to load car image: {e}")
                    
        if car_img:
            new_w, new_h = car_img.size
            paste_x = car_x + 90 - (new_w // 2)
            paste_y = panel_y + 95 - (new_h // 2)
            img.paste(car_img, (paste_x, paste_y), mask=car_img)
            car_img.close()
        else:
            draw.ellipse([car_x + 20, panel_y + 45, car_x + 150, panel_y + 145], fill=(100, 100, 100, 255))

        model = car_info.get("model", "Xe Chưa Đặt Tên")
        edition = car_info.get("edition", "Stock")
        serial = car_info.get("serial", 1)
        collection = car_info.get("collection", "Other")

        draw.text((car_x + 175, panel_y + 25), model, font=font_header, fill=(255, 255, 255, 255))
        draw.text((car_x + 175, panel_y + 55), f"Độ hiếm: {rarity}", font=font_bold, fill=accent_color)
        draw.text((car_x + 175, panel_y + 80), f"Phiên bản: {edition}", font=font_regular, fill=(200, 200, 200, 255))
        draw.text((car_x + 175, panel_y + 110), f"Bộ sưu tập: {collection}", font=font_regular, fill=(200, 200, 200, 255))
        draw.text((car_x + 175, panel_y + 135), f"Serial: #{serial:04d}", font=font_bold, fill=(255, 215, 0, 255))

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    img.close()
    return output


async def render_money_card(
    username: str,
    avatar_url: str,
    money: int,
    gold: int,
    role_text: str
) -> BytesIO:
    """Renders a beautiful balance (i?money) card image and returns it as a BytesIO buffer."""
    width = 600
    height = 310
    
    # 1. Create transparent base image
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 2. Draw outer card background with rounded corners
    draw.rounded_rectangle([10, 10, width - 10, height - 10], radius=16, fill=(43, 45, 49, 255))
    
    # 3. Fetch and process avatar
    avatar_bytes = await fetch_avatar(avatar_url)
    avatar_img = None
    avatar_size = 80
    avatar_x, avatar_y = 35, 30
    
    if avatar_bytes:
        try:
            avatar_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
            
            avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
            avatar_circle.paste(avatar_img, (0, 0), mask=mask)
            img.paste(avatar_circle, (avatar_x, avatar_y), mask=avatar_circle)
            avatar_circle.close()
            mask.close()
        except Exception as e:
            logger.error(f"Failed to render money card avatar: {e}")
            avatar_img = None
            
    if not avatar_img:
        # Fallback circle
        draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=(100, 100, 100, 255))
        
    # Avatar outline border (purple)
    draw.ellipse([avatar_x - 3, avatar_y - 3, avatar_x + avatar_size + 3, avatar_y + avatar_size + 3], outline=(148, 0, 211, 255), width=3)
    
    # 4. Load Fonts
    font_username = load_font("bold", 24)
    font_role = load_font("bold", 12)
    font_section_title = load_font("regular", 11)
    font_section_val = load_font("bold", 26)
    font_section_unit = load_font("regular", 11)
    
    # Draw User Info (Username and Role)
    draw.text((130, 35), username, font=font_username, fill=(255, 255, 255, 255))
    draw.text((130, 68), role_text, font=font_role, fill=(148, 155, 164, 255))
    
    # 5. Draw Middle Cards (SỐ DƯ and THỎI VÀNG)
    # Box 1: SỐ DƯ (Left)
    draw.rounded_rectangle([35, 125, 285, 225], radius=10, fill=(35, 36, 40, 255), outline=(184, 134, 11, 100), width=1)
    draw.text((50, 135), "💰 SỐ DƯ", font=font_section_title, fill=(148, 155, 164, 255))
    draw.text((50, 158), f"{money:,}", font=font_section_val, fill=(255, 215, 0, 255)) # Gold color
    draw.text((50, 195), "VND", font=font_section_unit, fill=(148, 155, 164, 255))
    
    # Box 2: THỎI VÀNG (Right)
    draw.rounded_rectangle([315, 125, 565, 225], radius=10, fill=(35, 36, 40, 255), outline=(184, 134, 11, 100), width=1)
    draw.text((330, 135), "🪙 THỎI VÀNG", font=font_section_title, fill=(148, 155, 164, 255))
    draw.text((330, 158), f"{gold:,}", font=font_section_val, fill=(255, 255, 255, 255)) # White
    draw.text((330, 195), "thỏi vàng", font=font_section_unit, fill=(148, 155, 164, 255))
    
    # 6. Draw Footer Card
    draw.rounded_rectangle([35, 240, 565, 275], radius=8, fill=(30, 31, 34, 255))
    draw.text((50, 250), "📅 Cập nhật lúc", font=font_section_title, fill=(148, 155, 164, 255))
    
    # Timestamp: MM/DD/YYYY — HH:MM:SS
    from datetime import datetime
    current_time_str = datetime.now().strftime("%m/%d/%Y — %H:%M:%S")
    try:
        ts_w = font_section_title.getlength(current_time_str)
    except AttributeError:
        ts_w = len(current_time_str) * 7
    ts_x = 550 - int(ts_w)
    draw.text((ts_x, 250), current_time_str, font=font_section_title, fill=(148, 155, 164, 255))
    
    # Return as BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    img.close()
    return buf
