"""NL-33 (PEB): the DDM GMNIA model of a PEB shed and its transfer gate.

* member releases are placed by the member's GEOMETRY: a PEB eave strut between off-grid nodes (198xxx) decoded as a
  "Y" beam while it runs along X, its major pin released global rotation 4 -- the strut's own torsion -- at both ends,
  and the GMNIA stiffness matrix was singular (IN_Ex1: UmfPack "numeric analysis returns 1", ARPACK "starting vector
  is zero"). Horizontal axis-aligned beams keep the global pin, so every earlier gold is unchanged; sloped / skew
  beams and released columns (PEB end-wall posts) get a pin spring on the element's local axes.
* transfer_gate._periods: a single roof master carries all the mass (rank 3); ARPACK cannot return 3 modes and the
  dense LAPACK fallback is O(neq^3) -- the periods come from the exact static condensation on the mass DOFs.

The package tests use the HR gold jobs when present (STELTIC_GOLD_JOBS / STELTIC_NL_REF) and skip otherwise."""
import glob
import io
import contextlib
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import openseespy.opensees as ops  # noqa: E402
from steltic_ddm.model_gmnia import GMNIAModel, PIN_NODE0  # noqa: E402
from steltic_ddm import transfer_gate as TG  # noqa: E402

GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")
NL_REF = os.environ.get("STELTIC_NL_REF", "/home/claude/nl_ref")
ENGINE = os.environ.get("STELTIC_ENGINE_DIR", "")


def test_geometric_dirn():
    g = GMNIAModel.geometric_dirn
    assert g((0, 15000, 11500), (7500, 15000, 11500)) == "X"        # the IN_Ex1 eave strut ele 325 (decoded "Y")
    assert g((0, 0, 0), (0, 7500, 0)) == "Y"
    assert g((0, 0, 0), (0, 0, 10000)) == "Z"
    assert g((0, 0, 10000), (0, 6000, 10600)) == ""                   # a 1:10 rafter in the Y-Z plane
    assert g((0, 0, 0), (3000, 4000, 0)) == ""                        # skew in plan


def test_local_axes_follow_the_opensees_convention():
    g = GMNIAModel.__new__(GMNIAModel)
    x, y = g.local_axes((0, 0, 0), (1000, 0, 0), 3)                    # X beam, vecxz Z: local y = global Y
    assert x == pytest.approx((1, 0, 0)) and y == pytest.approx((0, 1, 0))
    x, y = g.local_axes((0, 0, 0), (0, 1000, 0), 3)                    # Y beam: local y = -X
    assert y == pytest.approx((-1, 0, 0))
    x, y = g.local_axes((0, 0, 10000), (0, 6000, 10600), 3)            # rafter: local y = -X, in-plane bending
    assert y == pytest.approx((-1, 0, 0)) and math.hypot(*x) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        g.local_axes((0, 0, 0), (0, 0, 1000), 3)                       # vecxz parallel to the member


def test_condensed_periods_single_mass_node():
    """A cantilever with its mass at the tip in ux, uy only (mass rank 2): T = 2 pi sqrt(m L^3 / 3 E I)."""
    E, L, m = 200000.0, 5000.0, 10.0
    Iy, Iz = 2.0e8, 5.0e7
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0); ops.node(2, 0.0, 0.0, L)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)
    ops.element("elasticBeamColumn", 1, 1, 2, 1.0e4, E, 80000.0, 1.0e8, Iy, Iz, 1)
    ops.mass(2, m, m, 0.0, 0.0, 0.0, 0.0)
    T = TG._condensed_periods(2, {2: (m, m, 0.0, 0.0, 0.0, 0.0)})
    want = sorted((2 * math.pi * math.sqrt(m * L ** 3 / (3 * E * I)) for I in (Iy, Iz)), reverse=True)
    assert T == pytest.approx(want, rel=1e-6)
    assert TG._condensed_periods(2, {k: (1.0,) * 6 for k in range(20)}) is None   # 120 mass DOFs: not condensed
    ops.wipe()


