"""The independent review of the stage-2 branch (briefs/NL_STAGE2_REVIEW.md): one test per finding fixed. Stand-in
analyses (tests/stage2_stubs) where a run is needed; no OpenSees except the calibration run."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import types
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
RUNNER = os.path.join(ROOT, "scripts", "run_stage2.py")
from test_run_stage2 import _gold, _engine, _env, _cmd, _calls     # noqa: E402

GIT = ["git", "-c", "user.email=test@example.invalid", "-c", "user.name=stage2 test", "-c", "commit.gpgsign=false"]


def ns(**kw):
    return argparse.Namespace(**kw)


def _repo(path, files):
    os.makedirs(path, exist_ok=True)
    for rel, text in files.items():
        p = os.path.join(path, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(GIT + ["-C", path, "add", "-A"], check=True)
    subprocess.run(GIT + ["-C", path, "commit", "-qm", "c1"], check=True)
    return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def _commit(path, rel, text):
    open(os.path.join(path, rel), "w").write(text)
    subprocess.run(GIT + ["-C", path, "commit", "-qam", "c2"], check=True)
    return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


ENGINE_FILES = {"steel_engine/%s" % n: "# %s\n" % n for n in ("static_model.py", "engine3d.py", "india_loads.py",
                                                               "india_combos.py", "roof_geometry.py", "sections.py")}


# ---------------------------------------------------------------------------------------------------- B1
def test_the_runner_imports_and_plans_without_posix_modules(tmp_path):
    """B1: on Windows there is no fcntl, resource, termios, pwd or grp: the runner must import and plan without them."""
    gold = _gold(tmp_path / "gold")
    code = ("import sys, runpy\n"
            "for m in ('fcntl', 'resource', 'termios', 'pwd', 'grp'): sys.modules[m] = None\n"
            "sys.argv = ['run_stage2.py', 'plan', '--gold', %r, '--work', %r, '--workers', '4', '--memory-gb', '8',"
            " '--accept-versions']\n"
            "runpy.run_path(%r, run_name='__main__')\n") % (gold, str(tmp_path / "w"), RUNNER)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Stage-2 plan: 3 job(s)" in r.stdout


# ---------------------------------------------------------------------------------------------------- B2
def test_the_bundle_carries_the_commits_and_a_mismatch_is_refused(tmp_path, capsys):
    import run_stage2 as NS
    hr = str(tmp_path / "steltic_india")
    hr_c1 = _repo(hr, ENGINE_FILES)
    nl = str(tmp_path / "nl")
    nl_c1 = _repo(nl, {"README": "nl\n"})
    gold = _gold(tmp_path / "gold")
    out = str(tmp_path / "bundle.zip")
    man = NS.main(["bundle", "--jobs-root", gold, "--hr", hr, "--out", out, "--nl-repo", nl])
    assert man["hr_commit"] == hr_c1 and man["nl_commit"] == nl_c1
    assert man["jobs"] == ["IN_ExT", "IN_ExT/units/u1", "IN_ExU"] and man["without_collected_values"] == ["IN_ExU"]
    with zipfile.ZipFile(out) as z:
        assert NS.BUNDLE_MANIFEST in z.namelist() and "IN_ExT/hinge_params_collected.json" in z.namelist()
    eng = os.path.join(hr, "steel_engine")
    problems, info = NS.check_versions(man, eng, nl_root=nl)
    assert problems == [] and info["ok"]
    # the HR checkout moves on: refused, with the exact git checkout to run
    _commit(hr, "steel_engine/sections.py", "# sections, changed\n")
    problems, _ = NS.check_versions(man, eng, nl_root=nl)
    assert len(problems) == 1 and ("git checkout %s" % hr_c1) in problems[0] and "HR engine" in problems[0]
    subprocess.run(["git", "-C", hr, "checkout", "-q", hr_c1], check=True)
    # a local change in a tracked engine file
    open(os.path.join(eng, "engine3d.py"), "a").write("# edited\n")
    problems, _ = NS.check_versions(man, eng, nl_root=nl)
    assert len(problems) == 1 and "local changes" in problems[0] and "engine3d.py" in problems[0]
    subprocess.run(["git", "-C", hr, "checkout", "-q", "--", "."], check=True)
    # a folder that is not a git clone
    plain = str(tmp_path / "plain_engine")
    shutil.copytree(eng, plain)
    problems, _ = NS.check_versions(man, plain, nl_root=nl)
    assert len(problems) == 1 and "not a git clone" in problems[0]
    # the NL checkout at another commit
    _commit(nl, "README", "nl 2\n")
    problems, _ = NS.check_versions(man, eng, nl_root=nl)
    assert len(problems) == 1 and "nonlinear tools" in problems[0] and ("git checkout %s" % nl_c1) in problems[0]
    # plan refuses (exit 2) with the message; no bundle manifest at all is refused too
    with pytest.raises(SystemExit) as e:
        NS.main(["plan", "--gold", out, "--engine", plain, "--work", str(tmp_path / "w")])
    assert e.value.code == NS.EXIT_REFUSED and "not a git clone" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        NS.main(["plan", "--gold", gold, "--engine", eng, "--work", str(tmp_path / "w")])
    assert e.value.code == NS.EXIT_REFUSED and NS.BUNDLE_MANIFEST in capsys.readouterr().out
    # the bundle refuses unclean checkouts
    open(os.path.join(eng, "engine3d.py"), "a").write("# edited\n")
    with pytest.raises(SystemExit):
        NS.main(["bundle", "--jobs-root", gold, "--hr", hr, "--out", out, "--nl-repo", nl])


def test_the_launcher_has_no_hub_engine_fallback():
    src = open(os.path.join(ROOT, "windows", "Run-Stage2.ps1")).read()
    assert "modules\\steltic_india" not in src and "constraints.txt" in src and "UV_UNMANAGED_INSTALL" in src


def test_the_engine_fingerprint_covers_every_engine_file_and_ignores_line_ends(tmp_path):
    from snl.hr_gravity import engine_fingerprint, engine_files
    a, b = tmp_path / "a", tmp_path / "b"
    for d, nl in ((a, "\n"), (b, "\r\n")):
        d.mkdir()
        for n in ("engine3d.py", "static_model.py", "sections.py", "design_pipeline.py", "is808_shapes.csv"):
            (d / n).write_bytes(("line 1%sline 2%s" % (nl, nl)).encode())
    assert engine_fingerprint(str(a)) == engine_fingerprint(str(b))             # a CRLF checkout of the same commit
    assert {"sections.py", "design_pipeline.py", "is808_shapes.csv"} <= set(engine_files(str(a)))
    f0 = engine_fingerprint(str(a))
    (a / "sections.py").write_text("def double_angle_label(): pass\n")          # what the IN_Ex21 gold needs
    assert engine_fingerprint(str(a)) != f0


# ---------------------------------------------------------------------------------------------------- B3
def test_a_reused_pid_never_makes_the_runner_wait(tmp_path):
    """B3: after a restart the recorded pids belong to other processes. Only the very process recorded (pid and start
    token) counts."""
    import run_stage2 as NS
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        tok = NS.proc_token(p.pid)
        assert tok and NS.same_process(p.pid, tok)
        assert not NS.same_process(p.pid, "proc:another-boot:1") and not NS.same_process(p.pid, None)
        d = dict(steps=[dict(id="J/pushover", pid=p.pid, pid_token="proc:another-boot:1")])
        t0 = time.time()
        NS._wait_for_orphans(d, None)                          # returns at once: not the recorded process
        assert time.time() - t0 < 2.0
    finally:
        p.kill(); p.wait()


# ---------------------------------------------------------------------------------------------------- M1, M2
def _stub_run(gold, work, res, eng, extra=(), fail="", seconds="0.05", timeout=300):
    env = _env(seconds)
    if fail:
        env["STUB_FAIL"] = fail
    return subprocess.run(_cmd(gold, work, res, eng, extra=extra), env=env, capture_output=True, text=True,
                          timeout=timeout)


def _queue(work):
    return {s["id"]: s for s in json.load(open(os.path.join(work, "stage2_queue.json")))["steps"]}


def test_a_design_change_never_ships_the_old_results(tmp_path):
    """M1 / M2: gold B changes the design and B's pushover fails. Gold A's pushover package must not be in the zip,
    nor its DDM block in the calc package; A's fibre promotions and rounds do not count for B."""
    gold = _gold(tmp_path / "gold", names=("IN_ExT",), unit=False, params=("IN_ExT",))
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    r = _stub_run(gold, work, res, eng)
    assert r.returncode == 0, r.stdout + r.stderr
    job = os.path.join(work, "jobs", "IN_ExT")
    assert os.path.exists(os.path.join(job, "pushover", "pushover_package.json"))
    assert _queue(work)["IN_ExT/pushover"]["promotion_rounds"] == 1
    cp = os.path.join(job, "design", "calc_package.json")             # as the DDM writes its block
    json.dump(dict(json.load(open(cp)), ddm_analysis={"lambda_u": 1.3}), open(cp, "w"), indent=1)
    open(os.path.join(gold, "IN_ExT", "cfg.py"), "a").write("cfg['sizes'] = 'B'\n")   # gold B
    shutil.rmtree(res)
    r = _stub_run(gold, work, res, eng, fail="pushover")
    assert r.returncode == 3, r.stdout + r.stderr
    q = _queue(work)
    assert q["IN_ExT/pushover"]["state"] == "failed" and "promotion_rounds" not in q["IN_ExT/pushover"]
    zp = os.path.join(res, [f for f in os.listdir(res) if f.endswith(".zip")][0])
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        cpz = json.loads(z.read("jobs/IN_ExT/design/calc_package.json"))
    assert "jobs/IN_ExT/pushover/pushover_package.json" not in names       # A's package is set aside, not shipped
    assert "ddm_analysis" not in cpz or cpz["ddm_analysis"] != {"lambda_u": 1.3}
    assert any(f.startswith("pushover.before_refresh_") for f in os.listdir(job))
    assert any(f.startswith("nl_promote_fibre.json.before_refresh_") for f in os.listdir(job))


