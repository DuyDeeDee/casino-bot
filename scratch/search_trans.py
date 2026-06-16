import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\8b01ecfb-558a-425d-ad46-782d431ef5c7\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\step_1138_code.py"

with open(log_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i == 1138:
            data = json.loads(line)
            tc = data["tool_calls"][0]
            args = tc.get("args", {})
            with open(out_path, "w", encoding="utf-8") as out:
                out.write(str(args.get("ReplacementContent")))
            print("Done writing to step_1138_code.py")
            break