def _job(root, pattern):
    hits = sorted(glob.glob(os.path.join(root, pattern)))
    if not hits or not ENGINE:
        pytest.skip("gold job %s or STELTIC_ENGINE_DIR not available" % pattern)
    return hits[0]


def _load(job):
    from steltic_ddm import ingest
    with contextlib.redirect_stdout(io.StringIO()):
        nm = ingest.load_package(job, ENGINE)
        cfg = ingest.load_cfg(job, ENGINE)
    return nm, cfg


def _record_pins(monkeypatch):
    calls = []
    orig = GMNIAModel._pin

    def rec(self, grid_node, dup_node, released, axis=None, yp=None):
        calls.append(dict(grid=grid_node, dup=dup_node, released=set(released), axis=axis, yp=yp))
        return orig(self, grid_node, dup_node, released, axis, yp)
    monkeypatch.setattr(GMNIAModel, "_pin", rec)
    return calls


def test_peb_gmnia_is_not_singular_and_matches_the_hr_periods(monkeypatch):
    job = _job(GOLD, "IN_Ex3_PEB_crane_shed*")
    nm, cfg = _load(job)
    calls = _record_pins(monkeypatch)
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 2), elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0,
                   brace_bow=0.0)
    with contextlib.redirect_stdout(io.StringIO()):
        g.build(with_mass=True)
    # the struts whose decoded dirn is wrong are pinned about their own bending axis, never their torsion
    for m in nm.members:
        if m.kind == "beam" and m.relz:
            p1, p2 = g._coord(m.n1), g._coord(m.n2)
            gd = GMNIAModel.geometric_dirn(p1, p2)
            if gd in ("X", "Y"):
                for k in (1, 2):
                    if m.relz in (k, 3):
                        c = next(c for c in calls if c["dup"] == PIN_NODE0 + m.tag * 10 + k)
                        assert (5 if gd == "X" else 4) in c["released"] and c["axis"] is None
    assert any(c["yp"] is not None for c in calls)                    # released end-wall posts: oriented pins
    T_g = TG._periods(3)
    TG._replay(os.path.join(job, "model_opensees.py"))
    T_hr = TG._periods(3, masses=nm.masses)
    # T1 within 0.1 %; T2 / T3 (torsion-coupled) up to 2 % shorter: the fly-brace torsional restraints the HR model
    # does not have (the transfer gate allows 5 %)
    assert len(T_hr) == 3 and T_g[0] == pytest.approx(T_hr[0], rel=0.002) and T_g == pytest.approx(T_hr, rel=0.03)
    ops.wipe()


def test_earlier_golds_keep_the_global_pins(monkeypatch):
    """A pre-PEB gold (grid nodes only): every released beam is horizontal and axis-aligned, so the pins are the
    legacy global ones (major 5 for X beams, 4 for Y beams, minor 6), with no orientation."""
    job = _job(NL_REF, "*SCBF_bigbox_flexdiaphragm_Indore")
    nm, cfg = _load(job)
    calls = _record_pins(monkeypatch)
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 2), elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0,
                   brace_bow=0.0)
    with contextlib.redirect_stdout(io.StringIO()):
        g.build()
    n = 0
    for m in nm.members:
        if m.kind != "beam" or not (m.relz or m.rely):
            continue
        major = 5 if m.dirn == "X" else 4
        for k in (1, 2):
            want = ({major} if m.relz in (k, 3) else set()) | ({6} if m.rely in (k, 3) else set())
            if want:
                c = next(c for c in calls if c["dup"] == PIN_NODE0 + m.tag * 10 + k)
                assert c["released"] == want and c["axis"] is None and c["yp"] is None
                n += 1
    assert n > 0 and all(c["yp"] is None for c in calls)
    ops.wipe()


