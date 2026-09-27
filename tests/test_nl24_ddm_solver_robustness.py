"""NL-24: DDM solver robustness and the deck-beam transformation (IN_Ex11 gate partial, IN_Ex11 unitC_gym shortfall).

  * IN_Ex11 1.5DL+1.5LL stopped at lambda 0.977 ("step_exhausted", reported NO_LIMIT_POINT below lambda 1) on NPB700
    floor girders whose HR elastic D/C is 0.983: the Corotational girders inside the rigid diaphragm picked up catenary
    tension (1.5 MN) and yielded early; the solver then gave up after one KrylovNewton try and six step cuts.
  * IN_Ex11 unitC_gym 1.5DL+1.5LL: B-1.2 D/C 1.018 on the 17 m NPB700 roof girder from +335 kN catenary tension
    (HR: N = 0, M = 996.6 kN-m, D/C 0.960).
Fixes: horizontal beams inside one rigid diaphragm use P-Delta (like the HR design and the NL pushover / NLRHA models);
algorithm ladder + tolerance fallback + arc-length rescue; a numerical stop with the structure still stiff is
SOLVER_FAILURE and blocks the COMPLETE gate.
"""
import json
import os
import shutil
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")
ENGINE = os.environ.get("STELTIC_ENGINE_DIR", "")
EX11 = "IN_Ex11_SMF_3levels_Zplan_school_Chandigarh"


# ---------------------------------------------------------------- status rules
def test_numerical_stop_is_solver_failure_unless_at_a_genuine_limit():
    from steltic_ddm.solver import limit_status
    rising = [(0.1 * i, i) for i in range(1, 12)]
    assert limit_status(rising, 10, 1.1, termination="step_exhausted", tangent_ratio=0.8)[0] == "SOLVER_FAILURE"
    assert limit_status(rising, 10, 1.1, termination="too_many_failures", tangent_ratio=None)[0] == "SOLVER_FAILURE"
    # stiffness near zero at the stop: a genuine limit the plateau rule had not yet confirmed
    assert limit_status(rising, 10, 1.1, termination="step_exhausted", tangent_ratio=0.03)[0] == "NO_LIMIT_POINT"
    # clock / budget stops stay NO_LIMIT_POINT; detected limits win over the termination
    assert limit_status(rising, 10, 1.1, termination="time_limit", tangent_ratio=0.8)[0] == "NO_LIMIT_POINT"
    assert limit_status(rising, 10, 1.1, capped=True, termination="step_exhausted", tangent_ratio=0.8)[0] == "DUCTILITY_CAP"
    peak = [(0.1, 1), (0.5, 2), (0.9, 3), (0.88, 4), (0.85, 5)]
    assert limit_status(peak, 2, 0.9, termination="step_exhausted", tangent_ratio=0.8)[0] == "LIMIT_POINT"


def test_stop_tangent_ratio():
    from steltic_ddm.solver import stop_tangent_ratio
    hist = [(0.1, 1.0), (0.2, 2.0), (0.3, 3.0), (0.31, 4.0), (0.32, 5.0), (0.33, 6.0)]
    assert stop_tangent_ratio(hist, 0.1) == pytest.approx(0.1)
    assert stop_tangent_ratio(hist[:2], 0.1) is None


# ---------------------------------------------------------------- ladder and arc-length rescue (fake ops)
class _FakeOps:
    def __init__(self, ok_when):
        self.ok_when, self.alg, self.test_, self.integ, self.calls = ok_when, None, None, None, []

    def algorithm(self, *a):
        self.alg = a

    def test(self, *a):
        self.test_ = a

    def integrator(self, *a):
        self.integ = a

    def analyze(self, n):
        self.calls.append((self.alg, self.test_, self.integ))
        return 0 if self.ok_when(self) else -3


