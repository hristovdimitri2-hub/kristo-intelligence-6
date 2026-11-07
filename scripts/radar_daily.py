"""Run the AP2 radar and deliver the digest — one command, for a scheduler.

    python scripts/radar_daily.py            # scan + DRY-RUN (nothing sent)
    python scripts/radar_daily.py --send     # scan + really send the email

WHY THIS EXISTS. Both halves already worked and neither ran. Measured on
07.11.2026: `docs/AP2_RADAR.md` was 34 days stale and `RADAR-DIGEST.md` was 25
days stale, because NOTHING invoked either script — there was no scheduled task.
A monitor nobody starts is not a monitor.

It chains the two existing pieces rather than reimplementing them:

  1. `scripts/ap2_radar.py`      — scans public GitHub, rewrites docs/AP2_RADAR.md
  2. `scripts/send_radar_digest.py` — converts a Markdown digest to email

STEP 2 IS FED THE FRESH SCAN, not the workspace file. The digest the owner was
receiving came from a hand-maintained Cline workspace file, which is why it could
sit for 25 days: producing it needed a person. The radar's own output is
generated, so it cannot go stale that way. `--digest` overrides the path if the
workspace digest is wanted instead.

The send stays behind the DOUBLE DOOR inherited from send_radar_digest: without
`--send` nothing touches the network beyond the read-only GitHub scan.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RADAR = ROOT / "scripts" / "ap2_radar.py"
SENDER = ROOT / "scripts" / "send_radar_digest.py"


def _run(script: Path, args: list[str]) -> int:
    """Run one step, streaming its output so a scheduler log shows both."""
    print(f"--- {script.name} {' '.join(args)}".rstrip(), flush=True)
    proc = subprocess.run([sys.executable, str(script), *args], cwd=str(ROOT))
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan with the AP2 radar, then deliver the digest."
    )
    parser.add_argument("--send", action="store_true",
                        help="really send the email (double door)")
    parser.add_argument("--digest", default="",
                        help="Markdown to send; default is the radar's own output")
    args = parser.parse_args(argv)

    # Step 1 — the scan. Its exit code is reported, not fatal: the digest is still
    # worth sending if the scan degraded, and it says so in its own text.
    scan_rc = _run(RADAR, [])

    # Step 2 — delivery, fed the file the scan just wrote.
    digest = args.digest or str(ROOT / "docs" / "AP2_RADAR.md")
    send_args = ["--digest", digest] + (["--send"] if args.send else [])
    send_rc = _run(SENDER, send_args)

    if scan_rc != 0:
        print(f"NOTE: the scan exited {scan_rc}; the digest was still prepared.",
              file=sys.stderr)
    return send_rc


if __name__ == "__main__":
    raise SystemExit(main())