# ----------------------------------------------------------------------------------------- NL-33 restraint system
def test_fractions_uniform_without_stations_and_station_split():
    g = GMNIAModel.__new__(GMNIAModel)
    m = type("M", (), {"tag": 7})()
    g.peb = None
    assert g._fractions(m, 2) == [0.0, 0.5, 1.0] and g._fractions(m, 4) == [0.0, 0.25, 0.5, 0.75, 1.0]
    g.peb = {"member_fracs": {7: [0.31, 0.49, 0.67, 0.85]}}
    fr = g._fractions(m, 2)
    assert fr[0] == 0.0 and fr[-1] == 1.0 and {0.31, 0.49, 0.67, 0.85} <= set(fr)
    assert max(b - a for a, b in zip(fr, fr[1:])) <= 0.5 + 1e-9          # no sub-element longer than L / nsub
    g.peb = {"member_fracs": {7: [0.9]}}
    assert g._fractions(m, 2) == [0.0, 0.45, 0.9, 1.0]


def test_restraint_plan_reads_flange_braces_like_peb_build():
    from steltic_ddm import peb_restraints as PR
    job = _job(GOLD, "IN_Ex1_PEB_factory_shed*")
    nm, cfg = _load(job)
    p = PR.plan(nm, cfg)
    assert p and not p["skipped"]
    c = p["counts"]
    # IN_Ex1: 28 column chains with FLY_COL = GIRTS (3.1 / 4.9 / 6.7 / 8.5 m); fly braces on the rafters at 1.5 / 3 / 4.5
    # / 6 / 9 / 12 m from each eave; the purlin-only stations (7.5 / 10.5 / 13.5 / 14.7 m) are not modelled
    assert c["studs"] == 28 and c["column_lateral"] == c["column_torsion"] == 112
    assert c["rafter_torsion"] == 132 and c["not_modelled_one_flange"] > 0
    raf = [s for s in p["stations"] if s["member_kind"] == "rafter" and "torsion" in s["kinds"]]
    assert {round(s["at_mm"]) for s in raf} >= {1500, 3000, 4500, 6000, 9000, 12000, 18000, 21000, 24000, 28500}
    assert not any(round(s["at_mm"]) in (7500, 10500, 13500) for s in raf)
    assert all(s["dir"] == 1 for s in raf)                               # frames span Y: out of plane = X
    gable = [s for s in p["stations"] if s["member_kind"] == "column" and s["dir"] == 2]
    assert gable                                                         # gable posts (strong_dir X): restrained in Y


def test_no_plan_for_earlier_golds():
    from steltic_ddm import peb_restraints as PR
    job = _job(NL_REF, "*SCBF_bigbox_flexdiaphragm_Indore")
    nm, cfg = _load(job)
    assert PR.plan(nm, cfg) is None


