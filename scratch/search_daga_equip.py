import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\65ae5109-299d-47af-91c4-8fe0c179ee47\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\recovered_equip.txt"

with open(log_path, "r", encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            # Check if this step contains the view or replacement of daga.py
            if "daga.py" in content or "daga_equip" in content or "await ctx.send(f\"❌ **Lỗi: Bắt đầu" in content:
                out.write(f"--- Step {data.get('step_index', i)} Source {data.get('source')}: \n")
                out.write(content[:5000]) # write a snippet
                out.write("\n" + "="*80 + "\n")
            
            # Check tool_calls or tool outputs
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {})
                args_str = json.dumps(args, ensure_ascii=False)
                if "daga.py" in args_str or "daga_equip" in args_str:
                    out.write(f"--- Step {data.get('step_index', i)} Tool Call {name}: \n")
                    out.write(args_str[:5000])
                    out.write("\n" + "="*80 + "\n")
        except Exception as e:
            pass
print("Search completed.")
