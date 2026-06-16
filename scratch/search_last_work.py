import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\8b01ecfb-558a-425d-ad46-782d431ef5c7\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\last_work_matches.txt"

with open(log_path, "r", encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
    for i, line in enumerate(f):
        if "last_work" in line:
            out.write(f"--- Line {i} ---\n")
            out.write(line[:2000] + "\n\n")
print("Done searching for last_work.")