def test_promotion_rounds_are_read_from_the_design_s_own_promotion_file(tmp_path):
    """M2 / L13: the rounds come from nl_promote_fibre.json (one history entry per round), so a kill between the
    promotion and the queue save loses no round, and a new design (its file set aside) starts at zero."""
    import run_stage2 as NS
    job = str(tmp_path)
    assert NS.promotion_rounds(job, "pushover") == 0
    NS.promote(job, [5], "round 1", "pushover"); NS.promote(job, [6], "round 2", "pushover")
    NS.promote(job, [9], "round 1", "nlrha")
    assert NS.promotion_rounds(job, "pushover") == 2 and NS.promotion_rounds(job, "nlrha") == 1
    import nl_orchestrate as NO
    s = dict(state="done", promotion_rounds=2, promoted=[[5]], note_promotion="x", started_fingerprint={})
    NO._reset(s, "pending", "the job's input files changed")
    assert not {"promotion_rounds", "promoted", "note_promotion", "started_fingerprint"} & set(s)


# ---------------------------------------------------------------------------------------------------- M3, M4
def test_a_failed_gravity_record_ends_failed_with_the_zip_and_retry_runs_the_job(tmp_path):
    """M3: after an engine change a failed gravity re-record leaves no step in `recheck`: the run ends (rc 3) with the
    zip. M4: --retry-failed then runs the gravity record AND the job's analyses (not a false "Done")."""
    gold = _gold(tmp_path / "gold", names=("IN_ExT", "IN_ExV"), unit=False, params=("IN_ExT", "IN_ExV"))
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    assert _stub_run(gold, work, res, eng).returncode == 0
    open(os.path.join(eng, "engine3d.py"), "a").write("# engine 2\n")      # an engine change
    shutil.rmtree(res)
    r = _stub_run(gold, work, res, eng, fail="gravity")
    assert r.returncode == 3, r.stdout + r.stderr
    q = _queue(work)
    assert q["IN_ExT/gravity"]["state"] == "failed"
    assert not [k for k, s in q.items() if s["state"] in ("recheck", "pending", "resume")]
    assert q["IN_ExT/pushover"]["state"] == "skipped" and "gravity record" in q["IN_ExT/pushover"]["skip_reason"]
    assert [f for f in os.listdir(res) if f.endswith(".zip")]                # the zip is written
    shutil.rmtree(res)
    calls0 = len(_calls(work, "IN_ExT"))
    r = _stub_run(gold, work, res, eng, extra=["--retry-failed"])
    assert r.returncode == 0, r.stdout + r.stderr
    q = _queue(work)
    assert all(s["state"] == "done" for s in q.values()), {k: s["state"] for k, s in q.items()}
    new = _calls(work, "IN_ExT")[calls0:]
    assert "gravity" in new and any(c.startswith("ddm run") for c in new)    # the DDM (reset by the engine) ran


