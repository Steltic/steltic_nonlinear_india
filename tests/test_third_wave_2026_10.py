"""Third wave (2026-10-30), steltic_nonlinear_india: EBF link model (P1), engine version, P10 presentation, orchestrator.

P1 -- the Y-direction EBF links of IN_Ex15, IN_Ex19 and the IN_Ex19 stem rotated 0.42-0.50 rad at 0.6-1.1 % storey
drift. Cause: the link was ONE force-based element with the IS 18168 11.2 shear yielding aggregated on its sections, and
the HR gravity replay (NL-14) puts the floor load on it, so its shear varies along it. Once the link yields, the
element's local iteration accepts a false state -- the end sections yield in opposite directions (+/-0.4 rad), their
shear strains cancel in the element deformations, so the element's energy test passes while the sections are out of
equilibrium by about 2 V_pL -- and the link sheds its shear (the one-step strength loss). The Y-direction beams carry
the floor load (29 N/mm in IN_Ex15) and the X-direction ones only their self-weight, hence the direction. The link is
now two flexural fibre halves and one mid-length shear spring (pushover, NLRHA and DDM)."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MM = 25.4
L_BAY, E_LINK, H = 6000.0 / MM, 600.0 / MM, 4000.0 / MM          # inches (the India NL models run in kip-in)
LINK, BEAM, COL, BRACE = "WPB500X300X187.34", "WPB500X300X187.34", "WPB500X300X187.34", "WPB400X300X155.26"


def _ebf_pkg(direction, tmp):
    """A one-storey, one-bay EBF (V-braces meeting a 600 mm mid-span shear link, L / e = 10) along global X or Y, as a
    Steltic HR package would describe it: elasticBeamColumn columns and beams, the link as an ElasticTimoshenkoBeam
    (role link), the braces as Truss, one rigid diaphragm. The Y frame is the X frame turned by 90 degrees."""
    from pushover.package_reader import ElasticModel, DesignBasis, Package

    def P(s, z):                                     # in-plane coordinate s along the frame
        return (s, 0.0, z) if direction == "X" else (0.0, s, z)
    m = ElasticModel()
    nodes = {1: P(0, 0), 2: P(L_BAY, 0), 3: P(0, H), 4: P(L_BAY, H), 5: P((L_BAY - E_LINK) / 2, H),
             6: P((L_BAY + E_LINK) / 2, H), 9: P(L_BAY / 2, H)}
    m.nodes.update(nodes)
    m.fixes.update({1: [1] * 6, 2: [1] * 6, 9: [0, 0, 1, 1, 1, 0]})      # the HR diaphragm master: out-of-plane DOFs fixed
    m.masses[9] = [1.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    col_tr = 2 if direction == "X" else 1             # strong axis resisting the in-plane sway
    m.transfs.update({1: ("PDelta", 1.0, 0.0, 0.0), 2: ("PDelta", 0.0, 1.0, 0.0), 3: ("Linear", 0.0, 0.0, 1.0)})
    m.materials[90] = ("Elastic", 90, 29000.0)
    base = dict(A=36.9, E=29000.0, G=11154.0, J=10.0, Iy=2570.0, Iz=303.0, release=None)
    m.elements += [dict(base, tag=11, n1=1, n2=3, transf=col_tr), dict(base, tag=12, n1=2, n2=4, transf=col_tr),
                   dict(base, tag=21, n1=3, n2=5, transf=3), dict(base, tag=22, n1=6, n2=4, transf=3),
                   dict(tag=30, n1=5, n2=6, etype="ElasticTimoshenkoBeam",
                        raw=["ElasticTimoshenkoBeam", 30, 5, 6, 29000.0, 11154.0, 36.9, 10.0, 2570.0, 303.0, 21.7, 10.0, 3]),
                   dict(tag=41, n1=1, n2=5, etype="Truss", raw=["Truss", 41, 1, 5, 30.5, 90]),
                   dict(tag=42, n1=2, n2=6, etype="Truss", raw=["Truss", 42, 2, 6, 30.5, 90])]
    m.diaphragms.append((3, 9, [3, 4, 5, 6]))
    sched = {11: dict(member="col", section=COL, role="lateral_col"), 12: dict(member="col", section=COL, role="lateral_col"),
             21: dict(member="beam", section=BEAM, role="floor"), 22: dict(member="beam", section=BEAM, role="floor"),
             30: dict(member="beam", section=LINK, role="link"),
             41: dict(member="brace", section=BRACE, role="brace"), 42: dict(member="brace", section=BRACE, role="brace")}
    basis = DesignBasis(jurisdiction="india", system="EBF", package_units="kip-in")
    return Package(root=tmp, name="ebf_%s" % direction, model=m, schedule=sched, calc={}, basis=basis, files={})


def _push(direction, tmp, w_link=30.0, drift=0.01, n=100):
    """Gravity (a 30 N/mm floor load on the link and the beams, through the HR gravity replay) then a displacement-
    controlled push of the diaphragm to `drift`. Returns rows (drift, base shear kip, link rotation rad, Vlink kN)."""
    import openseespy.opensees as ops
    from pushover import nonlinear_model as NM, hinge_models as HM, member_response as MR
    os.environ["SNL_PLASTICITY"] = "fibre"
    pkg = _ebf_pkg(direction, tmp)
    prm = HM.load_params(None, jurisdiction="india")
    hinges, stats = NM.build_nonlinear(pkg, prm, {}, verbose=False, plasticity="fibre")
    rec = MR.MemberRecorder(pkg, hinges, stats)
    wl = [0.0, -w_link, 0.0]                                      # beamUniform Wy, Wz (local z up), N/mm
    loads = {"_hr": {"ele": [[30, 0.0, 1.0, "beamUniform", wl], [21, 0.0, 1.0, "beamUniform", wl],
                             [22, 0.0, 1.0, "beamUniform", wl]], "node": {}}}
    assert NM._apply_gravity(loads) == 0
    dof = 1 if direction == "X" else 2
    ops.timeSeries("Linear", 2); ops.pattern("Plain", 2, 2)
    f = [0.0] * 6; f[dof - 1] = 1.0; ops.load(9, *f)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-5, 100, 0); ops.algorithm("Newton")
    du = drift * H / n
    ops.integrator("DisplacementControl", 9, dof, du); ops.analysis("Static")
    rows = []
    lk = stats["link_registry"][30]
    for _ in range(n):
        assert NM._try_analyze(du, 9, dof)                          # the pushover's own step (tolerance, fallbacks)
        ops.reactions()
        V = -sum(ops.nodeReaction(t, dof) for t in (1, 2))
        smp = rec.sample()
        g = smp["l"][30][0]
        Vs = ops.eleResponse(lk["spring"], "basicForce")[2] * 4.4482216152605
        rows.append((ops.nodeDisp(9, dof) / H, V, g, Vs))
    return rows, lk, stats


@pytest.mark.parametrize("direction,n", [("X", 100), ("Y", 100), ("X", 20), ("Y", 20)])
def test_ebf_link_rotation_follows_the_drift_kinematics(direction, n, tmp_path):
    """Link rotation ~ (L / e) x storey drift once the link yields, the same along X and along Y, with a floor load on
    the link; no one-step loss of base shear; the spring carries the IS 18168 11.2 V_pL (plus the modelled hardening).
    With 20 steps to 1 % drift the old single-element link (shear aggregated on its sections) fell into the false
    state at the second step: base shear 33 kip instead of 321 kip and a "link rotation" of 0.33 rad at 0.1 % drift."""
    rows, lk, stats = _push(direction, str(tmp_path), n=n)
    l_over_e = L_BAY / E_LINK
    th, V, g, Vs = rows[-1]
    assert th == pytest.approx(0.01, rel=1e-6)
    kin = l_over_e * th
    assert 0.80 * kin < g <= 1.0 * kin, (g, kin)                   # 0.1 rad kinematic; the elastic drift share is the rest
    th1, _, g1, _ = rows[len(rows) // 2 - 1]                         # post-yield increments: d(gamma) / d(theta) = L / e
    assert (g - g1) / (th - th1) == pytest.approx(l_over_e, rel=0.10)
    for a, b in zip(rows, rows[1:]):
        assert b[1] >= 0.99 * a[1], "one-step loss of base shear at drift %.4f" % b[0]
    assert lk["Vp_kN"] < abs(Vs) < 1.3 * lk["Vp_kN"]                 # yielded; hardening 0.5 % of K (modelling assumption)
    assert lk["model"] == "shear_spring" and stats["links"] == 1


def test_ebf_x_and_y_links_are_the_same_model(tmp_path):
    """The Y frame is the X frame turned by 90 degrees: identical curves and link rotations."""
    rx, _, _ = _push("X", str(tmp_path), n=40)
    ry, _, _ = _push("Y", str(tmp_path), n=40)
    for a, b in zip(rx, ry):
        assert b[1] == pytest.approx(a[1], rel=1e-6, abs=1e-6) and b[2] == pytest.approx(a[2], rel=1e-6, abs=1e-9)


def test_link_halves_carry_the_gravity_replay(tmp_path):
    """The link's halves keep the parent tag and SEG_ELE_BASE + tag*100 + 1, so the HR gravity replay finds them
    (a load on a parent missing from the model would be counted in 'missing')."""
    import openseespy.opensees as ops
    from pushover import nonlinear_model as NM, hinge_models as HM
    from pushover.fibre_model import SEG_ELE_BASE
    os.environ["SNL_PLASTICITY"] = "fibre"
    pkg = _ebf_pkg("Y", str(tmp_path))
    hinges, stats = NM.build_nonlinear(pkg, HM.load_params(None, jurisdiction="india"), {}, verbose=False, plasticity="fibre")
    ch = NM.gravity_chains([30])
    assert ch[30] == [(30, 0.0, 0.5), (SEG_ELE_BASE + 30 * 100 + 1, 0.5, 1.0)]
    assert set(stats["link_registry"][30]["halves"]) <= set(stats["fibre_eles"])
    assert stats["link_registry"][30]["spring"] not in stats["fibre_eles"]      # no stiffness damping on the spring
    ops.wipe()


# ------------------------------------------------------------------ DDM: the same link model (GMNIA)
GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")
ENGINE = os.environ.get("STELTIC_ENGINE_DIR", "")


def test_ddm_gmnia_builds_the_link_halves_and_spring():
    """IN_Ex15 (HR gold, when present): every EBF link of the GMNIA model is two sub-elements and one shear spring;
    the spring carries V_pL = fy A_w / sqrt(3) on the link's local z."""
    import contextlib, glob, io
    hits = sorted(glob.glob(os.path.join(GOLD, "IN_Ex15_EBF*")))
    if not hits or not ENGINE:
        pytest.skip("IN_Ex15 gold job or STELTIC_ENGINE_DIR not available")
    import openseespy.opensees as ops
    from steltic_ddm import ingest
    from steltic_ddm.model_gmnia import GMNIAModel
    with contextlib.redirect_stdout(io.StringIO()):
        nm = ingest.load_package(hits[0], ENGINE)
        g = GMNIAModel(nm, nm.cfg, nsub=(2, 2, 2), elastic=False, residual="none", out_of_plumb=(None, 0.0), bow=0.0,
                       brace_bow=0.0)
        g.build()
    links = [m for m in nm.members if m.role == "link"]
    assert links and len(g.links) == len(links)
    tags = set(ops.getEleTags())
    for m in links:
        halves = [e for e in g.elems if e["mtag"] == m.tag]
        assert [e["s"] for e in halves] == [0, 1] and g.links[m.tag]["spring"] in tags
        rec = g.links[m.tag]
        assert rec["model"] == "shear_spring" and rec["Vp_kN"] == pytest.approx(rec["fy_MPa"] * rec["Aw_mm2"] / math.sqrt(3) / 1e3)
    ops.wipe()


