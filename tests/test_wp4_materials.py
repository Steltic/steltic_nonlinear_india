"""WP4.5: IS 2062 Table 3 fy by thickness, expected-strength factor default 1.0, IS 800 7.1.2 Pd, brace strengths."""
from __future__ import annotations
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover import india_materials as IM  # noqa: E402


def test_is2062_bands():
    assert IM.fy_is2062("E250", 10)[0] == 250
    assert IM.fy_is2062("E250", 20)[0] == 240
    assert IM.fy_is2062("E250B", 60)[0] == 230
    assert IM.fy_is2062("E350", 30)[0] == 330


def test_pd_wpb300_3500():
    r = IM.is800_Pd("WPB300X300X100.85", 3500.0, 250.0)
    assert r["Pd_N"] / 1e3 == pytest.approx(2410, rel=0.005)
    assert r["axis"] == "yy" and r["cls"] == "c"


def test_brace_pye_ex1_and_default_factor():
    f = IM.fy_for_member("CHS168.3X8", "brace", IM.material_plan({}))
    assert f["factor"] == 1.0 and f["fye_MPa"] == 250.0
    b = IM.brace_strengths("CHS168.3X8", 4500.0, f["fye_MPa"])
    assert b["Pye_N"] / 1e3 == pytest.approx(1007, rel=0.002)


def test_hinge_brace_spec_india_uses_is_strength():
    from pushover import hinge_models as HM
    from snl.india_units import KIP_TO_N
    prm = HM.load_params()
    s = HM.brace_spec("CHS168.3X8", 4500.0 / 25.4, prm, india=dict(fye_MPa=250.0))
    assert s.Pye_kip * KIP_TO_N / 1e3 == pytest.approx(1007, rel=0.003)
    assert s.Fye_ksi == pytest.approx(36.26, rel=1e-3)


def test_tube_detection_by_type():
    assert IM.is_tube("CHS168.3X8") is True
    assert IM.is_tube("WPB300X300X100.85") is False


def test_reference_rotations():
    assert IM.reference_rotation("SMF")["value"] == 0.04
    assert IM.reference_rotation("SCBF / SBF concentric braces")["value"] == 0.04
    assert IM.reference_rotation("OMRF")["value"] == 0.02
    assert IM.reference_rotation("OCBF")["value"] == 0.02