# ---------------------------------------------------------------------------------------------------- M5
def test_a_step_back_to_pending_takes_a_fresh_start_fingerprint(tmp_path):
    """M5: reconcile_rechecks puts a step back to pending without its old start fingerprint, so a later refresh
    does not set aside the record cache the new run builds."""
    import nl_orchestrate as NO
    job = tmp_path / "J"; (job / "design").mkdir(parents=True)
    (job / "cfg.py").write_text("cfg = {}\n")
    json.dump(dict(states={"D": 2.0}), open(job / "nl_hr_gravity.json", "w"))
    s = dict(id="J/nlrha", job=str(job), kind="nlrha", cmd=["py", "--record-cache", str(job / "ck")], state="recheck",
             chunks=[{}], fingerprint=dict(inputs="x", gravity="old", tables="t"), started_fingerprint=dict(gravity="old"))
    d = dict(env={}, steps=[s])
    NO.reconcile_rechecks(d, str(job))
    assert s["state"] == "pending" and "started_fingerprint" not in s


# ---------------------------------------------------------------------------------------------------- M6
def test_the_ddm_limit_is_cpu_time_journaled_for_a_replay(tmp_path):
    """M6: the journal records the CPU clock beside the wall clock; a replay gives the recorded CPU values (a pause or
    load does not move them), and the sweep's limit is taken on that clock."""
    from snl import checkpoint as CK
    import inspect
    from steltic_ddm import solver
    src = inspect.getsource(solver.sweep)
    assert "_CK.cpu_clock(c0) > time_limit" in src and "cpu_seconds=round(_CK.cpu_clock(c0), 1)" in src

    class Ops:
        t = 0.0

        def analyze(self, n=1):
            c = time.process_time()
            while time.process_time() - c < 0.02:
                pass
            time.sleep(0.05)                                    # wall time that is not CPU time
            self.t += 1.0
            return 0

        def getTime(self):
            return self.t

        def getNodeTags(self):
            return [1]

        def nodeDisp(self, n):
            return [self.t, 0.0, 0.0]
    ops = Ops()
    J = CK.Journal(str(tmp_path / "j.ckpt"), "k")
    J.begin("x", ops)
    for _ in range(4):
        ops.analyze(1)
    seg = list(J.data["segments"]["x"])
    J.end(); J.save()
    assert all(len(e) == 5 for e in seg) and seg[-1][4] < seg[-1][3]        # CPU below wall
    ops.t = 0.0
    J2 = CK.Journal(str(tmp_path / "j.ckpt"), "k")
    J2.begin("x", ops)
    got = []
    for _ in range(4):
        ops.analyze(1)
        got.append(J2.cpu_elapsed())
    J2.end()
    assert got == [e[4] for e in seg]                                        # the replay repeats the CPU clock


