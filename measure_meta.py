import io, json
raw = io.open("server.json", encoding="utf-8").read()
doc = json.loads(raw)
meta = doc["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]

def size(obj):
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

print("  whole _meta value (compact) : %5d bytes" % size(meta))
print("  whole _meta value (as ours) : %5d bytes" % len(json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")))
print("")
print("  breakdown:")
total = 0
for key, value in meta.items():
    n = size(value)
    total += n
    print("    %-18s %5d bytes" % (key, n))
print("    %-18s %5d" % ("(sum of parts)", total))
print("")
print("  the tools, individually:")
for tool in meta["tools"]:
    print("    %-30s %5d bytes  (description %d)"
          % (tool["name"], size(tool), len(tool["description"].encode("utf-8"))))
print("")
print("  paid_endpoints is redundant? does each tool already carry endpoint+price:")
for tool in meta["tools"]:
    print("    %-30s endpoint=%-26s price=%s"
          % (tool["name"], tool.get("endpoint"), tool.get("price_usd")))
print("")
print("  size if paid_endpoints is removed: %d bytes" % (size(meta) - size(meta["paid_endpoints"])))
