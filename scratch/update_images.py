import py_compile

file_path = "app/discord_bot/cogs/daga.py"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Locate get_cock_image_file block
start_pattern = "def get_cock_image_file(name: str, fallback_to_default: bool = False) -> str | None:"
end_pattern = "def process_cock_image("

start_idx = text.find(start_pattern)
end_idx = text.find(end_pattern)

if start_idx != -1 and end_idx != -1:
    new_func = """def get_cock_image_file(name: str, fallback_to_default: bool = False) -> str | None:
    # 0. Check custom exclusive folder first
    root_path = ABS_PATH.parent.parent
    exclusive_dir = root_path / "pictures" / "exclusive_cocks"
    norm_name = name.lower().strip()
    if norm_name.startswith("gà "):
        norm_name = norm_name[3:]
    # remove accents
    norm_name = unicodedata.normalize('NFKD', norm_name).encode('ASCII', 'ignore').decode('utf-8')
    norm_name = re.sub(r'[^a-z0-9]', '', norm_name)
    custom_filename = f"{norm_name}.png"
    custom_path = exclusive_dir / custom_filename
    if custom_path.exists():
        return str(custom_path)

    # 1. Strict mapping for known anime characters
    mapping = {
        "Goku (Ultra Instinct)": "Goku (Ultra Instinct).png",
        "Luffy (Gear 5)": "luffy-gear-5.png",
        "Naruto (Baryon Mode)": "Naruto-Baryon-Mode.png",
        "Saitama": "Saitama.png",
        "Gojo Satoru": "gojo .png",
        "Itachi Uchiha": "Itachi-Uchiha.png",
        "Vegeta": "vegeta.png",
        "Usopp": "usopp.png",
        "Krillin": "krillin.png",
        "Zenitsu": "zenitsu.png",
        "Killua": "Killua.png",
        "Sakura": "sakura.png",
        "Trunks": "trunks.png",
        "Levi Ackerman": "Levi-Ackerman.png",
        "Zoro": "zoro.png",
        "Akame": "akame.png",
        "Kakashi": "Kakashi.png",
        "Meliodas": "meliodas.png",
        "Ichigo": "ichigo.png",
    }
    
    # Direct strict mapping check first
    for key, filename in mapping.items():
        if key.lower().strip() == name.lower().strip() or key in name:
            path = ABS_PATH / "modules" / "daga" / filename
            if path.exists():
                return filename

    # 2. Dynamic fallback check
    filename = f"{norm_name}.png"
    path = ABS_PATH / "modules" / "daga" / filename
    if path.exists():
        return filename

    # 3. Default fallback
    if fallback_to_default:
        default_path = ABS_PATH / "modules" / "daga" / "default_cock.png"
        if default_path.exists():
            return "default_cock.png"

    return None

"""
    text = text[:start_idx] + new_func + text[end_idx:]
    print("SUCCESS: get_cock_image_file updated.")
else:
    print("ERROR: block not found.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

try:
    py_compile.compile(file_path, doraise=True)
    print("SUCCESS: compiled successfully!")
except Exception as e:
    print("ERROR:", e)
