"""2026-10 first wave (review E_NL): DDM runaway sweeps (NL-36), the IS 875-2 3.2.1 column imposed-load reduction in
the B-1.2 check (NL-37), out-of-plane restraints of rolled-section sheds (NL-38), and the presentation fixes (the
four-analyses header, pushover stop messages in mm, the site index builder, README counts).

Pure tests run everywhere. Package tests use the HR gold jobs (STELTIC_GOLD_JOBS, default /home/claude/gold/jobs_hr)
and the published NL gold set (STELTIC_NL_GOLD, default /home/claude/work/golds/nl_1004; matched on the title part of
the run id, so either numbering works) with STELTIC_ENGINE_DIR, and skip without them."""
import contextlib
import copy
import glob
import io
import json
import math
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")
NL_GOLD = os.environ.get("STELTIC_NL_GOLD", "/home/claude/work/golds/nl_1004")
ENGINE = os.environ.get("STELTIC_ENGINE_DIR", "")


def _job(root, pattern, engine=True):
    hits = sorted(glob.glob(os.path.join(root, pattern)))
    if not hits or (engine and not ENGINE):
        pytest.skip("gold job %s or STELTIC_ENGINE_DIR not available" % pattern)
    return hits[0]


def _load(job):
    from steltic_ddm import ingest
    with contextlib.redirect_stdout(io.StringIO()):
        nm = ingest.load_package(job, ENGINE)
    return nm, nm.cfg


def _stored(pattern):
    job = _job(NL_GOLD, pattern, engine=False)
    p = os.path.join(job, "ddm_results.json")
    if not os.path.exists(p):
        pytest.skip("no ddm_results.json in %s" % job)
    return json.load(open(p))


# =============================================================================================== NL-36 runaway sweeps
def test_runaway_check_bounds():
    from steltic_ddm.solver import runaway_check
    assert runaway_check(1.2, 1.17, drift=0.02, strain=35.0) is None
    assert "10" in runaway_check(5576.2, 0.71)["criterion"]                       # IN_Ex9
    assert runaway_check(-78891.6, 0.721)["criterion"].startswith("|lambda|")      # negative runaway
    assert "jumped" in runaway_check(3.2, 0.79)["criterion"]                       # a one-step jump below 10
    assert "drift" in runaway_check(1.668, 1.666, drift=16.1)["criterion"]         # IN_Ex18 1 615 %
    assert "strain" in runaway_check(0.79, 0.78, drift=0.01, strain=6.5e6)["criterion"]
    assert runaway_check(1.0, 0.95, drift=0.09, strain=999.0) is None              # inside every bound
    assert runaway_check(float("nan"), 0.5) is not None


def test_limit_status_runaway_is_solver_failure_unless_confirmed_before():
    from steltic_ddm.solver import limit_status, RUNAWAY_TERM
    rising = [(0.05 * i, i) for i in range(1, 16)]
    assert limit_status(rising, 14, 0.75, termination=RUNAWAY_TERM)[0] == "SOLVER_FAILURE"
    # a strain-capped or nearly flat curve is still a numerical failure when the run ended in a runaway
    assert limit_status(rising, 14, 0.75, capped=True, termination=RUNAWAY_TERM)[0] == "SOLVER_FAILURE"
    assert limit_status(rising, 14, 0.75, termination=RUNAWAY_TERM, tangent_ratio=0.01)[0] == "SOLVER_FAILURE"
    # >= 2 converged descending steps BEFORE the (discarded) runaway: the limit point stands
    peak = [(0.1, 1), (0.5, 2), (0.766, 3), (0.751, 4), (0.721, 5)]
    assert limit_status(peak, 2, 0.766, termination=RUNAWAY_TERM)[0] == "LIMIT_POINT"


def _stored_run(label, hist, status="DUCTILITY_CAP", b12=None, drifts=None, ratio=30.0):
    return dict(label=label, kind="seismic", status=status, termination="ductility_cap",
                lambda_u=max(l for l, _ in hist), lambda_end=max(l for l, _ in hist), hist=[list(x) for x in hist],
                check=[None, "INFO"], b12=b12, snapshot=dict(drifts=drifts), state={"roof|X": dict(ratio=ratio)})


