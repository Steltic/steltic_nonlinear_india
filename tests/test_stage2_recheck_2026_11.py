"""Stage 2, the re-check of c39942b (R1-R3, M6's verify check and the low notes)."""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_run_stage2 import RUNNER, _gold, _engine, _env, _cmd, _calls      # noqa: E402
from test_stage2_review_2026_11 import _repo, ENGINE_FILES                   # noqa: E402

BURN = "import time\nt = time.process_time()\nwhile time.process_time() - t < %s: pass\n"


def _run_to_end(NS, s, job, watchdog_s, limit=120):
    r = NS.Run(s, 1, 1.0, sys.executable, dict(os.environ), str(job), watchdog_s=watchdog_s)
    r.start_next()
    t0, rc = time.time(), None
    while rc is None and time.time() - t0 < limit:
        time.sleep(0.2)
        rc = r.poll()
    return r, rc


# ---------------------------------------------------------------------------------------------------- R1
def test_the_watchdog_counts_children_that_have_ended(tmp_path):
    """R1: the pushover runs X in one child process, then Y in another (L14). The second child computes at full speed
    from zero; the watchdog must count the first one's CPU too, or it calls a computing step hung. Each child here
    computes for longer than the watchdog's window."""
    import run_stage2 as NS
    job = tmp_path / "J"; job.mkdir()
    step = ("import subprocess, sys\n"
            "subprocess.check_call([sys.executable, '-c', %r])\n"
            "subprocess.check_call([sys.executable, '-c', %r])\n") % (BURN % 2.5, BURN % 3.5)
    s = dict(id="J/pushover", job=str(job), kind="pushover", cmd=[sys.executable, "-c", step], chunks=[],
             state="running")
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.5)
    assert rc == 0 and not r.hung


def test_the_watchdog_lets_a_parent_finish_after_its_pool(tmp_path):
    """R1, the NLRHA and DDM parents: a pool of workers computes, the pool closes, and the parent's own
    post-processing then takes longer than the window while using less CPU than the pool did."""
    import run_stage2 as NS
    job = tmp_path / "J"; job.mkdir()
    step = ("import subprocess, sys, time\n"
            "pool = [subprocess.Popen([sys.executable, '-c', %r]) for _ in range(2)]\n"
            "assert all(p.wait() == 0 for p in pool)\n" + BURN % 2.5) % (BURN % 2.0)
    s = dict(id="J/nlrha", job=str(job), kind="nlrha", cmd=[sys.executable, "-c", step], chunks=[], state="running")
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.5)
    assert rc == 0 and not r.hung
    # and a step that stops computing is still stopped once its children have ended
    step = "import subprocess, sys, time\nsubprocess.check_call([sys.executable, '-c', %r])\ntime.sleep(60)\n" % (BURN % 1.0)
    s = dict(id="J/ddm", job=str(job), kind="ddm", cmd=[sys.executable, "-c", step], chunks=[], state="running")
    t0 = time.time()
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.0)
    assert r.hung and time.time() - t0 < 30


# ---------------------------------------------------------------------------------------------------- R2
def _part_way(job, state="resume", gravity="g_old"):
    return dict(id="J/nlrha", job=str(job), kind="nlrha", cmd=["py", "--record-cache", str(job / "ck")], state=state,
                after=["J/gravity"], started_fingerprint=dict(inputs="i", engine="e_old", gravity=gravity, tables="t"))


