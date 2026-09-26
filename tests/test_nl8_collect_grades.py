"""NL-8: `snl collect` reads every grade the design uses (IS 2062 grades, IS 1161 tube grades) and every IS 800 /
IS 18168 rotation reference of a combined system. NL-9: a SCRIPTED transcriber -- an answers file written from
collect_request.json by an agent or a person -- goes through the same quote / value checks as a model."""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snl import collect, rag                                   # noqa: E402
import test_collect as TC                                      # noqa: E402


def _multigrade_job():
    job = TC._job()
    p = os.path.join(job, "design", "calc_package.json")
    calc = json.load(open(p, encoding="utf-8"))
    calc["members"] = (calc.get("members") or [])[:2] + [
        {"id": "lateral_col-BOX400X400X25", "inputs": {"role": "lateral_col", "section": "BOX400X400X25", "grade": "E350 B0"}},
        {"id": "brace-CHS193.7X6.3", "inputs": {"role": "brace", "section": "CHS193.7X6.3", "grade": "YSt 310"}}]
    json.dump(calc, open(p, "w", encoding="utf-8"))
    json.dump({"steel_grade": "E250 B0", "brace_grade": "YSt 310"}, open(os.path.join(job, "design", "cfg_snapshot.json"), "w"))
    lp = os.path.join(job, "load_plan.json")
    d = json.load(open(lp, encoding="utf-8")); d["seismic_summary"]["system"] = "SMRF+SCBF"; json.dump(d, open(lp, "w"))
    return job


def test_every_grade_and_every_reference_is_a_group():
    f = collect.gather(_multigrade_job())
    assert f["grade"] == "E250" and "cfg_snapshot" in f["grade_basis"]
    assert f["other_grades"] == ["E350"] and f["tube_grades"] == ["YST310"]
    n = f["needed"]
    assert n[:3] == ["material", "material@E350", "tube_material@YST310"]
    assert "overstrength" in n and "overstrength@E350" in n
    assert n.count("spectrum") == 1 and n[-1] == "damping"
    defs = [g for g in n if g.startswith("deformation_capacity")]
    assert defs[0] == "deformation_capacity" and "deformation_capacity@IS800:12.8.1" in defs           # SMRF + SCBF parts
    assert collect.plan_for("tube_material@YST310", f)[0][0] == "IS1161"
    assert "YSt 310" in collect.fields_for("tube_material@YST310", f)[0][1]
    assert "E 350" in collect.fields_for("material@E350", f)[0][1]
    assert collect.plan_for("deformation_capacity@IS800:12.8.1", f) == [("IS800", "exact_section", "12.8.1", 0)]


def test_mock_and_validate_cover_the_new_groups():
    f = collect.gather(_multigrade_job())
    got = collect.mock_collect(f, {})
    assert got["material@E350"]["fy_t40_MPa"] == 330.0 and got["tube_material@YST310"]["fy_MPa"] == 310.0
    ok, probs = collect.validate({k: dict(v, source="IS 2062 Table 3, p. 9") for k, v in got.items()}, f["needed"], f)
    assert ok, probs
    bad = dict(got["tube_material@YST310"], fy_MPa=250.0, source="IS 1161:2014 Table 2, p. 6")
    ok, probs = collect.validate({"tube_material@YST310": bad}, ["tube_material@YST310"], f)
    assert not ok and "IS1161_TABLE2" in " ".join(probs["tube_material@YST310"])


