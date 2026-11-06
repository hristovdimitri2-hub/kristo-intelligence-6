"""The saved state must be trustworthy or absent — never quietly broken.

``docs/monitor_state.json`` is the baseline every run diffs against, and the
whole value of this tool is noticing what MOVED. Three different situations
exist, and they must not collapse into one:

  * the file is absent              -> a first run; nothing to compare; normal
  * the file is readable            -> compare, and report what moved
  * the file is present, UNREADABLE -> we do not know what moved

The third used to be swallowed into the first: ``except Exception: prev = {}``
made a torn or truncated file indistinguishable from "no previous run", so the
monitor printed ``(no changes vs previous run)`` — a false all-clear from the one
tool whose entire job is to notice. That is the same defect class as an
unreadable number rendering as a zero on the dashboard, and the rule is the same:
**an absence must never be reported as "nothing moved".**

These tests also pin the write side, because the reader can only be taught to
detect corruption if the writer stops being able to create it: a run that dies
mid-save must leave the previous state intact, not a half-written file.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def monitor():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("scripts.listing_monitor")


def _state(rank_for_eth=3, score=80):
    """A minimal but complete state document of the shape the monitor writes."""
    return {
        "reliability": {
            "name": "Kristo Intelligence",
            "band": "strong",
            "score": score,
            "computed_at": "2026-11-05T00:00:00Z",
            "description": "DeFi signals API",
            "price_min": 0.003,
        },
        "ranks": {
            term: {"position": rank_for_eth, "total": 42}
            for term in ("eth", "defi", "signals", "whale", "rug", "ondo",
                         "kaito", "degen")
        },
        "glama": {},
    }


@pytest.fixture()
def offline(monitor, monkeypatch, tmp_path):
    """Point the module at a temp state file and take it off the network.

    fetch_state() and receiver_scan() are the only two things main() reaches
    out to; stubbing them keeps every assertion below about the state file and
    nothing else.
    """
    state_path = tmp_path / "monitor_state.json"
    monkeypatch.setattr(monitor, "STATE_PATH", str(state_path))
    monkeypatch.setattr(monitor, "fetch_state", lambda: _state())
    monkeypatch.setattr(monitor, "receiver_scan", lambda: None)
    monkeypatch.setattr(sys, "argv", ["listing_monitor.py"])
    return state_path


def test_a_corrupt_baseline_is_loud_and_never_called_no_changes(
        monitor, offline, capsys):
    """The defect: a torn file used to print "(no changes vs previous run)"."""
    offline.write_text('{"reliability": {"band": "stro', encoding="utf-8")

    code = monitor.main()
    out = capsys.readouterr().out

    assert "no changes vs previous run" not in out, (
        "a baseline we could not read was reported as 'nothing moved' — that is "
        "a false all-clear from the tool whose job is to notice"
    )
    assert code == 2, (
        "corruption must be distinguishable from 'no change' (0) and from "
        "'something changed' (1); got %r" % code
    )
    lowered = out.lower()
    assert "unreadable" in lowered or "corrupt" in lowered, (
        "the run never said out loud that the baseline could not be read"
    )


def test_a_missing_baseline_is_still_a_normal_first_run(
        monitor, offline, capsys):
    """Absent is not corrupt — a first run must not raise a false alarm."""
    code = monitor.main()
    out = capsys.readouterr().out

    assert code == 0, "a first run with no baseline is not an error"
    assert "unreadable" not in out.lower()
    assert "corrupt" not in out.lower()


def test_a_readable_baseline_still_reports_what_moved(
        monitor, offline, capsys, monkeypatch):
    """The path that matters most must keep working: a real move is reported."""
    offline.write_text(json.dumps(_state(rank_for_eth=3)), encoding="utf-8")
    monkeypatch.setattr(monitor, "fetch_state", lambda: _state(rank_for_eth=9))

    code = monitor.main()
    out = capsys.readouterr().out

    assert "RANK q=eth" in out, "a rank move from 3 to 9 was not reported"
    assert "3 -> 9" in out


def test_a_baseline_that_is_valid_json_but_not_an_object_is_not_trusted(
        monitor, offline, capsys):
    """'Readable' is not the same as 'usable'.

    A JSON file holding a list or a bare string parses fine and then explodes
    inside the diff (``prev.get``) or, worse, silently yields no changes. If we
    cannot use it as a baseline, that is the unreadable case.
    """
    offline.write_text('[1, 2, 3]', encoding="utf-8")

    code = monitor.main()
    out = capsys.readouterr().out

    assert code == 2
    assert "no changes vs previous run" not in out


def test_the_saved_state_is_written_atomically(monitor, offline, monkeypatch):
    """A run that dies mid-save must not leave a half-written baseline."""
    import os as real_os

    replaced = []
    original = real_os.replace

    def spy(src, dst, *a, **kw):
        replaced.append((str(src), str(dst)))
        return original(src, dst, *a, **kw)

    monkeypatch.setattr(monitor.os, "replace", spy)

    monitor.main()

    assert replaced, "the state was written in place — a crash mid-write tears it"
    src, dst = replaced[-1]
    assert dst == str(offline), "the atomic rename did not land on the state file"
    assert src.endswith(".tmp"), "the temp file was not named as one"
    # The temp file must not survive the rename.
    assert not Path(src).exists()
    assert json.loads(offline.read_text(encoding="utf-8"))["ranks"]


def test_a_corrupt_baseline_still_self_heals(monitor, offline):
    """Reporting the corruption must not leave the tool broken forever."""
    offline.write_text("not json at all", encoding="utf-8")

    monitor.main()

    healed = json.loads(offline.read_text(encoding="utf-8"))
    assert isinstance(healed, dict) and "ranks" in healed, (
        "after reporting a corrupt baseline the run must save a good one"
    )
