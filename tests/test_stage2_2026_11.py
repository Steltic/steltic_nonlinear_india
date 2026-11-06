"""Stage 2 (2026-11) step 0: the orchestrator's input fingerprints and `refresh`, peak memory per chunk, per-job
options, every HR input file in the journal and cache keys, `sync` from the gold, and the DDM time limit as a compute
budget scaled by the machine's speed factor. No OpenSees runs here."""
import argparse
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def ns(**kw):
    return argparse.Namespace(**kw)


# ------------------------------------------------------------------------------------------- DDM compute budget
def test_ddm_time_limit_is_a_compute_budget(monkeypatch):
    from steltic_ddm import cli
    monkeypatch.delenv("SNL_SPEED_FACTOR", raising=False)
    t = cli.resolve_time_limit()
    assert t["time_limit"] == 2400.0 and t["speed_factor"] == 1.0 and t["time_limit_base"] == 2400.0
    t = cli.resolve_time_limit(factor=1.6)                                   # this box
    assert t["time_limit"] == pytest.approx(3840.0) and t["time_limit_base"] == 2400.0
    assert "speed factor 1.6" in t["time_limit_basis"] and "3840" in t["time_limit_basis"]
    monkeypatch.setenv("SNL_SPEED_FACTOR", "1.6")
    assert cli.resolve_time_limit()["time_limit"] == pytest.approx(3840.0)
    assert cli.resolve_time_limit(factor=1.0)["time_limit"] == 2400.0      # the argument wins over the environment
    t = cli.resolve_time_limit(explicit=1000.0)                              # an explicit limit is taken as given
    assert t["time_limit"] == 1000.0 and t["time_limit_base"] == pytest.approx(625.0) and "given" in t["time_limit_basis"]
    for bad in ("0", "-2", "x"):
        monkeypatch.setenv("SNL_SPEED_FACTOR", bad)
        assert cli.speed_factor() == 1.0
    monkeypatch.delenv("SNL_SPEED_FACTOR")
    # a retry / refresh rescales the STORED budget: October outputs (2400 s, no factor) on this box -> 3840 s; a
    # stage-2 output of this box (3840 s at 1.6) on the owner's PC -> 2400 s
    o_oct = dict(time_limit=2400.0)
    assert cli._retry_opts(o_oct, True, 1.6)["time_limit"] == pytest.approx(3840.0)
    o_s2 = dict(time_limit=3840.0, speed_factor=1.6, time_limit_base=2400.0)
    r = cli._retry_opts(o_s2, True, 1.0)
    assert r["time_limit"] == 2400.0 and r["speed_factor"] == 1.0 and r["time_limit_base"] == 2400.0
    # the parsers: no wall-clock default any more, a speed factor on run and retry
    import inspect
    src = inspect.getsource(cli)
    assert 'r.add_argument("--time-limit", type=float, default=None' in src
    assert src.count('add_argument("--speed-factor"') == 2


def test_each_ddm_result_records_its_limit_and_factor(tmp_path, monkeypatch):
    """The limit of the rung that produced the result (x2, x4 for the NL-30 retries) and the factor are in every
    sweep result; the retry rows carry each rung's own limit."""
    from steltic_ddm import cli
    calls = []

    def do(dl, k):
        calls.append(k)
        return dict(status="SOLVER_FAILURE" if k < 4 else "LIMIT_POINT", lambda_end=1.0, steps=3, seconds=1.0)
    res = cli.sweep_with_retries(do, 0.05, time_limit=3840.0)
    assert [r["time_limit_s"] for r in res["retries"]] == [3840.0, 7680.0, 15360.0]
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from test_third_wave_2026_10 import _ddm_stubs
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    cli = _ddm_stubs(monkeypatch, [])
    job = str(tmp_path / "job"); os.makedirs(job)
    imp = dict(tag="+X", dir="X", psi=1 / 200.0, bow_sign=1)
    base = dict(nsub=(2, 2, 4), residual="none", hardening=0.002, fast=False, nip=5, bow=0.001, max_steps=50,
                time_limit=3840.0, speed_factor=1.6, time_limit_base=2400.0, dlam=0.05, retry_factors=(2, 4), india=False)
    out = cli._worker((job, None, "1.5DL+1.5LL", imp, dict(base)))
    assert out["res"]["time_limit_s"] == 3840.0 and out["res"]["speed_factor"] == 1.6