# ------------------------------------------------------------------ P10: Vmax up to the IS-MCE target, Te < T1
def _dd(u, V, t_mce, T1=1.0, Te=(1.1, 1.1), full=None, stop="reached max roof drift 10.0% of H"):
    full = full or (max(V), u[V.index(max(V))])
    return dict(T1=T1, curve_u_mm=u, curve_V_kN=V, stop_reason=stop,
                nsp={"IS-DBE": dict(target_disp_mm=t_mce / 2, Te=Te[0], W_kip=1000.0 / 4.4482216152605),
                     "IS-MCE": dict(target_disp_mm=t_mce, Te=Te[1], W_kip=1000.0 / 4.4482216152605)},
                capacity=dict(Vmax_kN=full[0], u_at_Vmax_in=full[1] / 25.4, V_design_kip=100.0 / 4.4482216152605,
                              tail_status="lower_bound" if stop.startswith("solver") else "captured"))


def test_headline_kinds_up_to_the_mce_target():
    """Review M1: the headline says what it is. Still rising at δt: the base shear at δt (not a strength, no '≥', ratios
    V(δt)/VB); a peak before δt: Vmax, a strength; the curve ended before δt: its computed peak, '≥' only if still rising
    at its end. The peak of the analysed curve is stated separately, with its displacement."""
    from pushover import vmax_policy as VP
    u = [0.0, 50.0, 100.0, 150.0, 2000.0]
    V = [0.0, 400.0, 500.0, 520.0, 1500.0]
    h = VP.vmax_to_target(_dd(u, V, 120.0, stop="solver non-convergence at roof u=78.74 in"))
    assert h["kind"] == "at_target" and h["at_target"] and not h["is_strength"] and not h["lower_bound"]
    assert h["V_kN"] == pytest.approx(508.0) and h["u_mm"] == pytest.approx(120.0)            # interpolated at δt
    assert h["V_over_VB"] == pytest.approx(5.08) and VP.ratio_label(h) == "V(δt)/VB" and VP.strength_text(h) == "508 kN"
    assert "Base shear at the IS-MCE target δt = 508 kN" in VP.headline_text("Y", h) and "not claimed" in h["qualifier"]
    pk = h["peak_analysed"]
    assert pk["V_kN"] == 1500.0 and pk["u_mm"] == 2000.0 and pk["numerical_stop"] and pk["at_curve_end"]
    t = VP.peak_text("Y", h)
    assert "1,500 kN at 2,000 mm" in t and "beyond the IS-MCE target" in t and "at least this" in t
    # a curve point exactly at δt, still rising: the same (the u_best = δt case)
    h0 = VP.vmax_to_target(_dd([0.0, 60.0, 120.0, 180.0], [0.0, 300.0, 520.0, 700.0], 120.0))
    assert h0["kind"] == "at_target" and h0["V_kN"] == 520.0
    # a peak before δt: the strength
    h1 = VP.vmax_to_target(_dd(u, [0.0, 400.0, 500.0, 450.0, 1500.0], 120.0))
    assert h1["kind"] == "peak" and h1["is_strength"] and h1["V_kN"] == 500.0 and h1["u_mm"] == 100.0
    assert VP.ratio_label(h1) == "Vmax/VB" and h1["label"] == "Vmax up to the IS-MCE target"
    # the curve ended before δt, still rising: a lower bound
    h2 = VP.vmax_to_target(_dd(u[:3], V[:3], 120.0, stop="solver non-convergence at roof u=3.94 in"))
    assert h2["kind"] == "ended" and h2["V_kN"] == 500.0 and not h2["target_reached"] and h2["lower_bound"]
    assert VP.strength_text(h2) == "≥ 500 kN" and VP.peak_text("Y", h2) is None
    # ... after a peak: the peak, no '≥'
    h3 = VP.vmax_to_target(_dd([0.0, 50.0, 100.0, 110.0], [0.0, 400.0, 500.0, 450.0], 120.0, stop="solver non-convergence"))
    assert h3["kind"] == "ended" and h3["V_kN"] == 500.0 and not h3["lower_bound"] and VP.strength_text(h3) == "500 kN"


def test_te_flags_below_and_far_above_t1():
    from pushover import vmax_policy as VP
    dd = _dd([0.0, 100.0, 200.0], [0.0, 1.0, 2.0], 150.0, T1=0.984, Te=(0.421, 0.722))
    f = VP.te_flags(dd)
    assert [x[0] for x in f] == ["IS-DBE", "IS-MCE"] and {x[3] for x in f} == {"below"}
    n = VP.te_note("Y", f)
    assert "below the elastic period T1 = 0.984 s" in n and "0.421" in n
    assert VP.te_flags(_dd([0.0, 100.0], [0.0, 1.0], 50.0, T1=0.984, Te=(0.99, 1.2))) == []
    hi = VP.te_flags(_dd([0.0, 100.0], [0.0, 1.0], 50.0, T1=1.0, Te=(1.2, 1.6)))     # review M2: Te >> T1
    assert hi == [("IS-MCE", 1.6, 1.0, "far_above")] and "more than 1.5 times the elastic period" in VP.te_note("X", hi)


def test_ki_is_the_initial_slope():
    """Review M2: Ki (ASCE 41-17 Eq. 7-27) is the elastic slope at the start of the curve -- not inflated by a base
    shear offset at the start or a near-zero first point, and not the secant at 0.3 x a peak far along the curve."""
    from pushover import postprocess as PP
    u = [0.0] + [2.43 * i for i in range(1, 12)]
    assert PP.initial_stiffness(u, [0.0] + [94.0 + 236.4 * x for x in u[1:]]) == pytest.approx(236.4)
    assert PP.initial_stiffness([0.0, 0.004, 6.48, 12.97, 19.45], [0.0, 1.1, 384.0, 769.0, 1153.0]) == pytest.approx(59.3, rel=0.01)
    # a coarse first step after which the curve softens (the shipped IN_Ex1 X curve): the secant to the first point
    assert PP.initial_stiffness([0.0, 0.47244, 0.94488, 1.41732], [0.0, 1174.932, 2244.614, 2962.203]) == \
        pytest.approx(1174.932 / 0.47244)
    u = [float(i) for i in range(0, 201)]                     # elastic 10 to u = 5, then a long rising branch to 245
    V = [10.0 * x if x <= 5 else 50.0 + (x - 5.0) for x in u]
    assert PP.initial_stiffness(u, V) == pytest.approx(10.0)
    i = next(k for k, v in enumerate(V) if v >= 0.3 * max(V))
    assert V[i] / u[i] < 3.0                                   # the old secant at 0.3 Vmax: about a quarter of it


