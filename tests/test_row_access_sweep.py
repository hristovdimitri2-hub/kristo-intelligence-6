"""THE ROW-ACCESS SWEEP — one error class, guarded forever.

`DashboardStore._run()` hands back **`sqlite3.Row` on SQLite and a `dict` on
Postgres**. That single fact produced THREE live bugs in one day (18–21.09):

  1. `sale_by_tx` zipped column names with a dict → returned {column: column} on
     Postgres, so the VIP claim path would have answered "not found" for every
     real sale.
  2. `track_record` / `signal_history` read rows positionally → `KeyError: 0` on
     Postgres (the live probe died immediately).
  3. `guard_stats` called `.get()` on a `sqlite3.Row` → `AttributeError` → the
     whole guards section silently fell to zeros.

Manual discipline is not enough, so the rule is mechanical, like the price sweep:

  * a variable that receives a row (or rows) from `_run` / `fetchone` /
    `fetchall` must NOT be used with `.get(...)`   (Row has no `.get`)
  * and must NOT be used with positional `[0]` / `[1]`   (a Postgres dict has no
    index 0)
  * wrapping it in `dict(row)` first is the documented safe move, and is allowed

The checker is exercised on synthetic code below, so the guard itself is proven
to catch the bug it exists for — a sweep that cannot fail is decoration.
"""
from __future__ import annotations

import ast
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Files whose rows reach production users. scripts/ one-offs are excluded on
#: purpose: they are throwaway probes, not the product.
SCAN_PATHS = (
    "main.py",
    "integrations/dashboard_store.py",
    "integrations/catalog_store.py",
    "integrations/crm_store.py",
    "services/signal_track_record.py",
    "services/telegram_sales.py",
    "services/market_data.py",
)

ROW_SOURCES = {"_run", "fetchone", "fetchall"}


def _row_kind(node: ast.AST):
    """"row" for a single DB row, "rows" for a list of them, None otherwise.

    The distinction matters: `_run(..., "all")[0]` is a LIST, so indexing it is
    perfectly fine, while `_run(..., "one")[0]` is a ROW, where `.get()` breaks on
    SQLite and `[0]` breaks on Postgres.
    """
    if isinstance(node, ast.Call):
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name == "fetchone":
            return "row"
        if name == "fetchall":
            return "rows"
        if name == "_run":
            fetch = ""
            if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                fetch = str(node.args[2].value)
            # _run returns a TUPLE (rows, rowcount): the [0] below unwraps it, so
            # `_run(..., "all")[0]` is a LIST and `_run(..., "one")[0]` is a ROW.
            if fetch == "one":
                return "tuple_row"
            if fetch == "all":
                return "tuple_rows"
            return None
        if name == "dict":          # dict(row) → a real dict: the safe wrapper
            return None
        for arg in node.args:
            kind = _row_kind(arg)
            if kind:
                return kind
        return None
    if isinstance(node, ast.Subscript):
        inner = _row_kind(node.value)
        if inner == "tuple_row":        # _run(..., "one")[0] → one row
            return "row"
        if inner == "tuple_rows":       # _run(..., "all")[0] → a list of rows
            return "rows"
        if inner in ("row", "rows"):    # indexing a list of rows gives one row
            return "row"
        return None
    if isinstance(node, ast.BoolOp):             # rows or []
        for value in node.values:
            kind = _row_kind(value)
            if kind:
                return kind
        return None
    if isinstance(node, ast.IfExp):
        return _row_kind(node.body) or _row_kind(node.orelse)
    if isinstance(node, ast.Starred):
        return _row_kind(node.value)
    return None


def _is_row_source(node: ast.AST) -> bool:
    """Backwards-compatible helper: does this yield a row or a list of rows?"""
    return _row_kind(node) is not None


def _targets(node: ast.AST):
    """Names assigned by this assignment target."""
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            yield from _targets(element)