def test_the_report_and_the_gate_read_the_budget():
    from steltic_ddm.report_ddm import _time_limit_text
    from nlrha.india_authority import ddm_time_limit_shortfall
    assert _time_limit_text(dict(time_limit=2400.0)) == "2400 s"                            # October
    t = _time_limit_text(dict(time_limit=3840.0, speed_factor=1.6, time_limit_base=2400.0))
    assert t.startswith("3840 s") and "2400 s on the reference machine" in t and "1.6" in t
    assert ddm_time_limit_shortfall(dict(time_limit=2400.0)) is None
    assert ddm_time_limit_shortfall(dict(time_limit=3840.0, speed_factor=1.6, time_limit_base=2400.0)) is None
    # a short budget is a short budget whatever the machine: 2,000 s here is 1,250 s on the owner's PC
    assert "1250 s on the reference machine" in ddm_time_limit_shortfall(dict(time_limit=2000.0, speed_factor=1.6))
    from snl import checkpoint as CK
    assert "SNL_SPEED_FACTOR" in CK.NON_MODEL_ENV                       # not a model knob: no pushover / NLRHA key


# ------------------------------------------------------------------------------------- every input in the keys
def _job(tmp_path, name="job"):
    job = tmp_path / name
    (job / "design").mkdir(parents=True)
    (job / "model_opensees.py").write_text("# model\n")
    (job / "cfg.py").write_text("cfg = {}\n")
    (job / "load_plan.json").write_text('{"cases": []}')
    (job / "design" / "member_schedule.csv").write_text("tag,section\n1,ISMB300\n")
    (job / "design" / "calc_package.json").write_text(json.dumps({"members": [1]}))
    return job


def _keys(tmp_path, job, monkeypatch):
    from nlrha import cli as NC
    from pushover import cli as PC
    from steltic_ddm import cli as DC
    pkg = types.SimpleNamespace(root=str(job))
    rec = dict(id=7, sf=1.2, x_comp="H1", dt=0.01, a1=[0.0, 0.1], a2=[0.0, 0.05])
    nj = (str(job), None, None, None, None, rec, 0.025, 0.01, 2.0, None, "hht", True)
    args = ns(checkpoint_dir=str(tmp_path / "ck"), params=None, max_drift=0.1, stop_at=0.8, tail="auto", member_nseg=4,
              gravity_elastic=None, plasticity="fibre", dirs=["X", "Y"], chunk_seconds=None)
    imp = dict(tag="+X", dir="X", psi=1 / 200.0, bow_sign=1)
    opts = dict(nsub=(2, 2, 4), _checkpoint=dict(dir=str(tmp_path / "dck"), budget_s=None, t0=None))
    return (NC.record_cache_key(pkg, "DBE", nj), PC._journal(args, pkg).key, DC._journal_for(str(job), "1.5DL+1.5LL", imp, opts).key)


def test_every_hr_input_is_in_the_journal_and_cache_keys(tmp_path, monkeypatch):
    """design/*, the load plan, the IS 1893 calculation, the design of record, the NL plans (the unit's and the
    parent folder's) change all three keys; the site hazard changes the NLRHA record key; the DDM's own block in
    design/calc_package.json and its backup change nothing."""
    from snl import checkpoint as CK
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    for k in list(os.environ):
        if k.startswith("SNL_") and k not in CK.NON_MODEL_ENV:
            monkeypatch.delenv(k)
    bld = tmp_path / "bld"; bld.mkdir()
    job = _job(bld, "unit")
    base = _keys(tmp_path, job, monkeypatch)
    assert _keys(tmp_path, job, monkeypatch) == base

    def edit(rel, text):
        p = job / rel
        old = p.read_text() if p.exists() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p, old

    for rel, text in (("load_plan.json", '{"cases": [1]}'), ("seismic_calc.json", '{"Z": 0.24}'),
                      ("design_of_record.json", '{"rev": 2}'), ("design/member_schedule.csv", "tag,section\n1,ISMB350\n"),
                      ("design/cfg_snapshot.json", "{}"), ("design/sub/extra.json", "{}"), ("nl_plan.json", "{}"),
                      ("../nl_plan.json", '{"material": {}}'), ("cfg.py", "cfg = {'a': 1}\n")):
        p, old = edit(rel, text)
        k = _keys(tmp_path, job, monkeypatch)
        assert all(a != b for a, b in zip(k, base)), rel
        p.write_text(old) if old is not None else p.unlink()
        assert _keys(tmp_path, job, monkeypatch) == base, rel
    p, _ = edit("nlrha/site_hazard.json", '{"design": {}}')
    k = _keys(tmp_path, job, monkeypatch)
    assert k[0] != base[0] and k[1:] == base[1:]                            # read by the NLRHA only
    p.unlink()
    cp = job / "design" / "calc_package.json"
    cp.write_text(json.dumps({"members": [1], "ddm_analysis": {"lambda_u": 1.4}}, indent=1))   # the DDM's own write
    (job / "design" / "calc_package.json.pre_ddm.bak").write_text("{}")
    assert _keys(tmp_path, job, monkeypatch) == base
    cp.write_text(json.dumps({"members": [1, 2], "ddm_analysis": {"lambda_u": 1.4}}))          # an HR change in it
    assert all(a != b for a, b in zip(_keys(tmp_path, job, monkeypatch), base))


