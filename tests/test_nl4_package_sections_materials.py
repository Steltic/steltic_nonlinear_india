"""NL-4: the HR package's built-up BOX sections and per-member steel (grade / fy) reach the NL models.

* boxes: design/cfg_snapshot.json `custom_sections` -> the same plate formulae as steltic_india sections.register_box
  (A, I and J equal to the elasticBeamColumn arguments the HR model_opensees.py exports), sections_db / fibre / IS 800
  helpers resolve them;
* steel: design/calc_package.json members[] (role, section) -> the HR material record (IS 2062 Table 3 by thickness,
  IS 1161 Table 2 for tubes); nl_plan.material stays an EOR override; a kind-only lookup that is ambiguous is flagged."""
import json
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover import india_sections as ISEC, sections_db as SDB, india_materials as IM  # noqa: E402


def test_box_matches_the_hr_formulae_and_model_export():
    p = ISEC.box_props_mm(400, 400, 25, 25)
    # IN_Ex3 model_opensees.py column: A 37500, J 1318359375, I 882812500 (both axes)
    assert p["A"] == pytest.approx(37500.0)
    assert p["Ix"] == pytest.approx(882812500.0) and p["Iy"] == pytest.approx(882812500.0)
    assert p["J"] == pytest.approx(1318359375.0)
    q = ISEC.box_props_mm(400, 450, 25, 25)            # BOX450X400X25: 450 deep (D), 400 wide (B)
    assert q["Ix"] > q["Iy"] and q["d"] == 450 and q["bf"] == 400
    with pytest.raises(ValueError):
        ISEC.box_props_mm(100, 100, 60, 10)


def _pkg(tmp_path, custom=None, members=None, snapshot=None):
    (tmp_path / "design").mkdir(exist_ok=True)
    snap = dict(snapshot or {})
    if custom:
        snap["custom_sections"] = custom
    (tmp_path / "design" / "cfg_snapshot.json").write_text(json.dumps(snap))
    (tmp_path / "design" / "calc_package.json").write_text(json.dumps({"members": members or []}))
    return tmp_path


def test_register_from_package_and_lookups(tmp_path):
    root = _pkg(tmp_path, custom={"BOX500X500X32": {"type": "box", "B_mm": 500, "D_mm": 500, "tf_mm": 32, "tw_mm": 32,
                                                     "source": "built-up welded box"}})
    assert ISEC.register_from_package(root) == ["BOX500X500X32"]
    pin = SDB.props("BOX500X500X32")
    pmm = ISEC.get_mm("BOX500X500X32")
    assert pin["A"] * 25.4 ** 2 == pytest.approx(pmm["A"]) and pin["Ix"] * 25.4 ** 4 == pytest.approx(pmm["Ix"])
    assert "cfg_snapshot" in pin["custom_note"]
    sp = IM.section_props_mm("BOX500X500X32")
    assert sp["box"] and not sp["tube"] and IM.governing_thickness_mm(sp) == 32
    assert IM.buckling_classes(sp)["zz"] == "c"                       # welded box: Table 10 row c, as the HR engine
    cap = IM.section_capacity("BOX500X500X32", 330.0)
    assert cap["Vd_N"] == pytest.approx(2 * (500 - 64) * 32 * 330 / (math.sqrt(3) * 1.10))
    with pytest.raises(KeyError):
        ISEC.register_custom_sections({"X": {"type": "plate_girder"}})


def test_undeclared_box_label_is_parsed_and_flagged():
    p = ISEC.get_mm("BOX450X400X20")
    assert p["d"] == 450 and p["bf"] == 400 and p["tf"] == 20 and "VERIFY" in p["source"]


class _FakeOps:
    def __init__(self):
        self.fibres = []

    def uniaxialMaterial(self, *a):
        pass

    def section(self, *a):
        pass

    def fiber(self, y, z, a, m):
        self.fibres.append((y, z, a))


def test_box_fibre_section_reproduces_A_and_I():
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    ISEC.register_box("BOX450X400X25", 400, 450, 25, 25)
    ops = _FakeOps()
    b = FiberSectionBuilder(ops, Fy=250.0, units="N-mm")
    b.build(1, "BOX450X400X25", "col")                                  # column: depth along local y
    A = sum(f[2] for f in ops.fibres)
    Iz = sum(f[2] * f[0] ** 2 for f in ops.fibres)
    p = ISEC.get_mm("BOX450X400X25")
    assert A == pytest.approx(p["A"], rel=1e-9)
    assert Iz == pytest.approx(p["Ix"], rel=0.01)                       # strong axis within the fibre discretisation
    assert b.log[-1][2] == "BOX"


