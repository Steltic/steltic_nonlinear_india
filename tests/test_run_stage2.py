"""Stage 2 on the owner's PC: scripts/run_stage2.py. The scheduler, the plan, and the runner end to end with the
stand-in analyses of tests/stage2_stubs (no OpenSees): the gold sync, the queue, the parallel steps, the NL-21
promotion, a kill in the middle (the PC restarting) and the resume, the skips, the results zip and its manifest."""
import json
import os
import signal
import subprocess
import sys
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
STUBS = os.path.join(ROOT, "tests", "stage2_stubs")
RUNNER = os.path.join(ROOT, "scripts", "run_stage2.py")


def _gold(root, names=("IN_ExT", "IN_ExU"), unit=True, params=("IN_ExT", "IN_ExT/units/u1")):
    for n in list(names) + (["IN_ExT/units/u1"] if unit else []):
        j = os.path.join(str(root), *n.split("/"))
        os.makedirs(os.path.join(j, "design"), exist_ok=True)
        open(os.path.join(j, "cfg.py"), "w").write("cfg = {'name': %r}\n" % n)
        open(os.path.join(j, "model_opensees.py"), "w").write("".join("ops.element('x', %d)\n" % i for i in range(40)))
        open(os.path.join(j, "load_plan.json"), "w").write('{"cases": []}')
        json.dump({"members": [1]}, open(os.path.join(j, "design", "calc_package.json"), "w"))
        if n in params:
            open(os.path.join(j, "hinge_params_collected.json"), "w").write('{"jurisdiction": "india"}')
    return str(root)


def _engine(root):
    e = os.path.join(str(root), "steel_engine")
    os.makedirs(e, exist_ok=True)
    for n in ("static_model.py", "engine3d.py", "india_loads.py", "india_combos.py", "roof_geometry.py"):
        open(os.path.join(e, n), "w").write("# %s\n" % n)
    return e


def _env(seconds="0.2"):
    env = dict(os.environ, STAGE2_PYTHONPATH=STUBS, STUB_SECONDS=seconds, PYTHONHASHSEED="0")
    for k in [k for k in env if k.startswith("SNL_")]:
        env.pop(k)
    return env


def _cmd(gold, work, res, eng, workers=3, extra=()):
    return [sys.executable, RUNNER, "run", "--gold", gold, "--work", work, "--results", res, "--workers", str(workers),
            "--memory-gb", "64", "--engine", eng, "--poll", "0.1"] + list(extra)


def _calls(work, job):
    p = os.path.join(work, "jobs", *job.split("/"), "stub_calls.log")
    return open(p).read().splitlines() if os.path.exists(p) else []


# ------------------------------------------------------------------------------------------------ scheduling
def _queue(NS, ests):
    """A queue of jobs with the given estimates (pushover_s, nlrha_total_s, ddm_work_s)."""
    d = dict(steps=[], env={})
    for jid, (p, n, dd) in ests.items():
        for s in NS.job_steps("/x/" + jid, jid, "py"):
            s["estimate"] = dict(elements=100, pushover_s=p, nlrha_total_s=n, nlrha_longest_s=n / 22.0, ddm_work_s=dd,
                                 ddm_longest_s=dd / 25.0, ddm_sweeps=25)
            d["steps"].append(s)
    return d


def test_the_scheduler_orders_widths_and_memory():
    import run_stage2 as NS
    d = _queue(NS, {"BIG": (3000, 40000, 50000), "SMALL": (10, 500, 300)})
    sch = NS.Scheduler(d, 12, 64)
    first = [(s["id"], w) for s, w, m in sch.picks()]
    assert first == [("BIG/gravity", 1), ("SMALL/gravity", 1)]               # the longest job first; gravity first
    for s in d["steps"]:
        if s["kind"] == "gravity":
            s["state"] = "done"
    picks = [(s["id"], w) for s, w, m in NS.Scheduler(d, 12, 64).picks()]
    # BIG: pushover (1) and DDM (11 of 12 left); the NLRHA waits for its pushover; SMALL waits for workers
    assert picks[0] == ("BIG/pushover", 1) and picks[1] == ("BIG/ddm", 11) and len(picks) == 2
    # a tight memory budget holds the wide DDM back while the pushover runs
    picks = [(s["id"], w) for s, w, m in NS.Scheduler(d, 12, 4.0).picks()]
    assert picks[0] == ("BIG/pushover", 1) and ("BIG/ddm", 11) not in picks
    # the NLRHA starts after its pushover ended, even when the pushover FAILED (as `snl run`); the report last
    nxt = next(s for s in d["steps"] if s["id"] == "BIG/pushover")
    nxt["state"] = "failed"
    ids = [s["id"] for s, w, m in NS.Scheduler(d, 12, 64).picks()]
    assert "BIG/nlrha" in ids and "BIG/report" not in ids
    # a failed gravity record skips the job's analyses
    d2 = _queue(NS, {"G": (10, 10, 10)})
    d2["steps"][0]["state"] = "failed"
    NS.Scheduler(d2, 4, 64).picks()
    assert all(s["state"] == "skipped" for s in d2["steps"][1:])


