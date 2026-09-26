"""WP4.3/4.4/4.9/4.10/4.11: informative response summary (no verdict), non-vacuous rule, DDM limit points,
B-1.2 section capacity, CLI refusals, damping warning, India NSP from the elastic spectrum."""
from __future__ import annotations
import math, os, sys, types
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIX = os.path.join(ROOT, "tests", "fixtures")


def _pkg(system="SMF"):
    from pushover import package_reader as PR
    pkg = PR.load(os.path.join(FIX, "IN_Ex2_pkg"))
    pkg.basis.system = system
    return pkg


def _result(member_peaks, meta, conv=True):
    return dict(record=1, label="r1", sf=1.0, converged=conv, reason="completed", heights=[144.0] * 2,
                peak_story_drift=[[0.01, 0.008], [0.009, 0.007]], peak_roof_in=[3.0, 2.0], residual_drift=[0.0, 0.0],
                peak_base_shear_kip=[500.0, 450.0], member_peaks=member_peaks, member_meta=meta, peak_colN={}, seconds=1, steps=1)


def test_response_summary_has_no_verdict_and_vacuous_moment_frame_is_flagged():
    from nlrha import response_summary as RS
    pkg = _pkg("SMF")
    meta = dict(members={}, braces={}, ips=[1], enabled=True)
    s = RS.summarise([_result({}, meta)], pkg, "DBE", "IS 1893 elastic DBE (Z/2)·I·Sa/g (no R)", T1=2.0)
    assert s["verdict"] is None and s["acceptance_basis"] is None
    assert "no acceptance criteria for nonlinear analysis" in s["statement"]
    assert s["non_vacuous"]["ok"] is False and set(s["non_vacuous"]["missing_kinds"]) == {"beam", "col"}   # all([]) never passes


def test_response_summary_member_rows_and_reference_rotation():
    from nlrha import response_summary as RS
    pkg = _pkg("SMF")
    meta = dict(members={1: dict(kind="beam", section="NPB450X190X67.16", level=1, fy_MPa=250),
                         2: dict(kind="col", section="WPB400X300X124.8", level=1, fy_MPa=250)}, braces={}, ips=[1], enabled=True)
    pk = dict(m={1: [2.5, 0.012], 2: [0.6, 0.004]}, b={})
    s = RS.summarise([_result(pk, meta)], pkg, "MCE", "IS 1893 elastic MCE Z·I·Sa/g (no R)", T1=2.0)
    assert s["non_vacuous"]["ok"] is True
    beam = next(g for g in s["member_groups"] if g["kind"] == "beam")
    assert beam["yielded"] and beam["reference_rot_rad"] == 0.04 and beam["ratio_to_reference"] == pytest.approx(0.3)
    assert s["base_shear"]["VB_design_kN"] == pytest.approx(pkg.basis.india["VB_kN"])
    assert s["base_shear"]["elastic_kN"] == pytest.approx(0.16 * 1.36 / 2.0 * pkg.basis.india["W_kN"])


def test_acceptance_refuses_asce_for_india():
    from nlrha import acceptance as AC
    pkg = _pkg()
    with pytest.raises(RuntimeError):
        AC.evaluate([], pkg, {}, {}, {}, 0.0)
    with pytest.raises(RuntimeError):
        AC.risk_category(pkg)


def test_ddm_limit_status():
    from steltic_ddm.solver import limit_status
    rising = [(0.1 * i, i) for i in range(1, 12)]
    assert limit_status(rising, 10, 1.1)[0] == "NO_LIMIT_POINT"
    peak = [(0.1, 1), (0.5, 2), (0.9, 3), (0.88, 4), (0.85, 5)]
    assert limit_status(peak, 2, 0.9)[0] == "LIMIT_POINT"
    assert limit_status(rising, 10, 1.1, plateau=True)[0] == "PLASTIC_PLATEAU"
    assert limit_status(rising, 10, 1.1, capped=True)[0] == "DUCTILITY_CAP"


def test_b12_section_capacity_and_interaction():
    from pushover import india_materials as IM
    cap = IM.section_capacity("NPB400X180X57.38", 250.0)
    assert cap["Mdz_Nmm"] / 1e6 == pytest.approx(1140000.5 * 250 / 1.1 / 1e6, rel=0.02)     # Zp·fy/gamma_m0 ~ 259 kN·m
    r = IM.b12_interaction(0.0, 99.75e6, 0.0, 0.0, cap)
    assert r["dc"] == pytest.approx(0.385, rel=0.03) and r["ok"]


