"""NL-7: pushover/hinge_params.json is the India file -- IS values or labelled modelling assumptions, no ASCE 41 /
AISC 342 acceptance values, IS 2062 E250 fy (not A992 50 ksi), expected-strength factor 1.0 (not Ry 1.1); the USA
placeholders are only loaded for a USA (non-India) package."""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover import hinge_models as HM  # noqa: E402


def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + "/" + str(k), k, v
            yield from _walk(v, path + "/" + str(k))


def test_india_file_has_no_acceptance_and_is_steel():
    prm = HM.load_params()
    assert prm["jurisdiction"] == "india" and prm["verified"] is False
    keys = {k for _, k, _ in _walk(prm)}
    for bad in ("IO_over_thetay", "LS_over_thetay", "CP_over_thetay", "IO_frac_of_a", "CP_frac_of_b", "IO_over_dc",
                "CP_over_dT", "Pcr_expected_factor", "fema_p695", "C1_site_factor_a"):
        assert bad not in keys, bad
    m = prm["material"]
    assert m["Fy_MPa"] == 250.0 and abs(m["Fy_ksi"] - 250.0 / 6.894757293168361) < 1e-3 and m["Ry_expected"] == 1.0
    assert "IS 2062" in m["source"] and "18168" in m["Ry_basis"]
    for g in ("beam_flexure", "column_flexure", "brace_axial"):
        assert prm[g]["role"] == "modelling_assumption"
    assert prm["damping"]["xi_cap"] == 0.05 and "7.2.4" in prm["damping"]["xi_cap_basis"]
    assert "IS 1893" in prm["gravity_for_pushover"]["expr"]
    txt = json.dumps(prm)
    assert "A992" not in txt and "1.1*(QD" not in txt


def test_usa_file_only_for_usa_packages():
    usa = HM.load_params(jurisdiction="usa")
    assert usa["material"]["Fy_ksi"] == 50.0 and "USA SCAFFOLDING" in usa["_README"][0]
    assert HM.default_params_path("india").endswith(os.path.join("pushover", "hinge_params.json"))
    assert HM.default_params_path(None).endswith(os.path.join("pushover", "hinge_params.json"))


def test_india_backbones_carry_nan_acceptance():
    prm = HM.load_params()
    b = HM.brace_spec("WPB200X200X50.92", 200.0, prm, india={"fye_MPa": 250.0, "hollow_forming": "hot_rolled"})
    assert math.isnan(b.IO) and math.isnan(b.CP_t) and b.Pye_kip > b.Pcre_kip > 0
    c = HM.column_hinge("WPB300X300X100.85", 150.0, 10.0, prm)
    assert math.isnan(c.IO) and not c.force_controlled
