"""NL-27: the gold batch re-runs a DDM that predates DDM_CODE (NL-24..26 change every DDM result) -- inline for an
unfinished job, in a refresh pass at the end for a finished one -- never repeats pushover / NLRHA, and stops cleanly on
$GOLD_NL/STOP_BATCH. Driven with a stub interpreter (no analysis runs)."""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "run_gold_batch.sh")
STUB = r'''#!/bin/bash
if [ "$1" = "-m" ]; then
  echo "$*" >> "$STUB_CALLS"
  if [ "$2" = "snl" ] && [ "$3" = "report" ]; then echo '{"status": "complete", "reasons": []}' > "$4/complete_gate.json"; fi
  exit 0
fi
exec python3 "$@"
'''


def _job(root, name, markers, done=False, ddm_code=None):
    j = root / name
    j.mkdir(parents=True)
    (j / "cfg.py").write_text("")
    (j / "hinge_params_collected.json").write_text("{}")
    for m in markers:
        d = {"seconds": 1}
        if m == "ddm" and ddm_code:
            d["ddm_code"] = ddm_code
        (j / (".batch_step_" + m)).write_text(json.dumps(d))
    if done:
        (j / "batch_done.json").write_text(json.dumps({"status": "partial", "seconds": 5}))
        (j / "ddm_results.json").write_text("{}")
    return j


def _run(tmp_path, jobs):
    stub = tmp_path / "py"; stub.write_text(STUB); stub.chmod(0o755)
    calls = tmp_path / "calls.txt"
    env = dict(os.environ, GOLD_NL=str(tmp_path / "gold"), PY=str(stub), STUB_CALLS=str(calls), ONLY_JOBS=" ".join(jobs),
               LOG=str(tmp_path / "progress.log"))
    r = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return (calls.read_text().splitlines() if calls.exists() else []), (tmp_path / "progress.log").read_text()


def test_stale_ddm_is_rerun_and_nothing_else(tmp_path):
    code = re.search(r'DDM_CODE="([^"]+)"', open(SCRIPT).read()).group(1)
    g = tmp_path / "gold"
    old = _job(g, "A_done_old", ["pushover", "nlrha", "ddm"], done=True)                   # finished at df041ec
    _job(g, "B_done_new", ["pushover", "nlrha", "ddm"], done=True, ddm_code=code)           # already current
    _job(g, "C_open_old", ["pushover", "nlrha", "ddm"])                                      # killed before batch_done
    _job(g, "D_no_ddm", ["pushover", "nlrha"])                                               # e.g. killed in its DDM
    calls, log = _run(tmp_path, ["A_done_old", "B_done_new", "C_open_old", "D_no_ddm"])
    runs = [c for c in calls if " run " in c]
    assert all("--only ddm" in c for c in runs)                                              # no pushover / NLRHA
    assert sorted(c.split()[3].split("/")[-1] for c in runs) == ["A_done_old", "C_open_old", "D_no_ddm"]
    assert runs[-1].split()[3].endswith("A_done_old")                                        # refresh pass last
    assert code in (old / ".batch_step_ddm").read_text()
    assert json.load(open(old / "batch_done.json"))["status"] == "complete"
    assert (old / ("_ddm_before_" + code) / "ddm_results.json").exists()
    assert "DDM refresh queued at the end" in log


def test_stop_file_stops_before_the_next_step(tmp_path):
    g = tmp_path / "gold"
    _job(g, "A", ["pushover", "nlrha"])
    g.joinpath("STOP_BATCH").write_text("")
    calls, log = _run(tmp_path, ["A"])
    assert not [c for c in calls if " run " in c] and "stopped cleanly" in log


def test_skip_jobs_file_is_never_started(tmp_path):
    """NL-28: jobs listed in $GOLD_NL/SKIP_JOBS (offloaded to the owner's PC) are neither run nor DDM-refreshed."""
    g = tmp_path / "gold"
    _job(g, "P_pc", ["pushover"])                                    # unfinished -> would run nlrha + ddm
    _job(g, "Q_pc_done", ["pushover", "nlrha", "ddm"], done=True)    # stale DDM -> would be refreshed
    _job(g, "R_here", ["pushover", "nlrha"])
    g.joinpath("SKIP_JOBS").write_text("# offloaded\nP_pc\n  Q_pc_done   # also\n")
    calls, log = _run(tmp_path, ["P_pc", "Q_pc_done", "R_here"])
    runs = [c for c in calls if " run " in c]
    assert runs and all(c.split()[3].endswith("R_here") for c in runs)
    assert log.count("listed in") == 2
