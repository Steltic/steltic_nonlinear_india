import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note, opt, pieces, speed

if __name__ == "__main__":
    a = sys.argv[1:]
    assert a[0] == "run"
    job = a[1]
    from _common import fail_if_asked
    fail_if_asked('ddm')
    ck = opt(a, "--checkpoint-dir")
    w = int(opt(a, "--workers", "1"))
    sf = float(opt(a, "--speed-factor", os.environ.get("SNL_SPEED_FACTOR", "1")))
    n = pieces(job, ck, ["s%02d" % i for i in range(6)], speed() / max(1, w) * 2, "ddm")
    note(job, "ddm run workers=%d computed=%d speed_factor=%g" % (w, n, sf))
    json.dump(dict(options=dict(speed_factor=sf, time_limit=2400.0 * sf, time_limit_base=2400.0)), open(os.path.join(job, "ddm_results.json"), "w"))
