"""NL-5: raw (replayed) elements of an N-mm HR model are converted with the Stage-B bridge, per element type and per
material usage -- EBF ElasticTimoshenkoBeam links, non-brace trusses, X02 roof-plane zeroLength springs."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover.package_reader import ElasticModel, convert_raw_elements_mm_to_in  # noqa: E402

KSI = 1 / 6.894757293168361


def test_raw_conversion_by_type_and_usage():
    m = ElasticModel()
    m.materials = {1: ["Elastic", 1, 200000.0], 990002: ["Elastic", 990002, 1.0e9]}
    m.elements = [
        dict(tag=10, n1=1, n2=2, etype="Truss", raw=["Truss", 10, 1, 2, 2500.0, 1]),
        dict(tag=275, n1=3, n2=4, etype="ElasticTimoshenkoBeam",
             raw=["ElasticTimoshenkoBeam", 275, 3, 4, 200000.0, 76923.08, 23800.0, 5.48e6, 1.07e9, 1.26e8, 14000.0, 6438.0, 3]),
        dict(tag=7002000, n1=5, n2=6, etype="zeroLength", raw=["zeroLength", 7002000, 5, 6, "-mat", 990002, 1, "-dir", 2, 5]),
    ]
    c = convert_raw_elements_mm_to_in(m)
    assert c["truss"] == 1 and c["timoshenko"] == 1 and c["zerolength"] == 1 and not c["other"]
    tr = m.elements[0]["raw"]
    assert tr[4] == pytest.approx(2500.0 / 25.4 ** 2)
    assert m.materials[tr[5]][2] == pytest.approx(200000.0 * KSI)                     # stress copy of material 1
    tm = m.elements[1]["raw"]
    assert tm[4] == pytest.approx(200000.0 * KSI) and tm[6] == pytest.approx(23800.0 / 25.4 ** 2)
    assert tm[8] == pytest.approx(1.07e9 / 25.4 ** 4) and tm[10] == pytest.approx(14000.0 / 25.4 ** 2) and tm[12] == 3
    zl = m.elements[2]["raw"]
    mf, mm_ = zl[5], zl[6]
    assert m.materials[mf][2] == pytest.approx(1.0e9 / 4448.2216152605 * 25.4)       # N/mm -> kip/in (dir 2)
    assert m.materials[mm_][2] == pytest.approx(200000.0 / 4448.2216152605 / 25.4)   # N-mm/rad -> kip-in/rad (dir 5)
    # idempotent: a second pass converts nothing again
    before = [list(e["raw"]) for e in m.elements]
    convert_raw_elements_mm_to_in(m)
    assert [e["raw"] for e in m.elements] == before
    assert m.materials[1] == ["Elastic", 1, 200000.0]                                # the original is left untouched


def test_non_elastic_raw_material_is_refused():
    m = ElasticModel()
    m.materials = {5: ["Steel01", 5, 250.0, 200000.0, 0.01]}
    m.elements = [dict(tag=1, n1=1, n2=2, etype="Truss", raw=["Truss", 1, 1, 2, 100.0, 5])]
    with pytest.raises(ValueError):
        convert_raw_elements_mm_to_in(m)
