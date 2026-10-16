"""NL-33: the PEB release of steltic_india (2026-10) -- welded plate I (`welded_I`, WI...) and web-tapered I
(`tapered_I`, TI..., modelled by the HR engine as stepped prismatic welded I segments) reach the NL models.

* the same plate formulae and segment depths as steltic_india sections.register_welded_I / register_tapered_I
  (reference numbers below are the HR engine's own output for WI1000X250X14X6 and TI300-1000X250X14X6);
* sections_db / india_materials / the fibre builder resolve them; Table 10 welded I buckling classes;
* IS 800 Table 2 welded rows and the 3.7.2(d) effective section, as india_is800.effective_section_3_7_2d, set the
  Annex B-1.2 section capacities (semi-compact Ze; slender A_eff / Ze_eff);
* the existing built-up boxes are unchanged."""
import json
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover import india_sections as ISEC, sections_db as SDB, india_materials as IM  # noqa: E402

# steltic_india sections.register_welded_I("WI1000X250X14X6", 1000, 250, 14, 6) (HR engine output, 2026-10-14)
HR_WI1000 = dict(A=12832.0, Ix=2160622357.333, Iy=36475829.333, Zx=4868176.0, Zy=446248.0, Sx=4321244.715,
                 Sy=291806.635, J=527317.333, Cw=8861161458333.334)
# steltic_india sections.register_tapered_I("TI300-1000X250X14X6", 300, 1000, 250, 14, 6, n_seg=8)["segments"]
HR_TI_SEGMENTS = ["WI344X250X14X6", "WI431X250X14X6", "WI519X250X14X6", "WI606X250X14X6", "WI694X250X14X6",
                  "WI781X250X14X6", "WI869X250X14X6", "WI956X250X14X6"]
# steltic_india india_is800.effective_section_3_7_2d("WI1000X250X14X6", fy, welded=True)
HR_EFF = {350.0: dict(A_eff_mm2=8277.87, Ze_eff_mm3=3675277.74, Ze_eff_minor_mm3=291806.63),
          330.0: dict(A_eff_mm2=8316.03, Ze_eff_mm3=3718537.43, Ze_eff_minor_mm3=291806.63)}


def test_welded_i_matches_the_hr_formulae():
    p = ISEC.welded_i_props_mm(1000, 250, 14, 6)
    for k, v in HR_WI1000.items():
        assert p[k] == pytest.approx(v, rel=1e-8), k   # reference values rounded to 0.001
    assert p["section_type"] == "welded_i" and p["Aw"] == pytest.approx((1000 - 28) * 6)
    with pytest.raises(ValueError):
        ISEC.welded_i_props_mm(20, 250, 14, 6)


def test_tapered_segments_match_the_hr_stepped_model():
    rec = ISEC.register_tapered_i("TI300-1000X250X14X6", 300, 1000, 250, 14, 6, n_seg=8)
    assert rec["segments"] == HR_TI_SEGMENTS
    assert all(ISEC.is_welded_i(s) for s in rec["segments"])
    assert ISEC.get_mm("WI344X250X14X6")["d"] == 344


def _pkg(tmp_path, custom):
    (tmp_path / "design").mkdir(exist_ok=True)
    (tmp_path / "design" / "cfg_snapshot.json").write_text(json.dumps({"custom_sections": custom}))
    return tmp_path


def test_register_from_package_welded_and_tapered(tmp_path):
    root = _pkg(tmp_path, {
        "TI300-1000X250X14X6": {"type": "tapered_I", "D_start_mm": 300.0, "D_end_mm": 1000.0, "bf_mm": 250.0,
                                "tf_mm": 14.0, "tw_mm": 6.0, "n_seg": 8, "source": "web-tapered welded I, IS 2062 E350"},
        "WI550X220X10X5": {"type": "welded_I", "D_mm": 550.0, "bf_mm": 220.0, "tf_mm": 10.0, "tw_mm": 5.0},
        "BOX400X400X25": {"type": "box", "B_mm": 400, "D_mm": 400, "tf_mm": 25, "tw_mm": 25}})
    labels = ISEC.register_from_package(root)
    assert labels[:8] == HR_TI_SEGMENTS and "WI550X220X10X5" in labels and "BOX400X400X25" in labels
    assert ISEC.is_box("BOX400X400X25") and not ISEC.is_welded_i("BOX400X400X25")
    assert ISEC.is_welded_i("WI550X220X10X5") and not ISEC.is_box("WI550X220X10X5")
    pin = SDB.props("WI550X220X10X5")
    pmm = ISEC.get_mm("WI550X220X10X5")
    assert pin["A"] * 25.4 ** 2 == pytest.approx(pmm["A"]) and pin["Ix"] * 25.4 ** 4 == pytest.approx(pmm["Ix"])
    assert pin["Type"] == "WELDED_I" and not pin["box"] and pin["welded_i"]
    assert pin["h_tw"] == pytest.approx((550 - 20) / 5)
    with pytest.raises(KeyError):
        ISEC.register_custom_sections({"X": {"type": "plate_girder"}})