def test_the_calibration_run_and_the_ddm_records(monkeypatch):
    """M6: a fixed calibration run is recorded with the factor; it is not in the journal key (it varies run to run);
    each retry rung records its CPU seconds."""
    from snl import checkpoint as CK
    from steltic_ddm import cli
    c = CK.calibration_benchmark(repeats=1)
    assert c is not None and c > 0
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    imp = dict(tag="+X", dir="X", psi=1 / 200.0, bow_sign=1)
    base = dict(nsub=(2, 2, 4), _checkpoint=dict(dir="/tmp/none_used", budget_s=None, t0=None))
    k1 = cli._journal_for("/tmp/job_none", "1.5DL+1.5LL", imp, dict(base, calibration_s=1.0)).key
    k2 = cli._journal_for("/tmp/job_none", "1.5DL+1.5LL", imp, dict(base, calibration_s=2.0)).key
    assert k1 == k2
    res = cli.sweep_with_retries(lambda dl, k: dict(status="SOLVER_FAILURE" if k < 2 else "LIMIT_POINT", lambda_end=1.0,
                                                    steps=1, seconds=2.0, cpu_seconds=1.5), 0.05, time_limit=2400.0)
    assert [r["cpu_seconds"] for r in res["retries"]] == [1.5, 1.5]


