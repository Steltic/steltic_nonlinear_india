import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note, opt, pieces, speed

if __name__ == "__main__":
    a = sys.argv[1:]
    job = a[1]
    if a[0] == "criteria":
        note(job, "criteria")
        open(os.path.join(job, "design_criteria_16_1_4.html"), "w").write("<html>criteria</html>")
        sys.exit(0)
    assert a[0] == "run"
    ck = opt(a, "--record-cache")
    par = int(opt(a, "--parallel", "1"))
    n = pieces(job, ck, ["r%02d" % i for i in range(22)], speed() / max(1, par) * 2, "nlrha")
    note(job, "nlrha run parallel=%d computed=%d" % (par, n))
    for lv in ("DBE", "MCE"):
        os.makedirs(os.path.join(job, "nlrha", lv), exist_ok=True)
        json.dump(dict(level=lv, elastic_members=dict(flagged_elastic=[]),
                       response_summary=dict(per_record=[dict(record=1, seconds=2.0, cpu_seconds=1.9)])),
                  open(os.path.join(job, "nlrha", lv, "nlrha_package.json"), "w"))
