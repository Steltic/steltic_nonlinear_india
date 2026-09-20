#!/usr/bin/env python3
"""WP1.14 CI check: the vendored shared India modules must be byte-identical to steltic_india (work/hr).

    python scripts/check_vendored.py [--hr /path/to/steltic_india]

Exit 1 on any drift (sha256 mismatch or missing file)."""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NL_VENDOR = os.path.join(os.path.dirname(HERE), "snl", "vendor_steltic_india")
DEFAULT_HR = os.environ.get("STELTIC_INDIA_HR", "/home/claude/rv/work/hr")
FILES = ("india_loads.py", "india_seismic.py", "india_units.py", "india_wind_tables.py", "india_combos.py",
         "india_is18168.py", "india_seismic_gates.py", "india_omega_is18168.py", "preflight.py")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr", default=DEFAULT_HR)
    a = ap.parse_args()
    src = os.path.join(a.hr, "steel_engine")
    bad = 0
    for f in FILES:
        p_hr, p_nl = os.path.join(src, f), os.path.join(NL_VENDOR, f)
        if not os.path.exists(p_hr):
            print("MISSING in HR:", f); bad += 1; continue
        if not os.path.exists(p_nl):
            print("MISSING in NL vendor:", f); bad += 1; continue
        h1, h2 = sha(p_hr), sha(p_nl)
        print("%s %s %s" % ("OK  " if h1 == h2 else "DRIFT", f, h2[:12]))
        bad += (h1 != h2)
    if bad:
        print("check_vendored: %d file(s) drift from steltic_india -- re-vendor (cp) from %s" % (bad, src))
        return 1
    print("check_vendored: all %d shared modules byte-identical to steltic_india" % len(FILES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