# ---------------------------------------------------------------------------------------------------- M7
def test_the_queue_survives_a_lost_write_and_a_held_file(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    q = str(tmp_path / "q.json")
    NO.save(q, dict(steps=[1]))
    NO.save(q, dict(steps=[1, 2]))
    assert json.load(open(q + ".bak")) == dict(steps=[1])
    open(q, "wb").write(b"\0" * 64)                                          # a power cut on NTFS
    assert NO.load(q) == dict(steps=[1])
    real, calls = os.replace, []

    def held(a, b):                                                          # an antivirus holding the file once
        calls.append(a)
        if len(calls) == 1:
            raise PermissionError("held")
        return real(a, b)
    monkeypatch.setattr(NO.os, "replace", held)
    monkeypatch.setattr(NO.time, "sleep", lambda s: None)
    NO.save(q, dict(steps=[3]))
    assert json.load(open(q)) == dict(steps=[3]) and len(calls) == 2


def test_an_error_in_one_step_s_bookkeeping_does_not_stop_the_others(tmp_path, monkeypatch):
    import run_stage2 as NS
    gold = _gold(tmp_path / "gold", names=("IN_ExT",), unit=False, params=("IN_ExT",))
    eng = _engine(tmp_path)
    for k, v in _env("0.02").items():
        monkeypatch.setenv(k, v)

    def boom(job, kind):
        raise RuntimeError("a disk error")
    monkeypatch.setattr(NS, "flagged_elastic", boom)
    rc = NS.main(["run", "--gold", gold, "--work", str(tmp_path / "w"), "--results", str(tmp_path / "r"), "--workers", "2",
                  "--memory-gb", "64", "--engine", eng, "--poll", "0.05", "--accept-versions"])
    q = _queue(str(tmp_path / "w"))
    assert rc == 3 and q["IN_ExT/pushover"]["state"] == "failed" and "bookkeeping" in q["IN_ExT/pushover"]["failed_reason"]
    assert q["IN_ExT/ddm"]["state"] == "done" and q["IN_ExT/report"]["state"] == "done"
    assert [f for f in os.listdir(tmp_path / "r") if f.endswith(".zip")]


# ---------------------------------------------------------------------------------------------------- M8
def test_the_library_versions_are_pinned_and_recorded():
    from snl import checkpoint as CK
    v = CK.library_versions()
    assert v["numpy"] and v["openseespy"] and v["scipy"]
    pins = dict(l.split("==") for l in open(os.path.join(ROOT, "windows", "constraints.txt")).read().split()
                if "==" in l)
    for n in ("openseespy", "numpy", "scipy"):
        assert pins[n] == v[n], n                                           # the box's versions are the pins
    os.environ.setdefault("PYTHONHASHSEED", "0")
    assert CK.run_key()["libraries"] == v                                     # in every journal / cache key


# ---------------------------------------------------------------------------------------------------- M9
def test_sync_keeps_a_unit_s_ddm_block(tmp_path):
    """M9: a unit nested in its building: the DDM's write into the unit's calc package is not an HR change."""
    import nl_orchestrate as NO
    gold, work = tmp_path / "gold", tmp_path / "work"
    for root in (gold, work):
        for rel in ("IN_ExB/design", "IN_ExB/unitC/design", "IN_ExB/units/stem/design"):
            os.makedirs(root / rel, exist_ok=True)
    for rel in ("IN_ExB/design/calc_package.json", "IN_ExB/unitC/design/calc_package.json",
                "IN_ExB/units/stem/design/calc_package.json"):
        (gold / rel).write_text(json.dumps({"members": [1]}, indent=2))
        (work / rel).write_text(json.dumps({"members": [1], "ddm_analysis": {"l": 1}}, indent=1))
    s = NO.sync(ns(src=str(gold), dst=str(work), jobs=[], dry_run=False))
    assert s["IN_ExB"]["changed"] == []
    for rel in ("IN_ExB/unitC/design/calc_package.json", "IN_ExB/units/stem/design/calc_package.json"):
        assert "ddm_analysis" in json.load(open(work / rel))


# ---------------------------------------------------------------------------------------------------- L10, L15
def test_a_hung_step_is_stopped_and_unmeasured_cpu_is_none(tmp_path, monkeypatch):
    import run_stage2 as NS
    job = tmp_path / "J"; job.mkdir()
    s = dict(id="J/gravity", job=str(job), kind="gravity", cmd=[sys.executable, "-c", "import time; time.sleep(60)"],
             chunks=[], state="running")
    r = NS.Run(s, 1, 1.0, sys.executable, dict(os.environ), str(job), watchdog_s=1.0)
    r.start_next()
    t0 = time.time()
    rc = None
    while rc is None and time.time() - t0 < 30:
        time.sleep(0.2)
        rc = r.poll()
    assert r.hung and time.time() - t0 < 20                                  # stopped, not waited for 60 s
    live, sch = {s["id"]: r}, types.SimpleNamespace(running={s["id"]: (1, 1.0)})
    NS._finish_step(dict(env={}, steps=[s]), s, r, rc, None, sys.executable, {}, live, sch)
    assert s["state"] == "failed" and "no CPU progress" in s["failed_reason"]
    # L15: neither resource nor psutil nor /proc: the CPU time is unknown, recorded as None (not 0)
    monkeypatch.setattr(NS, "children_cpu_s", lambda: None)
    monkeypatch.setattr(NS, "tree_cpu_s", lambda pid: {})
    s2 = dict(id="J/report", job=str(job), kind="report", cmd=[sys.executable, "-c", "pass"], chunks=[], state="running")
    r2 = NS.Run(s2, 1, 1.0, sys.executable, dict(os.environ), str(job))
    r2.start_next()
    while r2.poll() is None:
        time.sleep(0.05)
    NS._finish_step(dict(env={}, steps=[s2]), s2, r2, 0, None, sys.executable, {}, {s2["id"]: r2},
                    types.SimpleNamespace(running={}))
    assert s2["chunks"][-1]["cpu_s"] is None
    assert NS._sum_or_none([None, None]) is None and NS._sum_or_none([1.0, None]) == 1.0


# ---------------------------------------------------------------------------------------------------- L11, L12
def test_leftovers_short_paths_and_plain_errors(tmp_path, monkeypatch):
    import run_stage2 as NS
    import nl_orchestrate as NO
    res = tmp_path / "res"; res.mkdir()
    (res / "stage2_results_x.zip.zip_tmp").write_text("half")
    d = dict(steps=[], env={})
    monkeypatch.setattr(NS, "calibration_s", lambda py: None)
    NS.write_results(str(tmp_path), d, ns(workers=1, memory_gb=1.0), str(res))
    assert not [f for f in os.listdir(res) if f.endswith("zip_tmp")]
    gold = _gold(tmp_path / "gold")
    z = tmp_path / "a_very_long_bundle_name_that_would_eat_the_path_margin.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(NS.BUNDLE_MANIFEST, json.dumps(dict(hr_commit="x", nl_commit="y")))
        for base, ds, fs in os.walk(gold):
            for f in fs:
                p = os.path.join(base, f)
                zf.write(p, os.path.relpath(p, gold))
    root, src, bundle = NS.gold_root(str(z), str(tmp_path / "w"))
    assert os.path.basename(os.path.dirname(root)) == "gold" and len(os.path.basename(root)) == 12
    with pytest.raises(SystemExit) as e:
        NS.check_job_args(["IN_Ex19 pushover --tail none"])
    assert e.value.code == NS.EXIT_REFUSED

    def other_drive(paths):
        raise ValueError("Paths don't have the same drive")
    monkeypatch.setattr(NO.os.path, "commonpath", other_drive)
    NO.sync(ns(src=str(gold), dst=str(tmp_path / "elsewhere"), jobs=[], dry_run=True))     # no ValueError


# ---------------------------------------------------------------------------------------------------- L14
def test_each_pushover_direction_runs_in_a_process_of_its_own(monkeypatch, tmp_path):
    """L14: the eigen solver's start vector depends on the solves made before it in the process, so each direction
    is computed in a child process (--dirs <d> --direction-child, on the same journal) and the parent assembles."""
    from pushover import cli as PC
    assert PC._strip_opts(["run", "J", "--dirs", "X", "Y", "--tail", "none", "--checkpoint-dir", "c"],
                          ("--dirs", "--checkpoint-dir")) == ["run", "J", "--tail", "none"]
    done, cmds = {}, []

    class J:
        def done(self, name):
            return done.get(name)
    monkeypatch.setattr(PC, "_journal", lambda args, pkg: J())

    def call(cmd):
        cmds.append(cmd)
        done["push %s" % cmd[cmd.index("--dirs") + 1]] = {"run": {}}
        return 0
    monkeypatch.setattr(subprocess, "call", call)
    args = ns(dirs=["X", "Y"], checkpoint_dir=str(tmp_path), chunk_seconds=None,
              _argv=["run", "JOB", "--dirs", "X", "Y", "--plasticity", "fibre"])
    PC._directions_in_children(args, None, J())
    assert [c[c.index("--dirs") + 1] for c in cmds] == ["X", "Y"]
    assert all("--direction-child" in c and c[c.index("--checkpoint-dir") + 1] == str(tmp_path) for c in cmds)
    assert all(c[1:4] == ["-m", "pushover", "run"] and c.count("--dirs") == 1 for c in cmds)
