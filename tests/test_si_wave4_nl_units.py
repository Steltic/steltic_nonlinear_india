"""SI NL wave 4: Stage C fibre E/areas N-mm twin + Stage D analysis/g/portal helpers."""
from __future__ import annotations
import csv, json, os, sys, tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import india_units as U  # noqa: E402


class _FakeOps:
    """Minimal OpenSees stub that records fibre section calls."""

    def __init__(self):
        self.sections = []
        self.fibers = []
        self.mats = []

    def section(self, *a, **k):
        self.sections.append((a, k))

    def fiber(self, y, z, a, m):
        self.fibers.append((y, z, a, m))

    def uniaxialMaterial(self, *a):
        self.mats.append(a)


def test_set_analysis_units_and_g():
    U.set_analysis_units("kip-in")
    assert U.ANALYSIS_UNITS == "kip-in"
    assert abs(U.g_accel() - 386.4) < 1e-9
    assert abs(U.steel_E() - 29000.0) < 1e-6
    U.set_analysis_units("N-mm")
    assert U.ANALYSIS_UNITS == "N-mm"
    assert abs(U.g_accel({"_nl_analysis_units": "N-mm"}) - 9810.0) < 1e-9
    assert abs(U.steel_E({"_nl_analysis_units": "N-mm"}) - 200000.0) < 1e-6
    assert abs(U.steel_Fy_default({"_nl_analysis_units": "N-mm"}) - 250.0) < 1e-9
    U.set_analysis_units("kip-in")  # restore for other tests


def test_display_scale_native_nmm_analysis():
    U.set_analysis_units("N-mm")
    sc = U.display_scale({"units": "N-mm", "_nl_analysis_units": "N-mm"})
    assert sc["si"] is True and sc["analysis"] == "N-mm"
    assert abs(sc["force_div"] - 1000.0) < 1e-12
    assert abs(sc["moment_div"] - 1.0e6) < 1e-6
    U.set_analysis_units("kip-in")


def test_fibre_builder_si_mb300_E_and_area():
    """Stage C golden: MB300 fibre under units=N-mm uses E=2e5 MPa and mm² areas."""
    from steltic_ddm.sections_fiber import FiberSectionBuilder, is808_shapes

    assert "MB300" in is808_shapes() or "MB300" in {k.replace(" ", "") for k in is808_shapes()}
    ops = _FakeOps()
    b = FiberSectionBuilder(ops, units="N-mm", residual="none", elastic=True)
    assert abs(b.E - 200000.0) < 1e-6
    assert abs(b.length_scale - 25.4) < 1e-12
    props = b.w_shape(1, "MB300", nf_flange=(4, 2), nf_web=(8, 1), residual="none")
    assert abs(b.E - 200000.0) < 1e-6
    # depth ~ 300 mm
    assert abs(props["d"] - 300.0) < 1.0
    A_fib = sum(a for _, _, a, _ in ops.fibers)
    # IS808 A_si ~ 5860 mm²; fibre mesh without fillets is typically within ~5%
    assert 5000.0 < A_fib < 7000.0
    assert abs(A_fib - props["A"]) / props["A"] < 0.02
    # GJ uses G_MPA
    assert ops.sections and "Fiber" in ops.sections[0][0]


def test_fibre_builder_kip_unchanged_w12():
    """Legacy kip-in path: W12X58 (or first W available) stays inch / ksi."""
    from steltic_ddm.sections_fiber import FiberSectionBuilder, shapes

    labs = [k for k in shapes() if k.startswith("W12X")]
    assert labs
    lab = "W12X58" if "W12X58" in shapes() else labs[0]
    ops = _FakeOps()
    b = FiberSectionBuilder(ops, units="kip-in", residual="none", elastic=True)
    assert abs(b.E - 29000.0) < 1e-6
    props = b.w_shape(1, lab, nf_flange=(4, 2), nf_web=(8, 1), residual="none")
    assert 10.0 < props["d"] < 15.0  # inches
    A_fib = sum(a for _, _, a, _ in ops.fibers)
    assert 10.0 < A_fib < 30.0  # in²


