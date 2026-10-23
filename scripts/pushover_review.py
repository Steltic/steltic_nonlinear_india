#!/usr/bin/env python3
"""pushover_review.py -- put pushover directions of a stored run "under review" (2026-10 check fixes, finding 4).

    python scripts/pushover_review.py <job> --direction Y [--l-over-e 9.44] [--nlrha] [--dry-run]
    python scripts/pushover_review.py <job> --clear

Reads only the stored packages (pushover/pushover_package.json, and with --nlrha the NLRHA level packages), writes
<job>/pushover/pushover_review.json (pushover/review.py has the format and the evidence) and prints the text. Then run
`python -m snl report <job>` so the four-analyses sheet and the pushover report say it; the site index builder reads
the record directly. --l-over-e is the bay length over the link length of a chevron EBF, read from the job's design
input (for the kinematic link rotation); leave it out for other systems. --clear removes the record.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from pushover import review as RV  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job")
    ap.add_argument("--direction", action="append", default=[], help="X or Y (repeat for both)")
    ap.add_argument("--l-over-e", type=float, default=None, help="EBF bay length / link length (chevron, mid-span link)")
    ap.add_argument("--nlrha", action="store_true", help="add the NLRHA link-rotation sentence")
    ap.add_argument("--date", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args(argv)
    if a.clear:
        p = RV.record_path(a.job)
        if os.path.exists(p):
            os.remove(p)
            print("removed", p)
        return 0
    if not a.direction:
        ap.error("--direction is required")
    rec = RV.make_record(a.job, a.direction, l_over_e=a.l_over_e, with_nlrha=a.nlrha, date=a.date)
    for d, e in rec["directions"].items():
        print("== %s\n%s" % (d, RV.note_text_of(e)))
    if a.dry_run:
        print(json.dumps(rec, indent=1, default=str)[:4000])
        return 0
    print("wrote", RV.write_record(a.job, rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
