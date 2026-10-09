"""Unicode font styling utility ported from Ilis_Farm."""
import re
from typing import Optional

def _arr(s: str) -> list[str]:
    return list(s)

FONTS = {
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
        "D": None,
    },
    "bold_italic": {
        "label": "In đậm nghiêng",
        "U": _arr("𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁"),
        "L": _arr("𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛"),
        "D": None,
    },
    "script": {
        "label": "Chữ thảo",
        "U": _arr("𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵"),
        "L": _arr("𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
        "D": None,
    },
    "bold_script": {
        "label": "Chữ thảo đậm",
        "U": _arr("𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩"),
        "L": _arr("𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"),
        "D": None,
    },
    "gothic": {
        "label": "Gothic",
        "U": _arr("𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ"),
        "L": _arr("𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷"),
        "D": None,
    },
    "double": {
        "label": "Double Struck",
        "U": _arr("𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"),
        "L": _arr("𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝓸𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
        "D": _arr("𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"),
    },
    "sans": {
        "label": "Sans-Serif",
        "U": _arr("𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹"),
        "L": _arr("𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓"),
        "D": None,
    },
    "sans_bold": {
        "label": "Sans đậm",
        "U": _arr("𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝫭𝫮𝫯"),  # Standard mathematical sans-bold
        "L": _arr("𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
        "D": _arr("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    },
    "mono": {
        "label": "Monospace",
        "U": _arr("𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉"),
        "L": _arr("𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
        "D": _arr("𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
    },
    "bubble": {
        "label": "Bubble",
        "U": _arr("ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"),
        "L": _arr("ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"),
        "D": _arr("⓪①②③④⑤⑥⑦⑧⑨"),
    },
    "fullwidth": {
        "label": "Full-width",
        "U": _arr("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"),
        "L": _arr("ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"),
        "D": _arr("０１２３４５６７８９"),
    },
}

# Fix sans_bold U if any character mapping differs
FONTS["sans_bold"]["U"] = _arr("𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭")


def _convert_chars(text: str, U: list[str], L: list[str], D: Optional[list[str]]) -> str:
    res = []
    for ch in text:
        cp = ord(ch)
        if 65 <= cp <= 90:
            res.append(U[cp - 65] if cp - 65 < len(U) else ch)
        elif 97 <= cp <= 122:
            res.append(L[cp - 97] if cp - 97 < len(L) else ch)
        elif D and 48 <= cp <= 57:
            res.append(D[cp - 48] if cp - 48 < len(D) else ch)
        else:
            res.append(ch)
    return "".join(res)


def apply_font(text: str, font_key: Optional[str]) -> str:
    """Apply a stylized Unicode font, preserving custom Discord emojis."""
    if not text or not font_key:
        return text
    font = FONTS.get(font_key.lower())
    if not font:
        return text

    u_map, l_map, d_map = font["U"], font["L"], font["D"]

    # Split by custom emojis like <:name:id> or <a:name:id>
    parts = re.split(r"(<a?:[^:>]+:\d+>)", text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Emoji portion - keep intact
            result.append(part)
        else:
            result.append(_convert_chars(part, u_map, l_map, d_map))
    return "".join(result)


def display_len(text: str) -> int:
    """Calculate character length counting Discord emojis as 2 characters."""
    if not text:
        return 0
    # Replace custom emojis with 2 chars
    simplified = re.sub(r"<a?:[^:>]+:\d+>", "XX", text)
    return len(simplified)
