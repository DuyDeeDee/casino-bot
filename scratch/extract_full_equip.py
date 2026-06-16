# -*- coding: utf-8 -*-
import json
import re

log_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\65ae5109-299d-47af-91c4-8fe0c179ee47\.system_generated\logs\transcript.jsonl"

found_count = 0
with open(log_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            # Search in content, tool calls, and tool outputs
            step_idx = data.get("step_index", i)
            source = data.get("source", "")
            
            # Check content
            content = data.get("content", "")
            if "async def daga_equip" in content and "update_cock" in content:
                print(f"Found in content at Step {step_idx}:")
                # print the full block
                idx = content.find("async def daga_equip")
                print(content[idx:idx+2000])
                print("="*80)
                found_count += 1
                
            # Check tool_calls or response
            # Let's search raw line for keywords to be safe
            if "async def daga_equip" in line and "update_cock" in line:
                print(f"Found in raw line {i} (Step {step_idx}):")
                # find the JSON structure
                # We can print keys that have it
                for key, val in data.items():
                    if isinstance(val, str) and "async def daga_equip" in val and "update_cock" in val:
                        idx = val.find("async def daga_equip")
                        print(f"Key '{key}':")
                        print(val[idx:idx+2500])
                        print("="*80)
                        found_count += 1
                    elif isinstance(val, list):
                        # check elements
                        for item in val:
                            if isinstance(item, dict):
                                for k2, v2 in item.items():
                                    if isinstance(v2, str) and "async def daga_equip" in v2 and "update_cock" in v2:
                                        idx = v2.find("async def daga_equip")
                                        print(f"List Key '{key}' -> Dict Key '{k2}':")
                                        print(v2[idx:idx+2500])
                                        print("="*80)
                                        found_count += 1
        except Exception as e:
            pass

print(f"Search done. Found {found_count} matches.")
