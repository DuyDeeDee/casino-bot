"""Unicode font styling utility with 32 stylized fonts and Vietnamese support."""
import re
import unicodedata
from typing import Optional

def _arr(s: str) -> list[str]:
    return list(s)

FONTS = {
    # ── Group 1: Classic & Script ──
    "bold": {
        "label": "In đậm",
        "U": _arr("𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"),
        "L": _arr("𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"),
        "D": _arr("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    },
    "italic": {
        "label": "In nghiêng",
        "U": _arr("𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍"),
        "L": _arr("𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧"),
        "D": _arr("𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"),
    },
    "bold_italic": {
        "label": "In đậm nghiêng",
        "U": _arr("𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁"),
        "L": _arr("𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛"),
        "D": _arr("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    },
    "script": {
        "label": "Chữ thảo",
        "U": _arr("𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵"),
        "L": _arr("𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
        "D": _arr("𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"),
    },
    "bold_script": {
        "label": "Chữ thảo đậm",
        "U": _arr("𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩"),
        "L": _arr("𝓪𝫮𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"),
        "D": _arr("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    },
    "gothic": {
        "label": "Gothic",
        "U": _arr("𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ"),
        "L": _arr("𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷"),
        "D": _arr("𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
    },
    "bold_gothic": {
        "label": "Gothic đậm",
        "U": _arr("𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅"),
        "L": _arr("𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟"),
        "D": _arr("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    },
    "double": {
        "label": "Double Struck",
        "U": _arr("𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"),
        "L": _arr("𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝓸𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
        "D": _arr("𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"),
    },

    # ── Group 2: Modern Sans & Chunky ──
    "sans": {
        "label": "Sans-Serif",
        "U": _arr("𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹"),
        "L": _arr("𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓"),
        "D": _arr("𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"),
    },
    "sans_bold": {
        "label": "Sans đậm béo",
        "U": _arr("𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"),
        "L": _arr("𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
        "D": _arr("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    },
    "sans_italic": {
        "label": "Sans nghiêng",
        "U": _arr("𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡"),
        "L": _arr("𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝑢𝘷𝘸𝘹𝘺𝘻"),
        "D": _arr("𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"),
    },
    "sans_bold_italic": {
        "label": "Sans đậm nghiêng",
        "U": _arr("𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕"),
        "L": _arr("𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝒍𝙢𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯"),
        "D": _arr("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    },
    "mono": {
        "label": "Monospace",
        "U": _arr("𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉"),
        "L": _arr("𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝕞𝚗𝚘𝚙𝚚𝚛𝚜𝕥𝕦𝚟𝚠𝚡𝚢𝚣"),
        "D": _arr("𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
    },
    "fullwidth": {
        "label": "To bè Fullwidth",
        "U": _arr("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"),
        "L": _arr("ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"),
        "D": _arr("０１２３４５６７８９"),
    },
    "small_caps": {
        "label": "In hoa Mini",
        "U": _arr("ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"),
        "L": _arr("ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"),
        "D": _arr("₀₁₂₃₄₅₆₇₈₉"),
    },
    "curved_tail": {
        "label": "Móc đuôi uốn",
        "U": _arr("ȺɃȻĐɆƑԌĦƗɈҞŁM₦ØⱣɊɌŞŦɄỼШЖɎƵ"),
        "L": _arr("ąɓƈđҽƒɠɦɨʝƙɭɱɳσρҩɾʂɬųʋɯҳყȥ"),
        "D": _arr("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    },

    # ── Group 3: Bubbles & Boxes ──
    "bubble": {
        "label": "Bong bóng trắng",
        "U": _arr("ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"),
        "L": _arr("ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"),
        "D": _arr("⓪①②③④⑤⑥⑦⑧⑨"),
    },
    "black_bubble": {
        "label": "Nút tròn đen",
        "U": _arr("🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩"),
        "L": _arr("🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩"),
        "D": _arr("⓿➊➋➌➍➎➏➐➑➒"),
    },
    "square": {
        "label": "Khung vuông trắng",
        "U": _arr("🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉"),
        "L": _arr("🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉"),
        "D": _arr("𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"),
    },
    "black_square": {
        "label": "Khung hộp nổi",
        "U": _arr("🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉"),
        "L": _arr("🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉"),
        "D": _arr("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    },
    "parenthesis": {
        "label": "Ngoặc tròn",
        "U": _arr("⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵"),
        "L": _arr("⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵"),
        "D": _arr("⒪⑴⑵⑶⑷⑸⑹⑺⑻⑼"),
    },
    "superscript": {
        "label": "Số mũ trên cao",
        "U": _arr("ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᑫᴿˢᵀᵁⱽᵂˣʸᶻ"),
        "L": _arr("ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᑫʳˢᵗᵘᵛʷˣʸᶻ"),
        "D": _arr("⁰¹²³⁴⁵⁶⁷⁸⁹"),
    },
    "subscript": {
        "label": "Chỉ số dưới chân",
        "U": _arr("ₐᵦ𝒸𝒹ₑ𝒻𝓰ₕᵢⱼₖₗₘₙₒₚᵩᵣₛₜᵤᵥ𝓌ₓᵧ𝓏"),
        "L": _arr("ₐᵦ𝒸𝒹ₑ𝒻𝓰ₕᵢⱼₖₗₘₙₒₚᵩᵣₛₜᵤᵥ𝓌ₓᵧ𝓏"),
        "D": _arr("₀₁₂₃₄₅₆₇₈₉"),
    },

    # ── Group 4: Combining & Decorators ──
    "circle": {
        "label": "Viền tròn bọc chữ",
        "char": "\u20DD",
    },
    "square_outline": {
        "label": "Viền ô vuông bọc chữ",
        "char": "\u20E2",
    },
    "strike": {
        "label": "Gạch ngang chữ",
        "char": "\u0336",
    },
    "underline": {
        "label": "Gạch chân dưới",
        "char": "\u0332",
    },
    "double_underline": {
        "label": "Gạch chân kép",
        "char": "\u0333",
    },
    "slash": {
        "label": "Gạch xiên chéo",
        "char": "\u0337",
    },
    "wavy": {
        "label": "Gợn sóng chân",
        "char": "\u0330",
    },
    "sparkle": {
        "label": "Ánh sao lấp lánh",
        "custom": True,
    },
    "upside_down": {
        "label": "Lộn ngược 180°",
        "custom": True,
    },
}

_FLIP_MAP = dict(zip(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "ɐqɔpǝɟƃɥıɾʞlɯuodbɹsʇnʌʍxʎz∀ᗺƆᗡƎℲ⅁HIſʞ˥WNOԀὉᴚS⊥∩ΛMXʎZ0ƖᄅƐㄣϛ9ㄥ86"
))

def _convert_chars(text: str, U: list[str], L: list[str], D: Optional[list[str]]) -> str:
    res = []
    for ch in text:
        if ch in ("đ", "Đ"):
            base = "d" if ch == "đ" else "D"
            combining = "\u0335"
        else:
            decomposed = unicodedata.normalize("NFD", ch)
            base = decomposed[0]
            combining = decomposed[1:]

        cp = ord(base)
        if 65 <= cp <= 90:
            styled_base = U[cp - 65] if cp - 65 < len(U) else base
        elif 97 <= cp <= 122:
            styled_base = L[cp - 97] if cp - 97 < len(L) else base
        elif D and 48 <= cp <= 57:
            styled_base = D[cp - 48] if cp - 48 < len(D) else base
        else:
            styled_base = base

        res.append(styled_base + combining)
    return "".join(res)

def _apply_combining(text: str, mark: str) -> str:
    res = []
    for c in text:
        if c in (" ", "\n", "\t"):
            res.append(c)
        else:
            res.append(c + mark)
    return "".join(res)

def apply_font(text: str, font_key: Optional[str]) -> str:
    """Apply a stylized Unicode font, preserving custom Discord emojis."""
    if not text or not font_key:
        return text
    k = font_key.lower().strip()
    if k in ["none", "normal", "off", "macdinh", "reset"]:
        return text
    font = FONTS.get(k)
    if not font:
        return text

    parts = re.split(r"(<a?:[^:>]+:\d+>)", text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            if "char" in font:
                result.append(_apply_combining(part, font["char"]))
            elif k == "sparkle":
                result.append(f"✧ {part} ✧" if part.strip() else part)
            elif k == "upside_down":
                result.append("".join(_FLIP_MAP.get(c, c) for c in reversed(part)))
            else:
                u_map = font.get("U", [])
                l_map = font.get("L", [])
                d_map = font.get("D")
                result.append(_convert_chars(part, u_map, l_map, d_map))
    return "".join(result)

def display_len(text: str) -> int:
    """Calculate character length counting Discord emojis as 2 characters."""
    if not text:
        return 0
    simplified = re.sub(r"<a?:[^:>]+:\d+>", "XX", text)
    return len(simplified)