def test_site_index_headline_fields(tmp_path):
    """Review M1 in the site index: Vmax fields only for a strength, V(δt) fields for the base shear at the target."""
    import json
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import build_site_index as BSI
    job = tmp_path / "IN_ExT"
    (job / "pushover").mkdir(parents=True)
    pkg = dict(jurisdiction="india", directions={
        "X": _dd([0.0, 50.0, 100.0, 150.0, 2000.0], [0.0, 400.0, 500.0, 520.0, 1500.0], 120.0,
                 stop="solver non-convergence at roof u=78.74 in", Te=(0.9, 0.9)),
        "Y": _dd([0.0, 50.0, 100.0, 150.0, 2000.0], [0.0, 400.0, 500.0, 450.0, 1500.0], 120.0)})
    (job / "pushover" / "pushover_package.json").write_text(json.dumps(pkg))
    out = BSI.pushover_results(str(job))
    assert out["headline_kind_x"] == "at_target" and out["vmax_vb_x"] is None and out["vmax_vb_text_x"] is None
    assert out["v_target_vb_x"] == 5.1 and out["v_target_vb_text_x"] == "5.1" and not out["vmax_lower_bound_x"]
    assert out["headline_kind_y"] == "peak" and out["vmax_vb_y"] == 5.0 and out["v_target_vb_y"] is None
    assert out["mce_target_mm_x"] == 120.0 and "1,500" in out["peak_analysed_text_x"] and out["te_below_t1_x"]
    assert "vmax_lower_bound_note" not in out and "IS-MCE target" in out["vmax_basis"]
    m = BSI.meta_line(dict(pushover=out))
    assert "X V(δt)/VB 5.1; Y Vmax/VB 5.0" in m and "Vmax/VB = " not in m


# ------------------------------------------------------------------ P10: keys and solver words on public pages
def test_public_words():
    from snl.public_text import words, words_html, scrub_html, role_words, status_words, group_words
    s = words("1.5DL+1.5LL lateral_col BOX450 NO_LIMIT_POINT (terminated: time_limit at λ = 1.493); SOLVER_FAILURE; "
              "material@E350: IS 2062; tube_material@YST310: IS 1161; deformation_capacity: IS 18168 12.3.3.1")
    assert s == ("1.5DL+1.5LL lateral column BOX450 no limit point (terminated: time limit at λ = 1.493); numerical stop; "
                 "material (E350): IS 2062; tube material (YST310): IS 1161; deformation capacity: IS 18168 12.3.3.1")
    assert words(s) == s                                                     # idempotent
    assert role_words("gravity_col") == "gravity column" and status_words("PLASTIC_PLATEAU") == "plastic plateau"
    assert group_words("material@E350") == "material (E350)"
    h = "<p>gravity_col LIMIT_POINT</p><script>const R={'gravity_col':1,'LIMIT_POINT':2}</script>"
    assert words_html(h) == "<p>gravity column limit point</p><script>const R={'gravity_col':1,'LIMIT_POINT':2}</script>"
    assert "engineer of record" not in scrub_html("<p>to be checked by the engineer of record.</p>")


# ------------------------------------------------------------------ P10: member forces at lambda = 1 stored
def test_forces_at_lambda_one_are_stored_and_b12_can_be_reapplied():
    from steltic_ddm import india_checks as IC
    from steltic_ddm.cli import _india_fy_fn
    f1 = {11: dict(kind="col", role="lateral_col", section="WPB300X300X100.85", N_comp=1.2e6, N_abs=1.2e6, N_top=1.1e6,
                   M_major=95e6, M_minor=4e6, V=60e3),
          21: dict(kind="beam", role="floor", section="WPB400X300X155.26", N_comp=0.0, N_abs=1e4, N_top=0.0,
                   M_major=310e6, M_minor=0.0, V=250e3),
          "_lambda": dict(target=1.0, lower=0.95, upper=1.05)}
    fy = _india_fy_fn("/nonexistent")
    direct = IC.b12_check(f1, fy, 1.3, "1.5DL+1.5LL", status="LIMIT_POINT")
    packed = IC.pack_forces(f1)
    assert packed["m"]["11"] == [1200.0, 1200.0, 1100.0, 95.0, 4.0, 60.0] and packed["lambda_basis"]["lower"] == 0.95
    index = {"11": ["col", "lateral_col", "WPB300X300X100.85"], "21": ["beam", "floor", "WPB400X300X155.26"]}
    run = dict(label="1.5DL+1.5LL", lambda_end=1.3, status="LIMIT_POINT", forces_at_1=packed)
    again = IC.b12_from_stored(run, index, fy)
    assert again["ok"] == direct["ok"] and [g["dc_max"] for g in again["groups"]] == [g["dc_max"] for g in direct["groups"]]
    assert IC.b12_from_stored(dict(run, forces_at_1=None), index, fy) is None


# ------------------------------------------------------------------ engine version: HR main gravity
def test_hr_gravity_dead_factor_below_one_uses_the_permanent_dead_state():
    """HR main (first wave item 5) leaves roof collateral / PV off the IS 800 Table 4 0.9 DL rows: with a recorded 'Dp'
    state a dead-load factor below 1.0 applies to Dp, otherwise to D (records without collateral: unchanged)."""
    from snl import hr_gravity as HG
    st = lambda w: dict(ele=[[7, 0.0, 1.0, "beamUniform", [0.0, -w, 0.0]]], node={})
    d = dict(states={"D": st(10.0), "Dp": st(6.0), "L": st(3.0)})
    lo = HG.combine(d, {"D": 0.9, "L": 0.0})
    hi = HG.combine(d, {"D": 1.5, "L": 1.5})
    assert lo["ele"][0][4][1] == pytest.approx(-5.4) and len(lo["ele"]) == 1
    assert sum(e[4][1] for e in hi["ele"]) == pytest.approx(-15.0 - 4.5)
    d2 = dict(states={"D": st(10.0)})
    assert HG.combine(d2, {"D": 0.9})["ele"][0][4][1] == pytest.approx(-9.0)


def test_hr_gravity_engine_fingerprint(tmp_path):
    from snl import hr_gravity as HG
    eng = tmp_path / "steel_engine"; eng.mkdir()
    (eng / "static_model.py").write_text("x = 1\n")
    a = HG.engine_fingerprint(str(eng))
    (eng / "static_model.py").write_text("x = 2\n")
    assert a and HG.engine_fingerprint(str(eng)) != a and HG.engine_fingerprint(None) is None


def test_angle_brace_buckles_about_its_v_axis():
    """New section families (HR main IS 808 tables): a single-angle brace uses r_vv (r_min of the table)."""
    from pushover import india_materials as IM
    b = IM.brace_strengths("ISA100X100X10", 2500.0, 250.0)
    assert b["r_mm"] == pytest.approx(19.7) and b["cls"] == "c"
    assert IM.brace_strengths("CHS168.3X6.3", 4000.0, 310.0)["r_mm"] > 50.0


# ------------------------------------------------------------------ P2 / stage 2: resumable analyses
class _FakeOps:
    """A scripted 'OpenSees': at the states (converged-step counts) in `hard`, Newton fails and the second algorithm
    converges -- an outcome that depends on the state and the settings only, as in OpenSees (a failed call reverts)."""
    def __init__(self, hard, t0=0.0):
        self.hard, self.n, self.t, self.u, self.calls, self.alg = set(hard), 0, t0, 0.0, 0, "Newton"

    def algorithm(self, name):
        self.alg = name

    def analyze(self, n=1):
        self.calls += 1
        if self.alg == "Newton" and self.n in self.hard:
            return -3
        self.n += 1; self.t += 0.1; self.u += 0.01 * self.t
        return 0

    def getTime(self):
        return self.t

    def getNodeTags(self):
        return [1]

    def nodeDisp(self, n):
        return [self.u, 0.0, 0.0]


def _scripted_run(ops, n_steps):
    """A tiny step loop shaped like the sweeps: Newton, on failure a second algorithm, record the converged steps."""
    hist = []
    while len(hist) < n_steps:
        ok = ops.analyze(1)
        if ok != 0:
            ops.algorithm("Krylov"); ok = ops.analyze(1); ops.algorithm("Newton")
        hist.append((round(ops.getTime(), 6), round(ops.nodeDisp(1)[0], 9)))
    return hist


def test_journal_replays_converged_calls_and_skips_failed_ones(tmp_path):
    from snl import checkpoint as CK
    hard = {1, 3, 4, 6}
    full = _scripted_run(_FakeOps(hard), 8)
    path = str(tmp_path / "j.ckpt")
    o1 = _FakeOps(hard)
    J = CK.Journal(path, key="k", max_live_calls=6).begin("seg", o1)
    with pytest.raises(CK.ChunkExpired):
        _scripted_run(o1, 8)
    J.end()
    o2 = _FakeOps(hard)                              # a fresh process: the same code from the start
    J2 = CK.Journal(path, key="k").begin("seg", o2)
    part = _scripted_run(o2, 8)
    J2.end()
    assert part == full
    assert J2.data["chunks"] == 2 and J2.data["replayed_calls"] == 6
    # the journaled failures (calls 2 and 5) were answered from the journal, not computed
    assert o2.calls == 12 - 2
    J3 = CK.Journal(path, key="other")                 # a different key never replays
    assert J3.data["segments"] == {}


def test_journal_refuses_a_replay_that_lands_elsewhere(tmp_path):
    from snl import checkpoint as CK
    path = str(tmp_path / "j.ckpt")
    o1 = _FakeOps(set())
    J = CK.Journal(path, key="k", max_live_calls=2).begin("seg", o1)
    with pytest.raises(CK.ChunkExpired):
        _scripted_run(o1, 4)
    J.end()
    o2 = _FakeOps(set(), t0=5.0)                     # "another model"
    J2 = CK.Journal(path, key="k").begin("seg", o2)
    with pytest.raises(CK.ReplayDiverged):
        _scripted_run(o2, 4)
    J2.end()