def test_a_step_interrupted_in_its_first_run_follows_the_new_gravity_record(tmp_path, monkeypatch):
    """R2: a step part-way through its first run (no finished command, so no recheck) when the engine changes. After
    the gravity record is redone: other gravity states -> it starts again, its records set aside; the same states ->
    it keeps its records and takes the new start fingerprint, so a later refresh never sets aside what it computes."""
    import nl_orchestrate as NO
    job = tmp_path / "J"; (job / "ck").mkdir(parents=True)
    (job / "ck" / "r00.done").write_text("x")
    fp = dict(inputs="i", engine="e_new", gravity="g_new", tables="t")
    monkeypatch.setattr(NO, "fingerprint", lambda d, s: dict(fp))
    g = dict(id="J/gravity", job=str(job), kind="gravity", cmd=["py"], state="done")
    s = _part_way(job)
    NO.reconcile_rechecks(dict(env={}, steps=[g, s]), str(job))
    assert s["state"] == "pending" and "started_fingerprint" not in s
    assert not (job / "ck").exists() and any(f.startswith("ck.before_refresh_") for f in os.listdir(job))
    # only the engine changed: the records stand, the start fingerprint is the new one
    (job / "ck").mkdir(); (job / "ck" / "r00.done").write_text("x")
    s = _part_way(job, gravity="g_new")
    NO.reconcile_rechecks(dict(env={}, steps=[g, s]), str(job))
    assert s["state"] == "resume" and s["started_fingerprint"] == fp and (job / "ck" / "r00.done").exists()
    # a finished or skipped step, or one already in recheck, is not touched here
    for st in ("done", "skipped"):
        s = _part_way(job, state=st)
        NO.reconcile_rechecks(dict(env={}, steps=[g, s]), str(job))
        assert s["state"] == st and s["started_fingerprint"]["gravity"] == "g_old"


def _kill_after(cmd, env, work, ck, n_records, limit=120):
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < limit and not (os.path.isdir(ck) and
                                            len([f for f in os.listdir(ck) if f.endswith(".done")]) >= n_records):
        time.sleep(0.05)
    for s in json.load(open(os.path.join(work, "stage2_queue.json")))["steps"]:   # the PC restarting
        if s.get("pid"):
            try:
                os.killpg(int(s["pid"]), signal.SIGKILL)
            except Exception:                                    # noqa: BLE001
                pass
    p.kill(); p.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="kills process groups")
