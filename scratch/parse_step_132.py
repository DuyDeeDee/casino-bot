import json
import re

with open("scratch/step_132_extracted.txt", "r", encoding="utf-8") as f:
    text = f.read()

# Let's find ReplacementContent:
# and everything after it.
# We will use regex or string methods.
# The format in daga_edits_history.txt is:
# ReplacementContent:
# [complete replacement string, possibly with quotes and newlines]
# or we can parse it by splitting.

parts = text.split("ReplacementContent:\n")
if len(parts) > 1:
    content = parts[1]
    # If it has a trailing boundary marker, strip it
    content = content.split("--------------------------------------------------------------------------------")[0]
    # The content is a JSON-encoded string (or raw string representation)?
    # Wait, in inspect_transcript.py we wrote: out.write(str(args.get('ReplacementContent')))
    # So it is the raw string that was written.
    # Let's load it and write it out.
    # If it was saved as json, we can load it. Let's see if it's JSON or just text.
    # Let's write the content directly.
    with open("scratch/replacement_132.txt", "w", encoding="utf-8") as out:
        out.write(content)
    print("Replacement 132 content saved.")
else:
    print("ReplacementContent not found.")
