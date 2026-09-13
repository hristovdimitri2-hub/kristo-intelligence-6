"""Extract the Finance section + alphabetical neighbors from the remote README."""
import requests

url = "https://raw.githubusercontent.com/punkpeye/awesome-remote-mcp-servers/main/README.md"
t = requests.get(url, timeout=30).text
lines = t.splitlines()

# Find section boundaries
start = None
end = None
for i, ln in enumerate(lines):
    if ln.startswith("### ") and "Finance" in ln:
        start = i
    elif start is not None and ln.startswith("### ") and "Finance" not in ln:
        end = i
        break

print("=== FINANCE SECTION (verbatim) ===")
for i in range(start, end):
    print(f"{i+1:4d}: {lines[i]}")