def test_nsp_india_uses_elastic_spectrum_ex1_x_dbe():
    """Ex1 X (existing package curve and coefficients): Sa(Te)=0.300 g at DBE -> delta_t ~ 0.28 in (7 mm)."""
    from pushover import postprocess as PP, package_reader as PR, hinge_models as HM
    import csv
    pkg = PR.load(os.path.join(FIX, "IN_Ex1_pkg"))
    u, V = [], []
    for row in csv.DictReader(open(os.path.join(FIX, "ex1_curve_X_shipped.csv"))):
        u.append(float(row["roof_disp_in"])); V.append(float(row["base_shear_kip"]))
    # first-mode shape giving the shipped C0 = 1.2857 (5 storeys, masses of the package)
    lv = [1.0, 1.0, 1.0, 1.0, 2113.2 / 3164.4]
    def c0(p):
        phi = [((k + 1) / 5.0) ** p for k in range(5)]
        return sum(m * f for m, f in zip(lv, phi)) / sum(m * f * f for m, f in zip(lv, phi)), phi
    lo, hi = 0.3, 3.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if c0(mid)[0] < 1.28568 else (lo, mid)
    phi = c0(0.5 * (lo + hi))[1]
    run = dict(rec=dict(u=u, V=V, story_u=[[x * f for f in phi] for x in u]), H=708.66, heights=[141.73] * 5,
               pattern=dict(T1=0.267, phi={k + 1: phi[k] for k in range(5)}, masses={k + 1: lv[k] for k in range(5)}),
               gravity_table_QG=None)
    n = PP.nsp_target(run, pkg.basis, HM.load_params(), "DBE")
    assert n["Sa"] == pytest.approx(0.300, rel=1e-6) and n["level"] == "DBE"
    assert n["target_disp_in"] == pytest.approx(0.28, abs=0.03)
    m = PP.nsp_target(run, pkg.basis, HM.load_params(), "MCE")
    assert m["Sa"] == pytest.approx(0.600, rel=1e-6)


def test_nlrha_cli_refuses_code_target_for_india():
    from nlrha import cli
    pkg = _pkg()
    args = types.SimpleNamespace(target="code", usgs_scaffolding=False)
    with pytest.raises(SystemExit):
        cli._target_kind(args, pkg)
    assert cli._target_kind(types.SimpleNamespace(target=None), pkg) == "is1893"


def test_damping_above_cap_warns_not_exits(capsys):
    """NL-6: the India reference is IS 1893 7.2.4 (5 %), not the ASCE 16.3.5 2.5 % cap; above it -> warning."""
    from nlrha import cli, india_authority as IA
    from pushover import hinge_models as HM
    pkg = _pkg()
    ch16 = IA.load_ch16_params()
    prm = HM.load_params()
    d = cli._damping(types.SimpleNamespace(xi=0.06), pkg, ch16, prm)
    assert d["xi"] == 0.06 and d["warning"] and d["cap"] == 0.05
    assert "WARNING" in capsys.readouterr().out
    d = cli._damping(types.SimpleNamespace(xi=None), pkg, ch16, prm)
    assert d["xi"] == 0.025 and d["warning"] is None and "7.2.4" in d["basis"] and "ASCE" not in d["basis"]
    assert d["reference"]["value"] == 0.05


def test_sf_bounds_warning():
    from nlrha import ground_motions as GM
    recs = []
    for i in range(3):
        a = np.sin(np.linspace(0, 20, 1000)) * 0.1 * (i + 1)
        recs.append(dict(id=i, a1=a, a2=a * 0.8, dt=0.01, duration_s=10.0, comp1="a", comp2="b"))
    T = np.array([0.05, 0.5, 1.0, 2.0]); tgt = (T, np.full(4, 5.0), "IS 1893 elastic DBE (no R)")
    gm, chosen = GM.select_and_scale(recs, None, None, 8.0, 0.1, 1.5, n_select=2, target=tgt, sf_bounds=(0.9, 1.1), verbose=False)
    assert gm["sf_warnings"]