def test_restrained_peb_gravity_reaches_lambda_one_and_the_studs_follow_the_racking_line(tmp_path):
    """IN_Ex3: 1.5DL + 1.5LL to lambda = 1 with the restraints; a stud tie node stays on the straight line between the
    column base and top. (A copy of the job: snl.hr_gravity caches the HR gravity states in the job folder.)"""
    import shutil
    from steltic_ddm import loads, solver
    from snl import hr_gravity as HG
    src = _job(GOLD, "IN_Ex3_PEB_crane_shed*")
    job = str(tmp_path / os.path.basename(src))
    shutil.copytree(src, job)
    with contextlib.redirect_stdout(io.StringIO()):
        HG.ensure(job)                                                   # runs the HR model (wipes the domain) first
    nm, cfg = _load(job)
    combo = [c for c in loads.steltic_combos(cfg, nm=nm) if c[0] == "1.5DL+1.5LL"][0]   # before the build (it wipes)
    g = GMNIAModel(nm, cfg, nsub=(2, 2, 4), residual="none", out_of_plumb=("X", 0.005), bow=0.001, bow_sign=1,
                   brace_bow=0.001)
    with contextlib.redirect_stdout(io.StringIO()):
        g.build().prepare()
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        g.apply_gravity(combo[1], combo[2], combo[3], loads.present_sets(nm), meta=getattr(combo, "meta", None))
    assert g.peb_made["studs"] > 0 and g.peb_made["missing"] == 0
    solver._solver_settings()
    ops.analysis("Static"); ops.integrator("LoadControl", 0.1)
    assert ops.analyze(1) == 0
    lam = 0.0
    for _ in range(14):
        ops.integrator("LoadControl", 0.1)
        if ops.analyze(1) != 0:
            break
        lam = ops.getLoadFactor(1)
    assert lam >= 1.0 - 1e-9
    # NL-33 warping-equivalent torsion: no spurious twist of the deep welded columns at lambda = 1
    twist = max(abs(ops.nodeDisp(e["n2"], 6)) for e in g.elems if e["kind"] == "col")
    assert twist < 2e-3
    # a stud: base at the column base, top tied to the column top; station ties on the line between them
    stud = g.peb["studs"][0]
    d = stud["dir"]
    zb = ops.nodeCoord(stud["base"])[2]; zt = ops.nodeCoord(stud["top"])[2]
    ut = ops.nodeDisp(stud["top"], d)
    for i in stud["stations"]:
        st = g.peb["stations"][i]
        n = st["target"][1] if st["target"][0] == "node" else g._frac_nodes[(st["target"][1], round(st["target"][2], 9))]
        z = ops.nodeCoord(n)[2]
        assert ops.nodeDisp(n, d) == pytest.approx(ut * (z - zb) / (zt - zb), abs=0.05 + 0.01 * abs(ut))
    ops.wipe()


def test_peb_disclosures(tmp_path):
    import json
    from nlrha import india_authority as IA
    assert IA.peb_disclosures(str(tmp_path)) == []
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "cfg_snapshot.json").write_text(json.dumps({"custom_sections": {
        "TI300-1000X250X14X6": {"type": "tapered_I"}, "WI550X220X10X5": {"type": "welded_I"},
        "BOX400X400X25": {"type": "box"}}}))
    rows = IA.peb_disclosures(str(tmp_path))
    assert [r["id"] for r in rows] == ["peb_welded_plate_fibres"] and rows[0]["n_sections"] == 2
    assert rows[0]["tapered"] == ["TI300-1000X250X14X6"] and "local buckling" in rows[0]["note"]
    (tmp_path / "ddm_results.json").write_text(json.dumps({"options": {"peb_restraints": {
        "summary": "PEB restraints (NL-33 ...)", "counts": {"studs": 28}}}}))
    rows = IA.peb_disclosures(str(tmp_path))
    assert [r["id"] for r in rows] == ["peb_welded_plate_fibres", "peb_ddm_restraints"]
    assert rows[1]["counts"] == {"studs": 28}
    assert any(r["id"] == "peb_welded_plate_fibres" for r in IA.method_disclosures(str(tmp_path)))


def test_warping_equivalent_torsion_on_welded_i():
    import math as _m
    from pushover import india_sections as ISEC
    from steltic_ddm.sections_fiber import FiberSectionBuilder

    class _Ops:
        def __init__(self):
            self.sec = None

        def uniaxialMaterial(self, *a):
            pass

        def section(self, *a):
            self.sec = a

        def fiber(self, *a):
            pass
    ISEC.register_welded_i("WI956X250X14X6", 956, 250, 14, 6)
    p = ISEC.get_mm("WI956X250X14X6")
    o = _Ops(); b = FiberSectionBuilder(o, Fy=350.0, units="N-mm")
    out = b.build(1, "WI956X250X14X6", "col", axis="y")
    assert o.sec[-1] == pytest.approx(b.G * p["J"]) and out["warping_length"] is None
    o = _Ops(); b = FiberSectionBuilder(o, Fy=350.0, units="N-mm")
    out = b.build(1, "WI956X250X14X6", "col", axis="y", warping_length=1500.0)
    want = b.G * p["J"] + _m.pi ** 2 * b.E * p["Cw"] / 1500.0 ** 2
    assert o.sec[-1] == pytest.approx(want) and want > 100 * b.G * p["J"]   # the warping term dominates a deep I
    assert "Lt = 1500 mm" in b.log[-1][-1]


