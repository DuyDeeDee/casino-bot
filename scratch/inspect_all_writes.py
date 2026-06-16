import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\65ae5109-299d-47af-91c4-8fe0c179ee47\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\all_writes_history.txt"

with open(log_path, "r", encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                name = tc.get("name", "")
                if name == "write_to_file":
                    args = tc.get("args", {})
                    target_file = args.get("TargetFile", "")
                    out.write(f"=== Step {data.get('step_index', i)} target: {target_file} ===\n")
                    out.write(f"Description: {args.get('Description')}\n")
                    content = args.get("CodeContent", "")
                    out.write(f"Content length: {len(content)}\n")
                    out.write(f"Snippet:\n{content[:500]}\n")
                    out.write("-" * 80 + "\n")
        except Exception as e:
            pass
print("Done extracting all write_to_file calls.")