def test_ladder_tries_algorithms_then_relaxed_tolerance_and_restores_newton(monkeypatch):
    from steltic_ddm import solver
    fake = _FakeOps(lambda f: f.alg[0] == "Newton" and f.test_[1] == 1e-4)
    monkeypatch.setattr(solver, "ops", fake)
    ok, used = solver._ladder()
    assert ok == 0 and used == "Newton@0.0001"
    assert [c[0][0] for c in fake.calls] == ["KrylovNewton", "NewtonLineSearch", "ModifiedNewton", "KrylovNewton", "Newton"]
    assert max(c[1][2] for c in fake.calls) >= 200                          # more iterations on a rung
    assert fake.alg == ("Newton",) and fake.test_ == ("NormDispIncr", 1e-6, 25, 0)   # back to the default
    fake = _FakeOps(lambda f: False)
    monkeypatch.setattr(solver, "ops", fake)
    assert solver._ladder() == (-3, None)


def test_arc_rescue_uses_arc_length_control_and_cuts_the_increment(monkeypatch):
    from steltic_ddm import solver
    fake = _FakeOps(lambda f: f.integ[0] == "MinUnbalDispNorm" and f.integ[1] <= 0.05 / 4 + 1e-12)
    monkeypatch.setattr(solver, "ops", fake)
    ok, dl = solver._arc_rescue(0.05)
    assert ok == 0 and dl == pytest.approx(0.0125)
    assert fake.integ[0] == "MinUnbalDispNorm" and "-det" in fake.integ
    fake = _FakeOps(lambda f: False)
    monkeypatch.setattr(solver, "ops", fake)
    assert solver._arc_rescue(0.05)[0] != 0


# ---------------------------------------------------------------- gate
def test_complete_gate_blocks_solver_failure(tmp_path):
    from nlrha import india_authority as IA
    runs = [dict(label="1.5DL+1.5LL", kind="gravity", status="SOLVER_FAILURE", termination="step_exhausted", lambda_end=0.977),
            dict(label="0.9DL+1.5EQ_X", kind="seismic", status="SOLVER_FAILURE", termination="step_exhausted", lambda_end=2.9),
            dict(label="1.5DL+1.5W_X", kind="wind", status="DUCTILITY_CAP", termination="ductility_cap", lambda_end=2.5)]
    (tmp_path / "ddm_results.json").write_text(json.dumps(dict(runs=runs, gravity_gate=dict(ok=True), b12_check=dict(ok=True))))
    r = IA.artefact_gate(str(tmp_path))["reasons"]
    sf = [x for x in r if "SOLVER FAILURE" in x]
    assert len(sf) == 2 and "0.977" in sf[0] and "numerical stop" in sf[0]
    assert not any("1.5DL+1.5W_X" in x for x in r)


# ---------------------------------------------------------------- deck beams
def _nm():
    m = lambda tag, n1, n2, kind="beam": types.SimpleNamespace(tag=tag, n1=n1, n2=n2, kind=kind, role="floor")
    nodes = {1: (0, 0, 3000), 2: (6000, 0, 3000), 3: (6000, 0, 3500), 4: (0, 0, 6000), 5: (0, 0, 0)}
    return types.SimpleNamespace(nodes=nodes, diaphragms={199999: [1, 2, 3], 299999: [4]},
                                 members=[m(10, 1, 2), m(11, 2, 3), m(12, 1, 4), m(13, 5, 1, "col")])


def test_deck_beams_are_horizontal_beams_inside_one_diaphragm(monkeypatch):
    from steltic_ddm.model_gmnia import GMNIAModel
    g = GMNIAModel.__new__(GMNIAModel)
    g.nm, g.cfg, g.transf_type = _nm(), {"load_plan": {"jurisdiction": "india"}}, "Corotational"
    assert g.deck_beams() == {10}                       # 11 sloped, 12 spans two diaphragms, 13 a column
    monkeypatch.delenv("SNL_DDM_BEAM_TRANSF", raising=False)
    assert g.deck_beam_transf() == "PDelta"
    monkeypatch.setenv("SNL_DDM_BEAM_TRANSF", "Corotational")
    assert g.deck_beam_transf() == "Corotational"
    g._deck_beams = g.deck_beams()
    assert g._transf_for(g.nm.members[0]) == 6 and g._transf_for(g.nm.members[1]) == 3
    usa = GMNIAModel.__new__(GMNIAModel)
    usa.nm, usa.cfg, usa.transf_type = _nm(), {}, "Corotational"
    monkeypatch.delenv("SNL_DDM_BEAM_TRANSF", raising=False)
    assert usa.deck_beams() == set() and usa.deck_beam_transf() == "Corotational"