def test_portal_seis_and_udl_nmm():
    from steltic_ddm import portal_adapter as PA

    class M:
        kind = "beam"
        dirn = "X"
        section = "2xC203x76x2p4"
        n1, n2 = 1, 2

    class NM:
        nodes = {1: (0.0, 0.0, 3000.0), 2: (6000.0, 0.0, 4000.0)}

    cfg = {
        "_nl_analysis_units": "N-mm",
        "units": "N-mm",
        "native_nmm": True,
        "spacing_mm": 5000.0,
        "D_roof": 0.5,  # kN/m²
        "Lr": 0.75,
        "_portal_roof_psf": 0.75,
        "seis": {"Ah": 0.1, "R": 5.0, "I": 1.0, "W_frame_kN": 200.0},
    }
    U.set_analysis_units("N-mm")
    V = PA._seis_V(cfg)
    # Ah/(R/I)*W = 0.1/(5/1)*200e3 N = 4000 N
    assert abs(V - 4000.0) < 1e-6
    w = PA.portal_beam_udl(cfg, NM(), M(), 0, 1, 1.0, 0.0, 0.0)
    # p=0.5 kN/m² * (5/2)m = 1.25 kN/m = 1.25 N/mm
    assert abs(w - 1.25) < 1e-9
    U.set_analysis_units("kip-in")


def test_portal_seis_kip_legacy():
    from steltic_ddm import portal_adapter as PA
    U.set_analysis_units("kip-in")
    cfg = {"seis": {"SDS": 1.0, "R": 3.0, "Ie": 1.0, "W_frame_kip": 30.0}}
    assert abs(PA._seis_V(cfg) - 10.0) < 1e-9


def test_native_nmm_skips_kip_bridge():
    from pushover import package_reader as PR
    td = Path(tempfile.mkdtemp(prefix="si_native_"))
    (td / "design").mkdir()
    (td / "model_opensees.py").write_text(
        "import openseespy.opensees as ops\n"
        "ops.wipe()\n"
        "ops.model('basic', '-ndm', 3, '-ndf', 6)\n"
        "ops.node(1, 0.0, 0.0, 0.0)\n"
        "ops.node(2, 6000.0, 0.0, 3500.0)\n"
        "ops.fix(1, 1,1,1,1,1,1)\n"
        "ops.geomTransf('Linear', 1, 0, 1, 0)\n"
        "ops.element('elasticBeamColumn', 1, 1, 2, 15000.0, 200000.0, 76923.0, 1e8, 2e8, 3e8, 1)\n"
    )
    with open(td / "design" / "member_schedule.csv", "w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["ele_tag", "member", "section", "length_mm", "P_comp_N", "Mx_kNm", "governing_combo"],
        )
        w.writeheader()
        w.writerow(dict(ele_tag=1, member="col", section="MB300", length_mm=3500,
                        P_comp_N=1e6, Mx_kNm=100, governing_combo="1.5DL"))
    (td / "design" / "calc_package.json").write_text(json.dumps({
        "building": "SI_native", "units": "N-mm",
        "analysis_si": True, "_nl_analysis_units": "N-mm", "native_nmm": True,
        "members": [],
    }))
    (td / "cfg.py").write_text("units = 'N-mm'\nnative_nmm = True\nheights = [3500]\nsystem = 'SMF'\n")
    (td / "report.html").write_text("<html>W = 1000 kN</html>")
    U.set_analysis_units("kip-in")
    pkg = PR.load(td)
    br = pkg.calc["_nl_unit_bridge"]
    assert br["to"] == "N-mm" and br["analysis"] == "N-mm" and br["stage"] == "D"
    # coords stay mm
    assert abs(pkg.model.nodes[2][0] - 6000.0) < 1e-9
    assert abs(pkg.model.elements[0]["E"] - 200000.0) < 1e-6
    U.set_analysis_units("kip-in")


def test_g_accel_nlrha_helper():
    from nlrha import run as R
    U.set_analysis_units("N-mm")

    class P:
        calc = {"_nl_analysis_units": "N-mm", "units": "N-mm"}

    assert abs(R._g_accel(P()) - 9810.0) < 1e-9
    U.set_analysis_units("kip-in")
    assert abs(R._g_accel(None) - 386.4) < 1e-9