def test_chunked_pushover_repeats_the_uninterrupted_one(tmp_path):
    """The real OpenSees EBF push of the P1 test, interrupted after 12 converged calls and resumed in a rebuilt model:
    the same curve, bit for bit (deterministic replay)."""
    from snl import checkpoint as CK
    import openseespy.opensees as ops
    full, _, _ = _push("Y", str(tmp_path), n=30)
    path = str(tmp_path / "push.ckpt")
    J = CK.Journal(path, key="ebf", max_live_calls=12).begin("push Y", ops)
    with pytest.raises(CK.ChunkExpired):
        _push("Y", str(tmp_path), n=30)
    J.end()
    J2 = CK.Journal(path, key="ebf").begin("push Y", ops)
    again, _, _ = _push("Y", str(tmp_path), n=30)
    J2.end()
    assert again == full and J2.data["replayed_calls"] == 12


def _fake_journal(ck, calls, done=()):
    import pickle
    os.makedirs(ck, exist_ok=True)
    pickle.dump(dict(version=1, key="k", done={d: {} for d in done}, segments={"push Y": [(0, 1.0, 1.0, 1.0)] * calls}),
                open(os.path.join(ck, "pushover.ckpt"), "wb"))


def test_orchestrator_runs_steps_in_order_and_resumes(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import nl_orchestrate as NO
    job = tmp_path / "IN_ExT"; job.mkdir()
    q = str(tmp_path / "queue.json")
    NO.main(["plan", "--queue", q, "--jobs", str(job), "--analyses", "pushover", "ddm", "--python", "py", "--heavy", "H"])
    d = NO.load(q)
    assert [s["id"] for s in d["steps"]] == ["IN_ExT/gravity", "IN_ExT/pushover", "IN_ExT/ddm", "IN_ExT/report"]
    calls = []
    script = {"pushover": [75, 0], "ddm": [0], "gravity": [0], "report": [0]}

    def runner(cmd, **kw):
        kind = next(k for k in script if (k == "gravity" and "snl.hr_gravity" in cmd) or (k == "report" and cmd[-2:-1] == ["report"])
                    or (k == "pushover" and "pushover" in cmd and "run" in cmd) or (k == "ddm" and "steltic_ddm" in cmd))
        calls.append((kind, cmd[:4], "--deadline" in cmd, "--chunk-seconds" in cmd))
        rc = script[kind].pop(0)
        if kind == "pushover":                                       # the chunk journals its calls (progress)
            _fake_journal(NO._opt(cmd, "--checkpoint-dir"), 40 if rc else 0, () if rc else ("push Y",))
        return rc
    args = argparse_ns(queue=q, budget=7000.0, max_steps=0, dry_run=False, stop_on_failure=False)
    NO.next_steps(args, runner=runner)
    d = NO.load(q)
    assert [c[0] for c in calls] == ["gravity", "pushover", "pushover", "ddm", "report"]
    assert all(c[1][:2] == ["H", "py"] and c[1][3] == "_exec" and c[2] for c in calls)   # under heavy, deadline in the slot
    assert [c[3] for c in calls] == [False, True, True, True, False]
    assert all(s["state"] == "done" for s in d["steps"]) and len(d["steps"][1]["chunks"]) == 2
    assert d["steps"][1]["chunks"][0]["progress"] == [0, 40]
    log = open(q + ".runtime.log").read().splitlines()
    assert len(log) == 5 and "rc=75" in log[1] and "state=resume" in log[1]


def test_orchestrator_marks_a_step_without_progress_stalled(tmp_path):
    """Review M3: a chunk with real time that keeps nothing new, an exit 76 (no progress), or too many chunks: the step is
    `stalled` with its reason and is not run again; the other jobs go on."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import nl_orchestrate as NO
    jobs = [tmp_path / "IN_ExA", tmp_path / "IN_ExB"]
    for j in jobs:
        j.mkdir()
    q = str(tmp_path / "queue.json")
    NO.main(["plan", "--queue", q, "--jobs", *map(str, jobs), "--analyses", "pushover", "--python", "py", "--heavy", "H"])
    seen = []

    def runner(cmd, **kw):
        if not ("pushover" in cmd and "run" in cmd):
            return 0
        job = cmd[cmd.index("run") + 1]
        seen.append(os.path.basename(job))
        ck = NO._opt(cmd, "--checkpoint-dir")
        if job.endswith("IN_ExA"):                                    # replays its journal, keeps nothing new
            _fake_journal(ck, 40)
            return 75
        kw["stdout"].write(">> NO PROGRESS pushover Y: push Y: replaying its 900 journaled calls recomputes 7000 s\n")
        return 76
    _fake_journal(str(jobs[0] / "nl_checkpoints" / "pushover"), 40)
    args = argparse_ns(queue=q, budget=7000.0, max_steps=0, dry_run=False, stop_on_failure=False)
    NO.next_steps(args, runner=runner)
    d = NO.load(q)
    st = {s["id"]: s for s in d["steps"]}
    assert seen == ["IN_ExA", "IN_ExB"]                               # each tried once, neither looped
    assert st["IN_ExA/pushover"]["state"] == "stalled" and "kept nothing new" in st["IN_ExA/pushover"]["stalled_reason"]
    assert st["IN_ExB/pushover"]["state"] == "stalled" and "900 journaled calls" in st["IN_ExB/pushover"]["stalled_reason"]
    assert st["IN_ExA/report"]["state"] == "pending"                   # not run after a stalled analysis
    assert NO.MAX_CHUNKS_PER_STEP > 2


def argparse_ns(**kw):
    import argparse
    return argparse.Namespace(**kw)


def test_a_diverged_replay_restarts_live(tmp_path):
    """restart_live drops the segment and runs it again live: the result is the uninterrupted one."""
    from snl import checkpoint as CK
    path = str(tmp_path / "j.ckpt")
    o1 = _FakeOps(set())
    J = CK.Journal(path, key="k", max_live_calls=2).begin("seg", o1)
    with pytest.raises(CK.ChunkExpired):
        _scripted_run(o1, 4)
    J.end()
    o2 = _FakeOps(set(), t0=5.0)
    J2 = CK.Journal(path, key="k").begin("seg", o2)
    with pytest.raises(CK.ReplayDiverged):
        _scripted_run(o2, 4)
    o3 = _FakeOps(set(), t0=5.0)
    J2.restart_live("seg", o3)
    out = _scripted_run(o3, 4)
    J2.end()
    assert out == _scripted_run(_FakeOps(set(), t0=5.0), 4) and J2.data["diverged"] == 1


# ------------------------------------------------------------------ IN_Ex21: angle-truss shed (truss members, double angles)
EX21 = os.environ.get("STELTIC_EX21_JOB", os.path.join(GOLD, "IN_Ex21_MSME_angle_truss_shed_Hosur"))


def test_double_angle_properties_are_the_hr_ones():
    """2ISA70X70X6 on an 8 mm gusset, connected leg D: the HR model's element properties (A 1 630 mm2, in-plane
    I 760 000 mm4 in the beam's major slot, out-of-plane I 1 667 845 mm4)."""
    from pushover import india_sections as IS_, india_materials as IM
    p = IS_.register_double_angle("2ISA70X70X6", "ISA70X70X6", 8.0, "D")
    assert p["A"] == pytest.approx(1630.0) and p["Ix"] == pytest.approx(760000.0)
    assert p["Iy"] == pytest.approx(1667844.8, rel=1e-6) and p["r_min"] == pytest.approx(math.sqrt(760000.0 / 1630.0))
    sp = IM.section_props_mm("2ISA70X70X6")
    assert sp["type"] == "DOUBLE_ANGLE" and sp["double_angle"] and not sp["welded_i"]
    assert IM.buckling_classes(sp)["zz"] == "c"
    b = IM.brace_strengths("2ISA70X70X6", 1500.0, 250.0)
    assert b["r_mm"] == pytest.approx(math.sqrt(760000.0 / 1630.0)) and b["A_mm2"] == pytest.approx(1630.0)


def test_double_angle_fibre_section_stiffness():
    """The fibre section of a double angle (a cantilever chord along X, depth along local z) has the registry's
    in-plane and out-of-plane EI within 5 % (strips scaled to the catalogue area; fillets left out)."""
    import openseespy.opensees as ops
    from pushover import india_sections as IS_
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    p = IS_.register_double_angle("2ISA70X70X6", "ISA70X70X6", 8.0, "D")
    L = 2000.0
    for dof, I in ((3, p["Ix"]), (2, p["Iy"])):          # tip load along global Z (in plane), along Y (out of plane)
        ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
        ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0); ops.fix(1, 1, 1, 1, 1, 1, 1)
        ops.geomTransf("Linear", 1, 0.0, 0.0, 1.0)
        b = FiberSectionBuilder(ops, Fy=250.0, units="N-mm", residual="none")
        b.double_angle(1, "2ISA70X70X6", axis="z")
        ops.beamIntegration("Lobatto", 1, 1, 5)
        ops.element("forceBeamColumn", 1, 1, 2, 1, 1)
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        f = [0.0] * 6; f[dof - 1] = 100.0; ops.load(2, *f)
        ops.constraints("Plain"); ops.numberer("Plain"); ops.system("BandGeneral"); ops.test("NormDispIncr", 1e-10, 20)
        ops.algorithm("Newton"); ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        assert ops.analyze(1) == 0
        I_fib = 100.0 * L ** 3 / (3.0 * 200000.0 * abs(ops.nodeDisp(2, dof)))
        assert I_fib == pytest.approx(I, rel=0.05), (dof, I_fib, I)
    ops.wipe()


