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


def draw_candlestick_chart(symbol: str, history: list[int], current_price: int) -> io.BytesIO:
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
    
    # Determine color theme based on overall trend
    is_up = history[-1] >= history[0]
    theme_color = (16, 185, 129, 255) if is_up else (239, 68, 68, 255) # Green / Red
    
    draw.text((padding_left, 15), title_text, font=font_title, fill=(255, 255, 255, 255))
    draw.text((width - padding_right - 180, 18), price_text, font=font_title, fill=theme_color)
    
    # Generate mock OHLC data from Close history
    ohlc_list = []
    for i in range(len(history)):
        close_p = history[i]
        open_p = history[i-1] if i > 0 else int(close_p * 0.98)
        
        diff = abs(close_p - open_p)
        if diff == 0:
            diff = max(100, int(close_p * 0.01))
            
        high_p = int(max(open_p, close_p) + random.uniform(0.1, 0.4) * diff)
        low_p = int(min(open_p, close_p) - random.uniform(0.1, 0.4) * diff)
        
        # Ensure prices make sense
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)
        low_p = max(1, low_p) # No negative price
        
        ohlc_list.append({
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p
        })
        
    # Price limits
    min_val = min(x["low"] for x in ohlc_list)
    max_val = max(x["high"] for x in ohlc_list)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1000
        min_val -= 500
        max_val += 500
        
    # Pad vertical min/max a bit for better aesthetics
    min_val -= val_range * 0.1
    min_val = max(1, min_val)
    max_val += val_range * 0.1
    val_range = max_val - min_val
    
    # Price ticks (Y axis)
    num_ticks = 5
    for i in range(num_ticks):
        val = min_val + (val_range / (num_ticks - 1)) * i
        y = height - padding_bottom - (val - min_val) / val_range * chart_height
        # Draw grid line
        draw.line([(padding_left, y), (width - padding_right, y)], fill=(30, 30, 47, 255), width=1)
        # Draw label
        label = f"{int(val):,}"
        draw.text((10, y - 6), label, font=font_axis, fill=(150, 150, 170, 255))
        
    # Draw session candles (X axis)
    num_candles = len(ohlc_list)
    candle_width = max(4, int((chart_width / num_candles) * 0.6))
    
    for i in range(num_candles):
        ohlc = ohlc_list[i]
        x = padding_left + (i / (num_candles - 1)) * chart_width if num_candles > 1 else padding_left + chart_width / 2
        
        y_open = height - padding_bottom - (ohlc['open'] - min_val) / val_range * chart_height
        y_close = height - padding_bottom - (ohlc['close'] - min_val) / val_range * chart_height
        y_high = height - padding_bottom - (ohlc['high'] - min_val) / val_range * chart_height
        y_low = height - padding_bottom - (ohlc['low'] - min_val) / val_range * chart_height
        
        # Decide candle color (Green for Bullish, Red for Bearish)
        is_candle_up = ohlc['close'] >= ohlc['open']
        candle_color = (16, 185, 129, 255) if is_candle_up else (239, 68, 68, 255)
        
        # Draw shadow line (High to Low)
        draw.line([(x, y_high), (x, y_low)], fill=candle_color, width=2)
        
        # Draw body rectangle (Open to Close)
        y_top = min(y_open, y_close)
        y_bottom = max(y_open, y_close)
        if abs(y_top - y_bottom) < 2:
            y_bottom = y_top + 2
            
        draw.rectangle(
            [x - candle_width/2, y_top, x + candle_width/2, y_bottom],
            fill=candle_color,
            outline=candle_color
        )
        
        # X-axis label (Sessions)
        if i % max(1, num_candles // 5) == 0 or i == num_candles - 1:
            label = f"S{i+1}"
            draw.text((x - 8, height - padding_bottom + 10), label, font=font_axis, fill=(120, 120, 140, 255))

    # Draw chart border
    draw.line([(padding_left, height - padding_bottom), (width - padding_right, height - padding_bottom)], fill=(50, 50, 70, 255), width=1)
    draw.line([(padding_left, padding_top), (padding_left, height - padding_bottom)], fill=(50, 50, 70, 255), width=1)

    # Save to buffer
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

