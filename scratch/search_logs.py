import json

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\8b01ecfb-558a-425d-ad46-782d431ef5c7\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\recovered_writes.txt"

with open(log_path, 'r', encoding='utf-8') as f, open(output_path, 'w', encoding='utf-8') as out:
    for line_num, line in enumerate(f):
        try:
            data = json.loads(line)
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    name = tc.get('name')
                    args = tc.get('args', {})
                    # Convert args to string to search for keywords
                    args_str = json.dumps(args)
                    if ('replace_file_content' in name or 'write_to_file' in name) and ('process_daily' in args_str or 'process_work' in args_str or 'def work' in args_str):
                        out.write(f"--- Line {line_num} Tool Call {name}:\n")
                        out.write(json.dumps(args, indent=2))
                        out.write("\n" + "="*80 + "\n")
        except Exception as e:
            pass
print("Done searching.")
