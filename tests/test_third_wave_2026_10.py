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


def test_vmax_is_headlined_up_to_the_mce_target_only():
    from pushover import vmax_policy as VP
    u = [0.0, 50.0, 100.0, 150.0, 2000.0]
    V = [0.0, 400.0, 500.0, 520.0, 1500.0]
    h = VP.vmax_to_target(_dd(u, V, 120.0, stop="solver non-convergence at roof u=78.74 in"))
    assert h["Vmax_kN"] == pytest.approx(508.0) and h["u_mm"] == pytest.approx(120.0)   # interpolated at the target
    assert h["target_reached"] and not h["lower_bound"]                 # the curve passed the target: not a lower bound
    assert h["Vmax_over_VB"] == pytest.approx(5.08) and h["Vmax_over_W"] == pytest.approx(0.508)
    assert h["beyond"]["Vmax_kN"] == 1500.0 and h["beyond"]["lower_bound"]
    assert "information, not the pushover strength" in VP.beyond_text("Y", h) and "≥ 1,500" in VP.beyond_text("Y", h)
    # the curve stopped before the target: the peak of what was computed, a lower bound
    h2 = VP.vmax_to_target(_dd(u[:3], V[:3], 120.0, stop="solver non-convergence at roof u=3.94 in"))
    assert h2["Vmax_kN"] == 500.0 and not h2["target_reached"] and h2["lower_bound"] and h2["beyond"] is None
    assert VP.strength_text(h2) == "≥ 500 kN"


def test_te_below_t1_is_flagged():
    from pushover import vmax_policy as VP
    dd = _dd([0.0, 100.0, 200.0], [0.0, 1.0, 2.0], 150.0, T1=0.984, Te=(0.421, 0.722))
    f = VP.te_flags(dd)
    assert [x[0] for x in f] == ["IS-DBE", "IS-MCE"]
    n = VP.te_note("Y", f)
    assert "below the elastic period T1 = 0.984 s" in n and "0.421" in n
    assert VP.te_flags(_dd([0.0, 100.0], [0.0, 1.0], 50.0, T1=0.984, Te=(0.99, 1.2))) == []


def test_site_index_uses_the_capped_vmax(tmp_path):
    import json
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import build_site_index as BSI
    job = tmp_path / "IN_ExT"
    (job / "pushover").mkdir(parents=True)
    pkg = dict(jurisdiction="india", directions={
        "X": _dd([0.0, 50.0, 100.0, 150.0, 2000.0], [0.0, 400.0, 500.0, 520.0, 1500.0], 120.0,
                 stop="solver non-convergence at roof u=78.74 in", Te=(0.9, 0.9))})
    (job / "pushover" / "pushover_package.json").write_text(json.dumps(pkg))
    out = BSI.pushover_results(str(job))
    assert out["vmax_vb_x"] == 5.1 and out["vmax_vb_text_x"] == "5.1" and not out["vmax_lower_bound_x"]
    assert out["vmax_target_mm_x"] == 120.0 and "1,500" in out["vmax_beyond_text_x"] and out["te_below_t1_x"]
    assert "vmax_lower_bound_note" not in out and "IS-MCE target" in out["vmax_basis"]


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
        calls.append((kind, cmd[:3], "SNL_DEADLINE" in kw["env"], "--chunk-seconds" in cmd))
        return script[kind].pop(0)
    args = argparse_ns(queue=q, budget=7000.0, max_steps=0, dry_run=False, stop_on_failure=False)
    NO.next_steps(args, runner=runner)
    d = NO.load(q)
    assert [c[0] for c in calls] == ["gravity", "pushover", "pushover", "ddm", "report"]
    assert all(c[1][:2] == ["H", "timeout"] and c[2] for c in calls)            # under heavy, with a deadline
    assert [c[3] for c in calls] == [False, True, True, True, False]
    assert all(s["state"] == "done" for s in d["steps"]) and len(d["steps"][1]["chunks"]) == 2
    log = open(q + ".runtime.log").read().splitlines()
    assert len(log) == 5 and "rc=75" in log[1] and "state=resume" in log[1]


def argparse_ns(**kw):
    import argparse
    return argparse.Namespace(**kw)
