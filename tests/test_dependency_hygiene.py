# -*- coding: utf-8 -*-
"""Dependency hygiene: the deploy file, the dev file, and the pipeline.

This file used to be `test_requirements_lock.py` and its subject was
`requirements.lock`. That file is gone (see HANDOVER 90) because it was a
hand-maintained snapshot of the transitive closure that the deploy never
installed, carried no `--hash` lines so it verified nothing, and disagreed with
`requirements.txt` after every dependency bump until somebody updated it by
hand. On 23.11.2026 a Dependabot bump of psycopg failed the pipeline on exactly
that disagreement. A lock that has to be kept in sync by hand is not a lock.

What is left is the half that can be checked without a second copy of the
dependency list:

  * the deploy installs `requirements.txt`, so that is the file that must be
    complete (Dockerfile, DEPLOYMENT.md, DEPLOYMENT_CHECKLIST.md);
  * `pytest` is a DEV dependency, or every production image ships a test runner
    it never runs;
  * `cryptography` is a RUNTIME dependency and must be pinned, because
    `services/connectors.py` signs the CDP JWT with it;
  * the pipeline installs the dev file, or it has no pytest at all;
  * the secret scan states its SCOPE — the working tree, not the history;
  * the runner is pinned and the actions target a supported Node.

Historical note: F-35 in `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` is the
finding that started this file — `cryptography` was missing from the lock and
the lock had no hashes. The lock was removed rather than repaired; F-35 stays as
the record of why.
"""
import io
import re

REQUIREMENTS = "requirements.txt"
DEV_REQUIREMENTS = "requirements-dev.txt"
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


def test_the_deploy_installs_the_file_that_is_complete():
    """Dockerfile installs requirements.txt, so that is the file that must be right.

    The lock used to be the second file this test compared against. It is gone,
    so the assertion that matters now is the first one: the deployed file is the
    one the guards above cover. A reappearing `requirements.lock` in the
    Dockerfile would mean the deployed environment moved to a file nothing
    checks, which is exactly the change a reader should stop and look at.
    """
    dockerfile = io.open(DOCKERFILE, encoding="utf-8", errors="replace").read()

    assert "requirements.txt" in dockerfile, (
        "the Dockerfile no longer installs requirements.txt")
    assert "requirements.lock" not in dockerfile, (
        "the Dockerfile installs requirements.lock, which does not exist; if a "
        "lock is reintroduced it must be generated and hash-pinned first")


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
