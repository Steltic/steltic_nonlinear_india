"""Shared bits of the stand-in analyses (tests/test_run_stage2.py)."""
import json, os, sys, time


def opt(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def note(job, line):
    with open(os.path.join(job, "stub_calls.log"), "a") as f:
        f.write(line + "\n")


def pieces(job, ck, names, seconds, kind):
    """Work through `names`, each `seconds` long, keeping a marker per finished piece in `ck` (the journal / record
    cache stand-in); returns how many were computed here."""
    os.makedirs(ck, exist_ok=True)
    n = 0
    for nm in names:
        p = os.path.join(ck, nm + ".done")
        if os.path.exists(p):
            continue
        time.sleep(seconds)
        open(p, "w").write("x")
        n += 1
        note(job, "%s piece %s" % (kind, nm))
    return n


def promoted(job, analysis):
    try:
        d = json.load(open(os.path.join(job, "nl_promote_fibre.json")))
    except Exception:
        return set()
    return set(d.get(analysis) or []) | set(d.get("tags") or [])


def speed():
    return float(os.environ.get("STUB_SECONDS", "0.2"))


def fail_if_asked(kind):
    """STUB_FAIL=<kind>[,<kind>...]: that stand-in exits 1 (a failed analysis)."""
    if kind in (os.environ.get("STUB_FAIL") or "").split(","):
        sys.exit(1)