def test_section_tables_are_in_the_keys(tmp_path, monkeypatch):
    from snl import checkpoint as CK
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    for k in list(os.environ):
        if k.startswith("SNL_") and k not in CK.NON_MODEL_ENV:
            monkeypatch.delenv(k)
    eng = tmp_path / "engine"; eng.mkdir()
    (eng / "is808_shapes.csv").write_text("Label,d\nISMB300,300\n")
    monkeypatch.setenv("STELTIC_ENGINE_DIR", str(eng))
    monkeypatch.setattr(CK, "engine_key", lambda: "the same engine")
    job = _job(tmp_path)
    base = _keys(tmp_path, job, monkeypatch)
    (eng / "is808_shapes.csv").write_text("Label,d\nISMB300,301\n")
    assert all(a != b for a, b in zip(_keys(tmp_path, job, monkeypatch), base))


# ------------------------------------------------------------------------------------------------- peak memory
def test_exec_records_the_peak_memory_of_the_analysis(tmp_path):
    import nl_orchestrate as NO
    import time
    stamp = str(tmp_path / "stamp.json")
    rc = NO.main(["_exec", "--deadline", "%.0f" % (time.time() + 120), "--chunk", "120", "--stamp", stamp, "--",
                  sys.executable, "-c", "b = bytearray(120 * 1024 * 1024); b[::4096] = b'x' * len(b[::4096])"])
    st = json.load(open(stamp))
    assert rc == 0 and st["rc"] == 0 and st["peak_rss_mb"] >= 100 and st["deadline"] > st["slot_start"]


def test_the_chunk_record_and_the_runtime_log_carry_the_peak(tmp_path):
    import nl_orchestrate as NO
    job = tmp_path / "IN_ExM"; job.mkdir()
    q = str(tmp_path / "q.json")
    NO.main(["plan", "--queue", q, "--jobs", str(job), "--analyses", "pushover", "--python", "py", "--heavy", "H"])

    def runner(cmd, **kw):
        json.dump(dict(slot_start=1.0, deadline=7000.0, peak_rss_mb=1234.5), open(NO._opt(cmd, "--stamp"), "w"))
        return 0
    NO.next_steps(ns(queue=q, budget=7000.0, max_steps=0, dry_run=False, stop_on_failure=False), runner=runner)
    d = NO.load(q)
    assert all(s["chunks"][0]["peak_rss_mb"] == 1234.5 for s in d["steps"])
    assert all("peak_rss=1234MB" in x or "peak_rss=1235MB" in x for x in open(q + ".runtime.log").read().splitlines())