def test_reclassify_stored_run_synthetic():
    from steltic_ddm.cli import reclassify_stored_run
    # IN_Ex9 1.2DL+1.2LL+1.2SL-1.2EQ_Z+0.36EQ_X: the runaway step came after a descent -> LIMIT_POINT 0.791, and the
    # B-1.2 row (forces of the runaway state scaled by 1 / 5 576) is replaced by "lambda = 1 not reached"
    h = [(0.05, 0.1), (0.4, 0.4), (0.782, 0.84), (0.791, 0.9), (0.785, 0.95), (0.716, 1.0), (0.71, 1.015), (5576.2, 1.03)]
    b = dict(combo="x", ok=False, reached_lambda_1=True, lambda_basis=dict(target=1.0, lower=None, upper=5576.2),
             groups=[dict(role="brace", section="WPB140X140X24.66", dc_max=2.559, dc_shear_max=0.0)], quote="q")
    r = _stored_run("x", h, b12=b)
    assert reclassify_stored_run(r)
    assert r["status"] == "LIMIT_POINT" and r["lambda_u"] == pytest.approx(0.791) and len(r["hist"]) == 7
    assert r["b12"]["ok"] is False and not r["b12"]["groups"] and "not reached" in r["b12"]["note"]
    # rising to the runaway (IN_Ex9 0.9DL+1.5W_Y; IN_Ex18 1.2DL+1.2LL-1.2W_X): SOLVER_FAILURE, lambda_u None; a B-1.2
    # check taken at lambda = 1 BEFORE the runaway stays valid
    h2 = [(0.5, 10.0), (1.02, 40.0), (1.577, 116.0), (1.666, 123.9), (1.668, 124.0), (-731.6, 124.1)]
    b2 = dict(combo="y", ok=True, reached_lambda_1=True, lambda_basis=dict(target=1.0, lower=0.5, upper=1.02), groups=[])
    r2 = _stored_run("y", h2, b12=b2)
    assert reclassify_stored_run(r2)
    assert r2["status"] == "SOLVER_FAILURE" and r2["lambda_u"] is None and r2["lambda_end"] == pytest.approx(1.668)
    assert r2["b12"]["ok"] is True and r2["runaway"]["criterion"]
    assert reclassify_stored_run(r2) is None                                      # idempotent
    # a plausible run is left alone
    r3 = _stored_run("z", [(0.05 * i, i) for i in range(1, 30)])
    before = copy.deepcopy(r3)
    assert reclassify_stored_run(r3) is None and r3 == before
    # a stored peak snapshot 16 x storey heights out (IN_Ex18: 1 615 %) with a plausible curve
    r4 = _stored_run("w", [(0.05 * i, i) for i in range(1, 30)], drifts=[[1.0], [16.15]])
    assert reclassify_stored_run(r4) and r4["status"] == "SOLVER_FAILURE"


def test_b12_not_evaluated_for_a_numerical_stop_and_the_summary():
    from steltic_ddm.india_checks import b12_check
    from steltic_ddm.cli import b12_summary
    nr = b12_check(None, None, 0.7, "c", status="SOLVER_FAILURE")
    assert nr["ok"] is None and nr["evaluated"] is False
    assert b12_check(None, None, 0.7, "c", status="LIMIT_POINT")["ok"] is False      # a structural limit below 1
    ok = dict(combo="a", ok=True, quote="q")
    bad = dict(combo="b", ok=False, quote="q")
    assert b12_summary([ok])["ok"] is True
    assert b12_summary([ok, dict(nr, quote="q")])["ok"] is None                     # incomplete, not a shortfall
    assert b12_summary([ok, dict(nr, quote="q"), bad])["ok"] is False
    assert b12_summary([ok, dict(nr, quote="q")])["n_not_evaluated"] == 1