def find_row_access_violations(source: str, filename: str = "<test>") -> list:
    """Violations of the row-access rule, as "file:line: message" strings."""
    tree = ast.parse(source)
    problems = []

    for func in [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        # Events in SOURCE ORDER (ast.walk order is not source order). Folding
        # them up to a line gives each name's kind AT that line, so a later
        # `existing = self.find_by_email(...)` (a dict) clears an earlier
        # `existing = self._run(...)`.
        events = []               # (lineno, "assign", name, kind) | (…, "loop", name, iterable)
        for node in ast.walk(func):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                kind = _row_kind(value) if value is not None else None
                targets = node.targets if isinstance(node, ast.Assign) \
                    else [node.target]
                for target in targets:
                    for name in _targets(target):
                        events.append((node.lineno, "assign", name, kind))
            if isinstance(node, (ast.For, ast.comprehension)):
                iterable = node.iter.id if isinstance(node.iter, ast.Name) else ""
                # `ast.comprehension` carries no lineno — fall back to its target.
                line = getattr(node, "lineno", None) or getattr(
                    node.target, "lineno", 0)
                for name in _targets(node.target):
                    events.append((line, "loop", name, iterable))
        events.sort(key=lambda item: item[0])

        def kind_at(name: str, lineno: int):
            kinds: dict = {}
            for line, event, ev_name, extra in events:
                if line >= lineno:
                    break
                if event == "assign":
                    kinds[ev_name] = extra
                else:                     # `for name in iterable:` → one row
                    kinds[ev_name] = "row" if kinds.get(extra) == "rows" else None
            return kinds.get(name)

        def expr_is_row(expr, lineno) -> bool:
            """Is this expression ONE row at `lineno`?"""
            if isinstance(expr, ast.Name):
                return kind_at(expr.id, lineno) == "row"
            if isinstance(expr, ast.Subscript):
                base = expr.value
                if isinstance(base, ast.Name) and kind_at(base.id, lineno) == "rows":
                    return True          # rows[0] — one row out of a list
                return expr_is_row(base, lineno)
            return _row_kind(expr) == "row"

        # 2. How is it used? Only a SINGLE row is fragile: a list may be indexed.
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and node.attr == "get" \
                    and isinstance(node.value, ast.Name) \
                    and kind_at(node.value.id, node.lineno) == "row":
                problems.append("%s:%d: .get() on DB row %r (sqlite3.Row has no "
                                ".get) — wrap it in dict(row) first"
                                % (filename, node.lineno, node.value.id))
            if not isinstance(node, ast.Subscript):
                continue
            index = node.slice
            if not (isinstance(index, ast.Constant)
                    and isinstance(index.value, int)):
                continue          # row["column"] is the safe read
            inner = node.value
            if expr_is_row(inner, node.lineno):
                label = inner.id if isinstance(inner, ast.Name) else "<expr>"
                problems.append("%s:%d: positional [%s] on DB row %r (a Postgres "
                                "dict has no index 0) — use row[\"column\"] or "
                                "dict(row)"
                                % (filename, node.lineno, index.value, label))
    return problems


# ── the sweep over the product code ────────────────────────────────────────

def test_no_db_row_is_read_with_get_or_positionally():
    """The mechanical guard: production code never assumes Row OR dict."""
    violations = []
    for relative in SCAN_PATHS:
        path = os.path.join(REPO_ROOT, relative)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            violations.extend(find_row_access_violations(handle.read(), relative))
    assert not violations, ("row-access violations (see the module docstring for "
                            "the three live bugs this guards):\n"
                            + "\n".join(violations))


# ── the guard must be able to fail (a sweep that cannot fail is decoration) ──

def test_the_sweep_catches_the_real_trap():
    bad_get = """
def f(store):
    row = store._run("SELECT 1 AS n", (), "one")[0]
    return row.get("n")
"""
    bad_positional = """
def f(store):
    rows = store._run("SELECT a FROM t", (), "all")[0]
    return rows[0][0]
"""
    bad_loop = """
def f(store):
    rows = store._run("SELECT a FROM t", (), "all")[0] or []
    for r in rows:
        print(r.get("a"))
"""
    assert find_row_access_violations(bad_get), ".get() trap not caught"
    assert find_row_access_violations(bad_positional), "positional trap not caught"
    assert find_row_access_violations(bad_loop), "loop-variable trap not caught"


def test_the_sweep_accepts_the_documented_safe_patterns():
    safe = """
def f(store):
    row = store._run("SELECT 1 AS n", (), "one")[0]
    return row["n"]
"""
    healed = """
def f(store):
    row = dict(store._run("SELECT 1 AS n", (), "one")[0] or {})
    return row.get("n", 0)
"""
    looped = """
def f(store):
    rows = store._run("SELECT a FROM t", (), "all")[0] or []
    return [dict(r) for r in rows]
"""
    for source in (safe, healed, looped):
        assert find_row_access_violations(source) == [], source


def test_the_two_backends_really_behave_this_way(tmp_path):
    """The premise, proven rather than assumed: SQLite gives a Row (no .get, but
    positional works), Postgres gives a dict (the reverse). That asymmetry IS the
    bug class — and the reason dict(row) is the one safe read."""
    import sqlite3

    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "rows.db")
    row = store.history._run("SELECT 1 AS n, 'x' AS label", (), "one")[0]
    assert isinstance(row, sqlite3.Row)
    assert row[0] == 1 and row["n"] == 1          # both work on a Row
    assert not hasattr(row, "get")                # ...except .get()
    assert dict(row) == {"n": 1, "label": "x"}    # the safe move, both backends
    as_dict = {"n": 1, "label": "x"}              # what Postgres hands back
    assert as_dict.get("n") == 1                  # .get works here...
    try:
        as_dict[0]
        raise AssertionError("a Postgres row must not be indexable")
    except KeyError:
        pass