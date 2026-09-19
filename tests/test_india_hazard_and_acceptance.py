"""India NL v1 finish: hazard (no USGS), acceptance excerpts, hinge found:false, units."""
from __future__ import annotations
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nlrha import india_authority as IA  # noqa: E402
from nlrha import india_hazard as IH  # noqa: E402


def test_zone_factors_table_3():
    assert IH.ZONE_FACTOR_Z == {"II": 0.10, "III": 0.16, "IV": 0.24, "V": 0.36}
    assert IH.zone_factor("III") == 0.16
    assert IH.zone_factor(4) == 0.24


def test_sa_over_g_plateau_and_tails():
    assert abs(IH.sa_over_g(0.2, "I") - 2.5) < 1e-9
    assert abs(IH.sa_over_g(0.3, "II") - 2.5) < 1e-9
    assert abs(IH.sa_over_g(1.0, "II") - 1.36) < 1e-9  # 1.36/T
    assert abs(IH.sa_over_g(1.0, "III") - 1.67) < 1e-9
    assert IH.sa_over_g(5.0, "I") == 0.25


def test_design_Ah_formula():
    # Ah = (Z/2)*(Sa/g)/(R/I); zone III Z=0.16, soil II T=0.2 Sa/g=2.5, I=1, R=5
    # Ah = 0.08 * 2.5 / 5 = 0.04
    assert abs(IH.design_Ah(0.2, zone="III", I=1.0, R=5.0, soil="II") - 0.04) < 1e-12


def test_build_india_site_hazard_no_usgs():
    hz = IH.build_india_site_hazard(zone="IV", soil="II", I=1.2, R=5.0, T1x=0.8, T1y=1.0)
    assert hz["jurisdiction"] == "india"
    assert hz["india_authoritative"] is True
    assert hz["site"]["Z"] == 0.24
    assert "is1893_design" in hz["targets"]
    assert "mcer_multi_period" not in hz["targets"]
    assert hz["asce_usgs_scaffolding"]["found"] is False
    p, sa, label = IH.target_from_india_hazard(hz)
    assert len(p) == len(sa) > 10 and "IS 1893" in label
    json.dumps(hz)  # serializable


def test_inputs_from_cfg():
    cfg = {"seismic_zone": "V", "soil_type": "I", "importance_factor": 1.5, "R": 4.0}
    pulled = IH.inputs_from_cfg(cfg)
    hz = IH.build_india_site_hazard(cfg=cfg, T1x=1.0, T1y=1.0)
    assert hz["site"]["seismic_zone"] == "V" and hz["site"]["Z"] == 0.36
    assert pulled["I"] == 1.5


def test_india_acceptance_rules_from_excerpts():
    rules = IA.india_acceptance_rules()
    drift = rules["replace_ch16_where_honest"]["storey_drift_limit_ratio"]
    assert drift["value"] == 0.004
    assert "0.004" in drift["excerpt"]
    th = rules["replace_ch16_where_honest"]["time_history_spectrum_compatibility"]
    assert "design acceleration spectrum" in th["excerpt"]
    assert "asce_7_ch16_suite_acceptance" in rules["still_found_false"]


def test_hinge_analogue_found_false():
    h = IA.hinge_analogue_status()
    assert h["found"] is False
    assert "4.5" in h["note"] or "plastic" in h["note"].lower()


def test_storey_drift_limit_helper():
    d = IA.storey_drift_limit_ratio()
    assert d["found"] is True and d["value"] == 0.004 and d["clause"] == "7.11.1.1"


def test_india_units_metric_boundary():
    from snl import india_units as U
    cfg = {
        "units": "metric",
        "story_heights": [3.5, 3.5],
        "bay_x": [6.0],
        "bay_y": [5.0],
    }
    U.apply_metric_geometry(cfg)
    assert abs(cfg["story_heights"][0] - 3.5 * U.M_TO_IN) < 1e-6
    assert cfg["units"] == "kip-in"
    assert abs(U.metric_force_to_kip(4.4482216152605) - 1.0) < 1e-9


def test_india_package_stub_nl_plan_validates():
    stub = os.path.join(ROOT, "examples", "India_package_stub")
    plan = IA.find_nl_plan(job_dir=stub)
    assert plan and plan["jurisdiction"] == "india"
    findings = IA.validate_nl_plan(job_dir=stub)
    assert not any(s == "ERROR" for s, _ in findings)
    assert IA.drift_relief_analogue(job_dir=stub)["found"] is False


def test_nsp_acceptance_tables_found_false():
    st = IA.nsp_acceptance_tables_status()
    assert st["found"] is False
    assert st.get("prefer_fibre") is True
    assert st.get("hinge_params_verified") is False


def test_complete_gate_disclosures_include_found_false():
    rows = IA.complete_gate_disclosures()
    ids = {r.get("id") for r in rows}
    assert "india_nsp_acceptance_tables" in ids
    assert any(r.get("found") is False for r in rows)