def test_published_runaways_ex9_ex18_are_read_as_solver_failures():
    """The published 2026-09 results through the guard: IN_Ex9 lambda 5 576 / 106 901 / 1 402 093 and the B-1.2
    2.559 on the brace; IN_Ex18 the 1 615 % drift row."""
    from steltic_ddm.cli import reclassify_stored_run
    d = _stored("*Gable_warehouse_SMF_SCBF_snow_Shimla")
    by = {r["label"]: r for r in d["runs"]}
    for lab in ("1.2DL+1.2LL+1.2SL-1.2EQ_Z+0.36EQ_X", "1.2DL+1.2LL+1.2SL-1.2EQ_Z-0.36EQ_X", "0.9DL+1.5W_Y"):
        r = by[lab]
        assert r["lambda_end"] > 1000
        assert reclassify_stored_run(r)
        assert r["lambda_end"] < 10 and (r["lambda_u"] is None or r["lambda_u"] < 10)
        assert not any(g.get("dc_max", 0) > 2 for g in (r.get("b12") or {}).get("groups") or [])
    # rising into the runaway: SOLVER_FAILURE; a descent of >= 2 converged steps before it: the limit point stands
    assert by["1.2DL+1.2LL+1.2SL-1.2EQ_Z-0.36EQ_X"]["status"] == "SOLVER_FAILURE"
    assert by["0.9DL+1.5W_Y"]["status"] == "LIMIT_POINT" and by["0.9DL+1.5W_Y"]["lambda_u"] == pytest.approx(2.738, abs=1e-3)
    b = by["1.2DL+1.2LL+1.2SL-1.2EQ_Z+0.36EQ_X"]["b12"]                  # the 2.559 brace row came from the runaway
    assert b["ok"] is False and not b["groups"] and "not reached" in b["note"]
    e18 = _stored("*SMF_podium_11levels_Kochi")
    r = [x for x in e18["runs"] if x["label"] == "1.2DL+1.2LL-1.2W_X"][0]
    assert reclassify_stored_run(r) and r["status"] == "SOLVER_FAILURE" and r["lambda_u"] is None


def test_gate_states_solver_failures(tmp_path, monkeypatch):
    from nlrha import india_authority as IA
    runs = [dict(label="0.9DL+1.5W_Y", kind="wind", status="SOLVER_FAILURE", termination="runaway", lambda_end=2.6,
                 runaway=dict(criterion="|lambda| 1.4e+06 > 10"), phi={"cls": "W", "phi_s": 0.85})]
    (tmp_path / "ddm_results.json").write_text(json.dumps(dict(runs=runs, gravity_gate=dict(ok=True),
                                                               b12_check=dict(ok=None, n_not_evaluated=1, not_evaluated=["0.9DL+1.5W_Y"]),
                                                               options={})))
    art = IA.artefact_gate(str(tmp_path))
    assert any("numerical runaway" in r for r in art["reasons"])
    assert any("B-1.2 section check not evaluated" in r for r in art["reasons"])
    assert art["checks"]["ddm_solver_failures"] == 1 and art["checks"]["ddm_runaway_steps"] == 1
    # never COMPLETE silently: with everything else passing, disclosed (NL-31) stops name themselves in the status
    monkeypatch.setattr(IA, "complete_allowed", lambda *a, **k: (True, []))
    monkeypatch.setattr(IA, "artefact_gate", lambda job: dict(ok=True, reasons=[], checks={"ddm_solver_failures": 1},
                                                             capacity_shortfall=False))
    assert IA.design_status(job_dir=str(tmp_path))["status"] == "complete_with_solver_stops"
    monkeypatch.setattr(IA, "artefact_gate", lambda job: dict(ok=True, reasons=[], checks={"ddm_solver_failures": 0},
                                                             capacity_shortfall=False))
    assert IA.design_status(job_dir=str(tmp_path))["status"] == "complete"


def test_report_states_runaway(tmp_path):
    from steltic_ddm import report_ddm
    res = dict(lambda_u=None, lambda_end=0.71, status="SOLVER_FAILURE", termination="runaway",
               runaway=dict(criterion="|lambda| 5576 > 10"))
    assert "numerical runaway" in report_ddm._lam(res) and "not a capacity" in report_ddm._lam(res)
    runs = [dict(combo=("c",), imp="+X", res=res)]
    html_ = report_ddm._solver_failure_html(runs)
    assert "Solver failures: 1 sweep stopped numerically" in html_ and "5576" in html_
    assert "Solver failures: none" in report_ddm._solver_failure_html([dict(combo=("c",), imp="+X", res=dict(status="LIMIT_POINT"))])


