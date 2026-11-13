# -*- coding: utf-8 -*-
"""The two dependency files must describe the same environment.

F-35 in docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md. requirements.txt said "for full
reproducible builds, install from requirements.lock instead" - and requirements.lock
was missing `cryptography`, which requirements.txt declares directly. Installing only
the lock therefore produced a different environment from the one the suite passes in,
which is the one property a lock file exists to provide.

On top of that the lock has no --hash lines, so it was never the hash-pinned
reproducible build it was described as, and the deploy does not install it at all:
Dockerfile:25, DEPLOYMENT.md and DEPLOYMENT_CHECKLIST.md all install requirements.txt.

These tests hold the structural half - every direct dependency present, every exact
pin agreeing - because that is the half that silently rots.
"""
import io
import re

REQUIREMENTS = "requirements.txt"
DEV_REQUIREMENTS = "requirements-dev.txt"
LOCK = "requirements.lock"
DOCKERFILE = "Dockerfile"
CI_WORKFLOW = ".github/workflows/ci.yml"
GITLEAKS_CONFIG = ".gitleaks.toml"

#: name, optional extras, optional operator, version
_ENTRY = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(==|>=|~=|<=|>|<)?\s*([^\s;#]*)?")


def _parse(path):
    """Yield {normalised name: operator+version} for every requirement line."""
    found = {}
    for raw in io.open(path, encoding="utf-8", errors="replace").read().splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _ENTRY.match(line)
        if not match:
            continue
        found[match.group(1).lower().replace("_", "-")] = (
            (match.group(2) or "") + (match.group(3) or ""))
    return found


def _has_real_hashes(text):
    """True only for actual --hash pins, not the word appearing in prose.

    This distinction is the whole reason the first version of this guard was
    worthless: the lock's own explanation says "there are no --hash lines", so a
    plain `"--hash" in text` was true, the conditional was skipped, and the
    assertion it protected never ran once. It passed because it did nothing.
    """
    for line in text.splitlines():
        stripped = line.split("#")[0]
        if "--hash=" in stripped or "--hash " in stripped:
            return True
    return False


def test_every_direct_dependency_is_in_the_lock():
    """The defect itself: `cryptography` was absent from the lock."""
    direct = _parse(REQUIREMENTS)
    locked = _parse(LOCK)

    assert direct, "requirements.txt lists no dependencies - has it moved?"

    missing = sorted(set(direct) - set(locked))
    assert not missing, (
        "installing %s alone would not install %s, which %s declares directly; the "
        "lock is supposed to be the same environment"
        % (LOCK, ", ".join("%s (%s)" % (n, direct[n]) for n in missing),
           REQUIREMENTS))


def test_every_exact_pin_agrees_between_the_two_files():
    """A direct pin the lock disagrees with is a different environment, silently."""
    direct = _parse(REQUIREMENTS)
    locked = _parse(LOCK)

    disagreements = []
    for name, want in sorted(direct.items()):
        have = locked.get(name)
        if have and want.startswith("==") and have.startswith("==") and want != have:
            disagreements.append("%s: %s says %s, %s says %s"
                                 % (name, REQUIREMENTS, want, LOCK, have))

    assert not disagreements, (
        "the two files pin the same package differently:\n  "
        + "\n  ".join(disagreements))


def test_the_lock_does_not_claim_to_be_something_it_is_not():
    """The hashes and the sentence about hashes must agree.

    Written as an agreement rather than as "if there are no hashes, require the
    sentence", because the conditional version could be silenced by adding a single
    bogus --hash line: the guard would stop demanding the sentence without the file
    having become any more verifiable. Now the file must either carry real hash pins
    and say so, or carry none and say that too - and a half-measure fails both ways.
    """
    lock = io.open(LOCK, encoding="utf-8", errors="replace").read()
    hashed = _has_real_hashes(lock)
    admits_no_hashes = "not a hash-pinned reproducible build" in lock

    if hashed:
        assert not admits_no_hashes, (
            "the lock now carries --hash pins, so the sentence saying it is not "
            "hash-pinned is false and must be replaced")
    else:
        assert admits_no_hashes, (
            "the lock carries no --hash pins, so it must say so; nothing else in "
            "the file records that it constrains versions without verifying "
            "downloads")

    assert "the deploy does NOT install it" in lock or "deploy does not" in lock, (
        "the lock must say that the deploy installs requirements.txt, because that "
        "is the question a reader of a lock file is asking")


def test_requirements_txt_no_longer_promises_reproducibility_it_cannot_give():
    """The sentence that was wrong: "for full reproducible builds, install ..."."""
    direct = io.open(REQUIREMENTS, encoding="utf-8", errors="replace").read()
    lock = io.open(LOCK, encoding="utf-8", errors="replace").read()

    assert "For full reproducible builds" not in direct, (
        "requirements.txt still promises a full reproducible build from the lock, "
        "which has no hashes and was missing a direct dependency")
    assert "requirements.lock" in direct, (
        "requirements.txt should still tell a reader the lock exists")
    if not _has_real_hashes(lock):
        assert "point-in-time snapshot" in direct or "point-in-time" in lock, (
            "the lock is a snapshot without hashes and must be described as one")


def test_the_deploy_installs_the_file_that_is_complete():
    """Dockerfile installs requirements.txt, so that is the file that must be right.

    If this ever flips to the lock, the completeness tests above stop covering the
    deployed environment - which is exactly the kind of change that should make a
    reader stop and look.
    """
    dockerfile = io.open(DOCKERFILE, encoding="utf-8", errors="replace").read()

    assert "requirements.txt" in dockerfile, (
        "the Dockerfile no longer installs requirements.txt; the lock is declared "
        "complete by the tests above, but nothing has checked that it is")
    assert "requirements.lock" not in dockerfile, (
        "the Dockerfile now installs the lock; make sure it is genuinely complete "
        "and hash-pinned before relying on it for deploys")


def test_the_deploy_does_not_install_a_test_runner():
    """pytest used to be a PRODUCTION dependency.

    requirements.txt is what the deploy installs, and it carried pytest, so
    every production image shipped a test runner it never ran. Test-only
    dependencies belong in requirements-dev.txt.
    """
    direct = _parse(REQUIREMENTS)

    assert "pytest" not in direct, (
        "requirements.txt (installed by the deploy) declares pytest again; "
        "test-only dependencies belong in %s" % DEV_REQUIREMENTS)

    dev = io.open(DEV_REQUIREMENTS, encoding="utf-8", errors="replace").read()
    assert "-r requirements.txt" in dev, (
        "%s must build ON requirements.txt, or a dev install misses the runtime "
        "dependencies" % DEV_REQUIREMENTS)
    assert "pytest" in _parse(DEV_REQUIREMENTS), (
        "pytest moved out of the deploy file but not into %s" % DEV_REQUIREMENTS)


def test_the_dev_dependencies_are_in_the_lock_too():
    """The lock must describe the environment the suite passes in."""
    dev = _parse(DEV_REQUIREMENTS)
    locked = _parse(LOCK)

    missing = sorted(set(dev) - set(locked))
    assert not missing, (
        "%s declares %s, which %s does not list; the lock is supposed to be the "
        "same environment"
        % (DEV_REQUIREMENTS, ", ".join(missing), LOCK))


def test_the_crypto_dependency_is_pinned_and_is_not_called_test_only():
    """`cryptography` signs the CDP JWT at RUNTIME.

    It was declared as an unpinned `cryptography>=42.0.0` under a "Testing"
    heading — wrong twice: the deploy installed whatever pip resolved that day,
    and the heading told a reader it was a dev dependency.
    """
    direct = _parse(REQUIREMENTS)

    assert "cryptography" in direct, (
        "cryptography is imported by services/connectors.py at runtime")
    assert direct["cryptography"].startswith("=="), (
        "cryptography is unpinned (%s), so the deploy resolves it fresh each "
        "build" % direct["cryptography"])
    assert direct["cryptography"] == _parse(LOCK)["cryptography"], (
        "requirements.txt and the lock disagree about cryptography")

    text = io.open(REQUIREMENTS, encoding="utf-8", errors="replace").read()
    testing_at = text.find("# ── Testing")
    crypto_at = text.find("cryptography==")
    assert crypto_at != -1 and testing_at != -1
    assert crypto_at < testing_at, (
        "cryptography is listed under the Testing heading again, which reads as "
        "a dev-only dependency")


def test_the_pipeline_installs_the_dev_file_and_says_what_it_scans():
    """The deploy file no longer carries pytest, so the pipeline must not use it.

    A CI that installed requirements.txt alone would die at
    `pytest: command not found` — exactly the drift this guard is for. And the
    secret scan must state its SCOPE: the history is known to contain older
    material, and rewriting it is a destructive decision the owner has not
    taken, so the job scans the working tree and says so.
    """
    text = io.open(CI_WORKFLOW, encoding="utf-8", errors="replace").read()

    assert "requirements-dev.txt" in text, (
        "%s must install the dev file, or it has no pytest" % CI_WORKFLOW)
    assert "pytest" in text, "%s never runs the suite" % CI_WORKFLOW
    assert "--no-git" in text, (
        "the secret scan must name its scope; scanning the history would fail on "
        "material that only an owner-approved rewrite can remove")


def test_the_secret_scan_config_explains_every_exemption():
    """The config allowlists VALUES, never whole rules or whole directories.

    The first scan flagged 19 strings and all 19 were public by design — the
    USDC contract address, two keccak event topics, two domain-control tokens
    that the verifier fetches from /.well-known/, and one signed public
    attestation. Each is allowlisted with a written reason.

    What this file must never become is a blanket exemption. `useDefault = true`
    keeps every built-in rule armed, no rule is redefined (a `[[rules]]` block
    can silently drop one), and every allowlist carries a description so a
    reader can judge the decision instead of trusting it.
    """
    import tomllib

    with open(GITLEAKS_CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)

    assert cfg.get("extend", {}).get("useDefault") is True, (
        "the config must EXTEND gitleaks' default rules, not replace them")
    assert "rules" not in cfg, (
        "the config defines its own rules, which can silently drop the built-in "
        "ones; allowlists are the narrow tool")

    blocks = cfg.get("allowlists") or []
    assert blocks, (
        "no allowlists at all — the scan would fail on the known-public values")
    for block in blocks:
        assert block.get("description"), (
            "every allowlist must state WHY those values are not secrets")
        assert block.get("regexes") or block.get("paths"), (
            "an allowlist with neither regexes nor paths exempts everything")


def test_the_pipeline_does_not_run_on_a_moving_runner_or_a_dead_node():
    """`ubuntu-latest` and Node-20 actions are changes nobody commits.

    GitHub announced that `ubuntu-latest` migrates to Ubuntu 26 in October 2026,
    and that actions targeting Node.js 20 are deprecated. Both mean the build
    would change under a green pipeline without a commit — so the runner is
    pinned and the actions target Node 24.
    """
    text = io.open(CI_WORKFLOW, encoding="utf-8", errors="replace").read()
    # Comments are not configuration. The note explaining WHY the runner is
    # pinned names `ubuntu-latest`, and a guard that forbade the word would
    # forbid the explanation.
    code = "\n".join(
        line.split(" #")[0] for line in text.splitlines()
        if not line.lstrip().startswith("#"))

    assert "ubuntu-latest" not in code, (
        "ubuntu-latest migrates to Ubuntu 26; pin the runner so the change is a "
        "commit somebody makes")
    for dead in ("actions/checkout@v4", "actions/checkout@v5",
                 "actions/setup-python@v5", "actions/setup-python@v6"):
        assert dead not in code, "%s targets the deprecated Node.js 20" % dead
    assert "actions/checkout@v7" in code, "checkout must target Node 24"
    assert "actions/setup-python@v7" in code, "setup-python must target Node 24"