# --------------------------------------------------------------------------------------------------- job args
def test_plan_takes_per_job_options(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    monkeypatch.delenv("SNL_SPEED_FACTOR", raising=False)
    a = tmp_path / "IN_Ex19_main"; b = tmp_path / "IN_Ex11"
    a.mkdir(); b.mkdir()
    q = str(tmp_path / "q.json")
    NO.main(["plan", "--queue", q, "--jobs", str(a), str(b), "--python", "py", "--heavy", "H", "--speed-factor", "1.6",
             "--job-args", "IN_Ex19*:pushover=--dirs Y --tail none", "*:ddm=--combos 1.5DL+1.5LL 1.2DL+1.2LL-1.2W_X"])
    d = NO.load(q)
    st = {s["id"]: s for s in d["steps"]}
    p = st["IN_Ex19_main/pushover"]["cmd"]
    assert p.count("--dirs") == 1 and p[p.index("--dirs") + 1:p.index("--dirs") + 2] == ["Y"]
    assert p[p.index("--tail") + 1] == "none" and "--checkpoint-dir" in p and "--plasticity" in p
    assert st["IN_Ex19_main/pushover"]["job_args"] == ["--dirs Y --tail none"]
    q_ = st["IN_Ex11/pushover"]["cmd"]
    assert q_[q_.index("--dirs") + 1:q_.index("--dirs") + 3] == ["X", "Y"] and "--tail" not in q_
    for j in ("IN_Ex19_main", "IN_Ex11"):
        c = st[j + "/ddm"]["cmd"]
        assert c[c.index("--combos") + 1:] == ["1.5DL+1.5LL", "1.2DL+1.2LL-1.2W_X"]
    assert d["env"]["SNL_SPEED_FACTOR"] == "1.6"
    with pytest.raises(SystemExit):
        NO.main(["plan", "--queue", q, "--force", "--jobs", str(a), "--python", "py", "--job-args", "IN_Ex9*:pushover=--dirs Y"])
    with pytest.raises(SystemExit):
        NO.main(["plan", "--queue", q, "--force", "--jobs", str(a), "--python", "py", "--job-args", "IN_Ex19*--dirs Y"])
    assert NO._merge_args(["x", "--a", "1", "2", "--b"], ["--a", "3"]) == ["x", "--b", "--a", "3"]


# --------------------------------------------------------------------------------------- fingerprint + refresh
def _engine(tmp_path, text="# engine 1\n"):
    eng = tmp_path / "engine"; eng.mkdir(exist_ok=True)
    for n in ("static_model.py", "engine3d.py", "india_loads.py", "india_combos.py", "roof_geometry.py"):
        (eng / n).write_text(text + n)
    return eng


class _Runner:
    """A heavy runner without analyses: gravity writes nl_hr_gravity.json with `states`; journaled steps write a
    journal under their checkpoint dir; every step finishes in one chunk."""

    def __init__(self, NO):
        self.NO, self.ran, self.states = NO, [], {"D": 1.0}

    def __call__(self, cmd, **kw):
        NO = self.NO
        json.dump(dict(slot_start=1.0, deadline=7000.0, peak_rss_mb=10.0), open(NO._opt(cmd, "--stamp"), "w"))
        c = cmd[cmd.index("--") + 1:]
        if "snl.hr_gravity" in c:
            job = c[-1]
            json.dump(dict(schema=1, engine_sha="e", states=self.states, engine=kw["env"].get("STELTIC_ENGINE_DIR")),
                      open(os.path.join(job, "nl_hr_gravity.json"), "w"))
            self.ran.append((os.path.basename(job), "gravity"))
            return 0
        if c[-2:-1] == ["report"]:
            self.ran.append((os.path.basename(c[-1]), "report"))
            return 0
        job = c[c.index("run") + 1]
        kind = "pushover" if "pushover" in c[:3] else ("ddm" if "steltic_ddm" in c else "nlrha")
        ck = NO._opt(c, "--checkpoint-dir") or NO._opt(c, "--record-cache")
        os.makedirs(ck, exist_ok=True)
        open(os.path.join(ck, "x.pkl" if kind == "nlrha" else "x.ckpt"), "wb").write(b"")
        self.ran.append((os.path.basename(job), kind))
        return 0


def _done_queue(tmp_path, NO, monkeypatch):
    eng = _engine(tmp_path)
    (tmp_path / "work").mkdir()
    jobs = [_job(tmp_path / "work", n) for n in ("IN_ExA", "IN_ExB")]
    q = str(tmp_path / "q.json")
    NO.main(["plan", "--queue", q, "--jobs", *map(str, jobs), "--python", "py", "--heavy", "H", "--engine", str(eng)])
    run = _Runner(NO)
    args = ns(queue=q, budget=1e6, max_steps=0, dry_run=False, stop_on_failure=False)
    NO.next_steps(args, runner=run)
    d = NO.load(q)
    assert all(s["state"] == "done" and s.get("fingerprint") for s in d["steps"])
    return q, jobs, eng, run, args


def _states(NO, q):
    return {s["id"]: s["state"] for s in NO.load(q)["steps"]}


def test_a_finished_step_keeps_its_input_fingerprint(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    q, jobs, eng, run, args = _done_queue(tmp_path, NO, monkeypatch)
    d = NO.load(q)
    g = next(s for s in d["steps"] if s["id"] == "IN_ExA/gravity")
    p = next(s for s in d["steps"] if s["id"] == "IN_ExA/pushover")
    assert set(g["fingerprint"]) == {"inputs", "engine", "code"} and g["fingerprint"]["engine"]
    assert set(p["fingerprint"]) == {"inputs", "engine", "code", "gravity", "tables"} and p["fingerprint"]["gravity"]
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}


def test_refresh_resets_a_job_whose_hr_inputs_changed(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    q, (a, b), eng, run, args = _done_queue(tmp_path, NO, monkeypatch)
    (a / "design" / "member_schedule.csv").write_text("tag,section\n1,ISMB400\n")
    before = _states(NO, q)
    NO.refresh(ns(queue=q, engine=None, include_code=True, dry_run=True))
    assert _states(NO, q) == before                                        # a dry run changes nothing
    NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False))
    st = _states(NO, q)
    assert all(v == "pending" for k, v in st.items() if k.startswith("IN_ExA/"))
    assert all(v == "done" for k, v in st.items() if k.startswith("IN_ExB/"))
    pa = {s["id"]: s for s in NO.load(q)["steps"]}["IN_ExA/pushover"]
    assert "input files changed" in pa["refresh_reason"] and pa["set_aside"].startswith(str(a / "nl_checkpoints" / "pushover"))
    assert not os.path.exists(a / "nl_checkpoints" / "pushover") and os.path.isdir(pa["set_aside"])
    del run.ran[:]
    NO.next_steps(args, runner=run)
    assert [k for j, k in run.ran if j == "IN_ExA"] == ["gravity", "pushover", "nlrha", "ddm", "report"]
    assert not [x for x in run.ran if x[0] == "IN_ExB"]
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}
    # the DDM's own write into design/calc_package.json is not an input change
    cp = a / "design" / "calc_package.json"
    cp.write_text(json.dumps(dict(json.load(open(cp)), ddm_analysis={"x": 1})))
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}


