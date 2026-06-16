import json

raw_code = open("scratch/step_1138_code.py", "r", encoding="utf-8").read()
# The file contains a JSON-like string (with quotes). Let's load it.
# We can wrap it as a JSON string and parse it, or parse it directly if it's quoted.
try:
    # If the file content starts and ends with double quotes, it's a JSON string literal.
    decoded = json.loads(raw_code)
except Exception:
    # Try reading as Python string literal evaluation
    try:
        import ast
        decoded = ast.literal_eval(raw_code)
    except Exception as e:
        decoded = raw_code
        print("Failed to decode, using raw code:", e)

open("scratch/step_1138_decoded.py", "w", encoding="utf-8").write(decoded)
print("Decoded file written successfully.")
