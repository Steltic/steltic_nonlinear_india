import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note, opt, pieces, promoted, speed

if __name__ == "__main__":
    a = sys.argv[1:]
    assert a[0] == "run"
    job = a[1]
    dirs = a[a.index("--dirs") + 1:]
    dirs = [x for x in dirs[:2] if x in ("X", "Y")]
    ck = opt(a, "--checkpoint-dir")
    flag = [] if 5 in promoted(job, "pushover") else [5]          # member 5 yields until it is fibre
    tag = "p" if flag else "f"                                   # a promotion changes the model: a new journal
    n = pieces(job, ck, ["%s_%s" % (tag, d) for d in dirs], 3 * speed(), "pushover")
    note(job, "pushover run dirs=%s computed=%d" % ("".join(dirs), n))
    os.makedirs(os.path.join(job, "pushover"), exist_ok=True)
    json.dump(dict(directions=dirs, elastic_members=dict(flagged_elastic=flag)),
              open(os.path.join(job, "pushover", "pushover_package.json"), "w"))