def test_truss_members_are_nonlinear_axial_members(tmp_path):
    """A member of kind `truss` (IN_Ex21 diagonals, verticals and knee braces) gets the brace backbone, as `brace`."""
    from pushover import nonlinear_model as NM, hinge_models as HM
    os.environ["SNL_PLASTICITY"] = "fibre"
    pkg = _ebf_pkg("X", str(tmp_path))
    for t in (41, 42):
        pkg.schedule[t] = dict(member="truss", section=BRACE, role="truss_knee_brace")
    hinges, stats = NM.build_nonlinear(pkg, HM.load_params(None, jurisdiction="india"), {}, verbose=False, plasticity="fibre")
    assert stats["brace_nonlinear"] == 2 and {h["kind"] for t, h in hinges.items() if t in (41, 42)} == {"brace"}


def test_ex21_package_builds():
    """The IN_Ex21 gold (when present): every truss member is a nonlinear axial member, the double-angle chords are
    fibre members, and the gravity analysis converges."""
    if not os.path.isdir(EX21):
        pytest.skip("IN_Ex21 gold job not available")
    import contextlib, io
    from collections import Counter
    from pushover import package_reader as PR, nonlinear_model as NM, hinge_models as HM
    os.environ["SNL_PLASTICITY"] = "fibre"
    with contextlib.redirect_stdout(io.StringIO()):
        pkg = PR.load(EX21)
        prm = HM.load_params(None, jurisdiction="india")
        loads, gtable = NM.gravity_loads(pkg, prm)
        PG = NM.column_gravity_axials(pkg, loads)
        hinges, stats = NM.build_nonlinear(pkg, prm, PG, verbose=False, plasticity="fibre")
        ok = NM._apply_gravity(loads)
    roles = Counter((pkg.schedule.get(h["ele"]) or {}).get("role") for h in hinges.values() if h["kind"] == "brace")
    n_truss = sum(1 for r in pkg.schedule.values() if r.get("member") == "truss")
    assert sum(v for k, v in roles.items() if str(k).startswith("truss_")) == n_truss and roles["truss_knee_brace"] > 0
    assert ok == 0


def test_single_angle_fibre_section_buckles_about_v_v():
    """IS 808 single angle (IN_Ex21 webs and knee braces) in the DDM: the fibre section's weakest principal stiffness
    is the catalogue v-v one (A r_min^2) within 6 %, from a cantilever loaded normal to the v-v axis."""
    import openseespy.opensees as ops
    from pushover import india_materials as IM
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    p = IM.section_props_mm("ISA60X60X6")
    Iv_cat = p["A"] * p["r_min"] ** 2
    L, F = 2000.0, 100.0
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0); ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, 0.0, 0.0, 1.0)                 # local y = global Y, local z = global Z
    b = FiberSectionBuilder(ops, Fy=250.0, units="N-mm", residual="none")
    r = b.single_angle(1, "ISA60X60X6", axis="z")
    assert r["Iv"] == pytest.approx(Iv_cat, rel=0.06) and r["Ix"] == pytest.approx(p["Ix"], rel=0.06)
    ops.beamIntegration("Lobatto", 1, 1, 5); ops.element("forceBeamColumn", 1, 1, 2, 1, 1)
    u = (1.0 / math.sqrt(2.0), 1.0 / math.sqrt(2.0))           # along the symmetry line u-u (heel to centroid): bending about v-v
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1); ops.load(2, 0.0, F * u[0], F * u[1], 0.0, 0.0, 0.0)
    ops.constraints("Plain"); ops.numberer("Plain"); ops.system("BandGeneral"); ops.test("NormDispIncr", 1e-10, 20)
    ops.algorithm("Newton"); ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    assert ops.analyze(1) == 0
    d = ops.nodeDisp(2, 2) * u[0] + ops.nodeDisp(2, 3) * u[1]
    assert F * L ** 3 / (3.0 * 200000.0 * d) == pytest.approx(Iv_cat, rel=0.06)
    ops.wipe()


def test_bottom_chord_ties_read_from_the_design():
    """The bottom-chord tie stations: a declared list wins; else every Ly the design used (member_overrides); else none."""
    from steltic_ddm import peb_restraints as PR
    cfg = {"member_overrides": {"truss_bottom_chord:2ISA70X70X6": {"Ly_mm": 4500.0}}}
    assert PR._bottom_chord_ties(cfg, {}, 0.0, 18000.0)[0] == [4500.0, 9000.0, 13500.0]
    assert PR._bottom_chord_ties(cfg, {"bottom_chord_ties_mm": [6000.0, 12000.0]}, 0.0, 18000.0) == \
        ([6000.0, 12000.0], "roof plane bottom_chord_ties_mm")
    assert PR._bottom_chord_ties({}, {}, 0.0, 18000.0) == ([], None)


def test_ex21_ddm_truss_restraints_and_gate():
    """IN_Ex21 gold (when present) in the DDM GMNIA: purlins at the 11 inner top-chord panel points of each inner truss
    (the gable trusses are tied by the HR model), bottom-chord ties at 4.5 / 9.0 / 13.5 m, the column girts / fly
    braces; angle fibres; the gravity gate within +/-5 % of the HR forces."""
    if not os.path.isdir(EX21):
        pytest.skip("IN_Ex21 gold job not available")
    import contextlib, io, shutil, tempfile
    from steltic_ddm import ingest, loads, india_checks as IC, peb_restraints as PR
    d = tempfile.mkdtemp(); job = os.path.join(d, "ex21")
    shutil.copytree(EX21, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html", "rag", "secondary"))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            nm = ingest.load_package(job, os.environ.get("STELTIC_ENGINE_DIR"))
            pl = PR.plan(nm, nm.cfg)
            combos = [c for c in loads.prune(loads.steltic_combos(nm.cfg, nm=nm)) if c[0] == "1.5DL+1.5LL"]
            g = IC.gravity_gate(nm, nm.cfg, combos)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    c = pl["counts"]
    assert c["truss_top_chord_lateral"] == 5 * 11 and c["truss_bottom_chord_lateral"] == 7 * 3
    assert c["column_lateral"] > 0 and pl["truss_basis"][0]["bottom_chord_ties_mm"] == [4500.0, 9000.0, 13500.0]
    assert not [r for r in g["rows"] if not r["ok"]]


def test_india_design_criteria_page_in_public_words(tmp_path):
    """The India design-criteria draft (docx + html for the hub) says 'design engineer', and its page carries no
    sweep-status key, plan key path or role key (P10)."""
    job = os.path.join(GOLD, "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore")
    if not os.path.isdir(job) or not ENGINE:
        pytest.skip("IN_Ex10 gold job or HR engine not available")
    import contextlib, io, re
    from nlrha import design_criteria as DC
    from snl import public_text as PT
    with contextlib.redirect_stdout(io.StringIO()):
        docx, html = DC.write(job, out=str(tmp_path))
    h = open(html, encoding="utf-8").read()
    vis = re.sub(r"(?s)<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", h))
    assert "design engineer" in vis and "engineer of record" not in vis.lower()
    assert "NO_LIMIT_POINT" not in vis and "nl_plan" not in vis and PT.words(vis) == vis


# ------------------------------------------------------------------ review fixes (NL_REVIEW.md)
def _ddm_stubs(monkeypatch, log):
    """The DDM worker's collaborators as small stand-ins: a fake OpenSees (a counter), a model the sweep 'builds'
    (as solver.sweep -> build().prepare()), a classify that needs the built model (as the real one: model._bt)."""
    import types
    from steltic_ddm import cli, solver, ingest, loads

    class Ops:
        t = 0.0
        def analyze(self, n=1):
            self.t += 1.0; return 0
        def getTime(self):
            return self.t
        def getNodeTags(self):
            return [1, 2]
        def nodeDisp(self, n):
            return [0.1 * self.t * n, 0.0, 0.0]
    ops = Ops()
    monkeypatch.setattr(solver, "ops", ops)
    mem = [types.SimpleNamespace(tag=7, kind="beam", role="floor", section="WPB220X220X71.47"),
           types.SimpleNamespace(tag=8, kind="brace", role="brace", section="CHS114.3X3.6")]
    nm = types.SimpleNamespace(cfg={}, members=mem)
    combos = [("1.5DL+1.5LL", 1.5, 1.5), ("1.2DL+1.2LL+1.2EQ_X", 1.2, 1.2)]
    monkeypatch.setattr(ingest, "load_package", lambda job, eng: (log.append("ingest"), nm)[1])
    monkeypatch.setattr(loads, "steltic_combos", lambda cfg, nm=None: combos)
    monkeypatch.setattr(loads, "present_sets", lambda nm: {})

    class G:
        def __init__(self, nm, cfg, **kw):
            log.append("model"); ops.t = 0.0                  # a new model: wipe
            self.psi, self.builder = kw["out_of_plumb"][1], types.SimpleNamespace(log=[(1, "WPB220X220X71.47", "I", 40, "")])
    monkeypatch.setattr(cli, "GMNIAModel", G)

    def sweep(g, combo, pres, dlam, max_steps, verbose, time_limit, strain_cap, capture_lambda1):
        g._bt, g.elems = {7: 1}, [dict(mtag=7, tag=100701), dict(mtag=8, tag=100801)]      # build().prepare()
        hist = []
        for i in range(6):
            assert solver.ops.analyze(1) == 0
            hist.append((round(combo[1] * solver.ops.getTime() / 6.0, 4), 0.1 * i))
        y = 1.0 + g.psi * 100.0 + combo[1]
        return dict(status="LIMIT_POINT", termination="limit_point", lambda_u=hist[-1][0], lambda_end=hist[-1][0],
                    steps=6, seconds=1.0, hist=hist, frames=[], log=[],
                    snapshot=dict(yield_ratio={100701: y, 100801: 0.4}, braces={100801: dict(N=-12.0, offset=0.01, buckled=True)},
                                  disp={1: [0.1, 0.0, 0.0]}, drifts=None, step=6))
    monkeypatch.setattr(solver, "sweep", sweep)
    monkeypatch.setattr(solver, "classify", lambda res, g: dict(mechanism="beam hinge" if g._bt else "", buckled_braces=[8]))
    return cli