def test_the_plan_estimate_uses_the_workers():
    import run_stage2 as NS
    d = _queue(NS, {"A": (600, 22000, 25000), "B": (600, 22000, 25000)})
    w12, _ = NS.simulate(d, 12, 64)
    w2, _ = NS.simulate(d, 2, 64)
    serial = sum(NS.step_seconds(s, 1) for s in d["steps"])
    assert w12 < w2 < serial and w12 > (22000 + 25000) * 2 / 12.0
    assert all(s["state"] == "pending" for s in d["steps"])                  # a simulation changes nothing


def test_estimates_and_the_zip_root():
    import run_stage2 as NS
    t = NS.load_estimates()
    assert t["IN_Ex19_EBF_12levels_Tplan_Guwahati"]["nlrha_total_s"] > 0
    e = NS.estimate_for("IN_Ex21_new", 400, t)
    assert "element count" in e["basis"] and e["nlrha_total_s"] > 0
    assert NS._zip_root(["jobs_hr/A", "jobs_hr/A/units/s", "jobs_hr/B"]) == "jobs_hr"
    assert NS._zip_root(["A", "A/units/s"]) == ""
    assert NS._zip_root(["bundle/jobs/A"]) == "bundle/jobs"


def test_plan_lists_the_runs_and_the_skips(tmp_path, capsys):
    import run_stage2 as NS
    gold = _gold(tmp_path / "gold")
    r = NS.main(["plan", "--gold", gold, "--work", str(tmp_path / "w"), "--workers", "12", "--memory-gb", "16", "--verbose"])
    out = capsys.readouterr().out
    assert r["jobs"] == ["IN_ExT", "IN_ExT/units/u1", "IN_ExU"] and r["skipped"] == ["IN_ExU"]
    assert "--speed-factor 1" in out and "--parallel 12" in out and "nlrha criteria" in out
    assert not os.path.exists(tmp_path / "w")                                # a dry run writes nothing
    z = tmp_path / "gold.zip"                                                # the same from a zip, wrapped in a folder
    with zipfile.ZipFile(z, "w") as zf:
        for base, ds, fs in os.walk(gold):
            for f in fs:
                p = os.path.join(base, f)
                zf.write(p, "bundle/" + os.path.relpath(p, gold))
    r2 = NS.main(["plan", "--gold", str(z), "--work", str(tmp_path / "w"), "--workers", "12", "--memory-gb", "16"])
    assert r2["jobs"] == r["jobs"] and r2["skipped"] == ["IN_ExU"]


# ------------------------------------------------------------------------------------------------ end to end
def _kill_all(work, runner):
    """The PC restarting: the runner and every analysis process it started."""
    q = json.load(open(os.path.join(work, "stage2_queue.json")))
    for s in q["steps"]:
        if s.get("pid"):
            try:
                os.killpg(int(s["pid"]), signal.SIGKILL)
            except Exception:
                pass
    runner.kill()
    runner.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="the kill uses POSIX process groups")
