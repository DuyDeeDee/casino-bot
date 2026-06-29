import io
import random
from PIL import Image, ImageDraw, ImageFont

def draw_stock_chart(symbol: str, history: list[int], current_price: int) -> io.BytesIO:
    # Width and height of the image
    width, height = 600, 300
    img = Image.new("RGBA", (width, height), color=(18, 18, 30, 255)) # Dark background #12121e
    draw = ImageDraw.Draw(img)
    
    # Load font
    try:
        font_title = ImageFont.truetype("test.ttf", 20)
        font_axis = ImageFont.truetype("test.ttf", 12)
    except Exception:
        font_title = ImageFont.load_default()
        font_axis = ImageFont.load_default()

    # Padding/Margins
    padding_left = 75
    padding_right = 30
    padding_top = 60
    padding_bottom = 40
    
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom
    
    # Draw Title & Subtitle
    title_text = f"{symbol} Price Trend"
    price_text = f"{current_price:,} VND"
    
    # Determine color theme based on trend
    is_up = history[-1] >= history[0]
    theme_color = (16, 185, 129, 255) if is_up else (239, 68, 68, 255) # Green / Red
    
    draw.text((padding_left, 15), title_text, font=font_title, fill=(255, 255, 255, 255))
    draw.text((width - padding_right - 180, 18), price_text, font=font_title, fill=theme_color)
    
    # Price limits
    min_val = min(history)
    max_val = max(history)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1000
        min_val -= 500
        max_val += 500
        
    # Pad vertical min/max a bit for better aesthetics
    min_val -= val_range * 0.1
    max_val += val_range * 0.1
    val_range = max_val - min_val
    
    # Price ticks (Y axis)
    num_ticks = 5
    for i in range(num_ticks):
        val = min_val + (val_range / (num_ticks - 1)) * i
        # Calculate Y coordinate
        y = height - padding_bottom - (val - min_val) / val_range * chart_height
        # Draw grid line
        draw.line([(padding_left, y), (width - padding_right, y)], fill=(30, 30, 47, 255), width=1)
        # Draw label
        label = f"{int(val):,}"
        draw.text((10, y - 6), label, font=font_axis, fill=(150, 150, 170, 255))
        
    # Session ticks (X axis)
    num_points = len(history)
    points = []
    for i in range(num_points):
        x = padding_left + (i / (num_points - 1)) * chart_width
        y = height - padding_bottom - (history[i] - min_val) / val_range * chart_height
        points.append((x, y))
        
        # X-axis label (Sessions)
        label = f"S{i+1}"
        draw.text((x - 8, height - padding_bottom + 10), label, font=font_axis, fill=(120, 120, 140, 255))

    # Draw chart border
    draw.line([(padding_left, height - padding_bottom), (width - padding_right, height - padding_bottom)], fill=(50, 50, 70, 255), width=1)
    draw.line([(padding_left, padding_top), (padding_left, height - padding_bottom)], fill=(50, 50, 70, 255), width=1)

    # Draw gradient fill under the line
    fill_polygon = [(padding_left, height - padding_bottom)] + points + [(width - padding_right, height - padding_bottom)]
    fill_color = (16, 185, 129, 35) if is_up else (239, 68, 68, 35)
    draw.polygon(fill_polygon, fill=fill_color)
    
    # Draw trend line
    draw.line(points, fill=theme_color, width=3, joint="round")
    
    # Draw dots on data points and a glowing halo on the last point
    for i, pt in enumerate(points):
        x, y = pt
        if i == num_points - 1:
            # Last point: glow effect
            draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(theme_color[0], theme_color[1], theme_color[2], 80))
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=theme_color)
        else:
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=theme_color)

    # Save to buffer
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
