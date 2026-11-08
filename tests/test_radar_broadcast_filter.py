"""Broadcast detection: a spammer is found by SPREAD, not by wording.

BORROWED, AND REBUILT RATHER THAN COPIED. A foreign radar that watches this same
ecosystem states its rule plainly: a branch is cut when "one author or one host
appears in three or more FOREIGN repositories within two weeks". The idea worth
taking is that the identifier is the spread — so rewording cannot defeat it,
which is the failure mode every keyword filter eventually has.

WHY THE WATCH LIST HAD TO GROW IN THE SAME CHANGE. This script watched TWO
repositories. A "3+ repositories" rule cannot fire against two, and a rule that
cannot fire is worse than no rule at all: it reads like protection while
providing none. That is why `MONITORED` grew from 2 to 10 in the same commit —
and the test below pins the relationship, so the list cannot shrink back without
the rule being noticed as dead.
"""

from datetime import datetime, timezone

from scripts import ap2_radar as radar

TODAY = datetime(2026, 11, 8, tzinfo=timezone.utc)


def _item(user, updated, number=1, title="a thread"):
    return {"user": user, "updated": updated, "number": number, "title": title}


# ── the rule itself ─────────────────────────────────────────────────────────

def test_one_author_in_three_repositories_is_a_broadcaster():
    pairs = [("a/one", _item("spammer", "2026-11-05", 1)),
             ("b/two", _item("spammer", "2026-11-05", 2)),
             ("c/three", _item("spammer", "2026-11-06", 3))]
    found = radar._broadcast_authors(pairs, TODAY)
    assert "spammer" in found
    assert found["spammer"] == ["a/one", "b/two", "c/three"]


def test_two_repositories_is_not_enough():
    """A contributor who works in two places is a contributor."""
    pairs = [("a/one", _item("honest", "2026-11-05", 1)),
             ("b/two", _item("honest", "2026-11-05", 2))]
    assert radar._broadcast_authors(pairs, TODAY) == {}


def test_the_same_thread_count_in_ONE_repository_is_not_spread():
    """Chatty is not the same as spammy. Seven issues in one repo is one repo."""
    pairs = [("a/one", _item("chatty", "2026-11-05", n)) for n in range(1, 8)]
    assert radar._broadcast_authors(pairs, TODAY) == {}


def test_items_outside_the_window_do_not_count():
    """A long-standing contributor who touches three repos across a year is not
    a broadcaster; the same person doing it in a fortnight is."""
    pairs = [("a/one", _item("old", "2026-09-01", 1)),
             ("b/two", _item("old", "2026-09-02", 2)),
             ("c/three", _item("old", "2026-09-03", 3))]
    assert radar._broadcast_authors(pairs, TODAY) == {}


def test_only_the_in_window_repositories_are_listed():
    """The evidence shown must be the evidence that decided it."""
    pairs = [("a/one", _item("mixed", "2026-11-05", 1)),
             ("b/two", _item("mixed", "2026-11-05", 2)),
             ("c/three", _item("mixed", "2026-11-06", 3)),
             ("d/four", _item("mixed", "2026-08-01", 4))]
    found = radar._broadcast_authors(pairs, TODAY)
    assert found["mixed"] == ["a/one", "b/two", "c/three"]
    assert "d/four" not in found["mixed"]


def test_an_unparseable_date_does_not_excuse_an_author():
    """Dropping them would UNDER-report spread, and the thing being guarded
    against is noise — so an unknown date counts rather than being dropped."""
    pairs = [("a/one", _item("x", "", 1)), ("b/two", _item("x", "not-a-date", 2)),
             ("c/three", _item("x", "2026-11-05", 3))]
    assert "x" in radar._broadcast_authors(pairs, TODAY)


def test_an_item_without_an_author_is_ignored_not_crashed():
    pairs = [("a/one", _item("", "2026-11-05", 1)),
             ("a/one", {"number": 2, "updated": "2026-11-05", "title": "t"})]
    assert radar._broadcast_authors(pairs, TODAY) == {}


def test_an_empty_run_is_empty():
    assert radar._broadcast_authors([], TODAY) == {}


# ── the relationship that makes the rule alive ──────────────────────────────

def test_the_watch_list_is_wide_enough_for_the_rule_to_fire():
    """THE guard for a dead rule.

    With fewer than `BROADCAST_MIN_REPOS` repositories watched, no author can
    ever reach the threshold — the check would run on every scan and never once
    be able to act, which is the worst kind of safety code.
    """
    assert len(radar.MONITORED) >= radar.BROADCAST_MIN_REPOS + 2, (
        "the rule needs headroom: with only %d repositories watched, an author "
        "must appear in %d of them for the check to fire at all"
        % (len(radar.MONITORED), radar.BROADCAST_MIN_REPOS))


def test_the_watch_list_has_no_duplicates():
    """A duplicate would spend a request to fetch the same repo twice and make
    the spread count look wider than it is."""
    assert len(radar.MONITORED) == len(set(radar.MONITORED))


def test_the_repositories_we_depend_on_are_still_watched():
    """The two that were there before must survive the widening."""
    assert "google-agentic-commerce/AP2" in radar.MONITORED
    assert "google-agentic-commerce/a2a-x402" in radar.MONITORED