def test_sweep_discards_a_runaway_step(monkeypatch, tmp_path):
    """A real sweep (IN_Ex12 unitC gym, 1.5DL+1.5LL) with the drift measure forced past 10 % at its 6th converged
    step: the step is not recorded, the sweep stops as SOLVER_FAILURE with the runaway recorded, and no capacity."""
    from steltic_ddm import loads, solver
    from steltic_ddm.model_gmnia import GMNIAModel
    src = _job(GOLD, "IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitC_gym")
    job = str(tmp_path / "gym")
    shutil.copytree(src, job)
    nm, cfg = _load(job)
    c = [x for x in loads.steltic_combos(cfg, nm=nm) if x[0] == "1.5DL+1.5LL"][0]
    calls = {"n": 0}
    real = solver.max_drift_ratio

    def fake(model):
        calls["n"] += 1
        return 0.5 if calls["n"] == 6 else real(model)
    monkeypatch.setattr(solver, "max_drift_ratio", fake)
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 4), residual="none", out_of_plumb=("X", 1 / 200.0), bow=1 / 1000.0)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        res = solver.sweep(g, c, loads.present_sets(nm), dlam=0.05, max_steps=40, verbose=False, strain_cap=20.0,
                           capture_lambda1=True)
    assert res["status"] == "SOLVER_FAILURE" and res["termination"] == "runaway" and res["lambda_u"] is None
    assert res["runaway"]["step"] == 6 and "drift" in res["runaway"]["criterion"]
    assert len(res["hist"]) == 6                                   # the probe + 5 recorded steps; step 6 discarded
    assert res["lambda_end"] < 0.5 and res["forces_at_1"] is None


# ============================================================================== NL-37 IS 875-2 3.2.1 in the B-1.2 check
def test_eq_case_rule_matches_the_hr_engine():
    from steltic_ddm import imposed_reduction as IR
    assert IR.is_eq_case({"kind": "EQ"}) and IR.is_eq_case({"lateral_kind": "eq"})
    assert IR.is_eq_case({"kind": "G", "tags": ["col_only"]}) and IR.is_eq_case({"tags": ["is18168_5_5"]})
    assert not IR.is_eq_case({"kind": "W"}) and not IR.is_eq_case(None)
    assert IR.applies(1.5, {"kind": "W"}) and not IR.applies(0.0, None) and not IR.applies(1.2, {"kind": "EQ"})


def test_reduce_forces_like_the_hr_record():
    from steltic_ddm import imposed_reduction as IR
    plan = dict(columns={7: dict(r=0.5, N_LL_N=800e3), 8: dict(r=0.1, N_LL_N=100e3)})
    f = {7: dict(kind="col", role="gravity_col", section="BOX400X400X28", N_comp=9193e3, N_abs=9193e3, N_top=9150e3,
                 M_major=1e6, M_minor=0.0, V=0.0),
         8: dict(kind="col", role="gravity_col", section="X", N_comp=0.0, N_abs=50e3, M_major=0, M_minor=0, V=0),
         9: dict(kind="beam", role="floor", section="Y", N_comp=10e3, N_abs=10e3, M_major=5e8, M_minor=0, V=1e5),
         "_lambda": dict(target=1.0)}
    g = IR.reduce_forces(f, plan, 1.5, {"kind": None})
    assert g[7]["N_comp"] == pytest.approx(9193e3 - 1.5 * 0.5 * 800e3) and g[7]["N_abs"] == g[7]["N_comp"]
    assert g[7]["N_reduction_N"] == pytest.approx(600e3) and g[7]["N_top"] == pytest.approx(9150e3 - 600e3)
    assert g[8] is f[8] and g[9] is f[9] and g["_lambda"] == f["_lambda"]       # tension column, beam: unchanged
    assert g["_imposed_reduction"]["n_columns"] == 1 and f[7]["N_comp"] == 9193e3   # a copy
    assert IR.reduce_forces(f, plan, 1.2, {"kind": "EQ"}) is f                    # IS 875-5 8.1: never with EQ
    assert IR.reduce_forces(f, None, 1.5, None) is f


