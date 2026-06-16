import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\65ae5109-299d-47af-91c4-8fe0c179ee47\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\daga_edits_history.txt"

with open(log_path, "r", encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {})
                target_file = args.get("TargetFile", "")
                if "daga.py" in target_file:
                    out.write(f"=== Step {data.get('step_index', i)} Tool: {name} ===\n")
                    out.write(f"Instruction: {args.get('Instruction')}\n")
                    if "TargetContent" in args:
                        out.write(f"TargetContent:\n{args.get('TargetContent')}\n")
                    if "ReplacementContent" in args:
                        out.write(f"ReplacementContent:\n{args.get('ReplacementContent')}\n")
                    out.write("-" * 80 + "\n")
        except Exception as e:
            pass
print("History extraction completed.")