def test_warping_lengths_between_torsional_restraints():
    """L_t per gap between the MODELLED torsional springs (fly braces); a gap ending at a joint without one (base,
    knee, apex) takes twice its length; an element split by a station has one L_t per part."""
    from steltic_ddm import peb_restraints as PR
    job = _job(GOLD, "IN_Ex1_PEB_factory_shed*")
    nm, cfg = _load(job)
    p = PR.plan(nm, cfg)
    wi = p["warping_intervals"]
    bt = {m.tag: m for m in nm.members}
    # portal column top segment (8.75-10 m): last fly brace 8.5 m, the knee (no spring) at 10 m -> 2 x 1.5 m
    tops = [t for t, m in bt.items() if m.kind == "col" and str(m.section).startswith("WI956")]
    assert tops and all(wi[t] == [(0.0, 1.0, pytest.approx(3000.0, abs=1.0))] for t in tops)
    # the 2.5-3.75 m segment is split by the 3.1 m fly brace: below it the base gap (2 x 3.1 m), above it 4.9 - 3.1 m
    seg = [t for t, m in bt.items() if m.kind == "col" and abs(nm.nodes[m.n1][2] - 2500.0) < 1 and
           abs(nm.nodes[m.n2][2] - 3750.0) < 1 and str(m.section).startswith("WI")]
    assert seg
    ivs = wi[seg[0]]
    assert [round(iv[1], 3) for iv in ivs] == [0.48, 1.0]
    assert ivs[0][2] == pytest.approx(6200.0, abs=1.0) and ivs[1][2] == pytest.approx(1800.0, abs=1.0)
    # rafter segment next to the knee: eave (no spring) to the 1.5 m fly brace, 1:10 slope -> 2 x 1.5 m x 1.005
    knee = [t for t, m in bt.items() if m.kind == "beam" and str(m.section).startswith("WI972")]
    assert any(wi.get(t) and wi[t][0][2] == pytest.approx(3000.0 * _hyp10(), rel=1e-3) for t in knee)
    assert p["counts"]["warping_length_mm"][0] > 0


def test_studs_add_no_sway_stiffness_with_imperfections():
    """With out-of-plumb and bows, the studs (uz free) leave the lateral stiffness of the building as it is."""
    job = _job(GOLD, "IN_Ex3_PEB_crane_shed*")
    from steltic_ddm import peb_restraints as PR
    out = {}
    for mode in ("plan", "studs_only_off"):
        nm, cfg = _load(job)
        p = PR.plan(nm, cfg)
        if mode == "studs_only_off":
            p["studs"] = []
        nm._peb_plan = p
        g = GMNIAModel(nm, cfg, nsub=(2, 2, 2), elastic=True, residual="none", out_of_plumb=("Y", 0.005), bow=0.001,
                       brace_bow=0.001)
        with contextlib.redirect_stdout(io.StringIO()):
            g.build()
        master = max(t for t in nm.nodes if t % 100000 == 99999)
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        ops.load(master, 0.0, 1.0e5, 0.0, 0.0, 0.0, 0.0)
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-8, 10, 0); ops.algorithm("Linear"); ops.integrator("LoadControl", 1.0)
        ops.analysis("Static")
        assert ops.analyze(1) == 0
        out[mode] = ops.nodeDisp(master, 2)
        ops.wipe()
    assert out["plan"] == pytest.approx(out["studs_only_off"], rel=0.02)


def _hyp10():
    import math as _m
    return _m.sqrt(1 + 0.1 ** 2)