def test_refresh_after_an_engine_change_rechecks(tmp_path, monkeypatch):
    """Engine only: gravity runs again; the pushover, NLRHA and report are done again without a run when the gravity
    states come out the same; the DDM (it reads the engine's combinations) runs again. With other states the
    pushover and NLRHA run again too."""
    import nl_orchestrate as NO
    q, (a, b), eng, run, args = _done_queue(tmp_path, NO, monkeypatch)
    (eng / "engine3d.py").write_text("# engine 2\n")
    plan_ = NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False))
    st = _states(NO, q)
    for j in ("IN_ExA", "IN_ExB"):
        assert (st[j + "/gravity"], st[j + "/pushover"], st[j + "/nlrha"], st[j + "/ddm"], st[j + "/report"]) == \
            ("pending", "recheck", "recheck", "pending", "recheck"), st
    assert "engine changed" in plan_["IN_ExA/gravity"][1]
    del run.ran[:]
    run.states = {"D": 1.0}                                                 # the same states
    NO.next_steps(ns(queue=q, budget=1e6, max_steps=0, dry_run=False, stop_on_failure=False), runner=run)
    assert sorted(set(k for _, k in run.ran)) == ["ddm", "gravity", "report"]
    st = {s["id"]: s for s in NO.load(q)["steps"]}
    assert st["IN_ExA/pushover"]["state"] == "done" and "unchanged" in st["IN_ExA/pushover"]["recheck_note"]
    assert all(s["state"] == "done" for s in st.values())
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}
    # another engine that changes the gravity states
    (eng / "engine3d.py").write_text("# engine 3\n")
    NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False))
    del run.ran[:]
    run.states = {"D": 1.1}
    NO.next_steps(ns(queue=q, budget=1e6, max_steps=0, dry_run=False, stop_on_failure=False), runner=run)
    assert [k for j, k in run.ran if j == "IN_ExA"] == ["gravity", "pushover", "nlrha", "ddm", "report"]