def test_ddm_resume_returns_finished_sweeps_whole_and_builds_nothing(tmp_path, monkeypatch):
    """Review H1: a retry with a gravity combination (four imperfection cases) and a lateral one. Chunk 1 finishes two
    sweeps, expires inside the third, and has no budget for the rest. Chunk 2 returns the two finished sweeps unchanged
    (mechanism and member state included) without ingesting or building anything, resumes the third by replay, and
    completes the others -- every result equal to an uninterrupted run."""
    from snl import checkpoint as CK
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    log = []
    cli = _ddm_stubs(monkeypatch, log)
    job = str(tmp_path / "job"); os.makedirs(job)
    open(os.path.join(job, "model_opensees.py"), "w").write("# model\n")
    imps = [dict(tag=t, dir=t[1], psi=s / 200.0, bow_sign=s) for t, s in (("+X", 1), ("-X", -1), ("+Y", 1), ("-Y", -1))]
    tasks = [("1.5DL+1.5LL", i) for i in imps] + [("1.2DL+1.2LL+1.2EQ_X", imps[0])]
    base = dict(nsub=(2, 2, 4), residual="none", hardening=0.002, fast=False, nip=5, bow=0.001, max_steps=50,
                time_limit=600.0, dlam=0.05, retry_factors=(2, 4), india=False)
    ref = [cli._worker((job, None, c, i, dict(base))) for c, i in tasks]          # uninterrupted, no journal
    ck = dict(dir=str(tmp_path / "ck"), budget_s=None, t0=None)
    real_jf = cli._journal_for
    limits = {1: None, 2: None, 3: 3, 4: 0, 5: 0}                               # live calls allowed in chunk 1, per task
    state = {"n": 0}

    def jf_chunk1(job_, combo_label, imp, opts):
        J = real_jf(job_, combo_label, imp, opts)
        state["n"] += 1
        J.max_live_calls = limits[state["n"]]
        return J
    monkeypatch.setattr(cli, "_journal_for", jf_chunk1)
    c1 = [cli._worker((job, None, c, i, dict(base, _checkpoint=ck))) for c, i in tasks]
    assert [bool(r.get("resume")) for r in c1] == [False, False, True, True, True]
    assert c1[0] == ref[0] and c1[1] == ref[1]
    monkeypatch.setattr(cli, "_journal_for", real_jf)
    del log[:]
    c2 = [cli._worker((job, None, c, i, dict(base, _checkpoint=ck))) for c, i in tasks]
    assert c2 == ref                                                               # identical, every key
    assert c2[0]["cls"]["mechanism"] == "beam hinge" and c2[0]["state"] == ref[0]["state"]
    assert log.count("ingest") == 3 and log.count("model") == 3                    # nothing built for the finished two
    c3 = [cli._worker((job, None, c, i, dict(base, _checkpoint=ck))) for c, i in tasks]
    assert c3 == ref and log.count("model") == 3                                   # a third chunk: all from the journal


def _clocked(monkeypatch, CK, start):
    import time as _t, types
    clock = [float(start)]
    monkeypatch.setattr(CK, "time", types.SimpleNamespace(time=lambda: clock[0], strftime=_t.strftime))
    monkeypatch.delenv("SNL_DEADLINE", raising=False)
    return clock


def _timed_ops(clock, per_call):
    ops = _FakeOps(set())
    real = ops.analyze

    def analyze(n=1):
        clock[0] += per_call[0]
        return real(n)
    ops.analyze = analyze
    return ops


def _journal_with(tmp_path, monkeypatch, CK, n_calls, seconds_each):
    """A journal of one piece with n converged calls of `seconds_each` each (a live chunk at clock 1000)."""
    clock = _clocked(monkeypatch, CK, 1000.0)
    p = str(tmp_path / "j.ckpt")
    J = CK.Journal(p, "k", budget_s=None, t_start=1000.0)
    ops = _timed_ops(clock, [seconds_each])
    J.begin("piece", ops)
    for _ in range(n_calls):
        assert ops.analyze(1) == 0
    J.end(); J.save()
    return p, clock


def test_a_replay_longer_than_a_chunk_stops_with_a_reason(tmp_path, monkeypatch):
    """Review M3: a piece whose converged steps alone take more than a chunk can never advance in chunks -- NoProgress
    with a reason at the start of the replay (never a loop of killed chunks); one that fits a fresh chunk but not what
    is left of this one is ChunkExpired (exit 75)."""
    from snl import checkpoint as CK
    p, clock = _journal_with(tmp_path, monkeypatch, CK, 5, 18.0)            # 90 s of converged steps
    clock[0] = 2000.0
    J = CK.Journal(p, "k", budget_s=100.0, t_start=2000.0)
    assert J.replay_seconds("piece") == pytest.approx(90.0)
    with pytest.raises(CK.NoProgress, match="more than 80 % of a 100 s chunk"):
        J.begin("piece", _timed_ops(clock, [0.0]))
    J = CK.Journal(p, "k", budget_s=200.0, t_start=2000.0 - 150.0)        # fits a fresh 200 s chunk, 50 s left here
    with pytest.raises(CK.ChunkExpired):
        J.begin("piece", _timed_ops(clock, [0.0]))
    assert not CK.progress_possible(90.0, 100.0) and CK.progress_possible(90.0, 200.0)


def test_the_budget_is_checked_during_a_replay(tmp_path, monkeypatch):
    """Review M3: the replay itself watches the budget. A replay that started with (nearly) a whole chunk and still ran
    out is NoProgress; one that started late in a chunk is ChunkExpired."""
    from snl import checkpoint as CK
    p, clock = _journal_with(tmp_path, monkeypatch, CK, 5, 1.0)             # 5 s recorded
    for t_start, exc in ((3000.0, CK.NoProgress), (3000.0 - 50.0, CK.ChunkExpired)):
        clock[0] = 3000.0
        J = CK.Journal(p, "k", budget_s=100.0, t_start=t_start)
        ops = _timed_ops(clock, [200.0])                                     # the replay is far slower this time
        J.begin("piece", ops)
        with pytest.raises(exc):
            for _ in range(5):
                ops.analyze(1)
        J.end()


def test_a_piece_diverging_again_after_a_restart_stops(tmp_path, monkeypatch):
    """Review M3: one live restart per piece over all chunks; a replay that diverges again is NoProgress."""
    from snl import checkpoint as CK
    p, clock = _journal_with(tmp_path, monkeypatch, CK, 3, 1.0)
    J = CK.Journal(p, "k", budget_s=None, t_start=clock[0])
    ops = _timed_ops(clock, [0.0])
    J.begin("piece", ops)
    J.restart_live("piece", ops)                                             # chunk 1: the first divergence
    J.end(); J.save()
    J2 = CK.Journal(p, "k", budget_s=None, t_start=clock[0])                 # chunk 2: it diverges again
    J2.begin("piece", ops)
    with pytest.raises(CK.NoProgress, match="diverged in 2 chunks"):
        J2.restart_live("piece", ops)


def test_nlrha_record_longer_than_a_chunk_is_not_retried_forever():
    """Review M3: a record that already had (nearly) a whole chunk and did not finish stops the command (no progress);
    one that started late in a chunk is retried in a fresh one; before the first record nothing is known."""
    from nlrha.cli import record_chunk_decision as D
    assert D([6400.0], 6600.0, 6600.0, []) == "no_progress"
    assert D([900.0], 6600.0, 6600.0, [300.0]) == "run" and D([900.0], 600.0, 6600.0, [300.0]) == "resume"
    assert D([], 6600.0, 6600.0, []) == "run" and D([], 100.0, 6600.0, [300.0]) == "resume"
    assert D([], None, None, [300.0]) == "run"


