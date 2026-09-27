"""NL-10: EBF links are nonlinear -- the HR model's ElasticTimoshenkoBeam becomes a force-based fibre element whose
section carries the IS 18168:2023 11.2 shear yielding V_pL = fy A_wL / sqrt(3) on the vertical shear (Vz)."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _link_push(units):
    import openseespy.opensees as ops
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    from pushover import india_materials as IM
    sec = "WPB260X260X114.4"
    sp = IM.section_props_mm(sec)
    sc = 1.0 if units == "N-mm" else 1 / 25.4
    L = 600.0 * sc                                          # a short (shear) link
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0, 0, 0); ops.node(2, L, 0, 0)
    ops.fix(1, 1, 1, 1, 1, 1, 1); ops.fix(2, 1, 1, 0, 1, 1, 1)   # guided end: vertical translation only (double curvature)
    ops.geomTransf("Linear", 3, 0.0, 0.0, 1.0)
    b = FiberSectionBuilder(ops, Fy=(240.0 if units == "N-mm" else 240.0 / 6.894757293168361), units=units, residual="none")
    b.build(1, sec, "beam", axis="z")
    rec = b.link_aggregator(2, 1, sec, 240.0)
    ops.beamIntegration("Lobatto", 2, 2, 5)
    ops.element("forceBeamColumn", 1, 1, 2, 3, 2, "-iter", 30, 1e-10)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1); ops.load(2, 0, 0, 1.0, 0, 0, 0)
    ops.constraints("Plain"); ops.numberer("Plain"); ops.system("BandGeneral")
    ops.test("NormDispIncr", 1e-9, 50); ops.algorithm("Newton")
    target = 0.05 * L                                       # 0.05 rad link rotation
    n = 200
    ops.integrator("DisplacementControl", 2, 3, target / n); ops.analysis("Static")
    V = []
    for _ in range(n):
        assert ops.analyze(1) == 0
        ops.reactions(); V.append(-ops.nodeReaction(1, 3))
    return rec, V, sp


@pytest.mark.parametrize("units", ["N-mm", "kip-in"])
def test_link_yields_in_shear_at_is18168_vp(units):
    rec, V, sp = _link_push(units)
    Aw = (sp["d"] - 2 * sp["tf"]) * sp["tw"]
    Vp = 240.0 * Aw / math.sqrt(3)
    assert rec["Vp_kN"] == pytest.approx(Vp / 1e3) and "11.2" in rec["clause"] and "modelling assumption" in rec["hardening_basis"]
    f = 1.0 if units == "N-mm" else 4448.2216152605
    Vmax = max(V) * f
    # shear yield governs a short link (Mp / Vp > e / 2): the peak is Vp plus the modelled hardening (< 1.35 Vp at 0.05 rad)
    assert 1.0 * Vp < Vmax < 1.35 * Vp, (Vmax / Vp)
    early = V[2] * f
    assert early < 0.6 * Vp                                  # elastic at the start


def test_link_registry_and_link_groups():
    from pushover.member_response import group_summary
    meta = {"members": {}, "braces": {}, "links": {5: {"section": "WPB260X260X114.4", "level": 1, "Vp_kN": 700.0}}}
    peaks = [{"l": {5: [0.04, 20.0]}}, {"l": {5: [0.06, 30.0]}}]
    g = group_summary(peaks, meta)["link_groups"][0]
    assert g["gamma_max_rad"] == 0.06 and g["reference_rot_rad"] == 0.08 and g["ratio_to_reference"] == pytest.approx(0.75)
    assert "12.3.3.1" in g["reference"] and g["yielded"]
    from nlrha.response_summary import _sfrs_kinds
    assert "link" in _sfrs_kinds("EBF") and "link" not in _sfrs_kinds("SCBF")