def test_run_kill_and_resume_end_to_end(tmp_path):
    gold = _gold(tmp_path / "gold")
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    cmd = _cmd(gold, work, res, eng)
    p = subprocess.Popen(cmd, env=_env("0.4"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ck = os.path.join(work, "jobs", "IN_ExT", "nl_checkpoints", "nlrha")
    t0 = time.time()
    while time.time() - t0 < 120:                     # wait until the NLRHA of IN_ExT has kept a few records
        if os.path.isdir(ck) and len(os.listdir(ck)) >= 4:
            break
        time.sleep(0.05)
    else:
        p.kill(); raise AssertionError(p.stdout.read())
    _kill_all(work, p)
    q = json.load(open(os.path.join(work, "stage2_queue.json")))
    st = {s["id"]: s["state"] for s in q["steps"]}
    assert st["IN_ExT/gravity"] == "done" and st["IN_ExT/nlrha"] == "running"
    kept = len(os.listdir(ck))
    assert 4 <= kept < 22
    assert not os.listdir(res) if os.path.isdir(res) else True              # no results zip yet
    # the same command again: it continues
    r = subprocess.run(cmd, env=_env("0.05"), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    q = json.load(open(os.path.join(work, "stage2_queue.json")))
    st = {s["id"]: s for s in q["steps"]}
    assert all(s["state"] == "done" for k, s in st.items() if not k.startswith("IN_ExU/"))
    assert all(s["state"] == "skipped" and "hinge_params_collected" in s["skip_reason"]
               for k, s in st.items() if k.startswith("IN_ExU/") and s["kind"] != "report")
    calls = _calls(work, "IN_ExT")
    assert calls.count("gravity") == 1                                      # a finished step is not run again
    assert sum(1 for c in calls if c.startswith("nlrha piece")) == 22         # no record computed twice
    assert any(c.startswith("nlrha run") and "computed=%d" % (22 - kept) in c for c in calls)
    assert "interrupted" in " ".join(st["IN_ExT/nlrha"].get("notes") or [])
    # NL-21: the pushover flagged member 5, the runner promoted it and the pushover ran again (a new model)
    prom = json.load(open(os.path.join(work, "jobs", "IN_ExT", "nl_promote_fibre.json")))
    assert prom["pushover"] == [5] and st["IN_ExT/pushover"]["promotion_rounds"] == 1
    assert [c for c in calls if c.startswith("pushover run")] == ["pushover run dirs=XY computed=2"] * 2
    assert any("ddm run" in c and "speed_factor=1" in c for c in calls)
    assert calls[-1] == "report" and "criteria" in calls
    # ONE results zip: the job folders without the journals, and the manifest
    zips = [f for f in os.listdir(res) if f.endswith(".zip")]
    assert len(zips) == 1
    with zipfile.ZipFile(os.path.join(res, zips[0])) as z:
        names = z.namelist()
        man = json.loads(z.read("STAGE2_MANIFEST.json"))
    assert "jobs/IN_ExT/complete_gate.json" in names and "jobs/IN_ExT/units/u1/ddm_results.json" in names
    assert not [n for n in names if "nl_checkpoints" in n] and "STAGE2_RUN.log" in names
    assert man["settings"]["speed_factor"] == 1.0 and man["settings"]["ddm_first_rung_time_limit_s"] == 2400.0
    assert man["fingerprints"]["hr_engine_fingerprint"] and man["fingerprints"]["nl_code_key"]
    assert man["jobs"]["IN_ExU"]["steps"]["pushover"]["state"] == "skipped"
    assert man["jobs"]["IN_ExT"]["gate"]["status"] == "COMPLETE"
    assert man["jobs"]["IN_ExT"]["steps"]["nlrha"]["seconds"] > 0
    assert set(man["files"]) == {n for n in names if n.startswith("jobs/")}
    import run_stage2 as NS
    import argparse
    zp = os.path.join(res, zips[0])
    assert NS.cmd_verify(argparse.Namespace(zip=zp)) == 0
    with zipfile.ZipFile(zp, "a") as z:                                     # a file changed after the run
        z.writestr("jobs/IN_ExT/extra.txt", "x")
    assert NS.cmd_verify(argparse.Namespace(zip=zp)) == 4
    # once more: nothing to run, the zip is written again
    os.remove(zp)
    r = subprocess.run(cmd, env=_env("0.05"), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and _calls(work, "IN_ExT") == calls
    assert len([f for f in os.listdir(res) if f.endswith(".zip")]) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_a_closed_window_leaves_the_step_running_and_the_next_run_waits(tmp_path):
    """Only the runner is stopped (its window closed); its analysis process carries on. The next run waits for it,
    then continues: nothing runs twice at once."""
    gold = _gold(tmp_path / "gold", names=("IN_ExT",), unit=False, params=("IN_ExT",))
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    cmd = _cmd(gold, work, res, eng, workers=2)
    p = subprocess.Popen(cmd, env=_env("0.3"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ck = os.path.join(work, "jobs", "IN_ExT", "nl_checkpoints", "nlrha")
    t0 = time.time()
    while time.time() - t0 < 120 and not (os.path.isdir(ck) and len(os.listdir(ck)) >= 2):
        time.sleep(0.05)
    p.kill(); p.wait()                                     # the runner only
    r = subprocess.run(cmd, env=_env("0.05"), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "waiting for IN_ExT/nlrha" in r.stdout
    calls = _calls(work, "IN_ExT")
    assert sum(1 for c in calls if c.startswith("nlrha piece")) == 22


def test_a_second_runner_on_the_same_folder_is_refused(tmp_path):
    import run_stage2 as NS
    w = tmp_path / "w"; w.mkdir()
    (w / "stage2.lock").write_text("%d now\n" % os.getppid())             # a live process: the parent
    with pytest.raises(SystemExit):
        with NS.Lock(str(w)):
            pass
    (w / "stage2.lock").write_text("999999 then\n")                  # a dead runner's lock is taken over
    with NS.Lock(str(w)):
        assert (w / "stage2.lock").read_text().startswith(str(os.getpid()))