# ---------------------------------------------------------------- gold regressions
def _gold(rel, tmp_path):
    src = os.path.join(GOLD, rel)
    if not (os.path.isdir(src) and ENGINE and os.path.exists(os.path.join(ENGINE, "static_model.py"))):
        pytest.skip("gold job %s or steltic_india engine ($STELTIC_ENGINE_DIR) not available" % rel)
    job = tmp_path / os.path.basename(rel)
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html", "unitB_link", "unitC_gym"))
    return str(job)


def _sweep(job, label, imp_tag):
    from steltic_ddm import cli, imperfections, ingest, loads
    nm = ingest.load_package(job, ENGINE)
    combo = [c for c in loads.steltic_combos(nm.cfg, nm=nm) if c[0] == label][0]
    imp = [i for i in imperfections.cases_for(combo, psi=1 / 200.0) if i["tag"] == imp_tag][0]
    opts = dict(nsub=[2, 2, 4], residual="lehigh", Fy=None, hardening=0.002, fast=False, nip=5, bow=0.001, psi=1 / 200.0,
                dlam=0.05, max_steps=250, time_limit=2400.0, rigid_end_offset=False, india=True, strain_cap=20.0,
                bow_hollow=1 / 500.0)
    return cli._worker((job, ENGINE, label, imp, opts))


def test_gold_ex11_gravity_girders_run_past_first_yield(tmp_path, monkeypatch):
    monkeypatch.delenv("SNL_DDM_BEAM_TRANSF", raising=False)
    job = _gold(EX11, tmp_path)
    r = _sweep(job, "1.5DL+1.5LL", "+Y")
    res = r["res"]
    assert res["status"] in ("LIMIT_POINT", "PLASTIC_PLATEAU", "DUCTILITY_CAP"), (res["status"], res["log"])
    assert res["lambda_end"] > 1.1 and res["first_yield"] > 1.0
    g = next(x for x in r["b12"]["groups"] if x["section"] == "NPB700X250X143.42")
    # characteristic IS 2062 fy (E250, 20 < t <= 40 mm -> 240 MPa) in the fibres; gamma_m0 = 1.10 only in B-1.2
    assert g["fy_MPa"] == 240.0 and g["dc_max"] < 1.0
    assert any(x[1] == "NPB700X250X143.42" for x in r["section_log"])


def test_gold_ex11_gym_roof_girder_matches_hr_moment_without_catenary(tmp_path, monkeypatch):
    monkeypatch.delenv("SNL_DDM_BEAM_TRANSF", raising=False)
    job = _gold(os.path.join(EX11, "unitC_gym"), tmp_path)
    r = _sweep(job, "1.5DL+1.5LL", "+X")
    g = next(x for x in r["b12"]["groups"] if x["section"] == "NPB700X250X143.42")
    hr = json.load(open(os.path.join(job, "design", "member_combo_forces.json")))
    M_hr = hr["elements"]["11"]["records"]["1.5DL+1.5LL"][1] / 1e6          # 996.6 kN-m, N = 0 (Linear beams)
    assert g["M_major_kNm"] == pytest.approx(M_hr, rel=0.01)
    assert g["N_kN"] < 100.0                                                 # was +335 kN catenary (Corotational)
    assert g["dc_max"] < 1.0 and g["Md_kNm"] == pytest.approx(1038.5, rel=0.002)