def test_records_computed_after_an_engine_change_are_kept(tmp_path):
    """R2 end to end (the reviewer's r_started_fp): an NLRHA is killed in its first run; the engine changes the
    gravity states; it is killed again part-way; the third run finishes. Every record after the engine change is
    computed exactly once (22)."""
    gold = _gold(tmp_path / "gold", names=("IN_ExT",), unit=False, params=("IN_ExT",))
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    env = dict(_env("0.15"), STUB_GRAVITY_FROM_ENGINE="1")
    ck = os.path.join(work, "jobs", "IN_ExT", "nl_checkpoints", "nlrha")
    cmd = _cmd(gold, work, res, eng, workers=1)
    _kill_after(cmd, env, work, ck, 3)
    open(os.path.join(eng, "engine3d.py"), "a").write("# engine v2: other gravity states\n")
    shutil.rmtree(ck)                                # the real record keys hold the engine: v1 records are not reused
    _kill_after(cmd, env, work, ck, 4)
    r = subprocess.run(cmd, env=dict(env, STUB_SECONDS="0.01"), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = _calls(work, "IN_ExT")
    after = calls[calls.index("gravity", 1):]
    assert sum(1 for c in after if c.startswith("nlrha piece")) == 22, after
    s = [x for x in json.load(open(os.path.join(work, "stage2_queue.json")))["steps"] if x["kind"] == "nlrha"][0]
    assert not [h for h in s.get("refresh_history") or [] if h["from_state"] in ("running", "resume")
                and "gravity states changed" in h["reason"]]


# ---------------------------------------------------------------------------------------------------- R3
def test_a_bundle_without_commits_is_refused(tmp_path, capsys):
    """R3: a bundle made from a folder that is no git clone (bundle --accept-versions) records no HR commit; plan
    and run refuse it unless --accept-versions is given, and run refuses before it extracts or syncs anything."""
    import run_stage2 as NS
    hr = str(tmp_path / "steltic_india")
    _repo(hr, ENGINE_FILES)
    eng = os.path.join(hr, "steel_engine")
    gold = _gold(tmp_path / "gold")
    out = str(tmp_path / "bundle.zip")
    # the HR folder of the bundle is a plain copy (not a git clone): only --accept-versions makes the bundle
    hr_plain = str(tmp_path / "hr_plain"); os.makedirs(hr_plain)
    shutil.copytree(eng, os.path.join(hr_plain, "steel_engine"))
    man = NS.main(["bundle", "--jobs-root", gold, "--hr", hr_plain, "--out", out, "--accept-versions"])
    assert man["hr_commit"] is None and man["accepted_unclean"]
    problems, info = NS.check_versions(man, eng)
    assert problems and "does not record a clean HR engine commit" in problems[0] and not info["ok"]
    for m in (dict(man, hr_commit="abc", nl_commit=None, accepted_unclean=False),
              dict(man, hr_commit="abc", nl_commit="def", accepted_unclean=True)):
        assert any("does not record a clean" in p for p in NS.check_versions(m, eng)[0])
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        NS.main(["plan", "--gold", out, "--engine", eng, "--work", str(tmp_path / "w")])
    assert e.value.code == NS.EXIT_REFUSED and "does not record a clean" in capsys.readouterr().out
    work = tmp_path / "w2"
    with pytest.raises(SystemExit) as e:
        NS.main(["run", "--gold", out, "--engine", eng, "--work", str(work), "--results", str(tmp_path / "res"),
                 "--workers", "1", "--memory-gb", "8"])
    assert e.value.code == NS.EXIT_REFUSED
    assert not (work / "gold").exists() and not (work / "jobs").exists()     # refused before extracting / syncing
    p = NS.main(["plan", "--gold", out, "--engine", eng, "--work", str(tmp_path / "w"), "--workers", "2",
                 "--memory-gb", "8", "--accept-versions"])                               # the lead's tests only
    assert p["jobs"] == ["IN_ExT", "IN_ExT/units/u1", "IN_ExU"]


# ---------------------------------------------------------------------------------------------------- M6
def _results_zip(path, ddm):
    """A results zip as write_results makes it, with the given ddm_results.json per job."""
    files = {"jobs/%s/ddm_results.json" % j: json.dumps(d).encode() for j, d in ddm.items()}
    man = dict(files={k: hashlib.sha256(v).hexdigest() for k, v in files.items()}, summary={}, versions=dict(ok=True))
    with zipfile.ZipFile(path, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
        z.writestr("STAGE2_MANIFEST.json", json.dumps(man))
    return str(path)


def test_verify_checks_every_ddm_output_s_factor_and_budget(tmp_path, capsys):
    """M6: `verify` fails a results zip whose DDM outputs do not record factor 1.0 and the 2,400 s budget (a sweep
    rung 2,400 x 1, 2 or 4), so the lead sees that the PC ran with the right factor."""
    import run_stage2 as NS
    good = dict(options=dict(speed_factor=1.0, time_limit=2400.0, time_limit_base=2400.0),
                runs=[dict(label="1.5DL", time_limit_s=2400.0),
                      dict(label="1.2DL", time_limit_s=4800.0, retries=[dict(time_limit_s=2400.0), dict(time_limit_s=4800.0)])])
    z = _results_zip(tmp_path / "ok.zip", {"IN_ExT": good, "IN_ExT/units/u1": dict(good, runs=[])})
    assert NS.cmd_verify(argparse.Namespace(zip=z)) == 0
    bad = {"A": dict(good, options=dict(speed_factor=1.6, time_limit=3840.0, time_limit_base=2400.0)),
           "B": dict(good, options=dict(speed_factor=1.0, time_limit=2000.0, time_limit_base=2000.0)),
           "C": dict(good, options=dict(time_limit=2400.0)),                              # an October output
           "D": dict(good, runs=[dict(label="x", time_limit_s=3000.0)])}
    capsys.readouterr()
    z = _results_zip(tmp_path / "bad.zip", bad)
    assert NS.cmd_verify(argparse.Namespace(zip=z)) == 4
    out = capsys.readouterr().out
    assert "4 problem(s)" in out and out.count("DDM budget:") == 4
    assert "jobs/A/ddm_results.json records speed factor 1.6" in out and "[3000.0] s" in out


def test_the_ddm_report_says_the_budget_gives_more_compute_than_october():
    from steltic_ddm.report_ddm import _time_limit_text
    from steltic_ddm.cli import resolve_time_limit
    t = _time_limit_text(dict(time_limit=2400.0, speed_factor=1.0, time_limit_base=2400.0))
    assert "somewhat more compute than October's wall-clock limit" in t
    assert "somewhat more compute than the October wall-clock limit" in resolve_time_limit(factor=1.0)["time_limit_basis"]
    assert _time_limit_text(dict(time_limit=2400.0)) == "2400 s"                       # October outputs unchanged


# ---------------------------------------------------------------------------------------------------- low notes
def test_results_remove_only_their_own_temporary_files(tmp_path, monkeypatch):
    import run_stage2 as NS
    res = tmp_path / "res"; res.mkdir()
    (res / "stage2_results_old.zip.zip_tmp").write_text("half")
    (res / "stage2_results_old.json.json_tmp").write_text("half")
    (res / "other_upload.zip_tmp").write_text("someone else's")
    monkeypatch.setattr(NS, "calibration_s", lambda py: None)
    NS.write_results(str(tmp_path), dict(steps=[], env={}), argparse.Namespace(workers=1, memory_gb=1.0), str(res))
    left = sorted(os.listdir(res))
    assert "other_upload.zip_tmp" in left and not [f for f in left if f.startswith("stage2_results_") and f.endswith("_tmp")]


def test_status_before_any_run_is_not_an_error(tmp_path, capsys):
    import run_stage2 as NS
    assert NS.main(["status", "--work", str(tmp_path / "nothing_yet")]) == 0
    assert "No stage-2 run" in capsys.readouterr().out


def test_set_aside_outputs_go_once_the_re_run_has_finished(tmp_path):
    """Low note: a design change sets a step's outputs and journals aside (M1); once that step's re-run has
    finished they are removed. A failed re-run keeps them (tests/test_stage2_review_2026_11.py, M1)."""
    gold = _gold(tmp_path / "gold", names=("IN_ExT",), unit=False, params=("IN_ExT",))
    eng = _engine(tmp_path)
    work, res = str(tmp_path / "work"), str(tmp_path / "res")
    r = subprocess.run(_cmd(gold, work, res, eng), env=_env("0.02"), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    open(os.path.join(gold, "IN_ExT", "cfg.py"), "a").write("cfg['sizes'] = 'B'\n")      # a design change
    shutil.rmtree(res)
    r = subprocess.run(_cmd(gold, work, res, eng), env=_env("0.02"), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    left = []
    for base, ds, fs in os.walk(os.path.join(work, "jobs")):
        left += [os.path.join(base, x) for x in ds + fs if ".before_refresh_" in x]
    # what is left is only the earlier design's fibre promotions, which belong to no single step
    assert [os.path.basename(p).split(".before_refresh_")[0] for p in left] in ([], ["nl_promote_fibre.json"]), left
    q = json.load(open(os.path.join(work, "stage2_queue.json")))
    assert not [s["id"] for s in q["steps"] if s.get("set_aside_paths")]


def test_drop_set_aside_removes_only_what_was_moved_aside(tmp_path):
    import nl_orchestrate as NO
    keep = tmp_path / "pushover"; keep.mkdir()
    gone = tmp_path / "pushover.before_refresh_20261106000000"; gone.mkdir()
    s = dict(set_aside_paths=[str(gone), str(keep)], set_aside=str(gone))
    NO.drop_set_aside(s)
    assert keep.exists() and not gone.exists() and "set_aside_paths" not in s and "set_aside" not in s


def test_the_box_queue_runs_single_threaded_blas(tmp_path):
    """Low note (M6): the box's queue sets OMP_NUM_THREADS=1, as the PC's does, so threaded BLAS cannot count extra
    threads' CPU against a DDM sweep's CPU-time budget."""
    import nl_orchestrate as NO
    d = NO.plan(argparse.Namespace(queue=str(tmp_path / "q.json"), force=False, jobs=[], analyses=[], python="py",
                                   job_args=None, speed_factor=None, heavy=False, engine=None))
    assert d["env"]["OMP_NUM_THREADS"] == "1"
