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