def test_b12_reports_the_reduction():
    from steltic_ddm import imposed_reduction as IR
    from steltic_ddm.india_checks import b12_check
    plan = dict(columns={7: dict(r=0.5, N_LL_N=800e3)})
    f = {7: dict(kind="col", role="gravity_col", section="WPB400X400X191.11", N_comp=6000e3, N_abs=6000e3, M_major=0.0,
                 M_minor=0.0, V=0.0), "_lambda": dict(target=1.0, lower=0.98, upper=1.02)}
    b = b12_check(IR.reduce_forces(f, plan, 1.5, {}), lambda s, k=None: 250.0, 1.2, "1.5DL+1.5LL")
    g = b["groups"][0]
    assert g["N_kN"] == pytest.approx(5400.0) and g["N_reduction_kN"] == pytest.approx(600.0)
    assert b["imposed_reduction"]["n_columns"] == 1


def test_report_line_states_the_basis():
    from steltic_ddm import imposed_reduction as IR
    on = IR.report_line(dict(columns={1: {}}, n_columns=231, r_values=[0.1, 0.2, 0.3, 0.4, 0.5]))
    assert "3.2.1" in on and "B-1.2" in on and "231 columns" in on and "earthquake" in on and "unreduced" in on
    assert "unreduced" in IR.report_line(None, {}).lower()


def test_ex19_reduction_plan_from_the_hr_engine(tmp_path):
    """IN_Ex19: r per column from the HR engine (0.1 ... 0.5 over 11 floors carried) and N_LL > 0 on the columns."""
    from steltic_ddm import imposed_reduction as IR
    src = _job(GOLD, "IN_Ex19_EBF_12levels_Tplan_Guwahati")
    job = str(tmp_path / "ex19")
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("units", "rag", "figs", "*.html"))
    nm, cfg = _load(job)
    with contextlib.redirect_stdout(io.StringIO()):
        plan = IR.build_plan(nm, cfg)
    assert plan and plan["n_columns"] > 100 and plan["r_values"][-1] == 0.5 and 0.1 in plan["r_values"]
    assert all(c["N_LL_N"] > 0 for c in plan["columns"].values())


# ================================================================================ NL-38 rolled-section shed restraints
def test_rolled_spacings_and_brief_fallback():
    from steltic_ddm import peb_restraints as PR
    cfg = dict(LLT_hog_mm={"roof": 3000.0}, LLT_sag_mm={"roof": 1500.0},
               secondary_members=[dict(id="wall girt", spacing_mm=1500.0)])
    sp, src, fb = PR.rolled_spacings(cfg)
    assert sp == dict(fly=3000.0, purlin=1500.0, girt=1500.0) and not fb and "LLT_hog_mm" in src["fly"]
    sp, src, fb = PR.rolled_spacings({}, "IN_Ex8_SMF_portal_Chennai_wind")
    assert sp["fly"] == 3000.0 and set(fb) == {"fly", "purlin", "girt"} and "brief" in src["fly"]
    # slope positions: 3 m along a 14.04 deg slope from the eave, last gap at the ridge shorter
    pos = PR._side_positions(12000.0, 24000.0, 3000.0, 3000.0)
    assert len(pos) == 4 and pos[0] == pytest.approx(12000 + 3000 * 12000 / math.hypot(12000, 3000))


def test_rolled_plan_ex9():
    from steltic_ddm import peb_restraints as PR
    nm, cfg = _load(_job(GOLD, "IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla"))
    p = PR.plan(nm, cfg)
    assert p and p["source"] == "rolled" and not p["skipped"]
    c = p["counts"]
    # 9 rafter lines x (4 + 4 fly braces + the apex tie); fly braces torsional, purlins not modelled
    assert c["rafter_torsion"] == 72 and c["rafter_lateral"] == 81 and c["not_modelled_one_flange"] > 0
    raf = [s for s in p["stations"] if s["member_kind"] == "rafter" and "torsion" in s["kinds"]]
    assert all(s["dir"] == 2 for s in raf)                                   # portals in X: out of plane = Y
    assert {round(s["at_mm"]) for s in raf} >= {14910, 17821, 30179, 33090}  # 3 m along the slope from each eave
    cols = [s for s in p["stations"] if s["member_kind"] == "column"]
    assert cols and all(s["kinds"] == ["lateral"] for s in cols)            # lateral only (HR column LTB: element L)
    assert {round(s["at_mm"]) for s in cols} >= {3000, 6000, 1875}           # Ky 0.375 x 8 m / x 5 m
    assert p["basis"]["spacings_mm"] == dict(fly=3000.0, purlin=1500.0, girt=1500.0)
    assert "Rolled-section restraints (from the HR design input" in PR.summary(p)    # check fixes: no ticket id