def test_undeclared_wi_label_is_read_from_the_designation():
    p = ISEC.get_mm("WI731X200X12X6")
    assert (p["d"], p["bf"], p["tf"], p["tw"]) == (731, 200, 12, 6) and "designation" in p["source"]


def test_materials_buckling_class_and_thickness():
    sp = IM.section_props_mm("WI1000X250X14X6")
    assert sp["welded_i"] and not sp["box"] and not sp["tube"] and sp["type"] == "WELDED_I"
    assert IM.governing_thickness_mm(sp) == 14
    assert IM.buckling_classes(sp)["zz"] == "b" and IM.buckling_classes(sp)["yy"] == "c"
    ISEC.register_welded_i("WI700X300X45X14", 700, 300, 45, 14)
    assert IM.buckling_classes(IM.section_props_mm("WI700X300X45X14"))["zz"] == "c"


@pytest.mark.parametrize("fy", [350.0, 330.0])
def test_effective_section_matches_the_hr_engine(fy):
    e = IM.welded_i_effective("WI1000X250X14X6", fy)
    for k, v in HR_EFF[fy].items():
        assert e[k] == pytest.approx(v, abs=0.02), k
    c = IM.welded_i_class("WI1000X250X14X6", fy)
    assert c["cls"] == "slender" and c["flange"] == "semi-compact" and c["web"] == "slender"


def test_b12_capacity_uses_the_class():
    fy = 350.0
    slender = IM.section_capacity("WI1000X250X14X6", fy)
    assert slender["section_class"] == "slender"
    assert slender["Nd_N"] == pytest.approx(HR_EFF[fy]["A_eff_mm2"] * fy / 1.10, rel=1e-6)
    assert slender["Mdz_Nmm"] == pytest.approx(HR_EFF[fy]["Ze_eff_mm3"] * fy / 1.10, rel=1e-6)
    assert slender["Vd_N"] == pytest.approx((1000 - 28) * 6 * fy / (math.sqrt(3) * 1.10))
    semi = IM.section_capacity("WI300X180X8X5", fy)                # flange 11.25 > 9.4 eps -> semi-compact
    assert semi["section_class"] == "semi-compact"
    assert semi["Mdz_Nmm"] == pytest.approx(ISEC.get_mm("WI300X180X8X5")["Sx"] * fy / 1.10)
    ISEC.register_welded_i("WI400X200X16X12", 400, 200, 16, 12)   # stocky plates -> plastic: Zp
    plastic = IM.section_capacity("WI400X200X16X12", 250.0)
    assert plastic["section_class"] in ("plastic", "compact")
    assert plastic["Mdz_Nmm"] == pytest.approx(ISEC.get_mm("WI400X200X16X12")["Zx"] * 250.0 / 1.10)


class _FakeOps:
    def __init__(self):
        self.fibres = []

    def uniaxialMaterial(self, *a):
        pass

    def section(self, *a):
        pass

    def fiber(self, y, z, a, m):
        self.fibres.append((y, z, a))


@pytest.mark.parametrize("axis", ["y", "z"])
def test_welded_i_fibre_section_reproduces_A_and_I(axis):
    from steltic_ddm.sections_fiber import FiberSectionBuilder, elastic_props
    ISEC.register_welded_i("WI956X250X14X6", 956, 250, 14, 6)
    ops = _FakeOps()
    b = FiberSectionBuilder(ops, Fy=350.0, units="N-mm")
    out = b.build(1, "WI956X250X14X6", "col" if axis == "y" else "beam", axis=axis)
    p = ISEC.get_mm("WI956X250X14X6")
    A = sum(a for _, _, a in ops.fibres)
    depth = [(y if axis == "y" else z) for y, z, _ in ops.fibres]
    I = sum(a * d ** 2 for (_, _, a), d in zip(ops.fibres, depth))
    assert A == pytest.approx(p["A"], rel=1e-9) and out["A"] == pytest.approx(p["A"])
    assert I == pytest.approx(p["Ix"], rel=0.002)                  # fibre layers: within 0.2 % of the exact Ix
    assert "no residual stress" in b.log[-1][-1] and "local buckling not modelled" in b.log[-1][-1]
    A_in, Ix_in, _, _ = elastic_props("WI956X250X14X6")
    assert A_in * 25.4 ** 2 == pytest.approx(p["A"])


def test_boxes_unchanged():
    p = ISEC.box_props_mm(400, 400, 25, 25)
    assert p["A"] == pytest.approx(37500.0) and p["section_type"] == "box"
    ISEC.register_box("BOX400X400X25", 400, 400, 25, 25)
    sp = IM.section_props_mm("BOX400X400X25")
    assert sp["box"] and not sp["welded_i"] and IM.buckling_classes(sp)["zz"] == "c"
    cap = IM.section_capacity("BOX400X400X25", 330.0)
    assert cap["section_class"] is None and cap["Mdz_Nmm"] == pytest.approx(p["Zx"] * 330.0 / 1.10)
