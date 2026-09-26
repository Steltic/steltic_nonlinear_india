"""NL-15: HR packages with zeroLength springs (IN_Ex15 roof-plane springs), patterned gravity (IS 875-4 4.3 partial
snow, crane positions / surge) and vertical earthquake terms, and long axially-restrained beams (IN_Ex13) --
all of which broke the NL models or the DDM gravity-transfer gate on the gold set.

  * pushover.nonlinear_model.member_kind no longer divides by a zero length (zeroLength springs are passed through)
  * steltic_ddm.ingest keeps the zeroLength springs and their uniaxialMaterials; GMNIAModel rebuilds them
  * snl.hr_gravity records one state per snow / crane pattern the HR combinations use; factors_for() picks them
    (and EV for vertical EQ) from Case.meta; combine() refuses a non-zero factor on a state that was not recorded
  * the gate builds with the HR static model's P-Delta transformation (no Corotational catenary tension)
"""
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import hr_gravity as HG  # noqa: E402

GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")
ENGINE = os.environ.get("STELTIC_ENGINE_DIR", "")


def test_member_kind_zero_length_is_not_a_division_by_zero():
    from pushover import nonlinear_model as NM
    pkg = types.SimpleNamespace(schedule={}, model=types.SimpleNamespace(nodes={1: (0.0, 0.0, 0.0), 2: (0.0, 0.0, 0.0),
                                                                             3: (0.0, 0.0, 100.0)}))
    assert NM.member_kind(pkg, {"tag": 9, "n1": 1, "n2": 2}) == "zerolength"
    assert NM.member_kind(pkg, {"tag": 9, "n1": 1, "n2": 3}) == "col"


def test_ingest_keeps_zero_length_springs_and_materials(tmp_path):
    from steltic_ddm import ingest
    p = tmp_path / "model_opensees.py"
    p.write_text("\n".join([
        "ops.wipe()", "ops.model('basic', '-ndm', 3, '-ndf', 6)",
        "ops.node(100101, 0.0, 0.0, 3000.0)", "ops.node(199001, 0.0, 0.0, 3000.0)",
        "ops.uniaxialMaterial('Elastic', 990002, 1000000000.0)",
        "ops.element('zeroLength', 7002000, 199001, 100101, '-mat', 990002, '-dir', 2)"]))
    nodes, fixes, masses, transf, elems, diaph = ingest.parse_replay(str(p))
    assert ingest.parse_replay.uni_materials[990002] == ["Elastic", 990002, 1000000000.0]
    assert any(e[0] == "zeroLength" for e in elems)


def test_gmnia_rebuilds_springs_in_its_own_tag_range():
    import openseespy.opensees as ops
    from steltic_ddm.model_gmnia import GMNIAModel
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0); ops.node(2, 0.0, 0.0, 0.0)
    nm = types.SimpleNamespace(springs=[["zeroLength", 7002000, 1, 2, "-mat", 990002, "-dir", 1, 2]],
                               uni_materials={990002: ["Elastic", 990002, 5.0e8]})
    g = GMNIAModel.__new__(GMNIAModel); g.nm = nm
    g._add_springs()
    assert g.springs[0]["hr_tag"] == 7002000 and g.springs[0]["tag"] == GMNIAModel.SPRING_ELE0 + 1
    assert g.springs[0]["dirs"] == [1, 2]
    assert GMNIAModel.SPRING_ELE0 + 1 in ops.getEleTags()
    ops.wipe()


def test_pattern_keys_and_factors_from_meta():
    assert HG.pattern_key("S", ("X", "lo")) == "S@X,lo"
    assert HG.pattern_key("C", ("L", None)) == "C@L,-"
    f = HG.factors_for(1.5, 1.5, 1.5, {"fS": 1.5, "snow_pattern": ("X", "hi")})
    assert f == {"D": 1.5, "L": 1.5, "Lr": 1.5, "S@X,hi": 1.5}
    f = HG.factors_for(1.2, 1.2, 0.0, {"fC": 1.05, "crane_pattern": ("R", "S+"), "fEv": -0.016, "fS": 1.2})
    assert f["C@R,S+"] == 1.05 and f["EV"] == pytest.approx(-0.016) and f["S"] == 1.2


def test_combine_refuses_unrecorded_state():
    rec = {"states": {"D": {"ele": [], "node": {}}}}
    assert HG.combine(rec, {"D": 1.0, "S@X,lo": 0.0}) == {"ele": [], "node": {}}      # zero factor: fine
    with pytest.raises(KeyError):
        HG.combine(rec, {"D": 1.0, "S@X,lo": 1.5})


def test_gate_uses_the_hr_p_delta_transformation():
    import inspect
    from steltic_ddm import india_checks as IC
    from steltic_ddm.model_gmnia import GMNIAModel
    assert inspect.signature(GMNIAModel.__init__).parameters["transf_type"].default == "Corotational"
    assert inspect.getsource(IC.gravity_gate).count('transf_type="PDelta"') == 2


def _gold(name):
    d = os.path.join(GOLD, name)
    if not (os.path.isdir(d) and ENGINE and os.path.exists(os.path.join(ENGINE, "static_model.py"))):
        pytest.skip("gold job %s or steltic_india engine ($STELTIC_ENGINE_DIR) not available" % name)
    return d


@pytest.mark.parametrize("name", ["IN_Ex15_Gable_warehouse_SMF_SCBF_snow_Shimla", "IN_Ex13_SCBF_bigbox_flexdiaphragm_Indore",
                                  "IN_Ex14_Crane_bay_OMRF_OCBF_Vizag"])
def test_gold_gravity_gate_passes(name, tmp_path):
    import shutil
    src = _gold(name)
    job = tmp_path / name
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html"))
    from steltic_ddm import ingest, loads, india_checks as IC
    nm = ingest.load_package(str(job), ENGINE)
    kept = loads.prune(loads.steltic_combos(nm.cfg, nm=nm))
    g = IC.gravity_gate(nm, nm.cfg, kept)
    assert g["n_compared"] > 30 and g["ok"], g["summary"]