def test_refresh_reports_a_code_change_and_runs_it_only_when_asked(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    from snl import checkpoint as CK
    q, jobs, eng, run, args = _done_queue(tmp_path, NO, monkeypatch)
    monkeypatch.setattr(CK, "code_key", lambda: "other code")
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}
    d = NO.load(q)
    assert all(s["state"] == "done" for s in d["steps"])
    assert all("analysis code changed" in s["code_changed"] for s in d["steps"])
    NO.refresh(ns(queue=q, engine=None, include_code=True, dry_run=False))
    assert all(v == "pending" for v in _states(NO, q).values())


def test_refresh_resets_a_partly_run_step_on_an_input_change(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    eng = _engine(tmp_path)
    a = _job(tmp_path, "IN_ExP")
    q = str(tmp_path / "q.json")
    NO.main(["plan", "--queue", q, "--jobs", str(a), "--analyses", "pushover", "--python", "py", "--heavy", "H", "--engine", str(eng)])
    run = _Runner(NO)

    def runner(cmd, **kw):
        if "pushover" in cmd and "run" in cmd:
            json.dump(dict(slot_start=1.0, deadline=7000.0), open(NO._opt(cmd, "--stamp"), "w"))
            return 75
        return run(cmd, **kw)
    NO.next_steps(ns(queue=q, budget=1e6, max_steps=0, dry_run=False, stop_on_failure=False), runner=runner)
    s = {x["id"]: x for x in NO.load(q)["steps"]}["IN_ExP/pushover"]
    assert s["state"] == "resume" and s["started_fingerprint"]["inputs"]
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}
    (a / "load_plan.json").write_text('{"cases": [2]}')
    NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False))
    s = {x["id"]: x for x in NO.load(q)["steps"]}["IN_ExP/pushover"]
    assert s["state"] == "pending" and "started_fingerprint" not in s
    assert NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False)) == {}     # not reset twice


# -------------------------------------------------------------------------------------------------------- sync
def _tree(root, files):
    for rel, text in files.items():
        p = os.path.join(str(root), rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(text)


def _snapshot(root):
    out = {}
    for r, ds, fs in os.walk(str(root)):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, str(root))] = open(p, "rb").read()
    return out