def test_no_rolled_plan_without_sloped_rafters_or_restrained_columns():
    from steltic_ddm import peb_restraints as PR
    for pat in ("IN_Ex19_EBF_12levels_Tplan_Guwahati", "IN_Ex8_SMF_portal_Chennai_wind", "IN_Ex6_OMRF_warehouse_mezzanine_Hyderabad"):
        nm, cfg = _load(_job(GOLD, pat))
        assert PR.plan(nm, cfg) is None, pat
    nm, cfg = _load(_job(GOLD, "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore"))
    p = PR.plan(nm, cfg)                                                    # girts at Ky x L = 2.375 m on the SCBF columns
    assert p["source"] == "rolled" and p["counts"]["rafter_lateral"] == 0 and p["counts"]["column_lateral"] > 0


def test_rolled_gmnia_is_not_a_mechanism_and_keeps_the_hr_periods():
    """The stud of a column element standing on a roof / floor node is held vertically at its foot: an elastic
    eigen solve (ARPACK) of the restrained Ex9 GMNIA returns its periods within 5 % of the HR model's."""
    from steltic_ddm import transfer_gate as TG
    from steltic_ddm.model_gmnia import GMNIAModel
    nm, cfg = _load(_job(GOLD, "IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla"))
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 2), elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0, brace_bow=0.0)
    with contextlib.redirect_stdout(io.StringIO()):
        g.build(with_mass=True)
        import openseespy.opensees as ops
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        w2 = ops.eigen("-genBandArpack", 3)
    assert len(w2) == 3 and all(w > 0 for w in w2)
    assert g.peb_made["missing"] == 0 and g.peb_made["studs"] == 27
    T = [2 * math.pi / math.sqrt(w) for w in w2]
    assert T[0] == pytest.approx(0.329, rel=0.05)


def test_rolled_ex9_snow_gravity_carries_the_factored_load(tmp_path):
    """IN_Ex9 1.5DL+1.5LL+1.5SL: lambda 0.614 (rafters free out of plane, 2026-09) -> above 1 with the restraints, and
    the B-1.2 check at lambda = 1 satisfied with a small minor-axis moment in the roof NPB600."""
    from steltic_ddm import loads, solver
    from steltic_ddm.model_gmnia import GMNIAModel
    from steltic_ddm.cli import _india_fy_fn
    from steltic_ddm.india_checks import b12_check
    src = _job(GOLD, "IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla")
    job = str(tmp_path / "ex9")
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("rag", "figs", "*.html"))
    nm, cfg = _load(job)
    c = [x for x in loads.steltic_combos(cfg, nm=nm) if x[0] == "1.5DL+1.5LL+1.5SL"][0]
    fy = _india_fy_fn(job)
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 4), out_of_plumb=("Y", 1 / 200.0), bow=1 / 1000.0, fy_fn=fy, bow_hollow=1 / 500.0)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        res = solver.sweep(g, c, loads.present_sets(nm), dlam=0.05, max_steps=250, verbose=False, time_limit=900,
                           strain_cap=20.0, capture_lambda1=True)
    assert res["lambda_u"] is not None and res["lambda_u"] > 1.2
    b = b12_check(res["forces_at_1"], fy, res["lambda_end"], c[0], status=res["status"])
    assert b["ok"] is True
    roof = [x for x in b["groups"] if x["role"] == "roof" and x["section"].startswith("NPB600")][0]
    assert roof["dc_max"] < 0.85 and roof["M_minor_kNm"] < 10.0


