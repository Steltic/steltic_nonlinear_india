#!/usr/bin/env python3
"""WP1.14 CI check: the vendored shared India modules must be byte-identical to steltic_india/steel_engine.

    python scripts/check_vendored.py [--hr /path/to/steltic_india]   # sha256 compare; exit 1 on any drift
    python scripts/check_vendored.py --sync                          # print the cp commands (never copies)

The HR source root is (in order) --hr, $STELTIC_HR_ROOT, $STELTIC_INDIA_HR (legacy name), a sibling checkout
../steltic_india or ../steltic_india-main next to this repo, or the parent of $STELTIC_ENGINE_DIR when that points
at a steltic_india steel_engine.  When none exists the script prints SKIP and exits 0 (nothing to compare against)
-- the same pattern as steltic_CFS_india (C13 / L-08).  The commit the files were copied from is recorded in
snl/vendor_steltic_india/VENDORED_FROM.md.
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NL_ROOT = os.path.dirname(HERE)
NL_VENDOR = os.path.join(NL_ROOT, "snl", "vendor_steltic_india")
FILES = ("india_loads.py", "india_seismic.py", "india_units.py", "india_wind_tables.py", "india_combos.py",
         "india_is18168.py", "india_seismic_gates.py", "india_omega_is18168.py", "preflight.py")


def _is_hr(root):
    return bool(root) and os.path.isfile(os.path.join(root, "steel_engine", "india_seismic.py"))


def resolve_hr_root(explicit=None):
    """--hr, $STELTIC_HR_ROOT, $STELTIC_INDIA_HR, sibling ../steltic_india(-main), parent of $STELTIC_ENGINE_DIR; else None."""
    for cand in (explicit, os.environ.get("STELTIC_HR_ROOT"), os.environ.get("STELTIC_INDIA_HR")):
        if cand:
            return cand                       # named explicitly: use it even when wrong, so the error is visible
    for name in ("steltic_india", "steltic_india-main"):
        cand = os.path.join(os.path.dirname(NL_ROOT), name)
        if _is_hr(cand):
            return cand
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if eng and _is_hr(os.path.dirname(os.path.abspath(eng))):
        return os.path.dirname(os.path.abspath(eng))
    return None


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr", default=None, help="steltic_india checkout (default: $STELTIC_HR_ROOT, sibling checkout)")
    ap.add_argument("--sync", action="store_true", help="print the cp commands that would re-sync")
    a = ap.parse_args(argv)
    hr = resolve_hr_root(a.hr)
    if not hr:
        print("SKIP: no steltic_india checkout to compare against (set STELTIC_HR_ROOT, or place steltic_india next to this repo)")
        return 0
    src = os.path.join(hr, "steel_engine")
    bad = 0
    for f in FILES:
        p_hr, p_nl = os.path.join(src, f), os.path.join(NL_VENDOR, f)
        if not os.path.exists(p_hr):
            print("MISSING in HR:", f); bad += 1; continue
        if not os.path.exists(p_nl):
            print("MISSING in NL vendor:", f); bad += 1; continue
        h1, h2 = sha(p_hr), sha(p_nl)
        if a.sync:
            if h1 != h2:
                print("cp %s %s" % (p_hr, p_nl))
            continue
        print("%s %s %s" % ("OK  " if h1 == h2 else "DRIFT", f, h2[:12]))
        bad += (h1 != h2)
    if a.sync:
        return 0
    if bad:
        print("check_vendored: %d file(s) drift from steltic_india -- re-vendor (cp) from %s" % (bad, src))
        return 1
    print("check_vendored: all %d shared modules byte-identical to steltic_india (%s)" % (len(FILES), hr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
