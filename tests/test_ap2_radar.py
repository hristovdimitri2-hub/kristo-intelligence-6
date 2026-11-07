"""AP2 radar — the conversation watch, without touching the network.

THE DEFECT THESE TESTS PIN (07.11.2026). The radar read only `/commits` and
`/releases` and reported "ТИХО" for 34 consecutive days. Measured against the
live API, the CODE had genuinely been quiet since June — but the CONVERSATION
had not:

    AP2       pushed_at 2026-06-17   updated_at 2026-11-07   190 open issues/PRs
    a2a-x402  pushed_at 2026-08-04   updated_at 2026-11-07    75 open issues/PRs

Sixteen threads had moved, including "budget limit truncates floats (0.29 → 28
cents)" — our own atomic-units trap — and "one user consent can be redeemed for
multiple payments", the exact replay class fixed the same day. A radar that
measures only commits can report nothing but silence about a protocol whose work
happens in its issue tracker.

Every test here runs against a FAKE response object. No test touches the network,
so the suite stays deterministic and the radar stays read-only.
"""

import json

from scripts import ap2_radar as ar

_ = json


class _Resp:
    """A stand-in for `requests.Response`, with only what the radar uses."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _issue(number, title, *, pr=False, state="open", updated="2026-11-06",
           comments=0, body="", user="someone"):
    """One item shaped like the GitHub issues endpoint returns it."""
    item = {
        "number": number,
        "title": title,
        "state": state,
        "updated_at": updated + "T12:00:00Z",
        "comments": comments,
        "html_url": "https://github.com/o/r/issues/%d" % number,
        "user": {"login": user},
        "body": body,
    }
    if pr:
        # A pull request arrives through this endpoint carrying this key.
        item["pull_request"] = {"url": "https://api.github.com/..."}
    return item


def test_a_pull_request_is_not_reported_as_an_issue(monkeypatch):
    """The distinction matters: PRs are the actionable half of the list."""
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([
        _issue(1, "an issue"),
        _issue(2, "a pull request", pr=True),
    ]))
    items = ar._repo_conversation("o/r", set())
    kinds = {i["number"]: i["kind"] for i in items}
    assert kinds == {1: "issue", 2: "PR"}, kinds


def test_only_recently_updated_threads_are_returned(monkeypatch):
    """`per_page` is the window; whatever the API returns is what is reported."""
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([
        _issue(10, "newest", updated="2026-11-07"),
        _issue(11, "older", updated="2026-11-01"),
    ]))
    items = ar._repo_conversation("o/r", set())
    assert [i["number"] for i in items] == [10, 11]


def test_an_already_seen_number_is_never_reported_again(monkeypatch):
    """THE reason the filter is by NUMBER and not by timestamp.

    A GitHub `updated_at` moves whenever somebody comments. Filtering on it would
    re-report the same thread on every reply, and a radar that repeats itself is
    a radar nobody reads. The number is stable.
    """
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([
        _issue(10, "already seen"),
        _issue(11, "brand new"),
    ]))
    items = ar._repo_conversation("o/r", {"10"})
    assert [i["number"] for i in items] == [11], (
        "a thread already reported was reported again")


def test_a_thread_that_gained_replies_is_still_not_re_reported(monkeypatch):
    """Same as above, stated as the timestamp case: a NEW updated_at on a KNOWN
    number must not resurface it."""
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([
        _issue(10, "seen yesterday", updated="2026-11-07", comments=5),
    ]))
    assert ar._repo_conversation("o/r", {"10"}) == []


def test_keywords_are_matched_in_the_title_and_the_body(monkeypatch):
    """Our own subjects — discovery, manifest, settlement — are what make a
    thread worth reading rather than the fact that it moved."""
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([
        _issue(20, "Settlement binding proposal", body="about the manifest"),
        _issue(21, "unrelated chore", body="nothing here"),
    ]))
    items = {i["number"]: i for i in ar._repo_conversation("o/r", set())}
    assert "manifest" in items[20]["keywords"], items[20]["keywords"]
    assert items[21]["keywords"] == []


def test_an_api_error_is_reported_rather_than_shown_as_silence(monkeypatch):
    """`couldn't look` must never be presented as `found nothing` — the rule this
    whole codebase keeps. An HTTP failure is labelled, not swallowed."""
    monkeypatch.setattr(ar, "_get", lambda url: _Resp({}, status=403))
    items = ar._repo_conversation("o/r", set())
    assert items and "error" in items[0], (
        "a failed read was reported as an empty conversation")
    assert "403" in items[0]["error"]


def test_a_rate_limited_api_is_reported_as_an_error_not_as_silence(monkeypatch):
    """429 is the most likely failure in practice: the radar is unauthenticated
    and GitHub allows 60 requests an hour.

    It must NOT be swallowed into an empty list. An empty list means "the API
    answered and nothing moved", which is a measurement; a rate limit means we
    could not look. Reporting the second as the first is the defect class this
    codebase keeps closing — and here it would read as a quiet month on the very
    day the radar was blind.
    """
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([], status=429))
    items = ar._repo_conversation("o/r", set())
    assert items and "error" in items[0]
    assert "429" in items[0]["error"]


def test_a_malformed_response_is_reported_not_crashed(monkeypatch):
    """A 200 whose body is not a list of issues — a changed API shape.

    It must not raise inside the loop that builds the report, and it must not
    return an empty list either: `[]` claims the API answered and nothing moved.
    We did not understand the answer, so that is what gets said.
    """
    monkeypatch.setattr(ar, "_get", lambda url: _Resp({"message": "moved"}))
    items = ar._repo_conversation("o/r", set())
    assert items and "error" in items[0], (
        "a payload we could not read was reported as an empty conversation")
    assert "moved" in items[0]["error"] or "unexpected" in items[0]["error"]


def test_the_report_names_the_conversation_section(monkeypatch, tmp_path):
    """The section must exist in the OUTPUT. A watch whose findings never reach
    the report is the defect being fixed, not a detail of it."""
    monkeypatch.setattr(ar, "REPORT_PATH", tmp_path / "radar.md")
    monkeypatch.setattr(ar, "STATE_PATH", tmp_path / "radar.json")
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([]))
    monkeypatch.setattr(ar, "_repo_commits", lambda full, since: [])
    monkeypatch.setattr(ar, "_releases", lambda full, seen: [])
    monkeypatch.setattr(ar, "_search_new_wg_repos", lambda known: [])
    monkeypatch.setattr(ar, "_census_scan", lambda full, paths: [])
    monkeypatch.setattr(ar, "_repo_conversation",
                        lambda full, seen, per_page=8: [
                            {"number": 393, "kind": "issue", "state": "open",
                             "title": "what resolves a Mispick dispute?",
                             "url": "https://example/393", "updated": "2026-11-06",
                             "comments": 2, "user": "x", "keywords": ["buyer"]}])

    assert ar.main() == 0
    text = (tmp_path / "radar.md").read_text(encoding="utf-8")
    assert "## Разговорът" in text, "the conversation section is missing"
    assert "#393" in text, "a watched thread did not reach the report"
    assert "issues/PRs" in text or "issues и PR-и" in text


def test_the_report_says_so_when_nothing_moved(monkeypatch, tmp_path):
    """The other direction: an empty conversation must read as a measurement,
    not as a missing section."""
    monkeypatch.setattr(ar, "REPORT_PATH", tmp_path / "radar.md")
    monkeypatch.setattr(ar, "STATE_PATH", tmp_path / "radar.json")
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([]))
    monkeypatch.setattr(ar, "_repo_commits", lambda full, since: [])
    monkeypatch.setattr(ar, "_releases", lambda full, seen: [])
    monkeypatch.setattr(ar, "_search_new_wg_repos", lambda known: [])
    monkeypatch.setattr(ar, "_census_scan", lambda full, paths: [])
    monkeypatch.setattr(ar, "_repo_conversation", lambda full, seen, per_page=8: [])

    assert ar.main() == 0
    text = (tmp_path / "radar.md").read_text(encoding="utf-8")
    assert "## Разговорът" in text
    assert "Нищо ново обновено от миналия път." in text


def test_seen_numbers_survive_into_the_state_file(monkeypatch, tmp_path):
    """The watermark is what makes the second run quiet. If it is not persisted,
    every run re-reports the same sixteen threads and the radar becomes noise."""
    state_path = tmp_path / "radar.json"
    monkeypatch.setattr(ar, "REPORT_PATH", tmp_path / "radar.md")
    monkeypatch.setattr(ar, "STATE_PATH", state_path)
    monkeypatch.setattr(ar, "_get", lambda url: _Resp([]))
    monkeypatch.setattr(ar, "_repo_commits", lambda full, since: [])
    monkeypatch.setattr(ar, "_releases", lambda full, seen: [])
    monkeypatch.setattr(ar, "_search_new_wg_repos", lambda known: [])
    monkeypatch.setattr(ar, "_census_scan", lambda full, paths: [])
    monkeypatch.setattr(ar, "_repo_conversation",
                        lambda full, seen, per_page=8: [
                            {"number": 42, "kind": "issue", "state": "open",
                             "title": "t", "url": "u", "updated": "2026-11-06",
                             "comments": 0, "user": "x", "keywords": []}])

    ar.main()
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert "42" in saved.get("seen_conversation", []), (
        "the seen set was not persisted, so every run would repeat itself")
