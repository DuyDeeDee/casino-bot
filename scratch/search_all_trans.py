# -*- coding: utf-8 -*-
import json
import os

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\65ae5109-299d-47af-91c4-8fe0c179ee47\.system_generated\logs\transcript.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "async def daga_equip" in content:
                step_idx = data.get("step_index", i)
                print(f"Match in content at Step {step_idx}")
                if "update_cock" in content:
                    # Write to file
                    out_path = f"scratch/full_step_{step_idx}.txt"
                    with open(out_path, "w", encoding="utf-8") as out:
                        out.write(content)
                    print(f"-> Saved to {out_path}")
            
            # Check tool_calls arguments and responses
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                args = tc.get("args", {})
                args_str = json.dumps(args, ensure_ascii=False)
                if "async def daga_equip" in args_str:
                    step_idx = data.get("step_index", i)
                    print(f"Match in tool_args at Step {step_idx}")
                    out_path = f"scratch/args_step_{step_idx}.txt"
                    with open(out_path, "w", encoding="utf-8") as out:
                        out.write(args_str)
                    print(f"-> Saved to {out_path}")
        except Exception as e:
            pass
print("Done searching.")