def test_rolled_i_warping_term():
    import openseespy.opensees as ops
    from steltic_ddm.sections_fiber import FiberSectionBuilder, shape
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    b = FiberSectionBuilder(ops, Fy=250.0, residual="none", units="N-mm")
    p0 = b.build(1, "NPB600X220X154.47", "beam", axis="z")
    p1 = b.build(2, "NPB600X220X154.47", "beam", axis="z", warping_length=3000.0)
    r = shape("NPB600X220X154.47", prefer_is808=True)
    J = float(r["J"]) * 25.4 ** 4
    Cw = float(r["Cw"]) * 25.4 ** 6
    assert "GJ" not in p0
    assert p1["GJ"] == pytest.approx(b.G * J + math.pi ** 2 * b.E * Cw / 3000.0 ** 2, rel=1e-9)
    assert p1["GJ"] > 3 * b.G * J                                          # warping dominates over a 3 m fork length


# ============================================================================================== presentation (fix 4)
def test_four_analyses_header_reads_load_plan(tmp_path):
    from snl.compare import design_basis, design_header
    (tmp_path / "load_plan.json").write_text(json.dumps({"seismic_summary": dict(
        W_kN=956.121, R=3.0, R_x=4.0, R_y=3.0, VB_x_kN=29.879, VB_y_kN=39.838, VB_kN=39.838, Z=0.1, I=1.0)}))
    b = design_basis(str(tmp_path))
    assert design_header(b) == "design VB 29.9 / 39.8 kN (X / Y), W 956 kN, R 4 / 3 (X / Y)"
    assert "load_plan.json seismic_summary" in b["sources"]
    (tmp_path / "load_plan.json").write_text(json.dumps({"seismic_summary": dict(W_kN=58911.0, R=5.0, R_x=5.0, R_y=5.0,
                                                                                 VB_x_kN=6362.4, VB_y_kN=4024.6)}))
    assert design_header(design_basis(str(tmp_path))) == "design VB 6,362 / 4,025 kN (X / Y), W 58,911 kN, R 5"
    assert "not recorded" in design_header(design_basis(str(tmp_path / "nowhere")))


def test_pushover_stop_messages_in_mm():
    from pushover.report_india import stop_reason_mm
    assert stop_reason_mm("solver non-convergence at roof u=1.84 in (after 9 step halvings)") == \
        "solver non-convergence at roof u = 47 mm (after 9 step halvings)"
    s = stop_reason_mm("descending branch captured: V = 79% of Vmax at u=17.27 in (past 2 x the target estimate)")
    assert "u = 439 mm" in s and " in " not in s.replace("in (", "(")
    assert stop_reason_mm(None) is None and stop_reason_mm("reached max roof drift 8.0% of H") == "reached max roof drift 8.0% of H"


def test_margins_round_down():
    from snl.compare import floor3
    assert floor3(0.9997) == 0.999 and floor3(0.997) == 0.997 and floor3(1.0) == 1.0 and floor3(None) is None