def test_sync_brings_the_hr_files_and_leaves_the_nl_outputs(tmp_path):
    import nl_orchestrate as NO
    gold, work = tmp_path / "gold", tmp_path / "work"
    _tree(gold, {"IN_ExS/cfg.py": "cfg = 2\n", "IN_ExS/model_opensees.py": "# m\n",
                 "IN_ExS/design/calc_package.json": json.dumps({"members": [1]}),
                 "IN_ExS/design/member_schedule.csv": "new\n", "IN_ExS/units/stem/cfg.py": "u = 2\n",
                 "IN_ExS/__pycache__/x.pyc": "", "IN_ExN/cfg.py": "n\n"})
    _tree(work, {"IN_ExS/cfg.py": "cfg = 1\n", "IN_ExS/model_opensees.py": "# m\n", "IN_ExS/old_hr.json": "{}",
                 "IN_ExS/design/calc_package.json": json.dumps({"members": [1], "ddm_analysis": {"l": 1}}),
                 "IN_ExS/design/calc_package.json.pre_ddm.bak": "{}", "IN_ExS/design/member_schedule.csv": "old\n",
                 "IN_ExS/units/stem/cfg.py": "u = 1\n", "IN_ExS/units/stem/pushover/r.json": "nl",
                 "IN_ExS/pushover/pushover_package.json": "nl", "IN_ExS/nl_hr_gravity.json": "nl",
                 "IN_ExS/ddm_results.json": "nl", "IN_ExS/hinge_params_collected.json": "nl", "IN_ExS/nl_plan.json": "nl",
                 "IN_ExS/nl_checkpoints/ddm/a.ckpt": "nl", "IN_ExS/nl_orchestrate_ddm.log": "nl",
                 "IN_ExS/.nl_orchestrate_ddm.stamp": "nl", "IN_ExW/cfg.py": "work only\n",
                 "IN_ExS/pushover_before/pushover_package.json": "nl, a name sync does not know",
                 "IN_ExS/regress_pushover.log": "nl, a name sync does not know"})
    gold0 = _snapshot(gold)
    nl = {k: v for k, v in _snapshot(work).items() if NO._is_nl(k)}
    s = NO.sync(ns(src=str(gold), dst=str(work), jobs=[], dry_run=True))
    assert _snapshot(gold) == gold0 and sorted(s["IN_ExS"]["changed"]) == ["cfg.py", "design/member_schedule.csv",
                                                                          "units/stem/cfg.py"]
    assert not os.path.exists(work / "IN_ExN")                                  # a dry run copies nothing
    s = NO.sync(ns(src=str(gold), dst=str(work), jobs=[], dry_run=False))
    w = _snapshot(work)
    assert _snapshot(gold) == gold0                                             # the gold is only read
    assert w["IN_ExS/cfg.py"] == b"cfg = 2\n" and w["IN_ExS/units/stem/cfg.py"] == b"u = 2\n"
    assert w["IN_ExS/design/member_schedule.csv"] == b"new\n"
    # nothing is removed without an earlier sync record: old_hr.json and the unknown NL files stay
    assert s["IN_ExS"]["removed"] == [] and w["IN_ExS/old_hr.json"] == b"{}"
    assert w["IN_ExS/pushover_before/pushover_package.json"] and w["IN_ExS/regress_pushover.log"]
    assert all(w[k] == v for k, v in nl.items())                                # NL outputs untouched
    assert "ddm_analysis" in json.loads(w["IN_ExS/design/calc_package.json"])   # the same HR content: kept as it is
    assert "IN_ExS/design/calc_package.json.pre_ddm.bak" in w
    assert "IN_ExS/__pycache__/x.pyc" not in w and w["IN_ExN/cfg.py"] == b"n\n" and w["IN_ExW/cfg.py"] == b"work only\n"
    m = json.load(open(work / "IN_ExS" / ".nl_sync.json"))
    assert m["source"] == str(gold / "IN_ExS") and m["inputs"] and "design/member_schedule.csv" in m["files"]
    # an HR file the gold drops after a sync is removed; files the sync never brought in stay
    os.remove(gold / "IN_ExS" / "design" / "member_schedule.csv")
    s = NO.sync(ns(src=str(gold), dst=str(work), jobs=["IN_ExS"], dry_run=False))
    w = _snapshot(work)
    assert s["IN_ExS"]["removed"] == ["design/member_schedule.csv"] and "IN_ExS/design/member_schedule.csv" not in w
    assert w["IN_ExS/old_hr.json"] == b"{}" and w["IN_ExS/regress_pushover.log"]
    # the HR calc package changes: the gold's copy comes in, the DDM block and its stale backup go
    _tree(gold, {"IN_ExS/design/calc_package.json": json.dumps({"members": [1, 2]})})
    s = NO.sync(ns(src=str(gold), dst=str(work), jobs=["IN_ExS"], dry_run=False))
    w = _snapshot(work)
    assert json.loads(w["IN_ExS/design/calc_package.json"]) == {"members": [1, 2]}
    assert "IN_ExS/design/calc_package.json.pre_ddm.bak" not in w
    assert s["IN_ExS"]["removed"] == ["design/calc_package.json.pre_ddm.bak"]
    assert NO.sync(ns(src=str(gold), dst=str(work), jobs=["IN_ExS"], dry_run=False))["IN_ExS"] == dict(added=[], changed=[], removed=[])
    with pytest.raises(SystemExit):
        NO.sync(ns(src=str(gold), dst=str(gold / "IN_ExS"), jobs=[], dry_run=False))
    with pytest.raises(SystemExit):
        NO.sync(ns(src=str(gold), dst=str(work), jobs=["IN_ExZ"], dry_run=False))


def test_sync_then_refresh_finds_the_stale_steps(tmp_path, monkeypatch):
    import nl_orchestrate as NO
    q, (a, b), eng, run, args = _done_queue(tmp_path, NO, monkeypatch)
    gold = tmp_path / "gold"
    for j in (a, b):
        for rel in ("model_opensees.py", "cfg.py", "load_plan.json", "design/member_schedule.csv", "design/calc_package.json"):
            _tree(gold, {"%s/%s" % (j.name, rel): open(os.path.join(str(j), rel)).read()})
    _tree(gold, {"IN_ExB/load_plan.json": '{"cases": ["revised"]}'})
    NO.sync(ns(src=str(gold), dst=str(tmp_path / "work"), jobs=["IN_ExA", "IN_ExB"], dry_run=False))
    NO.refresh(ns(queue=q, engine=None, include_code=False, dry_run=False))
    st = _states(NO, q)
    assert all(v == "done" for k, v in st.items() if k.startswith("IN_ExA/"))
    assert all(v == "pending" for k, v in st.items() if k.startswith("IN_ExB/"))
