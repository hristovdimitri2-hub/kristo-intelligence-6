# -*- coding: utf-8 -*-
"""Local-only: generate fresh UUID v4 into TEMP kristo_tuesday_id.txt."""
from __future__ import annotations

import os
import re
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

temp = os.environ.get("TEMP") or "."
ident = str(uuid.uuid4())
path = os.path.join(temp, "kristo_tuesday_id.txt")
open(path, "w", encoding="ascii").write(ident)

print("identifier:", ident)
print("len:", len(ident))
print("pattern_ok:", bool(re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", ident)))
print("written:", path, os.path.getsize(path), "B")
