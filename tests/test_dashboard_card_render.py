"""The cards the owner reads are built in the BROWSER, so they are tested there.

`test_dashboard_plain_summary.py` proves the payload carries the customer half of
the money. It cannot prove the page prints it — and on 09.11 the difference was
real: the week cards were handed their new "от реални клиенти: $X" sentence as
the `hero` argument (`card()` took three parameters), so the sentence was silently
dropped and the card turned GREEN instead. Every Python assertion in that file
passed, because the string was in the template.

These tests run the page's REAL script under node with a stubbed DOM and assert
what the renderers actually produce. The owner's complaint was never that the
numbers were absent — it was that "16 · $0.15 днес" was read as income while all
sixteen payments were our own demo key settling against ourselves.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templates" / "dashboard.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to run the REAL page renderers")

# A DOM small enough to be honest: every element the renderers touch exists, and
# nothing else does. `fetch` never settles, because these tests render a payload
# they were handed rather than waking the network.
STUB = """const store = {};
const el = () => ({innerHTML: '', textContent: '', style: {},
                  closest: () => null, addEventListener: () => {},
                  querySelector: () => null, querySelectorAll: () => []});
global.document = {
  getElementById: (id) => {
    if (!store[id]) store[id] = el();
    return store[id];
  },
  querySelector: () => el(),
  querySelectorAll: () => [],
  addEventListener: () => {},
};
global.Chart = function () { return {destroy() {}, update() {}}; };
global.fetch = () => new Promise(() => {});
global.setInterval = () => 0;
"""

DRIVER = """
const payload = JSON.parse(process.argv[2]);
renderAnswers(payload.summary || {});
renderDays(payload.summary || {});
renderOnchain(payload.onchain || {});
process.stdout.write(JSON.stringify({
  cards: document.getElementById('answer-cards').innerHTML,
  week: document.getElementById('week-cards').innerHTML,
  onchain: document.getElementById('onchain-cards').innerHTML,
  classes: document.getElementById('onchain-classes').innerHTML,
  days: document.getElementById('days-body').innerHTML,
}));
"""


def _page_script() -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html,
                        re.DOTALL | re.IGNORECASE)
    assert len(blocks) == 1, "the board is expected to ship one inline script"
    return blocks[0]


def _render(tmp_path, summary: dict, onchain: dict) -> dict:
    harness = tmp_path / "render.js"
    harness.write_text(STUB + _page_script() + DRIVER, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(harness), json.dumps({"summary": summary, "onchain": onchain},
                                        ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        cwd=str(REPO))
    assert proc.returncode == 0, "the page's own script failed: %s" % (
        (proc.stderr or "")[:600])
    return json.loads(proc.stdout)


def _day_block(count, usdc, client_count, client_usdc) -> dict:
    day = {"from": "2026-11-09", "to": "2026-11-09", "count": count,
           "usdc": usdc, "client_count": client_count,
           "client_usdc": client_usdc}
    return {"today": day, "yesterday": dict(day, count=0, usdc=0.0),
            "this_week": dict(day), "last_week": dict(day, count=0, usdc=0.0),
            "all_time": {"count": count, "usdc": usdc, "payers": 9,
                         "days_live": 68, "first_sale": "2026-09-02T13:28:41Z"},
            "last_sale": {"amount_usdc": 0.003, "at": "2026-11-09T16:30:11Z",
                          "ago_words": "преди 8 мин"},
            "busiest_hour": None, "week_change": {}, "week_change_usdc": {},
            "best_day": None, "sales_by_day": [], "human_or_bot": []}


def test_a_day_of_our_own_tests_is_not_shown_as_a_green_sale(tmp_path):
    """The live shape of 09.11: sixteen payments, $0.15, zero customers."""
    out = _render(tmp_path,
                  _day_block(16, 0.15, 0, 0.0),
                  {"today_count": 16, "today_usdc": 0.15,
                   "today_client_count": 0, "today_client_usdc": 0.0,
                   "today_date": "2026-11-09"})

    assert "0 от реални клиенти" in out["cards"]
    # 0 customers out of 16 payments may not be painted as a win.
    today_card = out["cards"].split('class="card')[2]
    assert "warn" in today_card
    assert "hero" not in today_card
    assert "0 от реални клиенти" in out["onchain"]
    assert "warn" in out["onchain"].split('class="card')[-1]


def test_a_real_customer_is_counted_and_the_card_stops_warning(tmp_path):
    out = _render(tmp_path,
                  _day_block(3, 0.011, 2, 0.008),
                  {"today_count": 3, "today_usdc": 0.011,
                   "today_client_count": 2, "today_client_usdc": 0.008,
                   "today_date": "2026-11-09"})

    assert "2 от реални клиенти" in out["cards"]
    assert "warn" not in out["cards"].split('class="card')[2]
    assert "2 от реални клиенти" in out["onchain"]


def test_the_week_cards_print_the_customer_half_of_the_money(tmp_path):
    """The sub-line that was swallowed by the wrong argument.

    `card(v, k, hero)` has no room for a sentence; the call passed one anyway, so
    the text vanished and `hero` became truthy. The card must show the customer
    amount, in words, not merely be handed it.
    """
    out = _render(tmp_path,
                  _day_block(16, 0.15, 0, 0.0),
                  {"today_count": 16, "today_usdc": 0.15,
                   "today_client_count": 0, "today_client_usdc": 0.0})
    assert out["week"].count("от реални клиенти: $0.00") == 2

    with_client = _render(tmp_path,
                          _day_block(3, 0.011, 2, 0.008),
                          {"today_count": 3, "today_usdc": 0.011,
                           "today_client_count": 2, "today_client_usdc": 0.008})
    assert with_client["week"].count("от реални клиенти: $0.008") == 2


def test_the_day_table_counts_clients_in_its_own_column(tmp_path):
    summary = _day_block(16, 0.15, 0, 0.0)
    summary["sales_by_day"] = [
        {"date": "2026-11-08", "count": 4, "usdc": 0.014,
         "client_count": 4, "client_usdc": 0.014},
        {"date": "2026-11-09", "count": 16, "usdc": 0.15,
         "client_count": 0, "client_usdc": 0.0},
    ]
    out = _render(tmp_path, summary, {"today_count": 16, "today_usdc": 0.15,
                                      "today_client_count": 0,
                                      "today_client_usdc": 0.0})
    rows = out["days"].split("</tr>")
    # Newest first: today's row carries the day's own customer count.
    assert '<td class="num">16</td>' in rows[0]
    assert '<td class="num">0</td>' in rows[0]
    assert '<td class="num">4</td>' in rows[1]
    # Yesterday's four payments were four different customers.
    assert rows[1].count('<td class="num">4</td>') == 2


def test_the_all_time_class_tags_say_all_time(tmp_path):
    """They sit under the "Днес" card and add up to $0.32 while it shows $0.15."""
    out = _render(tmp_path, _day_block(16, 0.15, 0, 0.0),
                  {"today_count": 16, "today_usdc": 0.15,
                   "today_client_count": 0, "today_client_usdc": 0.0,
                   "by_class": {"own_key": {"count": 28, "total_usdc": 0.191}},
                   "class_labels": {"own_key": "нашият демо ключ — не е клиент"},
                   "last_scanned_block": 55259535})
    assert "от началото:" in out["classes"]
    assert "нашият демо ключ — не е клиент: 28 tx" in out["classes"]