MEMBERS = [
    {"id": "lateral_col-BOX400X400X25", "inputs": {"role": "lateral_col", "section": "BOX400X400X25", "grade": "E350 B0"},
     "governing_element_result": {"material": {"fy_MPa": 330.0, "fu_MPa": 490.0, "grade": "E350", "t_mm": 25.0,
                                               "thickness_band_mm": ">16-40", "cite": "IS 2062 (Part 1):2025 Table 3"}}},
    {"id": "brace-CHS193.7X6.3", "inputs": {"role": "brace", "section": "CHS193.7X6.3", "grade": "YSt 310"},
     "governing_element_result": {"material": {"fy_MPa": 310.0, "fu_MPa": 450.0, "grade": "YSt 310",
                                               "cite": "IS 1161:2014 Table 2"}}},
    {"id": "floor-WPB300X300X117.03", "inputs": {"role": "floor", "section": "WPB300X300X117.03", "grade": "E250 B0"},
     "governing_element_result": {"material": {"fy_MPa": 240.0, "grade": "E250", "t_mm": 19.0}}},
    {"id": "gravity_col-WPB300X300X117.03", "inputs": {"role": "gravity_col", "section": "WPB300X300X117.03", "grade": "E350 B0"},
     "governing_element_result": {"material": {"fy_MPa": 330.0, "grade": "E350", "t_mm": 19.0}}},
    {"id": "lateral_col-WPB300X300X117.03", "inputs": {"role": "lateral_col", "section": "WPB300X300X117.03", "grade": "E250 B0"},
     "governing_element_result": {"material": {"fy_MPa": 240.0, "grade": "E250", "t_mm": 19.0}}},
]


def test_fy_from_the_package_by_role(tmp_path):
    root = _pkg(tmp_path, custom={"BOX400X400X25": {"type": "box", "B_mm": 400, "D_mm": 400, "tf_mm": 25, "tw_mm": 25}},
                members=MEMBERS, snapshot={"steel_grade": "E250 B0", "brace_grade": "YSt 310", "brace_process": "HFS",
                                           "grade_by_section": {"BOX400X400X25": "E350 B0"}})
    ISEC.register_from_package(root)
    plan = IM.material_plan({}, IM.package_materials(root))
    f = IM.fy_for_member("BOX400X400X25", "lateral_col", plan)
    assert f["fy_MPa"] == 330.0 and f["grade"].startswith("E350") and f["table_fy_MPa"] == 330.0 and not f["flags"]
    t = IM.fy_for_member("CHS193.7X6.3", "brace", plan)
    assert t["fy_MPa"] == 310.0 and "1161" in t["cite"]
    # the same section in two roles with two grades: the role decides
    assert IM.fy_for_member("WPB300X300X117.03", "gravity_col", plan)["fy_MPa"] == 330.0
    assert IM.fy_for_member("WPB300X300X117.03", "floor", plan)["fy_MPa"] == 240.0
    amb = IM.fy_for_member("WPB300X300X117.03", "col", plan)             # kind only: lowest, flagged
    assert amb["fy_MPa"] == 240.0 and any("ambiguous_role" in x for x in amb["flags"])
    # not in the package: the package grade on the IS 2062 table (grade_by_section, then steel_grade)
    g = IM.fy_for_member("WPB260X260X114.4", "floor", plan)
    assert g["grade"] == "E250" and g["fy_MPa"] == 240.0                # tf 21.5 mm -> >16-40 band
    assert plan["default_grade_basis"].startswith("HR package")
    # an EOR grade in nl_plan wins over the package
    plan2 = IM.material_plan({"material": {"grade_by_section": {"BOX400X400X25": "E410"}}}, IM.package_materials(root))
    e = IM.fy_for_member("BOX400X400X25", "lateral_col", plan2)
    assert e["fy_MPa"] == 390.0 and "EOR" in e["source"]


def test_tube_grade_table_and_no_silent_e250_for_yst():
    sp = {"tube": True, "t": 6.3}
    assert IM._fy_from_grade("YSt 310", sp)[:2] == (310.0, 450.0)
    assert IM._fy_from_grade("E350 B0", {"tf": 25, "tw": 25})[0] == 330.0