def test_cache_and_journal_keys_cover_every_input(tmp_path, monkeypatch):
    """Review M4 / M5: the NLRHA record cache, the pushover journal and the DDM journal are invalidated by a change of
    the record data (same length), the member subdivisions, the fibre settings, gravity-elastic members, an outside
    --params file, the HR engine, and the analysis code including pushover/postprocess.py and pushover/cli.py."""
    import argparse, shutil, types
    from snl import checkpoint as CK
    from nlrha import cli as NC
    from pushover import cli as PC
    from steltic_ddm import cli as DC
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    for k in list(os.environ):
        if k.startswith("SNL_") and k not in CK.NON_MODEL_ENV:
            monkeypatch.delenv(k)
    job = tmp_path / "job"; job.mkdir()
    (job / "model_opensees.py").write_text("# model\n")
    prm = tmp_path / "outside_params.json"; prm.write_text('{"a": 1}')
    pkg = types.SimpleNamespace(root=str(job))
    rec = dict(id=7, sf=1.2, x_comp="H1", dt=0.01, a1=[0.0, 0.1, -0.2], a2=[0.0, 0.05, 0.1])
    nj = lambda r=rec: (str(job), str(prm), None, None, None, r, 0.025, 0.01, 2.0, None, "hht", True)   # noqa: E731
    args = argparse.Namespace(checkpoint_dir=str(tmp_path / "ck"), params=str(prm), max_drift=0.1, stop_at=0.8, tail="auto",
                              member_nseg=4, gravity_elastic=None, plasticity="fibre", dirs=["X", "Y"], chunk_seconds=None)
    imp = dict(tag="+X", dir="X", psi=1 / 200.0, bow_sign=1)
    opts = dict(nsub=(2, 2, 4), _checkpoint=dict(dir=str(tmp_path / "dck"), budget_s=None, t0=None))

    def keys():
        return (NC.record_cache_key(pkg, "MCE", nj()), PC._journal(args, pkg).key,
                DC._journal_for(str(job), "1.5DL+1.5LL", imp, opts).key)
    base = keys()

    def changed(label):
        k = keys()
        assert all(a != b for a, b in zip(k, base)) or label == "record", label
        return k
    rec2 = dict(rec, a1=[0.0, 0.1, -0.25])                                   # the same length, other data
    assert NC.record_cache_key(pkg, "MCE", nj(rec2)) != base[0]
    for var, val in (("SNL_MEMBER_NSEG", "8"), ("SNL_FIBRE_NIP", "7"), ("SNL_GRAVITY_ELASTIC", "0")):
        monkeypatch.setenv(var, val); changed(var); monkeypatch.delenv(var)
    assert keys() == base
    prm.write_text('{"a": 2}')
    k = keys(); assert k[0] != base[0] and k[1] != base[1]                    # the DDM does not read --params
    prm.write_text('{"a": 1}')
    monkeypatch.setattr(CK, "engine_key", lambda: "another engine"); changed("engine"); monkeypatch.undo()
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    for k_ in list(os.environ):
        if k_.startswith("SNL_") and k_ not in CK.NON_MODEL_ENV:
            monkeypatch.delenv(k_)
    assert keys() == base
    # the code: a copy of the analysis files with postprocess.py, then cli.py, edited
    root = tmp_path / "code"
    for rel in CK.ANALYSIS_FILES:
        src = os.path.join(ROOT, rel)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(root / rel), exist_ok=True); shutil.copy(src, root / rel)
    monkeypatch.setattr(CK, "__file__", str(root / "snl" / "checkpoint.py"))
    c0 = CK.code_key()
    assert c0 == CK.code_key() and "pushover/postprocess.py" in CK.ANALYSIS_FILES and "pushover/cli.py" in CK.ANALYSIS_FILES
    for rel in ("pushover/postprocess.py", "pushover/cli.py"):
        with open(root / rel, "a") as f:
            f.write("\n# changed\n")
        c1 = CK.code_key(); assert c1 != c0, rel; c0 = c1
        changed(rel)


def _spring_to(bld, mt, K, e, theta_in):
    """Drive one zeroLength carrying spring material `mt` to an inelastic rotation theta_in; returns (V, inelastic, total)."""
    import openseespy.opensees as ops
    from pushover import fibre_model as FM
    ops.node(1, 0, 0, 0); ops.node(2, 0, 0, 0); ops.fix(1, 1, 1, 1, 1, 1, 1); ops.fix(2, 1, 1, 0, 1, 1, 1)
    ops.uniaxialMaterial("Elastic", 990001, 1e12)
    ops.element("zeroLength", 9, 1, 2, "-mat", 990001, 990001, mt, 990001, 990001, 990001, "-dir", 1, 2, 3, 4, 5, 6,
                "-orient", 1, 0, 0, 0, 1, 0)
    FM.LINK_K[9] = K
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1); ops.sp(2, 3, 1.0)
    ops.constraints("Penalty", 1e14, 1e14); ops.numberer("Plain"); ops.system("FullGeneral")
    ops.test("NormDispIncr", 1e-12, 30); ops.algorithm("Newton")
    n = 400
    target = None
    for i in range(1, n + 1):                         # imposed deformation, in steps up to 0.12 e
        ops.integrator("LoadControl", 0.12 * e / n); ops.analysis("Static"); assert ops.analyze(1) == 0
        g = FM.link_rotation(9, e)
        if g >= theta_in:
            target = (ops.eleResponse(9, "basicForce")[2], g, FM.link_rotation(9, e, inelastic=False))
            break
    return target


def test_link_spring_reaches_the_is18168_overstrength_at_the_rotation_limit():
    """Review L6 / L2 / L5: the calibrated post-yield slope takes the spring to Sh x V_pL (IS 18168:2023 12.3.2.2: 1.25 I,
    1.4 box) at 0.08 rad of INELASTIC rotation (12.3.3.1); the reported rotation is the inelastic one, the total less
    V / K over e; a box link has two webs; e V_pL / M_pL is checked against 1.6 (11.3)."""
    import openseespy.opensees as ops
    from unittest import mock
    from pushover import india_materials as IM
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    real = IM.section_props_mm
    for box, Sh in ((False, 1.25), (True, 1.4)):
        ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
        b = FiberSectionBuilder(ops, Fy=250.0, units="N-mm", residual="none")
        with mock.patch.object(IM, "section_props_mm", lambda lab: dict(real("WPB400X300X155.26"), box=box)):
            mt, rec = b.link_shear_spring("WPB400X300X155.26", 250.0, 900.0)
        assert rec["box"] is box and rec["Sh"] == Sh and rec["short_link"] and rec["e_Vp_over_Mp"] < 1.6
        sp = real("WPB400X300X155.26")
        assert rec["Aw_mm2"] == pytest.approx((2 if box else 1) * (sp["d"] - 2 * sp["tf"]) * sp["tw"])
        assert rec["overstrength_at_limit"] == pytest.approx(Sh)
        V, g_in, g_tot = _spring_to(b, mt, rec["K"], 900.0, 0.08)
        assert V / (rec["Vp_kN"] * 1e3) == pytest.approx(Sh, rel=0.01)
        assert g_in == pytest.approx(g_tot - V / rec["K"] / 900.0, rel=1e-9) and g_tot - g_in > rec["gamma_y"]
    ops.wipe()
    b = FiberSectionBuilder(ops, Fy=250.0, units="N-mm", residual="none")
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    _, long_ = b.link_shear_spring("WPB400X300X155.26", 250.0, 4000.0)       # a 4 m "link": not short (11.3)
    assert not long_["short_link"] and long_["e_Vp_over_Mp"] > 1.6 and "NOT a short link" in b.log[-1][4]
    ops.wipe()


def test_link_shear_strength_takes_the_web_band():
    """Review L4: WPB500X300X187.34 E250 -- the member fy is the 28 mm flange's band (240 MPa), the link shear takes the
    14.5 mm web's (250 MPa); the expected-strength factor is kept; a section whose web shares the band is unchanged."""
    from pushover import india_materials as IM
    fy, note = IM.link_web_fy("WPB500X300X187.34", dict(grade="E250", fy_MPa=240.0, fye_MPa=264.0))
    assert fy == pytest.approx(264.0 * 250.0 / 240.0) and "web" in note and "250" in note
    assert IM.link_web_fy("WPB220X220X71.47", dict(grade="E250", fy_MPa=250.0, fye_MPa=250.0)) == (250.0, None)
    assert IM.link_web_fy("CHS114.3X3.6", dict(grade="YSt310", fy_MPa=310.0, fye_MPa=310.0)) == (310.0, None)


def test_a_link_the_models_cannot_carry_is_refused(tmp_path):
    """Review L7: a released link (DDM) or a link that is not the HR model's unreleased Timoshenko element (pushover)
    raises instead of silently becoming an ordinary member without its shear yielding."""
    import types
    from steltic_ddm.model_gmnia import GMNIAModel
    from pushover import nonlinear_model as NM, hinge_models as HM
    g = GMNIAModel.__new__(GMNIAModel)
    g.nsub_col = g.nsub_beam = g.nsub_brace = 2
    g._transf_for = lambda m: 3
    with pytest.raises(ValueError, match="end releases"):
        g._add_member(types.SimpleNamespace(tag=30, kind="beam", role="link", relz=3, rely=0, n1=5, n2=6, section="X"))
    os.environ["SNL_PLASTICITY"] = "fibre"
    pkg = _ebf_pkg("X", str(tmp_path))
    e = next(x for x in pkg.model.elements if x.get("tag") == 30)
    e.update(etype="elasticBeamColumn", release=["-releasez", 3])
    with pytest.raises(ValueError, match="needs an unreleased ElasticTimoshenkoBeam"):
        NM.build_nonlinear(pkg, HM.load_params(None, jurisdiction="india"), {}, verbose=False, plasticity="fibre")


