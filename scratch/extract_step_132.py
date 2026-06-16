import re

history_path = r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\daga_edits_history.txt"
with open(history_path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's find "=== Step 132 Tool: replace_file_content ==="
# and split the text after it.
parts = text.split("=== Step 132 Tool: replace_file_content ===")
if len(parts) > 1:
    step_content = parts[1].split("===")[0]
    
    # Save the step content to a separate file
    with open(r"c:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\scratch\step_132_extracted.txt", "w", encoding="utf-8") as out:
        out.write(step_content)
    print("Step 132 extracted successfully!")
else:
    print("Step 132 not found in history.")