def _mini_run(root, rid, phi=0.9975, lam=1.2468, status="PLASTIC_PLATEAU", sf=None):
    j = os.path.join(root, rid)
    os.makedirs(os.path.join(j, "pushover"), exist_ok=True)
    for lv in ("DBE", "MCE"):
        os.makedirs(os.path.join(j, "nlrha", lv), exist_ok=True)
        sel = [dict(sf=0.2 * (k + 1) * (2 if lv == "MCE" else 1)) for k in range(11)]
        json.dump(dict(response_summary=dict(n_records=11, n_converged=11 if lv == "DBE" else 10),
                       ground_motions=dict(selected=sel, sets=[])), open(os.path.join(j, "nlrha", lv, "nlrha_package.json"), "w"))
    json.dump(dict(gm_basis=dict(record_library="FEMA P-695 far-field set (22 pairs; PEER NGA) - record library"),
                   levels={lv: dict(package="%s/nlrha_package.json" % lv, n_records=11, n_converged=11,
                                    max_mean_drift=0.0026 * (2 if lv == "MCE" else 1)) for lv in ("DBE", "MCE")}),
              open(os.path.join(j, "nlrha", "nlrha_package.json"), "w"))
    json.dump(dict(directions={d: dict(capacity=dict(Vmax_over_VB=58.44, Vmax_over_W=3.5012, tail_status="captured"),
                                       stop_reason="descending branch captured: V = 79% of Vmax at u=17.27 in",
                                       nsp={"IS-MCE": dict(reached_target=(d == "X"))}) for d in ("X", "Y")}),
              open(os.path.join(j, "pushover", "pushover_package.json"), "w"))
    runs = [dict(label="1.5DL+1.5LL", kind="gravity", status=status, lambda_u=lam, lambda_end=lam, check=[phi, "INFO"],
                 hist=[[0.05 * k, k] for k in range(1, int(lam / 0.05) + 1)] + [[lam, 99]], state={})]
    if sf:
        runs.append(dict(label="0.9DL+1.5W_Y", kind="wind", status="SOLVER_FAILURE", termination="runaway", lambda_u=None,
                         lambda_end=2.6, check=[None, "NO_LIMIT_POINT"], hist=[[0.05 * k, k] for k in range(1, 53)], state={},
                         runaway=dict(criterion="x")))
    json.dump(dict(runs=runs, options=dict(dlam=0.05),
                   b12_check=dict(ok=True, combos=[dict(combo="1.5DL+1.5LL", ok=True, reached_lambda_1=True,
                                                        groups=[dict(role="roof", section="WPB450", dc_max=0.92300001)])]),
                   b11_preconditions=dict(ok=True, lateral_restraint="design engineer's statement required (not checked)")),
              open(os.path.join(j, "ddm_results.json"), "w"))
    json.dump(dict(status="complete_with_solver_stops" if sf else "complete", notes=["n"] if sf else []),
              open(os.path.join(j, "complete_gate.json"), "w"))
    return j


def test_site_index_builder(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import build_site_index as B
    _mini_run(str(tmp_path), "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore")
    _mini_run(str(tmp_path), "IN_Ex19_EBF_12levels_Tplan_Guwahati/units/stem", sf=True)
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps(dict(examples=[dict(id="IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore", title="Ex 10 · big box",
                                                   flag="old flag")])))
    idx = B.build(str(tmp_path), str(prev))
    ids = [e["id"] for e in idx["examples"]]
    assert ids == ["IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore", "IN_Ex19_EBF_12levels_Tplan_Guwahati/units/stem"]
    e = idx["examples"][0]
    assert e["title"] == "Ex 10 · big box" and e["flag"] != "old flag"
    assert e["flag"].startswith("Pushover Y: IS-MCE target not reached")    # check fixes, finding 1: said, not only flagged
    r = e["results"]
    n = r["nlrha"]
    assert n["record_set"] == "FEMA P-695 far-field set, amplitude-scaled to the IS 1893 spectrum"
    assert (n["pairs_dbe"], n["converged_dbe"], n["pairs_mce"], n["converged_mce"]) == (11, 11, 11, 10)
    assert n["converged_text"] == "11/11 · 10/11" and n["levels"]["MCE"]["sf_max"] == pytest.approx(4.4)
    p = r["pushover"]
    assert p["vmax_vb_x"] == 58.4 and p["vmax_w_y"] == 3.501 and p["mce_target_reached_y"] is False
    d = r["ddm"]
    assert d["gravity_lambda"] == 1.246 and d["gravity_lambda_text"] == "1.246" and d["gravity_status"] == "plastic plateau"
    assert d["min_phi_lambda"] == 0.997 and d["min_phi_lambda_text"] == "0.997"           # never 1.00
    assert d["b12_dc_text"] == "0.924" and d["b11_met"] is False and d["b11_sections_compact"] is True
    assert d["solver_failures"] == 0 and "λu 1.246" in e["meta"] and "Vmax/W 3.50" in e["meta"]
    s = idx["examples"][1]["results"]
    assert s["gate"] == "complete_with_solver_stops" and s["ddm"]["solver_failures"] == 1 and s["ddm"]["runaway_steps"] == 1
    assert "stopped numerically" in idx["examples"][1]["flag"]


def test_readme_counts():
    txt = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "24 nonlinear runs" in txt and "39 worked Indian designs" in txt and "19 nonlinear runs" not in txt