def _push_hard(tmp, n=10, counter=None):
    """The one-bay EBF push (Y) with a first attempt that fails after yield (Newton, 3 iterations at 1e-10) and the
    pushover's own fallback ladder (NM._try_analyze) -- REAL failed OpenSees calls, as the step cuts of a pushover."""
    import openseespy.opensees as ops
    from pushover import nonlinear_model as NM, hinge_models as HM
    os.environ["SNL_PLASTICITY"] = "fibre"
    pkg = _ebf_pkg("Y", tmp)
    NM.build_nonlinear(pkg, HM.load_params(None, jurisdiction="india"), {}, verbose=False, plasticity="fibre")
    wl = [0.0, -30.0, 0.0]
    loads = {"_hr": {"ele": [[30, 0.0, 1.0, "beamUniform", wl], [21, 0.0, 1.0, "beamUniform", wl],
                             [22, 0.0, 1.0, "beamUniform", wl]], "node": {}}}
    assert NM._apply_gravity(loads) == 0
    ops.timeSeries("Linear", 2); ops.pattern("Plain", 2, 2); ops.load(9, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    du = 0.01 * H / n
    ops.integrator("DisplacementControl", 9, 2, du); ops.analysis("Static")
    rows = []
    for _ in range(n):
        ops.test("NormDispIncr", 1e-10, 3, 0); ops.algorithm("Newton")
        if ops.analyze(1) != 0:
            assert NM._try_analyze(du, 9, 2)
        ops.reactions()
        rows.append((ops.nodeDisp(9, 2), -sum(ops.nodeReaction(t, 2) for t in (1, 2))))
    return rows


def test_chunked_pushover_with_real_failed_steps_repeats_the_uninterrupted_one(tmp_path):
    """Review (weak tests): a real OpenSees push whose step attempts fail and fall back (6 failed calls in 16),
    interrupted after 7 live calls -- past a failed one -- and resumed in a rebuilt model. The journaled failures are
    answered without calling OpenSees, and the curve is the uninterrupted one to 1e-9 -- NOT bit for bit: a failed
    analyze is not perfectly state-neutral in OpenSees, so skipping it changes the last digits (here ~1e-15 relative;
    the documented limit of snl/checkpoint.py), well inside the replay's fingerprint tolerance."""
    import contextlib, io
    import openseespy.opensees as ops
    from snl import checkpoint as CK
    with contextlib.redirect_stderr(io.StringIO()):
        full = _push_hard(str(tmp_path))
        path = str(tmp_path / "hard.ckpt")
        real = ops.analyze
        J = CK.Journal(path, key="hard", max_live_calls=7).begin("push Y", ops)
        with pytest.raises(CK.ChunkExpired):
            _push_hard(str(tmp_path))
        J.end()
        seg = J.data["segments"]["push Y"]
        assert len(seg) == 7 and any(ok != 0 for ok, *_ in seg)              # a failed call inside the chunk
        n_real = [0]

        def counted(*a):
            n_real[0] += 1
            return real(*a)
        ops.analyze = counted
        try:
            J2 = CK.Journal(path, key="hard").begin("push Y", ops)
            again = _push_hard(str(tmp_path))
            J2.end()
        finally:
            ops.analyze = real
    calls = J2.data["segments"]["push Y"]
    failed_in_chunk1 = sum(1 for ok, *_ in seg if ok != 0)
    # 17 journaled calls: the gravity analysis and the 16 calls of the push (6 failed)
    assert len(again) == len(full) and len(calls) == 17 and sum(1 for ok, *_ in calls if ok != 0) == 6
    for (u0, v0), (u1, v1) in zip(full, again):
        assert u1 == pytest.approx(u0, rel=1e-9) and v1 == pytest.approx(v0, rel=1e-9)
    assert max(abs(v1 - v0) / abs(v0) for (_, v0), (_, v1) in zip(full, again) if v0) < 1e-12
    assert n_real[0] == len(calls) - failed_in_chunk1                       # the journaled failures were not recomputed


def test_pushover_cli_restores_a_finished_direction(tmp_path, monkeypatch):
    """Review (weak tests): the pushover CLI's journal path. Chunk 1 finishes X and runs out inside Y (exit 75); chunk 2
    restores X from the journal (no push) and replays and finishes Y. Both directions' results equal an uninterrupted
    run's."""
    import argparse, types
    from snl import checkpoint as CK
    from pushover import cli as PC, nonlinear_model as NM, member_response as MR, postprocess as PP, report_india as RI
    from nlrha import india_hazard as IH
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    ops = _FakeOps(set())
    monkeypatch.setattr(NM, "ops", ops)
    pushed = []

    def fake_push(pkg, hinges, d, loads, prm, **kw):
        pushed.append(d)
        ops.t, ops.u, ops.n = 0.0, 0.0, 0                           # a new model (build_nonlinear wipes)
        u, V = [0.0], [0.0]
        for i in range(3):
            assert NM.ops.analyze(1) == 0
            u.append(ops.getTime()); V.append(100.0 * ops.getTime() * (1.0 if d == "X" else 2.0))
        return dict(rec=dict(u=u, V=V), stop_reason="reached max roof drift", tail=None)
    monkeypatch.setattr(NM, "pushover", fake_push)
    monkeypatch.setattr(NM, "gravity_loads", lambda pkg, prm: ({}, [dict(W_kN=1.0)]))
    monkeypatch.setattr(NM, "column_gravity_axials", lambda pkg, loads: {})
    monkeypatch.setattr(NM, "build_nonlinear", lambda pkg, prm, PG: ({}, {}))
    monkeypatch.setattr(MR, "MemberRecorder", lambda pkg, h, s: types.SimpleNamespace(braces=[], meta=lambda: {"m": 1}))
    monkeypatch.setattr(PP, "nsp_target", lambda run, basis, prm, lv: dict(Te=1.0, Sa=0.1, C0=1.0, C1=1.0, C2=1.0,
                                                                            target_disp_in=run["rec"]["u"][-1] / 2, target_over_H=0.01))
    monkeypatch.setattr(PP, "capacity_summary", lambda run, basis, n, V_design_kip=None: dict(Vmax_kN=max(run["rec"]["V"]), Vmax_over_VB=1.0))
    monkeypatch.setattr(PP, "response_at", lambda run, dt, lv, meta, ref, basis, V_design_kip=None: dict(
        base_shear_kN=dt * 10.0, V_over_VB=1.0, max_story_drift=0.001, census=None))
    monkeypatch.setattr(IH, "vb_direction_kN", lambda ind, d: 100.0)
    monkeypatch.setattr(PC, "elastic_check", lambda run, nsp: None)
    monkeypatch.setattr(RI, "write", lambda *a, **k: str(tmp_path / "report.html"))
    monkeypatch.setattr(PC, "_copy_params", lambda *a, **k: None)
    pkg = types.SimpleNamespace(root=str(tmp_path / "job"), calc={},
                                basis=types.SimpleNamespace(india=dict(Z=0.16, I=1.0, soil="II"), system="SCBF", jurisdiction="india"))
    os.makedirs(pkg.root)

    def args(ck):
        return argparse.Namespace(params=None, plasticity="fibre", gravity_elastic=None, member_nseg=4, tail="none",
                                  out=str(tmp_path / ("out_" + ("ck" if ck else "plain"))), max_drift=0.1, stop_at=0.8,
                                  dirs=["X", "Y"], checkpoint_dir=(str(tmp_path / "ck") if ck else None), chunk_seconds=None)
    ref = PC._run_india(args(False), pkg, 0.0)
    real_journal = PC._journal

    def chunk1(a, p):
        J = real_journal(a, p)
        J.max_live_calls = 5                                         # X takes 3 calls, Y runs out at its 3rd
        return J
    monkeypatch.setattr(PC, "_journal", chunk1)
    del pushed[:]
    with pytest.raises(SystemExit) as ex:
        PC._run_india(args(True), pkg, 0.0)
    assert ex.value.code == CK.EXIT_RESUME and pushed == ["X", "Y"]
    monkeypatch.setattr(PC, "_journal", real_journal)
    del pushed[:]
    out = PC._run_india(args(True), pkg, 0.0)
    assert pushed == ["Y"]                                            # X restored, not pushed again
    assert out == ref


def test_words_html_keeps_attribute_values():
    """Review L11: class, id and data-* values keep their keys (the pages' CSS and scripts use them); the text is in words."""
    from snl import public_text as PT
    h = '<tr class="lateral_col" data-role="gravity_col"><td id="r_lateral_col">lateral_col, NO_LIMIT_POINT</td></tr>'
    out = PT.words_html(h)
    assert 'class="lateral_col"' in out and 'data-role="gravity_col"' in out and 'id="r_lateral_col"' in out
    assert ">lateral column, no limit point<" in out


def test_replay_fingerprint_covers_every_node():
    """Review L9: a displacement at node 450 (above the old first-400 window) changes the fingerprint."""
    from snl import checkpoint as CK

    class O:
        u = 0.0
        def getTime(self): return 1.0
        def getNodeTags(self): return list(range(1, 501))
        def nodeDisp(self, n): return [self.u if n == 450 else 0.0]
    o = O()
    a = CK._fingerprint(o); o.u = 1.0
    assert CK._fingerprint(o) != a


def test_a_failed_gravity_record_fails_loudly(tmp_path):
    """Review L10: with an HR engine present, a recording that fails raises GravityRecordFailed -- the record of an
    earlier engine is not kept, and the NL idealisation is not used in its place."""
    import json
    from snl import hr_gravity as HG
    eng = tmp_path / "engine"; eng.mkdir()
    (eng / "static_model.py").write_text("raise ImportError('a broken engine')\\n")
    job = tmp_path / "job"; job.mkdir()
    (job / "cfg.py").write_text("cfg = {}\\n")
    (job / HG.OUT_NAME).write_text(json.dumps(dict(schema=HG.SCHEMA, inputs_sha256=HG._inputs_sha(str(job)),
                                                   engine_sha="an older engine", states={})))
    assert HG.load(str(job))["engine_sha"] == "an older engine"
    with pytest.raises(HG.GravityRecordFailed, match="the record on file .engine an older engine. is not used"):
        HG.ensure(str(job), engine_dir=str(eng), timeout=120)
