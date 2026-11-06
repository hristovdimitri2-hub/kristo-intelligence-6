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


# ── the chain scan is opt-in, and its absence is announced ───────────────────
# receiver_scan() reads ~302,400 Base blocks over a public RPC and took over
# twenty minutes, so this tool — whose whole purpose is to be run weekly — was
# not being run. The listing diff it exists for takes ~16 seconds. The fix is to
# make the scan opt-in, but the same rule as everywhere else applies: a thing
# that did not happen must not read as a thing that found nothing. "Scan skipped"
# must never look like "nobody paid".


@pytest.fixture()
def scan_calls(monitor, offline, monkeypatch):
    """Record every receiver_scan() call instead of performing it."""
    calls = []
    monkeypatch.setattr(monitor, "receiver_scan", lambda: calls.append(True))
    return calls


def test_a_normal_run_does_not_pay_for_the_chain_scan(
        monitor, offline, scan_calls):
    """The default has to be the sixteen-second path, or it stays unused."""
    monitor.main()

    assert scan_calls == [], (
        "a plain run still performed the ~20-minute chain scan — that is the "
        "behaviour that stopped this tool from being run at all"
    )


def test_the_skipped_scan_is_announced_and_never_reads_as_no_payments(
        monitor, offline, scan_calls, capsys):
    """Silence about a skipped scan is the defect; saying nothing is not."""
    monitor.main()
    out = capsys.readouterr().out

    assert "NOT RUN" in out, (
        "the run skipped the on-chain scan without saying so — the reader has no "
        "way to tell that from a silent week"
    )
    # The announcement must not accidentally claim a result it does not have.
    for false_claim in ("no payments", "0 payments", "no transfers",
                        "no new payments"):
        assert false_claim not in out.lower(), (
            f"the skip was described as {false_claim!r} — a scan that did not "
            f"run cannot report that nobody paid"
        )


def test_scan_flag_performs_the_scan(monitor, offline, scan_calls, monkeypatch):
    """--scan is the opt-in and it must actually opt in."""
    monkeypatch.setattr(sys, "argv", ["listing_monitor.py", "--scan"])

    monitor.main()

    assert scan_calls == [True], "--scan did not run the chain scan"


def test_no_scan_flag_is_accepted_and_skips(
        monitor, offline, scan_calls, monkeypatch):
    """Both spellings work, so a caller can be explicit either way."""
    monkeypatch.setattr(sys, "argv", ["listing_monitor.py", "--no-scan"])

    monitor.main()

    assert scan_calls == [], "--no-scan ran the chain scan anyway"


def test_the_two_scan_flags_cannot_both_be_given(
        monitor, offline, monkeypatch):
    """A contradictory request must fail loudly rather than pick one silently."""
    monkeypatch.setattr(sys, "argv",
                        ["listing_monitor.py", "--scan", "--no-scan"])

    with pytest.raises(SystemExit):
        monitor.main()


# ── "no such listing" is not "a listing with nothing in it" ──────────────────
# The Glama server entry for this project answers HTTP 404 Server not found, yet
# the monitor recorded tools=0, quality_score=None, spdx_license=None — identical
# to what a real-but-empty listing would produce, because _glama_get() turned
# every failure into None and the caller wrote `or {}`. For over a month the tool
# reported a MISSING listing as an EMPTY one, and the two need opposite fixes:
# an empty listing is a metadata job, a missing one is an "add it first" job.


def _glama_stub(statuses):
    """A _glama_get replacement keyed by the path suffix it is asked for."""
    def fake(path, key, params=None):
        for needle, answer in statuses.items():
            if needle in path:
                return answer
        return 200, {}
    return fake


def test_a_404_listing_is_recorded_as_missing_not_as_zero_tools(
        monitor, monkeypatch):
    """The defect: a missing listing was indistinguishable from an empty one."""
    monkeypatch.setattr(monitor, "_glama_get", _glama_stub({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": (404, None),
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": (200, {"healthy": True}),
    }))

    state = monitor.fetch_glama_state("fake-key")

    assert state["servers"]["status"] == 404
    assert state["servers"]["missing"] is True, (
        "a 404 was not recorded as a missing listing — nothing downstream can "
        "then tell it apart from a listing that exists with no tools"
    )


def test_a_real_listing_scoring_zero_tools_is_not_marked_missing(
        monitor, monkeypatch):
    """The other half: a genuine 200 with no tools must stay 'not missing'."""
    monkeypatch.setattr(monitor, "_glama_get", _glama_stub({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": (200, {"tools": []}),
        f"/v1/connectors/{monitor.GLAMA_CONNECTOR}": (200, {}),
    }))

    state = monitor.fetch_glama_state("fake-key")

    assert state["servers"]["status"] == 200
    assert state["servers"]["missing"] is False
    assert state["servers"]["tools"] == 0


def test_a_failed_request_is_distinguishable_from_a_completed_one(
        monitor, monkeypatch):
    """status 0 means the request never completed — not a 404, not a 200."""
    monkeypatch.setattr(monitor, "_glama_get", _glama_stub({
        f"/v1/servers/{monitor.GLAMA_SERVERS}": (0, None),
    }))

    state = monitor.fetch_glama_state("fake-key")

    assert state["servers"]["status"] == 0
    assert state["servers"]["missing"] is False, (
        "a transport failure was reported as a confirmed missing listing"
    )


def test_a_listing_appearing_is_reported_as_such(monitor):
    """If the listing gets added, the next run must say so, not just '0 -> 6'."""
    before = {"servers": {"status": 404, "missing": True, "tools": 0},
              "connector": {}, "positions": {}}
    after = {"servers": {"status": 200, "missing": False, "tools": 6},
             "connector": {}, "positions": {}}

    changes = monitor.diff_glama(before, after)
    joined = " | ".join(changes)

    assert "missing" in joined, (
        "the listing appearing was not called out — the single most important "
        "event this section can report"
    )


def test_a_failed_search_is_unknown_not_absent(monitor):
    """A search that did not answer must never read as 'we dropped out'."""
    before = {"servers": {}, "connector": {},
              "positions": {"defi": {"position": 2, "shown": 25, "status": 200}}}
    after = {"servers": {}, "connector": {},
             "positions": {"defi": {"position": None, "shown": 0, "status": 503}}}

    changes = monitor.diff_glama(before, after)
    joined = " | ".join(changes)

    assert "UNKNOWN" in joined, (
        "a failed search was reported as a ranking change: %r" % joined
    )
    assert "-> absent" not in joined, (
        "a failed search was reported as us being absent from the results"
    )


